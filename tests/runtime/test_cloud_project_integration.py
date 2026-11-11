"""Explicit cloud-only integration suite; run with injected environment credentials.

Never included in the default local suite. Uses a fresh, recorded project name.
"""
import json
import os
from pathlib import Path
import shutil
import uuid

import pytest

from dashboard_runtime.cloud_database import CloudDatabase
from dashboard_runtime.cloud_project import CloudProjectStore
from dashboard_runtime.model import DashboardError

pytestmark = pytest.mark.skipif(os.environ.get('CHARTS_RUN_CLOUD_TESTS') != '1',
                                reason='Requires explicit cloud integration invocation')


@pytest.fixture
def cloud_project(tmp_path):
    project = 'storage-test-' + uuid.uuid4().hex[:16]
    # Record exact names for subsequent scoped cleanup; never delete by wildcard.
    with Path('/private/tmp/charts-cloudbase-test-projects.jsonl').open('a') as output:
        output.write(json.dumps(project) + '\n')
    return CloudProjectStore(tmp_path / project, tmp_path / 'cache'), tmp_path, project


# @wu-test type=integration | scope=CloudProjectStore | protects=草稿历史批注在容器重建后丢失或并发更新覆盖
def test_project_state_survives_empty_cache(cloud_project):
    store, root, project = cloud_project
    created = store.create('board', 'Cloud persistence')
    assert created['revision'] == 1
    changed = store.mutate('board', 1, [{'op': 'set_title', 'value': 'Saved title'}])
    assert changed['revision'] == 2
    note = {'id': 'note', 'componentId': None, 'text': 'Retain this note', 'createdAt': '2026-11-11'}
    store.mutate('board', 2, [{'op': 'set_annotations', 'value': [note]}], expected_annotations=[])
    batch = store.begin('board', 2)
    store.checkpoint('board', 2, name='Saved', batch_id=batch['batch_id'])
    with pytest.raises(DashboardError) as conflict:
        store.mutate('board', 1, [{'op': 'set_title', 'value': 'Stale'}])
    assert conflict.value.code == 'REVISION_CONFLICT'
    shutil.rmtree(root / 'cache')
    shutil.rmtree(root / project)
    restored = CloudProjectStore(root / project, root / 'fresh-cache')
    assert restored.get('board')['manifest']['title'] == 'Saved title'
    assert restored.get('board')['manifest']['annotations'][0]['text'] == 'Retain this note'
    assert restored.history('board')[0]['name'] == 'Saved'
    assert restored.readable('board')['revision'] == 2
    assert project in CloudDatabase().call('projects')
    assert restored.mutate('board', 2, restore_revision=1)['revision'] == 3


# @wu-test type=integration | scope=CloudData | protects=数据缓存删除后原始行顺序缺失字段布尔值和查询语义丢失
def test_dataset_rebuild_preserves_rows_and_queries(cloud_project):
    store, root, project = cloud_project
    fields = {'z': {'type': 'number'}, 'label': {'type': 'string'}, 'active': {'type': 'boolean'}}
    rows = [{'z': i, 'label': f'row {i}', 'active': i % 2 == 0} for i in range(503)]
    rows += [{'z': None, 'label': None}, {'z': 1.5, 'label': 'tail', 'active': False}]
    ref = store.data.import_rows(rows, fields)
    shutil.rmtree(root / 'cache')
    fresh = CloudProjectStore(root / project, root / 'fresh-cache')
    assert fresh.data.describe(ref['version']) == ref
    assert list(fresh.data.iter_rows(ref)) == rows
    result = fresh.data.rows(ref, filters=[{'field': 'z', 'op': 'range', 'values': [500, 502]}])
    assert result['totalRows'] == 3
    assert result['rows'] == rows[500:503]
    assert fresh.data.aggregate(ref, {'total': {'aggregation': 'sum', 'field': 'z'}})[0]['total'] == sum(range(503)) + 1.5


# @wu-test type=integration | scope=CloudDatabase generations | protects=实例更换后已撤销链接重新生效
def test_link_revocation_survives_new_client(cloud_project):
    store, _, project = cloud_project
    assert store.database.call('generation', project, board='board') == 0
    assert store.database.call('revoke', project, board='board') == 1
    assert CloudDatabase().call('generation', project, board='board') == 1


# @wu-test type=integration | scope=CloudFiles | protects=真实COS上传后新实例不能恢复相同导出文件
def test_cos_export_survives_empty_local_directory(cloud_project):
    from dashboard_runtime.cloud_files import CloudFiles
    store, root, project = cloud_project
    files = CloudFiles(store.database)
    source = root / 'sample.csv'
    source.write_bytes(b'name,value\nsample,42\n')
    try:
        files.save(project, 'dashboards/exports/sample.csv', source)
        source.unlink()
        restored = root / 'new-instance' / 'sample.csv'
        assert CloudFiles(store.database).restore(project, 'dashboards/exports/sample.csv', restored)
        assert restored.read_bytes() == b'name,value\nsample,42\n'
    finally:
        files.storage.delete_prefix(project + '/')


# @wu-test type=integration | scope=PostgreSQL release lifecycle | protects=云端发布状态随草稿或实例更换意外变化
def test_cloud_release_lifecycle(cloud_project):
    from dashboard_runtime.versions import Versions
    store, root, project = cloud_project
    store.create('board', 'Original')
    versions = Versions(store)
    assert versions.publish('board', 1, 1)['publishedRevision'] == 1
    store.mutate('board', 1, [{'op': 'set_title', 'value': 'Next'}])
    store.checkpoint('board', 2)
    assert versions.status('board')['publishedRevision'] == 1
    versions.publish('board', 2, 2)
    versions.publish('board', 2, 2)
    assert len(versions.status('board')['releases']) == 2
    store.mutate('board', 2, restore_revision=1)
    fresh = Versions(CloudProjectStore(root / project, root / 'fresh-cache'))
    state = fresh.status('board')
    assert (state['draftRevision'], state['savedRevision'], state['publishedRevision']) == (3, 2, 2)
    assert fresh.read('board', 2)['manifest']['title'] == 'Next'
