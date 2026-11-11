"""Code-protected static publications; expiration cleanup runs only in cloud SCF."""
from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import tempfile
import time
import uuid
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from .model import require

SHARE_ID = re.compile(r'^[0-9a-f]{32}$')
ACCESS_KEY = re.compile(r'^[0-9]{8}$')
EXPIRATIONS = {'never': None, '7d': 7 * 86400, '30d': 30 * 86400}


def checked_id(value):
    require(isinstance(value, str) and bool(SHARE_ID.fullmatch(value)),
            'Invalid cloud share ID', 'INVALID_ARGUMENT')
    return value


def key_digest(key, salt):
    return hashlib.pbkdf2_hmac('sha256', key.encode(), bytes.fromhex(salt), 200000).hex()


class CloudShares:
    def __init__(self, storage, public_url):
        self.storage = storage
        parsed = urlparse(public_url)
        require(parsed.scheme == 'https' and bool(parsed.netloc) and not parsed.query and not parsed.fragment,
                'Configure CHARTS_PUBLIC_URL as the HTTPS cloud gateway address',
                'CLOUD_SHARE_NOT_CONFIGURED')
        self.public_url = public_url.rstrip('/')

    @classmethod
    def from_environment(cls):
        from .cloud_storage import CosShareStorage
        return cls(CosShareStorage.from_environment(), os.environ.get('CHARTS_PUBLIC_URL', ''))

    def _put_json(self, key, value):
        self.storage.put(key, json.dumps(value, ensure_ascii=False, allow_nan=False).encode(), 'application/json')

    def control(self, share_id):
        share_id = checked_id(share_id)
        raw = self.storage.get('shares/' + share_id + '/control.json')
        require(raw is not None, '分享不存在或已删除', 'SHARE_UNAVAILABLE')
        control = json.loads(raw)
        require(control['state'] == 'active' and
                (control['expiresAt'] is None or time.time() < control['expiresAt']),
                '分享已过期或已撤销', 'SHARE_EXPIRED')
        return control

    def publish(self, service, board, expected_revision, expiration='7d', access_key=None):
        require(expiration in EXPIRATIONS, 'expiration must be never, 7d or 30d', 'INVALID_ARGUMENT')
        access_key = access_key if access_key is not None else f'{secrets.randbelow(100000000):08d}'
        require(isinstance(access_key, str) and bool(ACCESS_KEY.fullmatch(access_key)),
                'accessKey must contain exactly eight ASCII digits', 'INVALID_ARGUMENT')
        doc = service.store.readable(board) if service.project_root else service.store.get(board, hydrate=False)
        require(doc['revision'] == expected_revision == service.store.revision(board),
                'Complete the current edit batch and read its latest revision before publishing', 'REVISION_CONFLICT')
        heartbeat = self.storage.get('cleaner-status.json')
        require(heartbeat is not None and time.time() - json.loads(heartbeat)['completedAt'] < 180,
                'Deploy the SCF minute timer and confirm a successful cloud cleanup invocation before publishing',
                'CLOUD_CLEANER_UNAVAILABLE')
        self.storage.check_private()
        share_id, now = uuid.uuid4().hex, int(time.time())
        lifetime = EXPIRATIONS[expiration]
        expires = now + lifetime if lifetime is not None else None
        owner = hashlib.sha256(str(Path(service.project_root or service.store.root).resolve()).encode()).hexdigest()
        job = {'shareId': share_id, 'state': 'uploading', 'cleanupAfter': now + 3600,
               'expiresAt': expires, 'owner': owner, 'dashboardId': board, 'revision': doc['revision']}
        self._put_json('jobs/' + share_id + '.json', job)
        # Only SCF deletes remote content. The upload staging directory is
        # local temporary data and is removed even if export/upload fails.
        with tempfile.TemporaryDirectory(prefix='charts-share-', dir='/private/tmp') as temporary:
            from .deployment import export_site
            exported = export_site(service.store, board, output_root=Path(temporary))['export']
            site = Path(exported['directory'])
            files = []
            for path in sorted(site.rglob('*')):
                if not path.is_file():
                    continue
                name = path.relative_to(site).as_posix()
                kind = mimetypes.guess_type(name)[0] or 'application/octet-stream'
                self.storage.put('shares/' + share_id + '/site/' + name, path.read_bytes(), kind)
                files.append(name)
            salt = secrets.token_hex(16)
            control = {'shareId': share_id, 'state': 'active', 'dashboardId': board,
                       'revision': doc['revision'], 'owner': owner, 'createdAt': now,
                       'expiresAt': expires, 'salt': salt, 'keyHash': key_digest(access_key, salt),
                       'files': files}
            self._put_json('shares/' + share_id + '/control.json', control)
            self._put_json('jobs/' + share_id + '.json', {**job, 'state': 'active', 'cleanupAfter': expires})
        return {'shareId': share_id, 'url': self.public_url + '/s/' + share_id + '/',
                'accessKey': access_key, 'expiration': expiration, 'expiresAt': expires,
                'revision': doc['revision'], 'cleanupExecutor': 'tencent-scf'}

    def authenticate(self, share_id, key):
        control = self.control(share_id)
        require(isinstance(key, str) and bool(ACCESS_KEY.fullmatch(key)) and
                hmac.compare_digest(key_digest(key, control['salt']), control['keyHash']),
                '访问密钥错误', 'INVALID_ACCESS_KEY')
        return control

    def content(self, share_id, name, *, control=None):
        # The gateway may reuse the control checked earlier in this request.
        control = self.control(share_id) if control is None else control
        path = PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts and name in control['files'],
                '分享文件不存在', 'NOT_FOUND')
        raw = self.storage.get('shares/' + checked_id(share_id) + '/site/' + name)
        require(raw is not None, '分享文件不存在', 'NOT_FOUND')
        return raw

    def revoke(self, service, board, share_id):
        control = self.control(share_id)
        owner = hashlib.sha256(str(Path(service.project_root or service.store.root).resolve()).encode()).hexdigest()
        require(control['owner'] == owner and control['dashboardId'] == board,
                'Share belongs to another project/dashboard', 'FORBIDDEN')
        self._put_json('shares/' + share_id + '/control.json', {**control, 'state': 'revoked'})
        self._put_json('jobs/' + share_id + '.json', {
            'shareId': share_id, 'state': 'revoked', 'expiresAt': control['expiresAt'],
            'cleanupAfter': int(time.time()), 'owner': owner, 'dashboardId': board,
            'revision': control['revision'],
        })
        return {'shareId': share_id, 'revoked': True, 'cleanupState': 'pending',
                'cleanupExecutor': 'tencent-scf'}

    def status(self, service, board, share_id=None):
        if share_id is not None:
            checked_id(share_id)
        owner = hashlib.sha256(str(Path(service.project_root or service.store.root).resolve()).encode()).hexdigest()
        keys = ['jobs/' + share_id + '.json'] if share_id else list(self.storage.list('jobs/'))
        shares = []
        for key in keys:
            raw = self.storage.get(key)
            if raw is None:
                continue
            job = json.loads(raw)
            if job.get('owner') != owner or job.get('dashboardId') != board:
                continue
            due = job['cleanupAfter'] is not None and time.time() >= job['cleanupAfter']
            shares.append({'shareId': job['shareId'], 'state': 'expired' if due and job['state'] == 'active' else job['state'],
                           'revision': job['revision'], 'expiresAt': job['expiresAt'],
                           'cleanupState': 'pending' if due else 'scheduled' if job['cleanupAfter'] else 'not_scheduled',
                           'url': self.public_url + '/s/' + job['shareId'] + '/'})
        return {'shares': shares, 'cleanupExecutor': 'tencent-scf'}


def cleanup_due(storage, now=None):
    """Called by the SCF timer, never scheduled by a local MCP or web server."""
    now = time.time() if now is None else now
    removed, failed = 0, []
    # Snapshot only the small job-key list; objects are deleted in bounded pages.
    for key in list(storage.list('jobs/')):
        try:
            raw = storage.get(key)
            if raw is None:
                continue
            job = json.loads(raw)
            share_id = checked_id(job['shareId'])
            require(key == 'jobs/' + share_id + '.json', 'Invalid cleanup job', 'INVALID_ARGUMENT')
            deadline = job['cleanupAfter']
            if deadline is None or deadline > now:
                continue
            storage.delete_prefix('shares/' + share_id + '/')
            # Delete access metadata, job and their historical versions only
            # after every content object has been physically deleted.
            storage.delete_prefix('jobs/' + share_id + '.json')
            removed += 1
        except Exception as error:
            # Preserve failed jobs for the next cloud invocation. Never log
            # remote payloads, access codes or credential-bearing SDK messages.
            failed.append({'job': key, 'type': type(error).__name__})
    return {'removed': removed, 'failed': failed}
