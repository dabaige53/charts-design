"""Explicit read-only SQLite execution against operator-configured aliases only."""
from __future__ import annotations
import datetime as dt
import json
import sqlite3
import time
import uuid
from pathlib import Path
from .model import DashboardError, inferred_fields, require, utcnow

MAX_QUERY_ROWS = 10000
SAFE_FUNCTIONS = frozenset('abs avg coalesce count date datetime dense_rank first_value hex ifnull instr julianday lag last_value lead length like likelihood lower ltrim max min nullif nth_value ntile percent_rank printf rank replace round row_number rtrim strftime substr substring sum time total trim typeof unicode unixepoch upper'.split())

class QueryRunner:
    def __init__(self, sources_file=None):
        self.sources = {}
        if sources_file:
            config = json.loads(Path(sources_file).read_text())
            require(isinstance(config, dict), 'Source configuration must be an object')
            for alias, source in config.items():
                require(source.get('engine') == 'sqlite', 'Only SQLite is currently executable; other engines can supply reviewed snapshots')
                path = Path(source['path']).expanduser().resolve(strict=True)
                require(path.is_file(), 'SQLite source must be an existing file')
                self.sources[alias] = path

    def execute(self, alias, sql, params=None, timeout=5):
        require(alias in self.sources, 'Unknown source alias; configure it on the server, not in the tool call', 'SOURCE_NOT_ALLOWED')
        require(isinstance(sql, str) and 0 < len(sql) < 100000, 'SQL must contain 1-99999 characters')
        require(params is None or isinstance(params, (dict, list)), 'Parameters must be an object or array')
        start = time.monotonic()
        allowed_actions = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE}
        def authorize(action, arg1, arg2, database, trigger):
            if action == sqlite3.SQLITE_FUNCTION:
                return sqlite3.SQLITE_OK if (arg2 or '').lower() in SAFE_FUNCTIONS else sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK if action in allowed_actions else sqlite3.SQLITE_DENY
        connection = sqlite3.connect(self.sources[alias].as_uri() + '?mode=ro', uri=True, timeout=timeout)
        try:
            connection.execute('PRAGMA query_only=ON')
            connection.enable_load_extension(False)
            connection.set_authorizer(authorize)
            connection.set_progress_handler(lambda: int(time.monotonic() - start > timeout), 1000)
            cursor = connection.execute(sql, params or ())
            require(cursor.description is not None, 'Only queries returning rows are allowed')
            columns = [c[0] for c in cursor.description]
            require(len(set(columns)) == len(columns), 'Duplicate SQL column names; add unique aliases')
            tuples = cursor.fetchmany(MAX_QUERY_ROWS + 1)
            require(len(tuples) <= MAX_QUERY_ROWS, f'Query exceeds {MAX_QUERY_ROWS} rows. Aggregate or narrow the query; rows are not silently truncated.')
            rows = [dict(zip(columns, row)) for row in tuples]
            require(all(not isinstance(v, bytes) for row in rows for v in row.values()), 'Binary columns cannot be rendered; select displayable fields')
        except sqlite3.Error as exc:
            raise DashboardError('QUERY_REJECTED', str(exc)) from exc
        finally:
            connection.close()
        fields = inferred_fields(rows) if rows else {c: {'type': 'string', 'label': c} for c in columns}
        execution = {'kind': 'query', 'verification': 'runtime-executed',
                     'query': {'id': uuid.uuid4().hex, 'engine': 'sqlite', 'connection': alias,
                               'sql': sql, 'parameters': params or {}, 'executedAt': utcnow(),
                               'durationMs': round((time.monotonic() - start) * 1000), 'rowCount': len(rows)}}
        return rows, fields, execution
