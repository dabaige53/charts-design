"""Immutable COS packages and the PostgreSQL reference/operation registry."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

from .cloud_database import CloudDatabase
from .cloud_files import CloudFiles
from .model import DashboardError, json_bytes, require


def parquet_resources(receipt):
    """Browser resources shared by immutable datasets and converted publications."""
    descriptor = {
        'dataFormat': receipt['format'],
        'shards': [item['path'] for item in receipt['files']],
        'options': {field: {'field': field, 'files': [item['path'] for item in files]}
                    for field, files in receipt['options'].items()},
    }
    if receipt.get('partitionIndex'):
        descriptor['partitionIndex'] = copy.deepcopy(receipt['partitionIndex'])
    return descriptor


class AssetDatabase(CloudDatabase):
    def __init__(self):
        super().__init__()
        self.url = self.url.rsplit('/', 1)[0] + '/charts_assets'


class CloudAssets:
    def __init__(self, project, database=None, storage=None):
        self.project = project
        self.database = database or AssetDatabase()
        self._storage = storage

    @property
    def storage(self):
        if self._storage is None:
            self._storage = CloudFiles().storage
        return self._storage

    def call(self, action, **payload):
        return self.database.call(action, self.project, **payload)

    def read_file(self, obj, name) -> bytes:
        entry = obj['descriptor']['files'].get(name)
        require(entry is not None, 'Object file is not registered', 'NOT_FOUND')
        raw = self.storage.get(obj['prefix'] + name)
        if raw is None:
            raise DashboardError('CLOUD_FILE_MISSING', 'COS object is missing')
        require(hashlib.sha256(raw).hexdigest() == entry['sha256'],
                'COS object checksum mismatch', 'CLOUD_FILE_CORRUPT')
        return raw

    def _put(self, obj, files, name, raw, content_type='application/octet-stream'):
        self.storage.put(obj['prefix'] + name, raw, content_type)
        files[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

    def save_dataset(self, data, ref):
        existing = self.call('object_get', version=ref['version'])
        if existing:
            return existing
        from .columnar import copy_package, export_format
        from .local_data import LocalData

        _, binary = export_format('parquet')
        partition_field = next((field for field in getattr(data, 'partition_fields', [])
                                if ref['fields'].get(field, {}).get('type') in ('date', 'string')), None)
        # CloudData resolves remote objects when reading. This dataset is not
        # ready yet, so export the validated local table through the base reader.
        local = LocalData(data.root)
        with tempfile.TemporaryDirectory(prefix='charts-data-') as temporary:
            package = Path(temporary) / 'package'
            package.mkdir()
            receipt = copy_package(package, local, ref, data.root / 'parquet-cache', binary,
                                   partition_field=partition_field, include_options=True)
            # Copy the validated table in SQLite, not through Python row decoding.
            target = Path(temporary) / 'query.sqlite3'
            with closing(sqlite3.connect(target)) as db, db:
                db.execute('ATTACH DATABASE ? AS source', (str(local.path),))
                table = 'd_' + ref['version']
                db.execute(f'CREATE TABLE {table} AS SELECT * FROM source.{table} ORDER BY rowid')
                db.execute('CREATE TABLE versions(version TEXT PRIMARY KEY, metadata TEXT NOT NULL)')
                db.execute('INSERT INTO versions VALUES(?,?)', (ref['version'], json.dumps(ref)))
                for index in range(len(ref['fieldOrder'])):
                    db.execute(f'CREATE INDEX i_{index} ON {table}(c{index})')
            obj = self.call('reserve', id=uuid.uuid4().hex, kind='dataset', version=ref['version'])
            files, pending = {}, deque()
            resources = [*receipt['files'], *(item for entries in receipt['options'].values() for item in entries)]
            # Bound buffered objects and await every upload before marking ready.
            with ThreadPoolExecutor(max_workers=4) as executor:
                for item in resources:
                    if len(pending) == 4:
                        pending.popleft().result()
                    name = item['path']
                    raw = (package / name).read_bytes()
                    pending.append(executor.submit(self.storage.put, obj['prefix'] + name, raw,
                                                   'application/octet-stream'))
                    files[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                while pending:
                    pending.popleft().result()
            self._put(obj, files, 'query.sqlite3', target.read_bytes())
        descriptor = {'format': 'cos-dataset-v1', 'queryFormat': 1, 'metadata': ref,
                      **parquet_resources(receipt), 'files': files,
                      'bytes': sum(entry['bytes'] for entry in files.values())}
        self._put(obj, files, 'manifest.json', json_bytes(descriptor), 'application/json')
        descriptor['bytes'] = sum(entry['bytes'] for entry in files.values())
        return self.call('ready', id=obj['id'], descriptor=descriptor)

    def save_document(self, doc):
        from .build import BACKEND_BUILD_ID
        content = copy.deepcopy(doc)
        content['manifest'].pop('annotations', None)
        identity = {key: content[key] for key in ('id', 'revision', 'manifest', 'snapshot')}
        identity['engineBuild'] = BACKEND_BUILD_ID
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        obj = self.call('object_get', kind='document', version=digest)
        if obj is None:
            obj = self.call('reserve', id=uuid.uuid4().hex, kind='document', version=digest)
            files = {}
            self._put(obj, files, 'document.json', json_bytes(content), 'application/json')
            descriptor = {'format': 'cos-document-v1', 'queryFormat': 1, 'engineBuild': BACKEND_BUILD_ID, 'files': files,
                          'bytes': sum(entry['bytes'] for entry in files.values())}
            self.call('ready', id=obj['id'], descriptor=descriptor)
        # Only the minimum metadata/references needed by transactional operations.
        return {'id': doc['id'], 'revision': doc['revision'], 'cosObject': obj['id'],
                'manifest': {'title': doc['manifest']['title'],
                             'viewMode': doc['manifest'].get('viewMode'),
                             'filters': doc['manifest']['filters'],
                             'components': {key: {'title': value.get('title', ''), 'kind': value['kind']}
                                            for key, value in doc['manifest']['components'].items()},
                             'annotations': copy.deepcopy(doc['manifest'].get('annotations', []))},
                'snapshot': {key: copy.deepcopy(doc['snapshot'].get(key, {}))
                             for key in ('datasetRefs', 'componentDataRefs')}}

    def hydrate_document(self, envelope):
        if not envelope or 'cosObject' not in envelope:
            return envelope
        obj = self.call('object_get', id=envelope['cosObject'])
        require(obj is not None, 'Version content is unavailable', 'ASSET_UNAVAILABLE')
        doc = json.loads(self.read_file(obj, 'document.json'))
        doc['revision'] = envelope['revision']
        doc['manifest']['annotations'] = copy.deepcopy(envelope['manifest'].get('annotations', []))
        return doc

    def delete_job(self, job):
        if job['state'] == 'complete':
            return job
        from .cloud_storage import publication_storage
        completed = list(job['completed'])
        try:
            for share in job['plan']['shares']:
                key = 'share:' + share['shareId']
                if key not in completed:
                    storage = publication_storage()
                    storage.delete_prefix('shares/' + share['shareId'] + '/')
                    storage.delete_prefix('jobs/' + share['shareId'] + '.json')
                    completed.append(key)
                    self.call('delete_progress', id=job['id'], completed=completed)
            for obj in job['plan']['objects']:
                key = 'object:' + obj['id']
                if key not in completed:
                    self.storage.delete_prefix(obj['prefix'])
                    completed.append(key)
                    self.call('delete_progress', id=job['id'], completed=completed)
            return self.call('delete_finish', id=job['id'])
        except Exception as error:
            # Persist only bounded codes; SDK messages may contain credentials.
            return self.call('delete_progress', id=job['id'], completed=completed,
                             error=getattr(error, 'code', type(error).__name__))


def cleanup_asset_jobs():
    database = AssetDatabase()
    result = {'removed': 0, 'failed': []}
    for entry in database.call('pending'):
        assets = CloudAssets(entry['project'], database)
        # The pending endpoint returns the board for scoped job reads.
        job = assets.call('delete_status', id=entry['id'], board=entry['board'])
        outcome = assets.delete_job(job)
        if outcome['state'] == 'complete':
            result['removed'] += 1
        else:
            result['failed'].append({'job': entry['id'], 'type': outcome.get('error')})
    return result
