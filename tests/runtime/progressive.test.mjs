import { test } from 'bun:test';
import assert from 'node:assert/strict';
import {createProgressiveLoader} from '../../dashboard_runtime/web/progressive.mjs';
const tick=()=>new Promise(resolve=>setTimeout(resolve,10));
// @wu-test type=behavior | scope=progressive loader | protects=旧筛选响应覆盖新结果或请求不可见组件 | debt=D9
test('visible requests only; stale filter response cannot apply',async()=>{
  const jobs=[],applied=[];const visible=new Set(['a']);
  const loader=createProgressiveLoader({delay:0,concurrency:1,visible:id=>visible.has(id),loading(){},failed(){},query:(id,seq)=>new Promise(resolve=>jobs.push({id,seq,resolve})),apply:(id,value)=>applied.push(value)});
  loader.invalidate(['a','b']);await tick();assert.equal(jobs.length,1);
  loader.invalidate(['a']);jobs[0].resolve('old');await tick();assert.deepEqual(applied,[]);
  jobs[1].resolve('new');await tick();assert.deepEqual(applied,['new']);
  visible.add('b');loader.visible();await tick();assert.equal(jobs[2].id,'b');jobs[2].resolve('b');await tick();loader.stop();
});

// @wu-test type=behavior | scope=progressive loader.loadAll | protects=屏幕外组件未加载完就报告加载完成
test('loadAll fetches offscreen components and resolves once nothing is pending',async()=>{
  const applied=[];
  const loader=createProgressiveLoader({query:async id=>id,apply:id=>applied.push(id),failed(){},visible:()=>false,loading(){},delay:0,concurrency:2});
  ['a','b','c'].forEach(id=>loader.need(id));
  await Promise.all([loader.loadAll(),loader.loadAll()]);
  assert.deepEqual(applied.sort(),['a','b','c']);
  await loader.loadAll();
  loader.stop();
});

// @wu-test type=boundary | scope=progressive loader.loadAll | protects=组件请求失败后仍允许输出缺图页面或重试后无法输出
test('loadAll rejects failed components and allows an explicit retry',async()=>{
  const failure=Error('source unavailable'),reported=[];let broken=true;
  const loader=createProgressiveLoader({query:async()=>{if(broken)throw failure;return 'ready';},apply(){},failed:(id,error)=>reported.push([id,error]),visible:()=>false,loading(){},delay:0});
  loader.need('chart');
  await assert.rejects(loader.loadAll(),error=>error instanceof AggregateError&&error.errors[0]===failure&&error.message.includes('chart'));
  assert.deepEqual(reported,[['chart',failure]]);
  await assert.rejects(loader.loadAll(),AggregateError);
  broken=false;loader.need('chart');await loader.loadAll();loader.stop();
});

// @wu-test type=boundary | scope=progressive loader.stop | protects=切换页面后旧输出请求仍报告准备完成
test('stopping the loader rejects a pending output request',async()=>{
  const loader=createProgressiveLoader({query:()=>new Promise(()=>{}),apply(){},failed(){},visible:()=>false,loading(){},delay:0});
  loader.need('chart');
  const pending=assert.rejects(loader.loadAll(),/已取消加载/);
  loader.stop();await pending;
});
