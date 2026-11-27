from contextlib import closing, contextmanager

import pytest
import json
import sqlite3

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


# @wu-test type=behavior | scope=Versions release archive | protects=旧版本裁剪过检查点后正式发布记录丢失并无法回退发布
def test_release_remains_readable_without_legacy_checkpoint(tmp_path):
    store = ProjectStore(tmp_path / 'project', tmp_path / 'runtime')
    store.create('board', 'Original')
    versions = Versions(store)
    versions.publish('board', 1, 1)
    store.mutate('board', 1, [{'op': 'set_title', 'value': 'Next'}])
    store.checkpoint('board', 2)
    # Model a project saved by an older runtime, which pruned checkpoints but not its release archive.
    # A confirmed deletion in the current runtime intentionally removes both.
    with store.connect() as db:
        db.execute('DELETE FROM revisions WHERE board_id=? AND revision=?', ('board', 1))
    assert [item['revision'] for item in store.history('board')] == [2]
    assert versions.read('board', 1)['manifest']['title'] == 'Original'
    versions.publish('board', 2, 2)
    assert versions.publish('board', 2, 1)['publishedRevision'] == 1


# @wu-test type=performance | scope=Versions 初始化与读取 | protects=每次版本读取回填发布历史并争用 SQLite 写锁
def test_repeated_version_reads_do_not_take_a_database_write_lock(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path / 'project', tmp_path / 'runtime')
    store.create('board', 'Original')
    versions = Versions(store)
    versions.publish('board', 1, 1)

    @contextmanager
    def connect_without_wait():
        with closing(sqlite3.connect(store.path, timeout=0)) as connection, connection:
            connection.row_factory = sqlite3.Row
            yield connection

    monkeypatch.setattr(store, 'connect', connect_without_wait)
    with store.connect() as writer:
        writer.execute('BEGIN IMMEDIATE')
        assert Versions(store).status('board')['publishedRevision'] == 1
        assert Versions(store).read('board', 1)['manifest']['title'] == 'Original'


# @wu-test type=integration | scope=旧发布历史迁移 | protects=升级后丢失旧发布指针或重启时自动恢复已明确清空的发布版本
def test_version_initialization_preserves_legacy_and_cleared_heads(tmp_path):
    store = ProjectStore(tmp_path / 'project', tmp_path / 'runtime')
    store.create('board', 'Original')
    with store.connect() as db:
        db.execute('''CREATE TABLE releases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, board_id TEXT NOT NULL,
            revision INTEGER NOT NULL, created_at TEXT NOT NULL, document TEXT NOT NULL)''')
        db.execute("INSERT INTO releases(board_id,revision,created_at,document) SELECT id,revision,'2026-11-26',document FROM boards")
    assert Versions(store).status('board')['publishedRevision'] == 1
    with store.connect() as db:
        db.execute('UPDATE version_heads SET published=NULL WHERE board_id=?', ('board',))
    reopened = ProjectStore(store.project_root, tmp_path / 'other-runtime')
    versions = Versions(reopened)
    assert versions.status('board')['publishedRevision'] is None
    assert versions.read('board', 1)['manifest']['title'] == 'Original'


# @wu-test type=boundary | scope=Versions.status 一致性快照 | protects=并发保存发布使一次状态返回旧草稿号与新保存发布号的混合状态
def test_status_uses_one_snapshot_across_concurrent_publication(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path / 'project', tmp_path / 'runtime')
    store.create('board', 'Original')
    versions = Versions(store)
    versions.publish('board', 1, 1)
    original_connect = store.connect
    advanced = False

    class InterleavingConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            nonlocal advanced
            if sql.startswith('SELECT max(revision) FROM revisions') and not advanced:
                advanced = True
                with original_connect() as writer:
                    writer.execute('BEGIN IMMEDIATE')
                    doc = json.loads(writer.execute('SELECT document FROM boards WHERE id=?', ('board',)).fetchone()[0])
                    doc['revision'] = 2
                    doc['manifest']['title'] = 'Concurrent publication'
                    raw = json.dumps(doc)
                    writer.execute('UPDATE boards SET revision=2, document=? WHERE id=?', (raw, 'board'))
                    writer.execute('INSERT INTO revisions VALUES(?,?,?,?,?)', ('board', 2, '2026-11-26', 'checkpoint', raw))
                    writer.execute('INSERT INTO releases(board_id,revision,created_at,document) VALUES(?,?,?,?)', ('board', 2, '2026-11-26', raw))
                    writer.execute('UPDATE version_heads SET published=2 WHERE board_id=?', ('board',))
            return super().execute(sql, parameters)

    @contextmanager
    def connect():
        with closing(sqlite3.connect(store.path, timeout=0, factory=InterleavingConnection)) as db, db:
            db.row_factory = sqlite3.Row
            yield db

    monkeypatch.setattr(store, 'connect', connect)
    status = versions.status('board')
    assert advanced
    assert (status['draftRevision'], status['savedRevision'], status['publishedRevision']) == (1, 1, 1)
    assert [release['revision'] for release in status['releases']] == [1]
    fresh = versions.status('board')
    assert (fresh['draftRevision'], fresh['savedRevision'], fresh['publishedRevision']) == (2, 2, 2)


# @wu-test type=boundary | scope=Versions.read 历史归档快照 | protects=读取旧版本时检查点与发布归档跨越删除事务而产生错误的版本不存在
def test_release_fallback_keeps_its_snapshot_during_deletion(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path / 'project', tmp_path / 'runtime')
    store.create('board', 'Original')
    versions = Versions(store)
    versions.publish('board', 1, 1)
    with store.connect() as db:
        db.execute('DELETE FROM revisions WHERE board_id=?', ('board',))
    original_connect = store.connect
    deleted = False

    class InterleavingConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            nonlocal deleted
            if sql.startswith('SELECT document FROM releases') and not deleted:
                deleted = True
                with original_connect() as writer:
                    writer.execute('DELETE FROM releases WHERE board_id=?', ('board',))
                    writer.execute('UPDATE version_heads SET published=NULL WHERE board_id=?', ('board',))
            return super().execute(sql, parameters)

    @contextmanager
    def connect():
        with closing(sqlite3.connect(store.path, timeout=0, factory=InterleavingConnection)) as db, db:
            db.row_factory = sqlite3.Row
            yield db

    monkeypatch.setattr(store, 'connect', connect)
    assert versions.read('board', 1)['manifest']['title'] == 'Original'
    assert deleted
    with pytest.raises(DashboardError) as removed:
        versions.read('board', 1)
    assert removed.value.code == 'NOT_FOUND'
