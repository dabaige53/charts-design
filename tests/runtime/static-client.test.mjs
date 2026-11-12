import { test } from 'bun:test';import assert from 'node:assert/strict';import {createStaticClient,staticPartitionScope} from '../../dashboard_runtime/web/static-client.mjs';
const month=value=>({id:'period',label:'月份',field:'month',op:'in',required:true,values:[value]});
const doc={manifest:{filters:[month('2026-09')]},staticPartitions:{sales:{field:'month'}},computed:{components:{}}};
// @wu-test type=boundary | scope=static partition selection | protects=必选分区查询全部或多个分区
test('required partition cannot query all months or multiple months',()=>{
 assert.throws(()=>staticPartitionScope(doc,[]),/必须选择一项/);assert.throws(()=>staticPartitionScope(doc,[{...month('2026-09'),values:[]}]),/必须选择一项/);assert.throws(()=>staticPartitionScope(doc,[{...month('2026-09'),values:['2026-08','2026-09']}]),/必须选择一项/);
});
// @wu-test type=integration | scope=static worker lifecycle | protects=切换月份后旧数据继续响应或资源不释放 | debt=impl-detail
test('same-month queries reuse worker; switching month terminates old data owner',async()=>{
 const instances=[];class FakeWorker{constructor(){instances.push(this);this.messages=[];}postMessage(data){this.messages.push(data);queueMicrotask(()=>{if(!this.dead)this.onmessage({data:{id:data.id,result:{ready:true}}});});}terminate(){this.dead=true;}}
 const client=createStaticClient(doc,'https://site.example/document.json','./assets/worker.js',FakeWorker);
 await client.query({filters:[month('2026-09')]});await client.query({filters:[month('2026-09')]});assert.equal(instances.length,1);
 await client.query({filters:[month('2026-08')]});assert.equal(instances.length,2);assert.equal(instances[0].dead,true);assert.equal(instances[1].messages[1].args.filters[0].values[0],'2026-08');client.destroy();assert.equal(instances[1].dead,true);
});
