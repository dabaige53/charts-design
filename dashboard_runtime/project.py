"""Project-owned assets, draft revisions and explicit checkpoints."""
from pathlib import Path
from typing import cast
from contextlib import contextmanager
import copy
import json
import tempfile
import uuid
from .store import Store
from .local_data import LocalData
from .file_lock import exclusive_file_lock
from .model import DashboardError, apply_operations, identifier, json_bytes, require, utcnow, validate_annotations

DEFAULTS = {'history': {'keepCheckpoints': 100}, 'loading': {'debounceMs': 150, 'maxConcurrent': 4, 'pageSize': 50}}

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.' + path.name + '.', suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            json.dump(value, output, ensure_ascii=False, indent=2)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

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
                CREATE INDEX IF NOT EXISTS annotation_events_board ON annotation_events(board_id);
            ''')

    def compatible(self, document):
        return document

    def display_revision(self, board):
        with self.connect() as db:
            return db.execute('SELECT max(revision) FROM revisions WHERE board_id=?',(board,)).fetchone()[0]

    def readable(self, board):
        with self.connect() as db:
            db.execute('BEGIN')
            row=db.execute('SELECT document FROM revisions WHERE board_id=? ORDER BY revision DESC LIMIT 1',(board,)).fetchone()
            require(row is not None, '暂无已保存版本', 'NO_SAVED_VERSION')
            doc=json.loads(row[0])
            doc['manifest']['annotations']=self._notes(db,board)
            return doc

    def _notes(self, db, board):
        row = db.execute('SELECT payload FROM annotations WHERE board_id=?', (board,)).fetchone()
        return json.loads(row[0]) if row else []

    def _annotation_state(self, db, board, include_targets):
        row = db.execute("""SELECT revision, json_extract(document, '$.manifest.title') AS title,
            json_extract(document, '$.manifest.viewMode') AS view_mode,
            json_extract(document, '$.manifest.filters') AS filters,
            json_extract(document, '$.snapshot.datasetRefs') AS refs
            FROM boards WHERE id=?""", (board,)).fetchone()
        if row is None:
            raise DashboardError('NOT_FOUND', 'Dashboard not found', 404)
        components = None
        if include_targets:
            components = {item[0]: {'title': item[1] or '', 'kind': item[2]} for item in db.execute("""
                SELECT c.key, json_extract(c.value, '$.title'), json_extract(c.value, '$.kind')
                FROM boards, json_each(document, '$.manifest.components') AS c WHERE boards.id=?
                """, (board,))}
        return {'id': board, 'revision': row['revision'], 'title': row['title'], 'annotations': self._notes(db, board),
                'components': components, 'viewMode': row['view_mode'], 'filters': json.loads(row['filters'] or '[]'),
                'datasetRefs': json.loads(row['refs'] or '{}')}

    def annotation_state(self, board, include_targets=False):
        identifier(board)
        with self.connect() as db:
            db.execute('BEGIN')
            return self._annotation_state(db, board, include_targets)

    def update_annotations(self, board, expected, previous, notes):
        identifier(board)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self._annotation_state(db, board, True)
            if state['revision'] != expected:
                raise DashboardError('REVISION_CONFLICT', '页面已更新，请重新打开批注。当前输入已保留。', 409)
            if state['annotations'] != previous:
                raise DashboardError('ANNOTATION_CONFLICT', '批注已被其他页面更新，请重新打开批注。当前输入已保留。', 409)
            validate_annotations(notes, state['components'])
            doc = {'id': board, 'revision': expected, 'manifest': {'filters': state['filters']},
                   'snapshot': {'datasetRefs': state['datasetRefs']}}
            self._save_notes(db, doc, notes, previous)
        # The previous request may have committed before a mirror write failed.
        # A successful no-op retry repairs those files without adding an event.
        self._files(board, draft=False, history=False, checkpoints=())
        return {'dashboardId': board, 'revision': expected, 'annotations': notes}

    def append_annotation(self, board, note):
        identifier(board)
        validate_annotations([note])
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self._annotation_state(db, board, bool(note.get('componentId') and 'anchor' not in note))
            previous = state['annotations']
            existing = next((item for item in previous if item['id'] == note['id']), None)
            if existing is None:
                validate_annotations([*previous, note], state['components'])
                doc = {'id': board, 'revision': state['revision'], 'manifest': {'filters': state['filters']},
                       'snapshot': {'datasetRefs': state['datasetRefs']}}
                self._save_notes(db, doc, [*previous, note], previous)
        self._files(board, draft=False, history=False, checkpoints=())
        return {'dashboardId': board, 'revision': state['revision'], 'annotation': existing or note}

    def get(self, board_id, hydrate=True):
        doc = super().get(board_id, hydrate=False)
        with self.connect() as db:
            doc['manifest']['annotations'] = self._notes(db, board_id)
        return self.compatible(doc) if hydrate else doc

    def _save_notes(self, db, doc, notes, previous_notes=None):
        previous = {n['id']: n for n in (self._notes(db, doc['id']) if previous_notes is None else previous_notes)}
        for note in notes:
            if note['id'] in previous:
                note['context'] = previous[note['id']].get('context', {})
            else:
                note['context'] = {'designRevision': doc['revision'], 'dataVersions': doc['snapshot'].get('datasetRefs', {}), 'filters': doc['manifest']['filters']}
        raw = json.dumps(notes, ensure_ascii=False)
        if notes != list(previous.values()):
            db.execute('INSERT OR REPLACE INTO annotations VALUES(?,?)', (doc['id'], raw))
            db.execute('INSERT INTO annotation_events VALUES(?,?,?,?)', (doc['id'], utcnow(), doc['revision'], raw))
            return True
        return False

    def _annotation_files(self, db, board):
        folder = self.root / board
        write_json(folder / 'annotations.json', self._notes(db, board))
        events = [dict(r) for r in db.execute('SELECT * FROM annotation_events WHERE board_id=? ORDER BY rowid', (board,))]
        write_json(folder / 'annotation-history.json', events)

    @contextmanager
    def _mirror_db(self, board):
        """Serialize mirror readers/writers without holding SQLite's write lock."""
        folder = self.root / board
        with exclusive_file_lock(folder / '.mirror.lock'):
            with self.connect() as db:
                db.execute('BEGIN')
                yield db

    def _files(self, board, rewrite=False, *, draft=True, annotations=True, history=True, checkpoints=None):
        """Portable readable mirrors; SQLite is the transactional project index."""
        folder = self.root / board
        with self._mirror_db(board) as db:
            if draft:
                row = db.execute('SELECT document FROM boards WHERE id=?', (board,)).fetchone()
                write_json(folder / 'draft.json', json.loads(row[0]))
            if annotations:
                self._annotation_files(db, board)
            if history:
                write_json(folder / 'history.json', [dict(r) for r in db.execute('SELECT r.revision,r.created_at,r.action,m.name,m.published FROM revisions r LEFT JOIN checkpoint_meta m ON r.board_id=m.board_id AND r.revision=m.revision WHERE r.board_id=? ORDER BY r.revision DESC',(board,))])
            directory = folder / 'checkpoints'
            # Normal writes know which checkpoint changed. Only creation and
            # migration need to reconcile the entire directory.
            if checkpoints is not None:
                for revision in checkpoints:
                    path = directory / f'{revision}.json'
                    row = db.execute('SELECT document FROM revisions WHERE board_id=? AND revision=?', (board, revision)).fetchone()
                    if row is None:
                        path.unlink(missing_ok=True)
                    elif not path.exists():
                        write_json(path, json.loads(row[0]))
                return
            existing = {path.name for path in directory.glob('*.json')} if directory.exists() else set()
            if rewrite:
                for name in existing:
                    (directory / name).unlink(missing_ok=True)
                existing = set()
            keep = set()
            for (revision,) in db.execute('SELECT revision FROM revisions WHERE board_id=?', (board,)):
                name = f'{revision}.json'
                keep.add(name)
                if name not in existing:
                    row = db.execute('SELECT document FROM revisions WHERE board_id=? AND revision=?', (board, revision)).fetchone()
                    write_json(directory / name, json.loads(row[0]))
            for name in existing - keep:
                (directory / name).unlink(missing_ok=True)

    def create(self, board_id, title, document=None):
        doc = super().create(board_id, title, document)
        with self.connect() as db:
            self._save_notes(db, doc, copy.deepcopy(doc['manifest'].get('annotations', [])))
        self._files(board_id)
        return self.get(board_id)

    def mutate(self, board_id, expected_revision, operations=None, restore_revision=None, use_current_data=False, expected_annotations=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT document,revision FROM boards WHERE id=?', (board_id,)).fetchone()
            require(row is not None, 'Dashboard not found', 'NOT_FOUND')
            require(row['revision'] == expected_revision, 'Reload before editing', 'REVISION_CONFLICT')
            current = json.loads(row['document'])
            current['manifest']['annotations'] = self._notes(db, board_id)
            if expected_annotations is not None:
                require(restore_revision is None and operations and all(isinstance(op, dict) and op.get('op') == 'set_annotations' for op in operations),
                        'Independent annotation saves may only replace annotations')
                require(current['manifest']['annotations'] == expected_annotations,
                        '批注已被其他页面更新，请重试以保留最新批注。', 'ANNOTATION_CONFLICT')
            if restore_revision is not None:
                saved = db.execute('SELECT document FROM revisions WHERE board_id=? AND revision=?', (board_id, restore_revision)).fetchone()
                if saved is None and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='releases'").fetchone():
                    saved = db.execute('SELECT document FROM releases WHERE board_id=? AND revision=? ORDER BY id DESC LIMIT 1',
                                       (board_id, restore_revision)).fetchone()
                if saved is None:
                    raise DashboardError('INVALID_DOCUMENT', 'Checkpoint not found')
                doc = json.loads(saved[0])
                doc['manifest']['annotations'] = copy.deepcopy(current['manifest']['annotations'])
                if use_current_data:
                    doc['snapshot'] = copy.deepcopy(current['snapshot'])
            else:
                doc = apply_operations(current, operations)
                if not any(op['op'] == 'set_annotations' for op in cast(list[dict], operations)):
                    doc['manifest']['annotations'] = copy.deepcopy(current['manifest']['annotations'])
            doc['revision'] = expected_revision
            doc = self.compact(doc)
            if doc == current:
                return self.compatible(current)
            if expected_annotations is None:
                doc['revision'] += 1
            notes_changed = self._save_notes(db, doc, doc['manifest'].get('annotations', []), current['manifest']['annotations'])
            stored = copy.deepcopy(doc)
            stored['manifest'].pop('annotations', None)
            if expected_annotations is None:
                db.execute('UPDATE boards SET revision=?,document=? WHERE id=?', (doc['revision'], json_bytes(stored).decode(), board_id))
        self._files(board_id, draft=expected_annotations is None, annotations=notes_changed,
                    history=False, checkpoints=())
        return doc

    def migrate(self, board_id, expected_revision):
        # Migration rewrites stored checkpoints in place; refresh their mirrors.
        result = super().migrate(board_id, expected_revision)
        self._files(board_id, rewrite=True)
        return result

    def begin(self, board, expected):
        require(self.revision(board) == expected, 'Reload before editing', 'REVISION_CONFLICT')
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO batches VALUES(?,?,?)', (board, uuid.uuid4().hex, expected))
            return dict(db.execute('SELECT * FROM batches WHERE board_id=?', (board,)).fetchone())

    def checkpoint(self, board, expected, name='', published=False, batch_id=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM boards WHERE id=?', (board,)).fetchone()
            if row is None or row['revision'] != expected:
                raise DashboardError('REVISION_CONFLICT', 'Reload before checkpoint')
            batch = db.execute('SELECT * FROM batches WHERE board_id=?', (board,)).fetchone()
            if batch_id:
                require(batch is not None and batch['batch_id'] == batch_id, 'Unknown edit batch')
            db.execute('INSERT OR IGNORE INTO revisions VALUES(?,?,?,?,?)', (board, expected, utcnow(), 'checkpoint', row['document']))
            if name or published:
                db.execute('INSERT OR REPLACE INTO checkpoint_meta VALUES(?,?,?,?)', (board, expected, name, int(published)))
            db.execute('DELETE FROM batches WHERE board_id=?', (board,))
        self._files(board, draft=False, annotations=False, checkpoints=(expected,))
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
        self._files(board, draft=False, annotations=False, checkpoints=())
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
        from .semantic_diff import semantic_diff
        return {'diff': '\n'.join(difflib.unified_diff(*documents, fromfile=str(first), tofile=str(second))), 'semanticChanges': semantic_diff(*(json.loads('\n'.join(lines)) for lines in documents))}
