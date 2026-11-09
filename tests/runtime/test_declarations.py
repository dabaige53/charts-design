"""Declaration discovery must reflect accepted runtime data, not renderer guesses."""
import json
from pathlib import Path

import pytest

from dashboard_runtime import declarations
from dashboard_runtime.declarations import declaration_contract
from dashboard_runtime.model import DashboardError, apply_operations, new_document, validate

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def reference():
    return declaration_contract()


# @wu-test type=integration | scope=组件声明示例 | protects=对外示例不能生成对应组件 | debt=D1
@pytest.mark.parametrize('family', ['chart', 'kpi', 'table'])
def test_legacy_family_examples_validate(reference, family):
    if not reference['legacy']['available']:
        pytest.skip('Original repository is required for legacy validation')
    example = reference['legacy']['families'][family]['example']
    document = apply_operations(new_document('example', family), example['operations'])
    assert document['manifest']['components'][example['componentId']]['family'] == family


# @wu-test type=integration | scope=KPI声明示例 | protects=指定KPI返回错误类型或无效示例 | debt=D1
@pytest.mark.parametrize('code', [f'mc{i:02d}' for i in range(1, 17)])
def test_each_legacy_kpi_selected_example_validates(code):
    if not declaration_contract(summary=True)['legacy']['available']:
        pytest.skip('Original repository is required for legacy validation')
    reference = declaration_contract(legacy_code=code)
    assert reference['selection'] == {'code': code, 'family': 'kpi'}
    assert list(reference['legacy']['kpiTypes']) == [code]
    example = reference['legacy']['families']['kpi']['example']
    document = apply_operations(new_document('example', code), example['operations'])
    assert document['manifest']['components'][example['componentId']]['config']['type'] == code


# @wu-test type=behavior | scope=图表发现 | protects=目录条目被误当可用图表 | debt=D1,D6
def test_legacy_registry_and_catalog_are_distinguished(reference):
    legacy = reference['legacy']
    if not legacy['available']:
        pytest.skip('Original repository is required for registry assertions')
    registry = declarations._registry()
    assert registry is not None
    catalog = json.loads((ROOT / declarations.LEGACY_CATALOG_SOURCE).read_text())
    assert [{key: value for key, value in entry.items() if key != 'filterBinding'} for entry in legacy['catalogEntries']] == catalog
    assert all('filterBinding' in entry for entry in legacy['catalogEntries'])
    assert legacy['counts'] == {
        'catalogEntries': 57, 'registeredChartCodes': 40, 'registeredKpiTypes': 16}
    assert set(legacy['chartCodes']) == set(registry.CHART_CODES)
    assert set(legacy['kpiTypes']) == set(registry.KPI_TYPES)
    assert 'r05' in legacy['chartCodes']
    assert legacy['chartCodes']['r05']['catalogEntry'] is None
    assert 'tb01' not in legacy['chartCodes']
    assert 'mc01' not in legacy['chartCodes']
    for code, entry in legacy['chartCodes'].items():
        assert entry['completeJsonSchema'] is False
        assert entry['schemaSource'] == declarations.LEGACY_SCHEMA_SOURCE
        assert entry['presentationRequirements'] == json.loads(json.dumps(registry.CHART_PRESENTATION_CONTRACTS[code]))
        assert entry['tableHeaderCount'] == registry.CHART_TABLE_HEADER_COUNTS[code]
        assert entry['registeredArrayFields'] == [
            {'field': name, 'items': kind, 'minItems': 1}
            for name, kind in registry.CHART_ARRAY_FIELDS.get(code, ())]


# @wu-test type=boundary | scope=图表声明 | protects=发现接口提供不支持原生图表
def test_index_only_advertises_original_charts(reference):
    index = declaration_contract(summary=True)
    assert index['summary'] is True
    assert 'nativeCharts' not in index and 'nativeCharts' not in reference
    assert len(index['legacy']['chartCodes']) == 40
    assert 'chartType' not in reference['common']['componentSchema']['properties']
    with pytest.raises(DashboardError):
        declaration_contract(chart_type='bar')


# @wu-test type=integration | scope=图表示例选择 | protects=请求t06却得到其他图表示例 | debt=D1
def test_legacy_selection_never_substitutes_a_different_code_example():
    if not declaration_contract(summary=True)['legacy']['available']:
        pytest.skip('Original repository is required for legacy selection')
    selected = declaration_contract(legacy_code='t06')
    assert list(selected['legacy']['chartCodes']) == ['t06']
    family = selected['legacy']['families']['chart']
    example = family['example']
    document = apply_operations(new_document('example', 't06'), example['operations'])
    assert document['manifest']['components'][example['componentId']]['config']['code'] == 't06'
    assert family['componentSchema']['properties']['config']['properties']['code'] == {'const': 't06'}
    assert selected['legacy']['chartCodes']['t06']['filterBinding']['supported'] is True


# @wu-test type=boundary | scope=图表声明选择 | protects=无效类型或冲突选择被接受
@pytest.mark.parametrize('arguments', [
    {'chart_type': 'unknown'}, {'chart_type': {}}, {'legacy_code': []}, {'legacy_code': 'unknown'},
    {'chart_type': 'bar', 'legacy_code': 'c01'}, {'chart_type': 'bar', 'summary': True},
])
def test_invalid_selections_fail_explicitly(arguments):
    with pytest.raises(DashboardError):
        declaration_contract(**arguments)


# @wu-test type=behavior | scope=声明数据 | protects=调用方修改结果污染后续发现
def test_discovery_is_detached_json_data(reference):
    encoded = json.dumps(reference, allow_nan=False)
    assert json.loads(encoded) == reference
    changed = declaration_contract(legacy_code='c01')
    changed['legacy']['families']['chart']['example']['operations'].clear()
    assert declaration_contract(legacy_code='c01')['legacy']['families']['chart']['example']['operations']


# @wu-test type=boundary | scope=原组件缺失 | protects=缺原资源时错误提供其他图表系统
def test_missing_original_sources_has_no_alternative_chart_system(tmp_path, monkeypatch):
    monkeypatch.setattr(declarations, 'REPO', tmp_path)
    reference = declaration_contract()
    assert reference['legacy']['available'] is False
    assert reference['legacy']['counts'] == {
        'catalogEntries': 0, 'registeredChartCodes': 0, 'registeredKpiTypes': 0}
    assert 'nativeCharts' not in reference
    with pytest.raises(DashboardError) as failure:
        declaration_contract(legacy_code='c01')
    assert failure.value.code == 'LEGACY_UNAVAILABLE'






# @wu-test type=integration | scope=声明schema | protects=对外示例不符合公开schema | debt=D1
def test_advertised_shape_schemas_accept_their_examples(reference):
    jsonschema = pytest.importorskip('jsonschema')
    for family in reference['legacy']['families'].values():
        schema = family['componentSchema']
        jsonschema.Draft202012Validator.check_schema(schema)
        component = next(op['value'] for op in family['example']['operations'] if op['op'] == 'put_component')
        jsonschema.validate(component, schema)
    for name in ('sourceSchema', 'metricSchema', 'datasetMetaSchema', 'componentSchema'):
        jsonschema.Draft202012Validator.check_schema(reference['common'][name])


# @wu-test type=integration | scope=高级图表示例 | protects=t06或m01示例不能按指定代码生成
@pytest.mark.parametrize('code', ['t06', 'm01'])
def test_advanced_examples_are_legal_own_code_configs(code):
    selected = declaration_contract(legacy_code=code)
    example = selected['legacy']['families']['chart']['example']
    doc = apply_operations(new_document('example', code), example['operations'])
    assert doc['manifest']['components'][example['componentId']]['config']['code'] == code
    assert validate(doc) is doc
    capability = selected['legacy']['chartCodes'][code]['filterBinding']
    assert capability['snapshotOnly'] is (code == 'm01')




# @wu-test type=boundary | scope=ECharts配置 | protects=原生配置丢失或非对象配置被接受
def test_native_echarts_options_are_discoverable_and_preserved():
    selected = declaration_contract(legacy_code='c01')
    chart = selected['legacy']['families']['chart']
    schema = chart['componentSchema']['properties']['config']['properties']['echarts']
    assert schema['type'] == 'object' and schema['additionalProperties'] is True
    operations = chart['example']['operations']
    component = next(op['value'] for op in operations if op['op'] == 'put_component')
    override = {'series': [{'label': {'show': False}}], 'brush': {'toolbox': ['rect']},
                'futureEChartsField': {'values': [1, 2, 3]}}
    component['config']['echarts'] = override
    document = apply_operations(new_document('options', 'Native options'), operations)
    assert document['manifest']['components'][chart['example']['componentId']]['config']['echarts'] == override
    component['config']['echarts'] = 'function () {}'
    with pytest.raises(DashboardError, match='config.echarts must be an ECharts option object'):
        apply_operations(new_document('options', 'Native options'), operations)
