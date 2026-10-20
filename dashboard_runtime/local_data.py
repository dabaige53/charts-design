"""Content-addressed, streaming local SQLite datasets. No network dependency."""
from __future__ import annotations

import csv
from contextlib import contextmanager, closing
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import time

from .model import DashboardError

MAX_RESULT_ROWS = 100_000


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'), sort_keys=True)


def _contains(raw, needle, kind):
    value = bool(raw) if raw is not None and kind == 'boolean' else raw
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = '' if value is None else ('true' if value is True else 'false' if value is False else str(value))
    return needle.lower() in text.lower()


def _search_text(raw, needle, kind):
    if raw is None:
        return needle.lower() in 'null'
    return _contains(raw, needle, kind)


def _sort_number(value):
    if value is None:
        return None
    cleaned = re.sub(r'[^0-9.\-]', '', str(value))
    match = re.match(r'^-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)', cleaned)
    if not match:
        return None
    number = float(match[0])
    return number if math.isfinite(number) else None


class LocalData:
    """Versions are immutable; result bounds raise errors instead of dropping rows."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'data.sqlite3'
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS versions (version TEXT PRIMARY KEY, metadata TEXT NOT NULL)')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path)
        db.create_function('contains_text', 3, _contains, deterministic=True)
        db.create_function('grain', 2, self._grain, deterministic=True)
        db.create_function('search_text', 3, _search_text, deterministic=True)
        db.create_function('sort_number', 1, _sort_number, deterministic=True)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _grain(raw, grain):
        value = raw
        if value is None:
            return None
        match = re.match(r'^(\d{4})-(\d{2})(?:-|$)', str(value))
        if not match or not 1 <= int(match[2]) <= 12:
            raise ValueError('Time grouping requires ISO dates')
        return f'{match[1]}-{match[2]}' if grain == 'month' else f'{match[1]} Q{(int(match[2])-1)//3+1}'

    def import_rows(self, rows, fields):
        if not isinstance(fields, dict) or not fields or not all(isinstance(k, str) for k in fields):
            raise ValueError('fields must be a nonempty field metadata mapping')
        keys = list(fields)
        fields = json.loads(_json(fields))
        fields = {key: fields[key] for key in keys}
        digest = hashlib.sha256(_json(fields).encode())
        if keys != sorted(keys):
            digest.update(b'\x00fieldOrder:')
            digest.update(_json(keys).encode())
        byte_count = count = 0
        has_missing = False
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE staging (' + ','.join(f'c{i}' for i in range(len(keys))) + ', _missing TEXT)')
            insert = 'INSERT INTO staging VALUES (' + ','.join('?' for _ in range(len(keys) + 1)) + ')'
            for row in rows:
                if not isinstance(row, dict) or set(row) - set(keys):
                    raise ValueError('Each row must be a field mapping with no undeclared fields')
                values = [row.get(k) for k in keys]
                for key, value in zip(keys, values):
                    kind = fields[key].get('type')
                    valid = value is None or (kind == 'number' and type(value) in (int, float) and math.isfinite(value) and (type(value) is float or -(2**63) <= value < 2**63)) or (kind == 'boolean' and type(value) is bool) or (kind in ('string', 'date') and isinstance(value, str))
                    if not valid:
                        raise ValueError(f'Invalid scalar value for field: {key}')
                raw = _json([row.get(k) for k in keys]).encode()
                digest.update(len(raw).to_bytes(8, 'big'))
                digest.update(raw)
                missing = [key for key in keys if key not in row]
                mask = _json(missing) if missing else None
                digest.update((mask or '').encode())
                digest.update(b'\x00')
                has_missing = has_missing or bool(missing)
                byte_count += len(raw)
                db.execute(insert, values + [mask])
                count += 1
            version = digest.hexdigest()
            ref = {'version': version, 'rowCount': count, 'fields': fields, 'fieldOrder': keys, 'bytes': byte_count}
            if has_missing:
                ref['hasMissingFields'] = True
            exists = db.execute('SELECT metadata FROM versions WHERE version=?', (version,)).fetchone()
            if exists:
                db.execute('DROP TABLE staging')
                return self._metadata(exists[0])
            db.execute(f'ALTER TABLE staging RENAME TO d_{version}')
            db.execute('INSERT INTO versions VALUES (?,?)', (version, _json(ref)))
            return ref

    def describe(self, version):
        with self._connect() as db:
            return self._version(db, {'version': version})[1]

    @staticmethod
    def _decode(keys, row, fields, missing=None):
        omitted = set(json.loads(missing)) if missing else set()
        return {k: bool(v) if v is not None and fields[k].get('type') == 'boolean' else v for k, v in zip(keys, row) if k not in omitted}

    def import_sqlite(self, path, table, fields=None):
        source = Path(path).resolve(strict=True)
        if not isinstance(table, str) or not table:
            raise ValueError('table must be a table name')
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                raise ValueError('Unknown SQLite table')
            quoted = '"' + table.replace('"', '""') + '"'
            cursor = db.execute('SELECT * FROM ' + quoted)
            keys = [c[0] for c in cursor.description]
            if fields is None:
                types = {r[1]: r[2].upper() for r in db.execute('PRAGMA table_info(' + quoted + ')')}
                fields = {k: {'type': 'number' if any(t in types[k] for t in ('INT', 'REAL', 'FLOA', 'DOUB', 'NUM', 'DEC')) else 'string'} for k in keys}
            def source_rows():
                for values in cursor:
                    row = dict(zip(keys, values))
                    for key, meta in fields.items():
                        if meta.get('type') == 'boolean' and type(row.get(key)) is int and row[key] in (0, 1):
                            row[key] = bool(row[key])
                    yield row
            return self.import_rows(source_rows(), fields)

    def _version(self, db, ref):
        version = ref.get('version') if isinstance(ref, dict) else None
        if not isinstance(version, str) or not re.fullmatch('[0-9a-f]{64}', version):
            raise ValueError('Invalid data version')
        record = db.execute('SELECT metadata FROM versions WHERE version=?', (version,)).fetchone()
        if not record:
            raise ValueError('Unknown data version')
        return 'd_' + version, self._metadata(record[0])

    @staticmethod
    def _metadata(raw):
        metadata = json.loads(raw)
        fields = metadata['fields']
        # Earlier versions stored physical columns in the JSON field order.
        order = metadata.get('fieldOrder', list(fields))
        metadata['fields'] = {key: fields[key] for key in order}
        return metadata

    @staticmethod
    def _column(fields, key):
        if key not in fields:
            raise ValueError(f'Unknown field: {key}')
        return f'c{list(fields).index(key)}'

    def _where(self, fields, filters, search=''):
        clauses, params = [], []
        for item in filters or []:
            col = self._column(fields, item['field'])
            values = item.get('values', [])
            if not values:
                continue
            op = item['op']
            if op == 'in':
                present = [v for v in values if v is not None]
                alternatives = []
                if present:
                    alternatives.append(f'{col} IN (' + ','.join('?' for _ in present) + ')')
                    params.extend(present)
                if None in values:
                    alternatives.append(f'{col} IS NULL AND NOT EXISTS (SELECT 1 FROM json_each(_missing) WHERE value=?)')
                    params.append(item['field'])
                clauses.append(' OR '.join(alternatives))
            elif op == 'contains':
                clauses.append(f'contains_text({col}, ?, ?)')
                params.extend([str(values[0]), fields[item['field']].get('type')])
            elif op == 'range' and len(values) == 2:
                # Native column values retain declared numeric and string types.
                clauses.append(f'{col} IS NOT NULL AND {col} BETWEEN ? AND ?')
                params.extend(values)
            else:
                raise ValueError('Unsupported filter operation or invalid range')
        if not isinstance(search, str):
            raise ValueError('search must be a string')
        if search:
            alternatives = []
            for field, meta in fields.items():
                if field.startswith(('raw', '_')):
                    continue
                alternatives.append(f'(search_text({self._column(fields, field)}, ?, ?) AND NOT EXISTS (SELECT 1 FROM json_each(_missing) WHERE value=?))')
                params.extend([search, meta.get('type'), field])
            clauses.append(' OR '.join(alternatives) if alternatives else '0')
        return (' WHERE ' + ' AND '.join('(' + c + ')' for c in clauses) if clauses else ''), params

    def _indexes(self, db, table, fields, filters, sort=None):
        keys = {item['field'] for item in (filters or []) + (sort or [])}
        for item in sort or []:
            key = item['field']
            raw = 'raw' + key[:1].upper() + key[1:]
            if fields.get(key, {}).get('type') == 'string' and fields.get(raw, {}).get('type') == 'number':
                keys.add(raw)
        for key in keys:
            column = self._column(fields, key)
            db.execute(f'CREATE INDEX IF NOT EXISTS i_{table}_{column} ON {table} ({column})')

    def _selection(self, fields, columns, sort):
        keys = list(fields) if columns is None else list(columns)
        if not keys:
            raise ValueError('Select at least one column')
        selected = ','.join(self._column(fields, k) for k in keys)
        ordering = []
        for item in sort or []:
            col = self._column(fields, item['field'])
            direction = item.get('direction', 'asc').lower()
            if direction not in ('asc', 'desc'):
                raise ValueError('Invalid sort direction')
            field = item['field']
            if fields[field].get('type') == 'string':
                raw_field = 'raw' + field[:1].upper() + field[1:]
                if raw_field in fields and fields[raw_field].get('type') == 'number':
                    col = self._column(fields, raw_field)
                    ordering.append(f'{col} {direction}')
                else:
                    ordering.extend([f'(sort_number({col}) IS NULL) ASC',
                                     f'sort_number({col}) {direction}',
                                     f'CASE WHEN sort_number({col}) IS NULL THEN {col} END {direction}'])
            else:
                ordering.append(f'{col} {direction}')
        return keys, selected, ' ORDER BY ' + ','.join(ordering + ['rowid'])

    def rows(self, ref, filters=None, columns=None, sort=None, offset=0, limit=100, search=''):
        started = time.perf_counter()
        if type(limit) is not int or not 0 < limit <= MAX_RESULT_ROWS or type(offset) is not int or offset < 0:
            raise ValueError(f'limit must be 1..{MAX_RESULT_ROWS}; offset must be nonnegative')
        with self._connect() as db:
            table, metadata = self._version(db, ref)
            fields = metadata['fields']
            self._indexes(db, table, fields, filters, sort)
            where, params = self._where(fields, filters, search)
            keys, selected, order = self._selection(fields, columns, sort)
            total = db.execute(f'SELECT COUNT(*) FROM {table}' + where, params).fetchone()[0]
            records = db.execute(f'SELECT {selected}, _missing FROM {table}' + where + order + ' LIMIT ? OFFSET ?', params + [limit, offset])
            result = [self._decode(keys, r[:-1], fields, r[-1]) for r in records]
        return {'rows': result, 'totalRows': total, 'durationMs': (time.perf_counter()-started)*1000}

    def aggregate(self, ref, metrics, filters=None, group_by=None, time_grain=None):
        groups = list(group_by or [])
        if time_grain and (time_grain not in ('month', 'quarter') or len(groups) != 1):
            raise ValueError('time_grain requires exactly one date group and month or quarter')
        if set(groups) & set(metrics):
            raise ValueError('Metric ids must differ from group fields')
        with self._connect() as db:
            table, metadata = self._version(db, ref)
            fields = metadata['fields']
            expressions = [self._column(fields, k) for k in groups]
            if time_grain:
                if fields[groups[0]].get('type') != 'date':
                    raise ValueError('time_grain requires a date field')
                expressions = [f"grain({expressions[0]}, '{time_grain}')"]
            if any(m['aggregation'] == 'entity_ratio' for m in metrics.values()):
                if not all(m['aggregation'] == 'entity_ratio' for m in metrics.values()):
                    raise ValueError('Entity ratios must be aggregated separately from additive measures')
                entity_fields = {m['entityField'] for m in metrics.values()}
                if len(entity_fields) != 1:
                    raise ValueError('Entity ratios must share one entity field')
                entity = self._column(fields, next(iter(entity_fields)))
                self._indexes(db, table, fields, filters)
                where, params = self._where(fields, filters)
                where += (' AND ' if where else ' WHERE ') + entity + ' IS NOT NULL'
                inner = [f'{expression} AS g{i}' for i, expression in enumerate(expressions)]
                outer = [f'g{i}' for i in range(len(groups))]
                for i, metric in enumerate(metrics.values()):
                    for part in ('numerator', 'denominator'):
                        if fields.get(metric[part], {}).get('type') != 'number':
                            raise ValueError('Entity ratio requires numeric fields')
                    n = self._column(fields, metric['numerator'])
                    d = self._column(fields, metric['denominator'])
                    inner.extend([f'SUM({n}) AS n{i}', f'SUM({d}) AS d{i}'])
                    outer.append(f'SUM(CASE WHEN n{i}>0 THEN 1 ELSE 0 END)*1.0/NULLIF(SUM(CASE WHEN d{i}>0 THEN 1 ELSE 0 END),0)')
                sql = f'SELECT {",".join(outer)} FROM (SELECT {",".join(inner)} FROM {table}{where} GROUP BY {",".join(expressions+[entity])})'
                if groups:
                    sql += ' GROUP BY ' + ','.join(f'g{i}' for i in range(len(groups)))
                records = db.execute(sql, params).fetchmany(MAX_RESULT_ROWS + 1)
                self._check_size(records)
                return [dict(zip(groups+list(metrics), row)) for row in records]
            measures = []
            for metric in metrics.values():
                op = metric['aggregation']
                if op == 'count':
                    measures.append('COUNT(*)')
                elif op == 'ratio':
                    if any(fields.get(metric[k], {}).get('type') != 'number' for k in ('numerator', 'denominator')):
                        raise ValueError('Ratio requires numeric fields')
                    numerator = self._column(fields, metric['numerator'])
                    denominator = self._column(fields, metric['denominator'])
                    measures.append(f'SUM({numerator}) * 1.0 / NULLIF(SUM({denominator}), 0)')
                elif op in ('sum', 'avg', 'min', 'max'):
                    if fields.get(metric.get('field'), {}).get('type') != 'number':
                        raise ValueError('Aggregation requires numeric field')
                    measures.append(f"{op}({self._column(fields, metric['field'])})")
                else:
                    raise ValueError('Unsupported metric aggregation')
            if not expressions and not measures:
                raise ValueError('At least one metric or group is required')
            self._indexes(db, table, fields, filters)
            where, params = self._where(fields, filters)
            sql = f'SELECT {",".join(expressions + measures)} FROM {table}' + where
            if expressions:
                sql += ' GROUP BY ' + ','.join(expressions) + ' ORDER BY MIN(rowid)'
            records = db.execute(sql, params).fetchmany(MAX_RESULT_ROWS + 1)
            self._check_size(records)
            return [dict(zip(groups + list(metrics), [bool(v) if v is not None and fields[k].get('type') == 'boolean' else v for k, v in zip(groups, row[:len(groups)])] + list(row[len(groups):]))) for row in records]

    @staticmethod
    def _check_size(records):
        if len(records) > MAX_RESULT_ROWS:
            raise DashboardError('RESULT_TOO_LARGE', f'Result exceeds {MAX_RESULT_ROWS} rows; use narrower filters or export CSV')

    def distinct(self, ref, field, filters=None):
        with self._connect() as db:
            table, metadata = self._version(db, ref)
            col = self._column(metadata['fields'], field)
            self._indexes(db, table, metadata['fields'], filters)
            where, params = self._where(metadata['fields'], filters)
            records = db.execute(f'SELECT {col} FROM {table}' + where + f' GROUP BY {col} ORDER BY MIN(rowid)', params).fetchmany(MAX_RESULT_ROWS+1)
            self._check_size(records)
            return [bool(r[0]) if r[0] is not None and metadata['fields'][field].get('type') == 'boolean' else r[0] for r in records]

    def option_page(self, refs, field, search='', offset=0, limit=100):
        """Page the complete option universe, including across consumer datasets."""
        if not isinstance(search, str) or len(search) > 1000 or type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('Invalid option search or pagination')
        with self._connect() as db:
            selects, versions = [], set()
            kind = None
            for ref in refs:
                table, metadata = self._version(db, ref)
                if metadata['version'] in versions:
                    continue
                versions.add(metadata['version'])
                column = self._column(metadata['fields'], field)
                kind = metadata['fields'][field]['type']
                selects.append(f'SELECT {column} AS value FROM {table}')
            if not selects:
                return {'values': [], 'totalValues': 0, 'offset': offset, 'hasMore': False}
            union = ' UNION ALL '.join(selects)
            where = ' WHERE search_text(value, ?, ?)' if search else ''
            params = [search, kind] if search else []
            query = f'SELECT value FROM ({union})' + where + ' GROUP BY value'
            total = db.execute('SELECT COUNT(*) FROM (' + query + ')', params).fetchone()[0]
            records = db.execute(query + ' ORDER BY value LIMIT ? OFFSET ?', params + [limit, offset])
            values = [bool(row[0]) if row[0] is not None and kind == 'boolean' else row[0] for row in records]
            return {'values': values, 'totalValues': total, 'offset': offset, 'hasMore': offset+len(values) < total}

    def iter_rows(self, ref, filters=None, columns=None, sort=None, search=''):
        """Stream every matching row for file exports, with no preview row limit."""
        with self._connect() as db:
            table, metadata = self._version(db, ref)
            fields = metadata['fields']
            self._indexes(db, table, fields, filters, sort)
            where, params = self._where(fields, filters, search)
            keys, selected, order = self._selection(fields, columns, sort)
            for row in db.execute(f'SELECT {selected}, _missing FROM {table}' + where + order, params):
                yield self._decode(keys, row[:-1], fields, row[-1])

    def export_csv(self, ref, output_path, filters=None, columns=None, sort=None, search=''):
        started = time.perf_counter()
        destination = Path(output_path).expanduser().resolve()
        if destination == self.path.resolve():
            raise ValueError('CSV output cannot overwrite the local data database')
        count = 0
        with self._connect() as db:
            table, metadata = self._version(db, ref)
            fields = metadata['fields']
            self._indexes(db, table, fields, filters, sort)
            where, params = self._where(fields, filters, search)
            keys, selected, order = self._selection(fields, columns, sort)
            cursor = db.execute(f'SELECT {selected} FROM {table}' + where + order, params)
            with destination.open('w', encoding='utf-8-sig', newline='') as output:
                writer = csv.writer(output)
                def safe(value):
                    if type(value) is bool:
                        return 'true' if value else 'false'
                    if isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r')):
                        return "'" + value
                    return value
                writer.writerow([safe(k) for k in keys])
                for row in cursor:
                    decoded = self._decode(keys, row, fields)
                    writer.writerow([safe(decoded.get(k)) for k in keys])
                    count += 1
        return {'path': str(destination), 'rowCount': count, 'bytes': destination.stat().st_size, 'durationMs': (time.perf_counter()-started)*1000}
