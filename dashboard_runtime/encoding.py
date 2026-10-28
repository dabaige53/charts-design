"""Declarative dynamic bindings for existing scatter and comparison components."""
from .model import require, field


def validate_encoding(component):
    e = component['config']['encoding']
    require(isinstance(e, dict), 'encoding must be an object')
    require(set(e) <= {'orientation', 'stacked', 'symbolSize', 'colors', 'tooltip', 'colorBy', 'sizeBy', 'showLabels'}, 'Unknown encoding option; consult chart_declarations')
    require(component['config'].get('code') in ('r02', 'c03'), 'encoding supports r02 and c03')
    require(component.get('binding'), 'encoding requires a dataset binding')
    require(e.get('orientation', 'vertical') in ('horizontal', 'vertical'), 'Invalid orientation')
    require(type(e.get('stacked', False)) is bool, 'stacked must be boolean')
    require(type(e.get('symbolSize', 18)) in (int, float) and 1 <= e.get('symbolSize', 18) <= 100, 'symbolSize must be 1–100')
    require(isinstance(e.get('tooltip', []), list) and all(isinstance(k, str) for k in e.get('tooltip', [])), 'tooltip must be an array of bound keys')
    require(type(e.get('showLabels', False)) is bool, 'showLabels must be boolean')
    require(isinstance(e.get('colors', {}), dict) and all(isinstance(v, str) for v in e.get('colors', {}).values()), 'colors maps categories to CSS colors')


def validate_encoding_binding(doc, c):
    b, e = c['binding'], c['config']['encoding']
    meta = doc['manifest']['datasets'][b['datasetId']]
    require(not b.get('scale'), 'Dynamic encoding uses metric units directly; remove binding.scale')
    field(meta, b.get('categoryField'))
    expected = {'x', 'y'} if c['config']['code'] == 'r02' else {'value'}
    require(expected <= set(b['measures']), 'encoding requires measures: ' + ', '.join(sorted(expected)))
    if c['config']['code'] == 'c03':
        field(meta, b.get('seriesField'))
        require(b['categoryField'] != b['seriesField'], 'Category and series must be different fields')
        require(not e.get('colorBy') and not e.get('sizeBy'), 'c03 uses series colors and does not support sizeBy')
        if e.get('stacked'):
            require(doc['manifest']['metrics'][b['measures']['value']]['aggregation'] in ('sum', 'count'), 'Stacked bars require an additive sum/count metric')
    require(not b.get('timeGrain'), 'encoding does not yet support timeGrain; use date categories')
    require(isinstance(b.get('attributes', {}), dict), 'attributes must map names to field aggregation declarations')
    for key, spec in b.get('attributes', {}).items():
        require(key not in b['measures'] and isinstance(spec, dict), 'Attributes must have distinct names')
        field(meta, spec.get('field'))
        require(spec.get('aggregation') in ('unique', 'min', 'max'), 'Attribute aggregation must be unique/min/max')
        if spec['aggregation'] != 'unique':
            require(meta['fields'][spec['field']]['type'] == 'number', 'min/max attributes require numeric fields')
    available = set(b['measures']) | set(b.get('attributes', {}))
    require(all(k in available for k in e.get('tooltip', [])), 'Tooltip keys must be bound measures or attributes')
    require(not e.get('colorBy') or e['colorBy'] in available, 'colorBy must be a bound key')
    require(not e.get('sizeBy') or e['sizeBy'] in b['measures'], 'sizeBy must be a bound measure')
    if b.get('orderBy'):
        require(b['orderBy'].get('target') in b['measures'] and b['orderBy'].get('direction') in ('asc', 'desc'), 'Invalid binding orderBy')


def resolve_encoding(view, ref, manifest, component, active):
    b = component['binding']
    definitions = {key: manifest['metrics'][mid] for key, mid in b['measures'].items()}
    definitions.update(b.get('attributes', {}))
    groups = [b['categoryField']] + ([b['seriesField']] if component['config']['code'] == 'c03' else [])
    rows, _ = view.aggregate(ref, definitions, active, groups)
    return [{'category': r[groups[0]], 'series': r[groups[1]] if len(groups) > 1 else None,
             'values': {key: r[key] for key in definitions}} for r in rows]
