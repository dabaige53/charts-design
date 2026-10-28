"""Resolve original component contracts against local data, without shipping observations."""
from __future__ import annotations

import copy
import json
import time
from decimal import Decimal, ROUND_HALF_UP

from .model import apply_operations, json_bytes, require
from .local_data import QueryCache, semantic_filters


def _key(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def formatted(value, metric, signed=False):
    if value is None:
        return '—'
    n = Decimal(str(value)) * (100 if metric.get('format') == 'percent' else 1)
    n = n.quantize(Decimal(1).scaleb(-metric.get('decimals', 2)), rounding=ROUND_HALF_UP)
    if n == 0:
        n = abs(n)
    text = format(n, ',f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    text += '%' if metric.get('format') == 'percent' else (' ' + metric['unit'] if metric.get('unit') else '')
    return ('+' if signed and n > 0 else '') + text


class LocalView:
    def __init__(self, data):
        self.data = data
        self.query_cache = QueryCache()

    def aggregate(self, ref, metrics, filters, groups=None, grain=None):
        # Metric identity and labels are presentation; cache the calculation only.
        names = list(metrics)
        semantic_keys = ('aggregation', 'field', 'numerator', 'denominator', 'entityField')
        definitions = [{k: v for k, v in metrics[name].items() if k in semantic_keys} for name in names]
        canonical = sorted({_key(d): d for d in definitions}.values(), key=_key)
        prefix = '__metric_'
        while any(f'{prefix}{i}' in (groups or []) for i in range(len(canonical))):
            prefix = '_' + prefix
        alias_names = [f'{prefix}{i}' for i in range(len(canonical))]
        aliases = dict(zip(alias_names, canonical))
        key = _key([ref['version'], canonical, semantic_filters(filters), groups or [], grain])
        result, hit = self.query_cache.get(key, lambda: self.data.aggregate(ref, aliases, filters, group_by=groups, time_grain=grain))
        translated = []
        for row in result:
            translated.append({**{k: row[k] for k in groups or []}, **{name: row[alias_names[canonical.index(definition)]] for name, definition in zip(names, definitions)}})
        return translated, hit

    def prepare(self, document, filters=None, table_states=None, granularities=None, component_ids=None, include_filter_options=True):
        started = time.perf_counter()
        doc = copy.deepcopy(document)
        if filters is not None:
            doc = apply_operations(doc, [{'op': 'set_filters', 'value': filters}])
        m, s = doc['manifest'], doc['snapshot']
        require(not s['datasets'], 'Local preview requires versioned datasets')
        refs = s.get('datasetRefs', {})
        computed = {'components': {}, 'tables': {}, 'grouped': {}, 'filterOptions': {}, 'filterPages': {}, 'cacheHits': 0}
        table_states, granularities = table_states or {}, granularities or {}
        require(set(table_states) <= set(m['components']), 'Unknown table view component')
        require(set(granularities) <= set(m['components']) and all(v in ('month', 'quarter') for v in granularities.values()), 'Invalid chart granularity')
        selected = set(m['components']) if component_ids is None else set(component_ids)
        require(selected <= set(m['components']), 'Unknown view component')
        if component_ids is None:
            for ds, ref in refs.items():
                declared = {f['field'] for f in m['filters'] if any(m['components'][cid].get('datasetId') == ds for cid in f['componentIds'])}
                for c in m['components'].values():
                    if c.get('datasetId') == ds and (c.get('family') == 'table' or c.get('kind') == 'table'):
                        declared.update(k for k, v in ref['fields'].items() if v['type'] == 'number')
                self.data.prepare_indexes(ref, declared)
        for key, c in m['components'].items():
            if key not in selected:
                continue
            family = c.get('family', 'chart') if c['kind'] == 'legacy' else c['kind']
            if family in ('text', 'statistical'):
                continue
            raw = copy.deepcopy(c.get('config', {}) if c['kind'] == 'legacy' else {**c.get('presentation', {}), **c.get('config', {})})
            binding = c.get('binding')
            ds = c.get('datasetId')
            ref = refs.get(ds) if ds else s.get('componentDataRefs', {}).get(key)
            active = [f for f in m['filters'] if key in f['componentIds'] and f['values']]
            if ref is None:
                computed['components'][key] = raw
                continue
            if family == 'table':
                state = {**raw.get('tableState', {}), **table_states.get(key, {})}
                page, size = state.get('page', 1), state.get('pageSize', 10)
                require(type(page) is int and page >= 1 and type(size) is int and size in (10, 20, 25, 50, 100, 9999), 'Invalid table pagination')
                metadata = m['datasets'][ds]['fields'] if ds else ref['fields']
                columns = raw.get('columns') or c.get('presentation', {}).get('columns') or [{'key': k, 'title': v.get('label', k), 'align': 'right' if v['type'] == 'number' else 'left'} for k, v in metadata.items()]
                fields = [col['key'] for col in columns]
                require(not (set(fields) - set(ref['fields'])), 'Unknown table column')
                sort = [{'field': state['sortCol'], 'direction': state.get('sortDir', 'asc')}] if state.get('sortCol') else []
                search = state.get('keyword', '')
                require(isinstance(search, str) and len(search) <= 1000, 'Table search must contain at most 1000 characters')
                request = self.data.rows(ref, active, columns=fields, sort=sort, offset=(page-1)*size, limit=size, search=search)
                total = request['totalRows']
                last_page = max(1, (total+size-1)//size)
                if page > last_page:
                    page = last_page
                    request = self.data.rows(ref, active, columns=fields, sort=sort, offset=(page-1)*size, limit=size, search=search)
                raw.update({'rows': request['rows'], 'columns': columns})
                computed['tables'][key] = {'page': page, 'pageSize': size, 'totalRows': total, 'sortCol': state.get('sortCol'), 'sortDir': state.get('sortDir', 'asc'), 'keyword': search, 'durationMs': request['durationMs']}
                computed['components'][key] = raw
                continue
            mids = binding.get('measures', {}) if binding else {mid: mid for mid in c.get('measures', [])}
            definitions = {mid: m['metrics'][mid] for mid in dict.fromkeys(mids.values())}
            if family == 'kpi':
                result, hit = self.aggregate(ref, definitions, active)
                computed['cacheHits'] += int(hit)
                values = result[0]
                if binding:
                    for name in ('yoy', 'mom', 'subVal', 'leftVal', 'rightVal'):
                        if name in raw and name not in mids:
                            raw[name] = '—'
                    for target, mid in mids.items():
                        value = values[mid]
                        value = None if value is None else value * binding.get('scale', {}).get(target, 1)
                        raw[target] = value if target == 'percent' else formatted(value, m['metrics'][mid], target in ('yoy', 'mom'))
                else:
                    metric = m['metrics'][c['measures'][0]]
                    raw.update({'type': raw.get('type', 'mc01'), 'label': c['title'], 'value': formatted(values[c['measures'][0]], metric),
                                'statusBadge': '已复核' if metric.get('status') == 'reviewed' else '待复核',
                                'subLabel': raw.get('subLabel', '统计口径'), 'subVal': raw.get('subVal', {'sum': '合计', 'ratio': '分子 / 分母', 'avg': '平均', 'count': '计数'}.get(metric['aggregation'], metric['aggregation']))})
                    if active:
                        for name in ('yoy', 'mom', 'subVal', 'leftVal', 'rightVal', 'trendLabel', 'gaugeSub'):
                            if name in raw:
                                raw[name] = '—'
                        raw['subLabel'] = '当前筛选范围'
                time_field = binding.get('timeField') if binding else raw.get('timeField')
                if raw.get('type') == 'mc03' and time_field:
                    mid = mids.get('value') if binding else c['measures'][0]
                    spark, hit = self.aggregate(ref, {mid: definitions[mid]}, active, [time_field])
                    computed['cacheHits'] += int(hit)
                    spark.sort(key=lambda row: str(row[time_field]))
                    raw['sparkMonths'] = [r[time_field] for r in spark]
                    multiplier = 100 if not binding and definitions[mid].get('format') == 'percent' else 1
                    raw['sparkData'] = [None if r[mid] is None else r[mid] * multiplier for r in spark]
                computed['components'][key] = raw
                continue
            if binding:
                category = binding['categoryField']
                grain = granularities.get(key, raw.get('defaultGranularity', 'month')) if binding.get('timeGrain') else None
                if grain:
                    raw['defaultGranularity'] = grain
                grouped, hit = self.aggregate(ref, definitions, active, [category], grain)
                computed['cacheHits'] += int(hit)
                if grain:
                    grouped.sort(key=lambda row: str(row[category]))
                if binding.get('orderBy'):
                    order = binding['orderBy']
                    mid = mids[order['target']]
                    direction = -1 if order['direction'] == 'desc' else 1
                    grouped.sort(key=lambda row: (row[mid] is None, direction*(row[mid] or 0), str(row[category])))
                raw.setdefault('data', {})
                data = {} if raw['code'] == 't06' else raw['data']
                def displayed(row, target, mid):
                    metric = m['metrics'][mid]
                    return None if row[mid] is None else float(Decimal(str(row[mid] * binding.get('scale', {}).get(target, 1))).quantize(Decimal(1).scaleb(-metric.get('decimals', 2)), rounding=ROUND_HALF_UP))
                if raw['code'] == 'r02':
                    points = []
                    for row in grouped:
                        values = [displayed(row, target, mids[target]) for target in ('x', 'y', 'size')]
                        if row[category] not in (None, '') and all(v is not None for v in values) and values[2] is not None and values[2] >= 0:
                            points.append([*values, row[category]])
                    data['clusters'] = points
                else:
                    data[binding['categoryTarget']] = [r[category] for r in grouped if r[category] is not None]
                    for target, mid in mids.items():
                        data[target] = [displayed(r, target, mid) for r in grouped if r[category] is not None]
                raw['data'] = {'month': data, 'quarter': copy.deepcopy(data)} if raw['code'] == 't06' else data
                raw['hasGranularity'] = bool(binding.get('timeGrain'))
                computed['components'][key] = raw
            else:
                groups = [c['x']] + ([c['series']] if c.get('series') else [])
                grouped, hit = self.aggregate(ref, definitions, active, groups)
                computed['cacheHits'] += int(hit)
                computed['grouped'][key] = [{'x': r[c['x']], 'group': r.get(c.get('series')), 'values': {mid: r[mid] for mid in definitions}} for r in grouped]
        for f in m['filters'] if include_filter_options else []:
            if f['op'] != 'in':
                continue
            options = self.filter_options(doc, f['id'])
            computed['filterOptions'][f['id']] = options['values']
            computed['filterPages'][f['id']] = options
        s['localMode'] = True
        computed['durationMs'] = (time.perf_counter()-started)*1000
        computed['sourceRows'] = {key: ref['rowCount'] for key, ref in refs.items()}
        computed['sourceBytes'] = sum(ref['bytes'] for ref in refs.values())
        doc['computed'] = computed
        computed['responseBytes'] = len(json_bytes(doc))
        return doc

    def filter_options(self, document, filter_id, search='', offset=0, limit=100):
        m = document['manifest']
        declared = next((f for f in m['filters'] if f['id'] == filter_id), None)
        require(declared is not None and declared['op'] == 'in', 'Unknown selection filter')
        assert declared is not None
        refs = document['snapshot'].get('datasetRefs', {})
        consumers = [refs[m['components'][key]['datasetId']] for key in declared['componentIds'] if m['components'][key].get('datasetId') in refs]
        return self.data.option_page(consumers, declared['field'], search, offset, limit)
