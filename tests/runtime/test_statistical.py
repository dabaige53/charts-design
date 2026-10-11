import base64
import copy
import pytest
from dashboard_runtime.model import DashboardError, new_document, apply_operations, validate
from dashboard_runtime.statistical import render_statistical, statistical_artifacts, _render
from dashboard_runtime.service import Service


def statistical_document(kind='histogram'):
    plot = {'type': kind, 'x': 'group' if kind == 'boxplot' else 'x'}
    if kind != 'histogram': plot['y'] = 'value'
    return apply_operations(new_document('statistics', 'Statistical example'), [
        {'op':'put_source','id':'synthetic','value':{'kind':'fixture','name':'Explicit synthetic observations'}},
        {'op':'put_dataset','id':'observations','meta':{'sourceId':'synthetic','fields':{'x':{'type':'number'},'value':{'type':'number'},'group':{'type':'string'}}},'rows':[{'x':i,'value':2*i+(i%3),'group':'A' if i%2 else 'B'} for i in range(1,25)] + [{'x':None,'value':None,'group':'A'}]},
        {'op':'put_component','id':'distribution','value':{'kind':'statistical','title':'Synthetic observations','datasetId':'observations','plot':plot,'analysis':{'definition':'One row per synthetic observation.','unit':'units'}}},
        {'op':'set_view_mode','value':'report'},
        {'op':'set_report_markdown','value':'# Statistical example\n\n```chart\n{"componentId":"distribution","caption":"Explicit synthetic data"}\n```'},
        {'op':'set_status','value':'fixture'},
    ])


@pytest.mark.parametrize('kind',['histogram','boxplot','regression'])
def test_render_formats(kind):
    pytest.importorskip('seaborn')
    doc=statistical_document(kind)
    svg=render_statistical(doc,'distribution')
    assert b'<svg' in base64.b64decode(svg['dataUri'].split(',')[1])
    assert svg == render_statistical(doc,'distribution')
    assert svg['provenance']['rowsUsed']==24 and svg['provenance']['rowsDropped']==1
    assert 'not certified' in svg['caption']
    png=render_statistical(doc,'distribution','png')
    assert base64.b64decode(png['dataUri'].split(',')[1]).startswith(b'\x89PNG\r\n\x1a\n')


@pytest.mark.parametrize('change',[
    {'plot':{'type':'histogram','x':'x','code':'print(1)'}},
    {'plot':{'type':'histogram','x':'x','bins':True}},
    {'plot':{'type':'histogram','x':'x','bins':101}},
    {'plot':{'type':'regression','x':'group','y':'value'}},
    {'plot':{'type':'boxplot','x':'x','y':'value'}},
    {'plot':{'type':'histogram','x':'missing'}},
    {'analysis':{'definition':'','unit':'units'}},
    {'image':'https://example.com/a.svg'},
])
def test_invalid_spec(change):
    doc=statistical_document()
    doc['manifest']['components']['distribution'].update(change)
    with pytest.raises(DashboardError): validate(doc)


def test_no_filters_and_degenerate_regression():
    doc=statistical_document()
    with pytest.raises(DashboardError,match='static raw-observation'):
        apply_operations(doc,[{'op':'set_filters','value':[{'id':'group-filter','field':'group','op':'in','values':['A'],'componentIds':['distribution']}]}])
    doc=statistical_document('regression')
    for row in doc['snapshot']['datasets']['observations']:row['x']=1
    with pytest.raises(DashboardError,match='distinct x'):validate(doc)


def test_revision_and_source_refresh(tmp_path):
    pytest.importorskip('seaborn')
    service=Service(tmp_path)
    before=service.call('dashboard_create',{'dashboardId':'statistics','document':statistical_document()})
    c=copy.deepcopy(before['document']['manifest']['components']['distribution']);c['plot']['bins']=4
    after=service.call('dashboard_patch',{'dashboardId':'statistics','expectedRevision':1,'operations':[{'op':'put_component','id':'distribution','value':c}]})
    assert before['statisticalArtifacts']['distribution']['dataUri']!=after['statisticalArtifacts']['distribution']['dataUri']
    assert 'statisticalArtifacts' not in service.store.get('statistics')
    assert service.call('statistical_render',{'dashboardId':'statistics','componentId':'distribution','format':'png'})['mimeType']=='image/png'
    from dashboard_runtime.assets import export_document
    assert 'statisticalArtifacts' in export_document(after['document'])


def test_missing_dependency_is_visible(monkeypatch):
    import builtins
    original=builtins.__import__
    def without_seaborn(name,*args,**kwargs):
        if name=='seaborn':raise ImportError('optional missing')
        return original(name,*args,**kwargs)
    _render.cache_clear()
    monkeypatch.setattr(builtins,'__import__',without_seaborn)
    assert statistical_artifacts(statistical_document())['distribution']['code']=='SEABORN_NOT_INSTALLED'


def test_row_and_category_limits():
    doc=statistical_document()
    doc['snapshot']['datasets']['observations']=[{'x':1,'value':2,'group':'A'}]*5001
    with pytest.raises(DashboardError,match='5000'):validate(doc)
    doc=statistical_document('boxplot')
    doc['snapshot']['datasets']['observations']=[{'x':i,'value':i,'group':str(i)} for i in range(21)]
    with pytest.raises(DashboardError,match='20 categories'):validate(doc)


def test_declaration_schema_is_explicit():
    from dashboard_runtime.declarations import declaration_contract
    entry=declaration_contract()['statistical']
    assert entry['componentSchema']['additionalProperties'] is False
    assert len(entry['componentSchema']['properties']['plot']['oneOf'])==3


def test_large_offset_regression_is_stable():
    import numpy as np
    from dashboard_runtime.statistical import regression_line
    x,y=regression_line(100000000+np.arange(5),np.arange(5))
    np.testing.assert_allclose(y,[0,4],atol=1e-10)
    np.testing.assert_allclose(x,[100000000,100000004])


def test_render_projects_only_selected_fields(monkeypatch):
    import json
    import dashboard_runtime.statistical as statistical
    doc=statistical_document()
    doc['manifest']['datasets']['observations']['fields']['irrelevant']={'type':'string'}
    doc['snapshot']['datasets']['observations'][0]['irrelevant']='unused'
    seen={}
    def capture(raw,format):
        seen.update(json.loads(raw));return 'eA==',{}
    monkeypatch.setattr(statistical,'_render',capture)
    render_statistical(doc,'distribution')
    assert set(seen['fields'])=={'x'}
    assert all(set(row)=={'x'} for row in seen['rows'])


@pytest.mark.parametrize('offset,slope,intercept',[(0,-2,3),(-1e11,2,-7),(1e11,0,4)])
def test_regression_negative_and_constant_cases(offset,slope,intercept):
    import numpy as np
    from dashboard_runtime.statistical import regression_line
    v=np.arange(5,dtype=float)
    _,y=regression_line(offset+v,intercept+slope*v)
    np.testing.assert_allclose(y,[intercept,intercept+slope*4],atol=1e-9)


def test_regression_missing_and_rank_requirements():
    doc=statistical_document('regression')
    doc['snapshot']['datasets']['observations']=[{'x':1,'value':None,'group':'A'}]
    with pytest.raises(DashboardError,match='complete observation'):validate(doc)
    doc['snapshot']['datasets']['observations']=[{'x':1,'value':2,'group':'A'},{'x':2,'value':4,'group':'A'}]
    with pytest.raises(DashboardError,match='at least 3'):validate(doc)


def test_regression_representable_offset_spacing():
    import numpy as np
    from dashboard_runtime.statistical import regression_line
    x=9e11+np.arange(4)*np.spacing(9e11)
    _,y=regression_line(x,np.arange(4))
    np.testing.assert_allclose(y,[0,3],atol=1e-10)


def test_regression_both_axes_large_offsets():
    import numpy as np
    from dashboard_runtime.statistical import regression_line
    x=9e11+np.arange(4)*np.spacing(9e11)
    y=-9e11+np.arange(4)*np.spacing(9e11)
    _,pred=regression_line(x,y)
    np.testing.assert_array_equal(pred,[y.min(),y.max()])
