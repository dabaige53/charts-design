"""Explicit data bindings for original components; no inferred or synthetic metrics."""
from .model import require, field

SERIES_TARGETS = {
    'c01': ('categories', ('values',)), 'c02': ('categories', ('values',)),
    'c03': ('clusters', ('budget', 'actual')), 'c04': ('fleets', ('deviations',)),
    'c06': ('hubs', ('offSeason', 'peakSeason')),
    'c07': ('clusters', ('base2024', 'curr2025')),
    'c08': ('categories', ('domestic', 'intl')),
    'd01': ('brackets', ('counts',)), 't01': ('months', ('rpk',)),
    't02': ('quarters', ('actual', 'forecast')),
    't04': ('quarters', ('premium', 'economy', 'cargo', 'ancillary')),
    'fn02': ('quarters', ('revenue', 'cost')),
    'fn03': ('variables', ('negative', 'positive')),
    't06': ('categories', ('revenue', 'yieldGrowth')),
}
KPI_TARGETS = {'value', 'leftVal', 'rightVal', 'subVal', 'yoy', 'mom', 'percent'}

def validate_binding(doc, component):
    b = component.get('binding')
    require(isinstance(b, dict), 'binding must be an object')
    ds = b.get('datasetId')
    m = doc['manifest']
    require(ds in m['datasets'], 'Binding dataset not found')
    require(component.get('datasetId') == ds, 'Binding and component datasets must match')
    family, config = component.get('family', 'chart'), component['config']
    measures = b.get('measures', {})
    require(isinstance(measures, dict), 'Binding measures must map target names to metric IDs')
    for mid in measures.values():
        require(isinstance(mid, str) and mid in m['metrics'], 'Binding references an unknown metric')
        require(m['metrics'][mid]['datasetId'] == ds, 'Binding metrics must share its dataset')
    scale = b.get('scale', {})
    require(isinstance(scale, dict) and set(scale) <= set(measures), 'Binding scale targets must be measures')
    require(all(type(v) in (int, float) and v > 0 for v in scale.values()), 'Binding scales must be positive finite numbers')
    if family == 'chart':
        target = SERIES_TARGETS.get(config.get('code'))
        require(target is not None, 'This original shape needs a dedicated reviewed data transform', 'BINDING_TRANSFORM_REQUIRED')
        require(b.get('categoryTarget') == target[0], 'Wrong category target for the original chart')
        require(set(measures) == set(target[1]), 'Bind every required series; stale snapshot series are not allowed')
        field(m['datasets'][ds], b.get('categoryField'))
        if b.get('timeGrain'):
            require(m['datasets'][ds]['fields'][b['categoryField']]['type'] == 'date', 'Monthly/quarterly binding requires a date field')
    elif family == 'kpi':
        require(set(measures) <= KPI_TARGETS, 'Unknown KPI binding target')
        required = {'leftVal', 'rightVal'} if config.get('type') == 'mc06' else {'value'}
        require(required <= set(measures), 'Bind each KPI headline value')
        require(config.get('type', 'mc01') not in ('mc07', 'mc08', 'mc09'), 'Ranking/threshold/breakdown KPI requires a dedicated reviewed transform', 'BINDING_TRANSFORM_REQUIRED')
        if config.get('type') == 'mc03':
            field(m['datasets'][ds], b.get('timeField'))
    elif family == 'table':
        require(not measures, 'Table bindings consume rows, not aggregate measures')
        for col in config['columns']:
            field(m['datasets'][ds], col['key'])
    return b
