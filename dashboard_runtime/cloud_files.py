"""Private durable files; PostgreSQL stores references, COS stores bytes."""
from __future__ import annotations

import hashlib
import mimetypes
import os
from pathlib import Path
import uuid

from .cloud_database import CloudDatabase
from .cloud_storage import CosShareStorage
from .model import require


class CloudFiles:
    def __init__(self, database=None, storage=None):
        self.database = database or CloudDatabase()
        if storage is None:
            shares = CosShareStorage.from_environment()
            prefix = os.environ.get('CHARTS_COS_ASSET_PREFIX', 'charts-assets/')
            require(not (prefix.rstrip('/') + '/').startswith(shares.prefix) and
                    not shares.prefix.startswith(prefix.rstrip('/') + '/'),
                    'Asset and disposable share prefixes must be separate', 'INVALID_CONFIG')
            storage = CosShareStorage(shares.client, shares.bucket, prefix)
            storage.check_private()
        self.storage = storage

    def save(self, project, relative_path, path):
        raw = Path(path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        key = f'{project}/{digest}'
        self.storage.put(key, raw, mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
        self.database.call('file_put', project, path=relative_path, key=key)
        return key

    def restore(self, project, relative_path, target):
        key = self.database.call('file_get', project, path=relative_path)
        if key is None:
            return False
        raw = self.storage.get(key)
        require(raw is not None, 'Stored file is missing', 'CLOUD_FILE_MISSING')
        assert raw is not None
        require(hashlib.sha256(raw).hexdigest() == key.rsplit('/', 1)[-1],
                'Stored file checksum mismatch', 'CLOUD_FILE_CORRUPT')
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_bytes(raw)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return True
