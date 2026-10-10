import copy
import importlib.util
from pathlib import Path
import pytest
from dashboard_runtime.demo import document
from dashboard_runtime.model import apply_operations,DashboardError
spec=importlib.util.spec_from_file_location('fixture',Path(__file__).with_name('fidelity_fixture.py'));fx=importlib.util.module_from_spec(spec);spec.loader.exec_module(fx)

def component():
    c=copy.deepcopy(fx.document()['manifest']['components']['c01'])
    c['binding']={'datasetId':'sales','categoryField':'region','categoryTarget':'categories','measures':{'values':'revenue'}}
    return c

def test_binding_roundtrip_preserves_original_config():
    doc=document();c=component();ds=doc['manifest']['metrics']['revenue']['datasetId'];c['binding']['datasetId']=ds
    actual=apply_operations(doc,[{'op':'put_component','id':'bound','value':c}])
    assert actual['manifest']['components']['bound']['config']==c['config']
    assert actual['manifest']['components']['bound']['datasetId']==ds
    f=copy.deepcopy(actual['manifest']['filters']);f[0]['componentIds'].append('bound')
    assert apply_operations(actual,[{'op':'set_filters','value':f}])['manifest']['filters']==f

@pytest.mark.parametrize('change',[{'datasetId':'missing'},{'categoryField':'missing'},{'categoryTarget':'__proto__'},{'measures':{}},{'measures':{'values':'missing'}},{'scale':{'values':-1}}])
def test_incomplete_or_unsafe_bindings_fail(change):
    doc=document();c=component();c['binding']['datasetId']=doc['manifest']['metrics']['revenue']['datasetId'];c['binding'].update(change)
    with pytest.raises(DashboardError):apply_operations(doc,[{'op':'put_component','id':'bound','value':c}])
