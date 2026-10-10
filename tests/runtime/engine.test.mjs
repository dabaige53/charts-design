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
  for(const type of ['bar','line','area','pie','funnel']){
    const d=structuredClone(doc);d.manifest.components.trend.chartType=type;
    assert.ok(optionFor(d,'trend').series.length);
    assert.deepEqual(d.snapshot,doc.snapshot);
  }
});
test('shape compatibility blocks missing roles',()=>{
  assert.ok(compatible(doc,doc.manifest.components.trend,'scatter'));
  assert.ok(compatible(doc,doc.manifest.components.trend,'heatmap'));
  assert.ok(compatible(doc,doc.manifest.components.trend,'waterfall'));
});
test('null measurements are missing, never coerced to zero',()=>{
  assert.equal(aggregate([{v:null}],{aggregation:'sum',field:'v'}),null);
});
test('CSV quotes values and neutralizes formula injection',()=>{
  assert.ok(csv([{label:'=HYPERLINK("x")',value:-3}]).includes("'=HYPERLINK"));
});
