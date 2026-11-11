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


# @wu-test type=integration | scope=KPI指南示例 | protects=对外示例不能生成对应类型指标卡
@pytest.mark.parametrize('code', sorted(GUIDE))
def test_every_guide_example_is_a_valid_card(code):
    doc = put(executive_document('kpi'), 'card', kpi_example(code))
    assert doc['manifest']['components']['card']['config']['type'] == code


# @wu-test type=boundary | scope=KPI结构校验 | protects=分位倒序或负比例等非法配置被接受
@pytest.mark.parametrize('code,change', [
    ('mc10', {'stats': {'min': 1, 'p25': 5, 'median': 3, 'p75': 6, 'max': 9}}),
    ('mc11', {'percent': -5}),
    ('mc12', {'sparkData': [1, 2]}),
    ('mc13', {'target': 'high'}),
    ('mc14', {'priorValue': None}),
    ('mc15', {'items': []}),
])
def test_malformed_shapes_are_rejected(code, change):
    with pytest.raises(DashboardError, match='KPI contract'):
        put(executive_document('kpi'), 'card', {**kpi_example(code), **change})


# @wu-test type=boundary | scope=KPI创建与编辑 | protects=卡片描述通过组件配置或整份文档导入绕过禁止规则
@pytest.mark.parametrize('location,field', [('component', 'subtitle'), ('config', 'note'), ('presentation', 'description')])
def test_kpi_descriptions_rejected_at_authoring_entries(tmp_path, location, field):
    doc = executive_document('kpi')
    component = doc['manifest']['components']['total']
    target = component if location == 'component' else component.setdefault(location, {})
    target[field] = '需要放入指标详情的解释'
    with pytest.raises(DashboardError) as edit_error:
        apply_operations(doc, [{'op': 'put_component', 'id': 'total', 'value': component}])
    assert edit_error.value.code == 'KPI_DESCRIPTION_NOT_ALLOWED'
    with pytest.raises(DashboardError) as import_error:
        Service(tmp_path).call('dashboard_create', {'dashboardId': 'kpi', 'document': doc})
    assert import_error.value.code == 'KPI_DESCRIPTION_NOT_ALLOWED'


# @wu-test type=integration | scope=KPI发现与绑定 | protects=选型返回的比较卡示例无法创建或按筛选重算
def test_discovery_example_creates_a_comparison_card_and_recomputes(tmp_path):
    selected = declaration_contract(legacy_code='mc14')['legacy']['kpiTypes']['mc14']
    config = selected['exampleConfig']
    doc = put(executive_document('kpi'), 'comparison', config,
              {'datasetId': 'sales', 'measures': {'value': 'revenue', 'currentValue': 'revenue', 'priorValue': 'baseline-revenue'}})
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.call('dashboard_create', {'dashboardId': 'kpi', 'document': doc})
    before = service.call('dashboard_view', {'dashboardId': 'kpi', 'componentIds': ['comparison']})['document']['computed']['components']['comparison']
    filters = copy.deepcopy(doc['manifest']['filters'])
    region = next(item for item in filters if item['id'] == 'region')
    region['values'] = ['华东基地']
    region['componentIds'].append('comparison')
    after = service.call('dashboard_view', {'dashboardId': 'kpi', 'componentIds': ['comparison'], 'filters': filters})['document']['computed']['components']['comparison']
    assert before['type'] == after['type'] == 'mc14'
    assert (before['currentValue'], before['priorValue']) == (484, 390)
    assert (after['currentValue'], after['priorValue']) == (278, 225)


# @wu-test type=boundary | scope=KPI绑定 | protects=仅快照类型被错误绑定数据
@pytest.mark.parametrize('code', ['mc10', 'mc15'])
def test_snapshot_only_shapes_refuse_bindings(code):
    with pytest.raises(DashboardError) as error:
        put(executive_document('kpi'), 'card', kpi_example(code), {'datasetId': 'sales', 'measures': {'value': 'revenue'}})
    assert error.value.code == 'BINDING_TRANSFORM_REQUIRED'


# @wu-test type=integration | scope=KPI筛选重算 | protects=筛选后几何字段或文本未按真实数据重算
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
