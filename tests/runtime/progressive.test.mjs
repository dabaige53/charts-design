import test from 'node:test';
import assert from 'node:assert/strict';
import {createProgressiveLoader} from '../../dashboard_runtime/web/progressive.mjs';
const tick=()=>new Promise(resolve=>setTimeout(resolve,10));
test('visible requests only; stale filter response cannot apply',async()=>{
  const jobs=[],applied=[];const visible=new Set(['a']);
  const loader=createProgressiveLoader({delay:0,concurrency:1,visible:id=>visible.has(id),loading(){},failed(){},query:(id,seq)=>new Promise(resolve=>jobs.push({id,seq,resolve})),apply:(id,value)=>applied.push(value)});
  loader.invalidate(['a','b']);await tick();assert.equal(jobs.length,1);
  loader.invalidate(['a']);jobs[0].resolve('old');await tick();assert.deepEqual(applied,[]);
  jobs[1].resolve('new');await tick();assert.deepEqual(applied,['new']);
  visible.add('b');loader.visible();await tick();assert.equal(jobs[2].id,'b');jobs[2].resolve('b');await tick();loader.stop();
});
