// Explicit composer attachments. Never send a message or change saved annotations.
export function supportsAnnotationContext(app){
  const caps=app?.getHostCapabilities();
  return Boolean(caps?.experimental?.['openai/modelContext']&&caps?.updateModelContext?.text);
}
export function annotationContent(document,note){
  const title=document.manifest.components?.[note.componentId]?.title||'页面';
  const context={projectRoot:document.projectRoot??null,dashboardId:document.id,revision:document.revision,title:document.manifest.title,
    componentId:note.componentId,componentTitle:title,anchor:note.anchor,
    filters:document.manifest.filters||[],comment:note.text||''};
  return {type:'text',text:'看板位置引用（用户选中内容）\n'+JSON.stringify(context,null,2),
    _meta:{'openai/title':title+' · '+(note.anchor?.kind==='area'?'选中区域':'选中位置'),
      'openai/group':{title:document.manifest.title||'看板批注'}}};
}
export function createAnnotationContext(app){
  let content=app.getHostContext()?.['openai/modelContext']?.content||[];
  let pending=Promise.resolve();
  return {
    sync(context){if(Object.hasOwn(context,'openai/modelContext'))content=context['openai/modelContext']?.content||[];},
    attach(document,note){
      const block=annotationContent(document,note);
      const operation=pending.then(async()=>{
        const next=[...content,block];
        const result=await app.updateModelContext({content:next});
        if(result?.isError)throw Error('客户端未接受引用，请重试。');
        content=next;
      });
      pending=operation.catch(()=>{});
      return operation;
    }
  };
}
