export function staticPartitionScope(doc,filters){
  const fields=new Set([...Object.values(doc.staticPartitions||{}),...Object.values(doc.staticPartitionIndexes||{})].map(p=>p.field));
  return JSON.stringify(doc.manifest.filters.filter(f=>f.required&&fields.has(f.field)).map(required=>{
    const filter=filters.find(f=>f.id===required.id);
    if(!filter||filter.op!=='in'||filter.values.length!==1)throw Error(`${required.label||required.field}必须选择一项`);
    return [filter.id,filter.values[0]];
  }));
}
export function createStaticClient(doc,base,workerUrl,WorkerClass=Worker,headers={}){
  let worker,ready,sequence=0,activeScope,activeFilters,closed=false;const pending=new Map();
  const partitionFields=new Set([...Object.values(doc.staticPartitions||{}),...Object.values(doc.staticPartitionIndexes||{})].map(p=>p.field));
  function scopeError(){return Object.assign(Error('筛选范围已切换'),{name:'AbortError',code:'PARTITION_CHANGED'});}
  function stop(error){
    worker?.terminate();worker=null;ready=null;
    for(const task of pending.values())task.reject(error);pending.clear();
  }
  function call(type,args){const id=++sequence;return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});worker.postMessage({id,type,args});});}
  function start(){
    if(ready)return ready;
    worker=new WorkerClass(new URL(workerUrl,base),{type:'module'});
    const current=worker;
    worker.onmessage=({data})=>{
      if(worker!==current)return;
      const task=pending.get(data.id);if(!task)return;pending.delete(data.id);
      if(data.error)task.reject(Error(data.error));else task.resolve(data.result);
    };
    worker.onerror=event=>{if(worker===current)stop(Error(event.message||'后台计算失败'));};
    const {computed,...definition}=doc;
    ready=call('init',{document:definition,base,headers}).catch(error=>{
      if(worker===current)stop(error);
      throw error;
    });return ready;
  }
  function relevantScope(filters,args){
    if(args.filterId)return '';
    const ids=args.componentIds||(args.detail?[args.componentId]:null);
    return JSON.stringify(filters.filter(f=>f.required&&partitionFields.has(f.field)&&
      (!ids||!f.componentIds||f.componentIds.some(id=>ids.includes(id)))).map(f=>[f.id,f.values]));
  }
  return {async query(args){
    if(closed)throw Object.assign(Error('页面已关闭'),{name:'AbortError'});
    const filters=args.filters||doc.manifest.filters;
    if(!args.filterId){
      const scope=staticPartitionScope(doc,filters);
      if(activeScope!==undefined&&scope!==activeScope)stop(scopeError());
      activeScope=scope;activeFilters=filters;
    }
    const requested=relevantScope(filters,args);
    for(;;){
      try{
        await start();
        if(closed)throw Object.assign(Error('页面已关闭'),{name:'AbortError'});
        if(activeFilters&&requested!==relevantScope(activeFilters,args))throw scopeError();
        return await call('query',args);
      }catch(error){
        if(closed||error.code!=='PARTITION_CHANGED'||requested!==relevantScope(activeFilters,args))throw error;
        // A partition restart also interrupts unrelated components/options.
        // Only replay requests whose own data selection is still current.
      }
    }
  },destroy(){closed=true;stop(Object.assign(Error('页面已关闭'),{name:'AbortError'}));}};
}
