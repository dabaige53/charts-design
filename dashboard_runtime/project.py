"""Project-owned assets, draft revisions and explicit checkpoints."""
from pathlib import Path
import copy
import json
import sqlite3
import uuid
from .store import Store
from .local_data import LocalData
from .model import apply_operations, validate, json_bytes, require, utcnow

DEFAULTS = {'history': {'keepCheckpoints': 100}, 'loading': {'debounceMs': 150, 'maxConcurrent': 4, 'pageSize': 50}}

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)

class ProjectStore(Store):
    def __init__(self, project_root, runtime_root):
        self.project_root = Path(project_root).expanduser().resolve()
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        config = self.project_root / 'charts-project.json'
        if not config.exists():
            write_json(config, DEFAULTS)
        self.config = json.loads(config.read_text())
        self.config = {key: {**value, **self.config.get(key, {})} for key, value in DEFAULTS.items()}
        require(1 <= self.config['history']['keepCheckpoints'] <= 10000, 'Invalid checkpoint retention')
        super().__init__(self.project_root / 'dashboards')
        self.data = LocalData(self.project_root / 'data')
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS checkpoint_meta (board_id TEXT, revision INTEGER, name TEXT, published INTEGER DEFAULT 0, PRIMARY KEY(board_id,revision));
                CREATE TABLE IF NOT EXISTS batches (board_id TEXT PRIMARY KEY, batch_id TEXT, base_revision INTEGER);
                CREATE TABLE IF NOT EXISTS annotations (board_id TEXT PRIMARY KEY, payload TEXT);
                CREATE TABLE IF NOT EXISTS annotation_events (board_id TEXT, at TEXT, revision INTEGER, payload TEXT);
            ''')

    def compatible(self, document):
        return document

    def display_revision(self, board):
        with self.connect() as db:
            return db.execute('SELECT max(revision) FROM revisions WHERE board_id=?',(board,)).fetchone()[0]

    def readable(self, board):
        revision=self.display_revision(board)
        with self.connect() as db:
            row=db.execute('SELECT document FROM revisions WHERE board_id=? AND revision=?',(board,revision)).fetchone()
            doc=json.loads(row[0])
            doc['manifest']['annotations']=self._notes(db,board)
            return doc

    def _notes(self, db, board):
        row = db.execute('SELECT payload FROM annotations WHERE board_id=?', (board,)).fetchone()
        return json.loads(row[0]) if row else []

    def get(self, board_id, hydrate=True):
        doc = super().get(board_id, hydrate=False)
        with self.connect() as db:
            doc['manifest']['annotations'] = self._notes(db, board_id)
        return self.compatible(doc) if hydrate else doc

    def _save_notes(self, db, doc, notes):
        previous = {n['id']: n for n in self._notes(db, doc['id'])}
        for note in notes:
            if note['id'] in previous:
                note['context'] = previous[note['id']].get('context', {})
            else:
                note['context'] = {'designRevision': doc['revision'], 'dataVersions': doc['snapshot'].get('datasetRefs', {}), 'filters': doc['manifest']['filters']}
        raw = json.dumps(notes, ensure_ascii=False)
        if notes != list(previous.values()):
            db.execute('INSERT OR REPLACE INTO annotations VALUES(?,?)', (doc['id'], raw))
            db.execute('INSERT INTO annotation_events VALUES(?,?,?,?)', (doc['id'], utcnow(), doc['revision'], raw))

    def _files(self, board):
        """Portable readable mirrors; SQLite is the transactional project index."""
        folder = self.root / board
        with self.connect() as db:
            row = db.execute('SELECT document FROM boards WHERE id=?', (board,)).fetchone()
            write_json(folder / 'draft.json', json.loads(row[0]))
            write_json(folder / 'annotations.json', self._notes(db, board))
            events = [dict(r) for r in db.execute('SELECT * FROM annotation_events WHERE board_id=?', (board,))]
            write_json(folder / 'annotation-history.json', events)
            revisions = list(db.execute('SELECT * FROM revisions WHERE board_id=?', (board,)))
            write_json(folder / 'history.json', [dict(r) for r in db.execute('SELECT r.revision,r.created_at,r.action,m.name,m.published FROM revisions r LEFT JOIN checkpoint_meta m ON r.board_id=m.board_id AND r.revision=m.revision WHERE r.board_id=? ORDER BY r.revision DESC',(board,))])
            keep = set()
            for revision in revisions:
                path = folder / 'checkpoints' / f'{revision["revision"]}.json'
                keep.add(path.name)
                write_json(path, json.loads(revision['document']))
            for path in (folder / 'checkpoints').glob('*.json'):
                if path.name not in keep:
                    path.unlink()

    def create(self, board_id, title, document=None):
        doc = super().create(board_id, title, document)
        with self.connect() as db:
            self._save_notes(db, doc, copy.deepcopy(doc['manifest'].get('annotations', [])))
        self._files(board_id)
        return self.get(board_id)

    def mutate(self, board_id, expected_revision, operations=None, restore_revision=None, use_current_data=False):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT document,revision FROM boards WHERE id=?', (board_id,)).fetchone()
            require(row is not None, 'Dashboard not found', 'NOT_FOUND')
            require(row['revision'] == expected_revision, 'Reload before editing', 'REVISION_CONFLICT')
            current = json.loads(row['document'])
            current['manifest']['annotations'] = self._notes(db, board_id)
            if restore_revision is not None:
                saved = db.execute('SELECT document FROM revisions WHERE board_id=? AND revision=?', (board_id, restore_revision)).fetchone()
                require(saved is not None, 'Checkpoint not found')
                doc = json.loads(saved[0])
                doc['manifest']['annotations'] = copy.deepcopy(current['manifest']['annotations'])
                if use_current_data:
                    doc['snapshot'] = copy.deepcopy(current['snapshot'])
            else:
                doc = apply_operations(current, operations)
                if not any(op['op'] == 'set_annotations' for op in operations):
                    doc['manifest']['annotations'] = copy.deepcopy(current['manifest']['annotations'])
            doc['revision'] = expected_revision
            doc = self.compact(doc)
            if doc == current:
                return self.compatible(current)
            doc['revision'] += 1
            self._save_notes(db, doc, doc['manifest'].get('annotations', []))
            stored = copy.deepcopy(doc)
            stored['manifest'].pop('annotations', None)
            db.execute('UPDATE boards SET revision=?,document=? WHERE id=?', (doc['revision'], json_bytes(stored).decode(), board_id))
            if restore_revision is not None:
                db.execute('INSERT OR REPLACE INTO revisions VALUES(?,?,?,?,?)', (board_id, doc['revision'], utcnow(), f'restore:{restore_revision}', json_bytes(stored).decode()))
        self._files(board_id)
        return self.get(board_id)

    def begin(self, board, expected):
        require(self.revision(board) == expected, 'Reload before editing', 'REVISION_CONFLICT')
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO batches VALUES(?,?,?)', (board, uuid.uuid4().hex, expected))
            return dict(db.execute('SELECT * FROM batches WHERE board_id=?', (board,)).fetchone())

    def checkpoint(self, board, expected, name='', published=False, batch_id=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM boards WHERE id=?', (board,)).fetchone()
            require(row is not None and row['revision'] == expected, 'Reload before checkpoint', 'REVISION_CONFLICT')
            batch = db.execute('SELECT * FROM batches WHERE board_id=?', (board,)).fetchone()
            if batch_id:
                require(batch is not None and batch['batch_id'] == batch_id, 'Unknown edit batch')
            db.execute('INSERT OR IGNORE INTO revisions VALUES(?,?,?,?,?)', (board, expected, utcnow(), 'checkpoint', row['document']))
            if name or published:
                db.execute('INSERT OR REPLACE INTO checkpoint_meta VALUES(?,?,?,?)', (board, expected, name, int(published)))
            db.execute('DELETE FROM batches WHERE board_id=?', (board,))
            obsolete = list(db.execute('SELECT r.revision FROM revisions r LEFT JOIN checkpoint_meta m ON r.board_id=m.board_id AND r.revision=m.revision WHERE r.board_id=? AND coalesce(m.name,\'\')=\'\' AND coalesce(m.published,0)=0 ORDER BY r.revision DESC LIMIT -1 OFFSET ?', (board, self.config['history']['keepCheckpoints'])))
            db.executemany('DELETE FROM revisions WHERE board_id=? AND revision=?', [(board, r[0]) for r in obsolete])
        self._files(board)
        return {'dashboardId': board, 'revision': expected, 'name': name, 'published': published}

    def history(self, board_id, offset=0, limit=50):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT r.revision,r.created_at,r.action,m.name,coalesce(m.published,0) AS published FROM revisions r LEFT JOIN checkpoint_meta m ON r.board_id=m.board_id AND r.revision=m.revision WHERE r.board_id=? ORDER BY r.revision DESC LIMIT ? OFFSET ?', (board_id, limit, offset))]

    def label_checkpoint(self, board, expected, revision, name, published=False):
        require(bool(name.strip()) or published, 'A name or published marker is required')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT revision FROM boards WHERE id=?',(board,)).fetchone()
            require(current is not None and current[0]==expected, 'Reload before labeling', 'REVISION_CONFLICT')
            require(db.execute('SELECT 1 FROM revisions WHERE board_id=? AND revision=?',(board,revision)).fetchone() is not None, 'Checkpoint not found')
            db.execute('INSERT OR REPLACE INTO checkpoint_meta VALUES(?,?,?,?)',(board,revision,name,int(published)))
        self._files(board)
        return {'revision':revision,'name':name,'published':published}

    def diff(self, board, first, second):
        import difflib
        with self.connect() as db:
            documents=[]
            for revision in (first, second):
                row=db.execute('SELECT document FROM revisions WHERE board_id=? AND revision=?', (board, revision)).fetchone()
                if row is None:
                    row=db.execute('SELECT document FROM boards WHERE id=? AND revision=?', (board, revision)).fetchone()
                require(row is not None, 'Checkpoint not found')
                documents.append(json.dumps(json.loads(row[0]), ensure_ascii=False, sort_keys=True, indent=2).splitlines())
        return {'diff': '\n'.join(difflib.unified_diff(*documents, fromfile=str(first), tofile=str(second)))}
