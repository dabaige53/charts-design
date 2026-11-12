import {createStaticQuery} from './static-query.mjs';
import {createStaticResources} from './static-resources.mjs';
const resources=createStaticResources(),engines=new Map(),tasks=new Map();
self.onmessage=async({data})=>{
  const {id,type,args,client=0}=data;
  if(type==='cancel'){tasks.get(id)?.controller.abort();return;}
  if(type==='dispose'){
    engines.delete(client);
    for(const task of tasks.values())if(task.client===client)task.controller.abort();
    return;
  }
  const controller=new AbortController();tasks.set(id,{controller,client});
  try{
    if(type==='init'){
      const {document,base,headers={}}=args;
      engines.set(client,createStaticQuery(document,(path,options={})=>{
        const url=new URL(path,base).href;
        return resources.json(url,{...options,headers,key:document.staticResourceKeys?.[path]||url});
      }));
      self.postMessage({id,result:{ready:true}});return;
    }
    const engine=engines.get(client);
    if(!engine)throw Error('数据读取器已关闭');
    const result=await engine.query(args,{signal:controller.signal});
    controller.signal.throwIfAborted();self.postMessage({id,result});
  }catch(error){self.postMessage({id,error:error.message,errorName:error.name,status:error.status});}
  finally{tasks.delete(id);}
};
