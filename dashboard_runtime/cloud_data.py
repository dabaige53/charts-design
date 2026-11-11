"""Durable PostgreSQL datasets with rebuildable SQLite query caches.

Query semantics remain identical to local mode. PostgreSQL owns metadata and
ordered immutable row chunks; a cache miss rebuilds only the requested version.
"""
from __future__ import annotations

import threading
import re
import json
import gzip

from .local_data import LocalData
from .model import json_bytes, require

CHUNK_ROWS = 500
TRANSFER_ROWS = 250


class CloudData(LocalData):
    def __init__(self, root, database, project):
        self.database, self.project = database, project
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
            self.transfers[upload] = {'state': 'running', 'ref': ref}

        def finish():
            try:
                def rows():
                    for part in range((count + TRANSFER_ROWS - 1) // TRANSFER_ROWS):
                        raw = self._transfer_storage().get(self._transfer_prefix(upload) + str(part))
                        chunk = json.loads(gzip.decompress(raw)) if raw is not None else None
                        expected = min(TRANSFER_ROWS, count - part * TRANSFER_ROWS)
                        require(isinstance(chunk, list) and len(chunk) == expected,
                                'A transfer chunk is missing', 'DATA_INCOMPLETE')
                        yield from chunk
                fields = {key: ref['fields'][key] for key in ref['fieldOrder']}
                # LocalData uses a staging table; serialize transfers and cache restores.
                with self.restore_lock:
                    checked = LocalData.import_rows(self, rows(), fields)
                    require(checked == ref, 'Transferred data checksum mismatch', 'DATA_CONFLICT')
                    saved_ref = self.import_rows(LocalData.iter_rows(self, checked), fields)
                    require(saved_ref == ref, 'Remote data metadata differs', 'DATA_CONFLICT')
                self.transfer_cleanup(upload)
                result = {'state': 'complete', 'ref': ref}
            except Exception as error:
                result = {'state': 'failed', 'code': getattr(error, 'code', 'TRANSFER_FAILED')}
            with self.transfer_lock:
                self.transfers[upload] = result

        threading.Thread(target=finish, daemon=True).start()
        return {'state': 'running'}

    def transfer_status(self, upload, ref):
        version, _ = self.transfer_ref(ref)
        require(isinstance(upload, str) and re.fullmatch('[0-9a-f]{64}', upload),
                'Invalid upload ID')
        saved = self.database.call('data_get', self.project, version=version)
        if saved is not None:
            require(saved == ref, 'Remote data metadata differs', 'DATA_CONFLICT')
            with self.transfer_lock:
                state = self.transfers.get(upload)
            if state and state['state'] == 'running':
                return {'state': 'running'}
            if state and state['state'] == 'complete':
                return {'state': 'complete', 'ref': saved}
            return {'state': 'cleanup_required', 'ref': saved}
        with self.transfer_lock:
            state = self.transfers.get(upload, {'state': 'unknown'})
            return {key: value for key, value in state.items() if key != 'ref'}

    def import_rows(self, rows, fields):
        ref = super().import_rows(rows, fields)
        if self.database.call('data_get', self.project, version=ref['version']) is not None:
            return ref
        chunk, part = [], 0
        # Base iter_rows reads the just-created cache, without remote hydration.
        for row in super().iter_rows(ref):
            chunk.append(row)
            if len(chunk) == CHUNK_ROWS:
                self.database.call('data_chunk_put', self.project, version=ref['version'], part=part, rows=chunk)
                part += 1
                chunk = []
        if chunk:
            self.database.call('data_chunk_put', self.project, version=ref['version'], part=part, rows=chunk)
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
        if db.execute('SELECT 1 FROM versions WHERE version=?', (version,)).fetchone():
            return super()._version(db, ref)
        with self.restore_lock:
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
