/** Explicit synthetic query benchmark; never runs as part of bun test. */
import {execFileSync,spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdir,mkdtemp,readFile,rm,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

export const repository=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const sourceFiles=['static-query.mjs','engine.mjs','bindings.mjs','encoding.mjs','request-queue.mjs'];

export function options(argv,defaults){
  const values={},common=['baseline-ref','baseline-dir','candidate-dir','output'];
  for(let i=0;i<argv.length;i++){
    const name=argv[i].replace(/^--/,'');
    if(!argv[i].startsWith('--')||(!common.includes(name)&&!Object.hasOwn(defaults,name)))throw Error(`Unknown option: ${argv[i]}`);
    if(Object.hasOwn(values,name)||i+1>=argv.length)throw Error(`Missing or duplicate option: --${name}`);
    values[name]=argv[++i];
  }
  if(!!values['baseline-ref']===!!values['baseline-dir']||!values.output){
    throw Error('Supply exactly one of --baseline-ref REF / --baseline-dir WEB_SOURCE_DIRECTORY, and --output PATH. Optional: --candidate-dir WEB_SOURCE_DIRECTORY.');
  }
  for(const [name,value]of Object.entries(defaults)){
    values[name]=Number(values[name]??value);
    if(!Number.isSafeInteger(values[name])||values[name]<1)throw Error(`--${name} must be a positive integer`);
  }
  values['candidate-dir']=resolve(values['candidate-dir']||join(repository,'dashboard_runtime/web'));
  values.output=resolve(values.output);
  return values;
}

export async function sources(config){
  let temporary,baseline,revision;
  try{
    if(config['baseline-ref']){
      revision=execFileSync('git',['rev-parse','--verify','--end-of-options',config['baseline-ref']+'^{commit}'],{cwd:repository,encoding:'utf8'}).trim();
      temporary=await mkdtemp(join(tmpdir(),'charts-static-baseline-'));
      baseline=temporary;
      const prefix='dashboard_runtime/web/';
      const files=execFileSync('git',['ls-tree','-r','--name-only',revision,'--',prefix],{cwd:repository,encoding:'utf8'}).trim().split('\n');
      for(const path of files.filter(path=>path.startsWith(prefix)&&path.endsWith('.mjs'))){
        const target=join(temporary,path.slice(prefix.length));
        await mkdir(dirname(target),{recursive:true});
        await writeFile(target,execFileSync('git',['show',revision+':'+path],{cwd:repository,maxBuffer:16*1024*1024}));
      }
    }else baseline=resolve(config['baseline-dir']);
    const identify=async directory=>({directory,sha256:Object.fromEntries(await Promise.all(sourceFiles.map(async name=>[name,createHash('sha256').update(await readFile(join(directory,name))).digest('hex')]))) });
    return {baseline:await identify(baseline),candidate:await identify(config['candidate-dir']),baselineRevision:revision??null,
      cleanup:async()=>{if(temporary)await rm(temporary,{recursive:true,force:true});}};
  }catch(error){if(temporary)await rm(temporary,{recursive:true,force:true});throw error;}
}

export async function queryModule(directory){
  return (await import(pathToFileURL(join(directory,'static-query.mjs')).href)).createStaticQuery;
}

export function worker(script,directory,mode,parameters){
  const result=spawnSync(process.execPath,[fileURLToPath(script),'--internal-run',directory,mode,JSON.stringify(parameters)],{encoding:'utf8',maxBuffer:16*1024*1024});
  if(result.error)throw result.error;
  if(result.status!==0)throw Error(result.stderr||`Benchmark worker exited with ${result.status}`);
  return JSON.parse(result.stdout);
}

export async function saveReport(path,report){
  await mkdir(dirname(path),{recursive:true});
  await writeFile(path,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({output:path,...report},null,2));
}

function fixture(count,components,probe){
  const counters={categoryReads:0,amountReads:0};
  let expectedSum=0;
  const rows=Array.from({length:count},(_,i)=>{
    expectedSum+=i%101;
    const row={region:'region-'+i%20,month:'2026-'+String(i%12+1).padStart(2,'0')+'-01',amount:i%101,n:i%17,d:i%19+1,entity:'e'+i%2000};
    if(probe){const {region,amount}=row;Object.defineProperties(row,{region:{get(){counters.categoryReads++;return region;}},amount:{get(){counters.amountReads++;return amount;}}});}
    return row;
  });
  const definitions={sum:{aggregation:'sum',field:'amount'},avg:{aggregation:'avg',field:'amount'},ratio:{aggregation:'ratio',numerator:'n',denominator:'d'}};
  const charts={};
  for(let i=0;i<components;i++)charts['chart'+i]={kind:'legacy',family:'chart',datasetId:'sales',title:'Synthetic chart '+i,
    binding:{datasetId:'sales',categoryField:'region',categoryTarget:'categories',measures:{values:['sum','avg','ratio'][i%3]}},
    config:{code:'c01',data:{categories:[],values:[]}}};
  const document={id:'synthetic',revision:1,manifest:{filters:[],datasets:{sales:{fields:{region:{type:'string'},amount:{type:'number'},n:{type:'number'},d:{type:'number'},entity:{type:'string'}}}},metrics:definitions,components:charts},snapshot:{datasets:{}},staticFiles:{sales:['all']}};
  return {document,rows,counters,expectedSum};
}

// @wu-test type=performance | scope=静态分组查询 | protects=重复分组扫描和聚合结果错误被性能数字掩盖
async function measure(directory,mode,{rows:count,components,samples}){
  const createStaticQuery=await queryModule(directory);
  const {document,rows,counters,expectedSum}=fixture(count,components,mode==='probe');
  const timings=[];let heapUsed=0;
  for(let sample=0;sample<samples;sample++){
    Bun.gc(true);
    const source=rows.slice(),query=createStaticQuery(document,async()=>source);
    const started=performance.now(),result=await query.query({});
    timings.push(performance.now()-started);
    const chart=result.computed.components.chart0.data;
    if(chart.categories.length!==Math.min(count,20)||chart.values.reduce((a,b)=>a+b,0)!==expectedSum)throw Error('Grouped totals differ from the independently calculated input sum');
    heapUsed=Math.max(heapUsed,process.memoryUsage().heapUsed);
  }
  return {rows:count,components,samplesMs:timings,medianMs:[...timings].sort((a,b)=>a-b)[Math.floor(timings.length/2)],
    heapUsedMiB:heapUsed/1024/1024,maxRssMiB:process.resourceUsage().maxRSS/1024,...counters};
}

async function main(){
  if(process.argv[2]==='--internal-run'){
    console.log(JSON.stringify(await measure(process.argv[3],process.argv[4],JSON.parse(process.argv[5]))));return;
  }
  const config=options(process.argv.slice(2),{rows:1000000,components:24,samples:3,'probe-rows':20000}),input=await sources(config);
  try{
    const results={};
    for(const name of ['baseline','candidate'])results[name]={
      timing:worker(import.meta.url,input[name].directory,'timing',{rows:config.rows,components:config.components,samples:config.samples}),
      work:worker(import.meta.url,input[name].directory,'probe',{rows:config['probe-rows'],components:config.components,samples:1}),
    };
    await saveReport(config.output,{synthetic:true,runtime:{bun:process.versions.bun,platform:process.platform,arch:process.arch},
      scope:'First static query over already decoded rows, one source and repeated category groups; excludes network, Parquet decoding, DOM rendering and MCP.',
      cache:'Each timed query has a new row-array identity; source objects are immutable. Baseline and candidate run in separate Bun processes. Explicit GC occurs before each sample.',
      baselineRevision:input.baselineRevision,source:{baseline:input.baseline.sha256,candidate:input.candidate.sha256},results});
  }finally{await input.cleanup();}
}

if(import.meta.main)await main();
