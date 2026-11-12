from concurrent.futures import ThreadPoolExecutor
import copy
import uuid

import pytest

from dashboard_runtime.model import DashboardError
from dashboard_runtime.project import ProjectStore


def command(action, key, **kwargs):
    return {'operationId': uuid.uuid4().hex, 'action': action, 'annotationId': key, **kwargs}


def add(key):
    return command('add', key, value={'text': key, 'componentId': None, 'createdAt': '2026-11-12'})


@pytest.fixture
def store(tmp_path):
    result = ProjectStore(tmp_path / 'project', tmp_path / 'runtime')
    result.create('board', 'Concurrent comments')
    return result


# @wu-test type=integration | scope=ProjectStore.annotation_command | protects=五个独立连接同时新增回复或修改不同批注时丢失内容
def test_five_clients_append_reply_edit_and_preserve_design(store):
    def client(cmd):
        independent = ProjectStore(store.project_root, store.runtime_root)
        return independent.annotation_command('board', 1, cmd)
    with ThreadPoolExecutor(5) as pool:
        list(pool.map(client, [add(f'n{i}') for i in range(5)]))
        list(pool.map(client, [command('reply', 'n0', value={
            'id': f'r{i}', 'text': f'Reply {i}', 'createdAt': '2026-11-12'}) for i in range(5)]))
        list(pool.map(client, [command('edit', f'n{i}', expectedVersion=1,
                                     value={'text': f'Edited {i}'}) for i in range(5)]))
    doc = store.get('board')
    assert len(doc['manifest']['annotations']) == 5
    assert len(next(n for n in doc['manifest']['annotations'] if n['id'] == 'n0')['replies']) == 5
    assert {n['text'] for n in doc['manifest']['annotations']} == {f'Edited {i}' for i in range(5)}
    assert doc['revision'] == 1
    changed = store.mutate('board', 1, [{'op': 'set_title', 'value': 'Design change'}])
    assert len(changed['manifest']['annotations']) == 5
    assert changed['manifest']['title'] == 'Design change'


# @wu-test type=boundary | scope=annotation operation receipts | protects=响应丢失重试产生重复内容或删除后重试使批注复活
def test_retries_conflicts_and_deleted_targets(store):
    original = add('note')
    first = store.annotation_command('board', 1, original)
    assert store.annotation_command('board', 1, original) == first
    changed = copy.deepcopy(original)
    changed['value']['text'] = 'Reused operation'
    with pytest.raises(DashboardError, match='Operation ID'):
        store.annotation_command('board', 1, changed)
    reply = command('reply', 'note', value={'id': 'reply', 'text': 'Response', 'createdAt': 'today'})
    store.annotation_command('board', 1, reply)
    store.annotation_command('board', 1, reply)
    assert len(store.get('board')['manifest']['annotations'][0]['replies']) == 1
    store.annotation_command('board', 1, command('edit', 'note', expectedVersion=1, value={'text': 'New text'}))
    with pytest.raises(DashboardError) as conflict:
        store.annotation_command('board', 1, command('edit', 'note', expectedVersion=1, value={'text': 'Stale'}))
    assert conflict.value.code == 'ANNOTATION_CONFLICT'
    store.annotation_command('board', 1, command('delete', 'note', expectedVersion=2))
    store.annotation_command('board', 1, original)
    assert store.get('board')['manifest']['annotations'] == []
    with pytest.raises(DashboardError) as missing:
        store.annotation_command('board', 1, command('reply', 'note', value={'id': 'r2', 'text': 'Lost', 'createdAt': 'today'}))
    assert missing.value.code == 'ANNOTATION_NOT_FOUND'


# @wu-test type=boundary | scope=annotation command validation | protects=不存在的版本非法正文和已解决目标收到回复
def test_version_text_and_status_guards(store):
    with pytest.raises(DashboardError):
        store.annotation_command('board', 99, add('note'))
    with pytest.raises(DashboardError):
        store.annotation_command('board', 1, command('add', 'note', value={'text': '', 'createdAt': 'today'}))
    store.annotation_command('board', 1, add('note'))
    store.annotation_command('board', 1, command('status', 'note', expectedStatus='open', status='resolved'))
    with pytest.raises(DashboardError):
        store.annotation_command('board', 1, command('reply', 'note', value={'id': 'r', 'text': 'Closed', 'createdAt': 'today'}))


# @wu-test type=integration | scope=legacy annotation replacement | protects=旧客户端改正文未更新条目版本导致新客户端覆盖其修改
def test_legacy_replacement_advances_content_version(store):
    store.annotation_command('board', 1, add('note'))
    previous = store.get('board')['manifest']['annotations']
    changed = copy.deepcopy(previous)
    changed[0]['text'] = 'Legacy edit'
    store.mutate('board', 1, [{'op': 'set_annotations', 'value': changed}], expected_annotations=previous)
    with pytest.raises(DashboardError) as conflict:
        store.annotation_command('board', 1, command('edit', 'note', expectedVersion=1, value={'text': 'Stale'}))
    assert conflict.value.code == 'ANNOTATION_CONFLICT'
