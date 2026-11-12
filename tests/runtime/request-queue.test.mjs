import { test } from 'bun:test';
import assert from 'node:assert/strict';
import {createRequestQueue,createToolQueue} from '../../dashboard_runtime/web/request-queue.mjs';
import {expandRecords} from '../../dashboard_runtime/web/tool-result.mjs';
// @wu-test type=behavior | scope=request queue | protects=并发超限或失败后队列阻塞 | debt=flaky
test('one budget bounds multiple callers and failures release slots',async()=>{
 const queue=createRequestQueue(4);let active=0,peak=0;
 const results=await Promise.allSettled(Array.from({length:20},(_,i)=>queue(async()=>{
  active++;peak=Math.max(peak,active);await new Promise(r=>setTimeout(r,2));active--;if(i===2)throw Error('expected');return i;
 })));
 assert.equal(peak,4);assert.equal(results.filter(r=>r.status==='fulfilled').length,19);
});
// @wu-test type=behavior | scope=tool queue | protects=慢图表请求占满队列导致版本操作无法发送
test('version actions start while four chart queries remain pending',async()=>{
 const queue=createToolQueue();let release;let started=0;
 const gate=new Promise(resolve=>{release=resolve;});
 const reads=Array.from({length:4},()=>queue('dashboard_view',async()=>{started++;await gate;}));
 await Promise.resolve();
 assert.equal(started,4);
 let controlStarted=false;
 const control=queue('dashboard_version_delete_preview',()=>{controlStarted=true;});
 await Promise.resolve();
 assert.equal(controlStarted,true);
 release();
 await Promise.all([...reads,control]);
});
// @wu-test type=behavior | scope=packed records decoding | protects=展开记录丢失Unicode零或null
test('column records preserve Unicode, zero, null and negative values',()=>{
 const value={computed:{components:{a:{data:{packedRecords:{keys:['value','label'],rows:[['西安','HO',0,null],['😀',null,-2,'机场']]}}}}}};
 const rows=expandRecords(value).computed.components.a.data.records;
 assert.deepEqual(rows,[{category:'西安',series:'HO',values:{value:0,label:null}},{category:'😀',series:null,values:{value:-2,label:'机场'}}]);
 assert.equal(expandRecords(value),value);
});
