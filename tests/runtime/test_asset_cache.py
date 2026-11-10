import pytest

from dashboard_runtime.model import DashboardError
from dashboard_runtime.demo import document
from dashboard_runtime.service import Service


# @wu-test type=behavior | scope=runtime_info | protects=读取版本时加载全部文档或返回过期版本
def test_runtime_info_reads_revision_without_loading_document(tmp_path, monkeypatch):
    service = Service(tmp_path)
    service.store.create('demo', 'Demo', document())
    monkeypatch.setattr(service.store, 'get', lambda *a, **k: pytest.fail('Revision check loaded the document'))
    assert service.call('runtime_info', {'dashboardId': 'demo'})['dashboardRevision'] == 1
    service.store.mutate('demo', 1, [{'op': 'set_title', 'value': 'Renamed'}])
    assert service.call('runtime_info', {'dashboardId': 'demo'})['dashboardRevision'] == 2
    assert service.store.list() == [{'id': 'demo', 'revision': 2, 'title': 'Renamed'}]
    with pytest.raises(DashboardError, match='Dashboard not found'):
        service.call('runtime_info', {'dashboardId': 'missing'})
