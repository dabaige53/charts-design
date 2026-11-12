"""Saved checkpoints and explicit releases are separate lifecycle states."""
from __future__ import annotations

import json
import hashlib
import uuid

from .cloud_database import CloudDatabase
from .model import DashboardError, json_bytes, require, utcnow


class ReleaseDatabase(CloudDatabase):
    def __init__(self):
        super().__init__()
        self.url = self.url.rsplit('/', 1)[0] + '/charts_release'


class Versions:
    def __init__(self, store):
        self.store = store
        self.remote = ReleaseDatabase() if getattr(store, 'database', None) is not None else None
        if self.remote is None:
            with store.connect() as db:
                db.execute('''CREATE TABLE IF NOT EXISTS releases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, board_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, created_at TEXT NOT NULL, document TEXT NOT NULL)''')
                db.execute('CREATE TABLE IF NOT EXISTS version_heads(board_id TEXT PRIMARY KEY, published INTEGER)')
                db.execute('''INSERT OR IGNORE INTO version_heads
                    SELECT board_id,revision FROM releases WHERE id IN (SELECT max(id) FROM releases GROUP BY board_id)''')
                db.execute('''CREATE TABLE IF NOT EXISTS version_delete_plans (
                    token TEXT PRIMARY KEY, board_id TEXT, revision INTEGER, fingerprint TEXT, plan TEXT)''')

    def status(self, board):
        if self.remote:
            return self.remote.call('status', self.store.project, board=board)
        with self.store.connect() as db:
            current = db.execute('SELECT revision FROM boards WHERE id=?', (board,)).fetchone()
            require(current is not None, 'Dashboard not found', 'NOT_FOUND')
            saved = db.execute('SELECT max(revision) FROM revisions WHERE board_id=?', (board,)).fetchone()[0]
            releases = [dict(row) for row in db.execute(
                'SELECT id,revision,created_at FROM releases WHERE board_id=? ORDER BY id DESC LIMIT 100', (board,))]
            head = db.execute('SELECT published FROM version_heads WHERE board_id=?', (board,)).fetchone()
        return {'draftRevision': current[0], 'savedRevision': saved, 'frozen': True,
                'publishedRevision': head[0] if head else None, 'releases': releases, 'deletionJobs': []}

    def read(self, board, revision):
        if self.remote:
            return self.store._decode(self.remote.call('read', self.store.project, board=board, revision=revision))
        with self.store.connect() as db:
            row = db.execute('SELECT document FROM revisions WHERE board_id=? AND revision=?', (board, revision)).fetchone()
            if row is None:
                row = db.execute('SELECT document FROM releases WHERE board_id=? AND revision=? ORDER BY id DESC LIMIT 1',
                                 (board, revision)).fetchone()
        require(row is not None, 'Saved version not found', 'NOT_FOUND')
        return json.loads(row[0])

    def publish(self, board, expected, revision):
        require(type(expected) is int and type(revision) is int and expected > 0 and revision > 0,
                'Expected draft and saved revision are required')
        if self.remote:
            return self.remote.call('publish', self.store.project, board=board,
                                    expected=expected, revision=revision, at=utcnow())
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT revision FROM boards WHERE id=?', (board,)).fetchone()
            require(current is not None and current[0] == expected, 'Reload before publishing', 'REVISION_CONFLICT')
            row = db.execute('SELECT document FROM revisions WHERE board_id=? AND revision=?', (board, revision)).fetchone()
            if row is None:
                row = db.execute('SELECT document FROM releases WHERE board_id=? AND revision=? ORDER BY id DESC LIMIT 1',
                                 (board, revision)).fetchone()
            require(row is not None, 'Publish a saved version', 'NOT_FOUND')
            last = db.execute('SELECT revision FROM releases WHERE board_id=? ORDER BY id DESC LIMIT 1', (board,)).fetchone()
            if last is None or last[0] != revision:
                db.execute('INSERT INTO releases(board_id,revision,created_at,document) VALUES(?,?,?,?)',
                           (board, revision, utcnow(), json_bytes(json.loads(row[0])).decode()))
            db.execute('INSERT OR REPLACE INTO version_heads VALUES(?,?)', (board, revision))
        return self.status(board)

    def delete_preview(self, board, expected, revision):
        if self.remote:
            # Reconcile existing COS publications before presenting the impact.
            from .cloud_shares import CloudShares
            manager = CloudShares.from_environment()
            manager.index_project(self.store)
            plan = self.store.assets.call('delete_preview', board=board, expected=expected,
                                           revision=revision, token=uuid.uuid4().hex)
            for share in plan['shares']:
                share['url'] = manager.public_url + '/s/' + share['shareId'] + '/'
            return plan
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            require(self.store.revision(board) == expected, 'Reload before deleting', 'REVISION_CONFLICT')
            doc = self.read(board, revision)
            fingerprint = self._fingerprint(db, board)
            next_saved = db.execute('SELECT max(revision) FROM revisions WHERE board_id=? AND revision<>?',
                                    (board, revision)).fetchone()[0]
            head = db.execute('SELECT published FROM version_heads WHERE board_id=?', (board,)).fetchone()
            token = uuid.uuid4().hex
            plan = {'token': token, 'revision': revision, 'shares': [], 'objects': [], 'datasets': [],
                    'retained': [{'version': ref['version'], 'references': [{'source': 'local-data'}]}
                                 for ref in doc['snapshot'].get('datasetRefs', {}).values()],
                    'cosBytes': 0, 'postgresBytes': 0, 'nextSavedRevision': next_saved,
                    'clearsPublication': bool(head and head[0] == revision), 'checkedAt': utcnow()}
            db.execute('INSERT INTO version_delete_plans VALUES(?,?,?,?,?)',
                       (token, board, revision, fingerprint, json.dumps(plan)))
        return plan

    @staticmethod
    def _fingerprint(db, board):
        parts = []
        for table, field in (('boards', 'id'), ('revisions', 'board_id'), ('releases', 'board_id'),
                             ('version_heads', 'board_id'), ('checkpoint_meta', 'board_id'),
                             ('annotations', 'board_id'), ('annotation_events', 'board_id')):
            parts.extend([list(row) for row in db.execute(f'SELECT * FROM {table} WHERE {field}=?', (board,))])
        return hashlib.sha256(json_bytes(parts)).hexdigest()

    def delete_status(self, board, job_id, retry=False):
        require(self.remote is not None, 'Cloud deletion task required', 'UNSUPPORTED_OPERATION')
        job = self.store.assets.call('delete_status', board=board, id=job_id)
        return self.store.assets.delete_job(job) if retry else job

    def delete_checkpoint(self, board, expected, revision, confirmation=None):
        require(type(expected) is int and type(revision) is int and expected > 0 and revision > 0,
                'Expected draft and checkpoint revision are required')
        if self.remote:
            require(bool(confirmation), 'Review deletion impact first', 'CONFIRMATION_REQUIRED')
            job = self.store.assets.call('delete_begin', board=board, expected=expected,
                                         revision=revision, token=confirmation)
            return self.store.assets.delete_job(job)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT revision FROM boards WHERE id=?', (board,)).fetchone()
            if current is None or current[0] != expected:
                raise DashboardError('REVISION_CONFLICT', 'Reload before deleting')
            plan = db.execute('SELECT * FROM version_delete_plans WHERE token=? AND board_id=? AND revision=?',
                              (confirmation, board, revision)).fetchone()
            if plan is None:
                raise DashboardError('CONFIRMATION_REQUIRED', 'Review deletion impact first')
            require(plan['fingerprint'] == self._fingerprint(db, board), '删除影响已变化，请重新确认', 'PLAN_CHANGED')
            db.execute('DELETE FROM revisions WHERE board_id=? AND revision=?', (board, revision))
            db.execute('DELETE FROM releases WHERE board_id=? AND revision=?', (board, revision))
            db.execute('UPDATE version_heads SET published=NULL WHERE board_id=? AND published=?', (board, revision))
            db.execute('DELETE FROM checkpoint_meta WHERE board_id=? AND revision=?', (board, revision))
            if current[0] == revision:
                stored = json.loads(db.execute('SELECT document FROM boards WHERE id=?', (board,)).fetchone()[0])
                stored['revision'] = revision + 1
                db.execute('UPDATE boards SET revision=?,document=? WHERE id=?',
                           (revision + 1, json_bytes(stored).decode(), board))
            db.execute('DELETE FROM batches WHERE board_id=?', (board,))
            db.execute('DELETE FROM version_delete_plans WHERE token=?', (confirmation,))
        self.store._files(board)
        return {'deleted': True, 'revision': revision, 'state': 'complete'}
