import json
import pytest
from dashboard_runtime.service import Service
from dashboard_runtime.model import new_document


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


def test_preview_has_no_component_results(tmp_path):
    from dashboard_runtime.demo import executive_document
    service=Service(tmp_path/'runtime', project_root=tmp_path/'project')
    service.call('dashboard_create', {'dashboardId':'demo','document':executive_document('demo')})
    result=service.call('dashboard_preview', {'dashboardId':'demo'})
    assert result['document']['snapshot']['datasets']=={}
    assert result['document']['computed']['components']=={}
    assert result['document']['progressive']
    component=next(iter(result['document']['manifest']['components']))
    view=service.call('dashboard_view', {'dashboardId':'demo','componentIds':[component],'responseMode':'patch'})
    assert view['componentIds']==[component]


def test_checkpoint_retention_protects_named_and_migration(tmp_path):
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
    assert {item['revision'] for item in store.history('board')}=={1,4}
    assert legacy.revision('board')==1
