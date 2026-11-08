"""Self-hosted server: real uvicorn, Streamable HTTP MCP client and Chromium."""
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
from dashboard_runtime.server import (EDIT_TOOLS, VIEW_TOOLS, RemoteServer, ServerSettings, Signer,
                                      WorkspaceProjects, create_app)

TOKEN = 'server-test-token-0123456789'


def settings(tmp_path, **extra):
    return ServerSettings(workspace=tmp_path / 'ws', runtime=tmp_path / 'ws' / '.runtime', tokens=(TOKEN,), port=8000, **extra)


# @wu-test type=boundary | scope=分享链接签名 | protects=篡改过期或错类型令牌被接受 | debt=D1
def test_signer_rejects_tampering_kind_and_expiry():
    signer = Signer(b'k' * 32)
    token = signer.sign({'k': 'share', 'p': 'sales', 'd': 'demo', 'exp': int(time.time()) + 60})
    assert signer.verify(token, 'share')['d'] == 'demo'
    assert signer.verify(token, 'file') is None
    body, mac = token.split('.')
    assert signer.verify(body + '.' + mac[:-2] + 'AA', 'share') is None
    assert Signer(b'x' * 32).verify(token, 'share') is None
    assert signer.verify(signer.sign({'k': 'share', 'exp': int(time.time()) - 1}), 'share') is None
    assert signer.verify('not-a-token', 'share') is None


# @wu-test type=boundary | scope=远程项目路径 | protects=项目参数逃逸工作区或非法名称被接受 | debt=D1
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


# @wu-test type=boundary | scope=服务器配置 | protects=无令牌或非回环地址免认证启动及签名密钥权限过宽 | debt=D1
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


# @wu-test type=boundary | scope=分享链接权限 | protects=只读或编辑链接可调用越权工具 | debt=D1,D3
def test_view_links_cannot_write():
    assert 'dashboard_patch' not in VIEW_TOOLS and 'dashboard_patch' in EDIT_TOOLS
    assert not {'dataset_import', 'query_execute', 'dataset_attach', 'dashboard_create', 'dashboard_export_open'} & EDIT_TOOLS


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


# @wu-test type=integration | scope=远程MCP与分享链接 | protects=跨项目读写或只读链接写入或撤销后链接仍可用 | debt=D1
@pytest.mark.filterwarnings('ignore:Use `streamable_http_client`:DeprecationWarning')
def test_remote_mcp_preview_link_and_scoped_viewer_api(tmp_path):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    port = free_port()
    server = start(tmp_path, port)
    with Running(create_app(server), port):
        base = f'http://127.0.0.1:{port}'

        async def session():
            async with streamablehttp_client(base + '/mcp', headers={'Authorization': 'Bearer ' + TOKEN}) as (read, write, _):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    names = {tool.name for tool in (await client.list_tools()).tools}
                    assert {'dashboard_share', 'dashboard_share_revoke', 'dashboard_preview'} <= names
                    assert 'dashboard_export_open' not in names
                    outside = await client.call_tool('dashboard_list', {'projectRoot': '/etc'})
                    assert outside.isError and outside.structuredContent['error']['code'] == 'PROJECT_OUTSIDE_WORKSPACE'
                    created = await client.call_tool('dashboard_create', {'projectRoot': 'fresh', 'dashboardId': 'blank', 'title': 'Blank'})
                    assert not created.isError and created.structuredContent['projectRoot'] == 'fresh'
                    preview = await client.call_tool('dashboard_preview', {'projectRoot': 'sales', 'dashboardId': 'exec'})
                    assert not preview.isError
                    data = preview.structuredContent
                    assert data['previewUrl'].startswith(base + '/view/sales/exec#token=')
                    assert json.loads(preview.content[0].text)['previewUrl'] == data['previewUrl']
                    export = await client.call_tool('dashboard_export', {'projectRoot': 'sales', 'dashboardId': 'exec', 'format': 'json'})
                    return data['previewUrl'], export.structuredContent

        preview_url, export = asyncio.run(session())
        token = preview_url.split('#token=')[1]
        api = base + '/api/v1/p/sales/tools/'
        status, value = post(api + 'dashboard_get', {'dashboardId': 'exec'}, token)
        assert status == 200 and value['document']['id'] == 'exec'
        assert post(api + 'dashboard_get', {'dashboardId': 'other'}, token)[0] == 403
        assert post(api + 'dashboard_patch', {'dashboardId': 'exec', 'expectedRevision': 1, 'operations': [{'op': 'set_title', 'value': 'x'}]}, token)[0] == 403
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
        server.state.revoke('sales', 'exec')
        assert post(api + 'dashboard_get', {'dashboardId': 'exec'}, token)[0] == 401
        assert post(api + 'dashboard_get', {'dashboardId': 'exec'}, edit_token)[0] == 401
        page = urllib.request.urlopen(base + '/view/sales/exec')
        assert "script-src 'self' 'sha256-" in page.headers['Content-Security-Policy']
        assert page.headers['Referrer-Policy'] == 'no-referrer'


# @wu-test type=integration | scope=分享页面 | protects=只读页出现编辑入口或令牌留在地址栏或图表不渲染 | debt=D1
def test_share_pages_render_dashboard_and_report_read_only(tmp_path):
    from dashboard_runtime.assets import DIST
    if not (DIST / 'app.js').exists():
        pytest.skip('Build runtime-ui before browser acceptance testing')
    from playwright.sync_api import sync_playwright
    port = free_port()
    server = start(tmp_path, port)
    with Running(create_app(server), port):
        links = {board: server.links.share('sales', board, 'view')['url'] for board in ('exec', 'report')}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
            page.goto(links['exec'])
            page.locator('.grid-stack canvas').first.wait_for()
            assert page.get_by_role('button', name='编辑', exact=True).count() == 0
            assert '只读预览' in page.locator('#notice').inner_text()
            assert '#token=' not in page.url
            page.goto(links['report'])
            figure = page.locator('.markdown-chart').first
            figure.wait_for()
            figure.scroll_into_view_if_needed()
            # Report figures in project mode receive progressive data by component ID.
            page.locator('.markdown-chart canvas').first.wait_for()
            assert errors == []
            browser.close()


# @wu-test type=boundary | scope=查看接口 | protects=超大请求体被读取或分块接口对链接开放 | debt=D1
def test_viewer_api_refuses_oversized_bodies_before_reading(tmp_path):
    import http.client
    port = free_port()
    server = start(tmp_path, port)
    token = server.links.share('sales', 'exec', 'view')['url'].split('#token=')[1]
    with Running(create_app(server), port):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        connection.request('POST', '/api/v1/p/sales/tools/dashboard_get', body=b'{}',
                           headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token, 'Content-Length': str(64 * 1024 * 1024)})
        response = connection.getresponse()
        assert response.status == 413
        assert json.loads(response.read())['error']['code'] == 'PAYLOAD_TOO_LARGE'
        status, _ = post(f'http://127.0.0.1:{port}/api/v1/p/sales/tools/runtime_result_chunk', {'requestId': 'x', 'index': 0}, token)
        assert status == 403
