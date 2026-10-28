import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {aggregate,visibleRows,grouped,optionFor,compatible,csv} from '../../dashboard_runtime/web/engine.mjs';
const doc=JSON.parse(execFileSync('python3',['-c','import json;from dashboard_runtime.demo import document;print(json.dumps(document()))'],{encoding:'utf8'}));
test('weighted ratio is recomputed, not mean of percentages',()=>{
  assert.equal(aggregate([{p:90,s:100},{p:1,s:10}],{aggregation:'ratio',numerator:'p',denominator:'s'}),91/110);
  assert.equal(aggregate([{p:1,s:0}],{aggregation:'ratio',numerator:'p',denominator:'s'}),null);
});
test('filters feed KPIs and charts from the same reviewed rows',()=>{
  const d=structuredClone(doc);d.manifest.filters[0].values=['East'];
  assert.equal(visibleRows(d,'total').length,3);
  assert.equal(aggregate(visibleRows(d,'total'),d.manifest.metrics.revenue),278);
  assert.equal(grouped(d,'trend').reduce((s,r)=>s+r.values.revenue,0),278);
});
test('native chart type switching preserves source snapshot',()=>{
  for(const [type,seriesType] of Object.entries({bar:'bar',line:'line',area:'line',pie:'pie',funnel:'funnel'})){
    const d=structuredClone(doc);d.manifest.components.trend.chartType=type;
    const series=optionFor(d,'trend').series;
    assert.deepEqual([...new Set(series.map(item=>item.type))],[seriesType]);
    if(type==='area')assert.ok(series.every(item=>item.areaStyle));
    assert.deepEqual(d.snapshot,doc.snapshot);
  }
});
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
test('null measurements are missing, never coerced to zero',()=>{
  assert.equal(aggregate([{v:null}],{aggregation:'sum',field:'v'}),null);
});
test('CSV quotes values and neutralizes formula injection',()=>{
  const result=csv([{label:'=HYPERLINK("x")',value:-3}]);
  const parsed=JSON.parse(execFileSync('python3',['-c',
    'import csv,io,json,sys; print(json.dumps(list(csv.reader(io.StringIO(sys.stdin.read().lstrip(chr(0xfeff)), newline="")))))'
  ],{input:result,encoding:'utf8'}));
  assert.deepEqual(parsed,[['label','value'],['\'=HYPERLINK("x")','-3']]);
});
test('declared search recomputes only its explicit consumers',()=>{
  const d=structuredClone(doc);d.manifest.filters=[{id:'search',op:'contains',field:'region',values:['EA'],componentIds:['total','trend']}];
  assert.equal(visibleRows(d,'total').length,3);
  assert.equal(aggregate(visibleRows(d,'total'),d.manifest.metrics.revenue),278);
  assert.equal(visibleRows(d,'details').length,6);
  d.manifest.filters[0].values=['no match'];assert.equal(visibleRows(d,'total').length,0);
});
