"""Bounded MCP responses and metadata-only transport diagnostics."""
import base64
import json
import sqlite3
import time
import uuid
from .model import DashboardError

class ResultTransport:
    def __init__(self, root):
        self.cache_path = root / 'transport-results.sqlite3'
        with sqlite3.connect(self.cache_path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS results (request_id TEXT PRIMARY KEY, expires REAL, encoded TEXT)")
        self.path = root / 'transport-diagnostics.sqlite3'
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at REAL, request_id TEXT, tool TEXT, stage TEXT, code TEXT, bytes INTEGER)')

            columns = {row[1] for row in db.execute('PRAGMA table_info(events)')}
            for name, kind in [('dashboard_id','TEXT'), ('duration_ms','REAL'), ('revision','INTEGER')]:
                if name not in columns:
                    db.execute(f'ALTER TABLE events ADD COLUMN {name} {kind}')

    def log(self, request_id, tool, stage, code='', size=0, dashboard_id=None, duration_ms=None, revision=None):
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO events(at,request_id,tool,stage,code,bytes,dashboard_id,duration_ms,revision) VALUES(?,?,?,?,?,?,?,?,?)', (time.time(), request_id, tool, stage, code, size, dashboard_id, duration_ms, revision))
            db.execute('DELETE FROM events WHERE id <= (SELECT coalesce(max(id),0)-2000 FROM events)')

    def pack(self, result, tool):
        request_id = result.get('requestId') or uuid.uuid4().hex
        board = result.get('dashboardId') or result.get('id') or result.get('document', {}).get('id')
        raw = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
        self.log(request_id, tool, 'serialized', size=len(raw), dashboard_id=board)
        if len(raw) <= 48000:
            return result
        encoded = base64.b64encode(raw).decode('ascii')
        chunks = [encoded[i:i+24000] for i in range(0, len(encoded), 24000)]
        with sqlite3.connect(self.cache_path) as db:
            db.execute("DELETE FROM results WHERE expires < ?", (time.time(),))
            db.execute("INSERT INTO results VALUES(?,?,?)", (request_id, time.time() + 86400, encoded))
        self.log(request_id, tool, 'chunked', size=len(raw), dashboard_id=board)
        return {'transport': {'encoding': 'base64-json-v1', 'requestId': request_id, 'chunks': len(chunks), 'bytes': len(raw)}}

    def chunk(self, args):
        token, index = args.get('requestId'), args.get('index')
        if not isinstance(token, str) or not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise DashboardError('INVALID_CHUNK', 'Invalid response chunk index or request ID')
        with sqlite3.connect(self.cache_path) as db:
            row = db.execute('SELECT length(encoded), substr(encoded, ?, 24000) FROM results WHERE request_id=? AND expires>=?', (index * 24000 + 1, token, time.time())).fetchone()
        if row is None:
            self.log(token, 'runtime_result_chunk', 'read', 'RESULT_EXPIRED')
            raise DashboardError('RESULT_EXPIRED', 'Preview response expired; reload the dashboard.')
        if index * 24000 >= row[0]:
            self.log(token, 'runtime_result_chunk', 'read', 'INVALID_CHUNK')
            raise DashboardError('INVALID_CHUNK', 'Invalid response chunk index')
        if index == 0 or (index + 1) * 24000 >= row[0]:
            self.log(token, 'runtime_result_chunk', 'read_start' if index == 0 else 'read_complete', size=len(row[1]))
        return {'requestId': token, 'index': index, 'data': row[1]}

    def diagnostics(self, args):
        limit = max(1, min(100, int(args.get('limit', 30))))
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            clauses, values = [], []
            for field, column in [('requestId','request_id'),('dashboardId','dashboard_id'),('stage','stage'),('code','code')]:
                if args.get(field):
                    clauses.append(column+'=?')
                    values.append(args[field])
            where = ' AND '.join(clauses) or '1=1'
            rows = db.execute('SELECT * FROM events WHERE '+where+' ORDER BY id DESC LIMIT ?', (*values, limit)).fetchall()
        return {'events': [dict(row) for row in rows]}
