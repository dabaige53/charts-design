"""Share copies inside the Cloudflare instance's private, checkpointed workspace."""
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from .cloud_shares import cleanup_due
from .model import require


class PrivateShares:
    executor = 'cloudflare-cron'

    def __init__(self, root, executor='cloudflare-cron'):
        self.executor = executor
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def check_private(self):
        require(self.root.stat().st_mode & 0o077 == 0, 'Share directory must be private', 'INVALID_CONFIG')

    def _path(self, key):
        path = (self.root / key).resolve()
        require(path != self.root.resolve() and self.root.resolve() in path.parents,
                'Invalid private object key', 'INVALID_ARGUMENT')
        return path

    def put(self, key, content, content_type='application/octet-stream'):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as staged:
            try:
                staged.write(content)
                staged.close()
                Path(staged.name).replace(path)
            finally:
                Path(staged.name).unlink(missing_ok=True)

    def get(self, key):
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            return None

    def list(self, prefix):
        return [path.relative_to(self.root).as_posix() for path in self._path(prefix).rglob('*') if path.is_file()]

    def delete_prefix(self, prefix):
        path = self._path(prefix)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)

    def size_prefix(self, prefix):
        return sum((self.root / key).stat().st_size for key in self.list(prefix))


def storage():
    return PrivateShares(Path(os.environ['CHARTS_RUNTIME_ROOT']) / 'private-shares',
                         'server-timer' if os.environ.get('CHARTS_STORAGE_BACKEND') == 'neon' else 'cloudflare-cron')


def clean():
    store = storage()
    result = cleanup_due(store)
    if store.executor == 'server-timer':
        from .cloud_assets import cleanup_asset_jobs
        result['failed'].extend(cleanup_asset_jobs()['failed'])
    if result['failed']:
        raise RuntimeError('Cloudflare cleanup failed; jobs retained')
    store.put('cleaner-status.json', json.dumps({'completedAt': int(time.time()), 'executor': store.executor}).encode())


if __name__ == '__main__':
    clean()
