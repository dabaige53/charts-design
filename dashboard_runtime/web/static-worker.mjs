import {createStaticQuery} from './static-query.mjs';
let engine;
self.onmessage=async({data})=>{
  const {id,type,args}=data;
  try{
    if(type==='init'){
      const {document,base,headers={}}=args;
      engine=createStaticQuery(document,async path=>{const response=await fetch(new URL(path,base),{headers});if(!response.ok)throw Error(`数据加载失败 (${response.status})`);return path.endsWith('.gz')?new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).json():response.json();});
      self.postMessage({id,result:{ready:true}});return;
    }
    self.postMessage({id,result:await engine.query(args)});
  }catch(error){self.postMessage({id,error:error.message});}
};
