export function staticPartitionScope(doc,filters){
  const fields=new Set(Object.values(doc.staticPartitions||{}).map(p=>p.field));
  return JSON.stringify(doc.manifest.filters.filter(f=>f.required&&fields.has(f.field)).map(required=>{
    const filter=filters.find(f=>f.id===required.id);
    if(!filter||filter.op!=='in'||filter.values.length!==1)throw Error(`${required.label||required.field}必须选择一项`);
    return [filter.id,filter.values[0]];
  }));
}
export function createStaticClient(doc,base,workerUrl,WorkerClass=Worker){
  let worker,ready,sequence=0,activeScope;const pending=new Map();
  function stop(message){worker?.terminate();worker=null;ready=null;for(const task of pending.values())task.reject(Object.assign(Error(message),{name:'AbortError'}));pending.clear();}
  function call(type,args){const id=++sequence;return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});worker.postMessage({id,type,args});});}
  function start(){
    if(ready)return ready;
    worker=new WorkerClass(new URL(workerUrl,base),{type:'module'});
    worker.onmessage=({data})=>{const task=pending.get(data.id);if(!task)return;pending.delete(data.id);if(data.error)task.reject(Error(data.error));else task.resolve(data.result);};
    worker.onerror=event=>{for(const task of pending.values())task.reject(Error(event.message||'后台计算失败'));pending.clear();};
    const {computed,...definition}=doc;
    ready=call('init',{document:definition,base});return ready;
  }
  return {async query(args){
    const scope=staticPartitionScope(doc,args.filters||doc.manifest.filters);
    if(activeScope!==undefined&&scope!==activeScope)stop('月份已切换');activeScope=scope;
    await start();if(scope!==activeScope)throw Object.assign(Error('月份已切换'),{name:'AbortError'});
    return call('query',args);
  },destroy(){stop('页面已关闭');}};
}
