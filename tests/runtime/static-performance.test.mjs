import test from 'node:test';import assert from 'node:assert/strict';
import {visibleRows,aggregate} from '../../dashboard_runtime/web/engine.mjs';
const document=rows=>({dataVersion:'v1',manifest:{components:{a:{datasetId:'sales'},b:{datasetId:'sales'}},metrics:{},datasets:{},filters:[{field:'carrier',op:'in',values:['HO'],componentIds:['a','b']}]},snapshot:{datasets:{sales:rows},componentData:{}}});
// @wu-test type=behavior | scope=filtered row cache | protects=筛选或数据变化后使用过期结果 | debt=D6
test('same filter scopes share rows, changing filters or snapshots invalidates results',()=>{
 const doc=document([{carrier:'HO',v:2},{carrier:'MU',v:7}]);const a=visibleRows(doc,'a');assert.equal(a,visibleRows(doc,'b'));assert.equal(aggregate(a,{aggregation:'sum',field:'v'}),2);
 doc.manifest.filters[0].values=['MU'];assert.equal(aggregate(visibleRows(doc,'a'),{aggregation:'sum',field:'v'}),7);
 doc.snapshot.datasets.sales=[{carrier:'MU',v:9}];assert.equal(aggregate(visibleRows(doc,'a'),{aggregation:'sum',field:'v'}),9);
});
// @wu-test type=behavior | scope=aggregation | protects=空值负数比例及大数组最大值错误
test('single-pass aggregates preserve nulls, negatives, ratios and large min/max',()=>{
 const rows=[{v:null,d:0},{v:NaN,d:2},{v:-3,d:2},{v:5,d:0}];
 for(const [aggregation,expected]of [['sum',2],['avg',1],['min',-3],['max',5]])assert.equal(aggregate(rows,{aggregation,field:'v'}),expected);
 assert.equal(aggregate(rows,{aggregation:'ratio',numerator:'v',denominator:'d'}),.5);
 assert.equal(aggregate([{v:null}],{aggregation:'sum',field:'v'}),null);
 assert.equal(aggregate(Array.from({length:200000},(_,v)=>({v})),{aggregation:'max',field:'v'}),199999);
});
