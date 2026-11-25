/* Bounded scheduling shared by tool calls and data-file reads. */
export function createRequestQueue(limit=4){
  let active=0;const pending=[];
  function drain(){while(active<limit&&pending.length){const {work,resolve,reject}=pending.shift();active++;Promise.resolve().then(work).then(resolve,reject).finally(()=>{active--;drain();});}}
  return work=>new Promise((resolve,reject)=>{pending.push({work,resolve,reject});drain();});
}

// Keep a control slot available while chart queries are still loading.
export function createToolQueue(){
  const reads=createRequestQueue(4), controls=createRequestQueue(1), annotations=createRequestQueue(4);
  const queries=new Set(['dashboard_view','dashboard_filter_options','component_data','dataset_export','semantic_inspect','dashboard_annotations','runtime_info']);
  return (name,work,{append}={})=>(name==='dashboard_annotations_update'&&append?annotations:queries.has(name)?reads:controls)(work);
}
