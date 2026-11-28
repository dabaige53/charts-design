import { test } from 'bun:test';import assert from 'node:assert/strict';
import {visibleRows,aggregate,aggregateGroups} from '../../runtime-ui/shared/engine.mjs';
const document=rows=>({dataVersion:'v1',manifest:{components:{a:{datasetId:'sales'},b:{datasetId:'sales'}},metrics:{},datasets:{},filters:[{field:'carrier',op:'in',values:['HO'],componentIds:['a','b']}]},snapshot:{datasets:{sales:rows},componentData:{}}});
// @wu-test type=behavior | scope=filtered row cache | protects=筛选或数据变化后使用过期结果 | debt=impl-detail
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

// @wu-test type=behavior | scope=共享筛选范围 | protects=同义筛选重复扫描，或null、缺失和不同标量类型串用缓存
test('equivalent filters share one scan while membership keeps scalar types and missing values',()=>{
 let reads=0;
 const rows=Array.from({length:2000},(_,i)=>({get carrier(){reads++;return i%2?'HO':'MU';},v:i}));
 const doc=document(rows);
 doc.manifest.filters=[
  {field:'carrier',op:'in',values:['HO','MU'],componentIds:['a']},
  {field:'v',op:'range',values:[0,1000],componentIds:['a']},
  {field:'v',op:'range',values:[0,1000],componentIds:['b']},
  {field:'carrier',op:'in',values:['MU','HO','HO'],componentIds:['b']},
 ];
 const first=visibleRows(doc,'a'),scanned=reads;
 assert.equal(visibleRows(doc,'b'),first);assert.equal(reads,scanned);assert.equal(first.length,1001);
 doc.snapshot.datasets.sales=[{carrier:null},{},{carrier:0},{carrier:false},{carrier:'0'}];
 for(const [value,index]of [[null,0],[undefined,1],[0,2],[false,3],['0',4]]){
  doc.manifest.filters=[{field:'carrier',op:'in',values:[value],componentIds:['a']}];
  assert.deepEqual(visibleRows(doc,'a'),[doc.snapshot.datasets.sales[index]]);
 }
});

// @wu-test type=behavior | scope=共享流式分组 | protects=相同分组重复遍历明细或组件修改返回值污染后续指标
test('grouped fields are scanned once and reused across measures, aliases and formatting',()=>{
 let groupReads=0,valueReads=0;
 const rows=Array.from({length:5000},(_,i)=>({get category(){groupReads++;return i%2;},get v(){valueReads++;return i%2+1;},n:i%2+1,d:2}));
 const first=aggregateGroups(rows,['category'],{total:{aggregation:'sum',field:'v'}});
 assert.deepEqual(first,[{keys:[0],values:{total:2500}},{keys:[1],values:{total:5000}}]);
 first[0].keys[0]='changed';first[0].values.total=-1;
 assert.deepEqual(aggregateGroups(rows,['category'],{average:{aggregation:'avg',field:'v',label:'Display only',decimals:1}}),
  [{keys:[0],values:{average:1}},{keys:[1],values:{average:2}}]);
 assert.equal(groupReads,rows.length);assert.equal(valueReads,rows.length);
 assert.deepEqual(aggregateGroups(rows,['category'],{ratio:{aggregation:'ratio',numerator:'n',denominator:'d'}}),
  [{keys:[0],values:{ratio:.5}},{keys:[1],values:{ratio:1}}]);
 assert.equal(groupReads,2*rows.length);assert.equal(valueReads,rows.length);
 assert.deepEqual(aggregateGroups(rows,['category'],{renamed:{aggregation:'sum',field:'v'}}),
  [{keys:[0],values:{renamed:2500}},{keys:[1],values:{renamed:5000}}]);
 assert.equal(groupReads,2*rows.length);
});

// @wu-test type=boundary | scope=分组语义 | protects=流式聚合改变空值、BigInt、实体净额、唯一属性或分组顺序
test('streamed groups preserve nulls, scalar keys, entity netting and unique attributes',()=>{
 const rows=[
  {g:'A',v:2,n:2,d:4,entity:'x',label:'one'},
  {g:'A',v:null,n:-2,d:1,entity:'x',label:'one'},
  {g:'A',v:4,n:1,d:2,entity:'y',label:'two'},
  {g:'A',v:NaN,n:0,d:0,entity:null,label:null},
  {g:null,v:-1,n:0,d:0,entity:'x'},
  {v:3,n:null,d:2,entity:'z'},
 ];
 const metrics={sum:{aggregation:'sum',field:'v'},avg:{aggregation:'avg',field:'v'},min:{aggregation:'min',field:'v'},max:{aggregation:'max',field:'v'},count:{aggregation:'count'},ratio:{aggregation:'ratio',numerator:'n',denominator:'d'},entity:{aggregation:'entity_ratio',entityField:'entity',numerator:'n',denominator:'d'},unique:{aggregation:'unique',field:'label'}};
 assert.deepEqual(aggregateGroups(rows,['g'],metrics,{nulls:true}),[
  {keys:['A'],values:{sum:6,avg:3,min:2,max:4,count:4,ratio:1/7,entity:.5,unique:null}},
  {keys:[null],values:{sum:2,avg:1,min:-1,max:3,count:2,ratio:0,entity:0,unique:null}},
 ]);
 const typed=[{g:'1'},{g:1},{g:null},{},{g:false},{g:-0},{g:0},{g:1n,v:4n},{g:1n,v:5}];
 assert.deepEqual(aggregateGroups(typed,['g'],{count:{aggregation:'count'},sum:{aggregation:'sum',field:'v'}}),[
  {keys:['1'],values:{count:1,sum:null}},{keys:[1],values:{count:1,sum:null}},
  {keys:[null],values:{count:1,sum:null}},{keys:[undefined],values:{count:1,sum:null}},
  {keys:[false],values:{count:1,sum:null}},{keys:[0],values:{count:2,sum:null}},
  {keys:[1n],values:{count:2,sum:5}},
 ]);
 assert.deepEqual(aggregateGroups([],['g'],metrics),[]);
});

// @wu-test type=boundary | scope=分组缓存容量 | protects=高基数分组被永久缓存并保留大量派生数据
test('high-cardinality grouping is complete but is not kept beyond the cache budget',()=>{
 let reads=0;
 const rows=Array.from({length:100000},(_,i)=>({get g(){reads++;return i;},v:1}));
 const first=aggregateGroups(rows,['g'],{value:{aggregation:'sum',field:'v'}});
 assert.equal(first.length,rows.length);assert.equal(first.at(-1).values.value,1);
 const second=aggregateGroups(rows,['g'],{value:{aggregation:'sum',field:'v'}});
 assert.equal(second.length,rows.length);assert.equal(reads,rows.length*2);
});
