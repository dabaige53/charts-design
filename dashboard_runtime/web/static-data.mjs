import {createRequestQueue} from './request-queue.mjs';
export function staticData(doc,fetcher=fetch){
  const requests=new Map(),queue=createRequestQueue(4);
  return key=>{
    if(!key||Object.hasOwn(doc.snapshot.datasets,key))return Promise.resolve();
    if(requests.has(key))return requests.get(key);
    const task=Promise.all((doc.staticFiles[key]||[]).map(url=>queue(async()=>{
      const response=await fetcher(url);if(!response.ok)throw Error(`数据加载失败 (${response.status})`);return response.json();
    }))).then(parts=>{doc.snapshot.datasets[key]=parts.flat();}).catch(error=>{requests.delete(key);throw error;});
    requests.set(key,task);return task;
  };
}
