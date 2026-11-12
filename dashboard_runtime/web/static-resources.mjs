import {createRequestQueue} from './request-queue.mjs';

// One resource owner per authorized worker pool. Query cancellation releases a
// consumer, not data still needed by another query. Both caches are bounded;
// retain decoded partitions so returning to a recent range avoids JSON work.
/** @param {{fetcher?: (url: string, init?: RequestInit) => Promise<Response>, maxBytes?: number, maxDecodedBytes?: number, concurrency?: number}} [options] */
export function createStaticResources({fetcher=fetch,maxBytes=32*1024*1024,maxDecodedBytes=64*1024*1024,concurrency=6}={}){
  const queue=createRequestQueue(concurrency),cached=new Map(),pending=new Map(),decoding=new Map(),decodedCache=new Map();
  const batches=new Map(),maxBatchBytes=16*1024*1024;
  let bytes=0,decodedBytes=0;
  function fetchResource(url,{key,headers,signal,batchUrl,size}){
    // Files larger than the bounded batch use the existing authorized GET.
    if(!batchUrl||size==null||size>maxBatchBytes)return fetcher(url,{headers,signal});
    const batchKey=JSON.stringify([batchUrl,Object.entries(headers).sort(([a],[b])=>a.localeCompare(b))]);
    let batch=batches.get(batchKey);
    if(!batch||batch.items.length===6||batch.bytes+size>maxBatchBytes){
      batch={items:[],bytes:0,controller:new AbortController()};
      batches.set(batchKey,batch);
      const current=batch;
      queueMicrotask(async()=>{
        if(batches.get(batchKey)===current)batches.delete(batchKey);
        const items=current.items.filter(item=>!item.signal.aborted);
        if(!items.length)return;
        try{
          const response=await fetcher(batchUrl,{method:'POST',
            headers:{...headers,'Content-Type':'application/json'},signal:current.controller.signal,
            body:JSON.stringify({files:items.map(item=>item.key)})});
          if(!response.ok)throw Object.assign(Error(`数据加载失败 (${response.status})`),{status:response.status});
          const body=await response.json();
          const values=items.map(item=>{
            if(typeof body.files?.[item.key]!=='string')throw Error('数据批次缺少请求的文件');
            return Uint8Array.from(atob(body.files[item.key]),char=>char.charCodeAt(0));
          });
          items.forEach((item,index)=>item.finish(item.resolve,new Response(values[index])));
        }catch(error){items.forEach(item=>item.finish(item.reject,error));}
      });
    }
    batch.bytes+=size;
    const current=batch;
    return new Promise((resolve,reject)=>{
      let settled=false;
      const item={key,signal,resolve,reject,finish:(fn,value)=>{
        if(settled)return;
        settled=true;signal.removeEventListener('abort',abort);fn(value);
      }};
      const abort=()=>{
        item.finish(reject,signal.reason);
        if(current.items.every(item=>item.signal.aborted))current.controller.abort();
      };
      current.items.push(item);
      signal.addEventListener('abort',abort,{once:true});
      if(signal.aborted)abort();
    });
  }
  function remember(key,value){
    if(value.byteLength>maxBytes)return;
    cached.set(key,value);bytes+=value.byteLength;
    while(bytes>maxBytes){
      const oldest=cached.keys().next().value;
      bytes-=cached.get(oldest).byteLength;cached.delete(oldest);
    }
  }
  function read(url,{key=url,headers={},signal,priority=0,batchUrl,size}={}){
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
        const response=await fetchResource(url,{key,headers,signal:controller.signal,batchUrl,size});
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
