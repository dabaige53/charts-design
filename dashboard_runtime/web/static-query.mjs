import {resolveOriginal} from './bindings.mjs';
import {visibleRows,csv} from './engine.mjs';
import {createRequestQueue} from './request-queue.mjs';
// The static site and the build-time seed use exactly the same query implementation.
export function createStaticQuery(document,read){
  const queue=createRequestQueue(4),loaded=new Map(),scopes=new Map();
  async function rowsFor(id,filters){
    const c=document.manifest.components[id],key=c.datasetId,partition=document.staticPartitions?.[key];
    const active=filters.filter(f=>f.componentIds.includes(id)&&f.values.length);
    let urls=document.staticFiles[key]||[];
    if(partition){
      const conditions=active.filter(f=>f.field===partition.field);
      urls=Object.entries(partition.files).filter(([value])=>conditions.every(f=>f.op==='in'?f.values.includes(value):f.op==='range'?value>=f.values[0]&&value<=f.values[1]:value.includes(f.values[0]))).flatMap(([,files])=>files);
    }
    const scope=JSON.stringify(urls);let cached=scopes.get(key);
    if(cached?.scope===scope)return cached.promise;
    const promise=Promise.all(urls.map(url=>{
      if(!loaded.has(url))loaded.set(url,queue(()=>read(url)).catch(error=>{loaded.delete(url);throw error;}));
      return loaded.get(url);
    })).then(parts=>parts.flat());
    scopes.set(key,{scope,promise});return promise;
  }
  function tableRows(doc,id){
    const c=doc.manifest.components[id],p=c.presentation||{};let rows=visibleRows(doc,id);
    if(p.groupBy){const groups=new Map();for(const row of rows){const key=JSON.stringify(p.groupBy.map(k=>row[k]??null));if(!groups.has(key))groups.set(key,Object.fromEntries([...p.groupBy.map(k=>[k,row[k]]),...(p.sumFields||[]).map(k=>[k,null])]));const target=groups.get(key);for(const k of p.sumFields||[])if(row[k]!=null)target[k]=(target[k]??0)+row[k];}rows=[...groups.values()];}
    return rows;
  }
  const groupedCache=new Map();
  async function query(args){
    const filters=args.filters||document.manifest.filters,computed={components:{},tables:{}};
    for(const id of args.componentIds){
      const c=document.manifest.components[id],rows=await rowsFor(id,filters);
      const doc={...document,computed:undefined,manifest:{...document.manifest,filters},snapshot:{...document.snapshot,datasets:{[c.datasetId]:rows}}};
      if(c.kind==='table'||c.family==='table'){
        const signature=JSON.stringify(filters.filter(f=>f.componentIds.includes(id)&&f.values.length));let cached=groupedCache.get(id);
        if(!cached||cached.source!==rows||cached.signature!==signature){cached={source:rows,signature,rows:tableRows(doc,id)};groupedCache.set(id,cached);}
        const state={page:1,pageSize:10,sortCol:null,sortDir:'asc',keyword:'',...c.presentation?.tableState,...args.tableStates?.[id]};
        let result=cached.rows;const columns=c.presentation?.columns||c.config?.columns||[];
        if(state.keyword){const needle=state.keyword.toLocaleLowerCase();result=result.filter(row=>columns.some(col=>String(row[col.key]??'').toLocaleLowerCase().includes(needle)));}
        if(state.sortCol)result=[...result].sort((a,b)=>{const x=a[state.sortCol],y=b[state.sortCol];return (typeof x==='number'&&typeof y==='number'?x-y:String(x??'').localeCompare(String(y??''),'zh-CN',{numeric:true}))*(state.sortDir==='desc'?-1:1);});
        if(args.export){const selected=args.export.columns||columns.map(c=>c.key);return {csv:csv(result.map(row=>Object.fromEntries(selected.map(key=>[columns.find(c=>c.key===key)?.title||key,row[key]])))),rowCount:result.length};}
        state.totalRows=result.length;state.pageSize=Math.max(1,Math.min(9999,Number(state.pageSize)||10));state.page=Math.max(1,Math.min(Number(state.page)||1,Math.max(1,Math.ceil(result.length/state.pageSize))));
        computed.components[id]={...c.presentation,...c.config,columns,rows:result.slice((state.page-1)*state.pageSize,state.page*state.pageSize)};computed.tables[id]=state;
      }else computed.components[id]=resolveOriginal(doc,id,args.granularities?.[id]||'month');
    }
    return {revision:document.revision,computed};
  }
  return {query};
}
