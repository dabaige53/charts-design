import pytest
from dashboard_runtime.generation import generation_examples
from dashboard_runtime.model import DashboardError, new_document, apply_operations, validate
from dashboard_runtime.service import Service, READ_ONLY

# @wu-test type=integration | scope=生成案例 | protects=案例无法从空文档生成看板报告
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

# @wu-test type=boundary | scope=案例发现 | protects=读取案例创建看板或接受路径穿越
def test_case_discovery_read_only(tmp_path):
    service=Service(tmp_path)
    cases=service.call('generation_examples',{})['cases']
    assert [case['id'] for case in cases]==['executive-dashboard','operations-scorecard','academic-report']
    assert service.call('dashboard_list',{})=={'dashboards':[]}
    assert 'generation_examples' in READ_ONLY
    with pytest.raises(DashboardError):
        generation_examples('../other')


# @wu-test type=integration | scope=示例绑定 | protects=多筛选下图表KPI未重算
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


# @wu-test type=integration | scope=运营案例 | protects=运营案例与高管案例雷同或筛选后指标未重算
def test_operations_case_contrasts_the_executive_case_and_recomputes(tmp_path):
    executive = apply_operations(new_document('a', 'A'), generation_examples('executive-dashboard')['operations'])
    case = generation_examples('operations-scorecard')
    assert any(op['op'] == 'apply_layout_template' for op in case['operations'])
    assert not any(op['op'] == 'set_layout' for op in case['operations'])
    doc = apply_operations(new_document('fresh', 'Blank'), case['operations'])
    m = doc['manifest']
    assert m['layoutTemplate']['id'] == 'scorecard'
    kinds = lambda d, family: {c['config'].get('type') or c['config'].get('code') for c in d['manifest']['components'].values() if c.get('family') == family}
    assert not kinds(doc, 'kpi') & kinds(executive, 'kpi')
    assert not kinds(doc, 'chart') & kinds(executive, 'chart')
    assert all(c.get('binding') for c in m['components'].values() if c['kind'] == 'legacy')
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.call('dashboard_create', {'dashboardId': 'ops', 'document': doc})
    assert service.call('dashboard_doctor', {'dashboardId': 'ops', 'mode': 'full'})['passed']
    filters = [{**f, 'values': ['华南基地']} if f['id'] == 'region' else f for f in m['filters']]
    computed = service.call('dashboard_view', {'dashboardId': 'ops', 'dataMode': 'local', 'filters': filters})['document']['computed']['components']
    assert (computed['budget-bullet']['actual'], computed['budget-bullet']['target']) == (206, 225)
    assert computed['period-compare']['priorValue'] == 165
    assert computed['region-rank']['data']['categories'] == ['华南基地']
