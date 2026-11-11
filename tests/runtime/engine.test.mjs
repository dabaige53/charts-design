import { test } from 'bun:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const pythonEntry = fileURLToPath(new URL('../../bin/python-runtime.js', import.meta.url));
import {aggregate,visibleRows,grouped,compatible,csv} from '../../dashboard_runtime/web/engine.mjs';
const doc=JSON.parse(execFileSync(process.execPath,[pythonEntry,'-c','import json;from dashboard_runtime.demo import document;print(json.dumps(document()))'],{encoding:'utf8'}));
// @wu-test type=behavior | scope=aggregate ratio | protects=比例按百分比平均或零分母产生错误值
test('weighted ratio is recomputed, not mean of percentages',()=>{
  assert.equal(aggregate([{p:90,s:100},{p:1,s:10}],{aggregation:'ratio',numerator:'p',denominator:'s'}),91/110);
  assert.equal(aggregate([{p:1,s:0}],{aggregation:'ratio',numerator:'p',denominator:'s'}),null);
});
// @wu-test type=integration | scope=filter aggregation | protects=KPI与图表使用不同筛选范围
test('filters feed KPIs and charts from the same reviewed rows',()=>{
  const d=structuredClone(doc);d.manifest.filters[0].values=['East'];
  assert.equal(visibleRows(d,'total').length,3);
  assert.equal(aggregate(visibleRows(d,'total'),d.manifest.metrics.revenue),278);
  assert.equal(grouped(d,'trend').reduce((s,r)=>s+r.values.revenue,0),278);
});
// @wu-test type=boundary | scope=chart compatibility | protects=字段角色不足时启用不兼容图表
test('shape compatibility blocks missing roles',()=>{
  const trend=doc.manifest.components.trend;
  assert.match(compatible(doc,trend,'scatter'),/numeric X field/);
  assert.match(compatible(doc,trend,'heatmap'),/second categorical field/);
  assert.match(compatible(doc,trend,'waterfall'),/additive delta metric/);
  assert.equal(compatible(doc,{...trend,x:'revenue'},'scatter'),null);
  assert.equal(compatible(doc,{...trend,series:'region'},'heatmap'),null);
  const delta=structuredClone(doc);delta.manifest.metrics.revenue.semantic='delta';
  assert.equal(compatible(delta,delta.manifest.components.trend,'waterfall'),null);
});
// @wu-test type=boundary | scope=CSV export | protects=公式注入及引号破坏CSV
test('CSV quotes values and neutralizes formula injection',()=>{
  const result=csv([{label:'=HYPERLINK("x")',value:-3}]);
  const parsed=JSON.parse(execFileSync(process.execPath,[pythonEntry,'-c',
    'import csv,io,json,sys; print(json.dumps(list(csv.reader(io.StringIO(sys.stdin.read().lstrip(chr(0xfeff)), newline="")))))'
  ],{input:result,encoding:'utf8'}));
  assert.deepEqual(parsed,[['label','value'],['\'=HYPERLINK("x")','-3']]);
});
// @wu-test type=behavior | scope=search filters | protects=搜索影响未绑定组件
test('declared search recomputes only its explicit consumers',()=>{
  const d=structuredClone(doc);d.manifest.filters=[{id:'search',op:'contains',field:'region',values:['EA'],componentIds:['total','trend']}];
  assert.equal(visibleRows(d,'total').length,3);
  assert.equal(aggregate(visibleRows(d,'total'),d.manifest.metrics.revenue),278);
  assert.equal(visibleRows(d,'details').length,6);
  d.manifest.filters[0].values=['no match'];assert.equal(visibleRows(d,'total').length,0);
});
