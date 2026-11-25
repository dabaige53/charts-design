"""Self-hosted server: real uvicorn, Streamable HTTP MCP and scoped data APIs."""
import asyncio
import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

pytest.importorskip('mcp', reason='Install the optional official MCP SDK for server integration tests')
pytest.importorskip('uvicorn', reason='uvicorn ships with the MCP SDK')

from dashboard_runtime.model import DashboardError
from dashboard_runtime.server import (RemoteServer, ServerSettings, Signer,
                                      WorkspaceProjects, create_app, load_secret)

TOKEN = 'server-test-token-0123456789'


def settings(tmp_path, **extra):
    return ServerSettings(workspace=tmp_path / 'ws', runtime=tmp_path / 'ws' / '.runtime', tokens=(TOKEN,), port=8000, **extra)


# @wu-test type=integration | scope=服务器发布健康检查 | protects=云端发布返回旧版本标记或本地运行要求云端发布参数
def test_health_reports_release_identity_only_when_configured(tmp_path, monkeypatch):
    from starlette.testclient import TestClient

    monkeypatch.delenv('CHARTS_RELEASE_VERSION', raising=False)
    monkeypatch.delenv('CHARTS_RELEASE_COMMIT', raising=False)
    with TestClient(create_app(RemoteServer(settings(tmp_path)))) as client:
        response = client.get('/health')
        assert response.status_code == 200
        assert response.json()['ok'] is True
        assert 'release' not in response.json()
        monkeypatch.setenv('CHARTS_RELEASE_VERSION', '1.2.1')
        monkeypatch.setenv('CHARTS_RELEASE_COMMIT', 'a' * 40)
        response = client.get('/health')
        assert response.json()['release'] == {'version': '1.2.1', 'commit': 'a' * 40}
        assert response.headers['cache-control'] == 'no-store'


# @wu-test type=integration | scope=COS editable content reads | protects=重复读取当前草稿或用错误修订授权数据文件
def test_edit_asset_authorizes_current_or_requested_revision(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from starlette.testclient import TestClient

    from dashboard_runtime import cos_view, versions

    server = RemoteServer(settings(tmp_path))
    reads = []

    def get(board, hydrate):
        reads.append(('draft', board))
        assert not hydrate
        return {'id': board, 'revision': 3}

    def history(_versions, board, revision):
        reads.append(('history', board, revision))
        return {'id': board, 'revision': revision}

    def asset(_store, doc, object_id, name):
        assert (object_id, name) == ('fixture', 'rows.json.gz')
        return str(doc['revision']).encode()

    app = create_app(server)
    connect = server.projects.service('default').store.connect
    store = SimpleNamespace(get=get, cos_enabled=True, connect=connect)
    monkeypatch.setattr(server.projects, 'service', lambda _name: SimpleNamespace(store=store))
    monkeypatch.setattr(versions.Versions, 'read', history)
    monkeypatch.setattr(cos_view, 'authorized_file', asset)
    url = '/api/v1/p/default/content/board/{}/fixture/rows.json.gz'
    with TestClient(app) as client:
        assert client.get(url.format(3)).status_code == 401
        headers = {'Authorization': 'Bearer ' + TOKEN}
        current = client.get(url.format(3), headers=headers)
        assert (current.status_code, current.content) == (200, b'3')
        assert reads == [('draft', 'board')]
        saved = client.get(url.format(2), headers=headers)
        assert (saved.status_code, saved.content) == (200, b'2')
        assert reads == [('draft', 'board'), ('draft', 'board'), ('history', 'board', 2)]


# @wu-test type=boundary | scope=分享链接签名 | protects=篡改过期或错类型令牌被接受
def test_signer_rejects_tampering_kind_and_expiry():
    signer = Signer(b'k' * 32)
    token = signer.sign({'k': 'share', 'p': 'sales', 'd': 'demo', 'exp': int(time.time()) + 60})
    verified = signer.verify(token, 'share')
    assert verified is not None and verified['d'] == 'demo'
    assert signer.verify(token, 'file') is None
    body, mac = token.split('.')
    assert signer.verify(body + '.' + mac[:-2] + 'AA', 'share') is None
    assert Signer(b'x' * 32).verify(token, 'share') is None
    assert signer.verify(signer.sign({'k': 'share', 'exp': int(time.time()) - 1}), 'share') is None
    assert signer.verify('not-a-token', 'share') is None


# @wu-test type=boundary | scope=远程项目路径 | protects=项目参数逃逸工作区或非法名称被接受
def test_projects_stay_inside_the_workspace(tmp_path):
    projects = WorkspaceProjects(settings(tmp_path))
    assert projects.name(None) == 'default'
    assert projects.name('sales') == 'sales'
    assert projects.name(str(tmp_path / 'ws' / 'sales')) == 'sales'
    for value in ('/etc', str(tmp_path / 'elsewhere'), str(tmp_path / 'ws' / 'a' / 'b')):
        with pytest.raises(DashboardError) as error:
            projects.name(value)
        assert error.value.code == 'PROJECT_OUTSIDE_WORKSPACE'
    for value in ('../escape', 'a/b', '.hidden', '', 'x' * 65, 3):
        with pytest.raises(DashboardError):
            projects.name(value)


# @wu-test type=boundary | scope=服务器配置 | protects=无令牌或非回环地址免认证启动及签名密钥权限过宽
def test_configuration_requires_tokens_and_loopback_trials(tmp_path):
    with pytest.raises(DashboardError, match='bearer token'):
        RemoteServer(ServerSettings(workspace=tmp_path / 'ws', runtime=tmp_path / 'rt'))
    with pytest.raises(DashboardError, match='at least 16'):
        ServerSettings(workspace=tmp_path / 'ws', runtime=tmp_path / 'rt', tokens=('short',))
    with pytest.raises(DashboardError, match='loopback'):
        ServerSettings(workspace=tmp_path / 'ws', runtime=tmp_path / 'rt', host='0.0.0.0', insecure_no_auth=True)
    first = ServerSettings(workspace=tmp_path / 'ws', runtime=tmp_path / 'rt', tokens=(TOKEN,))
    second = ServerSettings(workspace=tmp_path / 'ws', runtime=tmp_path / 'rt', tokens=(TOKEN,))
    assert first.secret == second.secret and len(first.secret) == 32
    assert oct((tmp_path / 'rt' / 'server-secret').stat().st_mode & 0o777) == '0o600'


# @wu-test type=boundary | scope=签名密钥并发初始化 | protects=多个副本首次启动失败或读取不同和未写完的密钥
def test_concurrent_startup_uses_one_complete_signing_key(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    path = tmp_path / 'runtime' / 'server-secret'
    readers = threading.Barrier(8, timeout=10)
    read_bytes = Path.read_bytes

    def simultaneous_first_read(target):
        try:
            return read_bytes(target)
        except FileNotFoundError:
            if target == path:
                readers.wait()
            raise

    monkeypatch.setattr(Path, 'read_bytes', simultaneous_first_read)
    with ThreadPoolExecutor(max_workers=8) as pool:
        keys = list(pool.map(lambda _: load_secret(path), range(8)))
    assert len(keys[0]) == 32
    assert all(value == keys[0] for value in keys)
    assert read_bytes(path) == keys[0]
    assert list(path.parent.iterdir()) == [path]


class Running:
    """uvicorn in a background thread."""

    def __init__(self, app, port):
        import uvicorn
        self.server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error', access_log=False))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        for _ in range(200):
            if self.server.started:
                return self
            time.sleep(0.05)
        raise RuntimeError('server did not start')

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(10)


def post(url, body, token=None):
    headers = {'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + token} if token else {})}
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b'{}')


def start(tmp_path, port):
    from dashboard_runtime.demo import executive_document, report_document
    config = ServerSettings(workspace=tmp_path / 'ws', runtime=tmp_path / 'ws' / '.runtime', tokens=(TOKEN,), port=port)
    server = RemoteServer(config)
    service = server.projects.service('sales')
    service.call('dashboard_create', {'dashboardId': 'exec', 'document': executive_document('exec')})
    service.call('dashboard_create', {'dashboardId': 'report', 'document': report_document('report')})
    service.call('dashboard_create', {'dashboardId': 'other', 'title': 'Other'})
    return server


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


# @wu-test type=integration | scope=统一 MCP 路由和首次提交 | protects=同名项目写错后端、首次提交重试覆盖看板或旧令牌取得双端权限
def test_unified_mcp_pins_backend(tmp_path, monkeypatch):
    from pydantic import AnyUrl
    from dashboard_runtime.backend_routing import BackendRoutes
    from dashboard_runtime.remote_client import connect

    cloud_port = free_port()
    cloud = start(tmp_path / 'cloud', cloud_port)
    cloud_base = f'http://127.0.0.1:{cloud_port}'
    cloud_app = create_app(cloud)
    entry_token = 'unified-test-token-distinct-from-both-backends'
    monkeypatch.setenv('CHARTS_UNIFIED_TOKEN', entry_token)
    monkeypatch.setenv('CHARTS_CLOUDBASE_URL', 'https://upstream.example')
    monkeypatch.setenv('CHARTS_CLOUDBASE_MCP_TOKEN', TOKEN)
    port = free_port()
    local = start(tmp_path / 'server', port)
    base = f'http://127.0.0.1:{port}'
    import dashboard_runtime.backend_routing as routing
    configure = routing.configured_routes

    def loopback(server):
        routes = configure(server)
        assert isinstance(routes, BackendRoutes)
        routes.base_url = cloud_base
        return routes

    monkeypatch.setattr(routing, 'configured_routes', loopback)

    async def check():
        async with connect(base + '/unified/mcp', entry_token) as client:
            async def call(tool, project, **args):
                result = await client.call_tool(tool, {'projectRoot': project, **args})
                assert result.structuredContent is not None
                return result.structuredContent

            assert (await call('dashboard_list', 'sales'))['error']['code'] == 'BACKEND_REQUIRED'
            assert (await call('dashboard_list', 'sales', backend='cloudbase'))['dashboards']
            assert (await call('dashboard_list', 'sales', backend='server'))['error']['code'] == 'BACKEND_CONFLICT'
            assert (await call('dashboard_create', 'fresh', dashboardId='board', title='New'))['error']['code'] == 'BACKEND_REQUIRED'
            assert (await call('dashboard_create', 'fresh', backend='cloudbase', dashboardId='board', title='New'))['revision'] == 1
            assert (await call('dashboard_list', 'fresh'))['dashboards'][0]['id'] == 'board'
            report = '# Quarterly report\n' + 'Quarterly results.\n' * 4000
            saved = await call('dashboard_submit', 'fresh', dashboardId='board', expectedRevision=1,
                                operations=[{'op': 'set_report_markdown', 'value': report}])
            assert saved['ok']
            packed = await call('dashboard_get', 'fresh', dashboardId='board')
            from mcp.types import TextResourceContents
            resource = (await client.read_resource(AnyUrl(packed['transport']['resourceUri']))).contents[0]
            assert isinstance(resource, TextResourceContents)
            assert json.loads(resource.text)['document']['manifest']['report']['markdown'] == report
            assert not local.projects.exists('fresh')
            initial = {'dashboardId': 'new', 'createTitle': 'Initial', 'operations': [
                {'op': 'set_title', 'value': 'Submitted'}]}
            assert (await call('dashboard_submit', 'first-submit', backend='server', **initial))['ok']
            duplicate = await call('dashboard_submit', 'first-submit', **initial)
            assert duplicate['error']['code'] == 'ALREADY_EXISTS'
            assert (await call('dashboard_get', 'first-submit', dashboardId='new'))['document']['revision'] == 2
            assert (await call('dashboard_create', 'local-new', backend='server', dashboardId='board', title='Local'))['revision'] == 1
            assert not cloud.projects.exists('local-new')

    with Running(cloud_app, cloud_port), Running(create_app(local), port):
        assert post(base + '/unified/mcp', {}, TOKEN)[0] == 401
        assert post(base + '/mcp', {}, entry_token)[0] == 401
        asyncio.run(check())

    async def after_restart():
        async with connect(base + '/unified/mcp', entry_token) as client:
            async def read(project):
                result = await client.call_tool('dashboard_list', {'projectRoot': project})
                assert result.structuredContent is not None
                return result.structuredContent
            assert (await read('fresh'))['error']['code'] == 'BACKEND_UNAVAILABLE'
            assert (await read('unbound'))['error']['code'] == 'CATALOG_UNAVAILABLE'
            assert (await read('local-new'))['dashboards'][0]['id'] == 'board'
            assert not local.projects.exists('fresh')
    with Running(create_app(local), port):
        asyncio.run(after_restart())


# @wu-test type=integration | scope=远程MCP与分享链接 | protects=远程发现清单不一致或分享链接越权与撤销后仍可用
@pytest.mark.filterwarnings('ignore:Use `streamable_http_client`:DeprecationWarning')
def test_remote_mcp_and_scoped_viewer_api(tmp_path):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from pydantic import AnyUrl
    port = free_port()
    server = start(tmp_path, port)
    with Running(create_app(server), port):
        base = f'http://127.0.0.1:{port}'

        async def session():
            async with streamablehttp_client(base + '/mcp', headers={'Authorization': 'Bearer ' + TOKEN}) as (read, write, _):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                    names = tools.keys()
                    from dashboard_runtime.tool_contract import AUTHOR_TOOLS
                    assert set(names) == AUTHOR_TOOLS
                    assert 'dashboard_export_open' not in names
                    from mcp.types import TextResourceContents
                    guide = (await client.read_resource(AnyUrl('charts://contract'))).contents[0]
                    assert isinstance(guide, TextResourceContents)
                    contract = json.loads(guide.text)
                    assert contract['tools'] == {name: tool.model_dump(by_alias=True, exclude_none=True, exclude={'name'})
                        for name, tool in tools.items()}
                    assert 'Project name on this server' in contract['projectRouting']['description']
                    assert {'runtime_keepalive', 'dashboard_share_revoke'} <= contract['clientTools'].keys()
                    outside = await client.call_tool('dashboard_list', {'projectRoot': '/etc'})
                    assert outside.isError and outside.structuredContent is not None
                    assert outside.structuredContent['error']['code'] == 'PROJECT_OUTSIDE_WORKSPACE'
                    created = await client.call_tool('dashboard_create', {'projectRoot': 'fresh', 'dashboardId': 'blank', 'title': 'Blank'})
                    assert not created.isError and created.structuredContent is not None
                    assert created.structuredContent['projectRoot'] == 'fresh'
                    assert created.structuredContent['dashboardId'] == 'blank'
                    assert created.structuredContent['revision'] == 1
                    assert 'document' not in created.structuredContent
                    preview = await client.call_tool('dashboard_preview', {'projectRoot': 'sales', 'dashboardId': 'exec'})
                    assert not preview.isError and preview.structuredContent is not None
                    assert preview.structuredContent['document']['id'] == 'exec'
                    shared = await client.call_tool('dashboard_share', {
                        'projectRoot': 'sales', 'dashboardId': 'exec', 'access': 'view',
                    })
                    assert not shared.isError and shared.structuredContent is not None
                    assert shared.structuredContent['url'].startswith(base + '/view/sales/exec#token=')
                    export = await client.call_tool('dashboard_export', {'projectRoot': 'sales', 'dashboardId': 'exec', 'format': 'json'})
                    assert not export.isError and export.structuredContent is not None
                    return shared.structuredContent['url'], export.structuredContent

        preview_url, export = asyncio.run(session())
        token = preview_url.split('#token=')[1]
        api = base + '/api/v1/p/sales/tools/'
        status, value = post(api + 'dashboard_get', {'dashboardId': 'exec'}, token)
        assert status == 200 and value['document']['id'] == 'exec'
        assert post(api + 'dashboard_get', {'dashboardId': 'other'}, token)[0] == 403
        assert post(api + 'dashboard_patch', {'dashboardId': 'exec', 'expectedRevision': 1, 'operations': [{'op': 'set_title', 'value': 'x'}]}, token)[0] == 403
        assert post(api + 'dashboard_submit', {'dashboardId': 'exec', 'expectedRevision': 1}, token)[0] == 403
        assert post(api + 'dashboard_publish', {'dashboardId': 'exec'}, token)[0] == 403
        assert post(api + 'dashboard_list', {}, token)[1]['dashboards'] == [{'id': 'exec', 'revision': 1, 'title': value['document']['manifest']['title']}]
        info = post(api + 'runtime_info', {}, token)[1]
        assert 'moduleRoot' not in info and 'processId' not in info and info['projectRoot'] == 'sales'
        assert post(base + '/api/v1/p/fresh/tools/dashboard_get', {'dashboardId': 'blank'}, token)[0] == 401
        assert post(api + 'dashboard_get', {'dashboardId': 'exec'})[0] == 401
        # Signed download of the server-side export; the token is not a path.
        with urllib.request.urlopen(export['export']['downloadUrl']) as response:
            assert json.loads(response.read())['id'] == 'exec'
        assert urllib.request.urlopen(base + '/health').status == 200
        with pytest.raises(urllib.error.HTTPError) as unauthorized:
            urllib.request.urlopen(urllib.request.Request(base + '/mcp', data=b'{}', headers={'Content-Type': 'application/json'}))
        assert unauthorized.value.code == 401
        # Revoking invalidates links already issued.
        status, edit = post(base + '/api/v1/share', {'project': 'sales', 'dashboardId': 'exec', 'access': 'edit'}, TOKEN)
        assert status == 200 and '/edit/sales/exec#token=' in edit['url']
        edit_token = edit['url'].split('#token=')[1]
        assert post(api + 'dashboard_patch', {'dashboardId': 'exec', 'expectedRevision': 1, 'operations': [{'op': 'set_title', 'value': 'Edited by link'}]}, edit_token)[0] == 200
        published = post(api + 'dashboard_publish', {'dashboardId': 'exec', 'expectedRevision': 2}, edit_token)[1]
        assert published['publishedRevision'] == published['versionStatus']['savedRevision'] == 2
        for tool in ('dataset_import', 'query_execute', 'dataset_attach', 'dashboard_create', 'dashboard_export_open',
                     'dataset_transfer_chunk', 'dataset_transfer_finish', 'dataset_transfer_status', 'dataset_transfer_cleanup'):
            status, denied = post(api + tool, {'dashboardId': 'exec'}, edit_token)
            assert status == 403 and denied['error']['code'] == 'FORBIDDEN', (tool, denied)
        server.state.revoke('sales', 'exec')
        assert post(api + 'dashboard_get', {'dashboardId': 'exec'}, token)[0] == 401
        assert post(api + 'dashboard_get', {'dashboardId': 'exec'}, edit_token)[0] == 401


# @wu-test type=integration | scope=网页与构建资源 | protects=网页缺少新应用入口或发布资源不可读取
def test_web_pages_and_assets_serve_the_shared_build(tmp_path):
    port = free_port()
    server = start(tmp_path, port)
    with Running(create_app(server), port):
        for path in ('/', '/assets/app.js', '/view/sales/exec', '/view/sales/report', '/edit/sales/exec'):
            with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}') as response:
                assert response.status == 200
                body = response.read()
                assert body
                assert response.headers['Content-Type'].startswith('text/javascript' if path.endswith('.js') else 'text/html')
                if not path.endswith('.js'):
                    assert b'window.__chartsBoot=' in body


# @wu-test type=boundary | scope=查看接口 | protects=超大请求体被读取或分享链接读取其他看板的缓存响应
def test_viewer_api_refuses_oversized_bodies_before_reading(tmp_path):
    import http.client
    port = free_port()
    server = start(tmp_path, port)
    token = server.links.share('sales', 'exec', 'view')['url'].split('#token=')[1]
    transfer = server.projects.service('sales').transport.pack(
        {'dashboardId': 'report', 'rows': ['Other dashboard content'] * 4000}, 'dashboard_view')['transport']
    with Running(create_app(server), port):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        connection.request('POST', '/api/v1/p/sales/tools/dashboard_get', body=b'{}',
                           headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token, 'Content-Length': str(64 * 1024 * 1024)})
        response = connection.getresponse()
        assert response.status == 413
        assert json.loads(response.read())['error']['code'] == 'PAYLOAD_TOO_LARGE'
        status, _ = post(f'http://127.0.0.1:{port}/api/v1/p/sales/tools/runtime_result_chunk',
                         {'requestId': transfer['requestId'], 'index': 0}, token)
        assert status == 403

# @wu-test type=boundary | scope=多页面签名分享 | protects=分享页面被遗漏或未选页面可访问或撤销后仍可访问
def test_multi_page_share_scope_and_revocation(tmp_path):
    from typing import cast

    server = RemoteServer(settings(tmp_path))
    service = server.projects.service('sales')
    for board in ('first', 'second', 'private'):
        service.call('dashboard_create', {'dashboardId': board, 'title': board})
    result = server.profile.call('dashboard_share', {'dashboardId': 'first', 'dashboardIds': ['second']}, service)
    assert result is not None
    token = result['url'].split('#token=')[1]
    principal = server.principal(token, 'sales')
    assert principal is not None
    dashboards = cast(list[dict], server.call_viewer('sales', 'dashboard_list', {}, principal)['dashboards'])
    assert {item['id'] for item in dashboards} == {'first', 'second'}
    document = cast(dict, server.call_viewer('sales', 'dashboard_get', {'dashboardId': 'second'}, principal)['document'])
    assert document['id'] == 'second'
    with pytest.raises(DashboardError) as error:
        server.call_viewer('sales', 'dashboard_get', {'dashboardId': 'private'}, principal)
    assert error.value.code == 'FORBIDDEN'
    edit_principal = server.principal(server.links.share('sales', 'first', 'edit', dashboards=['second'])['url'].split('#token=')[1], 'sales')
    assert edit_principal is not None
    with pytest.raises(DashboardError) as error:
        server.call_viewer('sales', 'dashboard_share_publish', {'dashboardId': 'first', 'pages': [{'dashboardId': 'private'}]},
                           edit_principal)
    assert error.value.code == 'FORBIDDEN'
    server.state.revoke('sales', 'second')
    assert server.principal(token, 'sales') is None


# @wu-test type=integration | scope=签名编辑链接的鉴权 | protects=慢数据库查询阻塞其他 HTTP 请求
def test_slow_share_authentication_does_not_block_health(tmp_path, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    server = RemoteServer(settings(tmp_path))
    service = server.projects.service('sales')
    service.call('dashboard_create', {'dashboardId': 'board', 'title': 'Board'})
    token = server.links.share('sales', 'board', 'edit')['url'].split('#token=')[1]
    entered = threading.Event()
    release = threading.Event()
    match = server.state.generations_match

    def slow_match(project, pages):
        entered.set()
        assert release.wait(timeout=4), 'Health check could not run during share authentication'
        return match(project, pages)

    monkeypatch.setattr(server.state, 'generations_match', slow_match)

    async def check():
        async with AsyncClient(transport=ASGITransport(app=create_app(server)), base_url='http://test.local') as client:
            pending = asyncio.create_task(client.post('/api/v1/p/sales/tools/dashboard_annotations',
                json={'dashboardId': 'board', 'includeTargets': False},
                headers={'Authorization': 'Bearer ' + token}))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                assert (await client.get('/health')).status_code == 200
                assert not pending.done()
            finally:
                release.set()
                response = await pending
            assert response.status_code == 200

    asyncio.run(check())
