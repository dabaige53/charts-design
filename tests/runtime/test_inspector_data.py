"""The inspector reads bounded pages without changing the board."""
import pytest
from dashboard_runtime.demo import document
from dashboard_runtime.model import DashboardError
from dashboard_runtime.service import Service


# @wu-test type=integration | scope=数据检查器分页 | protects=筛选分页漏行或读取改变版本
def test_inspector_reads_all_filtered_pages_and_keeps_revision(tmp_path):
    service = Service(tmp_path)
    doc = document('inspector')
    doc['snapshot']['datasets']['sales'] = [
        {'month': '2026-08', 'region': 'North' if i % 2 == 0 else 'East',
         'revenue': i, 'passengers': 1, 'seats': 2}
        for i in range(2010)
    ]
    saved = service.store.create('inspector', 'Inspector', doc)
    filters = [{'id': 'region', 'field': 'region', 'label': '区域', 'op': 'in',
                'values': ['North'], 'componentIds': ['trend']}]
    request = {'dashboardId': 'inspector', 'componentId': 'trend',
               'expectedRevision': saved['revision'], 'filters': filters}
    first = service.call('component_data', request)
    last = service.call('component_data', {**request, 'offset': 1000})
    assert first['totalRows'] == last['totalRows'] == 1005
    assert len(first['rows']) == 1000 and len(last['rows']) == 5
    assert [r['revenue'] for r in first['rows'] + last['rows']] == list(range(0, 2010, 2))
    assert service.store.get('inspector')['revision'] == saved['revision']
    with pytest.raises(DashboardError):
        service.call('component_data', {**request, 'expectedRevision': 999})
    with pytest.raises(DashboardError):
        service.call('component_data', {**request, 'limit': 1001})
