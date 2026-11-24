"""Custom chart declarations share validation across editing and document creation."""
import copy

import pytest

from dashboard_runtime.model import DashboardError, apply_operations, new_document
from dashboard_runtime.service import Service


def custom_document(config):
    return apply_operations(new_document('custom', '自由图表'), [
        {'op': 'put_source', 'id': 'source', 'value': {'kind': 'fixture', 'name': '示例数据'}},
        {'op': 'put_component', 'id': 'chart', 'value': {
            'kind': 'legacy', 'family': 'chart', 'title': '自由图表', 'sourceId': 'source', 'config': config}},
    ])


# @wu-test type=integration | scope=自由图表存储 | protects=库外ECharts或HTML声明无法保存或配置在读取时丢失
@pytest.mark.parametrize('config', [
    {'code': 'radar-custom', 'renderer': 'echarts', 'echarts': {
        'radar': {'indicator': [{'name': '收入', 'max': 100}, {'name': '预算', 'max': 100}]},
        'series': [{'type': 'radar', 'data': [{'value': [80, 90]}]}]},
     'table': {'headers': ['收入', '预算'], 'rows': [[80, 90]]}},
    {'code': 'html-custom', 'renderer': 'html', 'html': '<div id="value"></div><script>document.getElementById("value").textContent=window.chartData.value</script>',
     'data': {'value': 80}},
])
def test_custom_renderer_roundtrip(tmp_path, config):
    service = Service(tmp_path)
    service.call('dashboard_create', {'dashboardId': 'custom', 'document': custom_document(config)})
    assert service.store.get('custom')['manifest']['components']['chart']['config'] == config


# @wu-test type=integration | scope=自由图表结构简图 | protects=省略简图的自由图表编辑丢失旧简图或遗漏失效标记
def test_custom_renderer_omitted_diagram_is_retained(tmp_path):
    raw = {'code': 'html-custom', 'renderer': 'html', 'html': '<p>Original</p>'}
    diagram = {
        'version': 1, 'viewBox': [0, 0, 100, 100],
        'svg': '<svg><rect x="10" y="20" width="30" height="40"/></svg>',
        'annotations': [{'id': 'box', 'name': 'Box', 'anchor': [10, 20], 'label': [20, 10]}],
    }
    doc = custom_document({**raw, 'presentation': {'structureDiagram': diagram}})
    component = doc['manifest']['components']['chart']
    saved = component['config']['presentation']['structureDiagram']
    assert saved['status'] == 'ready'

    unchanged = apply_operations(doc, [
        {'op': 'put_component', 'id': 'chart', 'value': {**component, 'config': raw}},
    ])
    assert unchanged['manifest']['components']['chart']['config'] == component['config']

    edited = {**raw, 'html': '<p>Edited</p>'}
    changed = apply_operations(unchanged, [
        {'op': 'put_component', 'id': 'chart', 'value': {**component, 'config': edited}},
    ])
    service = Service(tmp_path)
    service.call('dashboard_create', {'dashboardId': 'custom', 'document': changed})
    assert service.store.get('custom')['manifest']['components']['chart']['config'] == {
        **edited, 'presentation': {'structureDiagram': {**saved, 'status': 'stale'}},
    }


# @wu-test type=boundary | scope=图表保存入口 | protects=未知预设或不完整自由渲染声明被编辑或整份文档创建保存
@pytest.mark.parametrize('invalid', [
    {'code': 'not-registered', 'data': {'values': [1]}},
    {'code': 'custom', 'renderer': 'echarts', 'echarts': {}},
    {'code': 'custom', 'renderer': 'html', 'html': 1},
    {'code': 'custom', 'renderer': 'html', 'html': '<p>1</p>', 'table': {'headers': ['值'], 'rows': [[1, 2]]}},
])
def test_invalid_renderer_rejected_by_edit_and_create(tmp_path, invalid):
    with pytest.raises(DashboardError) as edit_error:
        custom_document(invalid)
    assert edit_error.value.code == 'CHART_RENDERER_INVALID'
    doc = custom_document({'code': 'custom', 'renderer': 'html', 'html': '<p>1</p>'})
    doc['manifest']['components']['chart']['config'] = copy.deepcopy(invalid)
    with pytest.raises(DashboardError) as create_error:
        Service(tmp_path).call('dashboard_create', {'dashboardId': 'custom', 'document': doc})
    assert create_error.value.code == 'CHART_RENDERER_INVALID'
