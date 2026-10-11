import pytest
from dashboard_runtime.generation import generation_examples
from dashboard_runtime.model import DashboardError, new_document, apply_operations, validate
from dashboard_runtime.service import Service, READ_ONLY

@pytest.mark.parametrize('case_id,mode',[('executive-dashboard','dashboard'),('academic-report','report')])
def test_case_generates_from_blank(case_id,mode):
    case=generation_examples(case_id)
    doc=apply_operations(new_document('fresh','Blank'),case['operations'])
    assert validate(doc)
    assert doc['manifest']['viewMode']==mode
    assert doc['snapshot']['status']=='fixture'
    assert doc['manifest']['components']['trend']['chartType']=='line'
    if mode=='report':
        assert doc['manifest']['report']['markdown']==case['markdown']
        assert '```chart' in case['markdown']
    case['operations'].clear()
    assert generation_examples(case_id)['operations']

def test_case_discovery_read_only(tmp_path):
    service=Service(tmp_path)
    assert len(service.call('generation_examples',{})['cases'])==2
    assert service.call('dashboard_list',{})=={'dashboards':[]}
    assert 'generation_examples' in READ_ONLY
    with pytest.raises(DashboardError):generation_examples('../other')
