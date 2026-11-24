import { test } from 'bun:test';import assert from 'node:assert/strict';
import {createStaticQuery} from '../../dashboard_runtime/web/static-query.mjs';
const make=()=>({revision:4,manifest:{filters:[],datasets:{sales:{fields:{month:{},agent:{},pax:{}}}},metrics:{pax:{aggregation:'sum',field:'pax'}},components:{card:{kind:'legacy',family:'kpi',datasetId:'sales',binding:{measures:{value:'pax'}},config:{type:'mc01'}},table:{kind:'table',datasetId:'sales',config:{},presentation:{columns:[{key:'agent',title:'代理'},{key:'pax',title:'销量'}],groupBy:['agent'],sumFields:['pax']}}}},snapshot:{datasets:{}},staticFiles:{sales:['aug','sep']},staticPartitions:{sales:{field:'month',files:{'2026-08':['aug'],'2026-09':['sep']}}}});
// @wu-test type=integration | scope=static partition query | protects=跨月份取错数据或重复加载相同分区
test('month filtering loads only matching static partition and reuses it',async()=>{
 const calls=[];const engine=createStaticQuery(make(),async file=>{calls.push(file);return [{month:file==='aug'?'2026-08':'2026-09',agent:'A',pax:file==='aug'?2:3}];});
 const filters=[{field:'month',op:'in',values:['2026-09'],componentIds:['card','table']}];
 const result=await engine.query({componentIds:['card','table'],filters});assert.equal(result.computed.components.card.value,'3');assert.deepEqual(calls,['sep']);
 await engine.query({componentIds:['card'],filters});assert.deepEqual(calls,['sep']);
 const all=await engine.query({componentIds:['card'],filters:[]});assert.equal(all.computed.components.card.value,'5');assert.deepEqual(calls,['sep','aug']);
});
// @wu-test type=integration | scope=static filter options | protects=多个数据集串行读取或遗漏候选值
test('option reads use the bounded queue and combine distinct datasets',async()=>{
 const doc=make(),files=['a','b','c','d','e','f'];
 for(const file of files)doc.manifest.components[file]={datasetId:file};
 doc.manifest.components.extra={datasetId:'a'};
 doc.manifest.filters=[{id:'office',field:'office',op:'in',componentIds:[...files,'extra']}];
 doc.staticOptions=Object.fromEntries(files.map(file=>[file,{office:file}]));
 let active=0,peak=0;
 const calls=[];
 const query=createStaticQuery(doc,async file=>{
  calls.push(file);peak=Math.max(peak,++active);
  await new Promise(resolve=>setImmediate(resolve));
  active--;return [file,'shared'];
 });
 assert.deepEqual((await query.query({filterId:'office',offset:1,limit:2})),
  {values:['b','c'],offset:1,totalValues:7,hasMore:true});
 assert.equal(peak,4);
 assert.deepEqual(calls,files);
 assert.deepEqual((await query.query({filterId:'office',search:'shared'})).values,['shared']);
 assert.deepEqual(calls,files);
});
// @wu-test type=integration | scope=COS partition reads and options | protects=选项查询下载其他营业部分片或忽略完整的发布选项索引
test('prepared and partition options need no files, while scoped cards load only a selected shard',async()=>{
 const doc=make();
 delete doc.staticPartitions;
 doc.manifest.filters=[
  {id:'office',field:'month',op:'in',componentIds:['card'],values:['2026-09']},
  {id:'agent',field:'agent',op:'in',componentIds:['card'],values:[]},
 ];
 doc.staticFilterOptions={agent:['A','B']};
 doc.staticPartitionIndexes={sales:{field:'month',entries:[
  {value:'2026-08',files:['aug']},{value:'2026-09',files:['sep']},
 ]}};
 const calls=[];
 const query=createStaticQuery(doc,async file=>{
  calls.push(file);
  assert.equal(file,'sep');
  return {rows:[{month:'2026-09',pax:3}],ordinals:[1]};
 });
 assert.deepEqual((await query.query({filterId:'office'})).values,['2026-08','2026-09']);
 assert.deepEqual((await query.query({filterId:'agent',search:'b'})).values,['B']);
 assert.deepEqual(calls,[]);
 const result=await query.query({componentIds:['card']});
 assert.equal(result.computed.components.card.value,'3');
 assert.deepEqual(calls,['sep']);
});
// @wu-test type=integration | scope=static table query | protects=分页排序搜索与导出使用不同数据范围
test('table grouping, sort, paging, search and full CSV export use same scope',async()=>{
 const engine=createStaticQuery(make(),async file=>file==='aug'?[]:[{month:'2026-09',agent:'A',pax:2},{month:'2026-09',agent:'B',pax:5},{month:'2026-09',agent:'A',pax:4}]);
 const args={componentIds:['table'],tableStates:{table:{pageSize:1,sortCol:'pax',sortDir:'desc'}}};const first=await engine.query(args);assert.deepEqual(first.computed.components.table.rows,[{agent:'A',pax:6}]);assert.equal(first.computed.tables.table.totalRows,2);
 const second=await engine.query({...args,tableStates:{table:{...args.tableStates.table,page:2}}});assert.deepEqual(second.computed.components.table.rows,[{agent:'B',pax:5}]);
 const search=await engine.query({...args,tableStates:{table:{keyword:'B'}}});assert.equal(search.computed.tables.table.totalRows,1);
 const exported=await engine.query({...args,export:{}});assert.equal(exported.rowCount,2);assert.match(exported.csv,/代理/);assert.match(exported.csv,/6/);
});

// @wu-test type=integration | scope=static calculated table | protects=网页按行平均比例或空分母展示零值
test('table calculates ratio after grouping and after filtering',async()=>{
 const d=make(),c=d.manifest.components.table;c.presentation={columns:[{key:'agent',title:'代理'},{key:'rate',title:'指标值'},{key:'n'},{key:'d'},{key:'unit'}],groupBy:['agent','unit'],sumFields:['n','d','rate'],calculatedColumns:{rate:{numerator:'n',denominator:'d',unitField:'unit',decimals:1}},tableState:{pageSize:10}};
 d.staticFiles.sales=['all'];delete d.staticPartitions;
 const query=createStaticQuery(d,async()=>[{agent:'A',unit:'%',n:1,d:2},{agent:'A',unit:'%',n:2,d:8},{agent:'B',unit:'分钟',n:36,d:3},{agent:'C',unit:'%',n:null,d:0}]);
 let result=await query.query({componentIds:['table']});assert.deepEqual(result.computed.components.table.rows.map(r=>r.rate),['30.0%','12.0 分钟','—']);
 result=await query.query({componentIds:['table'],filters:[{field:'agent',op:'in',values:['B'],componentIds:['table']}]});assert.equal(result.computed.components.table.rows[0].rate,'12.0 分钟');
});
