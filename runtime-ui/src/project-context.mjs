import {decodeToolResult} from './tool-result.mjs';

// Each iframe binds once, before fetching chunks or starting background requests.
export function createProjectContext(send){
  let bound=false,projectRoot=null,resolveReady;
  const ready=new Promise(resolve=>{resolveReady=resolve;});
  return {
    get projectRoot(){return projectRoot;},
    accept(result){
      const value=decodeToolResult(result),next=value?.projectRoot??null;
      if(bound&&next!==projectRoot)throw Error('收到其他项目的预览，请在新的预览页面打开。');
      if(!bound){projectRoot=next;bound=true;resolveReady();}
    },
    async call(name,args={}){
      await ready;
      if(Object.hasOwn(args,'projectRoot')&&args.projectRoot!==projectRoot)throw Error('不能在当前预览中切换项目。');
      return send(name,projectRoot?{...args,projectRoot}:args);
    }
  };
}
