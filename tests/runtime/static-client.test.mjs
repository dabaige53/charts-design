import { test } from 'bun:test';import assert from 'node:assert/strict';import {createStaticClient,staticPartitionScope} from '../../dashboard_runtime/web/static-client.mjs';
import {createStaticQuery} from '../../dashboard_runtime/web/static-query.mjs';
const month=value=>({id:'period',label:'月份',field:'month',op:'in',required:true,values:[value]});
const doc={manifest:{filters:[month('2026-09')]},staticPartitions:{sales:{field:'month'}},computed:{components:{}}};
// @wu-test type=boundary | scope=static partition selection | protects=必选分区查询全部或多个分区
test('required partition cannot query all months or multiple months',()=>{
 assert.throws(()=>staticPartitionScope(doc,[]),/必须选择一项/);assert.throws(()=>staticPartitionScope(doc,[{...month('2026-09'),values:[]}]),/必须选择一项/);assert.throws(()=>staticPartitionScope(doc,[{...month('2026-09'),values:['2026-08','2026-09']}]),/必须选择一项/);
 assert.throws(()=>staticPartitionScope(doc,[{...month('2026-09'),op:'range',values:['2026-08','2026-09']}]),/必须选择一项/);
});
// @wu-test type=integration | scope=static worker lifecycle | protects=切换月份后旧数据继续响应或资源不释放 | debt=impl-detail
test('same-month queries reuse worker; switching month terminates old data owner',async()=>{
 const instances=[];class FakeWorker{constructor(){instances.push(this);this.messages=[];}postMessage(data){this.messages.push(data);queueMicrotask(()=>{if(!this.dead)this.onmessage({data:{id:data.id,result:{ready:true}}});});}terminate(){this.dead=true;}}
 const client=createStaticClient(doc,'https://site.example/document.json','./assets/worker.js',FakeWorker);
 await client.query({filters:[month('2026-09')]});await client.query({filters:[month('2026-09')]});assert.equal(instances.length,1);
 await client.query({filters:[month('2026-08')]});assert.equal(instances.length,2);assert.equal(instances[0].dead,true);assert.equal(instances[1].messages[1].args.filters[0].values[0],'2026-08');client.destroy();assert.equal(instances[1].dead,true);
});

// @wu-test type=regression | scope=static client filter options | protects=防止 required-month-20261112 复发：必选月份为空时无法读取候选项恢复且选项请求重置当前月份
test('required month options load without a selection and preserve the active data worker',async()=>{
 const reads=[],instances=[];
 const definition={...doc,manifest:{...doc.manifest,filters:[{...month('2026-09'),componentIds:['table']}],components:{table:{kind:'table',datasetId:'sales'}},datasets:{sales:{fields:{month:{type:'string'}}}}},
   snapshot:{datasets:{}},staticFiles:{sales:['rows']},staticOptions:{sales:{month:'months'}}};
 class Worker{
   constructor(){instances.push(this);}
   postMessage({id,type,args}){
     Promise.resolve().then(async()=>{
       if(type==='init'){this.engine=createStaticQuery(args.document,async file=>{reads.push(file);return ['2026-08','2026-09'];});return {ready:true};}
       return this.engine.query(args);
     }).then(result=>this.onmessage({data:{id,result}}),error=>this.onmessage({data:{id,error:error.message}}));
   }
   terminate(){this.dead=true;}
 }
 const client=createStaticClient(definition,'https://site.example/document.json','./worker.js',Worker);
 try{
   await assert.rejects(client.query({filters:[],componentIds:[]}),/必须选择一项/);
   const result=await client.query({filterId:'period',filters:[]});
   assert.deepEqual(result.values,['2026-08','2026-09']);
   assert.deepEqual(reads,['months']);
   await client.query({filters:[month('2026-09')],componentIds:[]});
   assert.deepEqual((await client.query({filterId:'period',filters:[],search:'08'})).values,['2026-08']);
   assert.equal(instances.length,1);
   assert.ok(!instances[0].dead);
 }finally{client.destroy();}
});
