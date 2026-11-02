import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequestQueue} from '../../dashboard_runtime/web/request-queue.mjs';
import {expandRecords} from '../../dashboard_runtime/web/tool-result.mjs';
test('one budget bounds multiple callers and failures release slots',async()=>{
 const queue=createRequestQueue(4);let active=0,peak=0;
 const results=await Promise.allSettled(Array.from({length:20},(_,i)=>queue(async()=>{
  active++;peak=Math.max(peak,active);await new Promise(r=>setTimeout(r,2));active--;if(i===2)throw Error('expected');return i;
 })));
 assert.equal(peak,4);assert.equal(results.filter(r=>r.status==='fulfilled').length,19);
});
test('column records preserve Unicode, zero, null and negative values',()=>{
 const value={computed:{components:{a:{data:{packedRecords:{keys:['value','label'],rows:[['西安','HO',0,null],['😀',null,-2,'机场']]}}}}}};
 const rows=expandRecords(value).computed.components.a.data.records;
 assert.deepEqual(rows,[{category:'西安',series:'HO',values:{value:0,label:null}},{category:'😀',series:null,values:{value:-2,label:'机场'}}]);
 assert.equal(expandRecords(value),value);
});
