"""Canonical, bounded JSON contract. No generated code or SQL runs at render time."""
from __future__ import annotations
import copy
import datetime as dt
import json
import math
import re

MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 20_000
MAX_COMPONENTS = 100
MAX_REPORT_BLOCKS = 100
MAX_REPORT_SUBTITLE = 1000
MAX_REPORT_MARKDOWN = 200_000
MAX_REPORT_CAPTION = 500
MAX_REPORT_SOURCE = 1000
ID = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,79}$')
TYPES = ('bar', 'line', 'area', 'pie', 'scatter', 'heatmap', 'funnel', 'waterfall')
COLS = {'desktop': 12, 'tablet': 8, 'mobile': 4}
AGGREGATES = ('sum', 'avg', 'min', 'max', 'count', 'ratio', 'entity_ratio')
VIEW_MODES = ('dashboard', 'report')

class DashboardError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status
    def as_dict(self):
        detail = {'code': self.code, 'message': str(self)}
        if getattr(self, 'request_id', None):
            detail['requestId'] = self.request_id
        return {'ok': False, 'error': detail}

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

def report_chart_references(markdown, components=None):
    """Read top-level chart fences as bounded data, never as executable code.

    Ordinary fenced code is skipped, including chart-looking examples nested in it.
    Both Markdown fence characters are accepted with 0-3 leading spaces. A chart
    block uses the exact, case-sensitive info string ``chart`` and must close.
    """
    require(isinstance(markdown, str) and len(markdown) <= MAX_REPORT_MARKDOWN,
            f'Report markdown must contain 0-{MAX_REPORT_MARKDOWN} characters')
    references = []
    opened, body, chart, start_line, containers = None, [], False, 0, []
    for line_number, original_line in enumerate(markdown.splitlines(), 1):
        # Expanding indentation tabs follows Markdown's four-column tab stops.
        line = original_line.expandtabs(4)
        candidate = line
        if opened is not None and containers:
            for prefix in containers:
                match = re.match(prefix, candidate)
                if match is None:
                    # Leaving a quote/list also ends its ordinary fenced code.
                    opened, body, chart, containers = None, [], False, []
                    break
                candidate = candidate[match.end():]
        if opened is not None:
            closed = re.fullmatch(r' {0,3}' + re.escape(opened[0]) +
                                  r'{' + str(len(opened)) + r',}[ \t]*', candidate)
            if not closed:
                if chart:
                    body.append(original_line)
                continue
            if chart:
                try:
                    def unique_keys(pairs):
                        result = {}
                        for key, value in pairs:
                            if key in result:
                                raise ValueError('Duplicate JSON key')
                            result[key] = value
                        return result
                    value = json.loads('\n'.join(body), object_pairs_hook=unique_keys)
                except (ValueError, RecursionError) as exc:
                    raise DashboardError('INVALID_DOCUMENT',
                        f'Chart fence at line {start_line}: invalid JSON; use {{"componentId":"trend"}}') from exc
                require(isinstance(value, dict) and 'componentId' in value and
                        set(value) <= {'componentId', 'caption', 'source'},
                        f'Chart fence at line {start_line} requires componentId and permits only optional caption/source')
                target = identifier(value['componentId'], 'chart fence componentId')
                for name, limit in (('caption', MAX_REPORT_CAPTION), ('source', MAX_REPORT_SOURCE)):
                    if name in value:
                        require(isinstance(value[name], str) and len(value[name]) <= limit,
                                f'Chart fence at line {start_line}: {name} must contain 0-{limit} characters')
                if components is not None:
                    require(target in components,
                            f'Chart fence refers to missing component "{target}"; insert an existing component ID')
                    require(components[target].get('kind') != 'text',
                            f'Chart fence "{target}" must reference a non-text component; write narrative in Markdown')
                references.append(target)
            opened, body, chart, containers = None, [], False, []
            continue
        # Recognize explicit containers so examples inside their ordinary code
        # fences stay inert, while real nested chart fences get useful feedback.
        candidate, prefixes = line, []
        while True:
            quote = re.match(r' {0,3}> ?', candidate)
            item = re.match(r'( {0,3})([-+*]|[0-9]{1,9}[.)])( +)', candidate)
            if quote:
                prefixes.append(r' {0,3}> ?')
                candidate = candidate[quote.end():]
            elif item:
                padding = len(item[3]) if len(item[3]) <= 4 else 1
                width = len(item[1]) + len(item[2]) + padding
                prefixes.append(r' {' + str(width) + '}')
                candidate = candidate[width:]
            else:
                break
        match = re.fullmatch(r' {0,3}(`{3,}|~{3,})(.*)', candidate)
        if match and not (match[1][0] == '`' and '`' in match[2]):
            opened, chart, start_line = match[1], match[2].strip() == 'chart', line_number
            require(not chart or not prefixes,
                    f'Chart fence at line {line_number} must be top-level; move it outside the list or blockquote')
            containers = prefixes
    require(opened is None or not chart,
            f'Chart fence at line {start_line} is not closed; add its closing fence before saving')
    return references


def validate_report(report, components=None):
    """Markdown is canonical when present; legacy metadata remains readable."""
    require(isinstance(report, dict), 'manifest.report must be an object')
    canonical = 'markdown' in report
    if canonical:
        report_chart_references(report['markdown'], components)
    if canonical and 'subtitle' not in report and 'blocks' not in report:
        return
    require(isinstance(report.get('subtitle'), str) and len(report['subtitle']) <= MAX_REPORT_SUBTITLE,
            f'Report subtitle must contain 0-{MAX_REPORT_SUBTITLE} characters')
    blocks = report.get('blocks')
    require(isinstance(blocks, list) and len(blocks) <= MAX_REPORT_BLOCKS,
            f'Report blocks must be an array of at most {MAX_REPORT_BLOCKS} items')
    ids, references = set(), set()
    for block in blocks:
        require(isinstance(block, dict), 'Report block must be an object')
        key = identifier(block.get('id'), 'report block id')
        target = identifier(block.get('componentId'), 'report component id')
        require(key not in ids, 'Duplicate report block id')
        require(target not in references, 'Duplicate report component reference')
        # Once migrated, historical blocks no longer control rendering or deletion.
        if components is not None and not canonical:
            require(target in components, 'Report refers to a missing component')
        ids.add(key)
        references.add(target)


def report_markdown(manifest):
    """Return canonical source, or safely migrate legacy display without mutation."""
    report = manifest.get('report', {})
    if 'markdown' in report:
        return report['markdown']

    def literal(value):
        # Preserve the old plain-text semantics: no injected Markdown or raw HTML.
        return re.sub(r'([!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])', r'\\\1', value)

    parts = ['# ' + literal(' '.join(manifest['title'].splitlines()))]
    if report.get('subtitle'):
        parts.append(literal(report['subtitle']))
    blocks = report.get('blocks')
    if blocks is None:
        blocks = [{'componentId': p['id']} for p in sorted(
            manifest['layout']['desktop'], key=lambda p: (p['y'], p['x']))]
    for block in blocks:
        key = block['componentId']
        component = manifest['components'][key]
        if component['kind'] == 'text':
            if component['title']:
                parts.append('## ' + literal(' '.join(component['title'].splitlines())))
            if isinstance(component.get('subtitle'), str) and component['subtitle']:
                parts.append(literal(component['subtitle']))
            if component['text']:
                parts.append(literal(component['text']))
        else:
            parts.append('```chart\n' + json.dumps({'componentId': key}, separators=(',', ':')) + '\n```')
    return '\n\n'.join(parts) + '\n'


def append_report_component(report, key):
    """Use readable bounded IDs, including when a custom block already owns the ID."""
    if any(block['componentId'] == key for block in report['blocks']):
        return
    ids = {block['id'] for block in report['blocks']}
    block_id, suffix = key, 2
    while block_id in ids:
        ending = f'-{suffix}'
        block_id = key[:80 - len(ending)] + ending
        suffix += 1
    report['blocks'].append({'id': block_id, 'componentId': key})

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
    assert isinstance(m, dict) and isinstance(s, dict)
    require(isinstance(m.get('title'), str) and 0 < len(m['title']) <= 240, 'Title must contain 1-240 characters')
    metadata = m.get('meta', {})
    require(isinstance(metadata, dict), 'manifest.meta must be an object')
    require(set(metadata) <= {'subtitle', 'org', 'system', 'statusText', 'iconKey'}, 'Unknown page metadata field')
    for name, value in metadata.items():
        require(isinstance(value, str) and len(value) <= 1000, f'meta.{name} must contain 0-1000 characters')
    require(metadata.get('iconKey', 'chart') in ('chart', 'plane'), 'Page iconKey must be chart or plane')
    require(m.get('theme') in ('light', 'dark'), 'Unknown theme')
    require(m.get('viewMode', 'dashboard') in VIEW_MODES, 'Unknown view mode')
    for name in ('components', 'datasets', 'metrics', 'sources', 'layout'):
        require(isinstance(m.get(name), dict), f'manifest.{name} must be an object')
    require(isinstance(s.get('datasets'), dict), 'snapshot.datasets must be an object')
    require(s.get('status') in ('ready', 'partial', 'blocked', 'fixture'), 'Unknown snapshot status')
    require(isinstance(s.get('updatedAt'), str), 'Snapshot timestamp is required')
    refs = s.get('datasetRefs', {})
    table_refs = s.get('componentDataRefs', {})
    require(isinstance(refs, dict), 'snapshot.datasetRefs must be an object')
    require(isinstance(table_refs, dict), 'snapshot.componentDataRefs must be an object')
    require(not (set(refs) & set(s['datasets'])), 'Dataset must have either rows or a local version, not both')
    require(set(m['datasets']) == set(s['datasets']) | set(refs), 'Dataset metadata and snapshot ids must match')
    for key in table_refs:
        component = m['components'].get(key, {})
        require(component.get('kind') == 'legacy' and component.get('family') == 'table' and not component.get('binding'),
                'Component data references belong to unbound original tables')
    for ref in [*refs.values(), *table_refs.values()]:
        require(isinstance(ref, dict) and isinstance(ref.get('version'), str)
                and re.fullmatch(r'[0-9a-f]{64}', ref['version']) is not None,
                'Local data version must be a content hash')
        require(type(ref.get('rowCount')) is int and ref['rowCount'] >= 0, 'Local data row count is required')
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
        if key in refs:
            require(refs[key].get('fields') == meta['fields'], f'{key}: local version fields must match dataset metadata')
            continue
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
        require(type(metric.get('decimals', 2)) is int and 0 <= metric.get('decimals', 2) <= 6, f'{key}: decimals must be an integer 0-6')
        if metric['aggregation'] in ('ratio', 'entity_ratio'):
            field(m['datasets'][ds], metric.get('numerator'), True)
            field(m['datasets'][ds], metric.get('denominator'), True)
            if metric['aggregation'] == 'entity_ratio':
                field(m['datasets'][ds], metric.get('entityField'))
        elif metric['aggregation'] != 'count':
            field(m['datasets'][ds], metric.get('field'), True)
    require(sum(isinstance(c, dict) and c.get('kind') == 'statistical' for c in m['components'].values()) <= 10, 'At most 10 statistical components per document')
    for key, c in m['components'].items():
        identifier(key, 'component id')
        require(isinstance(c, dict) and c.get('kind') in ('chart', 'kpi', 'table', 'text', 'legacy', 'statistical'), f'{key}: invalid component kind')
        require(isinstance(c.get('title'), str) and len(c['title']) <= 240, f'{key}: title required')
        require(isinstance(c.get('subtitle', ''), str) and len(c.get('subtitle', '')) <= 1000, f'{key}: subtitle must contain 0-1000 characters')
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
        if c['kind'] == 'statistical':
            from .statistical import validate_statistical
            validate_statistical(doc, c)
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
                from .legacy import validate_comparisons
                validate_comparisons(presentation, f'components.{key}.presentation')
                require(len(c['measures']) == 1, 'KPI must have one headline measure')
                card_type = presentation.get('type', 'mc01')
                require(isinstance(card_type, str) and card_type in {f'mc{i:02}' for i in range(1, 10)}, 'Unknown KPI presentation type')
                if presentation.get('type') == 'mc03':
                    if 'timeField' in presentation:
                        field(m['datasets'][ds], presentation['timeField'])
                    else:
                        require(isinstance(presentation.get('sparkData', presentation.get('sparkline')), list), 'mc03 requires timeField or explicit sparkData')
                if presentation.get('type') == 'mc06':
                    require('leftVal' in presentation and 'rightVal' in presentation, 'mc06 requires explicit leftVal and rightVal')
            else:
                problem = compatibility(doc, c, c.get('chartType'))
                require(problem is None, f'{key}: {problem}', 'INCOMPATIBLE_CHART')
    annotations = m.get('annotations', [])
    require(isinstance(annotations, list) and len(annotations) <= 100, 'At most 100 annotations per document')
    annotation_ids = set()
    for note in annotations:
        require(isinstance(note, dict), 'Annotation must be an object')
        identifier(note.get('id'), 'annotation id')
        require(note['id'] not in annotation_ids, 'Duplicate annotation id')
        annotation_ids.add(note['id'])
        require(note.get('componentId') is None or note['componentId'] in m['components'] or isinstance(note.get('anchor'), dict) or isinstance(note.get('context'), dict), 'Unknown annotation component')
        if note.get('componentId') is not None:
            identifier(note['componentId'], 'annotation component')
        if 'anchor' in note:
            anchor = note['anchor']
            require(isinstance(anchor, dict), 'Annotation anchor must be an object')
            require(anchor.get('scope') in ('component', 'text', 'page'), 'Invalid annotation scope')
            require((anchor['scope'] == 'component') == (note.get('componentId') is not None), 'Annotation scope must match component')
            require(anchor.get('kind') in ('element', 'area'), 'Invalid annotation selection')
            require(isinstance(anchor.get('quote'), str) and len(anchor['quote']) <= 1000, 'Invalid annotation quote')
            if anchor['scope'] == 'text':
                require(bool(anchor['quote'].strip()), 'Annotation text anchor requires quote')
                require(type(anchor.get('occurrence')) is int and 0 <= anchor['occurrence'] <= 10000, 'Invalid annotation occurrence')
            rect = anchor.get('rect')
            require(isinstance(rect, dict), 'Annotation rectangle required')
            for axis in ('x', 'y', 'width', 'height'):
                value = rect.get(axis)
                require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1, 'Invalid annotation rectangle')
            require(rect['x'] + rect['width'] <= 1.000001 and rect['y'] + rect['height'] <= 1.000001, 'Annotation rectangle exceeds target')
        require(isinstance(note.get('text'), str) and bool(note['text'].strip()) and len(note['text']) <= 4000, 'Annotation text must contain 1-4000 characters')
        require(isinstance(note.get('createdAt'), str) and 0 < len(note['createdAt']) <= 100, 'Annotation timestamp required')
    if 'report' in m:
        validate_report(m['report'], m['components'])
    require(isinstance(m.get('filters'), list) and len(m['filters']) <= 30, 'Invalid filters')
    seen = set()
    for f in m['filters']:
        require(isinstance(f, dict), 'Invalid filter')
        identifier(f.get('id'), 'filter id')
        require(f['id'] not in seen, 'Duplicate filter id')
        seen.add(f['id'])
        require(f.get('op') in ('in', 'range', 'contains'), 'Unknown filter operation')
        require(isinstance(f.get('values'), list), 'Filter values must be an array')
        require(f.get('selectionMode', 'multiple') in ('single', 'multiple'), 'Unknown filter selection mode')
        if f.get('selectionMode') == 'single':
            require(f['op'] == 'in' and len(f['values']) <= 1, 'Single-select filter allows at most one value')
        require(all(type(v) in (str, int, float, bool) or v is None for v in f['values']), 'Filter values must be scalar')
        require(f['op'] != 'range' or len(f['values']) in (0, 2), 'Range filter needs two bounds')
        if f['op'] == 'contains':
            require(len(f['values']) <= 1 and all(isinstance(v, str) and len(v) <= 1000 for v in f['values']), 'Search filter requires at most one text value (0-1000 characters)')
        targets = f.get('componentIds')
        require(isinstance(targets, list) and targets, 'Declare explicit filter consumers')
        for target in targets:
            require(target in m['components'], 'Filter refers to a missing component')
            c = m['components'][target]
            require(c['kind'] != 'statistical', 'Statistical components are static raw-observation plots; filters are not supported')
            require(c['kind'] != 'text' and (c['kind'] != 'legacy' or c.get('binding')), 'Original components need explicit bindings before filtering')
            metadata = m['datasets'][c['datasetId']]
            field(metadata, f.get('field'))
            kind = metadata['fields'][f['field']]['type']
            if f['op'] == 'contains':
                require(kind == 'string', 'Search filter requires a string field')
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

def place_new(m, key, c):
    height = 4 if c.get('kind') == 'kpi' or c.get('family') == 'kpi' else 6
    for bp, cols in COLS.items():
        layout = m['layout'][bp]
        y = max((p['y'] + p['h'] for p in layout), default=0)
        layout.append({'id': key, 'x': 0, 'y': y, 'w': cols, 'h': height})

def apply_operations(doc, operations):
    require(isinstance(operations, list) and 0 < len(operations) <= 200, 'Expected 1-200 operations')
    result = copy.deepcopy(doc)
    m, s = result['manifest'], result['snapshot']
    initialize_report = False
    for op in operations:
        require(isinstance(op, dict), 'Operation must be an object')
        kind = op.get('op')
        if kind in ('put_source', 'put_metric', 'put_component'):
            key = identifier(op.get('id'))
            collection = {'put_source': 'sources', 'put_metric': 'metrics', 'put_component': 'components'}[kind]
            require(isinstance(op.get('value'), dict), 'Operation value must be an object')
            if kind == 'put_component' and key not in m['components']:
                place_new(m, key, op['value'])
                if 'report' in m and 'markdown' not in m['report']:
                    append_report_component(m['report'], key)
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
            s.get('datasetRefs', {}).pop(key, None)
            s['updatedAt'] = utcnow()
        elif kind == 'put_dataset_ref':
            key = identifier(op.get('id'))
            m['datasets'][key] = copy.deepcopy(op.get('meta'))
            s['datasets'].pop(key, None)
            s.setdefault('datasetRefs', {})[key] = copy.deepcopy(op.get('ref'))
            s['updatedAt'] = utcnow()
        elif kind == 'remove_component':
            key = op.get('id')
            require(key in m['components'], 'Component does not exist')
            if 'markdown' in m.get('report', {}):
                require(key not in report_chart_references(m['report']['markdown']),
                        f'Component "{key}" is referenced in report Markdown; remove its chart fence before deleting it',
                        'REPORT_COMPONENT_REFERENCED')
            del m['components'][key]
            if 'annotations' in m:
                m['annotations'] = [note for note in m['annotations'] if note['componentId'] != key or note.get('anchor')]
            for bp in COLS:
                m['layout'][bp] = [p for p in m['layout'][bp] if p['id'] != key]
            for f in m['filters']:
                f['componentIds'] = [x for x in f['componentIds'] if x != key]
            m['filters'] = [f for f in m['filters'] if f['componentIds']]
            if 'report' in m and 'markdown' not in m['report']:
                m['report']['blocks'] = [b for b in m['report']['blocks'] if b['componentId'] != key]
        elif kind == 'set_original_chart':
            key, code = op.get('id'), op.get('code')
            require(key in m['components'], 'Chart not found')
            component = m['components'][key]
            require(component.get('kind') == 'legacy' and component.get('family') == 'chart', 'Original chart required')
            current = component['config']['code']
            require(current in ('c01', 'c02') and code in ('c01', 'c02'), 'No reviewed conversion between these original codes', 'INCOMPATIBLE_CHART')
            if current != code:
                component['config']['code'] = code
                axes = component['config']['presentation']['axisLabels']
                axes['x'], axes['y'] = axes['y'], axes['x']
        elif kind == 'set_chart':
            key = op.get('id')
            require(key in m['components'] and m['components'][key]['kind'] == 'chart', 'Chart not found')
            m['components'][key]['chartType'] = op.get('chartType')
        elif kind == 'set_layout':
            bp = op.get('breakpoint', 'desktop')
            require(bp in COLS, 'Unknown breakpoint')
            m['layout'][bp] = copy.deepcopy(op.get('value'))
        elif kind in ('set_title', 'set_theme', 'set_filters', 'set_meta', 'set_annotations'):
            m[kind[4:]] = copy.deepcopy(op.get('value'))
        elif kind == 'set_view_mode':
            value = op.get('value')
            require(value in VIEW_MODES, 'Unknown view mode')
            m['viewMode'] = value
            if value == 'report' and 'markdown' not in m.get('report', {}):
                initialize_report = True
        elif kind == 'set_report_markdown':
            markdown = copy.deepcopy(op.get('value'))
            # Component references may be created later in this atomic batch.
            report_chart_references(markdown)
            m.setdefault('report', {})['markdown'] = markdown
        elif kind == 'set_report':
            report = copy.deepcopy(op.get('value'))
            # References may be created by later operations in this atomic batch.
            validate_report(report)
            m['report'] = report
        elif kind == 'set_status':
            s['status'] = op.get('value')
        elif kind == 'set_data_mode':
            require(op.get('value') in ('local', 'snapshot'), 'Data mode must be local or snapshot')
            s['localMode'] = op['value'] == 'local'
        else:
            raise DashboardError('UNKNOWN_OPERATION', f'Unsupported operation: {kind}')
    if initialize_report and 'markdown' not in m.get('report', {}):
        if 'report' in m:
            validate_report(m['report'], m['components'])
        markdown = report_markdown(m)
        m.setdefault('report', {})['markdown'] = markdown
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
