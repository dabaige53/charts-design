from contextlib import contextmanager
import io
import json
import threading
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
import uuid
import zipfile

import pytest

from dashboard_runtime.demo import document
from dashboard_runtime.http_server import RuntimeHTTPServer, annotation_response
from dashboard_runtime.local_shares import LocalShares
from dashboard_runtime.mcp_server import McpProfile
from dashboard_runtime.model import DashboardError
from dashboard_runtime.service import Service


@contextmanager
def running(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(base, path, token, body=None):
    headers = {'Authorization': 'Bearer ' + token}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    with urlopen(req, timeout=5) as response:
        return json.load(response)


def note(key='note', component: str | None = 'trend'):
    return {'id': key, 'componentId': component, 'text': '请核对这个位置', 'createdAt': '2026-11-27T00:00:00Z',
            'anchor': {'scope': 'component' if component else 'text', 'kind': 'element',
                       'quote': '季度结论', 'occurrence': 0,
                       'rect': {'x': 0.1, 'y': 0.2, 'width': 0.2, 'height': 0.1}}}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr('dashboard_runtime.assets.require_preview', lambda: None)
    monkeypatch.setattr('dashboard_runtime.http_server.render_html', lambda *args, **kwargs: json.dumps(kwargs.get('boot_state', {})))
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.store.create('board', 'A', document('board'))
    return service


# @wu-test type=integration | scope=本机编辑、预览启动与批注 HTTP | protects=启动结果丢失项目标识、批注版本错位、刷新丢失、重复追加或冒充验证账户
def test_local_preview_annotations_survive_reload_without_content_revision(workspace):
    service = workspace
    service.store.mutate('board', 1, [{'op': 'remove_component', 'id': 'trend'}])
    server = RuntimeHTTPServer(service, 0, token='author-secret')
    with running(server) as base:
        links = request(base, '/api/browser-links/board', server.token)
        preview_token = parse_qs(urlparse(links['viewUrl']).fragment)['token'][0]
        bootstrap = request(base, '/view/board', '')
        assert bootstrap['readOnly'] is True and bootstrap['annotationAccess']['canAnnotate'] is True
        assert server.token not in json.dumps(bootstrap)
        preview = request(base, '/api/tools/dashboard_get', preview_token, {'dashboardId': 'board'})
        assert preview['document']['revision'] == 1
        editor_boot = request(base, '/edit/board', '')
        draft = request(base, '/api/tools/dashboard_get', server.token, {'dashboardId': 'board'})
        assert draft['projectRoot'] == editor_boot['projectRoot'] == preview['projectRoot'] == bootstrap['projectRoot']
        assert draft['document']['revision'] == 2
        payload = {'revision': 1, 'authorName': '  数据读者  ',
                   'append': {**note(), 'author': {'name': '伪造账户', 'verified': True, 'id': 'account'}}}
        for invalid_name in ('x' * 81, {'name': 'not a string'}):
            with pytest.raises(HTTPError) as invalid:
                request(base, '/api/annotations/board', preview_token, {**payload, 'authorName': invalid_name})
            assert invalid.value.code == 400
        saved = request(base, '/api/annotations/board', preview_token, payload)
        assert saved['targetRevision'] == 1 and saved['revision'] == 2
        assert saved['annotation']['context']['designRevision'] == 1
        assert saved['annotation']['author'] == {'name': '数据读者', 'verified': False}
        repeated = request(base, '/api/annotations/board', preview_token, payload)
        assert repeated == saved
        read = request(base, '/api/annotations/board?revision=1', preview_token)
        assert len(read['annotations']) == 1 and read['targets']['note']['componentExists'] is True
        assert read['canManageAnnotations'] is False
        assert read['author'] == {'name': '访客', 'verified': False}
        assert read['annotations'][0]['author'] == saved['annotation']['author']
    reopened = Service(service.store.runtime_root, project_root=service.project_root)
    assert reopened.store.revision('board') == 2
    assert len(reopened.store.history('board')) == 1
    persisted = reopened.store.annotation_state('board')['annotations'][0]
    assert persisted['context']['designRevision'] == 1
    assert persisted['author'] == {'name': '数据读者', 'verified': False}
    with reopened.store.connect() as db:
        assert db.execute('SELECT count(*) FROM annotation_events WHERE board_id=?', ('board',)).fetchone()[0] == 1


# @wu-test type=boundary | scope=本机预览能力令牌 | protects=预览批注权限获得内容编辑发布权限或跨看板管理权限
def test_local_preview_scope_rejects_content_version_and_other_board_writes(workspace):
    workspace.store.create('other', 'Other')
    server = RuntimeHTTPServer(workspace, 0, token='author-secret')
    with running(server) as base:
        token = server.preview_token('board')
        for path, body in [
            ('/api/tools/dashboard_patch', {'dashboardId': 'board', 'expectedRevision': 1, 'operations': [{'op': 'set_title', 'value': 'Changed'}]}),
            ('/api/tools/dashboard_checkpoint', {'dashboardId': 'board', 'expectedRevision': 1}),
            ('/api/tools/dashboard_publish', {'dashboardId': 'board'}),
            ('/api/tools/dashboard_annotations_update', {'dashboardId': 'board', 'append': note()}),
            ('/api/annotations/other', {'append': note()}),
            ('/api/annotations/board', {'expectedAnnotations': [], 'annotations': []}),
        ]:
            with pytest.raises(HTTPError) as rejected:
                request(base, path, token, body)
            assert rejected.value.code == 403
        assert request(base, '/api/tools/dashboard_list', token, {})['dashboards'][0]['id'] == 'board'
        with pytest.raises(HTTPError) as denied:
            request(base, '/api/browser-links/other', token)
        assert denied.value.code == 403
        assert 'editUrl' not in request(base, '/api/browser-links/board', token)
        assert workspace.store.revision('board') == 1


# @wu-test type=behavior | scope=作者报告段落批注共享HTTP处理器 | protects=报告段落位置无法按保存版读取或只读链接自动开放批注
def test_report_text_anchor_uses_selected_version_and_independent_permission(workspace):
    workspace.store.mutate('board', 1, [{'op': 'set_report_markdown', 'value': '# 报告\n\n季度结论'},
                                     {'op': 'set_view_mode', 'value': 'report'}])
    workspace.store.checkpoint('board', 2)
    payload = {'revision': 2, 'append': note('paragraph', None)}
    with pytest.raises(DashboardError) as denied:
        annotation_response(workspace, 'board', revision=2, payload=payload)
    assert denied.value.code == 'FORBIDDEN'
    result = annotation_response(workspace, 'board', revision=2, can_annotate=True, payload=payload)
    assert result['annotation']['context']['designRevision'] == 2
    workspace.store.mutate('board', 2, [{'op': 'set_report_markdown', 'value': '# 新版\n\n已移除结论'}])
    read = annotation_response(workspace, 'board', revision=2, can_annotate=True)
    assert read['targets']['paragraph']['sourcePath'] == 'manifest.report.markdown'
    assert read['targetRevision'] == 2 and read['revision'] == 3


# @wu-test type=integration | scope=stdio预览到普通浏览器入口 | protects=MCP预览没有可用本机批注入口或浏览器请求必须经过MCP
def test_stdio_profile_returns_reusable_loopback_browser_links(workspace):
    profile = McpProfile()
    try:
        result = profile.decorate('dashboard_preview', {'dashboardId': 'board'},
                                  {'document': workspace.store.readable('board')}, workspace)
        url = urlparse(result['browserLinks']['viewUrl'])
        token = parse_qs(url.fragment)['token'][0]
        base = f'{url.scheme}://{url.netloc}'
        saved = request(base, '/api/annotations/board', token, {'revision': 1, 'append': note()})
        assert saved['annotation']['id'] == 'note'
        repeated = profile.decorate('dashboard_preview', {'dashboardId': 'board'},
                                    {'document': workspace.store.readable('board')}, workspace)
        assert repeated['browserLinks'] == result['browserLinks']
        assert result['document']['browserLinks'] == result['browserLinks']
    finally:
        profile.close_previews()


@pytest.fixture
def share_gateway(tmp_path, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    state = {'requests': {}, 'attempts': 0, 'fail_once': True, 'active': True}

    class Gateway(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def answer(self, value, status=200):
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

        def do_POST(self):
            if self.headers.get('Authorization') != 'Bearer service-only-secret':
                return self.answer({'error': {'code': 'UNAUTHORIZED'}}, 401)
            raw = self.rfile.read(int(self.headers['Content-Length']))
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                document = json.loads(archive.read('document.json'))
            key = self.headers['X-Charts-Request']
            state['attempts'] += 1
            receipt = {'shareId': uuid.UUID(key).hex, 'revision': document['revision'],
                       'url': 'https://share.example/s/' + uuid.UUID(key).hex + '/',
                       'accessUrl': 'https://share.example/s/' + uuid.UUID(key).hex + '/#key=12345678',
                       'accessKey': '12345678', 'expiresAt': None, 'expiration': 'never',
                       'annotationMode': self.headers['X-Charts-Annotation-Mode'],
                       'pages': [{'id': document['id'], 'revision': document['revision']}]}
            state['requests'].setdefault(key, (raw, receipt, self.headers['X-Charts-Source']))
            assert state['requests'][key][0] == raw
            if state['fail_once']:
                state['fail_once'] = False
                self.close_connection = True
                return
            self.answer(receipt)

        def do_GET(self):
            if not state['active']:
                return self.answer({'error': {'code': 'SHARE_EXPIRED', 'message': 'Share is unavailable'}}, 410)
            share_id = urlparse(self.path).path.rsplit('/', 1)[-1]
            receipt = next(item[1] for item in state['requests'].values() if item[1]['shareId'] == share_id)
            self.answer({'shareId': share_id, 'revision': receipt['revision'], 'annotations': [note('feedback')],
                         'url': receipt['url'] + '?feedback=read-only'})

    server = ThreadingHTTPServer(('127.0.0.1', 0), Gateway)
    with running(server) as base:
        monkeypatch.setenv('CHARTS_SHARE_SERVICE_URL', base)
        monkeypatch.setenv('CHARTS_SHARE_SERVICE_TOKEN', 'service-only-secret')
        monkeypatch.setenv('CHARTS_SHARE_SERVICE_PROJECT', 'authorized-project')
        yield state


# @wu-test type=integration | scope=独立分享持久引用与幂等 HTTP 上传 | protects=丢失回执后重复创建链接、覆写正式发布版、泄露项目批注或重启丢失原版反馈
def test_local_publication_reuses_frozen_archive_and_persistent_reference(workspace, share_gateway, monkeypatch, tmp_path):
    from dashboard_runtime import deployment

    asset_dir = tmp_path / 'assets'
    asset_dir.mkdir()
    for name in deployment.UI_RESOURCES:
        (asset_dir / name).write_text('fixture public UI')
    monkeypatch.setattr(deployment, 'DIST', asset_dir)
    monkeypatch.setattr(deployment, 'require_preview', lambda: None)
    monkeypatch.setattr(workspace, '_doctor', lambda *args, **kwargs: {'passed': True})
    original_export = deployment.export_site

    def json_fixture_export(*args, **kwargs):
        assert kwargs['data_format'] == 'parquet'
        return original_export(*args, **{**kwargs, 'data_format': 'json'})

    monkeypatch.setattr(deployment, 'export_site', json_fixture_export)
    workspace.store.append_annotation('board', note('private'))
    workspace.store.mutate('board', 1, [{'op': 'set_title', 'value': 'B'}])
    workspace.store.checkpoint('board', 2)
    board = {'dashboardId': 'board'}
    workspace.call('dashboard_publish', {**board, 'revision': 2})
    formal = workspace.call('dashboard_version_status', board)
    args = {**board, 'revision': 1, 'requestId': str(uuid.uuid4()),
            'expiration': 'never', 'annotationMode': 'annotate'}
    for invalid in ({k: v for k, v in args.items() if k != 'requestId'}, {**args, 'revision': 3}):
        with pytest.raises(DashboardError):
            workspace.call('dashboard_share_publish', invalid)
    assert share_gateway['attempts'] == 0
    with pytest.raises(DashboardError) as first:
        workspace.call('dashboard_share_publish', args)
    assert first.value.code == 'SHARE_SERVICE_UNAVAILABLE'
    assert workspace.call('dashboard_version_status', board) == formal
    workspace.store.mutate('board', 2, [{'op': 'set_title', 'value': 'C'}])
    reopened = Service(tmp_path / 'new-runtime', project_root=workspace.project_root)
    shares = LocalShares(reopened)
    receipt = reopened.call('dashboard_share_publish', args)
    assert receipt['revision'] == 1 and len(share_gateway['requests']) == 1
    assert reopened.call('dashboard_share_publish', args) == receipt
    assert share_gateway['attempts'] == 2
    assert reopened.call('dashboard_version_status', board) == {**formal, 'draftRevision': 3}
    assert shares.feedback('board', receipt['shareId'])['revision'] == 1
    assert shares.status('board')['shares'][0]['revision'] == 1
    raw, _, source = next(iter(share_gateway['requests'].values()))
    assert source == shares.source
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        frozen = json.loads(archive.read('document.json'))
    assert frozen['revision'] == 1 and frozen['manifest']['title'] != 'B'
    assert not frozen['manifest'].get('annotations')
    assert b'service-only-secret' not in raw
    with pytest.raises(DashboardError) as conflict:
        reopened.call('dashboard_share_publish', {**args, 'annotationMode': 'view'})
    assert conflict.value.code == 'IDEMPOTENCY_CONFLICT'
    share_gateway['active'] = False
    with pytest.raises(DashboardError) as expired:
        shares.feedback('board', receipt['shareId'])
    assert expired.value.code == 'SHARE_EXPIRED'
    assert len(share_gateway['requests']) == 1


# @wu-test type=boundary | scope=静态ZIP与HTML权限清洗 | protects=重新导入的预览文档把作者令牌或可写批注能力泄漏给阅读者
def test_portable_exports_strip_imported_runtime_capabilities(workspace, monkeypatch, tmp_path):
    from dashboard_runtime import assets, deployment

    asset_dir = tmp_path / 'assets'
    asset_dir.mkdir()
    for name in deployment.UI_RESOURCES:
        (asset_dir / name).write_text('fixture public UI')
    (asset_dir / 'build.json').write_text('{"id":"test"}')
    monkeypatch.setattr(assets, 'DIST', asset_dir)
    monkeypatch.setattr(deployment, 'DIST', asset_dir)
    monkeypatch.setattr(deployment, 'require_preview', lambda: None)
    doc = workspace.store.readable('board')
    secret = 'author-secret-not-for-readers'
    doc.update({'browserLinks': {'editUrl': 'http://localhost/edit/board#token=' + secret},
                'annotationAccess': {'endpoint': '/api/annotations/board?token=' + secret, 'canAnnotate': True},
                'publicationApiBase': '/api/publications/' + secret, 'publication': {'shareId': 'old'}, 'annotationsOpen': True})
    static = deployment.export_site(workspace.store, 'board', document=doc, data_format='json')['export']
    with zipfile.ZipFile(static['path']) as archive:
        frozen = json.loads(archive.read('document.json'))
    for key in ('browserLinks', 'annotationAccess', 'publicationApiBase', 'publication', 'annotationsOpen'):
        assert key not in frozen
    html = assets.export_document(doc)
    assert secret not in html
    assert '"annotationAccess"' not in html and '"browserLinks"' not in html
