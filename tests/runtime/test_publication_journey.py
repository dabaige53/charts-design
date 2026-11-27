"""Author-to-publication boundaries using real HTTP and independent processes."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
from urllib.parse import urlsplit
import uuid

import httpx
import pytest
from starlette.testclient import TestClient

from dashboard_runtime.demo import document
from dashboard_runtime.model import apply_operations
from dashboard_runtime.server import RemoteServer, ServerSettings, create_app
from dashboard_runtime.service import Service

TOKEN = 'author-publication-test-token-123456'
SHARE_TOKEN = 'independent-share-test-token-654321'


def note(note_id='position-a', component='trend', text='请核对这张图的口径'):
    return {'id': note_id, 'componentId': component, 'text': text,
            'createdAt': '2026-11-27T01:00:00+00:00',
            'anchor': {'scope': 'component', 'kind': 'area', 'quote': 'Revenue by month', 'occurrence': 0,
                       'rect': {'x': .1, 'y': .1, 'width': .2, 'height': .2}},
            'view': {'revision': 1, 'filters': []}}


def auth(token):
    return {'Authorization': 'Bearer ' + token}


# @wu-test type=integration | scope=server workspace annotation REST permissions | protects=read-only tokens silently gaining write permissions or annotation saves changing content versions
def test_server_workspace_annotation_capability_and_original_revision(tmp_path):
    server = RemoteServer(ServerSettings(workspace=tmp_path / 'ws', runtime=tmp_path / 'runtime', tokens=(TOKEN,)))
    service = server.projects.service('default')
    service.store.create('board', 'A', document('board'))
    original = service.store.readable('board')
    service.store.mutate('board', 1, [{'op': 'set_title', 'value': 'B draft'}])
    view = urlsplit(server.links.share('default', 'board')['url']).fragment.removeprefix('token=')
    annotator = urlsplit(server.links.share('default', 'board', annotation_mode='annotate')['url']).fragment.removeprefix('token=')
    old_payload = server.signer.verify(view, 'share')
    assert old_payload is not None
    old_payload.pop('annotationMode')
    legacy = server.signer.sign(old_payload)
    endpoint = '/api/v1/p/default/annotations/board'
    with TestClient(create_app(server)) as client:
        for token in (view, legacy):
            response = client.post(endpoint, headers=auth(token), json={'revision': 1, 'append': note()})
            assert response.status_code == 403
            assert client.get(endpoint, headers=auth(token)).json()['canAnnotate'] is False
        response = client.post(endpoint, headers=auth(annotator), json={'revision': 1, 'append': note()})
        assert response.status_code == 200, response.text
        assert response.json()['annotation']['context']['designRevision'] == 1
        assert client.post(endpoint, headers=auth(annotator), json={'revision': 1, 'append': note()}).status_code == 200
        result = client.get(endpoint + '?revision=1', headers=auth(annotator)).json()
        assert len(result['annotations']) == 1
        assert result['canAnnotate'] is True and result['canManageAnnotations'] is False
        assert result['targets']['position-a']['title'] == original['manifest']['components']['trend']['title']
        for tool in ('dashboard_patch', 'dashboard_checkpoint', 'dashboard_publish', 'dashboard_annotations_update'):
            assert client.post('/api/v1/p/default/tools/' + tool, headers=auth(annotator),
                               json={'dashboardId': 'board', 'expectedRevision': 2}).status_code == 403
        assert client.post(endpoint, headers=auth(annotator), json={'expectedAnnotations': [], 'annotations': []}).status_code == 403
        assert client.get('/api/v1/p/default/annotations/other', headers=auth(annotator)).status_code == 403
        tools = '/api/v1/p/default/tools/'
        assert client.post(tools + 'dashboard_get', headers=auth(view), json={'dashboardId': 'board'}).json()['document']['revision'] == 1
        saved = client.post(tools + 'dashboard_submit', headers=auth(TOKEN),
                            json={'dashboardId': 'board', 'expectedRevision': 2})
        assert saved.status_code == 200 and saved.json()['ok'] is True
        # The existing online view follows the newly saved B checkpoint, while
        # the annotation created against A keeps its original location context.
        assert client.post(tools + 'dashboard_get', headers=auth(view), json={'dashboardId': 'board'}).json()['document']['revision'] == 2
        assert client.get(endpoint + '?revision=1', headers=auth(annotator)).json()['annotations'][0]['context']['designRevision'] == 1
    assert service.store.revision('board') == 2
    assert service.store.readable('board')['revision'] == 2


def _port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def _certificate(directory):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import ipaddress

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, '127.0.0.1')])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                   .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
                   .not_valid_after(now + timedelta(days=1))
                   .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
                   .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                   .sign(key, hashes.SHA256()))
    cert_path, key_path = directory / 'test-cert.pem', directory / 'test-key.pem'
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    key_path.chmod(0o600)
    return cert_path, key_path


AUTHOR_PROCESS = '''
import sys
from pathlib import Path
from dashboard_runtime.service import Service
from dashboard_runtime.http_server import RuntimeHTTPServer
server=RuntimeHTTPServer(Service(Path(sys.argv[1])/'runtime',project_root=Path(sys.argv[1])/'project'),
                         int(sys.argv[2]),token=sys.argv[3],idle_timeout=3600)
server.serve_forever()
'''

WORKSPACE_PROCESS = '''
import sys
from pathlib import Path
import uvicorn
from dashboard_runtime.server import RemoteServer, ServerSettings, create_app
root=Path(sys.argv[1]);port=int(sys.argv[2])
settings=ServerSettings(workspace=root, runtime=root/'runtime', tokens=(sys.argv[3],),
                        port=port, default_project='project')
uvicorn.run(create_app(RemoteServer(settings)), host='127.0.0.1', port=port, log_level='error', access_log=False)
'''

SHARE_PROCESS = '''
import json,os,sys,time
from pathlib import Path
import uvicorn
from starlette.responses import PlainTextResponse
from dashboard_runtime.server import RemoteServer,ServerSettings,create_app
from dashboard_runtime.cloudflare_shares import storage
from dashboard_runtime.cloud_shares import CloudShares
from dashboard_runtime.model import DashboardError
root=Path(sys.argv[1]);port=int(sys.argv[2])
os.environ.update(CHARTS_STORAGE_BACKEND='cloudflare', CHARTS_RUNTIME_ROOT=str(root/'runtime'),
                  CHARTS_PUBLIC_URL='https://127.0.0.1:'+str(port))
storage().put('cleaner-status.json',json.dumps({'completedAt':int(time.time())}).encode())
server=RemoteServer(ServerSettings(workspace=root/'workspace',runtime=root/'runtime',tokens=(sys.argv[3],),
                                  public_url=os.environ['CHARTS_PUBLIC_URL'], role='sharing'))
import_site = CloudShares.import_site
drop_once = True
def interrupt_receipt(self, *args, **kwargs):
    global drop_once
    receipt = import_site(self, *args, **kwargs)
    if drop_once:
        drop_once = False
        raise DashboardError('SHARE_SERVICE_UNAVAILABLE', 'Test interruption after storing the share', 503)
    return receipt
CloudShares.import_site = interrupt_receipt
app = create_app(server)
async def require_publisher_identity(scope, receive, send):
    if scope['type'] == 'http' and scope['method'] == 'POST' and scope['path'] == '/api/v1/publications':
        headers = dict(scope['headers'])
        if (headers.get(b'authorization') == ('Bearer ' + sys.argv[3]).encode()
                and not headers.get(b'user-agent', b'').startswith(b'Charts-Design-Publisher/')):
            await PlainTextResponse('Missing publisher identity', status_code=403)(scope, receive, send)
            return
    await app(scope, receive, send)
uvicorn.run(require_publisher_identity,host='127.0.0.1',port=port,log_level='error',access_log=False,
            ssl_certfile=sys.argv[4],ssl_keyfile=sys.argv[5])
'''


@contextmanager
def _process(script, args, url, env, *, verify: bool | ssl.SSLContext = True):
    process = subprocess.Popen([sys.executable, '-c', script, *map(str, args)],
                               cwd=Path(__file__).resolve().parents[2], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    stderr = process.stderr
    assert stderr is not None
    try:
        with httpx.Client(verify=verify, trust_env=False, timeout=1) as client:
            for _ in range(150):
                if process.poll() is not None:
                    raise AssertionError(stderr.read())
                try:
                    response = client.get(url)
                    if response.status_code < 500:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.05)
            else:
                raise AssertionError('Isolated HTTP process did not become ready')
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # An abrupt container stop must preserve the same durable
                # publication state. Never leave the fixture process behind.
                process.kill()
                process.wait(timeout=5)
        stderr.close()


# @wu-test type=integration | scope=本机与服务器独立分享 HTTP 和查询 Worker | protects=发布请求缺少客户端标识、重试重复分享、作者离线后内容或批注不可用、展开区域筛选读取明细分片
@pytest.mark.parametrize('author_mode', ['local', 'server'])
def test_independent_share_survives_author_shutdown_and_service_restart(tmp_path, author_mode):
    from dashboard_runtime.columnar import native_binary
    binary = native_binary()
    if binary is None:
        pytest.skip('The PR native artifact is required for real Parquet publication')
    author_root, cloud_root = tmp_path / 'author', tmp_path / 'share-service'
    author_root.mkdir()
    cloud_root.mkdir()
    certificate, private_key = _certificate(tmp_path)
    verify = ssl.create_default_context(cafile=str(certificate))
    local_port, cloud_port = _port(), _port()
    cloud_url, local_url = f'https://127.0.0.1:{cloud_port}', f'http://127.0.0.1:{local_port}'
    environment = {key: value for key, value in os.environ.items() if not key.startswith(('CHARTS_', 'CLOUDBASE_'))}
    environment['CHARTS_CORE_BIN'] = binary
    local_environment = {**environment, 'CHARTS_SHARE_SERVICE_URL': cloud_url,
                         'CHARTS_SHARE_SERVICE_TOKEN': SHARE_TOKEN, 'SSL_CERT_FILE': str(certificate)}
    source = Service(author_root / 'runtime', project_root=author_root / 'project')
    source.store.create('board', 'A', document('board'))
    source.store.append_annotation('board', note('private-note', text='本机私人批注'))
    cloud_args = [cloud_root, cloud_port, SHARE_TOKEN, certificate, private_key]
    local = author_mode == 'local'
    author_script = AUTHOR_PROCESS if local else WORKSPACE_PROCESS
    tools = '/api/tools/' if local else '/api/v1/p/project/tools/'
    feedback_base = '/api/publications/' if local else '/api/v1/p/project/publications/'
    with httpx.Client(base_url=cloud_url, verify=verify, trust_env=False, timeout=30) as reader:
        with _process(SHARE_PROCESS, cloud_args, cloud_url + '/health', environment, verify=verify):
            assert reader.get('/health').json()['role'] == 'sharing'
            for path in ('/mcp', '/mcp/' + SHARE_TOKEN, '/unified/mcp', '/api/v1/p/project/tools/dashboard_get'):
                assert reader.post(path, headers=auth(SHARE_TOKEN), json={}).status_code == 404
            for path in ('/', '/edit/project/board', '/view/project/board'):
                assert reader.get(path, headers=auth(SHARE_TOKEN)).status_code == 404
            assert reader.post('/api/v1/publications', headers=auth(TOKEN), content=b'').status_code == 401
            with _process(author_script, [author_root, local_port, TOKEN], local_url + '/', local_environment) as author:
                with httpx.Client(base_url=local_url, headers=auth(TOKEN), trust_env=False, timeout=60) as client:
                    request = {'dashboardId': 'board', 'revision': 1, 'requestId': str(uuid.uuid4()),
                               'annotationMode': 'annotate', 'expiration': '7d'}
                    failed = client.post(tools + 'dashboard_share_publish', json=request)
                    assert failed.status_code == 503 and failed.json()['error']['code'] == 'SHARE_SERVICE_UNAVAILABLE'
                    stored_copies = cloud_root / 'runtime' / 'private-shares' / 'shares'
                    stored_share_ids = {path.name for path in stored_copies.iterdir() if path.is_dir()}
                    assert len(stored_share_ids) == 1
                    state = client.post(tools + 'dashboard_version_status', json={'dashboardId': 'board'}).json()
                    assert state['publishedRevision'] is None and state['releases'] == []
                    result = client.post(tools + 'dashboard_share_publish', json=request)
                    assert result.status_code == 200, result.text
                    receipt = result.json()
                    assert {path.name for path in stored_copies.iterdir() if path.is_dir()} == stored_share_ids == {receipt['shareId']}
                    assert client.post(tools + 'dashboard_share_publish', json=request).json()['shareId'] == receipt['shareId']
                    state = client.post(tools + 'dashboard_version_status', json={'dashboardId': 'board'}).json()
                    assert state['publishedRevision'] is None and state['releases'] == []
                    page = f"/s/{receipt['shareId']}/"
                    if not local:
                        assert client.post('/api/v1/publications', content=b'').status_code == 404
                        assert client.get(page).status_code == 404
                    assert reader.get(page, follow_redirects=False).status_code == 200
                    opened = reader.post(page, data={'accessKey': receipt['accessKey']}, headers={'Origin': cloud_url})
                    assert opened.status_code == 303
                    frozen = reader.get(page + 'document.json').json()
                    assert frozen['revision'] == 1 and not frozen['manifest'].get('annotations')
                    assert frozen['annotationAccess']['canAnnotate'] is True
                    files = [name for names in frozen['staticFiles'].values() for name in names]
                    assert files and all(name.endswith('.parquet') for name in files)
                    before = {name: reader.get(page + name).content for name in files}
                    assert all(raw[:4] == b'PAR1' for raw in before.values())
                    changed = client.post(tools + 'dashboard_submit', json={'dashboardId': 'board', 'expectedRevision': 1,
                        'operations': [{'op': 'set_title', 'value': 'B saved'}]}).json()
                    assert changed.get('ok') is True, changed
                    preview = client.post(tools + 'dashboard_preview', json={'dashboardId': 'board'}).json()
                    assert preview['document']['revision'] == 2
                    assert reader.get(page + 'document.json').json()['revision'] == 1
                author.terminate()
                author.wait(timeout=15)
                assert author.poll() is not None
                # The author has stopped. All of these are real requests to the
                # independently running publication service and its own disk.
                assert reader.get(page).status_code == 200
                from static_fixture import worker_query
                independent_files = {name: reader.get(page + name).content for name in files}
                filters = [{'field': 'region', 'op': 'in', 'values': ['East'], 'componentIds': ['details']}]
                options, *queried = worker_query(reader.get(page + 'document.json').json(), independent_files, [
                    {'filterId': 'region'},
                    {'detail': True, 'componentId': 'details', 'filters': filters, 'limit': 1, 'offset': 0},
                    {'detail': True, 'componentId': 'details', 'filters': filters, 'limit': 1, 'offset': 1},
                ])
                assert options['result']['values'] == ['East', 'South'] and options['files'] == []
                assert [item['result']['totalRows'] for item in queried] == [3, 3]
                assert [item['result']['rows'][0]['revenue'] for item in queried] == [80, 102]
                assert queried[0]['files'] and queried[1]['files'] == []  # Same immutable dataset cache.
                payload = {'dashboardId': 'board', 'revision': 1, 'append': note('reader-note'), 'authorName': '同事'}
                saved = reader.post(page + 'api/annotations', json=payload, headers={'Origin': cloud_url})
                assert saved.status_code == 200, saved.text
                assert saved.json()['annotation']['context']['designRevision'] == 1
                assert reader.post(page + 'api/annotations', json=payload, headers={'Origin': cloud_url}).status_code == 200
                notes = reader.get(page + 'api/annotations').json()['annotations']
                assert [item['id'] for item in notes] == ['reader-note']
                assert notes[0]['author'] == {'name': '同事', 'verified': False}
                assert {name: reader.get(page + name).content for name in files} == before
                assert reader.get(page + 'document.json').json() == frozen
        # Restart the independent server against the same private volume. Its
        # signing key and annotation DB must survive; no author is running.
        with _process(SHARE_PROCESS, cloud_args, cloud_url + '/health', environment, verify=verify):
            assert reader.get(page + 'api/annotations').json()['annotations'] == notes
            with _process(author_script, [author_root, local_port, TOKEN], local_url + '/', local_environment):
                with httpx.Client(base_url=local_url, headers=auth(TOKEN), trust_env=False, timeout=30) as client:
                    result = client.get(feedback_base + receipt['shareId'] + '/feedback?dashboardId=board')
                    assert result.status_code == 200, result.text
                    feedback = result.json()
                    assert feedback['revision'] == 1 and feedback['annotations'] == notes
                    assert '#feedback=' in feedback['url'] and SHARE_TOKEN not in feedback['url']
                    assert client.post(tools + ('dashboard_get' if local else 'dashboard_preview'),
                                       json={'dashboardId': 'board'}).json()['document']['revision'] == 2
                    assert all(item['id'] != 'reader-note' for item in source.store.annotation_state('board')['annotations'])


# @wu-test type=integration | scope=CloudBase and Neon workspace annotation context | protects=preview annotations being attributed to the latest draft or re-encoding cloud assets
@pytest.mark.parametrize('backend', ['cloudbase', 'neon'])
def test_cloud_annotation_uses_displayed_checkpoint_without_rewriting_content(backend):
    from copy import deepcopy
    from dashboard_runtime.cloud_project import CloudProjectStore

    original = document('board')
    original['revision'] = 1
    draft = apply_operations(deepcopy(original), [{'op': 'set_title', 'value': 'B draft'}])
    draft['revision'] = 2
    calls = []

    class Database:
        def __init__(self, backend):
            self.backend = backend

        def call(self, action, project, **payload):
            calls.append(action)
            if action == 'get':
                return deepcopy(draft)
            assert action == 'commit' and payload['expected'] == 2
            assert payload['document']['revision'] == 2
            assert payload['document']['manifest']['title'] == 'B draft'
            assert payload['document']['snapshot'] == draft['snapshot']
            assert payload['previousNotes'] == []
            return payload['document']

    store = CloudProjectStore.__new__(CloudProjectStore)
    store.project, store.database = 'fixture', Database(backend)
    saved = store.append_annotation('board', note(), context_document=original)
    assert saved is not None
    assert saved['annotation']['context']['designRevision'] == 1
    assert calls == ['get', 'commit']
