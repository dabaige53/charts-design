"""Cloud publication boundaries tested with an in-memory object-store adapter."""
import importlib.util
import json
import time
from pathlib import Path

import pytest

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
    assert result['cleanupExecutor'] == 'tencent-scf'
    control = shares.authenticate(share_id, '01234567')
    source_title = service.store.get('board')['manifest']['title']
    assert control['expiresAt'] - control['createdAt'] == days * 86400
    saved_control = storage.get('shares/' + share_id + '/control.json')
    assert saved_control is not None
    assert '01234567' not in saved_control.decode()
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


# @wu-test type=boundary | scope=云分享发布前置条件 | protects=密钥格式错误或未保存草稿或无云清理进程仍发布
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
    storage.put('cleaner-status.json', json.dumps({'completedAt': int(time.time()) - 181}).encode())
    with pytest.raises(DashboardError) as error:
        shares.publish(service, 'board', 1)
    assert error.value.code == 'CLOUD_CLEANER_UNAVAILABLE'
    service.call('dashboard_patch', {'dashboardId': 'board', 'expectedRevision': 1,
                                   'operations': [{'op': 'set_title', 'value': 'Draft'}]})
    with pytest.raises(DashboardError) as error:
        shares.publish(service, 'board', 2)
    assert error.value.code == 'REVISION_CONFLICT'


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


# @wu-test type=integration | scope=云端网页密钥和到期访问 | protects=未输入密钥直接读取数据或已登录页面过期后仍从云端获取文件
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
        assert '8 位数字访问密钥' in client.get(root).text
        assert client.get(root + 'document.json').status_code == 401
        assert client.get(root + 'app.js').status_code == 401
        assert client.post(root, data={'accessKey': '00000000'}).status_code == 401
        response = client.post(root, data={'accessKey': '01234567'}, follow_redirects=False)
        assert response.status_code == 303
        assert 'HttpOnly' in response.headers['set-cookie'] and 'Secure' in response.headers['set-cookie']
        assert 'mode:"static"' in client.get(root).text
        content = client.get(root + 'document.json')
        assert content.status_code == 200 and 'no-store' in content.headers['cache-control']
        assert '01234567' not in content.text
        deadline = published['expiresAt']
        monkeypatch.setattr(time, 'time', lambda: deadline)
        assert client.get(root + 'document.json').status_code == 410
        assert client.get(root + 'app.js').status_code == 410
        assert cleanup_due(storage, deadline)['removed'] == 1
        assert client.get(root).status_code == 410


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
