/* One page-wide budget for tool calls, including chunks from different responses. */
export function createRequestQueue(limit=4){
  let active=0;const pending=[];
  function drain(){while(active<limit&&pending.length){const {work,resolve,reject}=pending.shift();active++;Promise.resolve().then(work).then(resolve,reject).finally(()=>{active--;drain();});}}
  return work=>new Promise((resolve,reject)=>{pending.push({work,resolve,reject});drain();});
}
