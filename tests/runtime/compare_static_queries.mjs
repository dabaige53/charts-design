/** Deterministic differential query check; invoke explicitly with baseline and output. */
import assert from 'node:assert/strict';
import {options,queryModule,saveReport,sources} from './benchmark_static.mjs';

// @wu-test type=integration | scope=静态查询新旧差分 | protects=优化改变指标、分组顺序、空值或表格导出语义
async function main(){
  const config=options(process.argv.slice(2),{fixtures:40,rows:200,seed:713}),input=await sources(config);
  try{
    const baseline=await queryModule(input.baseline.directory),candidate=await queryModule(input.candidate.directory);
    let state=config.seed,checked=0;
    const rand=n=>{state=(Math.imul(state,1664525)+1013904223)|0;return (state>>>0)%n;};
    for(let fixture=0;fixture<config.fixtures;fixture++){
      const choices=['A','B',null,undefined,0,'0',false,-0];
      const rows=Array.from({length:config.rows},(_,id)=>({id,g:choices[rand(choices.length)],series:choices[rand(choices.length)],v:[null,undefined,NaN,0,2,-3,7][rand(7)],n:[null,-1,0,1,2][rand(5)],d:[null,0,1,2,4][rand(5)],entity:choices[rand(choices.length)],label:choices[rand(choices.length)],date:'2026-'+String(rand(12)+1).padStart(2,'0')+'-01',unit:rand(2)?'%':'units'}));
      const metrics={sum:{aggregation:'sum',field:'v'},avg:{aggregation:'avg',field:'v'},count:{aggregation:'count'},ratio:{aggregation:'ratio',numerator:'n',denominator:'d'},entity:{aggregation:'entity_ratio',entityField:'entity',numerator:'n',denominator:'d'}};
      const components={
        native:{kind:'chart',datasetId:'sales',x:'g',series:'series',measures:['sum','avg','count','ratio','entity']},
        bar:{kind:'legacy',family:'chart',datasetId:'sales',binding:{categoryField:'g',categoryTarget:'categories',measures:{values:'sum'},orderBy:{target:'values',direction:rand(2)?'asc':'desc'}},config:{code:'c01',data:{}}},
        time:{kind:'legacy',family:'chart',datasetId:'sales',binding:{categoryField:'date',categoryTarget:'categories',measures:{values:'ratio'},timeGrain:true},config:{code:'t06',data:{}}},
        dynamic:{kind:'legacy',family:'chart',datasetId:'sales',binding:{categoryField:'g',seriesField:'series',measures:{value:'ratio',entity:'entity'},attributes:{attribute:{aggregation:'unique',field:'label'}}},config:{code:'c03',encoding:{},data:{}}},
        spark:{kind:'legacy',family:'kpi',datasetId:'sales',binding:{timeField:'g',measures:{value:'sum'}},config:{type:'mc03'}},
        kpi:{kind:'kpi',datasetId:'sales',title:'Value',measures:['avg'],config:{type:'mc03',timeField:'g'}},
        table:{kind:'table',datasetId:'sales',presentation:{columns:[{key:'id'},{key:'g'},{key:'rate'},{key:'n'},{key:'d'}],calculatedColumns:{rate:{numerator:'n',denominator:'d',unitField:'unit'}}}},
      };
      const fields=Object.fromEntries(['id','v','n','d','rate'].map(key=>[key,{type:'number'}]));
      Object.assign(fields,Object.fromEntries(['g','series','label','date','unit'].map(key=>[key,{type:'string'}])));
      const document={id:'test',revision:1,manifest:{filters:[],components,metrics,datasets:{sales:{fields}}},snapshot:{datasets:{}},staticFiles:{sales:['all']}};
      const before=baseline(structuredClone(document),async()=>rows),after=candidate(structuredClone(document),async()=>rows);
      for(const args of [
        {},{granularities:{time:'quarter'}},
        {filters:[{field:'n',op:'range',values:[0,2],componentIds:Object.keys(components)}]},
        {filters:[{field:'g',op:'in',values:['A','B'],componentIds:Object.keys(components)}]},
        {componentIds:['table'],tableStates:{table:{sortCol:'n',sortDir:'desc',page:3}}},
        {componentIds:['table'],tableStates:{table:{sortCol:'rate',sortDir:'asc',page:2}}},
        {componentIds:['table'],tableStates:{table:{keyword:'0.5'}}},
        {componentIds:['table'],export:{}},
        {detail:true,componentId:'table',offset:10,sort:[{field:'n',direction:'desc'}],search:'A'},
      ]){
        assert.deepEqual(await after.query(args),await before.query(args),JSON.stringify({fixture,args}));checked++;
      }
    }
    await saveReport(config.output,{synthetic:true,fixtures:config.fixtures,rowsPerFixture:config.rows,seed:config.seed,queriesChecked:checked,
      result:'All candidate results match the baseline',baselineRevision:input.baselineRevision,
      source:{baseline:input.baseline.sha256,candidate:input.candidate.sha256}});
  }finally{await input.cleanup();}
}

if(import.meta.main)await main();
