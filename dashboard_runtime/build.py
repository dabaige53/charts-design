"""Worker identity captured at startup, not re-read from a replaced installation."""
import hashlib
from pathlib import Path


def fingerprint(root):
    digest = hashlib.sha256()
    for path in sorted(Path(root).glob('*.py')):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


MODULE_ROOT = str(Path(__file__).resolve().parent)
BACKEND_BUILD_ID = fingerprint(MODULE_ROOT)
