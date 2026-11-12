"""Explicit, resumable project migration. Reading a plan never deletes content.

python -m dashboard_runtime.cos_migrate --project NAME --workspace PATH
Add --apply to upload, verify, atomically switch references and remove PG rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from .cloud_assets import CloudAssets
from .cloud_project import CloudProjectStore
from .model import DashboardError, json_bytes, require


def _identity(snapshot):
    return json_bytes({
        'documents': sorted(snapshot['documents'], key=lambda d: (d['source'], d['board'], d['revision'], json.dumps(d['document'], sort_keys=True))),
        'datasets': sorted(snapshot['datasets'], key=lambda d: d['version']),
    })


def migrate(project, workspace, apply=False, partition_fields=None):
    assets = CloudAssets(project)
    original = assets.call('migration_snapshot')
    result = {'project': project, 'format': original['format'], 'datasets': len(original['datasets']),
              'documents': sum(d['source'] in ('draft', 'checkpoint', 'release') for d in original['documents']),
              'logicalBytes': sum(d.get('bytes', 0) for d in original['datasets']),
              'unfinishedChunks': original['unfinishedChunks'],
              'action': 'already_migrated' if original['format'] == 'cos-v1' else 'plan'}
    if not apply or original['format'] == 'cos-v1':
        return result
    require(original['unfinishedChunks'] == 0,
            'Unfinished data chunks require transfer recovery or explicit cleanup before migration', 'DATA_INCOMPLETE')
    with tempfile.TemporaryDirectory(prefix='charts-cos-migrate-') as temporary:
        store = CloudProjectStore(Path(workspace) / project, Path(temporary))
        store.data.partition_fields = partition_fields or []
        for ref in original['datasets']:
            obj = assets.call('object_get', version=ref['version'])
            if obj is None:
                # Legacy hydration validates the original content address once.
                with store.data._connect() as db:
                    store.data._version(db, ref)
                obj = assets.save_dataset(store.data, ref)
            metadata = obj['descriptor']['metadata']
            require(metadata == ref, 'Dataset metadata changed', 'DATA_CONFLICT')
            # Re-read uploaded bytes before deleting the only PG row copy.
            count = 0
            import gzip
            for name in obj['descriptor']['shards']:
                content = json.loads(gzip.decompress(assets.read_file(obj, name)))
                count += len(content['rows'] if isinstance(content, dict) else content)
            require(count == ref['rowCount'], 'Uploaded dataset row count differs', 'DATA_INCOMPLETE')
            assets.read_file(obj, 'query.sqlite3')
        store.cos_enabled = store.data.cos_enabled = True
        documents = []
        by_content = {}
        for entry in original['documents']:
            if entry['source'] not in ('draft', 'checkpoint', 'release'):
                continue
            doc = assets.hydrate_document(entry['document'])
            # Full legacy payloads are compacted once before becoming immutable.
            doc = store.compact(doc)
            digest = hashlib.sha256(json_bytes(doc)).hexdigest()
            if digest not in by_content:
                by_content[digest] = store._encode(doc)
                read_back = assets.hydrate_document(by_content[digest])
                require(read_back['manifest'] == doc['manifest'] and read_back['snapshot'] == doc['snapshot'],
                        'Uploaded version differs', 'DATA_CONFLICT')
            documents.append({**entry, 'document': by_content[digest]})
        from .cloud_shares import CloudShares
        CloudShares.from_environment().index_project(store)
        latest = assets.call('migration_snapshot')
        require(_identity(original) == _identity(latest),
                'Project changed while migrating; rerun without deleting source data', 'PLAN_CHANGED')
        switched = assets.call('migration_commit', epoch=latest['epoch'], documents=documents,
                               partitionFields=partition_fields or [])
        return {**result, **switched, 'action': 'migrated'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--partition-field', action='append', default=[])
    args = parser.parse_args()
    import re
    require(re.fullmatch(r'[A-Za-z0-9_-]{1,64}', args.project) is not None, 'Invalid project')
    try:
        result = migrate(args.project, args.workspace, args.apply, args.partition_field)
        print(json.dumps(result, ensure_ascii=False))
    except DashboardError as error:
        print(json.dumps(error.as_dict(), ensure_ascii=False))
        return 2
    except Exception as error:
        print(json.dumps({'ok': False, 'error': {'code': 'MIGRATION_FAILED', 'type': type(error).__name__}}))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
