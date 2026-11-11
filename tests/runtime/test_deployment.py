import zipfile

from dashboard_runtime.demo import executive_document
from dashboard_runtime.service import Service


# @wu-test type=integration | scope=静态部署入口 | protects=导出缺少运行资源或改写已保存文档
def test_site_export_contains_runtime_and_preserves_document(tmp_path):
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.call('dashboard_create', {'dashboardId': 'demo', 'document': executive_document('demo')})
    before = service.store.get('demo', hydrate=False)
    result = service.call('dashboard_export_site', {'dashboardId': 'demo'})['export']
    with zipfile.ZipFile(result['path']) as archive:
        assert {'index.html', 'app.js', 'app.css', 'static-worker.js', 'document.json', 'export-manifest.json'} <= set(archive.namelist())
    assert service.store.get('demo', hydrate=False) == before
