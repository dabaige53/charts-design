import { afterAll, beforeAll, test } from 'bun:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {nativeRuntime} from '../../bin/native-runtime.js';
import {aggregate,visibleRows,grouped,compatible,csv} from '../../runtime-ui/shared/engine.mjs';
let doc,directory;
beforeAll(()=>{
  directory=mkdtempSync(path.join(tmpdir(),'charts-engine-'));
  const {binary,env}=nativeRuntime();
  const call=(tool,args)=>JSON.parse(execFileSync(binary,['--project-root',path.join(directory,'project'),
    '--runtime-root',path.join(directory,'runtime'),'call',tool,'--json-file','-'],
    {env,input:JSON.stringify(args),encoding:'utf8'}));
  const rows=[
    {month:'2026-07',region:'East',revenue:80,passengers:72,seats:100},
    {month:'2026-07',region:'South',revenue:60,passengers:45,seats:50},
    {month:'2026-08',region:'East',revenue:102,passengers:85,seats:100},
    {month:'2026-08',region:'South',revenue:72,passengers:48,seats:50},
    {month:'2026-09',region:'East',revenue:96,passengers:80,seats:100},
    {month:'2026-09',region:'South',revenue:74,passengers:46,seats:50},
  ];
  call('dashboard_create',{dashboardId:'fixture',title:'Synthetic revenue and capacity'});
  call('dashboard_patch',{dashboardId:'fixture',expectedRevision:1,operations:[
    {op:'put_source',id:'fixture',value:{kind:'fixture',name:'Synthetic acceptance-test data'}},
    {op:'put_dataset',id:'sales',meta:{sourceId:'fixture',fields:Object.fromEntries(Object.keys(rows[0])
      .map(key=>[key,{type:['month','region'].includes(key)?'string':'number'}]))},rows},
    {op:'put_metric',id:'revenue',value:{datasetId:'sales',field:'revenue',aggregation:'sum',label:'Revenue',unit:'10k CNY',
      definition:'Revenue across the selected months and regions, summed from synthetic records.',status:'unverified'}},
    {op:'put_component',id:'total',value:{kind:'kpi',title:'Revenue',datasetId:'sales',measures:['revenue']}},
    {op:'put_component',id:'trend',value:{kind:'legacy',family:'chart',title:'Revenue by month',sourceId:'fixture',
      config:{code:'t01',unit:'10k CNY',data:{months:['2026-07','2026-08','2026-09'],rpk:[140,174,170]},
        presentation:{axisLabels:{x:'Month',y:'Revenue'},seriesLabels:['Revenue'],tooltipValueLabels:['Revenue'],
          units:['10k CNY'],tableHeaders:['Month','Revenue','Change']}},
      binding:{datasetId:'sales',categoryField:'month',categoryTarget:'months',measures:{rpk:'revenue'}}}},
    {op:'put_component',id:'details',value:{kind:'table',title:'Synthetic rows',datasetId:'sales'}},
    {op:'set_filters',value:[{id:'region',label:'Region',field:'region',op:'in',values:[],componentIds:['total','trend','details']}]},
    {op:'set_status',value:'fixture'},
  ]});
  doc=call('dashboard_get',{dashboardId:'fixture'}).document;
  const preview=call('dataset_preview',{dashboardId:'fixture',datasetId:'sales',expectedRevision:doc.revision,limit:100});
  assert.equal(preview.totalRows,rows.length);
  doc.snapshot.datasets.sales=preview.rows;
  // The shared grouping helpers consume the category role as x.
  doc.manifest.components.trend.x=doc.manifest.components.trend.binding.categoryField;
},30000);
afterAll(()=>{if(directory)rmSync(directory,{recursive:true,force:true});});
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
  assert.equal(result,'\ufeff"label","value"\r\n"\'=HYPERLINK(""x"")","-3"');
});
// @wu-test type=behavior | scope=search filters | protects=搜索影响未绑定组件
test('declared search recomputes only its explicit consumers',()=>{
  const d=structuredClone(doc);d.manifest.filters=[{id:'search',op:'contains',field:'region',values:['EA'],componentIds:['total','trend']}];
  assert.equal(visibleRows(d,'total').length,3);
  assert.equal(aggregate(visibleRows(d,'total'),d.manifest.metrics.revenue),278);
  assert.equal(visibleRows(d,'details').length,6);
  d.manifest.filters[0].values=['no match'];assert.equal(visibleRows(d,'total').length,0);
});
