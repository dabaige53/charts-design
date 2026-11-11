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
