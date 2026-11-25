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
from tempfile import TemporaryDirectory
from typing import cast

from .cloud_assets import CloudAssets
from .local_data import LocalData
from .model import json_bytes, require
from .transfer_payload import BULK_ROWS, TRANSFER_ROWS, bulk_binary, bulk_raw, bulk_rows

CHUNK_ROWS = 500


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
            from .cloud_storage import publication_storage
            storage = publication_storage()
            storage.check_private()
            self.transfer_storage = storage
        return self.transfer_storage

    def _transfer_prefix(self, upload):
        return f"transfers/{self.project}/{upload}/"

    def transfer_cleanup(self, upload):
        require(isinstance(upload, str) and re.fullmatch("[0-9a-f]{64}", upload), "Invalid upload ID")
        self._transfer_storage().delete_prefix(self._transfer_prefix(upload))

    def _transfer_parts(self, upload, bulk):
        return self._transfer_prefix(upload) + ('bulk-v1/' if bulk else '')

    def transfer_chunk(self, upload, ref, part, rows=None, *, bulk=False, payload=None):
        version, count = self.transfer_ref(ref)
        require(isinstance(upload, str) and re.fullmatch('[0-9a-f]{64}', upload)
                and upload != version, 'Invalid upload ID')
        size = BULK_ROWS if bulk else TRANSFER_ROWS
        require(type(part) is int and 0 <= part < (count + size - 1) // size,
                'Invalid chunk number')
        expected = min(size, count - part * size)
        compressed = None
        if bulk:
            require(rows is None, 'Bulk chunks do not accept rows')
            compressed = bulk_binary(payload)
            raw = bulk_raw(compressed)
            bulk_rows(raw, expected)
        else:
            require(payload is None, 'Compressed chunks require gzip-json-v1 encoding')
            require(isinstance(rows, list) and len(rows) == expected, 'Invalid chunk row count')
            raw = json_bytes(rows)
            require(len(raw) <= 2 * 1024 * 1024, 'Chunk exceeds 2 MiB')
        saved = self.database.call('data_get', self.project, version=version)
        if saved is not None:
            require(saved == ref, 'Remote data metadata differs', 'DATA_CONFLICT')
            return {'complete': True, 'part': part}
        storage = self._transfer_storage()
        key = self._transfer_parts(upload, bulk) + str(part)
        previous = storage.get(key)
        if previous is not None:
            require((bulk_raw(previous) if bulk else gzip.decompress(previous)) == raw,
                    'Transfer chunk differs', 'DATA_CONFLICT')
        else:
            storage.put(key, compressed if compressed is not None else gzip.compress(raw), 'application/gzip')
        return {'complete': False, 'part': part}

    def transfer_finish(self, upload, ref, *, bulk=False):
        version, count = self.transfer_ref(ref)
        require(isinstance(upload, str) and re.fullmatch('[0-9a-f]{64}', upload)
                and upload != version, 'Invalid upload ID')
        saved = self.database.call('data_get', self.project, version=version)
        if saved is not None:
            require(saved == ref, 'Remote data metadata differs', 'DATA_CONFLICT')
            self.transfer_cleanup(upload)
            return {'state': 'complete', 'ref': saved}
        size = BULK_ROWS if bulk else TRANSFER_ROWS
        total = (count + size - 1) // size
        with self.transfer_lock:
            current = self.transfers.get(upload)
            if current and current['state'] == 'running':
                require(current['ref'] == ref and current['bulk'] == bulk,
                        'Upload already in use', 'DATA_CONFLICT')
                return {'state': 'running'}
            self.transfers[upload] = {'state': 'running', 'ref': ref, 'phase': 'reading',
                                      'completed': 0, 'total': total, 'bulk': bulk}

        def progress(phase, completed, total):
            with self.transfer_lock:
                self.transfers[upload].update(phase=phase, completed=completed, total=total)

        def finish():
            try:
                def rows():
                    storage = self._transfer_storage()
                    prefix = self._transfer_parts(upload, bulk)
                    with ThreadPoolExecutor(max_workers=4) as executor:
                        pending = deque()
                        next_part = 0
                        while pending or next_part < total:
                            while next_part < total and len(pending) < 4:
                                pending.append((next_part, executor.submit(storage.get, prefix + str(next_part))))
                                next_part += 1
                            part, future = pending.popleft()
                            raw = future.result()
                            chunk = json.loads(bulk_raw(raw) if bulk else gzip.decompress(raw)) if raw is not None else None
                            expected = min(size, count - part * size)
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

    def transfer_status(self, upload, ref, parts=None, *, bulk=False):
        result = self._transfer_status(upload, ref, bulk)
        if parts is not None:
            size = BULK_ROWS if bulk else TRANSFER_ROWS
            total = (ref['rowCount'] + size - 1) // size
            require(isinstance(parts, list) and len(parts) <= (4 if bulk else 128)
                    and all(type(part) is int and 0 <= part < total for part in parts)
                    and len(set(parts)) == len(parts), 'Invalid transfer receipt parts')
            received = {}
            if result['state'] not in ('complete', 'cleanup_required'):
                storage = self._transfer_storage()
                prefix = self._transfer_parts(upload, bulk)
                with ThreadPoolExecutor(max_workers=4) as executor:
                    for part, raw in zip(parts, executor.map(lambda part: storage.get(prefix + str(part)), parts)):
                        if raw is not None:
                            received[str(part)] = hashlib.sha256(bulk_raw(raw) if bulk else gzip.decompress(raw)).hexdigest()
            result['receivedParts'] = received
        return result

    def _transfer_status(self, upload, ref, bulk):
        version, _ = self.transfer_ref(ref)
        require(isinstance(upload, str) and re.fullmatch('[0-9a-f]{64}', upload),
                'Invalid upload ID')
        saved = self.database.call('data_get', self.project, version=version)
        if saved is not None:
            require(saved == ref, 'Remote data metadata differs', 'DATA_CONFLICT')
            with self.transfer_lock:
                state = self.transfers.get(upload)
            if state and state['state'] == 'running':
                require(state['bulk'] == bulk, 'Upload already in use', 'DATA_CONFLICT')
                return {key: value for key, value in state.items() if key not in ('ref', 'bulk')}
            if state and state['state'] == 'complete':
                return {'state': 'complete', 'ref': saved}
            return {'state': 'cleanup_required', 'ref': saved}
        with self.transfer_lock:
            state = self.transfers.get(upload, {'state': 'unknown'})
            if state['state'] == 'running':
                require(state['bulk'] == bulk, 'Upload already in use', 'DATA_CONFLICT')
            return {key: value for key, value in state.items() if key not in ('ref', 'bulk')}

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

    def repartition(self, ref, field):
        """Stage a private replacement package with identical logical rows."""
        require(self.cos_enabled, 'Repartitioning requires COS project storage', 'UNSUPPORTED_OPERATION')
        version, count = self.transfer_ref(ref)
        fields = ref['fields']
        require(isinstance(field, str) and fields.get(field, {}).get('type') in ('string', 'date'),
                'Partition field must be a declared string or date field')
        assets = cast(CloudAssets, self.assets)
        current = assets.call('object_get', version=version)
        require(current is not None, 'Data version is unavailable', 'ASSET_UNAVAILABLE')
        require(current['descriptor']['metadata'] == ref, 'Remote data metadata differs', 'DATA_CONFLICT')
        if current['descriptor'].get('partitionIndex', {}).get('field') == field:
            return ref

        keys = ref['fieldOrder']
        require(len(keys) > 1, 'Repartitioning requires at least two fields for a replacement version',
                'UNSUPPORTED_OPERATION')
        remaining = [key for key in keys if key != field]
        # A different physical column order produces a new content address.
        # The original version and its consumers remain readable.
        ordered = [*remaining, field] if keys[0] == field else [field, *remaining]
        with TemporaryDirectory(prefix='charts-repartition-', dir=self.root) as directory:
            target = LocalData(directory)
            target.partition_fields = [field]
            replacement = target.import_rows(self.iter_rows(ref), {key: fields[key] for key in ordered})
            require(replacement['rowCount'] == count and replacement['fields'] == fields,
                    'Repartitioning changed the source data metadata', 'DATA_CONFLICT')
            asset = assets.save_dataset(target, replacement)
        descriptor = asset['descriptor']
        require(descriptor['metadata'] == replacement and descriptor.get('partitionIndex', {}).get('field') == field,
                'Replacement version already exists with a different layout', 'DATA_CONFLICT')
        return replacement

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
                parts = iter(range((metadata['rowCount'] + CHUNK_ROWS - 1) // CHUNK_ROWS))
                # Bound both requests and buffered chunks, retaining checksum order.
                with ThreadPoolExecutor(max_workers=4) as pool:
                    def fetch(part):
                        return pool.submit(self.database.call, 'data_chunk_get',
                                           self.project, version=version, part=part)
                    pending = deque(fetch(part) for part in (next(parts, None) for _ in range(4))
                                    if part is not None)
                    while pending:
                        chunk = pending.popleft().result()
                        require(isinstance(chunk, list), 'Remote data chunk is missing', 'DATA_INCOMPLETE')
                        yield from chunk
                        part = next(parts, None)
                        if part is not None:
                            pending.append(fetch(part))

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

    def _option_page(self, refs, field, search='', offset=0, limit=100):
        unique = {ref['version']: ref for ref in refs}
        if not self.cos_enabled or len(unique) <= 10:
            return super()._option_page(refs, field, search, offset, limit)
        self._validate_option_page(search, offset, limit)
        # SQLite allows ten attached databases per connection. Collect each
        # file's distinct candidates before merging the complete option set.
        with self._connect() as merged:
            merged.execute('CREATE TEMP TABLE option_values (value UNIQUE)')
            for ref in unique.values():
                with self._connect() as source:
                    table, metadata = self._version(source, ref)
                    column = self._column(metadata['fields'], field)
                    kind = metadata['fields'][field]['type']
                    merged.executemany(
                        'INSERT OR IGNORE INTO option_values VALUES (?)',
                        source.execute(f'SELECT DISTINCT {column} FROM {table}'),
                    )
            return self._page_option_values(merged, 'option_values', kind, search, offset, limit)

    def _indexes(self, db, table, fields, filters, sort=None):
        if table.startswith('v_') and '.d_' in table:
            return  # The immutable query file already contains field indexes.
        return super()._indexes(db, table, fields, filters, sort)
