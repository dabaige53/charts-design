"""SQLite transactions provide one revision stream across web, CLI and MCP."""
from __future__ import annotations
import json
import copy
import sqlite3
from pathlib import Path
from .model import DashboardError, MAX_ROWS, apply_operations, identifier, inferred_fields, json_bytes, new_document, require, utcnow, validate
from .local_data import LocalData

class Store:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.root / 'dashboards.sqlite3'
        self.data = LocalData(self.root)
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

    def compact(self, document):
        """Persist immutable data once; revision records contain references only."""
        doc = copy.deepcopy(document)
        doc.pop('computed', None)
        snapshot = doc['snapshot']
        refs = snapshot.setdefault('datasetRefs', {})
        for key, rows in list(snapshot['datasets'].items()):
            refs[key] = self.data.import_rows(rows, doc['manifest']['datasets'][key]['fields'])
        snapshot['datasets'] = {}
        tables = snapshot.setdefault('componentDataRefs', {})
        for key, component in doc['manifest']['components'].items():
            if component.get('kind') == 'legacy' and component.get('family') == 'table' and not component.get('binding'):
                rows = component['config'].get('rows', [])
                if rows:
                    tables[key] = self.data.import_rows(rows, inferred_fields(rows))
                    component['config']['rows'] = []
                    component['config']['rowsRef'] = tables[key]['version']
                elif component['config'].get('rowsRef') != tables.get(key, {}).get('version'):
                    tables.pop(key, None)
            elif component.get('kind') == 'legacy' and component.get('family') == 'table' and component.get('binding'):
                component['config']['rows'] = []
        snapshot['componentDataRefs'] = {key: ref for key, ref in tables.items() if key in doc['manifest']['components']}
        for ref in [*refs.values(), *snapshot['componentDataRefs'].values()]:
            require(self.data.describe(ref['version']) == ref, 'Local data reference does not match its immutable version')
        self.statistical_document(doc)  # Validate raw statistical observations without sending them to the UI.
        return validate(doc)

    def statistical_document(self, document):
        doc = copy.deepcopy(document)
        for component in doc['manifest']['components'].values():
            if component.get('kind') == 'statistical':
                from .statistical import MAX_STAT_ROWS, validate_statistical
                key = component['datasetId']
                ref = doc['snapshot'].get('datasetRefs', {}).get(key)
                if ref:
                    require(ref['rowCount'] <= MAX_STAT_ROWS, 'Statistical plots accept at most 5000 raw rows')
                    doc['snapshot']['datasets'][key] = list(self.data.iter_rows(ref))
                validate_statistical(doc, component)
        return doc

    def hydrate(self, document):
        """Compatibility export is explicit and bounded by the old snapshot contract."""
        doc = copy.deepcopy(document)
        snapshot = doc['snapshot']
        refs = snapshot.get('datasetRefs', {})
        table_refs = snapshot.get('componentDataRefs', {})
        require(sum(ref['rowCount'] for ref in [*refs.values(), *table_refs.values()]) <= MAX_ROWS,
                'Large local data cannot be embedded in a snapshot; use dataset_export for full CSV', 'LOCAL_DATA_REQUIRED')
        for key, ref in refs.items():
            snapshot['datasets'][key] = list(self.data.iter_rows(ref))
        for key, ref in table_refs.items():
            if key in doc['manifest']['components']:
                doc['manifest']['components'][key]['config']['rows'] = list(self.data.iter_rows(ref))
                doc['manifest']['components'][key]['config'].pop('rowsRef', None)
        snapshot.pop('datasetRefs', None)
        snapshot.pop('componentDataRefs', None)
        return validate(doc)

    def compatible(self, document):
        if document['snapshot'].get('localMode'):
            return document
        refs = [*document['snapshot'].get('datasetRefs', {}).values(), *document['snapshot'].get('componentDataRefs', {}).values()]
        return self.hydrate(document) if sum(r['rowCount'] for r in refs) <= MAX_ROWS else document

    def create(self, board_id, title, document=None):
        identifier(board_id)
        doc = document or new_document(board_id, title)
        doc = json.loads(json_bytes(doc))
        doc['id'], doc['revision'] = board_id, 1
        doc = self.compact(validate(doc))
        try:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                raw = json_bytes(doc).decode()
                db.execute('INSERT INTO boards VALUES (?, ?, ?)', (board_id, 1, raw))
                db.execute('INSERT INTO revisions VALUES (?, ?, ?, ?, ?)', (board_id, 1, utcnow(), 'create', raw))
        except sqlite3.IntegrityError as exc:
            raise DashboardError('ALREADY_EXISTS', 'Dashboard already exists', 409) from exc
        return self.compatible(doc)

    def get(self, board_id, hydrate=True):
        identifier(board_id)
        with self.connect() as db:
            row = db.execute('SELECT document FROM boards WHERE id=?', (board_id,)).fetchone()
        if row is None:
            raise DashboardError('NOT_FOUND', 'Dashboard not found', 404)
        doc = json.loads(row['document'])
        return self.compatible(doc) if hydrate else doc

    def list(self):
        with self.connect() as db:
            rows = db.execute("SELECT id,revision,json_extract(document, '$.manifest.title') AS title FROM boards ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def revision(self, board_id):
        identifier(board_id)
        with self.connect() as db:
            row = db.execute('SELECT revision FROM boards WHERE id=?', (board_id,)).fetchone()
        if row is None:
            raise DashboardError('NOT_FOUND', 'Dashboard not found', 404)
        return row['revision']

    def history(self, board_id):
        self.get(board_id, hydrate=False)
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
                require(isinstance(operations, list), 'operations must be an array')
                assert isinstance(operations, list)
                doc = apply_operations(json.loads(row['document']), operations)
                action = ','.join(op['op'] for op in operations)
            doc['revision'] = expected_revision + 1
            doc = self.compact(validate(doc))
            raw = json_bytes(doc).decode()
            db.execute('UPDATE boards SET revision=?,document=? WHERE id=?', (doc['revision'], raw, board_id))
            db.execute('INSERT INTO revisions VALUES (?, ?, ?, ?, ?)', (board_id, doc['revision'], utcnow(), action, raw))
            db.execute('DELETE FROM revisions WHERE board_id=? AND revision<=?', (board_id, doc['revision'] - 100))
        return self.compatible(doc)

    def migrate(self, board_id, expected_revision):
        """Back up the old artifacts before converting their histories to references."""
        identifier(board_id)
        import uuid
        backup_id = board_id + '-' + uuid.uuid4().hex
        backup_dir = self.root / 'backups'
        backup_dir.mkdir(mode=0o700, exist_ok=True)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM boards WHERE id=?', (board_id,)).fetchone()
            require(row is not None, 'Dashboard not found', 'NOT_FOUND')
            require(row['revision'] == expected_revision, 'Reload before migrating', 'REVISION_CONFLICT')
            revisions = [dict(r) for r in db.execute('SELECT * FROM revisions WHERE board_id=?', (board_id,))]
            backup = backup_dir / (backup_id + '.json')
            backup.write_text(json.dumps({'board': dict(row), 'revisions': revisions}, ensure_ascii=False))
            backup.chmod(0o600)
            current = self.compact(json.loads(row['document']))
            current['snapshot']['localMode'] = True
            db.execute('UPDATE boards SET document=? WHERE id=?', (json_bytes(current).decode(), board_id))
            for old in revisions:
                doc = self.compact(json.loads(old['document']))
                db.execute('UPDATE revisions SET document=? WHERE board_id=? AND revision=?',
                           (json_bytes(doc).decode(), board_id, old['revision']))
        return {'backupId': backup_id, 'revision': expected_revision, 'revisionsMigrated': len(revisions)}

    def rollback_migration(self, board_id, expected_revision, backup_id):
        """Restore backed-up content as a new revision; never rewrite later history."""
        require(isinstance(backup_id, str) and backup_id.startswith(board_id + '-')
                and all(c.isalnum() or c in '-_' for c in backup_id), 'Invalid migration backup id')
        path = self.root / 'backups' / (backup_id + '.json')
        require(path.is_file(), 'Migration backup not found')
        old = json.loads(path.read_text())['board']
        require(old['id'] == board_id, 'Migration backup belongs to another dashboard')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision FROM boards WHERE id=?', (board_id,)).fetchone()
            require(row is not None and row['revision'] == expected_revision, 'Reload before rollback', 'REVISION_CONFLICT')
            doc = json.loads(old['document'])
            doc['revision'] = expected_revision + 1
            validate(doc)
            raw = json_bytes(doc).decode()
            db.execute('UPDATE boards SET revision=?,document=? WHERE id=?', (doc['revision'], raw, board_id))
            db.execute('INSERT INTO revisions VALUES (?, ?, ?, ?, ?)', (board_id, doc['revision'], utcnow(), 'migration-rollback', raw))
        return doc
