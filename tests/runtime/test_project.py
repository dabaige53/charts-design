from dashboard_runtime.service import Service
from dashboard_runtime.model import DashboardError
import pytest


# @wu-test type=integration | scope=项目草稿检查点 | protects=编辑恢复删除运行缓存后丢批注
def test_drafts_checkpoints_notes_and_runtime_removal(tmp_path):
    project, runtime = tmp_path/'project', tmp_path/'runtime'
    service = Service(runtime, project_root=project)
    service.call('dashboard_create', {'dashboardId':'board','title':'Original'})
    batch = service.call('dashboard_edit_begin', {'dashboardId':'board','expectedRevision':1})
    note={'id':'note','componentId':None,'text':'Keep me','createdAt':'2026-10-28'}
    service.call('dashboard_patch', {'dashboardId':'board','expectedRevision':1,
                                    'operations':[{'op':'set_title','value':'Updated'}]})
    service.call('dashboard_patch', {'dashboardId':'board','expectedRevision':2,'expectedAnnotations':[],
                                    'operations':[{'op':'set_annotations','value':[note]}]})
    assert len(service.store.history('board')) == 1
    assert service.call('runtime_info',{'dashboardId':'board'})['dashboardRevision']==1
    assert service.call('dashboard_refresh',{'dashboardId':'board'})['document']['manifest']['title']=='Original'
    service.call('dashboard_patch', {'dashboardId':'board','expectedRevision':2,'operations':[{'op':'set_title','value':'Updated'}]})
    assert service.store.revision('board') == 2
    done=service.call('dashboard_edit_finish', {'dashboardId':'board','expectedRevision':2,'batchId':batch['batch_id'],'name':'Approved'})
    assert done['ok']
    assert done['nextAction'] == 'dashboard_preview'
    assert done['displayPolicy'] == 'saved-dashboard-ui'
    assert len(service.store.history('board')) == 2
    restored=service.call('dashboard_restore', {'dashboardId':'board','expectedRevision':2,'revision':1})['document']
    assert restored['manifest']['title']=='Original'
    assert restored['manifest']['annotations'][0]['text']=='Keep me'
    import shutil
    shutil.rmtree(runtime)
    reopened=Service(runtime, project_root=project)
    assert reopened.store.get('board')['manifest']['annotations'][0]['text']=='Keep me'
    assert (project/'dashboards/board/draft.json').exists()
    assert not (runtime/'data.sqlite3').exists()


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


# @wu-test type=integration | scope=检查点保留 | protects=旧保留数量配置绕过明确删除确认而清理历史
def test_checkpoints_remain_until_explicit_deletion(tmp_path):
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
    assert {item['revision'] for item in store.history('board')}=={1,2,3,4}
    assert legacy.revision('board')==1


# @wu-test type=integration | scope=dashboard_version_delete | protects=未确认或过期确认删除版本及删除发布版本时损坏草稿
def test_delete_checkpoint_requires_current_confirmation_and_preserves_draft(tmp_path):
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.call('dashboard_create', {'dashboardId': 'board', 'title': 'Original'})
    service.call('dashboard_version_publish', {'dashboardId': 'board', 'expectedRevision': 1, 'revision': 1})
    for revision in (1, 2):
        service.call('dashboard_patch', {'dashboardId': 'board', 'expectedRevision': revision,
                                      'operations': [{'op': 'set_title', 'value': f'Title {revision}'}]})
        service.store.checkpoint('board', revision + 1)
    for revision in (1, 3):
        with pytest.raises(DashboardError) as error:
            service.call('dashboard_version_delete', {'dashboardId': 'board', 'expectedRevision': 3, 'revision': revision})
        assert error.value.code == 'CONFIRMATION_REQUIRED'
    with pytest.raises(DashboardError) as error:
        service.call('dashboard_version_delete', {'dashboardId': 'board', 'expectedRevision': 2, 'revision': 2})
    assert error.value.code == 'REVISION_CONFLICT'
    plan = service.call('dashboard_version_delete_preview', {'dashboardId': 'board', 'expectedRevision': 3, 'revision': 2})
    assert service.call('dashboard_version_delete', {'dashboardId': 'board', 'expectedRevision': 3, 'revision': 2,
                                                    'confirmation': plan['token']})['deleted']
    assert {item['revision'] for item in service.store.history('board')} == {1, 3}
    assert not (tmp_path / 'project/dashboards/board/checkpoints/2.json').exists()
    assert service.call('dashboard_version_status', {'dashboardId': 'board'})['publishedRevision'] == 1
    stale = service.call('dashboard_version_delete_preview', {'dashboardId': 'board', 'expectedRevision': 3, 'revision': 1})
    service.store.label_checkpoint('board', 3, 3, 'Keep current')
    with pytest.raises(DashboardError) as error:
        service.call('dashboard_version_delete', {'dashboardId': 'board', 'expectedRevision': 3, 'revision': 1,
                                                 'confirmation': stale['token']})
    assert error.value.code == 'PLAN_CHANGED'
    for revision in (1, 3):
        plan = service.call('dashboard_version_delete_preview', {'dashboardId': 'board', 'expectedRevision': 3, 'revision': revision})
        assert service.call('dashboard_version_delete', {'dashboardId': 'board', 'expectedRevision': 3, 'revision': revision,
                                                        'confirmation': plan['token']})['deleted']
    state = service.call('dashboard_version_status', {'dashboardId': 'board'})
    assert state['publishedRevision'] is None and state['savedRevision'] is None
    draft = service.store.get('board')
    assert draft['revision'] == 4 and draft['manifest']['title'] == 'Title 2'
    with pytest.raises(DashboardError) as error:
        service.store.readable('board')
    assert error.value.code == 'NO_SAVED_VERSION'


# @wu-test type=boundary | scope=dataset_storage_inventory | protects=跨项目盘点或将只读盘点注册成修改操作
def test_storage_inventory_routes_to_selected_cloud_project(tmp_path, monkeypatch):
    from dashboard_runtime import cloud_database
    from dashboard_runtime.tool_contract import tool_annotations
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.store.database = object()
    calls = []

    class Database:
        def __init__(self):
            self.url = 'https://example.invalid/rpc/charts_runtime'

        def call(self, action, project):
            calls.append((self.url, action, project))
            return {'versions': []}

    monkeypatch.setattr(cloud_database, 'CloudDatabase', Database)
    class Assets:
        def call(self, action):
            assert action == 'inventory'
            return {'objects': [], 'documents': [{'private': 'internal reference'}]}

    service.store.assets = Assets()
    service.store.project = 'selected-project'
    assert service.call('dataset_storage_inventory', {}) == {'versions': [], 'cos': {'objects': []}}
    assert calls == [('https://example.invalid/rpc/charts_data_inventory', 'inventory', 'selected-project')]
    assert tool_annotations('dataset_storage_inventory')['readOnlyHint']


# @wu-test type=regression | scope=ProjectStore/CloudProjectStore annotations | protects=防止 audit-2 复发：省略或过期批注比较值覆盖并发保存内容
@pytest.mark.parametrize('cloud', [False, True])
def test_annotation_replacement_requires_the_read_list(tmp_path, cloud):
    from dashboard_runtime.project import ProjectStore
    from dashboard_runtime.cloud_project import CloudProjectStore
    local = ProjectStore(tmp_path / 'project', tmp_path / 'runtime')
    local.create('board', 'Original')
    note = {'id': 'new', 'componentId': None, 'text': 'Keep concurrent comment', 'createdAt': '2026-11-12'}
    local.mutate('board', 1, [{'op': 'set_annotations', 'value': [note]}], expected_annotations=[])
    store = local
    if cloud:
        # Exercise the cloud store's input boundary without a remote service.
        store = object.__new__(CloudProjectStore)
        store.get = local.get
    for expected in (None, []):
        with pytest.raises(DashboardError) as error:
            store.mutate('board', 1, [{'op': 'set_annotations', 'value': []}], expected_annotations=expected)
        assert error.value.code == 'ANNOTATION_CONFLICT'
    assert local.revision('board') == 1
    assert local.get('board')['manifest']['annotations'][0]['text'] == note['text']
    notes = local.get('board')['manifest']['annotations']
    local.mutate('board', 1, [{'op': 'set_annotations', 'value': []}], expected_annotations=notes)
    assert local.get('board')['manifest']['annotations'] == []


# @wu-test type=regression | scope=ProjectStore mirrors | protects=防止 audit-3 复发：并发保存的JSON镜像碰撞或旧版本覆盖新版本
def test_mirrors_serialize_with_concurrent_project_writes(tmp_path, monkeypatch):
    import json
    import sqlite3
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from dashboard_runtime import project
    store = project.ProjectStore(tmp_path / 'project', tmp_path / 'runtime')
    store.create('board', 'Original')
    entered, release, second_started = threading.Event(), threading.Event(), threading.Event()
    original = project.write_json

    def hold_first(path, value):
        if path.name == 'draft.json' and not entered.is_set():
            entered.set()
            assert release.wait(5)
        original(path, value)

    def change():
        second_started.set()
        return store.mutate('board', 1, [{'op': 'set_title', 'value': 'Latest'}])

    monkeypatch.setattr(project, 'write_json', hold_first)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(store._files, 'board')
        assert entered.wait(5)
        try:
            with sqlite3.connect(store.path, timeout=0) as competing:
                with pytest.raises(sqlite3.OperationalError, match='locked'):
                    competing.execute("UPDATE boards SET revision=99 WHERE id='board'")
        except BaseException:
            release.set()
            raise
        second = pool.submit(change)
        assert second_started.wait(5)
        release.set()
        first.result()
        assert second.result()['revision'] == 2
    folder = store.root / 'board'
    assert json.loads((folder / 'draft.json').read_text())['manifest']['title'] == 'Latest'
    assert not list(folder.glob('*.tmp'))
