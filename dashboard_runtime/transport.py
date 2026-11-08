"""Bounded MCP responses and metadata-only transport diagnostics."""
import base64
import json
import sqlite3
import threading
import time
import uuid
from .model import DashboardError

INLINE_LIMIT = 48000
CHUNK_SIZE = 24000
EVENT_RETENTION = 2000
# Pruning is an indexed range delete; running it every insert only adds latency.
PRUNE_EVERY = 50


class ResultTransport:
    """One long-lived connection per database, serialized by a lock.

    Opening a connection and committing a rollback journal per diagnostic event
    cost milliseconds on every tool call. WAL with NORMAL synchronisation keeps
    commits visible to other worker processes immediately while avoiding a
    full fsync for metadata that is only used for diagnosis.
    """

    def __init__(self, root):
        self.cache_path = root / 'transport-results.sqlite3'
        self.path = root / 'transport-diagnostics.sqlite3'
        self._lock = threading.Lock()
        self._inserts = 0
        self._results = self._open(self.cache_path)
        self._results.execute("CREATE TABLE IF NOT EXISTS results (request_id TEXT PRIMARY KEY, expires REAL, encoded TEXT)")
        self._events = self._open(self.path)
        self._events.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at REAL, request_id TEXT, tool TEXT, stage TEXT, code TEXT, bytes INTEGER)')
        columns = {row[1] for row in self._events.execute('PRAGMA table_info(events)')}
        for name, kind in [('dashboard_id', 'TEXT'), ('duration_ms', 'REAL'), ('revision', 'INTEGER'), ('backend_build_id', 'TEXT'), ('cache_hits', 'INTEGER')]:
            if name not in columns:
                self._events.execute(f'ALTER TABLE events ADD COLUMN {name} {kind}')

    @staticmethod
    def _open(path):
        # Autocommit mode: every statement is its own short transaction.
        db = sqlite3.connect(str(path), timeout=10, isolation_level=None, check_same_thread=False)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=NORMAL')
        except sqlite3.OperationalError:
            pass  # Another process holds the database; defaults remain correct.
        return db

    def log(self, request_id, tool, stage, code='', size=0, dashboard_id=None, duration_ms=None, revision=None, cache_hits=None):
        self.log_many([(request_id, tool, stage, code, size, dashboard_id, duration_ms, revision, cache_hits)])

    def log_many(self, events):
        """Write several metadata events in one transaction (for example Doctor checks)."""
        from .build import BACKEND_BUILD_ID
        if not events:
            return
        now = time.time()
        rows = [(now, request_id, tool, stage, code or '', size or 0, dashboard_id, duration_ms, revision, BACKEND_BUILD_ID, cache_hits)
                for request_id, tool, stage, code, size, dashboard_id, duration_ms, revision, cache_hits in events]
        with self._lock:
            db = self._events
            db.execute('BEGIN')
            try:
                db.executemany('INSERT INTO events(at,request_id,tool,stage,code,bytes,dashboard_id,duration_ms,revision,backend_build_id,cache_hits) VALUES(?,?,?,?,?,?,?,?,?,?,?)', rows)
                self._inserts += len(rows)
                if self._inserts >= PRUNE_EVERY:
                    self._inserts = 0
                    db.execute('DELETE FROM events WHERE id <= (SELECT coalesce(max(id),0)-? FROM events)', (EVENT_RETENTION,))
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise

    def encode(self, result, tool):
        """Return the bounded payload and its exact JSON text.

        Hosts receive the same compact text that was measured, so a result is
        serialized once instead of once for sizing and again for text fallback.
        """
        request_id = result.get('requestId') or uuid.uuid4().hex
        board = result.get('dashboardId') or result.get('id') or result.get('document', {}).get('id')
        started = time.perf_counter()
        text = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        raw = text.encode()
        self.log(request_id, tool, 'serialized', size=len(raw), dashboard_id=board, duration_ms=(time.perf_counter()-started)*1000)
        if len(raw) <= INLINE_LIMIT:
            return result, text
        encoded = base64.b64encode(raw).decode('ascii')
        chunks = (len(encoded) + CHUNK_SIZE - 1) // CHUNK_SIZE
        with self._lock:
            self._results.execute("DELETE FROM results WHERE expires < ?", (time.time(),))
            self._results.execute("INSERT OR REPLACE INTO results VALUES(?,?,?)", (request_id, time.time() + 86400, encoded))
        self.log(request_id, tool, 'chunked', size=len(raw), dashboard_id=board)
        packed = {'transport': {'encoding': 'base64-json-v1', 'requestId': request_id, 'chunks': chunks, 'bytes': len(raw)}}
        return packed, None

    def pack(self, result, tool):
        return self.encode(result, tool)[0]

    def chunk(self, args):
        token, index = args.get('requestId'), args.get('index')
        if not isinstance(token, str) or not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise DashboardError('INVALID_CHUNK', 'Invalid response chunk index or request ID')
        with self._lock:
            row = self._results.execute('SELECT length(encoded), substr(encoded, ?, ?) FROM results WHERE request_id=? AND expires>=?', (index * CHUNK_SIZE + 1, CHUNK_SIZE, token, time.time())).fetchone()
        if row is None:
            self.log(token, 'runtime_result_chunk', 'read', 'RESULT_EXPIRED')
            raise DashboardError('RESULT_EXPIRED', 'Preview response expired; reload the dashboard.')
        if index * CHUNK_SIZE >= row[0]:
            self.log(token, 'runtime_result_chunk', 'read', 'INVALID_CHUNK')
            raise DashboardError('INVALID_CHUNK', 'Invalid response chunk index')
        if index == 0 or (index + 1) * CHUNK_SIZE >= row[0]:
            self.log(token, 'runtime_result_chunk', 'read_start' if index == 0 else 'read_complete', size=len(row[1]))
        return {'requestId': token, 'index': index, 'data': row[1]}

    def diagnostics(self, args):
        limit = max(1, min(100, int(args.get('limit', 30))))
        clauses, values = [], []
        for field, column in [('requestId', 'request_id'), ('dashboardId', 'dashboard_id'), ('stage', 'stage'), ('code', 'code')]:
            if args.get(field):
                clauses.append(column+'=?')
                values.append(args[field])
        where = ' AND '.join(clauses) or '1=1'
        with self._lock:
            cursor = self._events.execute('SELECT * FROM events WHERE '+where+' ORDER BY id DESC LIMIT ?', (*values, limit))
            names = [item[0] for item in cursor.description]
            rows = cursor.fetchall()
        return {'events': [dict(zip(names, row)) for row in rows]}
