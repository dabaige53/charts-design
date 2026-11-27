"""Bounded read-only SQL against operator-configured source aliases."""
from __future__ import annotations
import json
import math
import os
import re
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import date, time as time_of_day
from decimal import Decimal
from pathlib import Path
from threading import Timer
from .local_data import LocalData
from .model import DashboardError, SQL_SOURCE_ENGINES, inferred_fields, require, utcnow

MAX_QUERY_ROWS = 10000
SAFE_FUNCTIONS = frozenset('abs avg coalesce count date datetime dense_rank first_value hex ifnull instr julianday lag last_value lead length like likelihood lower ltrim max min nullif nth_value ntile percent_rank printf rank replace round row_number rtrim strftime substr substring sum time total trim typeof unicode unixepoch upper'.split())

class QueryRunner:
    def __init__(self, sources_file=None):
        self.sources: dict[str, tuple[str, str]] = {}
        if sources_file:
            config = json.loads(Path(sources_file).read_text())
            require(isinstance(config, dict), 'Source configuration must be an object')
            for alias, source in config.items():
                require(isinstance(source, dict), 'Source configuration must be an object', 'INVALID_CONFIG')
                engine = source.get('engine')
                require(isinstance(engine, str) and engine in SQL_SOURCE_ENGINES,
                        'Source engine must be sqlite, postgresql, or duckdb', 'INVALID_CONFIG')
                if engine == 'postgresql':
                    target = source.get('dsnEnv')
                    require(isinstance(target, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', target),
                            'PostgreSQL source requires dsnEnv with an environment variable name', 'INVALID_CONFIG')
                else:
                    raw_path = source.get('path')
                    require(isinstance(raw_path, str) and raw_path.strip(),
                            'File-based SQL source requires a path', 'INVALID_CONFIG')
                    path = Path(raw_path).expanduser().resolve(strict=True)
                    require(path.is_file(), 'SQL source must be an existing database file', 'INVALID_CONFIG')
                    target = str(path)
                self.sources[alias] = (engine, target)

    def _source(self, alias):
        require(isinstance(alias, str) and alias in self.sources, 'Unknown source alias; configure it on the server, not in the tool call', 'SOURCE_NOT_ALLOWED')
        return self.sources[alias]

    def sqlite_path(self, alias):
        engine, path = self._source(alias)
        require(engine == 'sqlite', 'dataset_attach requires a SQLite source. Use query_execute for other engines.',
                'SOURCE_NOT_ALLOWED')
        return Path(path)

    def execute(self, alias, sql, params=None, timeout=5, *, fields=None, expected_engine=None):
        engine, target = self._source(alias)
        require(expected_engine is None or engine == expected_engine,
                'Source engine changed; register the SQL again for the configured engine', 'SOURCE_ENGINE_CHANGED')
        require(isinstance(sql, str) and 0 < len(sql) < 100000, 'SQL must contain 1-99999 characters')
        require(params is None or isinstance(params, (dict, list)), 'Parameters must be an object or array')
        start = time.monotonic()
        if engine == 'sqlite':
            columns, records = self._sqlite(Path(target), sql, params, timeout, start)
        elif engine == 'postgresql':
            columns, records = self._postgresql(target, sql, params, timeout)
        else:
            columns, records = self._duckdb(target, sql, params, timeout)
        require(len(set(columns)) == len(columns), 'Duplicate SQL column names; add unique aliases')
        require(len(records) <= MAX_QUERY_ROWS, f'Query exceeds {MAX_QUERY_ROWS} rows. Aggregate or narrow the query; rows are not silently truncated.')
        rows = [dict(zip(columns, map(self._scalar, record))) for record in records]
        if fields is not None:
            require(set(columns) == set(fields), 'SQL result columns must match the declared fields', 'QUERY_SCHEMA_CHANGED')
            for field, info in fields.items():
                if info['type'] == 'boolean':
                    for row in rows:
                        if type(row[field]) is int and row[field] in (0, 1):
                            row[field] = bool(row[field])
        else:
            fields = inferred_fields(rows) if rows else {c: {'type': 'string', 'label': c} for c in columns}
            for column, values in zip(columns, zip(*records)):
                present = [value for value in values if value is not None]
                if present and all(isinstance(value, date) for value in present):
                    fields[column]['type'] = 'date'
        execution = {'kind': 'query', 'verification': 'runtime-executed',
                     'query': {'id': uuid.uuid4().hex, 'engine': engine, 'connection': alias,
                               'sql': sql, 'parameters': params or {}, 'executedAt': utcnow(),
                               'durationMs': round((time.monotonic() - start) * 1000), 'rowCount': len(rows)}}
        return rows, fields, execution

    @staticmethod
    def _scalar(value):
        if isinstance(value, Decimal):
            value = float(value)
        if isinstance(value, (date, time_of_day)):
            return value.isoformat()
        if isinstance(value, uuid.UUID):
            return str(value)
        require(value is None or type(value) in (str, int, float, bool),
                'SQL result must contain scalar fields; cast unsupported values in the query', 'QUERY_SCHEMA_CHANGED')
        require(type(value) is not float or math.isfinite(value),
                'SQL result contains a non-finite number', 'QUERY_SCHEMA_CHANGED')
        return value

    @staticmethod
    def _read_rows(cursor):
        require(cursor.description is not None, 'Only queries returning rows are allowed')
        return [column[0] for column in cursor.description], cursor.fetchmany(MAX_QUERY_ROWS + 1)

    def _sqlite(self, path, sql, params, timeout, start):
        allowed_actions = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE}
        def authorize(action, arg1, arg2, database, trigger):
            if action == sqlite3.SQLITE_FUNCTION:
                return sqlite3.SQLITE_OK if (arg2 or '').lower() in SAFE_FUNCTIONS else sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK if action in allowed_actions else sqlite3.SQLITE_DENY
        try:
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=timeout)) as connection:
                connection.execute('PRAGMA query_only=ON')
                connection.enable_load_extension(False)
                connection.set_authorizer(authorize)
                connection.set_progress_handler(lambda: int(time.monotonic() - start > timeout), 1000)
                return self._read_rows(connection.execute(sql, params or ()))
        except (sqlite3.Error, sqlite3.Warning) as exc:
            # Python <= 3.11 raises sqlite3.Warning (not an sqlite3.Error) for
            # multiple statements; reject it the same way on every version.
            raise DashboardError('QUERY_REJECTED', str(exc)) from exc

    def _postgresql(self, dsn_env, sql, params, timeout):
        import psycopg

        dsn = os.environ.get(dsn_env)
        require(dsn, f'Configure PostgreSQL connection in the {dsn_env} environment variable', 'INVALID_CONFIG')
        try:
            connection = psycopg.connect(dsn or '', connect_timeout=max(2, math.ceil(timeout)))
        except psycopg.Error:
            raise DashboardError('SOURCE_UNAVAILABLE', 'Could not connect to the configured PostgreSQL source', 503) from None
        with closing(connection):
            try:
                connection.read_only = True
                connection.execute("SELECT set_config('statement_timeout', %s, true)", (f'{round(timeout * 1000)}ms',))
                # DECLARE CURSOR accepts one SELECT and fetches at most the requested rows from the server.
                with connection.cursor(name='charts_query') as cursor:
                    cursor.execute(sql, params)
                    return self._read_rows(cursor)
            except psycopg.errors.QueryCanceled:
                raise DashboardError('QUERY_TIMEOUT', 'PostgreSQL query timed out') from None
            except psycopg.Error as error:
                raise DashboardError('QUERY_REJECTED',
                                     f'PostgreSQL query failed ({error.sqlstate or type(error).__name__})') from None

    def _duckdb(self, path, sql, params, timeout):
        import duckdb

        try:
            with closing(duckdb.connect(path, read_only=True, config={
                'enable_external_access': 'false',
                'autoinstall_known_extensions': 'false',
                'autoload_known_extensions': 'false',
                'lock_configuration': 'true',
                'python_enable_replacements': 'false',
                'temp_directory': '',
            })) as connection:
                statements = connection.extract_statements(sql)
                require(len(statements) == 1 and statements[0].type == duckdb.StatementType.SELECT,
                        'DuckDB source requires a single SELECT query', 'QUERY_REJECTED')
                timer = Timer(timeout, connection.interrupt)
                timer.start()
                try:
                    return self._read_rows(connection.execute(statements[0], params))
                finally:
                    timer.cancel()
                    timer.join()
        except duckdb.InterruptException:
            raise DashboardError('QUERY_TIMEOUT', 'DuckDB query timed out') from None
        except duckdb.Error as error:
            raise DashboardError('QUERY_REJECTED', str(error)) from error


class LiveQueryRequest:
    """Load each requested dataset once into request-scoped SQLite memory."""

    def __init__(self, queries, manifest):
        self.queries = queries
        self.manifest = manifest
        self._data: LocalData | None = None
        self.refs = {}

    @property
    def data(self) -> LocalData:
        if self._data is None:
            self._data = LocalData(None)
        return self._data

    def reference(self, dataset_id):
        if dataset_id not in self.refs:
            meta = self.manifest['datasets'][dataset_id]
            query = self.manifest['sources'][meta['sourceId']]['query']
            rows, fields, _ = self.queries.execute(query['connection'], query['sql'], query.get('parameters'),
                                                  fields=meta['fields'], expected_engine=query['engine'])
            self.add(dataset_id, rows, fields)
        return self.refs[dataset_id]

    def add(self, dataset_id, rows, fields):
        self.refs[dataset_id] = self.data.import_rows(rows, fields)

    def close(self):
        if self._data is not None:
            self._data.close()
