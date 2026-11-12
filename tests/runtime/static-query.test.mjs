import { test } from 'bun:test';import assert from 'node:assert/strict';
import {createStaticResources} from '../../dashboard_runtime/web/static-resources.mjs';
import {createStaticQuery} from '../../dashboard_runtime/web/static-query.mjs';
const make=()=>({revision:4,manifest:{filters:[],datasets:{sales:{fields:{month:{},agent:{},pax:{}}}},metrics:{pax:{aggregation:'sum',field:'pax'}},components:{card:{kind:'legacy',family:'kpi',datasetId:'sales',binding:{measures:{value:'pax'}},config:{type:'mc01'}},table:{kind:'table',datasetId:'sales',config:{},presentation:{columns:[{key:'agent',title:'代理'},{key:'pax',title:'销量'}],groupBy:['agent'],sumFields:['pax']}}}},snapshot:{datasets:{}},staticFiles:{sales:['aug','sep']},staticPartitions:{sales:{field:'month',files:{'2026-08':['aug'],'2026-09':['sep']}}}});
// @wu-test type=integration | scope=static partition query | protects=跨月份取错数据或重复加载相同分区
test('month filtering loads only matching static partition and reuses it',async()=>{
 const calls=[];const resources=createStaticResources({fetcher:async url=>{const file=new URL(url).pathname.slice(1);calls.push(file);return new Response(JSON.stringify([{month:file==='aug'?'2026-08':'2026-09',agent:'A',pax:file==='aug'?2:3}]));}});
 const engine=createStaticQuery(make(),file=>resources.json('https://site.example/'+file));
 const filters=[{field:'month',op:'in',values:['2026-09'],componentIds:['card','table']}];
 const result=await engine.query({componentIds:['card','table'],filters});assert.equal(result.computed.components.card.value,'3');assert.deepEqual(calls,['sep']);
 await engine.query({componentIds:['card'],filters});assert.deepEqual(calls,['sep']);
 const all=await engine.query({componentIds:['card'],filters:[]});assert.equal(all.computed.components.card.value,'5');assert.deepEqual(calls,['sep','aug']);
});

// @wu-test type=performance | scope=static range cache | protects=往返筛选范围再次读取组装数据或缓存不受数量上限约束
test('revisits recent ranges without rereading partitions and evicts old ranges',async()=>{
 const calls=[];
 const engine=createStaticQuery(make(),async file=>{calls.push(file);return [{month:file==='aug'?'2026-08':'2026-09',pax:file==='aug'?2:3}];},{maxScopes:2});
 const select=values=>engine.query({componentIds:['card'],filters:[{field:'month',op:'in',values,componentIds:['card']}]});
 await select(['2026-09']);await select(['2026-08']);
 assert.equal((await select(['2026-09'])).computed.components.card.value,'3');
 assert.deepEqual(calls,['sep','aug']);
 await select([]);await select(['2026-08']);
 assert.deepEqual(calls,['sep','aug','aug','sep','aug']);
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

// @wu-test type=performance | scope=static options loading | protects=多个选项索引串行等待或打开筛选器拉取行数据
test('loads independent option indexes concurrently and retains them across searches',async()=>{
 const d=make();d.manifest.components.second={...d.manifest.components.table,datasetId:'other'};
 d.manifest.filters=[{id:'agent',field:'agent',op:'in',values:[],componentIds:['card','table','second']}];
 d.staticOptions={sales:{agent:'one'},other:{agent:'two'}};
 const reads=[],releases=[];
 const engine=createStaticQuery(d,file=>{reads.push(file);return new Promise(resolve=>releases.push(()=>resolve(file==='one'?['A','B']:['B','C'])));});
 const first=engine.query({filterId:'agent'});
 for(let i=0;i<5;i++)await Promise.resolve();
 assert.deepEqual(reads,['one','two']);releases.forEach(f=>f());
 assert.deepEqual((await first).values,['A','B','C']);
 assert.deepEqual((await engine.query({filterId:'agent',search:'C'})).values,['C']);
 assert.deepEqual(reads,['one','two']);
});
// @wu-test type=boundary | scope=COS option index contract | protects=选项索引缺失时静默下载全部行分片
test('a missing COS option index fails without reading any rows',async()=>{
 const d=make();d.storageFormat='cos-v1';d.manifest.filters=[{id:'agent',field:'agent',op:'in',values:[],componentIds:['table']}];
 let reads=0;const engine=createStaticQuery(d,async()=>{reads++;return [];});
 await assert.rejects(engine.query({filterId:'agent'}),/选项索引缺失/);assert.equal(reads,0);
});

// @wu-test type=performance | scope=static query concurrent batches | protects=同一筛选被四个并发批次重复扫描且指标缓存无法复用
test('concurrent batches filter one shared row scope once',async()=>{
 const d=make(),ids=Array.from({length:16},(_,i)=>'card'+i);
 d.manifest.components=Object.fromEntries(ids.map(id=>[id,{...d.manifest.components.card}]));
 d.staticFiles.sales=['all'];delete d.staticPartitions;
 let visits=0;
 const rows=Array.from({length:1000},(_,i)=>({get agent(){visits++;return i%2?'B':'A';},pax:1}));
 const query=createStaticQuery(d,async()=>rows);
 const filters=[{id:'agent',field:'agent',op:'in',values:['A'],componentIds:ids}];
 const results=await Promise.all(Array.from({length:4},(_,i)=>query.query({componentIds:ids.slice(i*4,i*4+4),filters})));
 assert.equal(visits,rows.length);
 for(const result of results)for(const card of Object.values(result.computed.components))assert.equal(card.value,'500');
 const changed=await query.query({componentIds:ids,filters:[{...filters[0],values:['B']}]});
 assert.equal(visits,rows.length*2);
 assert.equal(changed.computed.components.card0.value,'500');
});

// @wu-test type=boundary | scope=static query cancellation | protects=取消旧查询导致同范围的新查询失败或接收已取消结果
test('cancelling one row consumer preserves a concurrent current query',async()=>{
 const d=make(),controller=new AbortController(),releases=[];
 const engine=createStaticQuery(d,()=>new Promise(resolve=>releases.push(resolve)));
 const args={componentIds:['card'],filters:[{field:'month',op:'in',values:['2026-09'],componentIds:['card']}]};
 const stale=assert.rejects(engine.query(args,{signal:controller.signal}),{name:'AbortError'});
 const current=engine.query(args);
 controller.abort();releases.forEach(resolve=>resolve([{month:'2026-09',pax:3}]));
 await stale;assert.equal((await current).computed.components.card.value,'3');
});

// @wu-test type=performance | scope=static query cooperative cancellation | protects=长批次占住Worker导致取消消息必须等所有组件算完
test('a slow component yields before calculating remaining stale components',async()=>{
 const d=make(),controller=new AbortController();let calculated=0;
 d.manifest.components=Object.fromEntries(['one','two','three'].map(id=>[id,{
  kind:'legacy',family:'kpi',datasetId:'sales',binding:{measures:{value:'pax'}},
  get config(){calculated++;if(calculated===1){
   setTimeout(()=>controller.abort(),0);
   const until=performance.now()+12;while(performance.now()<until){}
  }return {type:'mc01'};}
 }]));
 // Spread the component definition once per component; the config is then read by the resolver.
 const engine=createStaticQuery(d,async()=>[{pax:1}]);
 await assert.rejects(engine.query({componentIds:['one','two','three']},{signal:controller.signal}),{name:'AbortError'});
 assert.equal(calculated,1);
});
