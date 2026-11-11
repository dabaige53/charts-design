"""Durable PostgreSQL datasets with rebuildable SQLite query caches.

Query semantics remain identical to local mode. PostgreSQL owns metadata and
ordered immutable row chunks; a cache miss rebuilds only the requested version.
"""
from __future__ import annotations

import threading

from .local_data import LocalData
from .model import require

CHUNK_ROWS = 500


class CloudData(LocalData):
    def __init__(self, root, database, project):
        self.database, self.project = database, project
        self.restore_lock = threading.RLock()
        super().__init__(root)

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
