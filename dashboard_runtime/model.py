"""Canonical, bounded JSON contract. No generated code or SQL runs at render time."""
from __future__ import annotations
import copy
import datetime as dt
import json
import math
import re
from typing import Any

MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 20_000
MAX_COMPONENTS = 100
ID = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,79}$')
TYPES = ('bar', 'line', 'area', 'pie', 'scatter', 'heatmap', 'funnel', 'waterfall')
COLS = {'desktop': 12, 'tablet': 8, 'mobile': 4}
AGGREGATES = ('sum', 'avg', 'min', 'max', 'count', 'ratio')

class DashboardError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status
    def as_dict(self):
        return {'ok': False, 'error': {'code': self.code, 'message': str(self)}}

def require(test, message, code='INVALID_DOCUMENT'):
    if not test:
        raise DashboardError(code, message)

def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def identifier(value, label='id'):
    require(isinstance(value, str) and bool(ID.fullmatch(value)), f'{label}: invalid identifier')
    return value

def json_bytes(value):
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
    except (ValueError, TypeError, RecursionError) as exc:
        raise DashboardError('INVALID_JSON', 'Expected finite JSON values') from exc
    require(len(raw) <= MAX_BYTES, 'Artifact exceeds 16 MiB', 'PAYLOAD_TOO_LARGE')
    return raw

def new_document(board_id: str, title: str):
    identifier(board_id)
    return {'schemaVersion': 2, 'id': board_id, 'revision': 0,
            'manifest': {'title': title, 'theme': 'light', 'components': {},
                         'datasets': {}, 'metrics': {}, 'sources': {},
                         'filters': [], 'layout': {k: [] for k in COLS}},
            'snapshot': {'status': 'ready', 'updatedAt': utcnow(), 'datasets': {}}}

def field(meta, key, numeric=False):
    require(isinstance(key, str) and key in meta['fields'], f'Unknown field: {key}')
    if numeric:
        require(meta['fields'][key]['type'] == 'number', f'Numeric field required: {key}')

def compatibility(doc, component, chart_type):
    """Return an actionable reason instead of silently inventing missing fields."""
    if chart_type not in TYPES:
        return 'Unsupported chart type'
    meta = doc['manifest']['datasets'][component['datasetId']]
    x, series = component.get('x'), component.get('series')
    measures = component.get('measures', [])
    if not x:
        return 'Choose an X/category field'
    if chart_type in ('pie', 'funnel', 'waterfall', 'heatmap', 'scatter') and len(measures) != 1:
        return 'This chart requires exactly one measure'
    units = {(doc['manifest']['metrics'][mid].get('unit', ''), doc['manifest']['metrics'][mid].get('format', 'number')) for mid in measures}
    if len(units) > 1:
        return 'Mixed units require separate charts or an explicitly configured legacy dual-axis chart'
    if chart_type in ('pie', 'funnel') and doc['manifest']['metrics'][measures[0]]['aggregation'] not in ('sum', 'count'):
        return 'Pie/funnel requires an additive sum or count measure'
    if chart_type == 'scatter' and meta['fields'][x]['type'] != 'number':
        return 'Scatter requires a numeric X field'
    if chart_type == 'heatmap' and not series:
        return 'Heatmap requires a second categorical field (series)'
    if chart_type in ('pie', 'funnel', 'waterfall') and series:
        return 'Remove the series grouping for this chart'
    if chart_type == 'waterfall':
        metric = doc['manifest']['metrics'][measures[0]]
        if metric.get('semantic') != 'delta' or metric['aggregation'] != 'sum':
            return 'Waterfall requires an additive delta metric; it is not a generic bar chart'
    return None

def validate(doc):
    json_bytes(doc)
    require(isinstance(doc, dict) and doc.get('schemaVersion') == 2, 'schemaVersion must be 2')
    identifier(doc.get('id'), 'dashboard id')
    require(type(doc.get('revision')) is int and doc['revision'] >= 0, 'Invalid revision')
    m, s = doc.get('manifest'), doc.get('snapshot')
    require(isinstance(m, dict) and isinstance(s, dict), 'manifest and snapshot are required')
    require(isinstance(m.get('title'), str) and 0 < len(m['title']) <= 240, 'Title must contain 1-240 characters')
    require(m.get('theme') in ('light', 'dark'), 'Unknown theme')
    for name in ('components', 'datasets', 'metrics', 'sources', 'layout'):
        require(isinstance(m.get(name), dict), f'manifest.{name} must be an object')
    require(isinstance(s.get('datasets'), dict), 'snapshot.datasets must be an object')
    require(s.get('status') in ('ready', 'partial', 'blocked', 'fixture'), 'Unknown snapshot status')
    require(isinstance(s.get('updatedAt'), str), 'Snapshot timestamp is required')
    require(set(m['datasets']) == set(s['datasets']), 'Dataset metadata and snapshot ids must match')
    require(len(m['components']) <= MAX_COMPONENTS, 'Too many components')
    total_rows = 0
    for key, source in m['sources'].items():
        identifier(key, 'source id')
        require(isinstance(source, dict) and source.get('kind') in ('query', 'file', 'fixture', 'declared'), 'Source kind is required')
        if source['kind'] == 'query':
            q = source.get('query', {})
            require(isinstance(q, dict) and isinstance(q.get('sql'), str) and q['sql'].strip(), 'Query source needs actual SQL')
            require(isinstance(q.get('executedAt'), str) and q.get('engine') and q.get('id'), 'Query execution provenance is incomplete')
    for key, meta in m['datasets'].items():
        identifier(key, 'dataset id')
        require(isinstance(meta, dict) and isinstance(meta.get('fields'), dict) and meta['fields'], f'{key}: field metadata required')
        require(meta.get('sourceId') in m['sources'], f'{key}: sourceId is required')
        for name, info in meta['fields'].items():
            require(isinstance(name, str) and 0 < len(name) < 200, 'Invalid field name')
            require(isinstance(info, dict) and info.get('type') in ('string', 'number', 'boolean', 'date'), f'{name}: invalid field type')
        rows = s['datasets'][key]
        require(isinstance(rows, list), f'{key}: rows must be an array')
        total_rows += len(rows)
        for row in rows:
            require(isinstance(row, dict) and set(row) <= set(meta['fields']), f'{key}: undeclared row field')
            for name, value in row.items():
                kind = meta['fields'][name]['type']
                valid = (value is None or (kind == 'number' and type(value) in (int, float) and math.isfinite(value))
                         or (kind in ('string', 'date') and isinstance(value, str))
                         or (kind == 'boolean' and type(value) is bool))
                require(valid, f'{key}.{name}: value does not match {kind}')
    require(total_rows <= MAX_ROWS, f'Snapshot exceeds {MAX_ROWS} rows', 'PAYLOAD_TOO_LARGE')
    for key, metric in m['metrics'].items():
        identifier(key, 'metric id')
        require(isinstance(metric, dict), f'{key}: metric must be an object')
        ds = metric.get('datasetId')
        require(ds in m['datasets'], f'{key}: unknown metric dataset')
        require(metric.get('aggregation') in AGGREGATES, f'{key}: unsupported aggregation')
        require(isinstance(metric.get('label'), str) and metric['label'], f'{key}: label required')
        require(isinstance(metric.get('definition'), str) and metric['definition'], f'{key}: business definition required')
        require(isinstance(metric.get('unit'), str), f'{key}: explicit unit required (empty string allowed)')
        require(metric.get('format', 'number') in ('number', 'percent', 'currency'), 'Invalid metric format')
        if metric.get('format') == 'percent':
            require(metric.get('scale') == 'fraction', 'Percent metrics must declare fractional scale')
        require(metric.get('status', 'unverified') in ('unverified', 'reviewed'), 'Unsupported metric status')
        if metric['aggregation'] == 'ratio':
            field(m['datasets'][ds], metric.get('numerator'), True)
            field(m['datasets'][ds], metric.get('denominator'), True)
        elif metric['aggregation'] != 'count':
            field(m['datasets'][ds], metric.get('field'), True)
    for key, c in m['components'].items():
        identifier(key, 'component id')
        require(isinstance(c, dict) and c.get('kind') in ('chart', 'kpi', 'table', 'text', 'legacy'), f'{key}: invalid component kind')
        require(isinstance(c.get('title'), str) and len(c['title']) <= 240, f'{key}: title required')
        presentation = c.get('config', {}) if c['kind'] == 'legacy' else c.get('presentation', {})
        require(isinstance(presentation, dict), 'Presentation must be an object')
        state = presentation.get('tableState')
        if state is not None:
            require(isinstance(state, dict), 'Table state must be an object')
            columns = presentation.get('columns')
            names = {x['key'] for x in columns if isinstance(x, dict) and 'key' in x} if isinstance(columns, list) else set(m['datasets'].get(c.get('datasetId'), {}).get('fields', {}))
            for list_key in ('columns', 'visible'):
                values = state.get(list_key, [])
                require(isinstance(values, list) and all(isinstance(v, str) and v in names for v in values) and len(values) == len(set(values)), 'Unknown or repeated table state column')
            if 'columns' in state:
                require(set(state['columns']) == names, 'Table order must preserve every column')
            require(type(state.get('page', 1)) is int and state.get('page', 1) >= 1, 'Invalid table page')
            require(type(state.get('pageSize', 10)) is int and state.get('pageSize', 10) in (10, 20, 25, 50, 100, 9999), 'Invalid table page size')
            require(state.get('sortCol') is None or state['sortCol'] in names, 'Invalid table sort column')
            require(state.get('sortDir', 'asc') in ('asc', 'desc'), 'Invalid table sort direction')
        if c['kind'] == 'text':
            require(isinstance(c.get('text'), str), 'Text component requires text')
            continue
        if c['kind'] == 'legacy':
            from .legacy import validate_original
            validate_original(c)
            if c.get('binding') is not None:
                from .bindings import validate_binding
                validate_binding(doc, c)
            continue
        ds = c.get('datasetId')
        require(ds in m['datasets'], f'{key}: dataset not found')
        for dimension in ('x', 'series'):
            if c.get(dimension):
                field(m['datasets'][ds], c[dimension])
        if c['kind'] in ('chart', 'kpi'):
            require(isinstance(c.get('measures'), list) and c['measures'], f'{key}: measures required')
            require(len(c['measures']) == len(set(c['measures'])), f'{key}: repeated measure')
            for mid in c['measures']:
                require(mid in m['metrics'] and m['metrics'][mid]['datasetId'] == ds, f'{key}: metric/dataset mismatch')
            if c['kind'] == 'kpi':
                require(len(c['measures']) == 1, 'KPI must have one headline measure')
            else:
                problem = compatibility(doc, c, c.get('chartType'))
                require(problem is None, f'{key}: {problem}', 'INCOMPATIBLE_CHART')
    require(isinstance(m.get('filters'), list) and len(m['filters']) <= 30, 'Invalid filters')
    seen = set()
    for f in m['filters']:
        require(isinstance(f, dict), 'Invalid filter')
        identifier(f.get('id'), 'filter id')
        require(f['id'] not in seen, 'Duplicate filter id')
        seen.add(f['id'])
        require(f.get('op') in ('in', 'range'), 'Unknown filter operation')
        require(isinstance(f.get('values'), list), 'Filter values must be an array')
        require(all(type(v) in (str, int, float, bool) or v is None for v in f['values']), 'Filter values must be scalar')
        require(f['op'] != 'range' or len(f['values']) in (0, 2), 'Range filter needs two bounds')
        targets = f.get('componentIds')
        require(isinstance(targets, list) and targets, 'Declare explicit filter consumers')
        for target in targets:
            require(target in m['components'], 'Filter refers to a missing component')
            c = m['components'][target]
            require(c['kind'] != 'text' and (c['kind'] != 'legacy' or c.get('binding')), 'Original components need explicit bindings before filtering')
            metadata = m['datasets'][c['datasetId']]
            field(metadata, f.get('field'))
            kind = metadata['fields'][f['field']]['type']
            for value in f['values']:
                require(value is None or (kind == 'number' and type(value) in (int, float)) or (kind in ('string', 'date') and isinstance(value, str)) or (kind == 'boolean' and type(value) is bool), 'Filter value type differs from its field')
            if f['op'] == 'range' and f['values']:
                require(None not in f['values'] and f['values'][0] <= f['values'][1], 'Invalid filter range')
    for bp, columns in COLS.items():
        layout = m['layout'].get(bp)
        require(isinstance(layout, list), f'{bp}: layout must be an array')
        require(len(layout) == len(m['components']) and {p.get('id') for p in layout if isinstance(p, dict)} == set(m['components']), f'{bp}: every component needs exactly one placement')
        for i, p in enumerate(layout):
            require(all(type(p.get(v)) is int for v in ('x', 'y', 'w', 'h')), 'Layout uses integer grid coordinates')
            require(0 <= p['x'] and 0 <= p['y'] <= 10000 and 1 <= p['w'] <= columns and 2 <= p['h'] <= 100 and p['x'] + p['w'] <= columns, f'{bp}: layout out of bounds')
            for q in layout[:i]:
                overlap = p['x'] < q['x'] + q['w'] and q['x'] < p['x'] + p['w'] and p['y'] < q['y'] + q['h'] and q['y'] < p['y'] + p['h']
                require(not overlap, f'{bp}: overlapping cards {p["id"]} and {q["id"]}')
    return doc

def place_new(m, key):
    for bp, cols in COLS.items():
        layout = m['layout'][bp]
        y = max((p['y'] + p['h'] for p in layout), default=0)
        layout.append({'id': key, 'x': 0, 'y': y, 'w': cols, 'h': 6})

def apply_operations(doc, operations):
    require(isinstance(operations, list) and 0 < len(operations) <= 200, 'Expected 1-200 operations')
    result = copy.deepcopy(doc)
    m, s = result['manifest'], result['snapshot']
    for op in operations:
        require(isinstance(op, dict), 'Operation must be an object')
        kind = op.get('op')
        if kind in ('put_source', 'put_metric', 'put_component'):
            key = identifier(op.get('id'))
            collection = {'put_source': 'sources', 'put_metric': 'metrics', 'put_component': 'components'}[kind]
            require(isinstance(op.get('value'), dict), 'Operation value must be an object')
            if kind == 'put_component' and key not in m['components']:
                place_new(m, key)
            m[collection][key] = copy.deepcopy(op['value'])
            if kind == 'put_component' and m[collection][key].get('binding'):
                binding = m[collection][key]['binding']
                require(isinstance(binding, dict), 'binding must be an object')
                m[collection][key]['datasetId'] = binding.get('datasetId')
                require(isinstance(binding.get('measures', {}), dict), 'Binding measures must be an object')
                m[collection][key]['measures'] = list(dict.fromkeys(binding.get('measures', {}).values()))
        elif kind == 'put_dataset':
            key = identifier(op.get('id'))
            m['datasets'][key] = copy.deepcopy(op.get('meta'))
            s['datasets'][key] = copy.deepcopy(op.get('rows'))
            s['updatedAt'] = utcnow()
        elif kind == 'remove_component':
            key = op.get('id')
            require(key in m['components'], 'Component does not exist')
            del m['components'][key]
            for bp in COLS:
                m['layout'][bp] = [p for p in m['layout'][bp] if p['id'] != key]
            for f in m['filters']:
                f['componentIds'] = [x for x in f['componentIds'] if x != key]
            m['filters'] = [f for f in m['filters'] if f['componentIds']]
        elif kind == 'set_chart':
            key = op.get('id')
            require(key in m['components'] and m['components'][key]['kind'] == 'chart', 'Chart not found')
            m['components'][key]['chartType'] = op.get('chartType')
        elif kind == 'set_layout':
            bp = op.get('breakpoint', 'desktop')
            require(bp in COLS, 'Unknown breakpoint')
            m['layout'][bp] = copy.deepcopy(op.get('value'))
        elif kind in ('set_title', 'set_theme', 'set_filters'):
            m[kind[4:]] = copy.deepcopy(op.get('value'))
        elif kind == 'set_status':
            s['status'] = op.get('value')
        else:
            raise DashboardError('UNKNOWN_OPERATION', f'Unsupported operation: {kind}')
    return validate(result)

def inferred_fields(rows):
    require(isinstance(rows, list) and bool(rows), 'Non-empty rows are needed to infer field types')
    fields = {}
    for key in dict.fromkeys(k for row in rows for k in row):
        values = [r[key] for r in rows if r.get(key) is not None]
        kind = ('number' if values and all(type(v) in (int, float) for v in values)
                else 'boolean' if values and all(type(v) is bool for v in values) else 'string')
        fields[key] = {'type': kind, 'label': key}
    return fields
