"""Saved checkpoints and explicit releases are separate lifecycle states."""
from __future__ import annotations

import json

from .cloud_database import CloudDatabase
from .model import json_bytes, require, utcnow


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

    def status(self, board):
        if self.remote:
            return self.remote.call('status', self.store.project, board=board)
        with self.store.connect() as db:
            current = db.execute('SELECT revision FROM boards WHERE id=?', (board,)).fetchone()
            require(current is not None, 'Dashboard not found', 'NOT_FOUND')
            saved = db.execute('SELECT max(revision) FROM revisions WHERE board_id=?', (board,)).fetchone()[0]
            releases = [dict(row) for row in db.execute(
                'SELECT id,revision,created_at FROM releases WHERE board_id=? ORDER BY id DESC LIMIT 100', (board,))]
        return {'draftRevision': current[0], 'savedRevision': saved,
                'publishedRevision': releases[0]['revision'] if releases else None, 'releases': releases}

    def read(self, board, revision):
        if self.remote:
            return self.remote.call('read', self.store.project, board=board, revision=revision)
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
        return self.status(board)

    def delete_checkpoint(self, board, expected, revision):
        require(type(expected) is int and type(revision) is int and expected > 0 and revision > 0,
                'Expected draft and checkpoint revision are required')
        if self.remote:
            database = ReleaseDatabase()
            database.url = database.url.rsplit('/', 1)[0] + '/charts_delete_checkpoint'
            return database.call('delete', self.store.project, board=board, expected=expected, revision=revision)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT revision FROM boards WHERE id=?', (board,)).fetchone()
            require(current is not None and current[0] == expected, 'Reload before deleting', 'REVISION_CONFLICT')
            saved = db.execute('SELECT max(revision) FROM revisions WHERE board_id=?', (board,)).fetchone()[0]
            require(saved != revision, 'The latest saved checkpoint cannot be deleted', 'CHECKPOINT_IN_USE')
            require(db.execute('SELECT 1 FROM releases WHERE board_id=? AND revision=?', (board, revision)).fetchone() is None,
                    'Published versions must be retained', 'CHECKPOINT_IN_USE')
            result = db.execute('DELETE FROM revisions WHERE board_id=? AND revision=?', (board, revision))
            require(result.rowcount == 1, 'Checkpoint not found', 'NOT_FOUND')
            db.execute('DELETE FROM checkpoint_meta WHERE board_id=? AND revision=?', (board, revision))
        self.store._files(board)
        return {'deleted': True, 'revision': revision}
