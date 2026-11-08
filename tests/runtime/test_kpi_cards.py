"""KPI card shapes mc10-mc16: validation, discovery and bound recomputation."""
import copy

import pytest

from dashboard_runtime.declarations import declaration_contract
from dashboard_runtime.demo import executive_document
from dashboard_runtime.kpi_cards import GUIDE, kpi_example
from dashboard_runtime.model import DashboardError, apply_operations
from dashboard_runtime.service import Service


def put(doc, key, config, binding=None):
    value = {'kind': 'legacy', 'family': 'kpi', 'title': config.get('label', key), 'sourceId': 'fixture', 'config': config}
    if binding:
        value['binding'] = binding
    return apply_operations(doc, [{'op': 'put_component', 'id': key, 'value': value}])


@pytest.mark.parametrize('code', sorted(GUIDE))
def test_every_guide_example_is_a_valid_card(code):
    doc = put(executive_document('kpi'), 'card', kpi_example(code))
    assert doc['manifest']['components']['card']['config']['type'] == code


@pytest.mark.parametrize('code,change', [
    ('mc10', {'stats': {'min': 1, 'p25': 5, 'median': 3, 'p75': 6, 'max': 9}}),
    ('mc11', {'percent': -5}),
    ('mc12', {'sparkData': [1, 2]}),
    ('mc13', {'target': 'high'}),
    ('mc14', {'priorValue': None}),
    ('mc15', {'items': []}),
    ('mc16', {'note': 'x' * 121}),
])
def test_malformed_shapes_are_rejected(code, change):
    with pytest.raises(DashboardError, match='KPI contract'):
        put(executive_document('kpi'), 'card', {**kpi_example(code), **change})


def test_discovery_explains_each_shape_instead_of_one_generic_example():
    summary = declaration_contract(summary=True)
    guide = {item['code']: item for item in summary['kpiGuide']}
    assert len(guide) == 16 and guide['mc13']['bindable'] and not guide['mc10']['bindable']
    selected = declaration_contract(legacy_code='mc14')['legacy']['kpiTypes']['mc14']
    assert {'currentValue', 'priorValue'} <= set(selected['required'])
    assert {'currentValue', 'priorValue'} <= set(selected['bindableTargets'])
    assert selected['exampleConfig']['type'] == 'mc14' and 'thresholdLabel' not in selected['exampleConfig']


@pytest.mark.parametrize('code', ['mc10', 'mc15'])
def test_snapshot_only_shapes_refuse_bindings(code):
    with pytest.raises(DashboardError) as error:
        put(executive_document('kpi'), 'card', kpi_example(code), {'datasetId': 'sales', 'measures': {'value': 'revenue'}})
    assert error.value.code == 'BINDING_TRANSFORM_REQUIRED'


def test_bound_shapes_recompute_numeric_geometry_under_filters(tmp_path):
    doc = executive_document('kpi')
    doc = put(doc, 'bullet', {'type': 'mc13', 'label': '收入对预算', 'value': '—', 'unit': '万元', 'subLabel': '预算'},
              {'datasetId': 'sales', 'measures': {'value': 'revenue', 'actual': 'revenue', 'target': 'budget', 'subVal': 'budget'}})
    doc = put(doc, 'compare', {'type': 'mc14', 'label': '收入对基期', 'value': '—', 'currentLabel': '本期', 'priorLabel': '基期'},
              {'datasetId': 'sales', 'measures': {'value': 'revenue', 'currentValue': 'revenue', 'priorValue': 'baseline-revenue'}})
    doc = put(doc, 'ring', {'type': 'mc11', 'label': '预算完成', 'value': '—', 'subLabel': '预算'},
              {'datasetId': 'sales', 'measures': {'value': 'revenue', 'percent': 'attainment', 'subVal': 'budget'}, 'scale': {'percent': 100}})
    doc = put(doc, 'bars', {'type': 'mc12', 'label': '旅客', 'value': '—'},
              {'datasetId': 'sales', 'measures': {'value': 'passengers'}, 'timeField': 'month'})
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.call('dashboard_create', {'dashboardId': 'kpi', 'document': doc})
    computed = service.call('dashboard_view', {'dashboardId': 'kpi', 'dataMode': 'local'})['document']['computed']['components']
    assert (computed['bullet']['actual'], computed['bullet']['target']) == (484, 525)
    assert '484' in computed['bullet']['value'] and '525' in computed['bullet']['subVal']
    assert (computed['compare']['currentValue'], computed['compare']['priorValue']) == (484, 390)
    assert round(computed['ring']['percent'], 2) == round(100 * 484 / 525, 2)
    assert computed['bars']['sparkMonths'] == ['2026-07-01', '2026-08-01', '2026-09-01']
    assert computed['bars']['sparkData'] == [117, 133, 126]
    filters = copy.deepcopy(service.store.get('kpi', hydrate=False)['manifest']['filters'])
    region = next(item for item in filters if item['id'] == 'region')
    region['values'] = ['华东基地']
    region['componentIds'] += ['bullet', 'compare', 'ring', 'bars']
    computed = service.call('dashboard_view', {'dashboardId': 'kpi', 'dataMode': 'local', 'filters': filters})['document']['computed']['components']
    assert (computed['bullet']['actual'], computed['bullet']['target']) == (278, 300)
    assert (computed['compare']['currentValue'], computed['compare']['priorValue']) == (278, 225)
    assert computed['bars']['sparkData'] == [72, 85, 80]
