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

// @wu-test type=performance | scope=static resources batches | protects=同轮数据分片逐个请求重复鉴权或重读已缓存数据
test('groups file reads into one authorized request and retains individual cache entries',async()=>{
 const calls=[];
 const resources=createStaticResources({fetcher:async(url,init)=>{
   calls.push({url,init});
   const {files}=JSON.parse(init.body);
   return Response.json({files:Object.fromEntries(files.map(key=>[key,btoa('[1,2]')]))});
 }});
 const options={batchUrl:'https://example.test/content/board/1',headers:{Authorization:'Bearer reader'},size:5};
 const [a,b]=await Promise.all([
   resources.json('https://example.test/a.json',{...options,key:'object/a.json'}),
   resources.json('https://example.test/b.json',{...options,key:'object/b.json'}),
 ]);
 assert.deepEqual(a,[1,2]);assert.deepEqual(b,[1,2]);
 assert.equal(calls.length,1);assert.equal(calls[0].init.method,'POST');
 assert.equal(calls[0].init.headers.Authorization,'Bearer reader');
 assert.deepEqual(JSON.parse(calls[0].init.body).files,['object/a.json','object/b.json']);
 assert.equal(await resources.json('https://example.test/a.json',{...options,key:'object/a.json'}),a);
 assert.equal(calls.length,1);
});

// @wu-test type=boundary | scope=static resources batch isolation | protects=取消单个文件中断共享批次或不同版本和凭据混用授权请求
test('isolates batch endpoints and credentials and cancels only abandoned batches',async()=>{
 const calls=[],releases=[];
 const resources=createStaticResources({fetcher:(url,init)=>{
   calls.push({url,init});
   return new Promise(resolve=>releases.push(()=>resolve(Response.json({
     files:Object.fromEntries(JSON.parse(init.body).files.map(key=>[key,btoa('[]')]))
   }))));
 }});
 const options={batchUrl:'https://example.test/one',size:2};
 const controller=new AbortController();
 const cancelled=assert.rejects(resources.read('a',{...options,signal:controller.signal}),{name:'AbortError'});
 const retained=resources.read('b',options);
 const otherVersion=resources.read('c',{...options,batchUrl:'https://example.test/two'});
 const otherCredential=resources.read('d',{...options,headers:{Authorization:'other'}});
 await tick();controller.abort();
 assert.equal(calls.length,3);assert.equal(calls[0].init.signal.aborted,false);
 releases.forEach(release=>release());
 await cancelled;await Promise.all([retained,otherVersion,otherCredential]);
});

// @wu-test type=boundary | scope=static resources batch size and errors | protects=批次超过容量或部分响应被当作完整数据缓存
test('splits batches by byte budget and rejects incomplete responses without caching',async()=>{
 const calls=[];
 let incomplete=true;
 const resources=createStaticResources({fetcher:async(url,init)=>{
   calls.push({url,init});
   const {files}=JSON.parse(init.body);
   return Response.json({files:incomplete?{}:Object.fromEntries(files.map(key=>[key,btoa('[]')]))});
 }});
 const options={batchUrl:'https://example.test/batch',size:10*1024*1024};
 await Promise.all(['a','b'].map(url=>assert.rejects(resources.read(url,options),/缺少请求的文件/)));
 assert.equal(calls.length,2);
 incomplete=false;
 assert.equal(new TextDecoder().decode(await resources.read('a',options)),'[]');
 assert.equal(calls.length,3);
});

// @wu-test type=boundary | scope=static batch lifecycle | protects=整批取消后网络仍运行或权限失败后缓存错误结果
test('aborts a fully abandoned batch and permits retry after an authorization failure',async()=>{
 let signal,calls=0;
 const resources=createStaticResources({fetcher:async(_url,init)=>{
   calls++;
   if(calls===1){
     signal=init.signal;
     return new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(signal.reason),{once:true}));
   }
   if(calls===2)return new Response('',{status:401});
   return Response.json({files:{a:btoa('[]')}});
 }});
 const options={batchUrl:'https://example.test/batch',size:2};
 const controller=new AbortController();
 const cancelled=assert.rejects(resources.read('a',{...options,signal:controller.signal}),{name:'AbortError'});
 await tick();controller.abort();await cancelled;
 assert.equal(signal.aborted,true);
 await tick();
 await assert.rejects(resources.read('a',options),error=>error.status===401);
 assert.equal(new TextDecoder().decode(await resources.read('a',options)),'[]');
 assert.equal(calls,3);
});
