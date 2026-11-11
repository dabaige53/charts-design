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
def test_transfer_resume_verification_and_cleanup(tmp_path):
    fields = {'value': {'type': 'number'}, 'label': {'type': 'string'}}
    rows = [{'value': i, 'label': str(i)} for i in range(503)]
    source = LocalData(tmp_path / 'source')
    ref = source.import_rows(rows, fields)
    data = CloudData(tmp_path / 'remote', MemoryDatabase(), 'fixture')
    data.transfer_storage = MemoryStorage()
    upload = 'a' * 64
    data.transfer_chunk(upload, ref, 0, rows[:500])
    data.transfer_chunk(upload, ref, 0, rows[:500])
    with pytest.raises(DashboardError):
        data.transfer_chunk(upload, ref, 0, [rows[1]] * 500)
    data.transfer_finish(upload, ref)
    assert wait(data, upload, ref)['code'] == 'DATA_INCOMPLETE'
    assert data.database.call('data_get', 'fixture', version=ref['version']) is None
    data.transfer_chunk(upload, ref, 1, rows[500:])
    data.transfer_finish(upload, ref)
    assert wait(data, upload, ref)['state'] == 'complete'
    assert not data.transfer_storage.objects
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
def test_transfer_rejects_wrong_content_and_can_restart(tmp_path):
    fields = {'value': {'type': 'number'}}
    ref = LocalData(tmp_path / 'source').import_rows([{'value': 1}], fields)
    database, storage = MemoryDatabase(), MemoryStorage()
    data = CloudData(tmp_path / 'cache', database, 'fixture')
    data.transfer_storage = storage
    upload = 'b' * 64
    data.transfer_chunk(upload, ref, 0, [{'value': 2}])
    data.transfer_finish(upload, ref)
    assert wait(data, upload, ref)['code'] == 'DATA_CONFLICT'
    assert database.call('data_get', 'fixture', version=ref['version']) is None
    data.transfer_cleanup(upload)
    data.transfer_chunk(upload, ref, 0, [{'value': 1}])
    restarted = CloudData(tmp_path / 'other-cache', database, 'fixture')
    restarted.transfer_storage = storage
    assert restarted.transfer_status(upload, ref)['state'] == 'unknown'
    restarted.transfer_finish(upload, ref)
    assert wait(restarted, upload, ref)['state'] == 'complete'
    assert not storage.objects

