import {createStaticQuery} from './static-query.mjs';
import {readStaticData} from '../../runtime-ui/src/static-data.ts';
let engine;
self.onmessage=async({data})=>{
  const {id,type,args}=data;
  try{
    if(type==='init'){
      const {document,base,headers={}}=args;
      engine=createStaticQuery(document,async path=>{const url=new URL(path,base);return readStaticData(await fetch(url,{headers}),url.pathname);});
      self.postMessage({id,result:{ready:true}});return;
    }
    self.postMessage({id,result:await engine.query(args)});
  }catch(error){self.postMessage({id,error:error.message});}
};
