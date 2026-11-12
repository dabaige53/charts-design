from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dashboard_runtime.cos_view import authorized_files, browser_data, browser_version, web_document
from dashboard_runtime.model import DashboardError


def document():
    return {'id': 'board', 'revision': 3,
            'manifest': {'components': {'a': {'datasetId': 'sales'}, 'b': {'datasetId': 'copy'}},
                         'sources': {'private': {}}, 'annotations': []},
            'snapshot': {'datasets': {}, 'datasetRefs': {'sales': {'version': 'v1'}, 'copy': {'version': 'v1'}}},
            'computed': {'components': {'a': {'value': 42}}, 'tables': {}}}


# @wu-test type=performance | scope=web_document deferred data | protects=首屏查询数据对象目录导致保存结果不能立即返回
def test_saved_view_defers_descriptors_and_preserves_computed_content():
    doc = document()
    assets = Mock()
    store = SimpleNamespace(assets=assets)
    result = web_document(store, doc, lambda obj, name: f'/{obj}/{name}', editable=True,
                          data_url='/content/board/3')
    assets.call.assert_not_called()
    assert result['computed'] == doc['computed']
    assert result['browserDataUrl'] == '/content/board/3'
    assert 'staticFiles' not in result
    assert 'browserDataUrl' not in doc
    assert result['manifest']['sources'] == doc['manifest']['sources']


# @wu-test type=performance | scope=browser_data | protects=相同数据版本多次查询对象且延后目录与旧分享目录不一致
def test_directory_deduplicates_versions_and_matches_eager_shares():
    doc = document()
    assets = Mock()
    assets.call.return_value = {'id': 'obj', 'descriptor': {
        'shards': ['rows.gz'], 'options': {'month': 'months.gz'},
        'partitionIndex': {'field': 'month', 'entries': [{'value': '2026-10', 'files': ['rows.gz']}]}}}
    store = SimpleNamespace(assets=assets)
    url = lambda obj, name: f'/{obj}/{name}'
    result = browser_data(store, doc, url)
    assets.call.assert_called_once_with('object_get', version='v1')
    assert result['staticFiles'] == {'sales': ['/obj/rows.gz'], 'copy': ['/obj/rows.gz']}
    assert result['staticPartitionIndexes']['sales']['entries'][0]['files'] == ['/obj/rows.gz']
    eager = web_document(store, doc, url)
    assert all(eager[key] == value for key, value in result.items())
    assert 'sources' not in eager['manifest']


# @wu-test type=boundary | scope=browser_version | protects=目录读取泄露草稿或每个编辑文件重复读取完整文档
def test_browser_version_reads_once_and_rejects_stale_read_only_versions():
    doc = document()
    store = SimpleNamespace(get=Mock(return_value=doc), readable=Mock(return_value=doc))
    assert browser_version(store, 'board', 3, True) is doc
    store.get.assert_called_once_with('board', hydrate=False)
    store.readable.assert_not_called()
    assert browser_version(store, 'board', 3, False) is doc
    with pytest.raises(DashboardError) as error:
        browser_version(store, 'board', 2, False)
    assert error.value.code == 'REVISION_CONFLICT'
    assert store.get.call_count == 1


# @wu-test type=integration | scope=browser_version saved edit view | protects=草稿比保存版本更新时编辑页错误读取草稿数据
def test_editor_keeps_requested_saved_version_when_draft_is_newer(tmp_path):
    from dashboard_runtime.service import Service
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.call('dashboard_create', {'dashboardId': 'board', 'title': 'Saved'})
    service.call('dashboard_patch', {'dashboardId': 'board', 'expectedRevision': 1,
                                    'operations': [{'op': 'set_title', 'value': 'Draft'}]})
    assert browser_version(service.store, 'board', 1, True)['manifest']['title'] == 'Saved'
    assert browser_version(service.store, 'board', 2, True)['manifest']['title'] == 'Draft'

# @wu-test type=performance | scope=immutable file cache | protects=并发重复读取COS或无界保留压缩资源
def test_immutable_bytes_coalesce_and_evict_by_capacity():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from dashboard_runtime.cloud_assets import ImmutableFileCache
    cache = ImmutableFileCache(max_bytes=6)
    started, release = Event(), Event()
    calls = []
    def read():
        calls.append('A')
        started.set()
        assert release.wait(3)
        return b'aaa'
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(cache.get, 'A', read)
        assert started.wait(3)
        second = pool.submit(cache.get, 'A', read)
        release.set()
        assert first.result() == second.result() == b'aaa'
    assert calls == ['A']
    assert cache.get('B', lambda: b'bbb') == b'bbb'
    assert cache.get('C', lambda: b'ccc') == b'ccc'
    assert cache.get('A', lambda: b'new') == b'new'
    assert cache.bytes <= 6


# @wu-test type=performance | scope=browser_data preload | protects=首页候选项重复查询同一数据对象或加载无关字段与业务行
def test_preload_includes_complete_options_once_per_shared_field():
    import gzip
    import json
    doc = document()
    doc['manifest']['filters'] = [
        {'id': 'month', 'op': 'in', 'field': 'month', 'componentIds': ['a', 'b']},
        {'id': 'search', 'op': 'contains', 'field': 'label', 'componentIds': ['a']}]
    values = [None, *range(230)]
    obj = {'id': 'obj', 'descriptor': {
        'shards': ['rows.gz'], 'options': {'month': 'months.gz', 'label': 'labels.gz'},
        'files': {'rows.gz': {'bytes': 3000}, 'months.gz': {'bytes': 400}, 'labels.gz': {'bytes': 300}}}}
    assets = Mock()
    assets.call.return_value = obj
    assets.read_file.return_value = gzip.compress(json.dumps(values).encode())
    result = web_document(SimpleNamespace(assets=assets), doc,
                          lambda obj, name: f'/{obj}/{name}', editable=True, preload_options=True)
    assert result['staticOptionValues'] == {'sales': {'month': values}, 'copy': {'month': values}}
    assert result['staticResourceSizes']['/obj/rows.gz'] == 3000
    assert 'browserDataUrl' not in result
    assets.call.assert_called_once_with('object_get', version='v1')
    assets.read_file.assert_called_once_with(obj, 'months.gz')
    assert result['computed'] == doc['computed']


# @wu-test type=boundary | scope=authorized_files | protects=批量文件越过版本边界或部分授权失败仍读取业务字节
def test_batch_checks_every_file_before_reading_and_deduplicates_objects():
    obj = {'id': 'obj', 'kind': 'dataset', 'version': 'v1', 'descriptor': {
        'shards': ['a.gz', 'b.gz'], 'options': {},
        'files': {'a.gz': {'bytes': 2}, 'b.gz': {'bytes': 2}}}}
    assets = Mock()
    assets.call.return_value = obj
    assets.read_file.side_effect = lambda _obj, name: name.encode()
    store = SimpleNamespace(assets=assets)
    result = authorized_files(store, document(), ['obj/a.gz', 'obj/b.gz', 'obj/a.gz'], max_bytes=4)
    assert result == {'obj/a.gz': b'a.gz', 'obj/b.gz': b'b.gz'}
    assets.call.assert_called_once_with('object_get', id='obj')
    assets.read_file.reset_mock()
    with pytest.raises(DashboardError, match='not a browser data resource'):
        authorized_files(store, document(), ['obj/a.gz', 'obj/query.sqlite3'])
    assets.read_file.assert_not_called()
    with pytest.raises(DashboardError) as oversized:
        authorized_files(store, document(), ['obj/a.gz', 'obj/b.gz'], max_bytes=3)
    assert oversized.value.status == 413
    assets.read_file.assert_not_called()
    obj['version'] = 'private-version'
    with pytest.raises(DashboardError) as forbidden:
        authorized_files(store, document(), ['obj/a.gz'])
    assert forbidden.value.code == 'FORBIDDEN'
    assets.read_file.assert_not_called()
