/** Explicit paging/sorting/candidate benchmark; rows are decoded before timing. */
import {options,queryModule,saveReport,sources,worker} from './benchmark_static.mjs';

// @wu-test type=performance | scope=静态表格分页 | protects=首屏全量计算或翻页重复排序且结果未核对
async function measure(directory,{rows:count,samples}){
  const createStaticQuery=await queryModule(directory);
  const choices=Math.min(count,100000),label=id=>'Choice '+String(id).padStart(6,'0');
  const rows=Array.from({length:count},(_,i)=>({id:i,n:i%101,d:i%19+1,unit:'%',choice:label((count-i-1)%choices)}));
  const document={id:'table',revision:1,manifest:{filters:[{id:'choice',field:'choice',op:'in',componentIds:['table'],values:[]}],datasets:{sales:{fields:{id:{type:'number'},n:{type:'number'},d:{type:'number'},unit:{type:'string'},rate:{type:'number'},choice:{type:'string'}}}},metrics:{},
    components:{table:{kind:'table',datasetId:'sales',presentation:{columns:[{key:'id'},{key:'n'},{key:'d'},{key:'rate'}],calculatedColumns:{rate:{numerator:'n',denominator:'d',unitField:'unit'}}}}}},
    snapshot:{datasets:{}},staticFiles:{sales:['all']}};
  const samplesMs={},expected=Array.from({length:choices},(_,i)=>label(i));
  for(let sample=0;sample<samples;sample++){
   Bun.gc(true);
   const query=createStaticQuery(document,async()=>rows);
   for(const [name,state]of [['firstPage',{page:1}],['secondPage',{page:2}],['sortFirst',{page:1,sortCol:'n',sortDir:'desc'}],['sortNext',{page:2,sortCol:'n',sortDir:'desc'}]]){
    const started=performance.now(),result=await query.query({componentIds:['table'],tableStates:{table:{pageSize:10,...state}}});
    (samplesMs[name]??=[]).push(performance.now()-started);
    const table=result.computed.components.table;
    const page=result.computed.tables.table.page;
    if(result.computed.tables.table.totalRows!==count||table.rows.length!==Math.min(10,count-(page-1)*10))throw Error('Wrong page size or total');
    for(const row of table.rows)if(row.rate!==(100*row.n/row.d).toFixed(1)+'%')throw Error('Wrong calculated ratio');
   }
   for(const [name,args]of [['optionsFirst',{}],['optionsNext',{offset:10}],['optionsSearch',{search:'009'}],['optionsSearchNext',{search:'009',offset:10}]]){
    const started=performance.now(),result=await query.query({filterId:'choice',limit:10,...args});
    (samplesMs[name]??=[]).push(performance.now()-started);
    const matches=args.search?expected.filter(value=>value.includes(args.search)):expected;
    if(result.totalValues!==matches.length||JSON.stringify(result.values)!==JSON.stringify(matches.slice(args.offset||0,(args.offset||0)+10)))throw Error('Wrong candidate values or total');
   }
  }
  return {rows:count,choices,samplesMs,medianMs:Object.fromEntries(Object.entries(samplesMs).map(([name,values])=>[name,[...values].sort((a,b)=>a-b)[Math.floor(values.length/2)]])),maxRssMiB:process.resourceUsage().maxRSS/1024};
}

async function main(){
  if(process.argv[2]==='--internal-run'){
    console.log(JSON.stringify(await measure(process.argv[3],JSON.parse(process.argv[5]))));return;
  }
  const config=options(process.argv.slice(2),{rows:1000000,samples:3}),input=await sources(config);
  try{
    const results=Object.fromEntries(['baseline','candidate'].map(name=>[name,worker(import.meta.url,input[name].directory,'table',{rows:config.rows,samples:config.samples})]));
    await saveReport(config.output,{synthetic:true,runtime:{bun:process.versions.bun,platform:process.platform,arch:process.arch},
      scope:'One decoded dataset; calculated ratio columns; first and next pages, first sort and next sorted page, candidate first page/next page/search/next search page. Up to 100,000 unique candidates; page size 10. Excludes network, Parquet decoding and DOM rendering.',
      cache:'Fresh query engine for each sample; subsequent pages retain its cache. Explicit GC before each sample. Baseline and candidate run in separate Bun processes.',
      baselineRevision:input.baselineRevision,source:{baseline:input.baseline.sha256,candidate:input.candidate.sha256},results});
  }finally{await input.cleanup();}
}

if(import.meta.main)await main();
