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


# @wu-test type=integration | scope=全部图表 MCP 声明示例 | protects=选择任一已注册图表后得到缺字段或不同图形的示例
def test_every_registered_chart_has_an_own_code_runnable_example(reference):
    assert len(reference['legacy']['chartCodes']) == 40
    for code in reference['legacy']['chartCodes']:
        selected = declaration_contract(legacy_code=code)
        example = selected['legacy']['chartCodes'][code]['example']
        assert example['status'] == 'fixture'
        assert example == selected['legacy']['families']['chart']['example']
        document = apply_operations(new_document('example', code), example['operations'])
        assert document['manifest']['components'][example['componentId']]['config']['code'] == code


# @wu-test type=integration | scope=批量声明发现 | protects=多个声明查询重复公共合同或示例组件 ID 冲突使图表被覆盖
def test_bounded_batch_shares_common_schemas_and_composes_examples(tmp_path):
    from dashboard_runtime.service import Service
    selected = ['c02', 't01', 'mc03', 'mc14']
    result = Service(tmp_path).call('chart_declarations', {'codes': selected})
    assert list(result['legacy']['chartCodes']) == ['c02', 't01']
    assert list(result['legacy']['kpiTypes']) == ['mc03', 'mc14']
    assert [item['code'] for item in result['selections']] == selected
    operations, ids = [], set()
    for entries in (result['legacy']['chartCodes'], result['legacy']['kpiTypes']):
        for entry in entries.values():
            operations.extend(entry['example']['operations'])
            ids.add(entry['example']['componentId'])
    document = apply_operations(new_document('example', 'Batched declarations'), operations)
    assert len(ids) == 4 and set(document['manifest']['components']) == ids
    single_bytes = sum(len(json.dumps(declaration_contract(legacy_code=code))) for code in selected)
    assert len(json.dumps(result)) < single_bytes / 2


# @wu-test type=boundary | scope=批量声明输入 | protects=空批次超大批次重复选择或混合参数被接受
@pytest.mark.parametrize('arguments', [
    {'legacy_codes': []}, {'legacy_codes': ['c01'] * 2}, {'legacy_codes': ['c01'] * 9},
    {'legacy_codes': ['unknown']}, {'legacy_codes': 'c01'}, {'legacy_codes': [None]},
    {'legacy_code': 'c01', 'legacy_codes': ['c02']}, {'legacy_codes': ['c01'], 'summary': True},
])
def test_invalid_batches_fail_explicitly(arguments):
    with pytest.raises(DashboardError):
        declaration_contract(**arguments)


# @wu-test type=performance | scope=声明缓存隔离与更新 | protects=每次发现重新执行注册模块或原资源更新后永久保留过时声明
def test_discovery_reuses_registry_and_invalidates_replaced_catalog(tmp_path, monkeypatch):
    import shutil
    for path in (declarations.LEGACY_SCHEMA_SOURCE, declarations.LEGACY_CATALOG_SOURCE,
                 declarations.LEGACY_ROOT / 'scripts/core/chart_catalog.py'):
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, destination)
    monkeypatch.setattr(declarations, 'REPO', tmp_path)
    first = declaration_contract(legacy_code='c02')
    def no_reload(*args, **kwargs):
        raise AssertionError('unchanged declaration registry re-executed')
    monkeypatch.setattr(declarations.importlib.util, 'spec_from_file_location', no_reload)
    first['legacy']['chartCodes']['c02']['example']['operations'].clear()
    assert declaration_contract(legacy_code='c02')['legacy']['chartCodes']['c02']['example']['operations']
    assert declaration_contract(legacy_code='t01')['selection']['code'] == 't01'
    path = tmp_path / declarations.LEGACY_CATALOG_SOURCE
    catalog = json.loads(path.read_text())
    next(item for item in catalog if item['id'] == 'c02')['nameZh'] = '更新后的条形图名称'
    path.write_text(json.dumps(catalog, ensure_ascii=False))
    assert declaration_contract(legacy_code='c02')['legacy']['chartCodes']['c02']['catalogEntry']['nameZh'] == '更新后的条形图名称'


# @wu-test type=integration | scope=MCP公开发现与批量声明 | protects=公开工具缺参数或推荐引导依赖不可发现入口
def test_recommendation_and_batched_declarations_over_stdio(tmp_path):
    pytest.importorskip('mcp')
    import asyncio
    import os
    import sys
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.types import TextResourceContents
    from pydantic import AnyUrl

    async def check():
        params = StdioServerParameters(command=sys.executable,
            args=['-m', 'dashboard_runtime', '--root', str(tmp_path / 'runtime'), 'mcp'],
            env={**os.environ, 'PYTHONPATH': str(ROOT)})
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            assert tools['chart_declarations'].inputSchema['properties']['codes']['maxItems'] == 8
            assert 'requiresFilterBinding' in tools['chart_recommend'].inputSchema['properties']
            result = await session.call_tool('chart_recommend', {'intent': 'composition', 'requiresFilterBinding': True})
            assert not result.isError and result.structuredContent is not None
            assert all(item['filterBinding'] == 'supported' for item in result.structuredContent['charts'])
            selected = await session.call_tool('chart_declarations', {'codes': ['c02', 't01', 'mc03']})
            assert not selected.isError and selected.structuredContent is not None
            reference = selected.structuredContent
            if 'transport' in reference:
                resource = await session.read_resource(AnyUrl(reference['transport']['resourceUri']))
                assert isinstance(resource.contents[0], TextResourceContents)
                reference = json.loads(resource.contents[0].text)
            assert len(reference['selections']) == 3
            invalid = await session.call_tool('chart_declarations', {'code': 'c02', 'codes': ['t01']})
            assert invalid.isError
            index = await session.read_resource(AnyUrl('charts://examples'))
            assert isinstance(index.contents[0], TextResourceContents)
            workflow = json.loads(index.contents[0].text)['workflow']
            assert any(item.startswith('charts://examples/') for item in workflow)
            assert any(item.startswith('charts://layouts') for item in workflow)
            assert not any(item.startswith(('generation_examples(', 'layout_templates(')) for item in workflow)
    asyncio.run(check())


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
