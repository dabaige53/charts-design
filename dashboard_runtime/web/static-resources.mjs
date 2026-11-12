import {createRequestQueue} from './request-queue.mjs';

// One resource owner per authorized worker pool. Query cancellation releases a
// consumer, not data still needed by another query. Both caches are bounded;
// retain decoded partitions so returning to a recent range avoids JSON work.
/** @param {{fetcher?: (url: string, init?: RequestInit) => Promise<Response>, maxBytes?: number, maxDecodedBytes?: number, concurrency?: number}} [options] */
export function createStaticResources({fetcher=fetch,maxBytes=32*1024*1024,maxDecodedBytes=64*1024*1024,concurrency=6}={}){
  const queue=createRequestQueue(concurrency),cached=new Map(),pending=new Map(),decoding=new Map(),decodedCache=new Map();
  let bytes=0,decodedBytes=0;
  function remember(key,value){
    if(value.byteLength>maxBytes)return;
    cached.set(key,value);bytes+=value.byteLength;
    while(bytes>maxBytes){
      const oldest=cached.keys().next().value;
      bytes-=cached.get(oldest).byteLength;cached.delete(oldest);
    }
  }
  function read(url,{key=url,headers={},signal,priority=0}={}){
    signal?.throwIfAborted();
    if(cached.has(key)){
      const value=cached.get(key);cached.delete(key);cached.set(key,value);
      return Promise.resolve(value);
    }
    let entry=pending.get(key);
    if(!entry){
      const controller=new AbortController();
      entry={controller,consumers:0};
      entry.promise=queue(async()=>{
        const response=await fetcher(url,{headers,signal:controller.signal});
        if(!response.ok)throw Object.assign(Error(`数据加载失败 (${response.status})`),{status:response.status});
        const value=await response.arrayBuffer();
        controller.signal.throwIfAborted();
        remember(key,value);return value;
      },{signal:controller.signal,priority}).finally(()=>{
        if(pending.get(key)===entry)pending.delete(key);
      });
      pending.set(key,entry);
    }
    entry.consumers++;
    return new Promise((resolve,reject)=>{
      let settled=false;
      const finish=(fn,value)=>{
        if(settled)return;settled=true;
        signal?.removeEventListener('abort',abort);
        entry.consumers--;
        if(!entry.consumers&&pending.get(key)===entry){
          pending.delete(key);entry.controller.abort();
        }
        fn(value);
      };
      const abort=()=>finish(reject,signal.reason);
      signal?.addEventListener('abort',abort,{once:true});
      entry.promise.then(value=>finish(resolve,value),error=>finish(reject,error));
    });
  }
  return {read,async json(url,options){
    options?.signal?.throwIfAborted();
    const key=options?.key||url;
    if(decodedCache.has(key)){
      const entry=decodedCache.get(key);decodedCache.delete(key);decodedCache.set(key,entry);
      return entry.value;
    }
    const value=await read(url,options);
    options?.signal?.throwIfAborted();
    // A concurrent reader may have completed decoding while this one awaited bytes.
    if(decodedCache.has(key))return decodedCache.get(key).value;
    let decoded=decoding.get(key);
    if(!decoded){
      const response=new Response(value);
      decoded=(new URL(url).pathname.endsWith('.gz')
        ?new Response(response.body.pipeThrough(new DecompressionStream('gzip'))):response).text()
        .then(text=>{
          const value=JSON.parse(text),size=text.length*4;
          // An estimate for strings, objects and arrays, not a JS heap measurement.
          if(size<=maxDecodedBytes){
            decodedCache.set(key,{value,size});decodedBytes+=size;
            while(decodedBytes>maxDecodedBytes){
              const oldest=decodedCache.keys().next().value;
              decodedBytes-=decodedCache.get(oldest).size;decodedCache.delete(oldest);
            }
          }
          return value;
        })
        .finally(()=>{if(decoding.get(key)===decoded)decoding.delete(key);});
      decoding.set(key,decoded);
    }
    const result=await decoded;
    options?.signal?.throwIfAborted();
    return result;
  }};
}
