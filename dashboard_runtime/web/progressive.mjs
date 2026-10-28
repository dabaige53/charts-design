/* Component requests are independent; newer filter generations supersede older work. */
export function createProgressiveLoader({query,apply,failed,visible,loading,delay=150,concurrency=4}){
  const dirty=new Set(),active=new Map();let generation=0,timer=null,stopped=false;
  function drain(){
    if(stopped)return;
    for(const id of dirty){
      if(active.size>=concurrency)break;
      if(active.has(id)||!visible(id))continue;
      dirty.delete(id);const epoch=generation;active.set(id,epoch);loading(id,true);
      Promise.resolve().then(()=>query(id,epoch)).then(value=>{if(epoch===generation)apply(id,value);else dirty.add(id);}).catch(error=>{if(epoch===generation)failed(id,error);else dirty.add(id);}).finally(()=>{active.delete(id);loading(id,false);drain();});
    }
  }
  return {
    invalidate(ids){generation++;for(const id of active.keys())dirty.add(id);ids.forEach(id=>{dirty.add(id);if(visible(id))loading(id,true);});clearTimeout(timer);timer=setTimeout(drain,delay);},
    need(id){if(!active.has(id))dirty.add(id);clearTimeout(timer);timer=setTimeout(drain,delay);},
    visible:drain,
    stop(){stopped=true;clearTimeout(timer);},
  };
}
