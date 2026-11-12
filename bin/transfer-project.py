#!/usr/bin/env python3
"""Transfer explicitly selected current dashboard datasets to a cloud MCP server."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard_runtime.model import validate
from dashboard_runtime.remote_client import (
    TRANSFER_TOOLS, TransferClient, call_tool, check_source,
    connect, connection_settings, require_tools, run_command,
)


def read_project(manifest):
    root = Path(manifest['projectRoot']).resolve()
    uri = (root / 'dashboards' / 'dashboards.sqlite3').as_uri() + '?mode=ro'
    docs, refs = {}, {}
    with sqlite3.connect(uri, uri=True) as db:
        for page in manifest['pages']:
            board = page['dashboardId']
            row = db.execute('SELECT revision,document FROM boards WHERE id=?', (board,)).fetchone()
            if row is None or row[0] != page['draftRevision']:
                raise ValueError(f'{board}: draft revision changed; rebuild the manifest')
            doc = json.loads(row[1])
            if any(c.get('kind') == 'chart' for c in doc['manifest']['components'].values()):
                raise ValueError(f'{board}: native chart components cannot be imported by dashboard_create')
            notes = db.execute('SELECT payload FROM annotations WHERE board_id=?', (board,)).fetchone()
            doc['manifest']['annotations'] = json.loads(notes[0]) if notes else []
            if len(doc['manifest']['components']) != page['componentCount']:
                raise ValueError(f'{board}: component count changed')
            chosen = {item['id']: item for item in page['datasets']}
            if len(chosen) != len(page['datasets']):
                raise ValueError(f'{board}: duplicate dataset in manifest')
            snapshot = doc['snapshot']
            if snapshot.get('datasets') or snapshot.get('componentDataRefs'):
                raise ValueError(f'{board}: inline or component datasets require an explicit migration plan')
            for key, item in chosen.items():
                ref = snapshot['datasetRefs'][key]
                if any(ref.get(k) != item[k] for k in ('version', 'rowCount', 'bytes')):
                    raise ValueError(f'{board}/{key}: manifest data reference changed')
                prior = refs.setdefault(ref['version'], ref)
                if prior != ref:
                    raise ValueError('Conflicting immutable reference metadata')
            used = {c.get('datasetId') for c in doc['manifest']['components'].values() if c.get('datasetId')}
            used.update(c['binding']['datasetId'] for c in doc['manifest']['components'].values() if c.get('binding'))
            if not used <= set(chosen):
                raise ValueError(f'{board}: manifest omits a component dataset')
            doc['manifest']['datasets'] = {k: v for k, v in doc['manifest']['datasets'].items() if k in chosen}
            doc['manifest']['metrics'] = {k: v for k, v in doc['manifest']['metrics'].items() if v['datasetId'] in chosen}
            snapshot['datasetRefs'] = {k: v for k, v in snapshot['datasetRefs'].items() if k in chosen}
            for source in doc['manifest']['sources'].values():
                source['verification'] = 'supplied'
            validate(doc)
            docs[board] = doc
    return root, docs, refs


def normalized(doc):
    doc = json.loads(json.dumps(doc))
    for key in ('dataVersion', 'computed', 'progressive', 'loading'):
        doc.pop(key, None)
    doc['revision'] = 1
    return doc


async def run(args):
    manifest = json.loads(Path(args.manifest).read_text())
    root, docs, refs = read_project(manifest)
    endpoint, token = connection_settings()
    for ref in refs.values():
        check_source(root, ref)
    async with connect(endpoint, token) as session:
        await require_tools(session, {**TRANSFER_TOOLS,
            'dashboard_list': set(), 'dashboard_get': {'dashboardId'},
            'runtime_result_chunk': {'requestId', 'index'},
            'dashboard_create': {'dashboardId', 'document'}})
        async def call(name, arguments):
            return await call_tool(session, args.project, name, arguments)
        client = TransferClient(call, root, endpoint, args.project, args.state,
                                concurrency=args.concurrency)
        if args.resume_staged and args.resume_staged not in refs:
            raise ValueError('The staged version must exist in the manifest')
        existing = {item['id'] for item in (await call('dashboard_list', {}))['dashboards']}
        for board in existing & docs.keys():
            actual = (await call('dashboard_get', {'dashboardId': board}))['document']
            if normalized(actual) != normalized(docs[board]):
                raise ValueError(f'{board}: destination exists and differs; refusing to overwrite')
        if args.check_only:
            print(json.dumps({'checkedPages': len(docs), 'checkedDatasets': len(refs)}))
            return
        for version, ref in refs.items():
            await client.transfer(ref, resume_staged=version == args.resume_staged)
        for board, doc in docs.items():
            if board not in existing:
                await call('dashboard_create', {'dashboardId': board, 'document': doc})
            if board not in client.state['created']:
                client.state['created'].append(board)
                client.save()
            print(f'Imported {board}; run dashboard_checkpoint before publishing', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--state', required=True, help='Private resumable state file')
    parser.add_argument('--resume-staged', help='One existing data version already fully staged by an older client')
    parser.add_argument('--concurrency', type=int, choices=range(1, 5), default=4)
    parser.add_argument('--check-only', action='store_true', help='Validate source and remote capabilities without uploading')
    args = parser.parse_args()
    run_command(run(args), args.state)


if __name__ == '__main__':
    main()
