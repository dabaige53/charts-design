/* Bounded scheduling shared by tool calls and data-file reads. */
export function createRequestQueue(limit=4){
  let active=0;const pending=[];
  function drain(){while(active<limit&&pending.length){
    const task=pending.shift(),{work,resolve,reject,signal,abort}=task;
    signal?.removeEventListener('abort',abort);
    active++;Promise.resolve().then(()=>{signal?.throwIfAborted();return work();})
      .then(resolve,reject).finally(()=>{active--;drain();});
  }}
  /**
   * @template T
   * @param {() => Promise<T> | T} work
   * @param {{signal?: AbortSignal, priority?: number}} options
   * @returns {Promise<T>}
   */
  const enqueue=(work,{signal,priority=0}={})=>new Promise((resolve,reject)=>{
    if(signal?.aborted){reject(signal.reason);return;}
    const task={work,resolve,reject,signal,priority};
    task.abort=()=>{const index=pending.indexOf(task);if(index>=0){pending.splice(index,1);reject(signal.reason);}};
    signal?.addEventListener('abort',task.abort,{once:true});
    pending.push(task);pending.sort((a,b)=>b.priority-a.priority);drain();
  });
  return enqueue;
}

// Keep a control slot available while chart queries are still loading.
export function createToolQueue(){
  const reads=createRequestQueue(4), controls=createRequestQueue(1);
  const queries=new Set(['dashboard_view','dashboard_filter_options','component_data','dataset_export','semantic_inspect']);
  return (name,work)=>(queries.has(name)?reads:controls)(work,{priority:name==='dashboard_filter_options'?1:0});
}
