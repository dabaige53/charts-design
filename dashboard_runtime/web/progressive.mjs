/* Component requests are independent; newer filter generations supersede older work. */
export function createProgressiveLoader({query,apply,failed,visible,loading,delay=150,concurrency=4}){
  const dirty=new Set(),active=new Map(),errors=new Map();let generation=0,timer=null,stopped=false,forced=false;const waiters=[];
  function settle(){
    if(!stopped&&(!forced||dirty.size||active.size))return;
    forced=false;
    const error=stopped?Error('页面已切换，已取消加载'):errors.size?new AggregateError([...errors.values()],'组件加载失败：'+[...errors.keys()].join('、')):null;
    for(const waiter of waiters.splice(0))if(error)waiter.reject(error);else waiter.resolve();
  }
  function drain(){
    if(stopped)return settle();
    for(const id of dirty){
      if(active.size>=concurrency)break;
      if(active.has(id)||(!forced&&!visible(id)))continue;
      dirty.delete(id);const epoch=generation;active.set(id,epoch);loading(id,true);
      Promise.resolve().then(()=>query(id,epoch)).then(value=>{if(stopped)return;if(epoch===generation){errors.delete(id);apply(id,value);}else dirty.add(id);}).catch(error=>{if(stopped)return;if(epoch===generation){errors.set(id,error);failed(id,error);}else dirty.add(id);}).finally(()=>{active.delete(id);if(stopped)return;if(!dirty.has(id))loading(id,false);drain();});
    }
    settle();
  }
  return {
    invalidate(ids){generation++;for(const id of active.keys())dirty.add(id);ids.forEach(id=>{errors.delete(id);dirty.add(id);if(visible(id))loading(id,true);});clearTimeout(timer);timer=setTimeout(drain,delay);},
    need(id){errors.delete(id);if(!active.has(id))dirty.add(id);clearTimeout(timer);timer=setTimeout(drain,delay);},
    visible:drain,
    /* Export and print need every component, including the ones never scrolled into view. */
    loadAll(){clearTimeout(timer);return new Promise((resolve,reject)=>{waiters.push({resolve,reject});forced=true;drain();});},
    isReady(){return !stopped&&!dirty.size&&!active.size&&!errors.size;},
    stop(){stopped=true;clearTimeout(timer);settle();},
  };
}
