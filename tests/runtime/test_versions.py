import pytest

from dashboard_runtime.model import DashboardError
from dashboard_runtime.project import ProjectStore
from dashboard_runtime.versions import Versions


# @wu-test type=behavior | scope=Versions lifecycle | protects=保存或恢复草稿意外改变正式发布内容
def test_save_publish_restore_are_separate(tmp_path):
    store = ProjectStore(tmp_path / 'project', tmp_path / 'runtime')
    store.create('board', 'Original')
    versions = Versions(store)
    assert versions.status('board')['publishedRevision'] is None
    versions.publish('board', 1, 1)
    store.mutate('board', 1, [{'op': 'set_title', 'value': 'New draft'}])
    store.checkpoint('board', 2, name='Saved')
    assert versions.status('board')['publishedRevision'] == 1
    versions.publish('board', 2, 2)
    versions.publish('board', 2, 2)
    assert len(versions.status('board')['releases']) == 2
    restored = store.mutate('board', 2, restore_revision=1)
    assert restored['revision'] == 3
    status = versions.status('board')
    assert (status['draftRevision'], status['savedRevision'], status['publishedRevision']) == (3, 2, 2)
    assert versions.read('board', 2)['manifest']['title'] == 'New draft'


# @wu-test type=boundary | scope=Versions.publish | protects=过期操作或未保存的草稿被直接发布
def test_publish_requires_current_draft_and_saved_revision(tmp_path):
    store = ProjectStore(tmp_path / 'project', tmp_path / 'runtime')
    store.create('board', 'Original')
    versions = Versions(store)
    store.mutate('board', 1, [{'op': 'set_title', 'value': 'Draft'}])
    with pytest.raises(DashboardError) as stale:
        versions.publish('board', 1, 1)
    assert stale.value.code == 'REVISION_CONFLICT'
    with pytest.raises(DashboardError) as unsaved:
        versions.publish('board', 2, 2)
    assert unsaved.value.code == 'NOT_FOUND'


# @wu-test type=behavior | scope=Versions release archive | protects=保存历史清理后正式发布记录丢失并无法回退发布
def test_release_remains_readable_after_checkpoint_pruning(tmp_path):
    store = ProjectStore(tmp_path / 'project', tmp_path / 'runtime')
    store.create('board', 'Original')
    versions = Versions(store)
    versions.publish('board', 1, 1)
    store.config['history']['keepCheckpoints'] = 1
    store.mutate('board', 1, [{'op': 'set_title', 'value': 'Next'}])
    store.checkpoint('board', 2)
    assert [item['revision'] for item in store.history('board')] == [2]
    assert versions.read('board', 1)['manifest']['title'] == 'Original'
    versions.publish('board', 2, 2)
    assert versions.publish('board', 2, 1)['publishedRevision'] == 1
