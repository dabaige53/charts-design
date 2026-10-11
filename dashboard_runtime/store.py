"""SQLite transactions provide one revision stream across web, CLI and MCP."""
from __future__ import annotations
import json
import os
import sqlite3
from pathlib import Path
from .model import DashboardError, apply_operations, identifier, json_bytes, new_document, require, utcnow, validate

class Store:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.root / 'dashboards.sqlite3'
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS boards (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions (
                    board_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL, action TEXT NOT NULL, document TEXT NOT NULL,
                    PRIMARY KEY(board_id, revision));
            ''')
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def connect(self):
        connection = sqlite3.connect(str(self.path), timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def create(self, board_id, title, document=None):
        identifier(board_id)
        doc = document or new_document(board_id, title)
        doc = json.loads(json_bytes(doc))
        doc['id'], doc['revision'] = board_id, 1
        validate(doc)
        try:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                raw = json_bytes(doc).decode()
                db.execute('INSERT INTO boards VALUES (?, ?, ?)', (board_id, 1, raw))
                db.execute('INSERT INTO revisions VALUES (?, ?, ?, ?, ?)', (board_id, 1, utcnow(), 'create', raw))
        except sqlite3.IntegrityError as exc:
            raise DashboardError('ALREADY_EXISTS', 'Dashboard already exists', 409) from exc
        return doc

    def get(self, board_id):
        identifier(board_id)
        with self.connect() as db:
            row = db.execute('SELECT document FROM boards WHERE id=?', (board_id,)).fetchone()
        if row is None:
            raise DashboardError('NOT_FOUND', 'Dashboard not found', 404)
        return json.loads(row['document'])

    def list(self):
        with self.connect() as db:
            rows = db.execute('SELECT id,revision,document FROM boards ORDER BY id').fetchall()
        return [{'id': r['id'], 'revision': r['revision'], 'title': json.loads(r['document'])['manifest']['title']} for r in rows]

    def history(self, board_id):
        self.get(board_id)
        with self.connect() as db:
            rows = db.execute('SELECT revision,created_at,action FROM revisions WHERE board_id=? ORDER BY revision DESC LIMIT 100', (board_id,)).fetchall()
        return [dict(row) for row in rows]

    def mutate(self, board_id, expected_revision, operations=None, restore_revision=None):
        identifier(board_id)
        require(type(expected_revision) is int and expected_revision > 0, 'expectedRevision is required')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM boards WHERE id=?', (board_id,)).fetchone()
            if row is None:
                raise DashboardError('NOT_FOUND', 'Dashboard not found', 404)
            if row['revision'] != expected_revision:
                raise DashboardError('REVISION_CONFLICT', f'Expected revision {expected_revision}; current revision is {row["revision"]}. Reload before editing.', 409)
            if restore_revision is not None:
                require(type(restore_revision) is int, 'restoreRevision must be an integer')
                old = db.execute('SELECT document FROM revisions WHERE board_id=? AND revision=?', (board_id, restore_revision)).fetchone()
                require(old is not None, 'Historical revision is unavailable')
                doc, action = json.loads(old['document']), f'restore:{restore_revision}'
            else:
                doc = apply_operations(json.loads(row['document']), operations)
                action = ','.join(op['op'] for op in operations)
            doc['revision'] = expected_revision + 1
            validate(doc)
            raw = json_bytes(doc).decode()
            db.execute('UPDATE boards SET revision=?,document=? WHERE id=?', (doc['revision'], raw, board_id))
            db.execute('INSERT INTO revisions VALUES (?, ?, ?, ?, ?)', (board_id, doc['revision'], utcnow(), action, raw))
            db.execute('DELETE FROM revisions WHERE board_id=? AND revision<=?', (board_id, doc['revision'] - 100))
        return doc
