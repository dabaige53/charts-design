import { test } from 'bun:test';import assert from 'node:assert/strict';import {createStaticClient,staticPartitionScope} from '../../dashboard_runtime/web/static-client.mjs';
import {createStaticQuery} from '../../dashboard_runtime/web/static-query.mjs';
const month=value=>({id:'period',label:'月份',field:'month',op:'in',required:true,values:[value]});
const doc={manifest:{filters:[month('2026-09')]},staticPartitions:{sales:{field:'month'}},computed:{components:{}}};
// @wu-test type=boundary | scope=static partition selection | protects=必选分区查询全部或多个分区
test('required partition cannot query all months or multiple months',()=>{
 assert.throws(()=>staticPartitionScope(doc,[]),/必须选择一项/);assert.throws(()=>staticPartitionScope(doc,[{...month('2026-09'),values:[]}]),/必须选择一项/);assert.throws(()=>staticPartitionScope(doc,[{...month('2026-09'),values:['2026-08','2026-09']}]),/必须选择一项/);
 assert.throws(()=>staticPartitionScope(doc,[{...month('2026-09'),op:'range',values:['2026-08','2026-09']}]),/必须选择一项/);
});
// @wu-test type=integration | scope=static worker lifecycle | protects=切换任意分区时销毁共享资源或关闭一个读取器影响其他读取器
test('partition changes preserve the worker and readers share its authorized lifetime',async()=>{
 const instances=[];class FakeWorker{constructor(){instances.push(this);this.messages=[];}postMessage(data){this.messages.push(data);if(!['init','query'].includes(data.type))return;queueMicrotask(()=>{if(!this.dead)this.onmessage({data:{id:data.id,result:{ready:true}}});});}terminate(){this.dead=true;}}
 const definition={manifest:{filters:[{id:'segment',field:'segment',op:'in',values:['A'],required:true}]},staticPartitions:{sales:{field:'segment'}}};
 const client=createStaticClient(definition,'https://site.example/document.json','./assets/worker.js',FakeWorker);
 const other=createStaticClient(definition,'https://site.example/other.json','./assets/worker.js',FakeWorker);
 await client.query({});await client.query({filters:[{...definition.manifest.filters[0],values:['B']}]});await other.query({});
 assert.equal(instances.length,1);client.destroy();assert.ok(!instances[0].dead);
 await other.query({});other.destroy();assert.equal(instances[0].dead,true);
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

// @wu-test type=regression | scope=static worker recovery | protects=防止 audit-4 复发：初始化失败后重试仍复用失败线程
test('a failed worker initialization can be retried with a new worker',async()=>{
 const instances=[];
 class Worker{
   constructor(){instances.push(this);}
   postMessage({id}){queueMicrotask(()=>{
     if(instances.length===1)this.onerror({message:'load failed'});
     else this.onmessage({data:{id,result:{ok:true}}});
   });}
   terminate(){this.dead=true;}
 }
 const client=createStaticClient(doc,'https://site.example/','worker.js',Worker);
 try{
   await assert.rejects(client.query({componentIds:[]}),/load failed/);
   assert.deepEqual(await client.query({componentIds:[]}),{ok:true});
   assert.equal(instances.length,2);assert.equal(instances[0].dead,true);
 }finally{client.destroy();}
});

// @wu-test type=regression | scope=static query cancellation | protects=防止 audit-5 复发：条件变化中断无关查询或旧结果覆盖当前选择
test('query changes cancel only stale consumers without replaying unrelated work',async()=>{
 const instances=[];
 const selection=value=>({id:'area',field:'area',op:'in',values:[value],componentIds:['affected']});
 const definition={manifest:{filters:[selection('A')]}};
 class Worker{
   constructor(){instances.push(this);this.messages=[];}
   postMessage(message){this.messages.push(message);if(message.type==='init')queueMicrotask(()=>this.finish(message));}
   finish(message){this.onmessage({data:{id:message.id,result:{componentIds:message.args?.componentIds}}});}
   terminate(){this.dead=true;}
 }
 const client=createStaticClient(definition,'https://site.example/','worker.js',Worker);
 try{
   const unrelated=client.query({componentIds:['other']});
   const mixed=client.query({componentIds:['affected','other']});
   const options=client.query({filterId:'area'});
   const stale=assert.rejects(client.query({componentIds:['affected']}),{name:'AbortError'});
   for(let i=0;i<5;i++)await Promise.resolve();
   const latest=client.query({filters:[selection('B')],componentIds:['affected']});
   for(let i=0;i<5;i++)await Promise.resolve();
   const worker=instances[0];
   for(const message of worker.messages.filter(m=>m.type==='query'))worker.finish(message);
   assert.deepEqual((await unrelated).componentIds,['other']);await options;await stale;await latest;
   assert.deepEqual((await mixed).componentIds,['affected','other']);
   assert.equal(instances.length,1);
   assert.equal(worker.messages.filter(m=>m.type==='query'&&m.args.componentIds?.[0]==='other').length,1);
 }finally{client.destroy();}
 await assert.rejects(client.query({componentIds:['other']}),/页面已关闭/);
});

// @wu-test type=boundary | scope=static client authorization | protects=服务端确认权限失效后仍从共享缓存返回数据
test('a denied resource invalidates all readers in its authorization pool',async()=>{
 const instances=[];
 class Worker{
  constructor(){instances.push(this);}
  postMessage(message){
   if(message.type==='init')queueMicrotask(()=>this.onmessage({data:{id:message.id,result:{ready:true}}}));
   if(message.type==='query')queueMicrotask(()=>this.onmessage({data:{id:message.id,error:'access revoked',status:403}}));
  }
  terminate(){this.dead=true;}
 }
 const definition={manifest:{filters:[]}};
 const first=createStaticClient(definition,'https://site.example/','worker.js',Worker);
 const second=createStaticClient(definition,'https://site.example/','worker.js',Worker);
 try{
  await assert.rejects(first.query({componentIds:['card']}),/access revoked/);
  await assert.rejects(second.query({componentIds:['card']}),/access revoked/);
  assert.equal(instances.length,1);
  assert.equal(instances[0].dead,true);
 }finally{first.destroy();second.destroy();}
});

// @wu-test type=integration | scope=static client AbortSignal | protects=界面取消旧查询后仍占据请求名额直到Worker计算完成
test('an external abort immediately releases a pending worker query',async()=>{
 const messages=[];
 class Worker{
  postMessage(message){messages.push(message);if(message.type==='init')queueMicrotask(()=>this.onmessage({data:{id:message.id,result:{ready:true}}}));}
  terminate(){}
 }
 const client=createStaticClient({manifest:{filters:[]}},'https://site.example/','worker.js',Worker);
 const controller=new AbortController();
 try{
  const pending=assert.rejects(client.query({componentIds:['card']},{signal:controller.signal}),{name:'AbortError'});
  for(let i=0;i<5;i++)await Promise.resolve();
  const request=messages.find(message=>message.type==='query');assert.ok(request);
  controller.abort();await pending;
  assert.ok(messages.some(message=>message.type==='cancel'&&message.id===request.id));
  assert.equal('signal' in request.args,false);
 }finally{client.destroy();}
});
