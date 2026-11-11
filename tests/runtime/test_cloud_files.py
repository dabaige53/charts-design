"""File durability boundaries without making network calls."""
import hashlib

import pytest

from dashboard_runtime.cloud_files import CloudFiles
from dashboard_runtime.model import DashboardError


class ObjectStorage:
    def __init__(self):
        self.objects = {}

    def put(self, key, content, content_type):
        self.objects[key] = content

    def get(self, key):
        return self.objects.get(key)


class FileCatalog:
    def __init__(self):
        self.files = {}

    def call(self, action, project, **payload):
        identity = project, payload['path']
        if action == 'file_put':
            self.files[identity] = payload['key']
            return True
        assert action == 'file_get'
        return self.files.get(identity)


# @wu-test type=integration | scope=CloudFiles | protects=容器目录丢失后导出文件仍可恢复且项目互不混读
def test_file_restores_from_durable_storage(tmp_path):
    catalog, objects = FileCatalog(), ObjectStorage()
    source = tmp_path / 'source.csv'
    source.write_bytes(b'a,b\n1,2\n')
    CloudFiles(catalog, objects).save('one', 'exports/data.csv', source)
    source.unlink()
    target = tmp_path / 'fresh' / 'data.csv'
    assert not CloudFiles(catalog, objects).restore('two', 'exports/data.csv', target)
    assert CloudFiles(catalog, objects).restore('one', 'exports/data.csv', target)
    assert target.read_bytes() == b'a,b\n1,2\n'


# @wu-test type=boundary | scope=CloudFiles.restore | protects=缺失或损坏的云文件不能作为有效下载返回
@pytest.mark.parametrize('content', [None, b'corrupt'])
def test_file_rejects_missing_or_corrupt_object(tmp_path, content):
    catalog, objects = FileCatalog(), ObjectStorage()
    key = 'one/' + hashlib.sha256(b'original').hexdigest()
    catalog.files[('one', 'data.csv')] = key
    if content is not None:
        objects.objects[key] = content
    with pytest.raises(DashboardError):
        CloudFiles(catalog, objects).restore('one', 'data.csv', tmp_path / 'data.csv')
    assert not (tmp_path / 'data.csv').exists()
