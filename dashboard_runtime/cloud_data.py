"""Cloud datasets with PostgreSQL metadata and immutable SQLite query files.

Migrated projects download the COS query file. Legacy projects retain ordered
PostgreSQL chunks until their explicit migration completes.
"""
from __future__ import annotations

import threading
import re
import json
import gzip
import hashlib
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import cast

from .cloud_assets import CloudAssets
from .local_data import LocalData
from .model import json_bytes, require

CHUNK_ROWS = 500
TRANSFER_ROWS = 250


class CloudData(LocalData):
    def __init__(self, root, database, project, assets: CloudAssets | None = None, cos_enabled=False):
        self.database, self.project = database, project
        self.assets, self.cos_enabled = assets, cos_enabled
        self.partition_fields: list[str] = []
        self.restore_lock = threading.RLock()
        self.transfer_lock = threading.Lock()
        self.transfers = {}
        self.transfer_storage = None
        super().__init__(root)

    @staticmethod
    def transfer_ref(ref):
        require(isinstance(ref, dict), 'Invalid transfer reference')
        version, count = ref.get('version'), ref.get('rowCount')
        fields, order = ref.get('fields'), ref.get('fieldOrder')
        require(isinstance(version, str) and re.fullmatch('[0-9a-f]{64}', version),
                'Invalid data version')
        require(type(count) is int and 0 <= count <= 10_000_000, 'Invalid row count')
        require(isinstance(fields, dict) and fields and isinstance(order, list)
                and len(order) == len(fields) and set(order) == set(fields),
                'Invalid field order')
        return version, count

    def _transfer_storage(self):
        if self.transfer_storage is None:
            from .cloud_storage import CosShareStorage
            storage = CosShareStorage.from_environment()
            storage.check_private()
            self.transfer_storage = storage
        return self.transfer_storage

    def _transfer_prefix(self, upload):
        return f"transfers/{self.project}/{upload}/"

    def transfer_cleanup(self, upload):
        require(isinstance(upload, str) and re.fullmatch("[0-9a-f]{64}", upload), "Invalid upload ID")
        self._transfer_storage().delete_prefix(self._transfer_prefix(upload))

    def transfer_chunk(self, upload, ref, part, rows):
        version, count = self.transfer_ref(ref)
        require(isinstance(upload, str) and re.fullmatch('[0-9a-f]{64}', upload)
                and upload != version, 'Invalid upload ID')
        require(type(part) is int and 0 <= part < (count + TRANSFER_ROWS - 1) // TRANSFER_ROWS,
                'Invalid chunk number')
        expected = min(TRANSFER_ROWS, count - part * TRANSFER_ROWS)
        require(isinstance(rows, list) and len(rows) == expected, 'Invalid chunk row count')
        require(len(json_bytes(rows)) <= 2 * 1024 * 1024, 'Chunk exceeds 2 MiB')
        saved = self.database.call('data_get', self.project, version=version)
        if saved is not None:
            require(saved == ref, 'Remote data metadata differs', 'DATA_CONFLICT')
            return {'complete': True, 'part': part}
        storage = self._transfer_storage()
        key = self._transfer_prefix(upload) + str(part)
        raw = json_bytes(rows)
        previous = storage.get(key)
        if previous is not None:
            require(gzip.decompress(previous) == raw, 'Transfer chunk differs', 'DATA_CONFLICT')
        else:
            storage.put(key, gzip.compress(raw), 'application/gzip')
        return {'complete': False, 'part': part}

    def transfer_finish(self, upload, ref):
        version, count = self.transfer_ref(ref)
        require(isinstance(upload, str) and re.fullmatch('[0-9a-f]{64}', upload)
                and upload != version, 'Invalid upload ID')
        saved = self.database.call('data_get', self.project, version=version)
        if saved is not None:
            require(saved == ref, 'Remote data metadata differs', 'DATA_CONFLICT')
            self.transfer_cleanup(upload)
            return {'state': 'complete', 'ref': saved}
        with self.transfer_lock:
            current = self.transfers.get(upload)
            if current and current['state'] == 'running':
                require(current['ref'] == ref, 'Upload already in use', 'DATA_CONFLICT')
                return {'state': 'running'}
            self.transfers[upload] = {'state': 'running', 'ref': ref, 'phase': 'reading',
                                      'completed': 0, 'total': (count + TRANSFER_ROWS - 1) // TRANSFER_ROWS}

        def progress(phase, completed, total):
            with self.transfer_lock:
                self.transfers[upload].update(phase=phase, completed=completed, total=total)

        def finish():
            try:
                def rows():
                    total = (count + TRANSFER_ROWS - 1) // TRANSFER_ROWS
                    storage = self._transfer_storage()
                    prefix = self._transfer_prefix(upload)
                    with ThreadPoolExecutor(max_workers=4) as executor:
                        pending = deque()
                        next_part = 0
                        while pending or next_part < total:
                            while next_part < total and len(pending) < 4:
                                pending.append((next_part, executor.submit(storage.get, prefix + str(next_part))))
                                next_part += 1
                            part, future = pending.popleft()
                            raw = future.result()
                            chunk = json.loads(gzip.decompress(raw)) if raw is not None else None
                            expected = min(TRANSFER_ROWS, count - part * TRANSFER_ROWS)
                            require(isinstance(chunk, list) and len(chunk) == expected,
                                    'A transfer chunk is missing', 'DATA_INCOMPLETE')
                            assert isinstance(chunk, list)
                            progress('reading', part + 1, total)
                            yield from chunk
                fields = {key: ref['fields'][key] for key in ref['fieldOrder']}
                # LocalData uses a staging table; serialize transfers and cache restores.
                with self.restore_lock:
                    checked = LocalData.import_rows(self, rows(), fields)
                    require(checked == ref, 'Transferred data checksum mismatch', 'DATA_CONFLICT')
                    progress('saving', 0, (count + CHUNK_ROWS - 1) // CHUNK_ROWS)
                    saved_ref = self._persist_cached(
                        checked, lambda part: progress('saving', part, (count + CHUNK_ROWS - 1) // CHUNK_ROWS))
                    require(saved_ref == ref, 'Remote data metadata differs', 'DATA_CONFLICT')
                progress('cleanup', 0, 1)
                self.transfer_cleanup(upload)
                result = {'state': 'complete', 'ref': ref}
            except Exception as error:
                result = {'state': 'failed', 'code': getattr(error, 'code', 'TRANSFER_FAILED')}
            with self.transfer_lock:
                self.transfers[upload] = result

        threading.Thread(target=finish, daemon=True).start()
        return {'state': 'running'}

    def transfer_status(self, upload, ref, parts=None):
        result = self._transfer_status(upload, ref)
        if parts is not None:
            total = (ref['rowCount'] + TRANSFER_ROWS - 1) // TRANSFER_ROWS
            require(isinstance(parts, list) and len(parts) <= 128
                    and all(type(part) is int and 0 <= part < total for part in parts)
                    and len(set(parts)) == len(parts), 'Invalid transfer receipt parts')
            received = {}
            if result['state'] not in ('complete', 'cleanup_required'):
                storage = self._transfer_storage()
                prefix = self._transfer_prefix(upload)
                with ThreadPoolExecutor(max_workers=4) as executor:
                    for part, raw in zip(parts, executor.map(lambda part: storage.get(prefix + str(part)), parts)):
                        if raw is not None:
                            received[str(part)] = hashlib.sha256(gzip.decompress(raw)).hexdigest()
            result['receivedParts'] = received
        return result

    def _transfer_status(self, upload, ref):
        version, _ = self.transfer_ref(ref)
        require(isinstance(upload, str) and re.fullmatch('[0-9a-f]{64}', upload),
                'Invalid upload ID')
        saved = self.database.call('data_get', self.project, version=version)
        if saved is not None:
            require(saved == ref, 'Remote data metadata differs', 'DATA_CONFLICT')
            with self.transfer_lock:
                state = self.transfers.get(upload)
            if state and state['state'] == 'running':
                return {key: value for key, value in state.items() if key != 'ref'}
            if state and state['state'] == 'complete':
                return {'state': 'complete', 'ref': saved}
            return {'state': 'cleanup_required', 'ref': saved}
        with self.transfer_lock:
            state = self.transfers.get(upload, {'state': 'unknown'})
            return {key: value for key, value in state.items() if key != 'ref'}

    def import_rows(self, rows, fields, progress=None):
        ref = super().import_rows(rows, fields)
        return self._persist_cached(ref, progress)

    def _persist_cached(self, ref, progress=None):
        if self.cos_enabled:
            cast(CloudAssets, self.assets).save_dataset(self, ref)
            if progress:
                progress((ref['rowCount'] + CHUNK_ROWS - 1) // CHUNK_ROWS)
            return ref
        if self.database.call('data_get', self.project, version=ref['version']) is not None:
            return ref
        chunk, part = [], 0
        # Base iter_rows reads the just-created cache, without remote hydration.
        for row in super().iter_rows(ref):
            chunk.append(row)
            if len(chunk) == CHUNK_ROWS:
                self.database.call('data_chunk_put', self.project, version=ref['version'], part=part, rows=chunk)
                part += 1
                if progress:
                    progress(part)
                chunk = []
        if chunk:
            self.database.call('data_chunk_put', self.project, version=ref['version'], part=part, rows=chunk)
            if progress:
                progress(part + 1)
        saved = self.database.call('data_finish', self.project, metadata=ref)
        require(saved == ref, 'Remote data metadata differs from this version', 'DATA_CONFLICT')
        return ref

    def describe(self, version):
        import json
        metadata = self.database.call('data_get', self.project, version=version)
        require(metadata is not None, 'Unknown durable data version', 'NOT_FOUND')
        return self._metadata(json.dumps(metadata))

    def _version(self, db, ref):
        # Validate the content hash before using it as an identifier.
        import re
        version = ref.get('version') if isinstance(ref, dict) else None
        require(isinstance(version, str) and re.fullmatch('[0-9a-f]{64}', version),
                'Invalid data version')
        if self.cos_enabled:
            return self._cos_version(db, ref)
        if db.execute('SELECT 1 FROM versions WHERE version=?', (version,)).fetchone():
            return super()._version(db, ref)
        with self.restore_lock:
            if db.execute('SELECT 1 FROM versions WHERE version=?', (version,)).fetchone():
                return super()._version(db, ref)
            metadata = self.database.call('data_get', self.project, version=version)
            require(metadata is not None, 'Unknown data version', 'NOT_FOUND')

            def rows():
                for part in range((metadata['rowCount'] + CHUNK_ROWS - 1) // CHUNK_ROWS):
                    chunk = self.database.call('data_chunk_get', self.project, version=version, part=part)
                    require(isinstance(chunk, list), 'Remote data chunk is missing', 'DATA_INCOMPLETE')
                    yield from chunk

            fields = {key: metadata['fields'][key] for key in metadata['fieldOrder']}
            restored = super().import_rows(rows(), fields)
            require(restored == metadata, 'Remote dataset checksum mismatch', 'DATA_CONFLICT')
        return super()._version(db, ref)

    def _cos_version(self, db, ref):
        import uuid
        version = ref['version']
        assets = cast(CloudAssets, self.assets)
        obj = assets.call('object_get', version=version)
        require(obj is not None, 'Data version is unavailable', 'ASSET_UNAVAILABLE')
        require(obj['descriptor'].get('queryFormat') == 1, 'Unsupported query file format', 'DATA_CONFLICT')
        # A new object generation gets a new cache file even for identical data.
        alias = 'v_' + obj['id']
        if alias not in {row[1] for row in db.execute('PRAGMA database_list')}:
            target = self.root / (obj['id'] + '.sqlite3')
            with self.restore_lock:
                if not target.exists():
                    raw = assets.read_file(obj, 'query.sqlite3')
                    temporary = target.with_suffix('.' + uuid.uuid4().hex + '.tmp')
                    try:
                        temporary.write_bytes(raw)
                        temporary.replace(target)
                    finally:
                        temporary.unlink(missing_ok=True)
            db.execute(f'ATTACH DATABASE ? AS {alias}', (target.as_uri() + '?mode=ro',))
        return alias + '.d_' + version, self._metadata(json.dumps(obj['descriptor']['metadata']))

    def _indexes(self, db, table, fields, filters, sort=None):
        if table.startswith('v_') and '.d_' in table:
            return  # The immutable query file already contains field indexes.
        return super()._indexes(db, table, fields, filters, sort)
