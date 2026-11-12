import {test} from 'bun:test';
import assert from 'node:assert/strict';
import {createStaticResources} from '../../dashboard_runtime/web/static-resources.mjs';
const tick=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
// @wu-test type=performance | scope=static resources | protects=相同资源并发重复下载或条件切换后丢失可复用内容
test('deduplicates concurrent reads and reuses immutable bytes with a bounded LRU',async()=>{
 const calls=[];
 const resources=createStaticResources({maxBytes:6,fetcher:async url=>{calls.push(url);return new Response('abc');}});
 await Promise.all([resources.read('A'),resources.read('A')]);
 await resources.read('B');await resources.read('A');await resources.read('C');await resources.read('B');
 assert.deepEqual(calls,['A','B','C','B']);
});
// @wu-test type=integration | scope=static resources cancellation | protects=取消一个查询中断其他消费者且排队旧请求继续下载
test('cancellation releases only its consumer and removes queued orphan requests',async()=>{
 const calls=[],releases=[];
 const resources=createStaticResources({concurrency:1,fetcher:url=>{calls.push(url);return new Promise(resolve=>releases.push(()=>resolve(new Response('ok'))));}});
 const cancelled=new AbortController(),queued=new AbortController();
 const first=resources.read('shared',{signal:cancelled.signal});
 const firstRejected=assert.rejects(first,{name:'AbortError'});
 const second=resources.read('shared');
 const obsolete=assert.rejects(resources.read('obsolete',{signal:queued.signal}),{name:'AbortError'});
 await tick();cancelled.abort();queued.abort();releases[0]();
 await firstRejected;await obsolete;assert.equal(new TextDecoder().decode(await second),'ok');
 await tick();assert.deepEqual(calls,['shared']);
});
// @wu-test type=boundary | scope=static resource errors | protects=失败缓存永久阻断重试或权限失败被当成成功数据
test('failed resources are retried and never returned as cached data',async()=>{
 let calls=0;
 const resources=createStaticResources({fetcher:async()=>new Response('[]',{status:++calls===1?403:200})});
 await assert.rejects(resources.json('https://example.test/data.json'),/403/);
 assert.deepEqual(await resources.json('https://example.test/data.json'),[]);assert.equal(calls,2);
});

// @wu-test type=performance | scope=decoded resource cache | protects=切回已加载范围重复解压解析或解析缓存无限增长
test('retains decoded values across reads and evicts least recently used values within the budget',async()=>{
 let downloads=0;
 const resources=createStaticResources({maxDecodedBytes:24,fetcher:async()=>{downloads++;return new Response('[1]');}});
 const a=await resources.json('https://example.test/a');
 const b=await resources.json('https://example.test/b');
 assert.equal(await resources.json('https://example.test/a'),a);
 await resources.json('https://example.test/c');
 assert.equal(await resources.json('https://example.test/a'),a);
 assert.notEqual(await resources.json('https://example.test/b'),b);
 assert.equal(downloads,3);
 const cancelled=new AbortController();cancelled.abort();
 await assert.rejects(resources.json('https://example.test/b',{signal:cancelled.signal}),{name:'AbortError'});
});
