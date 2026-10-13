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
    assert all(c['kind'] != 'chart' for c in doc['manifest']['components'].values())
    if mode == 'dashboard':
        assert doc['manifest']['components']['trend']['config']['code'] == 't06'
        assert doc['manifest']['meta']['statusText'] == '月度经营复盘'
        assert '合成示例' not in doc['manifest']['title']
        assert doc['snapshot']['status'] == 'fixture'
        cards = ['total', 'load', 'passengers', 'goal']
        assert [doc['manifest']['components'][key]['config']['type'] for key in cards] == ['mc01', 'mc02', 'mc03', 'mc04']
        assert all(doc['manifest']['components'][key]['binding'] for key in cards + ['trend'])
        assert [(p['x'], p['w']) for p in doc['manifest']['layout']['desktop'][:4]] == [(0, 3), (3, 3), (6, 3), (9, 3)]
        assert {f['field'] for f in doc['manifest']['filters']} >= {'region', 'month'}
    else:
        assert doc['manifest']['components']['trend']['config']['code'] == 't01'
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
    with pytest.raises(DashboardError):
        generation_examples('../other')


def test_executive_binding_recomputes_data_after_combined_filters():
    import json
    from pathlib import Path
    import subprocess
    case = generation_examples('executive-dashboard')
    doc = apply_operations(new_document('fresh', 'Blank'), case['operations'])
    module = (Path(__file__).resolve().parents[2] / 'dashboard_runtime/web/bindings.mjs').as_uri()
    script = f"""import {{resolveOriginal}} from {json.dumps(module)};
import {{readFileSync}} from 'node:fs';
import assert from 'node:assert/strict';
const doc=JSON.parse(readFileSync(0,'utf8'));
doc.manifest.filters.find(f=>f.id==='region').values=['华东基地'];
doc.manifest.filters.find(f=>f.id==='period').values=['2026-08-01','2026-09-01'];
assert.deepEqual(resolveOriginal(doc,'trend').data.month.revenue,[102,96]);
assert.deepEqual(resolveOriginal(doc,'trend','quarter').data.quarter.revenue,[198]);
assert.equal(resolveOriginal(doc,'load').value,'82.5%');
assert.deepEqual(resolveOriginal(doc,'passengers').sparkData,[85,80]);
assert.equal(resolveOriginal(doc,'goal').percent,99);
doc.manifest.filters.find(f=>f.id==='search').values=['no match'];
assert.deepEqual(resolveOriginal(doc,'trend').data.month.revenue,[]);
"""
    result = subprocess.run(['node', '--input-type=module', '-e', script], input=json.dumps(doc), text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
