import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveOriginal} from '../../dashboard_runtime/web/bindings.mjs';
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
 const r=resolveOriginal(d,'dual','quarter');assert.deepEqual(r.data.month.categories,['2026 Q1']);assert.equal(r.data.month.revenue[0],155);assert.ok(Math.abs(r.data.month.yieldGrowth[0]-98/120*100)<1e-9);
});
