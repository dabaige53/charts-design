import zipfile
import gzip
import json

from dashboard_runtime.assets import FAVICON_LINK, bundle_asset, render_html
from dashboard_runtime.demo import executive_document
from dashboard_runtime.deployment import _write_shards
from dashboard_runtime.model import MAX_BYTES
from dashboard_runtime.service import Service


# @wu-test type=integration | scope=静态部署入口 | protects=导出缺少运行资源或选项索引并改写已保存文档
def test_site_export_contains_runtime_and_preserves_document(tmp_path):
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.call('dashboard_create', {'dashboardId': 'demo', 'document': executive_document('demo')})
    before = service.store.get('demo', hydrate=False)
    result = service.call('dashboard_export_site', {'dashboardId': 'demo'})['export']
    with zipfile.ZipFile(result['path']) as archive:
        assert {'index.html', 'app.js', 'app.css', 'static-worker.js', 'document.json', 'export-manifest.json'} <= set(archive.namelist())
        assert FAVICON_LINK in archive.read('index.html').decode()
        assert archive.read('app.js') == bundle_asset('app.js', static=True)
        assert 'window.__chartsDocument=fetch(' in archive.read('index.html').decode()
        doc = json.loads(archive.read('document.json'))
        for selection in doc['manifest']['filters']:
            if selection['op'] != 'in':
                continue
            for component in selection['componentIds']:
                dataset = doc['manifest']['components'][component]['datasetId']
                options = json.loads(gzip.decompress(archive.read(doc['staticOptions'][dataset][selection['field']])))
                rows = [row for path in doc['staticFiles'][dataset]
                        for row in json.loads(gzip.decompress(archive.read(path)))]
                assert set(options) == {row.get(selection['field']) for row in rows}
    assert FAVICON_LINK in render_html()
    assert service.store.get('demo', hydrate=False) == before


# @wu-test type=boundary | scope=静态网页数据分片 | protects=宽字段数据超过16MiB时无法发布或分片丢失记录
def test_wide_rows_are_split_by_bytes_without_losing_order(tmp_path):
    (tmp_path / 'data').mkdir()
    rows = [{'id': i, 'text': '合' * 300_000} for i in range(20)]
    files, count = _write_shards(tmp_path, 'wide', iter(rows))
    assert count == len(rows)
    assert len(files) > 1
    restored = []
    for name in files:
        raw = gzip.decompress((tmp_path / name).read_bytes())
        assert len(raw) <= MAX_BYTES
        restored.extend(json.loads(raw))
    assert restored == rows
