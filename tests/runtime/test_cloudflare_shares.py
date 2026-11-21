import json

from dashboard_runtime.cloudflare_shares import clean
from dashboard_runtime.cloud_shares import CloudShares
from dashboard_runtime.demo import executive_document
from dashboard_runtime.service import Service


# @wu-test type=integration | scope=Cloudflare 分享发布与撤销 | protects=真实项目不能用独立密钥访问或撤销后仍能读取副本
def test_publish_and_revoke_without_tencent(tmp_path, monkeypatch):
    monkeypatch.setenv('CHARTS_STORAGE_BACKEND', 'cloudflare')
    monkeypatch.setenv('CHARTS_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CHARTS_PUBLIC_URL', 'https://example.org')
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.call('dashboard_create', {'dashboardId': 'board', 'document': executive_document('board')})
    service.call('dashboard_version_publish', {'dashboardId': 'board', 'expectedRevision': 1, 'revision': 1})
    clean()
    share = service.call('dashboard_share_publish', {'dashboardId': 'board', 'expectedRevision': 1})
    gateway = CloudShares.from_environment()
    assert gateway.authenticate(share['shareId'], share['accessKey'])['revision'] == 1
    assert gateway.content(share['shareId'], 'index.html')
    removed = service.call('dashboard_share_delete', {'dashboardId': 'board', 'shareId': share['shareId']})
    assert removed['cleanupExecutor'] == 'cloudflare-cron'
    clean()
    assert not gateway.storage.list('shares/')
    assert service.store.get('board')['revision'] == 1


# @wu-test type=integration | scope=Cloudflare 私密分享清理 | protects=清理误连腾讯云或误删尚未过期的分享
def test_cloudflare_cleanup_is_independent(tmp_path, monkeypatch):
    monkeypatch.setenv('CHARTS_STORAGE_BACKEND', 'cloudflare')
    monkeypatch.setenv('CLOUDBASE_API_KEY', 'unused')
    monkeypatch.setenv('CHARTS_RUNTIME_ROOT', str(tmp_path))
    monkeypatch.setenv('CHARTS_PUBLIC_URL', 'https://example.org')
    shares = CloudShares.from_environment()
    assert shares.executor == 'cloudflare-cron'
    shares.storage.check_private()
    for share_id, deadline in [('a' * 32, 0), ('b' * 32, None)]:
        shares.storage.put(f'jobs/{share_id}.json', json.dumps({'shareId': share_id, 'cleanupAfter': deadline}).encode())
        shares.storage.put(f'shares/{share_id}/site/document.json', b'{}')
    clean()
    assert shares.storage.list('jobs/') == ['jobs/' + 'b' * 32 + '.json']
    assert shares.storage.get('shares/' + 'a' * 32 + '/site/document.json') is None
    assert shares.storage.get('shares/' + 'b' * 32 + '/site/document.json') == b'{}'
    assert json.loads(shares.storage.get('cleaner-status.json'))['executor'] == 'cloudflare-cron'
