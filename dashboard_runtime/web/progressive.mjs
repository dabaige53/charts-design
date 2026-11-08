/* Component requests are independent; newer filter generations supersede older work. */
export function createProgressiveLoader({query,apply,failed,visible,loading,delay=150,concurrency=4}){
  const dirty=new Set(),active=new Map();let generation=0,timer=null,stopped=false,forced=false;const waiters=[];
  function settle(){if(stopped||(forced&&!dirty.size&&!active.size)){forced=false;waiters.splice(0).forEach(resolve=>resolve());}}
  function drain(){
    if(stopped)return settle();
    for(const id of dirty){
      if(active.size>=concurrency)break;
      if(active.has(id)||(!forced&&!visible(id)))continue;
      dirty.delete(id);const epoch=generation;active.set(id,epoch);loading(id,true);
      Promise.resolve().then(()=>query(id,epoch)).then(value=>{if(stopped)return;if(epoch===generation)apply(id,value);else dirty.add(id);}).catch(error=>{if(stopped)return;if(epoch===generation)failed(id,error);else dirty.add(id);}).finally(()=>{active.delete(id);if(stopped)return;if(!dirty.has(id))loading(id,false);drain();});
    }
    settle();
  }
  return {
    invalidate(ids){generation++;for(const id of active.keys())dirty.add(id);ids.forEach(id=>{dirty.add(id);if(visible(id))loading(id,true);});clearTimeout(timer);timer=setTimeout(drain,delay);},
    need(id){if(!active.has(id))dirty.add(id);clearTimeout(timer);timer=setTimeout(drain,delay);},
    visible:drain,
    /* Export and print need every component, including the ones never scrolled into view. */
    loadAll(){return new Promise(resolve=>{waiters.push(resolve);forced=true;drain();});},
    stop(){stopped=true;clearTimeout(timer);settle();},
  };
}
