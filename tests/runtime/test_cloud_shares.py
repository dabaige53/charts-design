"""Cloud publication boundaries tested with an in-memory object-store adapter."""
import importlib.util
import json
import time
from pathlib import Path

import pytest

from dashboard_runtime.assets import FAVICON_LINK
from dashboard_runtime.cloud_shares import CloudShares, cleanup_due
from dashboard_runtime.cloud_storage import CosShareStorage
from dashboard_runtime.demo import executive_document
from dashboard_runtime.model import DashboardError
from dashboard_runtime.service import Service


class MemoryStorage:
    """Test object-store boundary; no credentials, network or local cleanup timer."""
    def __init__(self):
        self.objects = {'cleaner-status.json': json.dumps({'completedAt': int(time.time())}).encode()}
        self.fail_prefix = None

    def check_private(self):
        pass

    def put(self, key, content, content_type='application/octet-stream'):
        self.objects[key] = content

    def get(self, key):
        return self.objects.get(key)

    def list(self, prefix):
        return sorted(key for key in self.objects if key.startswith(prefix))

    def delete_prefix(self, prefix):
        if prefix == self.fail_prefix:
            raise OSError('simulated object storage failure')
        for key in list(self.objects):
            if key.startswith(prefix):
                del self.objects[key]


def publication(tmp_path, expiration='7d'):
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'source')
    service.call('dashboard_create', {'dashboardId': 'board', 'document': executive_document('board')})
    service.call('dashboard_version_publish', {'dashboardId': 'board', 'expectedRevision': 1, 'revision': 1})
    storage = MemoryStorage()
    shares = CloudShares(storage, 'https://charts.example.com')
    result = shares.publish(service, 'board', 1, expiration, '01234567')
    return service, storage, shares, result


# @wu-test type=integration | scope=腾讯云分享副本与到期清理 | protects=到期仅失效链接却残留远程数据密钥或误删原稿和其他分享
@pytest.mark.parametrize('expiration,days', [('7d', 7), ('30d', 30)])
def test_publication_expiry_removes_only_its_remote_copy(tmp_path, monkeypatch, expiration, days):
    service, storage, shares, result = publication(tmp_path, expiration)
    share_id = result['shareId']
    assert result['accessKey'] == '01234567'
    assert result['accessUrl'] == result['url'] + '#key=01234567'
    assert result['cleanupExecutor'] == 'tencent-scf'
    control = shares.authenticate(share_id, '01234567')
    source_title = service.store.get('board')['manifest']['title']
    assert control['expiresAt'] - control['createdAt'] == days * 86400
    saved_control = storage.get('shares/' + share_id + '/control.json')
    assert saved_control is not None
    assert '01234567' not in saved_control.decode()
    assert 'accessUrl' not in shares.status(service, 'board')['shares'][0]
    assert json.loads(shares.content(share_id, 'document.json'))['manifest']['title'] == source_title
    with pytest.raises(DashboardError, match='访问密钥错误'):
        shares.authenticate(share_id, '01234568')
    other = shares.publish(service, 'board', 1, 'never')
    assert len(other['accessKey']) == 8 and other['accessKey'].isascii() and other['accessKey'].isdigit()
    deadline = result['expiresAt']
    monkeypatch.setattr(time, 'time', lambda: deadline)
    with pytest.raises(DashboardError) as error:
        shares.content(share_id, 'app.js')
    assert error.value.code == 'SHARE_EXPIRED'
    assert cleanup_due(storage, deadline) == {'removed': 1, 'failed': []}
    assert not list(storage.list('shares/' + share_id + '/'))
    assert storage.get('jobs/' + share_id + '.json') is None
    assert shares.authenticate(other['shareId'], other['accessKey'])['expiresAt'] is None
    assert service.store.get('board')['manifest']['title'] == source_title


# @wu-test type=integration | scope=云端清理重试与不过期分享 | protects=删除失败丢失任务或不过期副本被自动清除或撤销仍可访问
def test_never_expiring_share_revocation_and_failed_cleanup_retry(tmp_path):
    service, storage, shares, result = publication(tmp_path, 'never')
    share_id = result['shareId']
    assert cleanup_due(storage, time.time() + 10 * 365 * 86400)['removed'] == 0
    # Failed delete operations keep both the job and access metadata.
    revoked = shares.revoke(service, 'board', share_id)
    assert revoked['cleanupState'] == 'pending'
    with pytest.raises(DashboardError) as error:
        shares.authenticate(share_id, '01234567')
    assert error.value.code == 'SHARE_EXPIRED'
    storage.fail_prefix = 'shares/' + share_id + '/'
    failed = cleanup_due(storage)
    assert len(failed['failed']) == 1
    assert storage.get('jobs/' + share_id + '.json') is not None
    assert shares.status(service, 'board', share_id)['shares'][0]['cleanupState'] == 'pending'
    storage.fail_prefix = None
    assert cleanup_due(storage) == {'removed': 1, 'failed': []}
    assert shares.status(service, 'board')['shares'] == []


# @wu-test type=boundary | scope=云分享发布前置条件 | protects=密钥格式错误、未发布草稿或清理状态失效时仍发布
def test_publication_requires_valid_key_checkpoint_and_cloud_heartbeat(tmp_path):
    service, storage, shares, _ = publication(tmp_path)
    for key in ('1234567', '１２３４５６７８', '1234567x', 12345678):
        with pytest.raises(DashboardError) as error:
            shares.publish(service, 'board', 1, '7d', key)
        assert error.value.code == 'INVALID_ARGUMENT'
    storage.objects.pop('cleaner-status.json')
    with pytest.raises(DashboardError) as error:
        shares.publish(service, 'board', 1)
    assert error.value.code == 'CLOUD_CLEANER_UNAVAILABLE'
    storage.put('cleaner-status.json', json.dumps({'completedAt': int(time.time()) - 6 * 3600}).encode())
    shares.publish(service, 'board', 1)
    storage.put('cleaner-status.json', json.dumps({'completedAt': int(time.time()) - 7 * 3600}).encode())
    with pytest.raises(DashboardError) as error:
        shares.publish(service, 'board', 1)
    assert error.value.code == 'CLOUD_CLEANER_UNAVAILABLE'
    service.call('dashboard_patch', {'dashboardId': 'board', 'expectedRevision': 1,
                                   'operations': [{'op': 'set_title', 'value': 'Draft'}]})
    with pytest.raises(DashboardError) as error:
        shares.publish(service, 'board', 2)
    assert error.value.code == 'REVISION_CONFLICT'


# @wu-test type=integration | scope=分享与发布版本 | protects=编辑草稿悄悄改变新分享或已有分享的发布内容
def test_share_uses_published_version_while_draft_changes(tmp_path):
    service, storage, shares, first = publication(tmp_path)
    title = service.store.get('board')['manifest']['title']
    service.store.mutate('board', 1, [{'op': 'set_title', 'value': 'Unpublished draft'}])
    second = shares.publish(service, 'board', 1)
    assert json.loads(shares.content(second['shareId'], 'document.json'))['manifest']['title'] == title
    service.store.checkpoint('board', 2)
    service.call('dashboard_version_publish', {'dashboardId': 'board', 'expectedRevision': 2, 'revision': 2})
    third = shares.publish(service, 'board', 2)
    assert json.loads(shares.content(third['shareId'], 'document.json'))['manifest']['title'] == 'Unpublished draft'
    assert json.loads(shares.content(first['shareId'], 'document.json'))['manifest']['title'] == title


# @wu-test type=behavior | scope=CloudShares.replace | protects=替换分享未更换密钥或旧链接仍可访问
def test_replace_rotates_key_and_revokes_only_selected_share(tmp_path):
    service, storage, shares, old = publication(tmp_path)
    other = shares.publish(service, 'board', 1, 'never')
    new = shares.replace(service, 'board', old['shareId'], 1, '30d')
    assert new['previousRevoked'] and new['shareId'] != old['shareId']
    assert new['accessKey'] != old['accessKey']
    assert shares.authenticate(new['shareId'], new['accessKey'])['revision'] == 1
    with pytest.raises(DashboardError) as expired:
        shares.authenticate(old['shareId'], old['accessKey'])
    assert expired.value.code == 'SHARE_EXPIRED'
    assert shares.authenticate(other['shareId'], other['accessKey'])['expiresAt'] is None


# @wu-test type=boundary | scope=CloudShares.replace | protects=上传新副本失败时提前撤销旧分享
def test_failed_replacement_upload_preserves_old_share(tmp_path, monkeypatch):
    service, storage, shares, old = publication(tmp_path)
    put = storage.put

    def fail_site(key, content, content_type='application/octet-stream'):
        if '/site/' in key:
            raise OSError('simulated upload failure')
        put(key, content, content_type)

    monkeypatch.setattr(storage, 'put', fail_site)
    with pytest.raises(OSError):
        shares.replace(service, 'board', old['shareId'], 1)
    assert shares.authenticate(old['shareId'], old['accessKey'])['state'] == 'active'


# @wu-test type=boundary | scope=CloudShares.replace | protects=旧分享撤销失败导致新凭据丢失或误报旧链接已失效
def test_partial_replacement_returns_new_credentials(tmp_path, monkeypatch):
    service, storage, shares, old = publication(tmp_path)
    put = storage.put

    def fail_revoke(key, content, content_type='application/octet-stream'):
        if key == 'shares/' + old['shareId'] + '/control.json':
            raise OSError('simulated revoke failure')
        put(key, content, content_type)

    monkeypatch.setattr(storage, 'put', fail_revoke)
    new = shares.replace(service, 'board', old['shareId'], 1)
    assert new['previousRevoked'] is False
    assert new['followUp'] == 'dashboard_share_delete'
    assert shares.authenticate(new['shareId'], new['accessKey'])['state'] == 'active'
    assert shares.authenticate(old['shareId'], old['accessKey'])['state'] == 'active'


# @wu-test type=boundary | scope=云分享读取和删除归属 | protects=跨项目访问密钥记录或路径穿越读取控制记录及删除其他项目副本
def test_cloud_share_file_and_owner_boundaries(tmp_path):
    service, _, shares, result = publication(tmp_path)
    for name in ('../control.json', '/control.json', 'control.json', 'data/../../control.json'):
        with pytest.raises(DashboardError) as error:
            shares.content(result['shareId'], name)
        assert error.value.code == 'NOT_FOUND'
    other = Service(tmp_path / 'other-cache', project_root=tmp_path / 'other')
    assert shares.status(other, 'board')['shares'] == []
    with pytest.raises(DashboardError) as error:
        shares.revoke(other, 'board', result['shareId'])
    assert error.value.code == 'FORBIDDEN'
    assert shares.authenticate(result['shareId'], result['accessKey'])


class VersionedCosClient:
    def __init__(self):
        self.fail_delete = False
        self.versions = [
            {'Key': 'charts-shares/shares/a/site/data.json', 'VersionId': 'old'},
            {'Key': 'charts-shares/shares/a/site/data.json', 'VersionId': 'new'},
        ]
        self.markers = [{'Key': 'charts-shares/shares/a/site/data.json', 'VersionId': 'deleted'}]
        self.outside = {'Key': 'charts-shares/shares/b/site/data.json', 'VersionId': 'keep'}

    def list_objects_versions(self, **args):
        # Deliberately page one version at a time.
        versions = [item for item in self.versions if item['Key'].startswith(args['Prefix'])][:1]
        markers = [] if versions else self.markers[:1]
        return {'Version': versions, 'DeleteMarker': markers}

    def delete_objects(self, **args):
        if self.fail_delete:
            return {'Error': [{'Code': 'AccessDenied'}]}
        for item in args['Delete']['Object']:
            assert 'VersionId' in item
            assert item != self.outside
            if item in self.versions:
                self.versions.remove(item)
            if item in self.markers:
                self.markers.remove(item)
        return {}

    def list_objects(self, **args):
        return {'Contents': []}


# @wu-test type=integration | scope=COS物理版本删除 | protects=遗留历史版本或清理越过分享前缀或部分删除失败被当作完成
def test_cos_cleanup_deletes_versions_and_markers_in_bounded_pages():
    client = VersionedCosClient()
    storage = CosShareStorage(client, 'private-bucket')
    storage.delete_prefix('shares/a/')
    assert client.versions == [] and client.markers == []
    assert client.outside['VersionId'] == 'keep'
    denied = VersionedCosClient()
    denied.fail_delete = True
    with pytest.raises(DashboardError) as error:
        CosShareStorage(denied, 'private-bucket').delete_prefix('shares/a/')
    assert error.value.code == 'COS_DELETE_FAILED'
    assert len(denied.versions) == 2 and len(denied.markers) == 1


# @wu-test type=boundary | scope=COS私有存储发布检查 | protects=公开桶或匿名桶策略使访问密钥可被绕过
def test_cos_private_bucket_check_uses_sdk_acl_and_rejects_public_policy():
    pytest.importorskip('qcloud_cos')

    class AclClient:
        acl = 'private'
        policy = {'Statement': []}

        def get_bucket_acl(self, **args):
            return {'CannedACL': self.acl}

        def get_bucket_policy(self, **args):
            return {'Policy': json.dumps(self.policy)}

    client = AclClient()
    storage = CosShareStorage(client, 'private-bucket')
    storage.check_private()
    client.acl = 'public-read'
    with pytest.raises(DashboardError) as error:
        storage.check_private()
    assert error.value.code == 'COS_BUCKET_NOT_PRIVATE'
    client.acl = 'private'
    client.policy = {'Statement': [{'Effect': 'Allow', 'Principal': {'qcs': ['*']}}]}
    with pytest.raises(DashboardError) as error:
        storage.check_private()
    assert error.value.code == 'COS_BUCKET_NOT_PRIVATE'


# @wu-test type=integration | scope=SCF定时清理入口 | protects=清理从本地执行或云端删除失败不重试却报告正常
def test_scf_handler_requires_cloud_and_preserves_failures(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('cloud_cleaner', Path(__file__).resolve().parents[2] / 'deploy/tencent-cleaner/index.py')
    assert spec is not None and spec.loader is not None
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    monkeypatch.delenv('TENCENTCLOUD_RUNENV', raising=False)
    with pytest.raises(RuntimeError, match='Tencent SCF'):
        handler.main_handler({}, None)
    service, storage, shares, result = publication(tmp_path, 'never')
    shares.revoke(service, 'board', result['shareId'])
    monkeypatch.setenv('TENCENTCLOUD_RUNENV', 'SCF')
    monkeypatch.setattr(CosShareStorage, 'from_environment', classmethod(lambda cls: storage))
    storage.fail_prefix = 'shares/' + result['shareId'] + '/'
    with pytest.raises(RuntimeError, match='retained for retry'):
        handler.main_handler({}, None)
    assert storage.get('jobs/' + result['shareId'] + '.json') is not None
    storage.fail_prefix = None
    assert handler.main_handler({}, None)['removed'] == 1
    heartbeat = storage.get('cleaner-status.json')
    assert heartbeat is not None
    assert json.loads(heartbeat)['executor'] == 'tencent-scf'


# @wu-test type=integration | scope=云端网页密钥和到期访问 | protects=分享图标丢失或未授权及过期后仍可读取云端文件
def test_gateway_gates_every_file_and_rejects_expired_sessions(tmp_path, monkeypatch):
    pytest.importorskip('mcp')
    from starlette.testclient import TestClient
    from dashboard_runtime.server import RemoteServer, ServerSettings, create_app

    _, storage, shares, published = publication(tmp_path)
    server = RemoteServer(ServerSettings(workspace=tmp_path / 'gateway', runtime=tmp_path / 'gateway-cache',
                                        tokens=('gateway-admin-token-0123456789',),
                                        public_url='https://charts.example.com'))
    server.cloud_shares = shares
    root = '/s/' + published['shareId'] + '/'
    with TestClient(create_app(server), base_url='https://charts.example.com') as client:
        form = client.get(root)
        assert '8 位数字访问密钥' in form.text
        assert FAVICON_LINK in form.text
        assert 'img-src data:' in form.headers['content-security-policy']
        assert client.get(root + 'document.json').status_code == 401
        assert client.get(root + 'app.js').status_code == 401
        assert client.post(root, data={'accessKey': '00000000'}).status_code == 401
        response = client.post(root, data={'accessKey': '01234567'}, follow_redirects=False)
        assert response.status_code == 303
        assert 'HttpOnly' in response.headers['set-cookie'] and 'Secure' in response.headers['set-cookie']
        page = client.get(root).text
        assert 'mode:"static"' in page
        assert FAVICON_LINK in page
        content = client.get(root + 'document.json')
        assert content.status_code == 200 and 'no-store' in content.headers['cache-control']
        assert '01234567' not in content.text
        deadline = published['expiresAt']
        monkeypatch.setattr(time, 'time', lambda: deadline)
        assert client.get(root + 'document.json').status_code == 410
        assert client.get(root + 'app.js').status_code == 410
        assert cleanup_due(storage, deadline)['removed'] == 1
        assert client.get(root).status_code == 410


# @wu-test type=boundary | scope=分享登录表单来源 | protects=浏览器提交失败或跨站来源绕过限制
@pytest.mark.parametrize('origin, expected_status', [
    ('https://charts.example.com', 303),
    ('null', 403),
    ('https://other.example.com', 403),
])
def test_share_form_preserves_browser_origin_and_rejects_foreign_origins(tmp_path, origin, expected_status):
    pytest.importorskip('mcp')
    from starlette.testclient import TestClient
    from dashboard_runtime.server import RemoteServer, ServerSettings, create_app

    _, _, shares, published = publication(tmp_path)
    server = RemoteServer(ServerSettings(workspace=tmp_path / 'gateway', runtime=tmp_path / 'gateway-cache',
                                        tokens=('gateway-admin-token-0123456789',),
                                        public_url='https://charts.example.com'))
    server.cloud_shares = shares
    root = '/s/' + published['shareId'] + '/'
    with TestClient(create_app(server), base_url='https://charts.example.com') as client:
        form = client.get(root)
        assert form.headers['referrer-policy'] == 'same-origin'
        nonce = form.text.split('<style nonce="')[1].split('"')[0]
        assert "'nonce-" + nonce + "'" in form.headers['content-security-policy']
        assert "'unsafe-inline'" not in form.headers['content-security-policy']
        response = client.post(root, data={'accessKey': '01234567'},
                               headers={'Origin': origin}, follow_redirects=False)
        assert response.status_code == expected_status
        if expected_status == 303:
            assert client.get(root + 'document.json').status_code == 200
        else:
            assert 'text/html' in response.headers['content-type']
            assert '重新打开分享' in response.text
            assert 'set-cookie' not in response.headers
            assert client.get(root + 'document.json').status_code == 401


# @wu-test type=boundary | scope=8位密钥在线尝试限制 | protects=短数字密钥可被无限在线枚举
def test_gateway_limits_key_guesses(tmp_path):
    pytest.importorskip('mcp')
    from starlette.testclient import TestClient
    from dashboard_runtime.server import RemoteServer, ServerSettings, create_app

    _, _, shares, published = publication(tmp_path)
    server = RemoteServer(ServerSettings(workspace=tmp_path / 'gateway', runtime=tmp_path / 'gateway-cache',
                                        tokens=('gateway-admin-token-0123456789',),
                                        public_url='https://charts.example.com'))
    server.cloud_shares = shares
    root = '/s/' + published['shareId'] + '/'
    with TestClient(create_app(server), base_url='https://charts.example.com') as client:
        for _ in range(5):
            assert client.post(root, data={'accessKey': '00000000'}).status_code == 401
        assert client.post(root, data={'accessKey': '01234567'}).status_code == 429

# @wu-test type=integration | scope=多页面云分享 | protects=分享遗漏选中页面或替换时丢失页面和发布版本
def test_multi_page_publication_and_replace(tmp_path):
    import gzip
    import posixpath

    service, storage, shares, _ = publication(tmp_path)
    service.call('dashboard_create', {'dashboardId': 'second', 'document': executive_document('second')})
    with pytest.raises(DashboardError):
        shares.publish(service, 'board', 1, pages=[{'dashboardId': 'second', 'expectedRevision': 1}])
    service.call('dashboard_version_publish', {'dashboardId': 'second', 'expectedRevision': 1, 'revision': 1})
    third_document = executive_document('third')
    third_document['snapshot']['datasets']['sales'][0]['revenue'] += 1
    service.call('dashboard_create', {'dashboardId': 'third', 'document': third_document})
    service.call('dashboard_version_publish', {'dashboardId': 'third', 'expectedRevision': 1, 'revision': 1})
    result = shares.publish(service, 'board', 1, pages=[
        {'dashboardId': 'second', 'expectedRevision': 1},
        {'dashboardId': 'third', 'expectedRevision': 1},
    ])
    root = json.loads(shares.content(result['shareId'], 'document.json'))
    assert [page['id'] for page in root['staticPages']] == ['board', 'second', 'third']
    second = json.loads(shares.content(result['shareId'], root['staticPages'][1]['path']))
    assert second['id'] == 'second'
    for dataset, files in second['staticFiles'].items():
        assert len(files) == len(root['staticFiles'][dataset])
        for relative, root_file in zip(files, root['staticFiles'][dataset]):
            resolved = posixpath.normpath(posixpath.join('pages/second', relative))
            assert resolved == root_file
            assert json.loads(gzip.decompress(shares.content(result['shareId'], resolved)))
    assert not [key for key in storage.objects if key.startswith('shares/' + result['shareId'] + '/site/pages/second/data/')]
    third = json.loads(shares.content(result['shareId'], 'pages/third/document.json'))
    third_file = posixpath.normpath(posixpath.join('pages/third', third['staticFiles']['sales'][0]))
    assert third_file.startswith('pages/third/data/')
    assert json.loads(gzip.decompress(shares.content(result['shareId'], third_file)))[0]['revenue'] != \
        json.loads(gzip.decompress(shares.content(result['shareId'], root['staticFiles']['sales'][0])))[0]['revenue']
    assert len(shares.status(service, 'board', result['shareId'])['shares'][0]['pages']) == 3
    replaced = shares.replace(service, 'board', result['shareId'], 1)
    assert replaced['previousRevoked']
    assert [page['id'] for page in replaced['pages']] == ['board', 'second', 'third']
    assert json.loads(shares.content(replaced['shareId'], 'pages/second/document.json'))['id'] == 'second'
