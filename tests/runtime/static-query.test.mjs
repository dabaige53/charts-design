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

// @wu-test type=performance | scope=static filter option paging | protects=防止 audit-9 复发：读取后续候选页重复遍历完整候选集
test('option pages reuse prepared values and search changes invalidate that result',async()=>{
 const d=make();d.manifest.filters=[{id:'agent',field:'agent',op:'in',values:[],componentIds:['table']}];
 d.staticOptions={sales:{agent:'options'}};
 let visits=0;
 const values=Array.from({length:301},(_,i)=>`Agent ${String(i).padStart(3,'0')}`);
 values[Symbol.iterator]=function*(){for(let i=0;i<this.length;i++){visits++;yield this[i];}};
 const query=createStaticQuery(d,async()=>values);
 const first=await query.query({filterId:'agent',limit:100});
 const second=await query.query({filterId:'agent',offset:100,limit:100});
 const last=await query.query({filterId:'agent',offset:300,limit:100});
 assert.equal(visits,301);
 assert.equal(first.totalValues,301);assert.equal(second.values[0],'Agent 100');
 assert.deepEqual(last.values,['Agent 300']);assert.equal(last.hasMore,false);
 assert.deepEqual((await query.query({filterId:'agent',search:'299'})).values,['Agent 299']);
});
