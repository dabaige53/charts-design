import io
import json

import qcloud_cos

from dashboard_runtime import cloud_credentials


# @wu-test type=boundary | scope=CloudBaseCosClient | protects=长时间运行后继续使用过期COS凭据导致存储失败
def test_cos_credentials_refresh_without_changing_active_client(monkeypatch):
    clock, exchanges = [100], []

    def exchange(request, timeout):
        exchanges.append(request)
        suffix = str(len(exchanges))
        return io.BytesIO(json.dumps({'code': 0, 'data': {
            'TmpSecretId': 'test-id-' + suffix,
            'TmpSecretKey': 'test-secret-' + suffix, 'Token': 'test-token-' + suffix}}).encode())

    monkeypatch.setattr(cloud_credentials.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(cloud_credentials, 'urlopen', exchange)
    monkeypatch.setattr(qcloud_cos, 'CosS3Client', lambda config: config)
    provider = cloud_credentials.CloudBaseCosClient('ap-shanghai', 'test-env', 'test-key', 'ap-shanghai')
    first = provider._current()
    clock[0] = 1299
    assert provider._current() is first
    clock[0] = 1300
    second = provider._current()
    assert second is not first
    assert len(exchanges) == 2
