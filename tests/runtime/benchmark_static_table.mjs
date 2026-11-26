/** Explicit paging/sorting benchmark; rows are decoded before the timer starts. */
import {options,queryModule,saveReport,sources,worker} from './benchmark_static.mjs';

// @wu-test type=performance | scope=静态表格分页 | protects=首屏全量计算或翻页重复排序且结果未核对
async function measure(directory,{rows:count}){
  const createStaticQuery=await queryModule(directory);
  const rows=Array.from({length:count},(_,i)=>({id:i,n:i%101,d:i%19+1,unit:'%'}));
  const document={id:'table',revision:1,manifest:{filters:[],datasets:{sales:{fields:{id:{type:'number'},n:{type:'number'},d:{type:'number'},unit:{type:'string'},rate:{type:'number'}}}},metrics:{},
    components:{table:{kind:'table',datasetId:'sales',presentation:{columns:[{key:'id'},{key:'n'},{key:'d'},{key:'rate'}],calculatedColumns:{rate:{numerator:'n',denominator:'d',unitField:'unit'}}}}}},
    snapshot:{datasets:{}},staticFiles:{sales:['all']}};
  const query=createStaticQuery(document,async()=>rows),samplesMs={};
  for(const [name,state]of [['firstPage',{page:1}],['secondPage',{page:2}],['sortFirst',{page:1,sortCol:'n',sortDir:'desc'}],['sortNext',{page:2,sortCol:'n',sortDir:'desc'}]]){
    const started=performance.now(),result=await query.query({componentIds:['table'],tableStates:{table:{pageSize:10,...state}}});
    samplesMs[name]=performance.now()-started;
    const table=result.computed.components.table;
    const page=result.computed.tables.table.page;
    if(result.computed.tables.table.totalRows!==count||table.rows.length!==Math.min(10,count-(page-1)*10))throw Error('Wrong page size or total');
    for(const row of table.rows)if(row.rate!==(100*row.n/row.d).toFixed(1)+'%')throw Error('Wrong calculated ratio');
  }
  return {rows:count,samplesMs,maxRssMiB:process.resourceUsage().maxRSS/1024};
}

async function main(){
  if(process.argv[2]==='--internal-run'){
    console.log(JSON.stringify(await measure(process.argv[3],JSON.parse(process.argv[5]))));return;
  }
  const config=options(process.argv.slice(2),{rows:1000000}),input=await sources(config);
  try{
    const results=Object.fromEntries(['baseline','candidate'].map(name=>[name,worker(import.meta.url,input[name].directory,'table',{rows:config.rows})]));
    await saveReport(config.output,{synthetic:true,runtime:{bun:process.versions.bun,platform:process.platform,arch:process.arch},
      scope:'One decoded dataset; calculated ratio columns; first page, next page, first sort and next sorted page. Page size 10. Excludes network, Parquet decoding and DOM rendering.',
      cache:'One query engine per process; subsequent pages retain its cache. Baseline and candidate run in separate Bun processes.',
      baselineRevision:input.baselineRevision,source:{baseline:input.baseline.sha256,candidate:input.candidate.sha256},results});
  }finally{await input.cleanup();}
}

if(import.meta.main)await main();
