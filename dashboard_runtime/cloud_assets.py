"""Immutable COS packages and the PostgreSQL reference/operation registry."""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import uuid
from contextlib import closing

from .cloud_database import CloudDatabase
from .cloud_files import CloudFiles
from .model import DashboardError, json_bytes, require


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
        obj = self.call('reserve', id=uuid.uuid4().hex, kind='dataset', version=ref['version'])
        files, shards, options = {}, [], {key: {} for key in ref['fieldOrder']}
        batch, ordinals, size = [], [], 64
        partition_field = next((field for field in getattr(data, 'partition_fields', [])
                                if ref['fields'].get(field, {}).get('type') in ('date', 'string')), None)
        partitions, batch_values = {}, set()

        def flush():
            nonlocal batch, ordinals, size
            name = f'rows-{len(shards)}.json.gz'
            payload = b'[' + b','.join(batch) + b']'
            if partition_field:
                payload = b'{"rows":' + payload + b',"ordinals":' + json_bytes(ordinals) + b'}'
            raw = gzip.compress(payload, mtime=0)
            self._put(obj, files, name, raw, 'application/gzip')
            shards.append(name)
            if partition_field:
                for value in batch_values:
                    partitions.setdefault(value, []).append(name)
                batch_values.clear()
            batch, ordinals, size = [], [], 64

        from .local_data import LocalData
        local = LocalData(data.root)

        def ordered_rows():
            with local._connect() as db:
                table, metadata = local._version(db, ref)
                fields = metadata['fields']
                keys = list(fields)
                columns = ','.join(local._column(fields, key) for key in keys)
                order = (local._column(fields, partition_field) + ',') if partition_field else ''
                for record in db.execute(f'SELECT {columns},_missing,rowid FROM {table} ORDER BY {order}rowid'):
                    yield record[-1], local._decode(keys, record[:-2], fields, record[-2])

        for ordinal, row in ordered_rows():
            encoded = json_bytes(row)
            row_size = len(encoded) + len(str(ordinal)) + 2
            require(row_size + 64 <= 16 * 1024 * 1024, 'A data row exceeds 16 MiB', 'PAYLOAD_TOO_LARGE')
            partition_value = json.dumps(row.get(partition_field), ensure_ascii=False) if partition_field else None
            if batch and (len(batch) >= 5000 or size + row_size > 16 * 1024 * 1024
                          or (partition_field and partition_value not in batch_values)):
                flush()
            batch.append(encoded)
            ordinals.append(ordinal)
            if partition_field:
                # Nulls have a separate index entry and are never discarded on
                # an unfiltered read. The actual filter still runs on rows.
                batch_values.add(partition_value)
            size += row_size
            for key, values in options.items():
                value = row.get(key)
                values[json.dumps(value, ensure_ascii=False)] = value
        if batch:
            flush()
        option_files = {}
        for index, (key, values) in enumerate(options.items()):
            name = f'options-{index}.json.gz'
            self._put(obj, files, name, gzip.compress(json_bytes(list(values.values())), mtime=0), 'application/gzip')
            option_files[key] = name
        # Copy the validated table in SQLite, not through Python row decoding.
        with tempfile.TemporaryDirectory(prefix='charts-data-') as temporary:
            target = Path(temporary) / 'query.sqlite3'
            with closing(sqlite3.connect(target)) as db, db:
                db.execute('ATTACH DATABASE ? AS source', (str(data.path),))
                table = 'd_' + ref['version']
                db.execute(f'CREATE TABLE {table} AS SELECT * FROM source.{table} ORDER BY rowid')
                db.execute('CREATE TABLE versions(version TEXT PRIMARY KEY, metadata TEXT NOT NULL)')
                db.execute('INSERT INTO versions VALUES(?,?)', (ref['version'], json.dumps(ref)))
                for index in range(len(ref['fieldOrder'])):
                    db.execute(f'CREATE INDEX i_{index} ON {table}(c{index})')
            self._put(obj, files, 'query.sqlite3', target.read_bytes())
        descriptor = {'format': 'cos-dataset-v1', 'queryFormat': 1, 'metadata': ref,
                      'shards': shards, 'options': option_files, 'files': files,
                      'bytes': sum(entry['bytes'] for entry in files.values())}
        if partition_field:
            descriptor['partitionIndex'] = {'field': partition_field,
                                           'entries': [{'value': json.loads(value), 'files': names}
                                                       for value, names in partitions.items()]}
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
        from .cloud_storage import CosShareStorage
        completed = list(job['completed'])
        try:
            for share in job['plan']['shares']:
                key = 'share:' + share['shareId']
                if key not in completed:
                    storage = CosShareStorage.from_environment()
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
