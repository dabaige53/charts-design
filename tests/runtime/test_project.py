from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier
import json
import sqlite3

from dashboard_runtime.service import Service
from dashboard_runtime.model import DashboardError
import pytest


# @wu-test type=boundary | scope=Store connection lifecycle | protects=成功异常或提交失败后连接依赖GC回收、回滚丢失或嵌套连接共用未提交事务
@pytest.mark.parametrize('outcome', ['commit', 'body_error', 'commit_error'])
def test_store_connections_close_after_commit_and_rollback(tmp_path, outcome):
    from dashboard_runtime.store import Store

    store = Store(tmp_path / 'store')
    with store.connect() as setup:
        setup.execute('CREATE TABLE lifecycle_parent (id INTEGER PRIMARY KEY)')
        setup.execute('CREATE TABLE lifecycle_child (parent INTEGER REFERENCES lifecycle_parent(id) DEFERRABLE INITIALLY DEFERRED)')
        setup.execute('INSERT INTO lifecycle_parent VALUES(1)')
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        setup.execute('SELECT 1')

    def transaction():
        nonlocal connection, nested
        with store.connect() as connection:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('INSERT INTO lifecycle_parent VALUES(2)')
            with store.connect() as nested:
                assert nested is not connection
                assert [row['id'] for row in nested.execute('SELECT id FROM lifecycle_parent')] == [1]
            with pytest.raises(sqlite3.ProgrammingError, match='closed'):
                nested.execute('SELECT 1')
            assert connection.execute('SELECT count(*) FROM lifecycle_parent').fetchone()[0] == 2
            if outcome == 'body_error':
                raise RuntimeError('body failed')
            if outcome == 'commit_error':
                connection.execute('INSERT INTO lifecycle_child VALUES(99)')

    connection = nested = None
    if outcome == 'commit':
        transaction()
    else:
        expected = RuntimeError if outcome == 'body_error' else sqlite3.IntegrityError
        with pytest.raises(expected):
            transaction()
    # Keep the actual objects alive: success must not depend on refcount or GC.
    assert connection is not None and nested is not None
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        connection.execute('SELECT 1')
    with store.connect() as verified:
        assert [row['id'] for row in verified.execute('SELECT id FROM lifecycle_parent')] == ([1, 2] if outcome == 'commit' else [1])
        assert verified.execute('SELECT count(*) FROM lifecycle_child').fetchone()[0] == 0
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        verified.execute('SELECT 1')


# @wu-test type=integration | scope=独立批注读写 | protects=读取或提交批注会加载整页，或者旧批注列表覆盖并发修改
def test_annotations_use_their_own_read_and_write_path(tmp_path, monkeypatch):
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    board = {'dashboardId': 'board'}
    service.call('dashboard_create', {**board, 'title': 'Board'})

    def unexpected(*args, **kwargs):
        pytest.fail('Independent annotations must not load or save the full dashboard')

    monkeypatch.setattr(service.store, 'get', unexpected)
    monkeypatch.setattr(service.store, 'mutate', unexpected)
    initial = service.call('dashboard_annotations', {**board, 'includeTargets': False})
    args = {**board, 'expectedRevision': initial['revision'], 'expectedAnnotations': initial['annotations'],
            'annotations': [{'id': 'note', 'componentId': None, 'text': 'Reviewed', 'createdAt': '2026-11-25'}]}
    saved = service.call('dashboard_annotations_update', args)
    assert saved['revision'] == initial['revision'] and 'document' not in saved
    assert saved['annotations'][0]['text'] == 'Reviewed'
    with pytest.raises(DashboardError, match='批注|annotations') as failure:
        service.call('dashboard_annotations_update', {**args, 'annotations': []})
    assert failure.value.code == 'ANNOTATION_CONFLICT'
    assert service.call('dashboard_annotations', board)['annotations'] == saved['annotations']


# @wu-test type=integration | scope=独立新增批注 | protects=同时新增时漏存一条，或重试时重复新增
def test_concurrent_annotation_appends_are_merged(tmp_path, monkeypatch):
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    board = {'dashboardId': 'board'}
    service.call('dashboard_create', {**board, 'title': 'Board'})
    initial = service.store.revision('board')

    def unexpected(*args, **kwargs):
        pytest.fail('Appending an annotation must not load or save the full dashboard')

    monkeypatch.setattr(service.store, 'get', unexpected)
    monkeypatch.setattr(service.store, 'mutate', unexpected)
    ready = Barrier(2, timeout=5)

    def append(note_id):
        return service.call('dashboard_annotations_update', {**board, 'append': {
            'id': note_id, 'componentId': None, 'text': note_id, 'createdAt': '2026-11-25',
        }})

    def submit(note_id):
        ready.wait()
        return append(note_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(submit, ('first', 'second')))
    assert all(item.keys() == {'dashboardId', 'revision', 'annotation'} and item['revision'] == initial
               for item in (first, second))
    assert append('first') == first
    saved = service.call('dashboard_annotations', {**board, 'includeTargets': False})['annotations']
    assert {item['id'] for item in saved} == {'first', 'second'}
    assert len(saved) == 2
    folder = service.store.root / 'board'
    assert json.loads((folder / 'annotations.json').read_text()) == saved
    events = json.loads((folder / 'annotation-history.json').read_text())
    assert len(events) == 2 and json.loads(events[-1]['payload']) == saved


# @wu-test type=integration | scope=项目草稿检查点 | protects=编辑恢复删除运行缓存后丢批注
def test_drafts_checkpoints_notes_and_runtime_removal(tmp_path):
    project, runtime = tmp_path/'project', tmp_path/'runtime'
    service = Service(runtime, project_root=project)
    service.call('dashboard_create', {'dashboardId':'board','title':'Original'})
    batch = service.call('dashboard_edit_begin', {'dashboardId':'board','expectedRevision':1})
    note={'id':'note','componentId':None,'text':'Keep me','createdAt':'2026-10-28'}
    for revision, operations in [(1,[{'op':'set_title','value':'Updated'}]),(2,[{'op':'set_annotations','value':[note]}])]:
        service.call('dashboard_patch', {'dashboardId':'board','expectedRevision':revision,'operations':operations})
    assert len(service.store.history('board')) == 1
    assert service.call('runtime_info',{'dashboardId':'board'})['dashboardRevision']==1
    assert service.call('dashboard_refresh',{'dashboardId':'board'})['document']['manifest']['title']=='Original'
    service.call('dashboard_patch', {'dashboardId':'board','expectedRevision':3,'operations':[{'op':'set_title','value':'Updated'}]})
    assert service.store.revision('board') == 3
    done=service.call('dashboard_edit_finish', {'dashboardId':'board','expectedRevision':3,'batchId':batch['batch_id'],'name':'Approved'})
    assert done['ok']
    assert done['nextAction'] == 'dashboard_preview'
    assert done['displayPolicy'] == 'saved-dashboard-ui'
    assert len(service.store.history('board')) == 2
    restored=service.call('dashboard_restore', {'dashboardId':'board','expectedRevision':3,'revision':1})['document']
    assert restored['manifest']['title']=='Original'
    assert restored['manifest']['annotations'][0]['text']=='Keep me'
    import shutil
    shutil.rmtree(runtime)
    reopened=Service(runtime, project_root=project)
    assert reopened.store.get('board')['manifest']['annotations'][0]['text']=='Keep me'
    assert (project/'dashboards/board/draft.json').exists()
    assert not (runtime/'data.sqlite3').exists()


# @wu-test type=integration | scope=dashboard_submit | protects=组件计算失败后丢失修订或把未通过的草稿保存为检查点
def test_submit_keeps_failed_draft_for_correction(tmp_path, monkeypatch):
    from dashboard_runtime.demo import executive_document

    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    board = {'dashboardId': 'review'}
    service.call('dashboard_create', {**board, 'document': executive_document('review')})

    def unavailable(*args, **kwargs):
        raise DashboardError('ASSET_UNAVAILABLE', 'Data unavailable')

    with monkeypatch.context() as patch:
        patch.setattr(service.views, 'aggregate', unavailable)
        failed = service.call('dashboard_submit', {**board, 'expectedRevision': 1,
                              'operations': [{'op': 'set_title', 'value': 'Updated'}]})
    assert not failed['ok'] and failed['error']['code'] == 'DOCTOR_FAILED'
    assert failed['revision'] == 2 and service.store.display_revision('review') == 1
    assert service.store.get('review')['manifest']['title'] == 'Updated'
    saved = service.call('dashboard_submit', {**board, 'expectedRevision': failed['revision']})
    assert saved['ok'] and saved['checkpoint']['revision'] == 2


# @wu-test type=behavior | scope=dashboard_publish 内容检查 | protects=检查失败的保存版替换正式发布版
def test_publish_preserves_previous_release_on_failed_checks(tmp_path, monkeypatch):
    from dashboard_runtime.demo import executive_document

    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    board = {'dashboardId': 'review'}
    service.call('dashboard_create', {**board, 'document': executive_document('review')})
    assert service.call('dashboard_publish', {**board, 'revision': 1})['publishedRevision'] == 1
    service.call('dashboard_patch', {**board, 'expectedRevision': 1,
                 'operations': [{'op': 'set_title', 'value': 'Updated'}]})
    service.store.checkpoint('review', 2)

    def unavailable(*args, **kwargs):
        raise DashboardError('ASSET_UNAVAILABLE', 'Data unavailable')

    monkeypatch.setattr(service.views, 'aggregate', unavailable)
    failure = service.call('dashboard_publish', {**board, 'revision': 2})
    assert not failure['ok'] and failure['error']['code'] == 'DOCTOR_FAILED'
    status = service.call('dashboard_version_status', board)
    assert status['draftRevision'] == 2
    assert status['publishedRevision'] == 1 and status['savedRevision'] == 2


# @wu-test type=integration | scope=dashboard_view | protects=筛选后计算值与返回的口径、来源或数据版本不一致
def test_component_view_returns_evidence_for_the_effective_slice(tmp_path):
    from dashboard_runtime.demo import executive_document

    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    board = {'dashboardId': 'board'}
    doc = service.call('dashboard_create', {**board, 'document': executive_document('board')})['document']
    selected_filter = {**doc['manifest']['filters'][0], 'values': ['missing-region']}
    view = service.call('dashboard_view', {**board, 'expectedRevision': doc['revision'],
                        'componentIds': ['total'], 'filters': [selected_filter], 'includeEvidence': True})
    evidence = view['evidence']['total']
    assert view['revision'] == doc['revision'] and 'total' in view['computed']['components']
    assert evidence['filters'] == [selected_filter]
    assert evidence['localVersion']['version'] == doc['snapshot']['datasetRefs']['sales']['version']
    assert evidence['metrics']['revenue'] == doc['manifest']['metrics']['revenue']
    assert evidence['source'] == doc['manifest']['sources']['fixture']
    assert service.store.get('board')['manifest']['filters'][0]['values'] == []


# @wu-test type=integration | scope=dashboard_doctor 与 dashboard_checkpoint | protects=相同草稿保存时重复计算组件，或草稿改变后沿用旧检查
def test_checkpoint_reuses_only_an_unchanged_full_doctor_report(tmp_path):
    from dashboard_runtime.demo import executive_document

    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    board = {'dashboardId': 'board'}
    service.call('dashboard_create', {**board, 'document': executive_document('board')})

    def stages(report):
        return {event['stage'] for event in service.call('runtime_diagnostics', {
            'requestId': report['requestId'], 'limit': 100,
        })['events']}

    full = service.call('dashboard_doctor', {**board, 'mode': 'full'})
    assert full['passed'] and 'component' in stages(full)
    saved = service.call('dashboard_checkpoint', {**board, 'expectedRevision': 1})
    assert saved['ok'] and saved['doctor']['checks'] == full['checks']
    assert 'component' not in stages(saved['doctor'])
    assert any(stage.startswith('dataset:') for stage in stages(saved['doctor']))

    service.call('dashboard_patch', {**board, 'expectedRevision': 1,
                 'operations': [{'op': 'set_title', 'value': 'Updated'}]})
    with pytest.raises(DashboardError) as stale:
        service.call('dashboard_checkpoint', {**board, 'expectedRevision': 1})
    assert stale.value.code == 'REVISION_CONFLICT'
    assert service.call('dashboard_doctor', {**board, 'mode': 'quick'})['passed']
    updated = service.call('dashboard_checkpoint', {**board, 'expectedRevision': 2})
    assert updated['ok'] and 'component' in stages(updated['doctor'])


# @wu-test type=behavior | scope=渐进数据读取 | protects=定义读取提前携带完整数据或无法按组件加载
def test_local_document_has_no_component_results(tmp_path):
    from dashboard_runtime.demo import executive_document
    service=Service(tmp_path/'runtime', project_root=tmp_path/'project')
    service.call('dashboard_create', {'dashboardId':'demo','document':executive_document('demo')})
    result=service.call('dashboard_get', {'dashboardId':'demo','dataMode':'local'})
    assert result['document']['snapshot']['datasets']=={}
    assert result['document']['computed']['components']=={}
    assert result['document']['progressive']
    component=next(iter(result['document']['manifest']['components']))
    view=service.call('dashboard_view', {'dashboardId':'demo','componentIds':[component],'responseMode':'patch'})
    assert view['componentIds']==[component]


# @wu-test type=integration | scope=检查点保留 | protects=保存新版本时自动删除命名或未命名的历史检查点
def test_saving_does_not_prune_migrated_project_history(tmp_path):
    from dashboard_runtime.project_migration import migrate_project
    from dashboard_runtime.store import Store
    legacy=Store(tmp_path/'legacy')
    legacy.create('board','Legacy')
    assert not migrate_project(tmp_path/'legacy',tmp_path/'project',tmp_path/'cache',['board'])['applied']
    assert migrate_project(tmp_path/'legacy',tmp_path/'project',tmp_path/'cache',['board'],True)['applied']
    service=Service(tmp_path/'cache',project_root=tmp_path/'project')
    store=service.store
    store.config['history']['keepCheckpoints']=1
    store.checkpoint('board',1,'protected')
    for revision in range(1,4):
        store.mutate('board',revision,[{'op':'set_title','value':f'Title {revision}'}])
        store.checkpoint('board',revision+1)
    history = store.history('board')
    assert [item['revision'] for item in history] == [4, 3, 2, 1]
    assert history[-1]['name'] == 'protected'
    assert {path.name for path in (store.root / 'board/checkpoints').glob('*.json')} == {
        '1.json', '2.json', '3.json', '4.json',
    }
    assert legacy.revision('board')==1


# @wu-test type=integration | scope=dashboard_version_delete | protects=未经专用确认删除版本、删除当前发布后错误回退、复用已删除修订号
def test_delete_checkpoint_requires_confirmation_and_preserves_draft(tmp_path):
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    board = {'dashboardId': 'board'}
    checkpoints = service.store.root / 'board/checkpoints'
    service.call('dashboard_create', {**board, 'title': 'Original'})
    service.call('dashboard_version_publish', {**board, 'expectedRevision': 1, 'revision': 1})
    for revision in (1, 2):
        service.call('dashboard_patch', {**board, 'expectedRevision': revision,
                                      'operations': [{'op': 'set_title', 'value': f'Title {revision}'}]})
        service.store.checkpoint('board', revision + 1)
    current = {**board, 'expectedRevision': 3}
    for revision in (1, 3):
        with pytest.raises(DashboardError) as error:
            service.call('dashboard_version_delete', {**current, 'revision': revision})
        assert error.value.code == 'CONFIRMATION_REQUIRED'
    published = service.call('dashboard_version_delete_preview', {**current, 'revision': 1})
    assert published['clearsPublication'] and published['nextSavedRevision'] == 3
    with pytest.raises(DashboardError) as error:
        service.call('dashboard_version_delete', {**current, 'expectedRevision': 2, 'revision': 1,
                                                  'confirmation': published['token']})
    assert error.value.code == 'REVISION_CONFLICT'
    with pytest.raises(DashboardError) as error:
        service.call('dashboard_version_delete', {**current, 'revision': 3, 'confirmation': published['token']})
    assert error.value.code == 'CONFIRMATION_REQUIRED'
    assert [item['revision'] for item in service.store.history('board')] == [3, 2, 1]
    assert service.call('dashboard_version_delete', {**current, 'revision': 1, 'confirmation': published['token']})['deleted']
    assert not (checkpoints / '1.json').exists()
    status = service.call('dashboard_version_status', board)
    assert status['publishedRevision'] is None
    assert status['releases'] == []
    latest = service.call('dashboard_version_delete_preview', {**current, 'revision': 3})
    assert not latest['clearsPublication'] and latest['nextSavedRevision'] == 2
    assert service.call('dashboard_version_delete', {**current, 'revision': 3, 'confirmation': latest['token']})['deleted']
    assert [item['revision'] for item in service.store.history('board')] == [2]
    assert not (checkpoints / '3.json').exists()
    assert service.store.readable('board')['manifest']['title'] == 'Title 1'
    draft = service.store.get('board')
    assert (draft['revision'], draft['manifest']['title']) == (4, 'Title 2')


# @wu-test type=boundary | scope=dataset_storage_inventory | protects=跨项目盘点或将只读盘点注册成修改操作
def test_storage_inventory_routes_to_selected_cloud_project(tmp_path, monkeypatch):
    from dashboard_runtime import cloud_assets, cloud_database, cloud_project
    from dashboard_runtime.tool_contract import tool_annotations
    calls = []

    class Database:
        def __init__(self):
            self.url = 'https://example.invalid/rpc/charts_runtime'

        def call(self, action, project, **args):
            calls.append((self.url, action, project))
            if action == 'ensure':
                return {**args['config'], 'storageFormat': 'cos-v1'}
            return {'versions': []}

    class Assets:
        def __init__(self, project):
            self.project = project

        def call(self, action):
            calls.append(('assets', action, self.project))
            return {'storageFormat': 'cos-v1', 'datasets': [], 'documents': [{'revision': 1}]}

    monkeypatch.setenv('CHARTS_STORAGE_BACKEND', 'cloudbase')
    monkeypatch.setattr(cloud_database, 'CloudDatabase', Database)
    monkeypatch.setattr(cloud_project, 'CloudDatabase', Database)
    monkeypatch.setattr(cloud_assets, 'CloudAssets', Assets)
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'selected-project')
    assert service.call('dataset_storage_inventory', {}) == {
        'versions': [], 'cos': {'storageFormat': 'cos-v1', 'datasets': []},
    }
    assert calls == [
        ('https://example.invalid/rpc/charts_runtime', 'ensure', 'selected-project'),
        ('https://example.invalid/rpc/charts_data_inventory', 'inventory', 'selected-project'),
        ('assets', 'inventory', 'selected-project'),
    ]
    assert tool_annotations('dataset_storage_inventory')['readOnlyHint']


# @wu-test type=performance | scope=ProjectStore 镜像刷新 | protects=普通草稿编辑重写全部历史或批注、保存时重复生成不可变检查点
def test_design_edits_only_refresh_changed_mirrors(tmp_path, monkeypatch):
    from dashboard_runtime import project

    store = project.ProjectStore(tmp_path / 'project', tmp_path / 'runtime')
    store.create('board', 'Original')
    for revision in range(1, 8):
        store.mutate('board', revision, [{'op': 'set_title', 'value': f'Title {revision}'}])
        store.checkpoint('board', revision + 1)
    written = []
    original_write = project.write_json

    def record(path, value):
        written.append(path.relative_to(store.root / 'board').as_posix())
        original_write(path, value)

    monkeypatch.setattr(project, 'write_json', record)
    store.mutate('board', 8, [{'op': 'set_title', 'value': 'Latest'}])
    assert written == ['draft.json']
    assert json.loads((store.root / 'board/draft.json').read_text())['revision'] == 9
    written.clear()
    store.checkpoint('board', 9)
    assert written == ['history.json', 'checkpoints/9.json']
    assert len(json.loads((store.root / 'board/history.json').read_text())) == 9
    written.clear()
    store.label_checkpoint('board', 9, 1, 'Original')
    assert written == ['history.json']
    written.clear()
    store.checkpoint('board', 9)
    assert written == ['history.json']


# @wu-test type=integration | scope=批注事务与镜像 | protects=批注文件写入长期占用 SQLite 写锁或文件反映尚未提交的批注
def test_annotation_mirrors_follow_commit_without_blocking_database_writes(tmp_path, monkeypatch):
    from dashboard_runtime.project import ProjectStore

    store = ProjectStore(tmp_path / 'project', tmp_path / 'runtime')
    store.create('board', 'Original')
    original_files = store._annotation_files
    committed = []

    def check_commit(db, board):
        # A separate writer must be able to start even while the mirror is being
        # generated, and must already see the committed annotation.
        with closing(sqlite3.connect(store.path, timeout=0)) as probe, probe:
            probe.execute('BEGIN IMMEDIATE')
            committed.append(json.loads(probe.execute('SELECT payload FROM annotations WHERE board_id=?', (board,)).fetchone()[0]))
        original_files(db, board)

    monkeypatch.setattr(store, '_annotation_files', check_commit)
    saved = store.append_annotation('board', {
        'id': 'note', 'componentId': None, 'text': 'Review', 'createdAt': '2026-11-26',
    })
    assert committed == [[saved['annotation']]]
    assert store.revision('board') == 1 and store.display_revision('board') == 1
    notes = store.annotation_state('board')['annotations']
    updated = [{**notes[0], 'text': 'Updated review'}]
    store.update_annotations('board', 1, notes, updated)
    assert committed[-1] == updated
    assert json.loads((store.root / 'board/annotations.json').read_text()) == updated


# @wu-test type=boundary | scope=write_json 原子替换 | protects=并发报告或配置写入复用同名临时文件而丢失输出或产生半份 JSON
def test_atomic_json_writes_use_independent_temporary_files(tmp_path):
    from dashboard_runtime.project import write_json

    path = tmp_path / 'report.json'
    ready = Barrier(8, timeout=5)
    values = [{'id': value, 'payload': '结果' * 1000} for value in range(8)]

    def write(value):
        ready.wait()
        write_json(path, value)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, values))
    assert json.loads(path.read_text()) in values
    assert list(tmp_path.iterdir()) == [path]


# @wu-test type=boundary | scope=批注镜像失败重试 | protects=数据库提交后镜像失败，幂等重试不修复文件或重复增加批注事件
@pytest.mark.parametrize('operation', ['append', 'replace'])
def test_annotation_retry_repairs_failed_mirrors_without_another_event(tmp_path, monkeypatch, operation):
    from dashboard_runtime import project

    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.call('dashboard_create', {'dashboardId': 'board', 'title': 'Original'})
    note = {'id': 'note', 'componentId': None, 'text': 'Review', 'createdAt': '2026-11-26'}
    args = {'dashboardId': 'board', **({'append': note} if operation == 'append' else {
        'expectedRevision': 1, 'expectedAnnotations': [], 'annotations': [note],
    })}
    original_write = project.write_json
    failed = False

    def fail_history_once(path, value):
        nonlocal failed
        if path.name == 'annotation-history.json' and not failed:
            failed = True
            raise OSError('Mirror storage temporarily unavailable')
        original_write(path, value)

    monkeypatch.setattr(project, 'write_json', fail_history_once)
    with pytest.raises(OSError, match='temporarily unavailable'):
        service.call('dashboard_annotations_update', args)
    stored = service.store.annotation_state('board')['annotations']
    assert len(stored) == 1 and stored[0]['id'] == note['id']
    folder = service.store.root / 'board'
    assert json.loads((folder / 'annotation-history.json').read_text()) == []
    with service.store.connect() as db:
        assert db.execute('SELECT count(*) FROM annotation_events WHERE board_id=?', ('board',)).fetchone()[0] == 1

    if operation == 'replace':
        # Replacement keeps its compare-and-swap contract. After an uncertain
        # write, reread the saved list before issuing a no-op replacement.
        with pytest.raises(DashboardError) as conflict:
            service.call('dashboard_annotations_update', args)
        assert conflict.value.code == 'ANNOTATION_CONFLICT'
        args = {'dashboardId': 'board', 'expectedRevision': 1,
                'expectedAnnotations': stored, 'annotations': stored}
    service.call('dashboard_annotations_update', args)
    assert json.loads((folder / 'annotations.json').read_text()) == stored
    events = json.loads((folder / 'annotation-history.json').read_text())
    assert len(events) == 1 and json.loads(events[0]['payload']) == stored
    assert service.store.revision('board') == 1 and service.store.display_revision('board') == 1
