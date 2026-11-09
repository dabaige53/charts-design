import test from 'node:test';import assert from 'node:assert/strict';
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
// @wu-test type=integration | scope=static table query | protects=分页排序搜索与导出使用不同数据范围
test('table grouping, sort, paging, search and full CSV export use same scope',async()=>{
 const engine=createStaticQuery(make(),async file=>file==='aug'?[]:[{month:'2026-09',agent:'A',pax:2},{month:'2026-09',agent:'B',pax:5},{month:'2026-09',agent:'A',pax:4}]);
 const args={componentIds:['table'],tableStates:{table:{pageSize:1,sortCol:'pax',sortDir:'desc'}}};const first=await engine.query(args);assert.deepEqual(first.computed.components.table.rows,[{agent:'A',pax:6}]);assert.equal(first.computed.tables.table.totalRows,2);
 const second=await engine.query({...args,tableStates:{table:{...args.tableStates.table,page:2}}});assert.deepEqual(second.computed.components.table.rows,[{agent:'B',pax:5}]);
 const search=await engine.query({...args,tableStates:{table:{keyword:'B'}}});assert.equal(search.computed.tables.table.totalRows,1);
 const exported=await engine.query({...args,export:{}});assert.equal(exported.rowCount,2);assert.match(exported.csv,/代理/);assert.match(exported.csv,/6/);
});
