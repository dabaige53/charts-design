import zipfile
import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess

import pytest

from dashboard_runtime.assets import FAVICON_LINK, render_html
from dashboard_runtime.demo import executive_document
from dashboard_runtime.deployment import _write_shards
from dashboard_runtime.model import MAX_BYTES, DashboardError, apply_operations, new_document
from dashboard_runtime.service import Service
from dashboard_runtime import columnar, deployment
from static_fixture import worker_query, worker_rows


# @wu-test type=integration | scope=静态部署入口 | protects=导出缺少运行资源和网页图标或改写已保存文档
def test_site_export_contains_runtime_and_preserves_document(tmp_path):
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.call('dashboard_create', {'dashboardId': 'demo', 'document': executive_document('demo')})
    before = service.store.get('demo', hydrate=False)
    result = service.call('dashboard_export_site', {'dashboardId': 'demo'})['export']
    with zipfile.ZipFile(result['path']) as archive:
        assert {'index.html', 'app.js', 'app.css', 'static-worker.js', 'document.json', 'export-manifest.json'} <= set(archive.namelist())
        assert FAVICON_LINK in archive.read('index.html').decode()
        assert archive.testzip() is None
        assert all(archive.read(name) == (Path(result['directory']) / name).read_bytes()
                   for name in archive.namelist())
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


# @wu-test type=boundary | scope=静态UI压缩缓存 | protects=并发重复压缩损坏缓存复用旧资源或把私有文档混入共享模板
def test_ui_archive_reuses_content_repairs_corruption_and_invalidates_changes(tmp_path, monkeypatch):
    site, cache = tmp_path / 'site', tmp_path / 'cache'
    site.mkdir()
    for name in deployment.UI_RESOURCES:
        (site / name).write_text(name * 1000)
    (site / 'document.json').write_text('{"private":"not a UI asset"}')
    writes, original = [], zipfile.ZipFile.write

    def recorded(output, path, *args, **kwargs):
        writes.append(Path(path).name)
        return original(output, path, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, 'write', recorded)
    archives = [tmp_path / f'{index}.zip' for index in range(4)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda path: deployment._prepare_archive(site, path, cache), archives))
    assert sorted(writes) == sorted(deployment.UI_RESOURCES)
    for path in archives:
        with zipfile.ZipFile(path) as archive:
            assert set(archive.namelist()) == set(deployment.UI_RESOURCES)
            assert archive.testzip() is None
            assert all(archive.read(name) == (site / name).read_bytes() for name in archive.namelist())

    damaged = next(cache.glob('*/ui.zip'))
    damaged.write_bytes(b'FAIL' + damaged.read_bytes()[4:])
    deployment._prepare_archive(site, archives[0], cache)
    assert len(writes) == 6
    with zipfile.ZipFile(archives[0]) as archive:
        assert archive.testzip() is None
    (site / 'app.js').write_text('new UI content without a build-id change')
    deployment._prepare_archive(site, archives[0], cache)
    assert len(writes) == 9
    with zipfile.ZipFile(archives[0]) as archive:
        assert archive.read('app.js') == (site / 'app.js').read_bytes()


# @wu-test type=boundary | scope=静态包原子交付 | protects=压缩失败留下可下载的半成品目录或不完整UI模板
def test_archive_failure_removes_staging_and_allows_retry(tmp_path, monkeypatch):
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.call('dashboard_create', {'dashboardId': 'demo', 'document': executive_document('demo')})

    def failure(*args, **kwargs):
        raise OSError('simulated archive failure')

    with monkeypatch.context() as patch:
        patch.setattr(zipfile.ZipFile, 'write', failure)
        with pytest.raises(OSError, match='simulated archive failure'):
            service.call('dashboard_export_site', {'dashboardId': 'demo', 'dataFormat': 'json'})
    assert not list((service.store.root / 'exports').iterdir())
    assert not list((service.store.runtime_root / 'ui-archive-cache').glob('*/ui.zip'))
    result = service.call('dashboard_export_site', {'dashboardId': 'demo', 'dataFormat': 'json'})['export']
    with zipfile.ZipFile(result['path']) as archive:
        assert archive.testzip() is None


def native_service(tmp_path):
    if not columnar.native_binary():
        pytest.skip('Parquet export requires the native exporter built by the native CI job')
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.call('dashboard_create', {'dashboardId': 'demo', 'document': executive_document('demo')})
    return service


# @wu-test type=integration | scope=独立分享的预生成筛选候选项 | protects=展开月份或区域时读取明细分片，或者高基数列表被截断和草稿值泄漏到保存版
def test_site_export_inlines_complete_small_filter_option_lists(tmp_path):
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    fields = {'month': {'type': 'date'}, 'region': {'type': 'string'}, 'route': {'type': 'number'}}
    meta = {'fields': fields, 'sourceId': 'fixture'}
    operations = [{'op': 'put_source', 'id': 'fixture', 'value': {'kind': 'fixture', 'name': 'Synthetic data'}}]
    for key, rows in (
        ('inbound', [{'month': '2026-01-01', 'region': '华东', 'route': i} for i in range(101)]),
        ('outbound', [{'month': '2026-02-01', 'region': '华北', 'route': 1}]),
    ):
        operations.extend([
            {'op': 'put_dataset', 'id': key, 'meta': meta, 'rows': rows},
            {'op': 'put_component', 'id': key, 'value': {'kind': 'table', 'title': key, 'datasetId': key}},
        ])
    operations.append({'op': 'set_filters', 'value': [
        {'id': field, 'field': field, 'label': field, 'op': 'in', 'componentIds': ['inbound', 'outbound'],
         'values': ['华东'] if field == 'region' else []}
        for field in fields
    ]})
    doc = apply_operations(new_document('filters', 'Shared filters'), operations)
    service.store.create('filters', 'Shared filters', doc)
    service.store.mutate('filters', 1, [
        {'op': 'put_dataset', 'id': 'outbound', 'meta': meta,
         'rows': [{'month': '2026-03-01', 'region': '华南', 'route': 1}]},
    ])

    exported = service.call('dashboard_export_site', {'dashboardId': 'filters', 'dataFormat': 'json'})['export']
    with zipfile.ZipFile(exported['path']) as archive:
        published = json.loads(archive.read('document.json'))
        files = {name: archive.read(name) for group in published['staticFiles'].values() for name in group}
    assert published['staticFilterOptions'] == {'region': ['华东', '华北'], 'month': ['2026-01-01', '2026-02-01']}
    months, regions, routes = worker_query(published, files, [
        {'filterId': 'month'}, {'filterId': 'region', 'search': '北'}, {'filterId': 'route', 'limit': 100},
    ])
    assert months['result']['values'] == ['2026-01-01', '2026-02-01'] and months['files'] == []
    assert regions['result']['values'] == ['华北'] and regions['files'] == []
    assert routes['result']['values'] == list(range(100))
    assert routes['result']['hasMore'] is True and routes['result']['totalValues'] == 101 and routes['files']


# @wu-test type=integration | scope=Parquet独立导出与缓存 | protects=导出未保存草稿丢行依赖外网或仅改标题就重新编码数据
def test_parquet_site_uses_saved_version_and_reuses_immutable_data(tmp_path, monkeypatch):
    service = native_service(tmp_path)
    saved = service.store.readable('demo')
    service.call('dashboard_patch', {'dashboardId': 'demo', 'expectedRevision': 1,
                 'operations': [{'op': 'set_title', 'value': 'Unsaved change'}]})
    args = {'dashboardId': 'demo', 'dataFormat': 'parquet'}
    exported = service.call('dashboard_export_site', args)['export']
    assert exported['manifest']['dataFormat'] == 'parquet'
    assert exported['manifest']['revision'] == 1
    assert all(not info['cacheHit'] for info in exported['manifest']['encodings'].values())
    with zipfile.ZipFile(exported['path']) as archive:
        doc = json.loads(archive.read('document.json'))
        assert doc['manifest']['title'] == saved['manifest']['title']
        assert doc['snapshot'] == {'datasets': {}}
        assert not {'annotations', 'sources', 'queries'} & set(doc['manifest'])
        for dataset, files in doc['staticFiles'].items():
            assert all(name.endswith('.parquet') for name in files)
            restored = [row for name in files for row in worker_rows(archive.read(name), name)]
            ref = saved['snapshot']['datasetRefs'].get(dataset)
            if ref:
                assert restored == list(service.store.data.iter_rows(ref))
            assert len(restored) == exported['manifest']['datasets'][dataset]

    def unexpected(*args, **kwargs):
        pytest.fail('An unchanged data version must reuse Parquet without native execution or Python row decoding')

    monkeypatch.setattr(columnar.subprocess, 'run', unexpected)
    monkeypatch.setattr(service.store.data, 'iter_rows', unexpected)
    repeated = service.call('dashboard_export_site', args)['export']
    assert all(info['cacheHit'] for info in repeated['manifest']['encodings'].values())
    assert service.store.revision('demo') == 2


# @wu-test type=boundary | scope=Parquet缓存完整性 | protects=同长度文件损坏仍作为原不可变版本导出或修复改变原数据
def test_same_size_corrupt_cache_is_rebuilt_from_sqlite(tmp_path):
    service = native_service(tmp_path)
    args = {'dashboardId': 'demo', 'dataFormat': 'parquet'}
    first = service.call('dashboard_export_site', args)['export']
    cache = service.store.runtime_root / 'parquet-cache' / columnar.FORMAT
    damaged = next(cache.glob('*/*.parquet'))
    original = damaged.read_bytes()
    damaged.write_bytes(b'FAIL' + original[4:])
    assert damaged.stat().st_size == len(original)
    second = service.call('dashboard_export_site', args)['export']
    assert damaged.read_bytes() == original
    assert first['manifest']['datasets'] == second['manifest']['datasets']
    assert any(not info['cacheHit'] for info in second['manifest']['encodings'].values())


# @wu-test type=boundary | scope=Parquet原生失败与兼容模式 | protects=显式Parquet失败静默退回JSON或留下成功缓存
def test_native_failure_is_explicit_and_legacy_export_stays_available(tmp_path, monkeypatch):
    service = native_service(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(columnar.subprocess, 'run', lambda *args, **kwargs:
                      subprocess.CompletedProcess(args, 1, stdout='', stderr='precision would be lost'))
        with pytest.raises(DashboardError, match='precision would be lost') as failure:
            service.call('dashboard_export_site', {'dashboardId': 'demo', 'dataFormat': 'parquet'})
        assert failure.value.code == 'PARQUET_EXPORT_FAILED'
        assert not list((service.store.runtime_root / 'parquet-cache').rglob('receipt.json'))
        assert not list((service.store.root / 'exports').iterdir())
    monkeypatch.setattr(columnar, 'native_binary', lambda: None)
    with pytest.raises(DashboardError) as failure:
        service.call('dashboard_export_site', {'dashboardId': 'demo', 'dataFormat': 'parquet'})
    assert failure.value.code == 'NATIVE_UNAVAILABLE'
    exported = service.call('dashboard_export_site', {'dashboardId': 'demo'})['export']
    assert exported['manifest']['dataFormat'] == 'json'
    assert list((Path(exported['directory']) / 'data').glob('*.json.gz'))
