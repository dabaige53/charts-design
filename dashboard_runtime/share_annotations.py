"""Append-only publication annotations, separate from author content versions."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time

from .cloud_database import CloudDatabase
from .file_lock import exclusive_file_lock
from .model import DashboardError, require


class ShareAnnotationDatabase(CloudDatabase):
    """Reuse the server-only PostgreSQL gateway; no reader gets its API key."""

    kind = 'postgres-v1'

    def __init__(self):
        super().__init__()
        self.url = self.url.rsplit('/', 1)[0] + '/charts_share_annotations'


class LocalShareAnnotations:
    """Private SQLite files are included in the existing workspace checkpoint."""

    kind = 'sqlite-v1'

    def __init__(self, root):
        self.root = Path(root)

    def call(self, action, project='', **payload):
        from .cloud_shares import checked_id

        share_id = checked_id(payload['shareId'])
        with exclusive_file_lock(self.root / 'share-locks' / (share_id + '.lock')):
            return self._call(action, share_id, payload)

    def _call(self, action, share_id, payload):
        path = self.root / 'shares' / share_id / 'annotations.sqlite3'
        retired = self.root / 'retired' / share_id
        if action in ('delete', 'cleanup_claim') and (retired.exists() or not path.is_file()):
            retired.parent.mkdir(parents=True, exist_ok=True)
            retired.touch()
            return {'claimed': True, 'deleted': True}
        require(not retired.exists(), '分享已过期或撤销', 'SHARE_EXPIRED')
        if action == 'ready':
            return {'ready': True}
        if action == 'configure':
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            database = sqlite3.connect(path, timeout=30)
        else:
            require(path.is_file(), '分享批注存储不可用', 'SHARE_UNAVAILABLE')
            database = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=30)
        with closing(database) as db, db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN IMMEDIATE')
            if action in ('delete', 'cleanup_claim') and not db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='scope'").fetchone():
                retired.parent.mkdir(parents=True, exist_ok=True)
                retired.touch()
                return {'claimed': True, 'deleted': True}
            if action == 'configure':
                db.execute('CREATE TABLE IF NOT EXISTS scope (id INTEGER PRIMARY KEY CHECK(id=1), state TEXT, payload TEXT)')
                db.execute('CREATE TABLE IF NOT EXISTS notes (board TEXT, id TEXT, fingerprint TEXT, payload TEXT, '
                           'PRIMARY KEY(board,id))')
                definition = {key: payload.get(key) for key in ('owner', 'pages', 'expiresAt', 'annotationMode', 'sourceDigest')}
                definition['stagingUntil'] = payload.get('stagingUntil', int(time.time()) + 3600)
                row = db.execute('SELECT * FROM scope WHERE id=1').fetchone()
                if row is not None:
                    require(row['state'] in ('uploading', 'active'), '分享已撤销', 'SHARE_EXPIRED')
                    previous = json.loads(row['payload'])
                    require((previous['expiresAt'] is None or time.time() < previous['expiresAt']) and
                            (row['state'] == 'active' or time.time() < previous['stagingUntil']),
                            '分享发布暂存已过期', 'SHARE_EXPIRED')
                    compared = dict(definition)
                    compared['stagingUntil'] = previous['stagingUntil']
                    if definition['sourceDigest'] is not None:
                        compared['expiresAt'] = previous['expiresAt']
                    require(previous == compared, '分享请求已用于其他版本或权限', 'REVISION_CONFLICT')
                    definition = previous
                else:
                    db.execute('INSERT INTO scope VALUES(1,?,?)', ('uploading', json.dumps(definition)))
                return {'ready': True, 'expiresAt': definition['expiresAt'], 'stagingUntil': definition['stagingUntil']}
            row = db.execute('SELECT * FROM scope WHERE id=1').fetchone()
            require(row is not None, '分享不存在', 'SHARE_UNAVAILABLE')
            scope = json.loads(row['payload'])
            if action in ('delete', 'cleanup_claim'):
                now = payload.get('now', time.time())
                due = (row['state'] in ('revoked', 'retired') or payload.get('revoked') or
                       (row['state'] == 'uploading' and scope['stagingUntil'] <= now) or
                       (row['state'] == 'active' and scope['expiresAt'] is not None and scope['expiresAt'] <= now))
                if action == 'cleanup_claim' and not due:
                    return {'claimed': False, 'state': row['state'], 'stagingUntil': scope['stagingUntil']}
                retired.parent.mkdir(parents=True, exist_ok=True)
                retired.touch()
                db.execute('DELETE FROM notes')
                db.execute("UPDATE scope SET state='retired',payload='{}' WHERE id=1")
                return {'claimed': True, 'deleted': True}
            if action == 'revoke':
                db.execute("UPDATE scope SET state='revoked' WHERE id=1")
                return {'revoked': True}
            if action == 'activate':
                require(row['state'] in ('uploading', 'active') and
                        (scope['expiresAt'] is None or time.time() < scope['expiresAt']) and
                        (row['state'] == 'active' or time.time() < scope['stagingUntil']),
                        '分享已过期或撤销', 'SHARE_EXPIRED')
                db.execute("UPDATE scope SET state='active' WHERE id=1")
                return {'active': True}
            require(row['state'] == 'active' and (scope['expiresAt'] is None or time.time() < scope['expiresAt']),
                    '分享已过期或撤销', 'SHARE_EXPIRED')
            board = payload['dashboardId']
            page = next((page for page in scope['pages'] if page['id'] == board), None)
            require(page is not None, '此分享不包含该页面', 'FORBIDDEN')
            if action == 'read':
                return [json.loads(note['payload']) for note in db.execute(
                    'SELECT payload FROM notes WHERE board=? ORDER BY rowid', (board,))]
            require(action == 'append', 'Unknown annotation operation', 'INVALID_ARGUMENT')
            require(scope['annotationMode'] == 'annotate', '此分享仅允许查看', 'FORBIDDEN')
            note = payload['annotation']
            require(note['context']['designRevision'] == page['revision'], '批注版本不匹配', 'REVISION_CONFLICT')
            existing = db.execute('SELECT * FROM notes WHERE board=? AND id=?', (board, note['id'])).fetchone()
            if existing is not None:
                require(existing['fingerprint'] == payload['fingerprint'], '此批注编号已用于其他内容', 'ANNOTATION_CONFLICT')
                return json.loads(existing['payload'])
            count = db.execute('SELECT count(*) FROM notes WHERE board=?', (board,)).fetchone()[0]
            require(count < 100, '此页面最多保存 100 条批注', 'ANNOTATION_LIMIT')
            db.execute('INSERT INTO notes VALUES(?,?,?,?)', (board, note['id'], payload['fingerprint'], json.dumps(note)))
            return note


def annotation_store(storage):
    configured = getattr(storage, 'annotation_store', None)
    if configured is not None:
        return configured
    if getattr(storage, 'root', None) is not None:
        return LocalShareAnnotations(storage.root.resolve())
    try:
        return ShareAnnotationDatabase()
    except DashboardError as error:
        raise DashboardError('ANNOTATIONS_NOT_CONFIGURED', '分享服务尚未配置持久批注数据库', 503) from error
