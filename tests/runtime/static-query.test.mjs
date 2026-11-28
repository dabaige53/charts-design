import { test } from 'bun:test';import assert from 'node:assert/strict';
import {createStaticQuery} from '../../runtime-ui/shared/static-query.mjs';
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

// @wu-test type=integration | scope=静态计算列表格分页 | protects=为当前页计算全部行，或翻页重新排序及遗漏搜索/CSV所需计算值
test('calculated tables evaluate only the page unless search, sorting or CSV needs every value',async()=>{
 let valueReads=0,idReads=0;
 const rows=Array.from({length:1000},(_,i)=>({get id(){idReads++;return i;},get n(){valueReads++;return i*2+1;},d:2,unit:'%'}));
 const doc=make();delete doc.staticPartitions;doc.staticFiles.sales=['all'];
 doc.manifest.datasets.sales.fields={id:{type:'number'},n:{type:'number'},d:{type:'number'},unit:{type:'string'},rate:{type:'number'}};
 doc.manifest.components.table.presentation={columns:[{key:'id'},{key:'rate'}],calculatedColumns:{rate:{numerator:'n',denominator:'d',unitField:'unit'}}};
 const query=createStaticQuery(doc,async()=>rows);
 const page=state=>query.query({componentIds:['table'],tableStates:{table:{pageSize:10,...state}}});
 let result=await page({page:1});assert.equal(result.computed.tables.table.totalRows,1000);
 assert.equal(result.computed.components.table.rows[0].rate,'50.0%');assert.equal(valueReads,10);
 result=await page({page:2});assert.equal(result.computed.components.table.rows[0].id,10);assert.equal(valueReads,20);
 await page({page:1,sortCol:'id',sortDir:'desc'});const sortedReads=idReads;
 result=await page({page:2,sortCol:'id',sortDir:'desc'});
 assert.equal(result.computed.components.table.rows[0].id,989);assert.equal(idReads,sortedReads+10);
 const beforeCalculatedSort=valueReads;
 result=await page({sortCol:'rate',sortDir:'desc'});
 assert.equal(result.computed.components.table.rows[0].id,999);assert.equal(valueReads,beforeCalculatedSort+1000);
 result=await page({keyword:'499.5'});
 assert.equal(result.computed.tables.table.totalRows,1);assert.equal(result.computed.components.table.rows[0].id,499);
 const exported=await query.query({componentIds:['table'],export:{columns:['id','rate'],fieldNames:true}});
 assert.equal(exported.rowCount,1000);assert.match(exported.csv,/"499","499.5"/);assert.match(exported.csv,/"999","999.5"/);
});

// @wu-test type=boundary | scope=延后计算列 | protects=改变计算列依赖顺序或忽略用于排序的raw计算列
test('deferred columns preserve numeric/display passes and derived raw sorting',async()=>{
 const doc=make();delete doc.staticPartitions;doc.staticFiles.sales=['all'];
 doc.manifest.datasets.sales.fields={id:{type:'number'},n:{type:'number'},d:{type:'number'},unit:{type:'string'},rate:{type:'string'},rawRate:{type:'number'},mid:{type:'number'},final:{type:'number'}};
 doc.manifest.components.table.presentation={columns:[{key:'id'},{key:'final'},{key:'mid'},{key:'rate'}],calculatedColumns:{
  final:{numerator:'mid',denominator:'d',unitField:'unit'},
  mid:{numerator:'n',denominator:'d',unitField:'unit'},
  rawRate:{numerator:'n',denominator:'d',unitField:'unit'},
 }};
 const query=createStaticQuery(doc,async()=>[{id:1,n:8,d:2,mid:100,rate:'z',unit:'units'},{id:2,n:2,d:2,mid:100,rate:'a',unit:'units'}]);
 const page=await query.query({componentIds:['table']});
 assert.equal(page.computed.components.table.rows[0].final,'2.0 units');
 const sorted=await query.query({componentIds:['table'],tableStates:{table:{sortCol:'rate',sortDir:'asc'}}});
 assert.deepEqual(sorted.computed.components.table.rows.map(row=>row.id),[2,1]);
});

// @wu-test type=integration | scope=静态图表共享分组 | protects=同数据同分组的不同图表重复扫全表或共享结果被渲染器改写
test('static charts share grouped calculations without sharing mutable display results',async()=>{
 let reads=0;
 const rows=Array.from({length:1000},(_,i)=>({get agent(){reads++;return i%2?'B':'A';},pax:i%2+1}));
 const doc=make();delete doc.staticPartitions;doc.staticFiles.sales=['all'];
 doc.manifest.components={};
 for(let i=0;i<12;i++)doc.manifest.components['chart'+i]={kind:'legacy',family:'chart',datasetId:'sales',
  binding:{categoryField:'agent',categoryTarget:'categories',measures:{values:'pax'}},config:{code:'c01',data:{}}};
 const query=createStaticQuery(doc,async()=>rows),first=await query.query({});
 assert.equal(reads,rows.length);assert.deepEqual(first.computed.components.chart0.data.values,[500,1000]);
 first.computed.components.chart0.data.values[0]=-1;
 first.computed.components.chart0.data.categories[0]='Changed';
 assert.deepEqual(first.computed.components.chart1.data.values,[500,1000]);
 const second=await query.query({componentIds:['chart0']});
 assert.deepEqual(second.computed.components.chart0.data,{categories:['A','B'],values:[500,1000]});
 assert.equal(reads,rows.length);
});

// @wu-test type=integration | scope=Parquet候选项分片 | protects=候选项被当作JSON值数组或漏读分片，破坏去重排序和分页
test('columnar option descriptors retain legacy values, missing values and paging semantics',async()=>{
 const doc=make(),calls=[];
 doc.manifest.components.other={datasetId:'other'};
 doc.manifest.filters=[{id:'office',field:'office',op:'in',componentIds:['card','other'],values:[]}];
 doc.staticOptions={sales:{office:{field:'candidate',files:['first.parquet','second.parquet']}},other:{office:'legacy.json.gz'}};
 const query=createStaticQuery(doc,async file=>{
  calls.push(file);
  if(file==='first.parquet')return [{candidate:'A'},{candidate:null},{candidate:'B'}];
  if(file==='second.parquet')return {rows:[{candidate:'B'},{candidate:'C'},{}],ordinals:[0,1,2]};
  assert.equal(file,'legacy.json.gz');return ['C','D'];
 });
 assert.deepEqual(await query.query({filterId:'office',offset:1,limit:2}),{values:['A','B'],offset:1,totalValues:5,hasMore:true});
 assert.deepEqual((await query.query({filterId:'office',search:'c'})).values,['C']);
 assert.deepEqual(calls,['first.parquet','second.parquet','legacy.json.gz']);
});

// @wu-test type=integration | scope=静态明细分页缓存 | protects=相同排序的后续明细页重排全量行，或筛选搜索变化后沿用旧结果
test('detail pages reuse sorted rows and invalidate for changed search or filters',async()=>{
 let reads=0;
 const rows=Array.from({length:1000},(_,i)=>({id:i,get value(){reads++;return i;},agent:i%2?'B':'A'}));
 const doc=make();delete doc.staticPartitions;doc.staticFiles.sales=['all'];
 doc.manifest.datasets.sales.fields={id:{type:'number'},value:{type:'number'},agent:{type:'string'}};
 const query=createStaticQuery(doc,async()=>rows),args={detail:true,componentId:'card',sort:[{field:'value',direction:'desc'}],limit:10};
 const first=await query.query(args),scanned=reads;
 assert.deepEqual(first.rows.map(row=>row.id),[999,998,997,996,995,994,993,992,991,990]);
 const next=await query.query({...args,offset:10});assert.equal(next.rows[0].id,989);assert.equal(reads,scanned+10);
 const searched=await query.query({...args,search:'B'});assert.equal(searched.totalRows,500);assert.equal(searched.rows[1].id,997);
 const filtered=await query.query({...args,filters:[{field:'agent',op:'in',values:['A'],componentIds:['card']}]});
 assert.equal(filtered.totalRows,500);assert.equal(filtered.rows[0].id,998);
});

// @wu-test type=boundary | scope=静态读取缓存隔离 | protects=返回值改写污染后续查询，或字段类型及计算定义变化后复用旧结果
test('reading results are isolated and definition changes invalidate computed row caches',async()=>{
 const doc=make();delete doc.staticPartitions;doc.staticFiles.sales=['all'];
 doc.manifest.datasets.sales.fields={agent:{type:'string'},pax:{type:'number'},revenue:{type:'number'}};
 const query=createStaticQuery(doc,async()=>[{agent:'A',pax:2,revenue:20},{agent:'A',pax:3,revenue:30}]);
 const first=await query.query({componentIds:['table']});
 first.computed.components.table.rows[0].pax=999;
 first.computed.components.table.columns[0].title='changed';
 const next=await query.query({componentIds:['table']});
 assert.deepEqual(next.computed.components.table.rows,[{agent:'A',pax:5}]);
 assert.equal(next.computed.components.table.columns[0].title,'代理');
 doc.manifest.components.table.presentation.sumFields=['revenue'];
 assert.deepEqual((await query.query({componentIds:['table']})).computed.components.table.rows,[{agent:'A',revenue:50}]);
 const detail=await query.query({detail:true,componentId:'card'});
 detail.rows[0].pax=999;detail.fields.pax.type='string';
 assert.equal((await query.query({detail:true,componentId:'card'})).rows[0].pax,2);
 assert.equal(doc.manifest.datasets.sales.fields.pax.type,'number');

 const typed=make();delete typed.staticPartitions;typed.staticFiles.sales=['all'];
 typed.manifest.datasets.sales.fields.pax={type:'string'};
 const typedQuery=createStaticQuery(typed,async()=>[{pax:'2%'},{pax:'10%'}]);
 const args={detail:true,componentId:'card',sort:[{field:'pax'}]};
 assert.deepEqual((await typedQuery.query(args)).rows.map(row=>row.pax),['2%','10%']);
 typed.manifest.datasets.sales.fields.pax.type='number';
 assert.deepEqual((await typedQuery.query(args)).rows.map(row=>row.pax),['10%','2%']);
});

// @wu-test type=performance | scope=静态候选项分页 | protects=候选项每次翻页或搜索重新遍历全部行，替换数据源后却复用旧候选值
test('option pages reuse immutable field values and separate changed sources and fields',async()=>{
 let reads=0;
 const rows=Array.from({length:2000},(_,i)=>({get office(){reads++;return 'Office '+String(i%1000).padStart(4,'0');},region:'Region '+i%2}));
 const doc=make();delete doc.staticPartitions;doc.staticFiles.sales=['all'];
 doc.manifest.filters=[{id:'office',field:'office',op:'in',componentIds:['card'],values:[]}];
 let loads=0;
 const query=createStaticQuery(doc,async file=>{loads++;return file==='all'?rows:[{office:'Replacement'}];});
 const [first,next]=await Promise.all([
  query.query({filterId:'office',limit:10}),query.query({filterId:'office',offset:10,limit:10}),
 ]);
 assert.equal(first.totalValues,1000);assert.equal(first.values[0],'Office 0000');assert.equal(reads,2000);
 assert.equal(loads,1);
 first.values[0]='Changed by consumer';
 assert.equal(next.values[0],'Office 0010');assert.equal(reads,2000);
 assert.equal((await query.query({filterId:'office',limit:10})).values[0],'Office 0000');
 const found=await query.query({filterId:'office',search:'009',limit:5});
 assert.deepEqual(found.values,['Office 0009','Office 0090','Office 0091','Office 0092','Office 0093']);
 assert.equal((await query.query({filterId:'office',search:'009',offset:5,limit:5})).values[0],'Office 0094');
 assert.equal(reads,2000);
 doc.manifest.filters[0].field='region';
 assert.deepEqual((await query.query({filterId:'office'})).values,['Region 0','Region 1']);
 doc.manifest.filters[0].field='office';doc.staticFiles.sales=['replacement'];
 assert.deepEqual((await query.query({filterId:'office'})).values,['Replacement']);
});

// @wu-test type=boundary | scope=候选值缓存语义及容量 | protects=混合标量搜索改变比较顺序，或多个候选范围无界常驻
test('option caching retains scalar search order and evicts older candidate scopes',async()=>{
 const doc=make();delete doc.staticPartitions;
 doc.manifest.filters=[];doc.staticOptions={};
 let reads=0;
 for(let i=0;i<20;i++){
  const id='dataset'+i;doc.manifest.components[id]={datasetId:id};
  doc.manifest.filters.push({id,field:'value',op:'in',componentIds:[id],values:[]});
  doc.staticOptions[id]={value:{field:'value',files:[id]}};
 }
 const query=createStaticQuery(doc,async()=>[12,'word',2,null,false,0,'0'].map(value=>({get value(){reads++;return value;}})));
 assert.deepEqual((await query.query({filterId:'dataset0',search:'2'})).values,[2,12]);
 assert.equal(reads,7);
 assert.deepEqual((await query.query({filterId:'dataset0',search:'null'})).values,[null]);
 const all=await query.query({filterId:'dataset0'});
 assert.equal(all.totalValues,7);
 assert(all.values.includes(0)&&all.values.includes('0')&&all.values.includes(false));
 assert.equal(reads,7);
 for(let i=1;i<20;i++)await query.query({filterId:'dataset'+i});
 const scanned=reads;
 assert.deepEqual((await query.query({filterId:'dataset0',search:'2'})).values,[2,12]);
 assert.equal(reads,scanned+7);
});

// @wu-test type=boundary | scope=候选值缓存失效与资源上限 | protects=同版本替换输入后显示旧值，长字符串缓存越界或非法查询仍读数据
test('option cache follows replaced arrays and accounts for long scalar values',async()=>{
 const doc=make();delete doc.staticFiles;delete doc.staticPartitions;
 doc.dataVersion='same-version';doc.snapshot.datasets.sales=[{office:'Original'}];
 doc.manifest.filters=[{id:'office',field:'office',op:'in',componentIds:['card'],values:[]}];
 const query=createStaticQuery(doc,async()=>{throw Error('No files expected');});
 assert.deepEqual((await query.query({filterId:'office'})).values,['Original']);
 doc.snapshot.datasets.sales=[{office:'Replacement'}];
 assert.deepEqual((await query.query({filterId:'office'})).values,['Replacement']);
 let reads=0;
 doc.snapshot.datasets.sales=Array.from({length:1000},(_,i)=>({get office(){reads++;return String(i)+':'+ 'x'.repeat(5000);}}));
 await query.query({filterId:'office'});
 assert.equal(reads,1000);
 await query.query({filterId:'office',offset:100});
 assert.equal(reads,2000);
 for(const args of [{search:'x'.repeat(1001)},{search:17},{offset:-1},{offset:.5},{limit:0},{limit:1001}]){
  await assert.rejects(query.query({filterId:'office',...args}));
 }
 assert.equal(reads,2000);
});
