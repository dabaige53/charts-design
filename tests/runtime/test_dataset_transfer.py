import time

import pytest

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



# @wu-test type=integration | scope=CloudProjectStore.create | protects=迁移批注时丢失原始版本和筛选上下文
def test_cloud_import_keeps_annotation_context(tmp_path):
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



# @wu-test type=integration | scope=transfer-project resume | protects=服务重启后重新发送已经完整暂存的数据行
def test_client_resumes_staged_version_without_rows(tmp_path, monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    import hashlib
    import json
    from pathlib import Path
    import runpy
    from types import SimpleNamespace

    run = runpy.run_path(str(Path(__file__).parents[2] / 'bin' / 'transfer-project.py'))['run']
    namespace = run.__globals__
    version = 'd' * 64
    root = tmp_path / 'source'
    endpoint = 'https://example.test/mcp'
    state_path = tmp_path / 'state.json'
    identity = hashlib.sha256((endpoint + '\0fixture\0' + str(root)).encode()).hexdigest()
    state_path.write_text(json.dumps({'identity': identity, 'uploads': {version: 'e' * 64}, 'created': []}))
    manifest_path = tmp_path / 'manifest.json'
    manifest_path.write_text('{}')
    monkeypatch.setenv('CHARTS_MCP_URL', endpoint)
    monkeypatch.setenv('CHARTS_SERVER_TOKENS', 'synthetic-token')
    monkeypatch.setitem(namespace, 'read_project', lambda _: (root, {}, {version: {'rowCount': 1}}))
    def forbidden_batches(*_):
        raise AssertionError('Already staged rows must not be read or sent')
    monkeypatch.setitem(namespace, 'batches', forbidden_batches)
    class Http:
        def __init__(self, **_): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
    class Session:
        def __init__(self, *_): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def initialize(self): pass
    @asynccontextmanager
    async def stream(*_, **__):
        yield None, None, None
    calls = []
    async def call(_session, _project, tool, _args):
        calls.append(tool)
        return {'dashboards': []} if tool == 'dashboard_list' else {'state': 'complete'}
    monkeypatch.setitem(namespace, 'httpx', SimpleNamespace(AsyncClient=Http))
    monkeypatch.setitem(namespace, 'ClientSession', Session)
    monkeypatch.setitem(namespace, 'streamable_http_client', stream)
    monkeypatch.setitem(namespace, 'call_tool', call)
    args = SimpleNamespace(manifest=str(manifest_path), project='fixture', state=str(state_path), resume_staged=version)
    asyncio.run(run(args))
    assert calls == ['dashboard_list', 'dataset_transfer_finish']
    assert json.loads(state_path.read_text())['staged'] == [version]

