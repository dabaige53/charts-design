export function staticPartitionScope(doc,filters){
  const fields=new Set([...Object.values(doc.staticPartitions||{}),...Object.values(doc.staticPartitionIndexes||{})].map(p=>p.field));
  return JSON.stringify(doc.manifest.filters.filter(f=>f.required&&fields.has(f.field)).map(required=>{
    const filter=filters.find(f=>f.id===required.id);
    if(!filter||filter.op!=='in'||filter.values.length!==1)throw Error(`${required.label||required.field}必须选择一项`);
    return [filter.id,filter.values[0]];
  }));
}
const pools=new WeakMap();
let clientSequence=0;
const aborted=message=>Object.assign(Error(message),{name:'AbortError'});
// A pool is scoped to the worker location and authorization headers. Independent
// share roots and different online credentials never share downloaded resources.
export function createStaticClient(doc,base,workerUrl,WorkerClass=Worker,headers={}){
  const url=new URL(workerUrl,base).href;
  const key=JSON.stringify([url,Object.entries(headers).sort(([a],[b])=>a.localeCompare(b))]);
  let group=pools.get(WorkerClass);
  if(!group){group=new Map();pools.set(WorkerClass,group);}
  let pool=group.get(key);
  if(!pool){pool={worker:null,sequence:0,pending:new Map(),owners:new Map()};group.set(key,pool);}
  const owner={id:++clientSequence,ready:null};pool.owners.set(owner.id,owner);
  let activeFilters,closed=false;
  function relevant(filters,args){
    if(args.filterId)return '';
    const ids=args.componentIds||(args.detail?[args.componentId]:null);
    return JSON.stringify(filters.filter(f=>!ids||!f.componentIds||f.componentIds.some(id=>ids.includes(id)))
      .map(f=>[f.id,f.field,f.op,f.values]));
  }
  function obsolete(filters,args){
    if(args.filterId)return false;
    const before=args.filters||doc.manifest.filters;
    const ids=args.componentIds||(args.detail?[args.componentId]:null);
    // A batch can still contain consumers unaffected by the new selection.
    // Keep that response; the UI applies its per-consumer generation checks.
    return ids?.length?ids.every(id=>relevant(before,{componentIds:[id]})!==relevant(filters,{componentIds:[id]}))
      :relevant(before,args)!==relevant(filters,args);
  }
  function cancel(id,task,error){
    pool.pending.delete(id);pool.worker?.postMessage({type:'cancel',id});task.reject(error);
  }
  function send(type,args,signal){
    const id=++pool.sequence;
    return new Promise((resolve,reject)=>{
      signal?.throwIfAborted();
      const abort=()=>cancel(id,task,signal.reason);
      const finish=(fn,value)=>{signal?.removeEventListener('abort',abort);fn(value);};
      const task={owner:owner.id,resolve:value=>finish(resolve,value),reject:error=>finish(reject,error),args,type};
      pool.pending.set(id,task);
      signal?.addEventListener('abort',abort,{once:true});
      pool.worker.postMessage({client:owner.id,id,type,args});
    });
  }
  function start(){
    if(pool.denied)throw pool.denied;
    if(owner.ready)return owner.ready;
    if(!pool.worker){
      const current=pool.worker=new WorkerClass(url,{type:'module'});
      current.onmessage=({data})=>{
        if(pool.worker!==current)return;
        if([401,403,410].includes(data.status)){
          pool.denied=Error(data.error);
          for(const task of pool.pending.values())task.reject(pool.denied);
          pool.pending.clear();current.terminate();pool.worker=null;
          return;
        }
        const task=pool.pending.get(data.id);if(!task)return;pool.pending.delete(data.id);
        if(data.error)task.reject(Object.assign(Error(data.error),{name:data.errorName||'Error'}));
        else task.resolve(data.result);
      };
      current.onerror=event=>{
        if(pool.worker!==current)return;
        current.terminate();pool.worker=null;
        for(const task of pool.pending.values())task.reject(Error(event.message||'后台计算失败'));
        pool.pending.clear();for(const item of pool.owners.values())item.ready=null;
      };
    }
    const {computed,...definition}=doc;
    owner.ready=send('init',{document:definition,base,headers}).catch(error=>{owner.ready=null;throw error;});
    return owner.ready;
  }
  return {async query(args,{signal}={}){
    signal?.throwIfAborted();
    if(closed)throw aborted('页面已关闭');
    const filters=args.filters||doc.manifest.filters;
    if(!args.filterId){
      staticPartitionScope(doc,filters);
      activeFilters=filters;
      for(const [id,task]of pool.pending){
        if(task.owner===owner.id&&task.type==='query'&&obsolete(filters,task.args))
          cancel(id,task,aborted('筛选范围已切换'));
      }
    }
    await start();
    signal?.throwIfAborted();
    if(closed)throw aborted('页面已关闭');
    if(activeFilters&&obsolete(activeFilters,args))throw aborted('筛选范围已切换');
    return send('query',args,signal);
  },destroy(){
    closed=true;
    for(const [id,task]of pool.pending)if(task.owner===owner.id)cancel(id,task,aborted('页面已关闭'));
    pool.worker?.postMessage({type:'dispose',client:owner.id});pool.owners.delete(owner.id);
    if(!pool.owners.size){pool.worker?.terminate();pool.worker=null;group.delete(key);}
  }};
}
