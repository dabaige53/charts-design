"""Publish fixed workspace versions through an already configured share service.

Only immutable export bytes leave the author's workspace. Service credentials
stay in this process; share references live beside the project files
and survive disposal of the runtime cache. Feedback is fetched on demand.
"""
from __future__ import annotations

from contextlib import closing, contextmanager, nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import __version__
from .file_lock import exclusive_file_lock
from .model import DashboardError, identifier, json_bytes, require

UUID_V4 = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
SHARE_ID = re.compile(r'^[0-9a-f]{32}$')


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the author's service bearer to a redirected origin.
        return None


class LocalShares:
    def __init__(self, service):
        require(service.project_root is not None, 'A workspace project is required', 'PROJECT_REQUIRED')
        self.service = service
        self.url = os.environ.get('CHARTS_SHARE_SERVICE_URL', '').rstrip('/')
        require(bool(self.url), 'Configure CHARTS_SHARE_SERVICE_URL on the author workspace', 'CLOUD_SHARE_NOT_CONFIGURED')
        require(getattr(getattr(service.store, 'database', None), 'backend', None) != 'cloudbase',
                'Use a local or self-hosted workspace to publish a new share', 'INVALID_CONFIG')
        self.token = os.environ.get('CHARTS_SHARE_SERVICE_TOKEN', '')
        self.project = os.environ.get('CHARTS_SHARE_SERVICE_PROJECT', 'default')
        self.parquet_layout = os.environ.get('CHARTS_SHARE_PARQUET_LAYOUT', 'sharded')
        require(self.parquet_layout in ('sharded', 'single'),
                'CHARTS_SHARE_PARQUET_LAYOUT must be sharded or single', 'INVALID_CONFIG')
        parsed = urlsplit(self.url)
        require(bool(parsed.netloc) and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
                and (parsed.scheme == 'https' or parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')),
                'Configure an HTTPS CHARTS_SHARE_SERVICE_URL (loopback HTTP is allowed for local verification)', 'INVALID_CONFIG')
        require(bool(self.token) and '\r' not in self.token and '\n' not in self.token,
                'Configure CHARTS_SHARE_SERVICE_TOKEN in the local server environment', 'INVALID_CONFIG')
        require(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', self.project) is not None,
                'CHARTS_SHARE_SERVICE_PROJECT must name the authorized destination project', 'INVALID_CONFIG')
        self.root = Path(service.project_root).resolve() / 'dashboards'
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'share-references.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS identity(id INTEGER PRIMARY KEY CHECK(id=1), source TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests(
                    id TEXT PRIMARY KEY, board TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    revision INTEGER NOT NULL, service_url TEXT NOT NULL, project TEXT NOT NULL,
                    archive TEXT, archive_sha TEXT, receipt TEXT, state TEXT NOT NULL, created_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS requests_board ON requests(board,created_at);
            ''')
            db.execute('INSERT OR IGNORE INTO identity VALUES(1,?)', (str(uuid.uuid4()),))
            self.source = db.execute('SELECT source FROM identity WHERE id=1').fetchone()[0]
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            with db:
                yield db

    def _request(self, method, path, *, headers=None, archive=None):
        request_headers = {
            'Authorization': 'Bearer ' + self.token,
            'User-Agent': 'Charts-Design-Publisher/' + __version__,
            **(headers or {}),
        }
        opener = build_opener(_NoRedirect())
        try:
            with (archive.open('rb') if archive else nullcontext(None)) as body:
                if archive:
                    request_headers['Content-Length'] = str(archive.stat().st_size)
                request = Request(self.url + path, data=body if archive else None,
                                  headers=request_headers, method=method)
                with opener.open(request, timeout=120) as response:
                    value = json.load(response)
            require(isinstance(value, dict) and value.get('ok') is not False,
                    'Share service did not confirm the request', 'SHARE_SERVICE_FAILED')
            return value
        except HTTPError as error:
            try:
                value = json.loads(error.read(1024 * 1024))
                details = value.get('error', {})
                message = details.get('message') or 'Share service rejected the request'
                code = details.get('code') or 'SHARE_SERVICE_FAILED'
            except (ValueError, TypeError, AttributeError):
                message, code = 'Share service rejected the request', 'SHARE_SERVICE_FAILED'
            finally:
                error.close()
            raise DashboardError(code, message, error.code) from error
        except (URLError, TimeoutError, OSError, ValueError) as error:
            raise DashboardError('SHARE_SERVICE_UNAVAILABLE',
                                 'Could not confirm the share service response. Retry the same request.', 503) from error

    @staticmethod
    def _checksum(path):
        value = hashlib.sha256()
        with path.open('rb') as source:
            while chunk := source.read(1024 * 1024):
                value.update(chunk)
        return value.hexdigest()

    def _reference(self, board, share_id):
        identifier(board)
        require(isinstance(share_id, str) and SHARE_ID.fullmatch(share_id) is not None, 'Invalid share ID', 'INVALID_ARGUMENT')
        with self.connect() as db:
            rows = db.execute('SELECT * FROM requests WHERE board=? AND receipt IS NOT NULL', (board,)).fetchall()
        for row in rows:
            receipt = json.loads(row['receipt'])
            if receipt.get('shareId') == share_id:
                require(row['service_url'] == self.url and row['project'] == self.project,
                        'Configure the original share service to access this publication', 'SHARE_SERVICE_MISMATCH')
                return dict(row), receipt
        raise DashboardError('FORBIDDEN', 'This share does not belong to this local project and dashboard', 403)

    def _owner_path(self, board, share_id):
        return '/api/v1/publications/' + quote(share_id) + '?' + urlencode({
            'source': self.source, 'project': self.project, 'dashboardId': board})

    def publish(self, board, revision, expiration='7d', *, annotation_mode='view', request_id):
        from .deployment import export_site
        from .model import live_datasets
        from .versions import Versions

        identifier(board)
        require(type(revision) is int and revision > 0, 'Choose a saved revision', 'INVALID_ARGUMENT')
        require(isinstance(request_id, str) and UUID_V4.fullmatch(request_id) is not None,
                'Use a stable UUID v4 requestId when retrying', 'INVALID_ARGUMENT')
        require(expiration in ('never', '7d', '30d') and annotation_mode in ('view', 'annotate'),
                'Invalid share options', 'INVALID_ARGUMENT')
        versions = Versions(self.service.store)
        # The empty draft-revision slot preserves existing standalone receipts.
        fingerprint = hashlib.sha256(json_bytes([board, revision, None, expiration,
                                                 annotation_mode, self.url, self.project])).hexdigest()
        # The lock serializes uncertain retries without holding a SQLite write
        # transaction across data encoding or a network request.
        with exclusive_file_lock(self.root / '.share-locks' / (request_id + '.lock')):
            with self.connect() as db:
                row = db.execute('SELECT * FROM requests WHERE id=?', (request_id,)).fetchone()
            if row:
                require(row['fingerprint'] == fingerprint, 'This request ID was used for different share options', 'IDEMPOTENCY_CONFLICT')
                if row['receipt']:
                    receipt = json.loads(row['receipt'])
                    self.feedback(board, receipt['shareId'])  # Recheck revocation/expiry before reporting a retry as successful.
                    return receipt
            else:
                document = versions.read(board, revision)
                require(not live_datasets(document), '实时 SQL 看板请通过运行服务查看', 'LIVE_DATA_REQUIRES_RUNTIME')
                report = self.service._doctor(document, 'full', reuse=True)
                require(report['passed'], 'Saved version checks failed.', 'DOCTOR_FAILED')
                with self.connect() as db:
                    db.execute('INSERT INTO requests(id,board,fingerprint,revision,service_url,project,state,created_at) VALUES(?,?,?,?,?,?,?,?)',
                               (request_id, board, fingerprint, revision, self.url, self.project, 'uploading', time.time()))
                    row = db.execute('SELECT * FROM requests WHERE id=?', (request_id,)).fetchone()
            try:
                if row['archive']:
                    archive = Path(row['archive'])
                    require(archive.is_file() and self._checksum(archive) == row['archive_sha'],
                            'The pending publication copy is missing or changed; inspect the existing request before creating another share',
                            'SHARE_RETRY_ASSET_MISSING')
                else:
                    exported = export_site(self.service.store, board, document=versions.read(board, revision),
                                           data_format='parquet', single_parquet=self.parquet_layout == 'single')['export']
                    archive = Path(exported['path'])
                    with self.connect() as db:
                        db.execute('UPDATE requests SET archive=?,archive_sha=? WHERE id=?',
                                   (str(archive), self._checksum(archive), request_id))
                receipt = self._request('POST', '/api/v1/publications', archive=archive, headers={
                    'Content-Type': 'application/zip', 'X-Charts-Source': self.source,
                    'X-Charts-Project': self.project, 'X-Charts-Request': request_id,
                    'X-Charts-Expiration': expiration, 'X-Charts-Annotation-Mode': annotation_mode})
                require(isinstance(receipt.get('shareId'), str) and SHARE_ID.fullmatch(receipt['shareId']) is not None
                        and isinstance(receipt.get('url'), str) and bool(receipt['url'])
                        and isinstance(receipt.get('accessKey'), str) and re.fullmatch(r'[0-9]{8}', receipt['accessKey']) is not None
                        and receipt.get('revision') == revision and receipt.get('annotationMode', 'view') == annotation_mode,
                        'Share service returned a different publication', 'SHARE_SERVICE_FAILED')
                with self.connect() as db:
                    db.execute('UPDATE requests SET receipt=?,state=? WHERE id=?', (json.dumps(receipt, ensure_ascii=False), 'active', request_id))
            except OSError as error:
                raise DashboardError('SHARE_EXPORT_FAILED', 'Could not prepare the fixed publication copy.', 503) from error
            return receipt

    def feedback(self, board, share_id):
        _, receipt = self._reference(board, share_id)
        result = self._request('GET', self._owner_path(board, share_id))
        require(result.get('shareId') == share_id and result.get('revision') == receipt['revision'],
                'Feedback belongs to another publication', 'SHARE_SERVICE_FAILED')
        return result

    def status(self, board, share_id=None):
        identifier(board)
        with self.connect() as db:
            rows = db.execute('SELECT * FROM requests WHERE board=? AND receipt IS NOT NULL ORDER BY created_at DESC', (board,)).fetchall()
            pending = [dict(row) for row in db.execute(
                'SELECT id AS requestId,revision,state FROM requests WHERE board=? AND receipt IS NULL ORDER BY created_at DESC', (board,))]
        shares = []
        for row in rows:
            receipt = json.loads(row['receipt'])
            if share_id is not None and receipt['shareId'] != share_id:
                continue
            due = receipt.get('expiresAt') is not None and time.time() >= receipt['expiresAt']
            cleanup = receipt.get('cleanup', {})
            shares.append({**{key: receipt[key] for key in ('shareId', 'url', 'revision', 'expiresAt', 'pages', 'annotationMode') if key in receipt},
                           'state': 'expired' if due and row['state'] == 'active' else row['state'],
                           'cleanupState': cleanup.get('cleanupState', 'pending') if due or row['state'] == 'revoked' else 'scheduled' if receipt.get('expiresAt') else 'not_scheduled',
                           'feedbackEndpoint': '/api/publications/' + receipt['shareId'] + '/feedback?' + urlencode({'dashboardId': board}),
                           'localReference': True})
        return {'shares': shares, 'pendingRequests': pending, 'cleanupExecutor': 'share-service'}

    def revoke(self, board, share_id):
        row, _ = self._reference(board, share_id)
        with exclusive_file_lock(self.root / '.share-locks' / (row['id'] + '.lock')):
            row, receipt = self._reference(board, share_id)
            cleanup = receipt.get('cleanup', {})
            if row['state'] == 'revoked' and cleanup.get('cleanupState') == 'complete':
                return {'shareId': share_id, 'revoked': True, **cleanup}
            result = self._request('DELETE', self._owner_path(board, share_id))
            require(result.get('revoked') is True, 'Share service did not confirm revocation', 'SHARE_SERVICE_FAILED')
            receipt['cleanup'] = {key: result[key] for key in ('cleanupState', 'cleanupExecutor') if key in result}
            with self.connect() as db:
                db.execute('UPDATE requests SET state=?,receipt=? WHERE id=?',
                           ('revoked', json.dumps(receipt, ensure_ascii=False), row['id']))
            return result

    def replace(self, board, share_id, revision, expiration='7d'):
        _, previous = self._reference(board, share_id)
        identity = hashlib.sha256(json_bytes([self.source, board, share_id, revision, expiration])).digest()[:16]
        request_id = str(uuid.UUID(bytes=identity, version=4))
        result = self.publish(board, revision, expiration, annotation_mode=previous.get('annotationMode', 'view'),
                              request_id=request_id)
        try:
            self.revoke(board, share_id)
        except DashboardError as error:
            return {**result, 'previousShareId': share_id, 'previousRevoked': False,
                    'followUp': 'dashboard_share_delete', 'warning': error.as_dict()['error']}
        return {**result, 'previousShareId': share_id, 'previousRevoked': True}
