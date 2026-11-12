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


# @wu-test type=integration | scope=remote-project upload/read | protects=正式命令返回未完成引用或下载时丢失大型组件配置
def test_remote_cli_upload_and_complete_read(tmp_path, monkeypatch, capsys):
    import asyncio
    from contextlib import asynccontextmanager
    import json
    from pathlib import Path
    import runpy
    from types import SimpleNamespace
    from dashboard_runtime.transport import ResultTransport
    from dashboard_runtime.tool_contract import TOOLS

    run = runpy.run_path(str(Path(__file__).parents[2] / 'bin' / 'remote-project.py'))['run']
    root = tmp_path / 'source'
    rows, fields = [{'value': 1}], {'value': {'type': 'number'}}
    rows_path, fields_path = tmp_path / 'rows.jsonl', tmp_path / 'fields.json'
    rows_path.write_text(json.dumps(rows[0]) + '\n')
    fields_path.write_text(json.dumps(fields))
    data = CloudData(tmp_path / 'remote', MemoryDatabase(), 'fixture')
    storage = MemoryStorage()
    monkeypatch.setattr(data, 'transfer_storage', storage)
    transport = ResultTransport(tmp_path)
    document = {'revision': 7, 'manifest': {'components': {'trend': {'description': '字' * 50000}}}}
    class Session:
        async def list_tools(self, cursor=None):
            return SimpleNamespace(tools=[SimpleNamespace(name=name, inputSchema=schema)
                                          for name, (_, schema) in TOOLS.items()], nextCursor=None)
        async def call_tool(self, name, args):
            if name == 'dashboard_get':
                result = transport.pack({'document': document}, name)
            elif name == 'runtime_result_chunk':
                result = transport.chunk(args)
            elif name == 'dataset_transfer_chunk':
                result = data.transfer_chunk(args['uploadId'], args['ref'], args['part'], args['rows'])
            elif name == 'dataset_transfer_finish':
                result = data.transfer_finish(args['uploadId'], args['ref'])
            else:
                assert name == 'dataset_transfer_status'
                result = data.transfer_status(args['uploadId'], args['ref'], args.get('parts'))
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
                           state=str(tmp_path / 'state.json'), concurrency=4, check_only=True)
    asyncio.run(run(args))
    assert not data.database.refs and not storage.objects
    assert not output.exists()
    args.check_only = False
    asyncio.run(run(args))
    ref = json.loads(output.read_text())
    assert list(data.iter_rows(ref)) == rows
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


# @wu-test type=integration | scope=remote_client staged recovery | protects=旧版已完整暂存的传输恢复时再次发送所有数据行
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
        if name == 'dataset_transfer_status':
            return data.transfer_status(upload, ref)
        assert name == 'dataset_transfer_finish'
        return data.transfer_finish(upload, ref)
    client = TransferClient(call, root, endpoint, 'fixture', state, emit=lambda _: None)
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
