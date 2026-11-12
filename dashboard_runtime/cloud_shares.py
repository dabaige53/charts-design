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

from .model import identifier, require

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

    def publish(self, service, board, expected_revision, expiration='7d', access_key=None, pages=None):
        require(expiration in EXPIRATIONS, 'expiration must be never, 7d or 30d', 'INVALID_ARGUMENT')
        access_key = access_key if access_key is not None else f'{secrets.randbelow(100000000):08d}'
        require(isinstance(access_key, str) and bool(ACCESS_KEY.fullmatch(access_key)),
                'accessKey must contain exactly eight ASCII digits', 'INVALID_ARGUMENT')
        versions = None
        if service.project_root:
            from .versions import Versions
            versions = Versions(service.store)
            require(versions.status(board)['publishedRevision'] == expected_revision,
                    'Publish the saved version before sharing it', 'REVISION_CONFLICT')
            doc = versions.read(board, expected_revision)
        else:
            doc = service.store.get(board, hydrate=False)
            require(doc['revision'] == expected_revision, 'Reload before sharing', 'REVISION_CONFLICT')
        documents = [(board, doc)]
        if pages is not None:
            require(service.project_root is not None and isinstance(pages, list),
                    'Multiple pages require a project and a page list', 'INVALID_ARGUMENT')
            assert versions is not None
            seen = {board}
            for page in pages:
                require(isinstance(page, dict) and isinstance(page.get('dashboardId'), str)
                        and type(page.get('expectedRevision')) is int,
                        'Each page requires dashboardId and expectedRevision', 'INVALID_ARGUMENT')
                page_id, revision = identifier(page['dashboardId']), page['expectedRevision']
                require(page_id not in seen, 'Duplicate page', 'INVALID_ARGUMENT')
                require(versions.status(page_id)['publishedRevision'] == revision,
                        'Publish each selected page before sharing it', 'REVISION_CONFLICT')
                documents.append((page_id, versions.read(page_id, revision)))
                seen.add(page_id)
        heartbeat = self.storage.get('cleaner-status.json')
        require(heartbeat is not None and time.time() - json.loads(heartbeat)['completedAt'] < 7 * 3600,
                'Deploy the SCF six-hour timer and confirm a successful cloud cleanup invocation before publishing',
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
        with tempfile.TemporaryDirectory(prefix='charts-share-') as temporary:
            from .deployment import export_site
            exported = export_site(service.store, board, output_root=Path(temporary), document=doc)['export']
            site = Path(exported['directory'])
            if len(documents) > 1:
                import os
                import shutil
                shards = {}
                for path in (site / 'data').iterdir():
                    if path.is_file():
                        shards[hashlib.sha256(path.read_bytes()).hexdigest()] = path
                entries = [{'id': board, 'title': doc['manifest']['title'], 'path': 'document.json', 'revision': doc['revision']}]
                for page_id, page_doc in documents[1:]:
                    page_export = export_site(service.store, page_id, output_root=Path(temporary), document=page_doc)['export']
                    page_site = Path(page_export['directory'])
                    target = site / 'pages' / page_id
                    target.mkdir(parents=True)
                    page_document = json.loads((page_site / 'document.json').read_bytes())
                    for dataset, paths in page_document['staticFiles'].items():
                        reused = []
                        for name in paths:
                            source = page_site / name
                            digest = hashlib.sha256(source.read_bytes()).hexdigest()
                            destination = shards.get(digest)
                            if destination is None:
                                destination = target / name
                                destination.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copyfile(source, destination)
                                shards[digest] = destination
                            reused.append(Path(os.path.relpath(destination, target)).as_posix())
                        page_document['staticFiles'][dataset] = reused
                    (target / 'document.json').write_text(json.dumps(page_document, ensure_ascii=False), encoding='utf-8')
                    entries.append({'id': page_id, 'title': page_doc['manifest']['title'],
                                    'path': 'pages/' + page_id + '/document.json', 'revision': page_doc['revision']})
                root_doc = json.loads((site / 'document.json').read_bytes())
                root_doc['staticPages'] = entries
                (site / 'document.json').write_text(json.dumps(root_doc, ensure_ascii=False), encoding='utf-8')
            else:
                entries = [{'id': board, 'title': doc['manifest']['title'], 'path': 'document.json', 'revision': doc['revision']}]
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
                       'files': files, 'pages': entries}
            self._put_json('shares/' + share_id + '/control.json', control)
            self._put_json('jobs/' + share_id + '.json', {**job, 'state': 'active', 'cleanupAfter': expires, 'pages': entries})
        url = self.public_url + '/s/' + share_id + '/'
        return {'shareId': share_id, 'url': url, 'accessUrl': url + '#key=' + access_key,
                'accessKey': access_key, 'expiration': expiration, 'expiresAt': expires,
                'revision': doc['revision'], 'pages': entries, 'cleanupExecutor': 'tencent-scf'}

    def authenticate(self, share_id, key):
        control = self.control(share_id)
        require(isinstance(key, str) and bool(ACCESS_KEY.fullmatch(key)) and
                hmac.compare_digest(key_digest(key, control['salt']), control['keyHash']),
                '访问密钥错误', 'INVALID_ACCESS_KEY')
        return control

    def replace(self, service, board, share_id, expected_revision, expiration='7d'):
        """Finish the new publication before revoking the selected old link."""
        previous = self.control(share_id)
        owner = hashlib.sha256(str(Path(service.project_root or service.store.root).resolve()).encode()).hexdigest()
        require(previous['owner'] == owner and previous['dashboardId'] == board,
                'Share belongs to another project/dashboard', 'FORBIDDEN')
        access_key = f'{secrets.randbelow(100000000):08d}'
        while hmac.compare_digest(key_digest(access_key, previous['salt']), previous['keyHash']):
            access_key = f'{secrets.randbelow(100000000):08d}'
        pages = []
        if len(previous.get('pages', [])) > 1:
            from .versions import Versions
            versions = Versions(service.store)
            for page in previous['pages'][1:]:
                revision = versions.status(page['id'])['publishedRevision']
                require(revision is not None, 'Publish each selected page before sharing it', 'REVISION_CONFLICT')
                pages.append({'dashboardId': page['id'], 'expectedRevision': revision})
        result = self.publish(service, board, expected_revision, expiration, access_key, pages)
        try:
            job_key = 'jobs/' + result['shareId'] + '.json'
            raw = self.storage.get(job_key)
            require(raw is not None, 'New share job is missing', 'NOT_FOUND')
            assert raw is not None
            self._put_json(job_key, {**json.loads(raw), 'replacesShareId': share_id})
            self.revoke(service, board, share_id)
        except Exception as error:
            # Return the new credentials even if revocation fails; retry only
            # the old ID rather than creating another publication.
            return {**result, 'previousShareId': share_id, 'previousRevoked': False,
                    'followUp': 'dashboard_share_delete',
                    'warning': {'code': 'PREVIOUS_SHARE_REVOKE_FAILED', 'type': type(error).__name__}}
        return {**result, 'previousShareId': share_id, 'previousRevoked': True}

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
                           'revision': job['revision'], 'expiresAt': job['expiresAt'], 'pages': job.get('pages', []),
                           'replacesShareId': job.get('replacesShareId'),
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
