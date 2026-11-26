import time
from threading import Barrier

import pytest

from dashboard_runtime.cloud_assets import CloudAssets
from dashboard_runtime.cloud_data import CloudData
from dashboard_runtime.local_data import LocalData
from dashboard_runtime.model import DashboardError


class MemoryDatabase:
    def __init__(self):
        self.parts = {}
        self.refs = {}

    def call(self, action, project, **args):
        if action == 'data_get':
            return self.refs.get(args['version'])
        if action == 'data_chunk_put':
            key = (args['version'], args['part'])
            if key in self.parts and self.parts[key] != args['rows']:
                raise DashboardError('DATA_CONFLICT', 'conflicting chunk')
            self.parts[key] = args['rows']
            return True
        if action == 'data_finish':
            self.refs[args['metadata']['version']] = args['metadata']
            return args['metadata']
        raise AssertionError(action)


class MemoryStorage:
    def __init__(self):
        self.objects = {}

    def get(self, key):
        return self.objects.get(key)

    def put(self, key, value, _content_type):
        self.objects[key] = value

    def delete_prefix(self, prefix):
        for key in list(self.objects):
            if key.startswith(prefix):
                del self.objects[key]


class MemoryAssetRegistry:
    def __init__(self):
        self.objects = {}
        self.by_version = {}
        self.shares = []

    def call(self, action, _project, **kwargs):
        if action == 'object_get':
            return (self.objects.get(kwargs['id']) if 'id' in kwargs else
                    self.by_version.get(kwargs['version']))
        if action == 'share_register':
            self.shares.append(kwargs)
            return True
        if action == 'reserve':
            obj = kwargs | {'prefix': kwargs['id'] + '/'}
            self.objects[obj['id']] = obj
            return obj
        assert action == 'ready'
        obj = self.objects[kwargs['id']] | kwargs
        self.objects[obj['id']] = obj
        self.by_version[obj['version']] = obj
        return obj


@pytest.fixture
def native_cos():
    from dashboard_runtime.columnar import native_binary
    if not native_binary():
        pytest.skip('New COS packages require the native exporter built by the native CI job')


# @wu-test type=integration | scope=COS dataset repartition | protects=重建分区篡改原数据或更新看板引用
def test_repartition_stages_one_replacement_and_preserves_original(tmp_path, monkeypatch, native_cos):
    from dashboard_runtime.server import EDIT_TOOLS
    from dashboard_runtime.service import Service
    from static_fixture import worker_rows

    monkeypatch.setenv('CHARTS_STORAGE_BACKEND', 'local')
    fields = {'department': {'type': 'string'}, 'month': {'type': 'string'}, 'value': {'type': 'number'}}
    rows = [
        {'department': 'A', 'month': '2026-10', 'value': 3},
        {'department': 'B', 'month': '2026-11', 'value': None},
        {'department': 'A', 'month': '2026-11'},
    ]
    registry = MemoryAssetRegistry()
    assets = CloudAssets('test', database=registry, storage=MemoryStorage())
    local = LocalData(tmp_path / 'source')
    ref = local.import_rows(rows, fields)
    original = assets.save_dataset(local, ref)
    cloud = CloudData(tmp_path / 'reader', MemoryDatabase(), 'test', assets, cos_enabled=True)
    service = Service(tmp_path / 'service')
    service.store.data = cloud
    doc = {'snapshot': {'datasetRefs': {'sales': ref}}}
    monkeypatch.setattr(service.store, 'get', lambda _board, hydrate: doc)
    request = {'dashboardId': 'board', 'datasetId': 'sales', 'field': 'department',
               'expectedVersion': ref['version']}
    assert 'dataset_repartition' not in EDIT_TOOLS
    with pytest.raises(DashboardError) as stale:
        service.call('dataset_repartition', dict(request, expectedVersion='0' * 64))
    assert stale.value.code == 'DATA_CONFLICT'
    replacement = service.call('dataset_repartition', request)['ref']
    assert replacement['version'] != ref['version']
    assert replacement['fields'] == ref['fields']
    assert list(cloud.iter_rows(replacement)) == list(cloud.iter_rows(ref)) == rows
    obj = registry.by_version[replacement['version']]
    index = obj['descriptor']['partitionIndex']
    assert index['field'] == 'department'
    office_a = next(entry['files'][0] for entry in index['entries'] if entry['value'] == 'A')
    assert office_a.endswith('.parquet')
    assert worker_rows(assets.read_file(obj, office_a), office_a) == [rows[0], rows[2]]
    assert service.call('dataset_repartition', request)['ref'] == replacement
    assert len(registry.objects) == 2
    assert registry.by_version[ref['version']] == original
    assert doc['snapshot']['datasetRefs']['sales'] == ref


# @wu-test type=integration | scope=COS report options | protects=月报引用超过十个数据集时无法保存或缺少筛选选项
def test_cos_report_seed_can_have_more_consumers_than_sqlite_attachment_limit(tmp_path, native_cos):
    from dashboard_runtime.cloud_project import CloudProjectStore
    from dashboard_runtime.local_view import LocalView
    from dashboard_runtime.model import new_document

    class Assets(CloudAssets):
        def save_document(self, doc):
            return doc

    doc = new_document('report', 'Monthly report')
    doc['snapshot']['datasetRefs'] = {}
    source = LocalData(tmp_path / 'source')
    registry = MemoryAssetRegistry()
    assets = Assets('test', database=registry, storage=MemoryStorage())
    store = CloudProjectStore.__new__(CloudProjectStore)
    store.cos_enabled, store.assets = True, assets
    store.data = CloudData(tmp_path / 'reader', MemoryDatabase(), 'test', assets, cos_enabled=True)
    store.prepared_views = LocalView(store.data)
    fields = {'office': {'type':'string'}}
    for index in range(13):
        key = f'table-{index}'
        ref = source.import_rows([{'office':f'Office {index:02}'}], fields)
        assets.save_dataset(source, ref)
        doc['manifest']['datasets'][key] = {'fields':fields}
        doc['manifest']['components'][key] = {'kind':'table','datasetId':key}
        doc['snapshot']['datasetRefs'][key] = ref
    doc['manifest']['filters'] = [{'id':'office','field':'office','op':'in',
        'selectionMode':'single','required':True,'componentIds':list(doc['manifest']['components']),'values':['Office 00']}]
    prepared = store._encode(doc)
    assert set(prepared['computed']['filterPages']['office']['values']) == {f'Office {index:02}' for index in range(13)}
    assert store.prepared_views.filter_options(doc, 'office', search='office 1', offset=1, limit=1) == {
        'values': ['Office 11'], 'totalValues': 3, 'offset': 1, 'hasMore': True,
    }


# @wu-test type=integration | scope=COS prepared scope options | protects=编辑绑定后继续使用上一数据集的筛选选项
def test_cos_scope_option_seed_tracks_changed_consumer(tmp_path):
    import copy
    from types import SimpleNamespace
    from dashboard_runtime.cloud_project import CloudProjectStore
    from dashboard_runtime.cos_view import web_document
    from dashboard_runtime.local_view import LocalView
    from dashboard_runtime.model import new_document

    store = CloudProjectStore.__new__(CloudProjectStore)
    store.cos_enabled = True
    data = LocalData(tmp_path)
    store.prepared_views = LocalView(data)
    store.assets = SimpleNamespace(
        save_document=lambda doc: doc,
        call=lambda _action, *, version: {
            'id': version, 'descriptor': {'shards': [], 'options': {}},
        },
    )
    doc = new_document('board', 'Scope options')
    doc['snapshot']['datasetRefs'] = {}
    fields = {'office': {'type': 'string'}}
    for dataset, office in [('initial', 'A'), ('replacement', 'B')]:
        doc['manifest']['datasets'][dataset] = {'fields': fields}
        doc['snapshot']['datasetRefs'][dataset] = data.import_rows([{'office': office}], fields)
    doc['manifest']['components']['table'] = {'kind': 'table', 'datasetId': 'initial'}
    doc['manifest']['filters'] = [{
        'id': 'office', 'field': 'office', 'op': 'in', 'selectionMode': 'single',
        'required': True, 'componentIds': ['table'], 'values': ['A'],
    }]
    initial = store._encode(doc)
    assert web_document(store, initial, lambda *_: '')['staticFilterOptions'] == {'office': ['A']}
    updated = copy.deepcopy(doc)
    updated['manifest']['components']['table']['datasetId'] = 'replacement'
    next_revision = store._encode(updated, previous=initial)
    assert web_document(store, next_revision, lambda *_: '')['staticFilterOptions'] == {'office': ['B']}
    oversized = copy.deepcopy(updated)
    oversized['snapshot']['datasetRefs']['replacement'] = data.import_rows([{'office': 'x' * 5000}], fields)
    encoded = store._encode(oversized, previous=next_revision)
    assert web_document(store, encoded, lambda *_: '')['staticFilterOptions'] == {}


# @wu-test type=integration | scope=CloudAssets dataset writes | protects=并行写入失败仍将不完整数据包标记为可用
def test_cos_dataset_failed_parallel_write_never_becomes_ready(tmp_path, native_cos):
    class Database:
        def call(self, action, project, **args):
            if action == 'object_get':
                return None
            assert action == 'reserve', action
            return {'prefix': 'dataset/'}

    class Storage(MemoryStorage):
        def __init__(self):
            super().__init__()
            self.writes = Barrier(3, timeout=5)

        def put(self, key, value, content_type):
            self.writes.wait()
            if key.endswith('-options-1-0.parquet'):
                raise OSError('option write failed')
            super().put(key, value, content_type)

    source = LocalData(tmp_path / 'source')
    ref = source.import_rows([{'count': 1, 'office': 'A'}], {
        'count': {'type': 'number'},
        'office': {'type': 'string'},
    })
    storage = Storage()
    assets = CloudAssets('test', database=Database(), storage=storage)
    with pytest.raises(OSError, match='option write failed'):
        assets.save_dataset(source, ref)
    assert set(storage.objects) == {f"dataset/{ref['version']}-0.parquet",
                                    f"dataset/{ref['version']}-options-0-0.parquet"}


# @wu-test type=integration | scope=COS Parquet persistence and browser query | protects=首次云保存递归读取未ready对象或分区排序遗漏空值缺失字段候选项及缓存恢复
def test_cos_parquet_package_preserves_query_file_partition_order_and_options(tmp_path, monkeypatch, native_cos):
    from types import SimpleNamespace

    from dashboard_runtime.cos_view import authorized_file, web_document
    from dashboard_runtime.model import new_document
    from static_fixture import worker_query

    registry = MemoryAssetRegistry()
    assets = CloudAssets('test', database=registry, storage=MemoryStorage())
    cloud = CloudData(tmp_path / 'writer', MemoryDatabase(), 'test', assets, cos_enabled=True)
    cloud.partition_fields = ['department']
    fields = {'department': {'type': 'string'}, 'amount': {'type': 'number'},
              'active': {'type': 'boolean'}, 'label': {'type': 'string'}}
    rows = [
        {'department': 'B', 'amount': 3, 'active': True, 'label': '首行'},
        {'department': 'A', 'amount': None, 'active': False},
        {'department': 'B', 'active': None, 'label': None},
        {'department': None, 'amount': 1.5},
        {'amount': 0, 'active': True},
    ]
    with monkeypatch.context() as patch:
        patch.setattr(LocalData, 'iter_rows', lambda *_args, **_kwargs: pytest.fail('Cloud packaging must read SQLite natively'))
        ref = cloud.import_rows(rows, fields)
    obj = registry.by_version[ref['version']]
    descriptor = obj['descriptor']
    assert (descriptor['format'], descriptor['dataFormat'], descriptor['queryFormat']) == ('cos-dataset-v1', 'parquet-v1', 1)
    assert all(name.endswith('.parquet') for name in descriptor['files'] if name not in ('manifest.json', 'query.sqlite3'))
    assert set(descriptor['options']) == set(fields)
    assert all(entry['field'] == field and entry['files'] for field, entry in descriptor['options'].items())

    fresh = CloudData(tmp_path / 'fresh-cache', MemoryDatabase(), 'test', assets, cos_enabled=True)
    assert list(fresh.iter_rows(ref)) == rows
    assert fresh.aggregate(ref, {'total': {'aggregation': 'sum', 'field': 'amount'}}) == [{'total': 4.5}]
    doc = new_document('board', 'Cloud Parquet')
    doc['manifest']['datasets'] = {'sales': {'fields': fields}}
    doc['manifest']['components'] = {'table': {'kind': 'table', 'datasetId': 'sales'}}
    selected = {'id': 'department', 'field': 'department', 'op': 'in', 'componentIds': ['table'], 'values': ['B']}
    doc['manifest']['filters'] = [selected, {'id': 'amount', 'field': 'amount', 'op': 'in', 'componentIds': ['table'], 'values': []}]
    doc['snapshot']['datasetRefs'] = {'sales': ref}
    store = SimpleNamespace(assets=assets)
    web = web_document(store, doc, lambda _object, name: name)
    payloads = {name: authorized_file(store, doc, obj['id'], name) for name in [
        *descriptor['shards'], *(name for entry in descriptor['options'].values() for name in entry['files']),
    ]}
    results = worker_query(web, payloads, [
        {'detail': True, 'componentId': 'table'},
        {'detail': True, 'componentId': 'table', 'filters': []},
        {'filterId': 'amount'},
    ])
    selected_files = next(entry['files'] for entry in descriptor['partitionIndex']['entries'] if entry['value'] == 'B')
    assert results[0]['files'] == selected_files
    assert results[0]['result']['rows'] == [rows[0], rows[2]]
    assert results[1]['result']['rows'] == rows
    assert results[2]['result']['values'] == [None, 0, 1.5, 3]
    assert results[2]['files'] == descriptor['options']['amount']['files']
    with pytest.raises(DashboardError) as denied:
        authorized_file(store, doc, obj['id'], 'query.sqlite3')
    assert denied.value.code == 'FORBIDDEN'


# @wu-test type=boundary | scope=COS new package format | protects=缺少原生程序时静默保存JSON或提前登记半成品
def test_cos_new_package_requires_native_before_reserving_objects(tmp_path, monkeypatch):
    from dashboard_runtime import columnar

    source = LocalData(tmp_path / 'source')
    ref = source.import_rows([{'value': 1}], {'value': {'type': 'number'}})
    registry, storage = MemoryAssetRegistry(), MemoryStorage()
    assets = CloudAssets('test', database=registry, storage=storage)
    monkeypatch.setattr(columnar, 'native_binary', lambda: None)
    with pytest.raises(DashboardError) as missing:
        assets.save_dataset(source, ref)
    assert missing.value.code == 'NATIVE_UNAVAILABLE'
    assert not registry.objects and not storage.objects


# @wu-test type=integration | scope=COS migration read-back verification | protects=只信任Parquet回执或哈希导致损坏分片及错误行数仍删除旧PG数据
def test_cos_migration_decodes_downloaded_parquet_and_keeps_legacy_readable(tmp_path, native_cos):
    import copy
    import gzip
    import hashlib
    import json

    from dashboard_runtime.cos_migrate import verify_dataset

    source = LocalData(tmp_path / 'source')
    rows = [{'label': 'B', 'value': 2}, {'label': 'A'}, {'label': None, 'value': None}]
    fields = {'label': {'type': 'string'}, 'value': {'type': 'number'}}
    ref = source.import_rows(rows, fields)
    source.partition_fields = ['label']
    assets = CloudAssets('test', database=MemoryAssetRegistry(), storage=MemoryStorage())
    obj = assets.save_dataset(source, ref)
    verify_dataset(assets, obj, ref)

    incorrect = copy.deepcopy(obj)
    incorrect_ref = {**ref, 'rowCount': ref['rowCount'] + 1}
    incorrect['descriptor']['metadata'] = incorrect_ref
    with pytest.raises(DashboardError) as count:
        verify_dataset(assets, incorrect, incorrect_ref)
    assert count.value.code == 'DATA_INCOMPLETE'

    damaged = copy.deepcopy(obj)
    name = damaged['descriptor']['shards'][0]
    key = damaged['prefix'] + name
    original = assets.storage.objects[key]
    raw = original[:-8]
    assets.storage.objects[key] = raw
    damaged['descriptor']['files'][name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    with pytest.raises(DashboardError) as corrupt:
        verify_dataset(assets, damaged, ref)
    assert corrupt.value.code == 'PARQUET_EXPORT_FAILED'
    assets.storage.objects[key] = original

    legacy = copy.deepcopy(obj)
    legacy['descriptor'].pop('dataFormat')
    legacy['descriptor'].pop('partitionIndex')
    legacy['descriptor']['shards'] = ['rows-0.json.gz']
    legacy['descriptor']['options'] = {'label': 'options-0.json.gz'}
    assets._put(legacy, legacy['descriptor']['files'], 'rows-0.json.gz', gzip.compress(json.dumps(rows).encode()))
    assets._put(legacy, legacy['descriptor']['files'], 'options-0.json.gz', gzip.compress(b'["B","A",null]'))
    verify_dataset(assets, legacy, ref)


# @wu-test type=integration | scope=CloudData legacy restore | protects=并发恢复分块乱序改变数据校验值或重复读取已缓存版本
def test_legacy_restore_fetches_four_chunks_and_preserves_order(tmp_path):
    import threading
    rows = [{'value': i} for i in range(2501)]
    source = LocalData(tmp_path / 'source')
    ref = source.import_rows(rows, {'value': {'type': 'number'}})
    barrier = threading.Barrier(4)

    class Database:
        def __init__(self):
            self.parts = []

        def call(self, action, project, **args):
            if action == 'data_get':
                return ref
            assert action == 'data_chunk_get'
            part = args['part']
            self.parts.append(part)
            if part < 4:
                barrier.wait(timeout=5)
            return rows[part * 500:(part + 1) * 500]

    database = Database()
    data = CloudData(tmp_path / 'cache', database, 'test')
    with data._connect() as db:
        _, restored = data._version(db, ref)
        assert restored == ref
        data._version(db, ref)
    assert sorted(database.parts) == list(range(6))


def wait(data, upload, ref):
    for _ in range(500):
        status = data.transfer_status(upload, ref)
        if status['state'] != 'running':
            return status
        time.sleep(.01)
    raise AssertionError('transfer did not finish')


# @wu-test type=integration | scope=CloudData transfer | protects=重传重复数据或分块缺失时发布不完整版本
def test_transfer_resume_verification_and_cleanup(tmp_path, monkeypatch):
    fields = {'value': {'type': 'number'}, 'label': {'type': 'string'}}
    rows = [{'value': i, 'label': str(i)} for i in range(503)]
    source = LocalData(tmp_path / 'source')
    ref = source.import_rows(rows, fields)
    data = CloudData(tmp_path / 'remote', MemoryDatabase(), 'fixture')
    storage = MemoryStorage()
    monkeypatch.setattr(data, 'transfer_storage', storage)
    upload = 'a' * 64
    data.transfer_chunk(upload, ref, 0, rows[:250])
    data.transfer_chunk(upload, ref, 0, rows[:250])
    with pytest.raises(DashboardError):
        data.transfer_chunk(upload, ref, 0, [rows[1]] * 250)
    data.transfer_finish(upload, ref)
    assert wait(data, upload, ref)['code'] == 'DATA_INCOMPLETE'
    assert data.database.call('data_get', 'fixture', version=ref['version']) is None
    data.transfer_chunk(upload, ref, 1, rows[250:500])
    data.transfer_chunk(upload, ref, 2, rows[500:])
    data.transfer_finish(upload, ref)
    assert wait(data, upload, ref)['state'] == 'complete'
    assert not storage.objects
    assert data.describe(ref['version']) == ref
    assert list(data.iter_rows(ref)) == rows



# @wu-test type=boundary | scope=transfer-project manifest | protects=迁移时上传未引用数据或漏掉组件数据
def test_manifest_retains_components_and_excludes_unselected_data(tmp_path):
    import runpy
    from pathlib import Path
    from dashboard_runtime.demo import report_document
    from dashboard_runtime.project import ProjectStore

    script = runpy.run_path(str(Path(__file__).parents[2] / 'bin' / 'transfer-project.py'))
    root = tmp_path / 'project'
    store = ProjectStore(root, tmp_path / 'runtime')
    store.create('board', 'Fixture', report_document('board'))
    changed = store.mutate('board', 1, [
        {'op': 'put_dataset', 'id': 'unused',
         'meta': {'sourceId': 'fixture', 'fields': {'secret': {'type': 'string'}}},
         'rows': [{'secret': 'synthetic-only'}]},
        {'op': 'put_metric', 'id': 'unused-metric', 'value': {
            'datasetId': 'unused', 'aggregation': 'count', 'label': 'Count',
            'definition': 'Synthetic unused count', 'unit': ''}},
    ])
    ref = changed['snapshot']['datasetRefs']['sales']
    item = {'id': 'sales', **{k: ref[k] for k in ('version', 'rowCount', 'bytes')}}
    manifest = {'projectRoot': str(root), 'pages': [{'dashboardId': 'board',
        'draftRevision': changed['revision'], 'componentCount': len(changed['manifest']['components']),
        'datasets': [item]}]}
    _, docs, refs = script['read_project'](manifest)
    result = docs['board']
    assert set(result['manifest']['datasets']) == {'sales'}
    assert 'unused-metric' not in result['manifest']['metrics']
    assert result['manifest']['components'] == changed['manifest']['components']
    assert result['manifest']['filters'] == changed['manifest']['filters']
    assert list(refs) == [ref['version']]
    manifest['pages'][0]['datasets'] = []
    with pytest.raises(ValueError, match='omits a component dataset'):
        script['read_project'](manifest)



# @wu-test type=boundary | scope=CloudData transfer checksum | protects=分块内容损坏时错误数据被登记为已完成版本
def test_transfer_rejects_wrong_content_and_can_restart(tmp_path, monkeypatch):
    fields = {'value': {'type': 'number'}}
    ref = LocalData(tmp_path / 'source').import_rows([{'value': 1}], fields)
    database, storage = MemoryDatabase(), MemoryStorage()
    data = CloudData(tmp_path / 'cache', database, 'fixture')
    monkeypatch.setattr(data, 'transfer_storage', storage)
    upload = 'b' * 64
    data.transfer_chunk(upload, ref, 0, [{'value': 2}])
    data.transfer_finish(upload, ref)
    assert wait(data, upload, ref)['code'] == 'DATA_CONFLICT'
    assert database.call('data_get', 'fixture', version=ref['version']) is None
    data.transfer_cleanup(upload)
    data.transfer_chunk(upload, ref, 0, [{'value': 1}])
    restarted = CloudData(tmp_path / 'other-cache', database, 'fixture')
    monkeypatch.setattr(restarted, 'transfer_storage', storage)
    assert restarted.transfer_status(upload, ref)['state'] == 'unknown'
    restarted.transfer_finish(upload, ref)
    assert wait(restarted, upload, ref)['state'] == 'complete'
    assert not storage.objects


# @wu-test type=boundary | scope=CloudData bulk payload | protects=无效压缩包或解压后超限的数据进入暂存
@pytest.mark.parametrize(('compressed', 'limit', 'message'), [
    (b'not-gzip', 16_384, 'Invalid bulk chunk gzip'),
    (b'', 16_384, 'Invalid bulk chunk gzip'),
    (None, 32, 'Bulk chunk exceeds 16 MiB decoded'),
])
def test_bulk_rejects_invalid_payload_before_staging(tmp_path, monkeypatch, compressed, limit, message):
    import base64
    import gzip
    from dashboard_runtime import transfer_payload

    rows = [{'label': 'x' * 1024}]
    ref = LocalData(tmp_path / 'source').import_rows(rows, {'label': {'type': 'string'}})
    data = CloudData(tmp_path / 'cache', MemoryDatabase(), 'fixture')
    storage = MemoryStorage()
    monkeypatch.setattr(data, 'transfer_storage', storage)
    monkeypatch.setattr(transfer_payload, 'BULK_DECODED', limit)
    if compressed is None:
        compressed = gzip.compress(transfer_payload.json_bytes(rows))
    with pytest.raises(DashboardError, match=message):
        data.transfer_chunk('d' * 64, ref, 0, bulk=True, payload=base64.b64encode(compressed).decode())
    assert not storage.objects and not data.database.refs



# @wu-test type=integration | scope=CloudProjectStore.create | protects=迁移批注时丢失原始版本和筛选上下文
def test_cloud_import_keeps_annotation_context(tmp_path, monkeypatch):
    from dashboard_runtime.cloud_project import CloudProjectStore
    from dashboard_runtime.model import new_document
    from dashboard_runtime.project import DEFAULTS

    class Database:
        def call(self, action, project, **args):
            if action == 'ensure':
                return DEFAULTS
            if action == 'create':
                return args['document']
            raise AssertionError(action)

    from dashboard_runtime import cloud_assets
    monkeypatch.setattr(cloud_assets, 'AssetDatabase', Database)
    doc = new_document('board', 'Synthetic')
    original = {'designRevision': 42, 'dataVersions': {}, 'filters': []}
    doc['manifest']['annotations'] = [{'id': 'note', 'componentId': None, 'text': 'Synthetic note',
                                      'createdAt': '2026-11-11', 'context': original}]
    store = CloudProjectStore(tmp_path / 'fixture', tmp_path / 'cache', Database())
    result = store.create('board', 'Synthetic', doc)
    assert result['manifest']['annotations'][0]['context'] == original



# @wu-test type=integration | scope=transfer-project MCP response | protects=页面配置超过传输上限时丢失内容或误判已有页面
def test_client_reassembles_large_mcp_response():
    import asyncio
    import base64
    import json
    import runpy
    from pathlib import Path
    from types import SimpleNamespace

    call = runpy.run_path(str(Path(__file__).parents[2] / 'bin' / 'transfer-project.py'))['call_tool']
    raw = json.dumps({'document': {'title': 'x' * 50000}}).encode()
    encoded = base64.b64encode(raw).decode()
    pages = [encoded[i:i+24000] for i in range(0, len(encoded), 24000)]
    class Session:
        async def call_tool(self, tool, args):
            assert args['projectRoot'] == 'fixture'
            if tool == 'dashboard_get':
                result = {'transport': {'encoding': 'base64-json-v1', 'requestId': 'token',
                                        'chunks': len(pages), 'bytes': len(raw)}}
            else:
                assert tool == 'runtime_result_chunk'
                result = {'requestId': 'token', 'index': args['index'], 'data': pages[args['index']]}
            return SimpleNamespace(isError=False, structuredContent=result, content=[])
    assert asyncio.run(call(Session(), 'fixture', 'dashboard_get', {}))['document']['title'] == 'x' * 50000



# @wu-test type=integration | scope=CloudData transfer progress | protects=合并期间无法区分暂存读取和持久化进度
def test_transfer_reports_reading_progress(tmp_path, monkeypatch):
    import threading

    fields = {'value': {'type': 'number'}}
    ref = LocalData(tmp_path / 'source').import_rows([{'value': 1}], fields)
    started, release = threading.Event(), threading.Event()
    class BlockingStorage(MemoryStorage):
        def get(self, key):
            started.set()
            assert release.wait(5)
            return super().get(key)

    storage = BlockingStorage()
    data = CloudData(tmp_path / 'remote', MemoryDatabase(), 'fixture')
    monkeypatch.setattr(data, 'transfer_storage', storage)
    upload = 'c' * 64
    # Populate before the blocking reader is enabled.
    MemoryStorage.put(storage, data._transfer_prefix(upload) + '0', __import__('gzip').compress(b'[{"value":1}]'), 'application/gzip')
    data.transfer_finish(upload, ref)
    try:
        assert started.wait(5)
        status = data.transfer_status(upload, ref)
        assert (status['state'], status['phase'], status['completed'], status['total']) == ('running', 'reading', 0, 1)
        assert 'ref' not in status
    finally:
        release.set()
    assert wait(data, upload, ref)['state'] == 'complete'


# @wu-test type=integration | scope=remote_client transfer resume | protects=上传响应丢失后重复发送已暂存分块或提前完成不完整数据
def test_shared_client_recovers_lost_receipt_with_bounded_concurrency(tmp_path, monkeypatch):
    import asyncio
    from collections import Counter
    from dashboard_runtime.remote_client import TransferClient, check_source
    from dashboard_runtime.service import Service

    monkeypatch.setenv('CHARTS_STORAGE_BACKEND', 'local')
    root = tmp_path / 'source'
    rows = [{'value': i} for i in range(1001)]
    ref = LocalData(root / 'data').import_rows(rows, {'value': {'type': 'number'}})
    check_source(root, ref)
    database, storage = MemoryDatabase(), MemoryStorage()
    data = CloudData(tmp_path / 'remote', database, 'fixture')
    monkeypatch.setattr(data, 'transfer_storage', storage)
    service = Service(tmp_path / 'service')
    service.store.data = data
    sent, events = Counter(), []
    active, peak, fail = 0, 0, True

    async def call(name, args):
        nonlocal active, peak, fail
        if name == 'dataset_transfer_chunk':
            part = args['part']
            sent[part] += 1
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0)
                result = service.call(name, args)
                if fail and part == 0:
                    fail = False
                    raise ConnectionError('Synthetic response loss after storage')
                return result
            finally:
                active -= 1
        if name == 'dataset_transfer_status':
            return service.call(name, args)
        assert name == 'dataset_transfer_finish'
        return service.call(name, args)

    async def scenario():
        client = TransferClient(call, root, 'https://example.test/mcp', 'fixture',
                                tmp_path / 'state.json', emit=events.append)
        with pytest.raises(ConnectionError):
            await client.transfer(ref)
        assert not database.refs
        assert set(sent) == {0, 1, 2, 3}
        # A new client and service instance simulate both sides restarting.
        nonlocal data
        data = CloudData(tmp_path / 'remote', database, 'fixture')
        monkeypatch.setattr(data, 'transfer_storage', storage)
        service.store.data = data
        resumed = TransferClient(call, root, 'https://example.test/mcp', 'fixture',
                                 tmp_path / 'state.json', emit=events.append)
        assert await resumed.transfer(ref) == ref

    asyncio.run(scenario())
    assert peak == 4
    assert sent == Counter({0: 1, 1: 1, 2: 1, 3: 1, 4: 1})
    assert list(data.iter_rows(ref)) == rows
    assert not storage.objects
    assert any(event.get('reusedParts') == 4 for event in events)


# @wu-test type=integration | scope=remote_client finalize | protects=空数据或服务重启后的清理状态被误判为上传失败
@pytest.mark.parametrize('already_saved', [False, True])
def test_client_completes_empty_and_cleanup_required(tmp_path, already_saved, monkeypatch):
    import asyncio
    from dashboard_runtime.remote_client import TransferClient

    root = tmp_path / 'source'
    ref = LocalData(root / 'data').import_rows([], {'value': {'type': 'number'}})
    data = CloudData(tmp_path / 'remote', MemoryDatabase(), 'fixture')
    monkeypatch.setattr(data, 'transfer_storage', MemoryStorage())
    if already_saved:
        data.import_rows([], {'value': {'type': 'number'}})

    async def call(name, args):
        assert name != 'dataset_transfer_chunk'
        if name == 'dataset_transfer_status':
            return data.transfer_status(args['uploadId'], ref, args.get('parts'))
        return data.transfer_finish(args['uploadId'], ref)

    client = TransferClient(call, root, 'https://example.test/mcp', 'fixture',
                            tmp_path / 'state.json', emit=lambda _: None)
    assert asyncio.run(client.transfer(ref)) == ref
    assert data.describe(ref['version']) == ref


# @wu-test type=boundary | scope=remote_client transfer receipts | protects=续传把服务端内容不同的分块当作已上传而跳过
def test_client_rejects_changed_remote_part(tmp_path, monkeypatch):
    import asyncio
    import gzip
    from dashboard_runtime.remote_client import TransferClient

    root = tmp_path / 'source'
    ref = LocalData(root / 'data').import_rows([{'value': 1}], {'value': {'type': 'number'}})
    data = CloudData(tmp_path / 'remote', MemoryDatabase(), 'fixture')
    storage = MemoryStorage()
    monkeypatch.setattr(data, 'transfer_storage', storage)
    async def call(name, args):
        assert name == 'dataset_transfer_status'
        return data.transfer_status(args['uploadId'], ref, args.get('parts'))
    client = TransferClient(call, root, 'https://example.test/mcp', 'fixture',
                            tmp_path / 'state.json', emit=lambda _: None)
    upload = 'f' * 64
    client.state['uploads'][ref['version']] = upload
    storage.put(data._transfer_prefix(upload) + '0',
                gzip.compress(b'[{"value":999}]'), 'application/gzip')
    with pytest.raises(ValueError, match='DATA_CONFLICT'):
        asyncio.run(client.transfer(ref))
    assert not data.database.refs


# @wu-test type=boundary | scope=CloudData receipt query | protects=无效分块范围触发无界存储读取或访问非分块对象
@pytest.mark.parametrize('parts', [[-1], [1], [True], [0, 0], list(range(129))])
def test_transfer_receipts_reject_invalid_parts(tmp_path, parts):
    ref = LocalData(tmp_path / 'source').import_rows([{'value': 1}], {'value': {'type': 'number'}})
    data = CloudData(tmp_path / 'remote', MemoryDatabase(), 'fixture')
    with pytest.raises(DashboardError, match='Invalid transfer receipt parts'):
        data.transfer_status('a' * 64, ref, parts)


# @wu-test type=boundary | scope=remote_client protocol | protects=缺失状态字段导致无限轮询或误报成功
def test_client_reports_missing_state(tmp_path):
    import asyncio
    from dashboard_runtime.remote_client import TransferClient
    async def call(*_):
        return {'status': 'complete'}
    client = TransferClient(call, tmp_path, 'https://example.test/mcp', 'fixture',
                            tmp_path / 'state.json', emit=lambda _: None)
    with pytest.raises(RuntimeError, match='TRANSFER_PROTOCOL_ERROR'):
        asyncio.run(client.transfer({'version': 'a' * 64}))


# @wu-test type=boundary | scope=remote_client preflight | protects=旧服务缺少续传接口时仍开始发送数据
def test_client_checks_paginated_capabilities():
    import asyncio
    from types import SimpleNamespace
    from dashboard_runtime.remote_client import require_tools, TRANSFER_TOOLS

    class Session:
        async def list_tools(self, cursor=None):
            names = ['dataset_transfer_chunk', 'dataset_transfer_finish'] if cursor is None else ['dataset_transfer_status']
            tools = [SimpleNamespace(name=name, inputSchema={'properties': {
                key: {} for key in TRANSFER_TOOLS[name] if key != 'parts'}}) for name in names]
            return SimpleNamespace(tools=tools, nextCursor='next' if cursor is None else None)
    with pytest.raises(RuntimeError, match='CAPABILITY_MISSING: dataset_transfer_status'):
        asyncio.run(require_tools(Session(), TRANSFER_TOOLS))


# @wu-test type=boundary | scope=remote_client response decoding | protects=分块身份或长度错误时保存损坏的组件配置
@pytest.mark.parametrize('corruption', ['requestId', 'index', 'bytes'])
def test_client_rejects_corrupt_response(corruption):
    import asyncio
    import base64
    from types import SimpleNamespace
    from dashboard_runtime.remote_client import call_tool

    class Session:
        async def call_tool(self, name, args):
            if name == 'dashboard_get':
                value = {'transport': {'encoding': 'base64-json-v1', 'requestId': 'one',
                                       'chunks': 1, 'bytes': 3 if corruption == 'bytes' else 2}}
            else:
                value = {'requestId': 'wrong' if corruption == 'requestId' else 'one',
                         'index': 1 if corruption == 'index' else 0, 'data': base64.b64encode(b'{}').decode()}
            return SimpleNamespace(isError=False, structuredContent=value, content=[])
    with pytest.raises(ValueError, match='does not match'):
        asyncio.run(call_tool(Session(), 'fixture', 'dashboard_get', {}))


# @wu-test type=integration | scope=remote-project upload/read | protects=批量上传响应丢失后重传已暂存分片、登记不完整数据或下载时丢失大型组件配置
def test_remote_cli_upload_and_complete_read(tmp_path, monkeypatch, capsys):
    import asyncio
    from contextlib import asynccontextmanager
    import json
    from pathlib import Path
    import runpy
    from types import SimpleNamespace
    from dashboard_runtime.remote_client import batches
    from dashboard_runtime.model import json_bytes
    from dashboard_runtime.service import Service
    from dashboard_runtime.transfer_payload import BULK_ENCODING
    from dashboard_runtime.transport import ResultTransport
    from dashboard_runtime.tool_contract import TOOLS

    run = runpy.run_path(str(Path(__file__).parents[2] / 'bin' / 'remote-project.py'))['run']
    root = tmp_path / 'source'
    rows = [{'value': number, 'label': '渠道覆盖率'} for number in range(5003)]
    fields = {'value': {'type': 'number'}, 'label': {'type': 'string'}}
    rows_path, fields_path = tmp_path / 'rows.jsonl', tmp_path / 'fields.json'
    rows_path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
    fields_path.write_text(json.dumps(fields))
    data = CloudData(tmp_path / 'remote', MemoryDatabase(), 'fixture')
    storage = MemoryStorage()
    monkeypatch.setattr(data, 'transfer_storage', storage)
    transport = ResultTransport(tmp_path)
    service = Service(tmp_path / 'service')
    service.store.data = data
    document = {'revision': 7, 'manifest': {'components': {'trend': {'description': '字' * 50000}}}}
    uploads = []
    class Session:
        async def list_tools(self, cursor=None):
            return SimpleNamespace(tools=[SimpleNamespace(name=name, inputSchema=schema)
                                          for name, (_, schema) in TOOLS.items()], nextCursor=None)
        async def call_tool(self, name, args):
            if name == 'dashboard_get':
                result = transport.pack({'document': document}, name)
            elif name == 'runtime_result_chunk':
                result = transport.chunk(args)
            else:
                assert args['encoding'] == BULK_ENCODING
                result = service.call(name, args)
                if name == 'dataset_transfer_chunk':
                    uploads.append((args['part'], len(args['payload'])))
                    if len(uploads) == 1:
                        raise RuntimeError('synthetic response lost')
            return SimpleNamespace(isError=False, structuredContent=result, content=[])
    @asynccontextmanager
    async def connect(*_):
        yield Session()
    monkeypatch.setitem(run.__globals__, 'connect', connect)
    monkeypatch.setenv('CHARTS_MCP_URL', 'https://example.test/mcp')
    monkeypatch.setenv('CHARTS_SERVER_TOKENS', 'synthetic-token')
    output = tmp_path / 'ref.json'
    args = SimpleNamespace(command='upload', project='fixture', root=str(root), ref=None,
                           rows=str(rows_path), fields=str(fields_path), output=str(output),
                           state=str(tmp_path / 'state.json'), concurrency=1, check_only=True, legacy=False)
    asyncio.run(run(args))
    assert not data.database.refs and not storage.objects
    assert not output.exists()
    args.check_only = False
    with pytest.raises(RuntimeError, match='response lost'):
        asyncio.run(run(args))
    assert not output.exists()
    asyncio.run(run(args))
    ref = json.loads(output.read_text())
    assert list(data.iter_rows(ref)) == rows
    assert [part for part, _ in uploads] == [0, 1]
    legacy = list(batches(root, ref))
    assert len(legacy) == 21
    assert sum(size for _, size in uploads) < sum(len(json_bytes(part)) for part in legacy)
    assert not storage.objects
    assert output.stat().st_mode & 0o777 == 0o600
    download = tmp_path / 'dashboard.json'
    asyncio.run(run(SimpleNamespace(command='read', project='fixture', dashboard='board', output=str(download))))
    assert json.loads(download.read_text()) == {'document': document}
    assert '字' * 100 not in capsys.readouterr().out


# @wu-test type=boundary | scope=remote_client source preflight | protects=宽行分块上传到一半才发现超出请求限制
def test_source_preflight_rejects_oversized_chunk(tmp_path):
    from dashboard_runtime.remote_client import check_source
    root = tmp_path / 'source'
    ref = LocalData(root / 'data').import_rows([{'value': 'x' * 9000}] * 250,
                                              {'value': {'type': 'string'}})
    with pytest.raises(ValueError, match='exceeds 2 MiB'):
        check_source(root, ref)


# @wu-test type=integration | scope=remote_client staged recovery | protects=批量功能上线后旧暂存任务改用新分片格式或重新发送数据
def test_shared_client_recovers_legacy_staged_state(tmp_path, monkeypatch):
    import asyncio
    import hashlib
    import json
    from dashboard_runtime.remote_client import TransferClient

    ref = LocalData(tmp_path / 'source').import_rows([{'value': 1}], {'value': {'type': 'number'}})
    data = CloudData(tmp_path / 'remote', MemoryDatabase(), 'fixture')
    monkeypatch.setattr(data, 'transfer_storage', MemoryStorage())
    upload, endpoint = 'e' * 64, 'https://example.test/mcp'
    data.transfer_chunk(upload, ref, 0, [{'value': 1}])
    # The historical state has no per-part receipt metadata; the caller confirms staging.
    root = tmp_path / 'missing-local-project'
    identity = hashlib.sha256((endpoint + '\0fixture\0' + str(root)).encode()).hexdigest()
    state = tmp_path / 'state.json'
    state.write_text(json.dumps({'identity': identity, 'uploads': {ref['version']: upload}, 'created': []}))
    async def call(name, args):
        assert 'encoding' not in args
        if name == 'dataset_transfer_status':
            return data.transfer_status(upload, ref)
        assert name == 'dataset_transfer_finish'
        return data.transfer_finish(upload, ref)
    client = TransferClient(call, root, endpoint, 'fixture', state, emit=lambda _: None,
                            bulk_available=True)
    assert asyncio.run(client.transfer(ref, resume_staged=True)) == ref


# @wu-test type=integration | scope=remote_client incomplete recovery | protects=已标记暂存的数据缺块后反复合并失败而无法补传
def test_client_repairs_missing_part_after_failed_finalize(tmp_path, monkeypatch):
    import asyncio
    from dashboard_runtime.remote_client import TransferClient

    root = tmp_path / 'source'
    ref = LocalData(root / 'data').import_rows([{'value': 1}], {'value': {'type': 'number'}})
    data = CloudData(tmp_path / 'remote', MemoryDatabase(), 'fixture')
    monkeypatch.setattr(data, 'transfer_storage', MemoryStorage())
    upload = 'b' * 64
    data.transfer_finish(upload, ref)
    assert wait(data, upload, ref)['code'] == 'DATA_INCOMPLETE'
    sent = []
    async def call(name, args):
        if name == 'dataset_transfer_status':
            return data.transfer_status(upload, ref, args.get('parts'))
        if name == 'dataset_transfer_chunk':
            sent.append(args['part'])
            return data.transfer_chunk(upload, ref, args['part'], args['rows'])
        return data.transfer_finish(upload, ref)
    client = TransferClient(call, root, 'https://example.test/mcp', 'fixture',
                            tmp_path / 'state.json', emit=lambda _: None)
    client.state['uploads'][ref['version']] = upload
    client.state['staged'] = [ref['version']]
    assert asyncio.run(client.transfer(ref)) == ref
    assert sent == [0]
