import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveOriginal} from '../../dashboard_runtime/web/bindings.mjs';
import {formatComparison} from '../../dashboard_runtime/web/engine.mjs';
import {linkageValue, linkagePoint} from '../../dashboard_runtime/web/linkage.mjs';
const source={
 manifest:{components:{bar:{kind:'legacy',family:'chart',datasetId:'ds',config:{code:'c01',data:{categories:['old'],values:[999]},presentation:{}},binding:{datasetId:'ds',categoryField:'region',categoryTarget:'categories',measures:{values:'revenue'}}}},metrics:{revenue:{aggregation:'sum',field:'revenue'},ratio:{aggregation:'ratio',numerator:'p',denominator:'s',format:'percent'}},filters:[]},
 snapshot:{datasets:{ds:[{region:'East',date:'2026-01-01',revenue:100,p:90,s:100},{region:'East',date:'2026-02-01',revenue:20,p:1,s:10},{region:'West',date:'2026-02-01',revenue:35,p:7,s:10}]}}};
test('original bars and table use the same explicit filter without mutating the source',()=>{
 const d=structuredClone(source);d.manifest.filters=[{componentIds:['bar'],field:'region',op:'in',values:['East']}];
 assert.deepEqual(resolveOriginal(d,'bar').data,{categories:['East'],values:[120]});assert.equal(d.manifest.components.bar.config.data.values[0],999);
});
test('original KPI ratio recomputes numerator/denominator',()=>{
 const d=structuredClone(source);d.manifest.components.kpi={kind:'legacy',family:'kpi',datasetId:'ds',config:{type:'mc01',value:'old',yoy:'+123%'},binding:{datasetId:'ds',measures:{value:'ratio'}}};
 d.manifest.filters=[{componentIds:['kpi'],field:'region',op:'in',values:['East']}];
 const k=resolveOriginal(d,'kpi');assert.equal(k.value,'82.73%');assert.equal(k.yoy,'\u2014');
});
test('quarterly dual-axis ratio is not an average of monthly percentages',()=>{
 const d=structuredClone(source);d.manifest.components.dual={kind:'legacy',family:'chart',datasetId:'ds',config:{code:'t06',data:{}},binding:{datasetId:'ds',categoryField:'date',categoryTarget:'categories',timeGrain:true,measures:{revenue:'revenue',yieldGrowth:'ratio'},scale:{yieldGrowth:100}}};
 const r=resolveOriginal(d,'dual','quarter');assert.deepEqual(r.data.month.categories,['2026 Q1']);assert.equal(r.data.month.revenue[0],155);assert.equal(r.data.month.yieldGrowth[0],81.67);
});
test('metric decimals set the shown precision after scaling',()=>{
 const d=structuredClone(source);d.manifest.metrics.ratio={...d.manifest.metrics.ratio,decimals:0};d.manifest.components.dual={kind:'legacy',family:'chart',datasetId:'ds',config:{code:'t06',data:{}},binding:{datasetId:'ds',categoryField:'date',categoryTarget:'categories',timeGrain:true,measures:{revenue:'revenue',yieldGrowth:'ratio'},scale:{yieldGrowth:100}}};
 assert.equal(resolveOriginal(d,'dual','quarter').data.month.yieldGrowth[0],82);
});
test('filtered KPI comparisons retain signs, units and neutral zero',()=>{
 const d=structuredClone(source);
 d.manifest.components.kpi={kind:'legacy',family:'kpi',datasetId:'ds',config:{type:'mc02',value:'old'},binding:{datasetId:'ds',measures:{value:'revenue',yoy:'ratio',mom:'change'}}};
 d.manifest.metrics.change={aggregation:'sum',field:'change',format:'percent',decimals:1};
 d.snapshot.datasets.ds=[{region:'East',revenue:100,p:12.4,s:100,change:-0.01},{region:'West',revenue:50,p:0,s:100,change:0}];
 d.manifest.filters=[{componentIds:['kpi'],field:'region',op:'in',values:['East']}];
 assert.equal(resolveOriginal(d,'kpi').yoy,'+12.4%');
 assert.equal(resolveOriginal(d,'kpi').mom,'-1%');
 d.manifest.filters[0].values=['West'];
 assert.equal(resolveOriginal(d,'kpi').yoy,'0%');
 assert.equal(resolveOriginal(d,'kpi').mom,'0%');
 d.manifest.filters[0].values=['Missing'];
 assert.equal(resolveOriginal(d,'kpi').yoy,'—');
});
test('rounded zero never receives a positive or negative sign',()=>{
 assert.equal(formatComparison(0.00001,{format:'percent',decimals:1}),'0%');
 assert.equal(formatComparison(-0.00001,{format:'percent',decimals:1}),'0%');
 assert.equal(formatComparison(0,{unit:'m2'}),'0 m2');
});
test('bubble aggregation follows filters and keeps the clicked agent identity',()=>{
 const d=structuredClone(source);
 d.manifest.components.bubble={kind:'legacy',family:'chart',datasetId:'ds',config:{code:'r02',data:{clusters:[[99,99,99,'old']]}},binding:{datasetId:'ds',categoryField:'region',categoryTarget:'clusters',measures:{x:'ratio',y:'revenue',size:'count'},scale:{x:100}}};
 d.manifest.metrics.count={aggregation:'count'};
 d.manifest.filters=[{componentIds:['bubble'],field:'date',op:'in',values:['2026-02-01']}];
 const points=resolveOriginal(d,'bubble').data.clusters;
 assert.deepEqual(points,[[10,20,1,'East'],[70,35,1,'West']]);
 const highlighted=linkagePoint(points[0],0,[],'East',true);
 assert.equal(highlighted.itemStyle.opacity,1);
 assert.equal(linkagePoint(points[1],1,[],'East',true).itemStyle.opacity,.22);
 assert.equal(linkageValue({value:highlighted.value},true),'East');
 assert.equal(linkageValue({name:'East'},false),'East');
 d.manifest.filters[0].values=['missing'];
 assert.deepEqual(resolveOriginal(d,'bubble').data.clusters,[]);
});
