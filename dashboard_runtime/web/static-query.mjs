import {resolveOriginal} from './bindings.mjs';
import {visibleRows,csv,calculateTableRows,grouped} from './engine.mjs';
const compareValue=(a,b)=>a==null?(b==null?0:-1):b==null?1:a<b?-1:a>b?1:0;
function sortNumber(value){
  if(value==null)return null;
  const match=String(value).replace(/[^0-9.\-]/g,'').match(/^-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)/);
  const number=match?Number(match[0]):NaN;return Number.isFinite(number)?number:null;
}
function sortRows(rows,sort,fields){
  if(!sort?.length)return rows;
  return [...rows].sort((a,b)=>{
    for(const {field,direction='asc'}of sort){
      const sign=direction==='desc'?-1:1,raw='raw'+field[0].toUpperCase()+field.slice(1);
      let result;
      if(fields[field]?.type==='string'&&fields[raw]?.type==='number')result=compareValue(a[raw],b[raw]);
      else if(fields[field]?.type==='string'){
        const x=sortNumber(a[field]),y=sortNumber(b[field]);
        if((x==null)!==(y==null))return x==null?1:-1;
        result=x==null?compareValue(a[field],b[field]):compareValue(x,y);
      }else result=compareValue(a[field],b[field]);
      if(result)return sign*result;
    }
    return 0;
  });
}
function searchRows(rows,search,fields){
  if(!search)return rows;
  const needle=search.toLocaleLowerCase();
  return rows.filter(row=>Object.keys(fields).some(key=>!key.startsWith('_')&&!key.startsWith('raw')&&key in row&&
    String(row[key]===null?'null':row[key]).toLocaleLowerCase().includes(needle)));
}
// The static site and the build-time seed use exactly the same query implementation.
export function createStaticQuery(document,read,{maxScopes=8,maxScopeRows=250000}={}){
  const scopes=new Map();
  let scopeRows=0;
  function cachedRows(key){
    const rows=scopes.get(key);
    if(rows){scopes.delete(key);scopes.set(key,rows);}
    return rows;
  }
  const datasetFor=id=>document.manifest.components[id].datasetId||document.manifest.components[id].binding?.datasetId||document.staticComponentDatasets?.[id];
  const fieldsFor=key=>document.manifest.datasets[key]?.fields||document.staticDatasetFields?.[key]||{};
  const scopedDocument=(id,rows,filters)=>({...document,computed:undefined,
    manifest:{...document.manifest,filters,components:{...document.manifest.components,
      [id]:{...document.manifest.components[id],datasetId:datasetFor(id)}}},
    snapshot:{...document.snapshot,datasets:{[datasetFor(id)]:rows}}});
  async function rowsFor(id,filters,signal){
    signal?.throwIfAborted();
    const key=datasetFor(id),partition=document.staticPartitions?.[key];
    const active=filters.filter(f=>f.componentIds.includes(id)&&f.values.length);
    if(!document.staticFiles?.[key])return document.snapshot.datasets[key]||[];
    let urls=document.staticFiles[key]||[];
    const index=document.staticPartitionIndexes?.[key];
    if(index){
      const conditions=active.filter(f=>f.field===index.field);
      const selected=new Set(index.entries.filter(entry=>conditions.every(f=>f.op==='in'?f.values.includes(entry.value):
        f.op==='range'?entry.value!=null&&entry.value>=f.values[0]&&entry.value<=f.values[1]:
        String(entry.value??'').toLocaleLowerCase().includes(String(f.values[0]).toLocaleLowerCase()))).flatMap(entry=>entry.files));
      urls=urls.filter(url=>selected.has(url));
    }
    if(partition){
      const conditions=active.filter(f=>f.field===partition.field);
      urls=Object.entries(partition.files).filter(([value])=>conditions.every(f=>f.op==='in'?f.values.includes(value):f.op==='range'?value>=f.values[0]&&value<=f.values[1]:value.includes(f.values[0]))).flatMap(([,files])=>files);
    }
    const scope=JSON.stringify([key,urls]);let cached=cachedRows(scope);
    if(cached)return cached;
    const parts=await Promise.all(urls.map(url=>read(url,{signal})));
    signal?.throwIfAborted();
    // Another component batch may have finished the same shared downloads.
    // Keep one row array so filtering and metric caches can serve every batch.
    cached=cachedRows(scope);
    if(cached)return cached;
    const rows=(()=>{
      if(parts.every(Array.isArray))return parts.flat();
      // Partition files retain original row positions so changing a filter
      // does not silently change unsorted details, grouping or export order.
      return parts.flatMap(part=>part.rows.map((row,index)=>({row,ordinal:part.ordinals[index]})))
        .sort((a,b)=>a.ordinal-b.ordinal).map(entry=>entry.row);
    })();
    signal?.throwIfAborted();
    scopes.set(scope,rows);scopeRows+=rows.length;
    // Keep the current range even when it alone exceeds the reference budget.
    while(scopes.size>1&&(scopes.size>maxScopes||scopeRows>maxScopeRows)){
      const oldest=scopes.keys().next().value;
      scopeRows-=scopes.get(oldest).length;scopes.delete(oldest);
    }
    return rows;
  }
  function tableRows(doc,id){
    const c=doc.manifest.components[id],p={...c.presentation,...c.config};let rows=visibleRows(doc,id);
    if(p.groupBy){const groups=new Map();for(const row of rows){const key=JSON.stringify(p.groupBy.map(k=>row[k]??null));if(!groups.has(key))groups.set(key,Object.fromEntries([...p.groupBy.map(k=>[k,row[k]]),...(p.sumFields||[]).map(k=>[k,null])]));const target=groups.get(key);for(const k of p.sumFields||[])if(row[k]!=null)target[k]=(target[k]??0)+row[k];}rows=[...groups.values()];}
    return calculateTableRows(rows,p,false);
  }
  const groupedCache=new Map(),optionCache=new Map();
  async function query(args,{signal}={}){
    signal?.throwIfAborted();
    const filters=args.filters||document.manifest.filters,computed={components:{},tables:{},grouped:{}};
    if(args.filterId){
      const filter=document.manifest.filters.find(f=>f.id===args.filterId);
      if(!filter||filter.op!=='in')throw Error('Unknown selection filter');
      const search=(args.search||'').toLocaleLowerCase();
      let cached=optionCache.get(filter.id);
      if(!cached){
        const promise=(async()=>{
          const values=new Map();
          const datasets=new Map(filter.componentIds.map(id=>[datasetFor(id),id]));
          const sources=await Promise.all([...datasets].map(async([dataset,id])=>{
            const url=document.staticOptions?.[dataset]?.[filter.field];
            if(url)return read(url,{priority:1});
            // Embedded/legacy documents have no external option index.
            // Hosted COS documents always carry indexes; do not silently scan
            // their full row resources if that contract is broken.
            if(document.storageFormat==='cos-v1'&&document.staticFiles?.[dataset])
              throw Error('筛选选项索引缺失，请更新数据目录');
            return (await rowsFor(id,[])).map(row=>row[filter.field]??null);
          }));
          for(const source of sources){
            for(const value of source)values.set(JSON.stringify(value),value);
          }
          return [...values.values()].sort(compareValue);
        })().catch(error=>{
          if(optionCache.get(filter.id)?.promise===promise)optionCache.delete(filter.id);
          throw error;
        });
        cached={promise};optionCache.set(filter.id,cached);
      }
      const values=await cached.promise;
      signal?.throwIfAborted();
      if(cached.search!==search){
        cached.search=search;cached.matches=search?values.filter(v=>String(v).toLocaleLowerCase().includes(search)):values;
      }
      const matches=cached.matches;
      const offset=args.offset||0,limit=args.limit||100;
      return {values:matches.slice(offset,offset+limit),offset,totalValues:matches.length,hasMore:offset+limit<matches.length};
    }
    if(args.detail){
      const id=args.componentId,rows=await rowsFor(id,filters,signal);
      const doc=scopedDocument(id,rows,filters);
      let result=visibleRows(doc,id);
      const fields=fieldsFor(datasetFor(id));
      result=sortRows(searchRows(result,args.search,fields),args.sort,fields);
      if(args.export)return {csv:csv(result.map(row=>Object.fromEntries((args.columns||Object.keys(fields)).map(key=>[key,row[key]])))),rowCount:result.length};
      const offset=args.offset||0,limit=args.limit||10;
      return {rows:result.slice(offset,offset+limit),fields,totalRows:result.length,offset,limit,hasMore:offset+limit<result.length};
    }
    const ids=args.componentIds||Object.keys(document.manifest.components);
    const sources=new Map(),ranges=new Map();
    for(const id of ids){
      const c=document.manifest.components[id];
      if(c.kind==='text'||c.kind==='statistical')continue;
      // Filters may apply differently to two consumers of the same dataset.
      const key=JSON.stringify([datasetFor(id),filters.filter(f=>f.componentIds.includes(id))
        .map(f=>[f.field,f.op,f.values])]);
      if(!ranges.has(key))ranges.set(key,rowsFor(id,filters,signal));
      sources.set(id,ranges.get(key));
    }
    const rowsById=new Map(await Promise.all([...sources].map(async([id,rows])=>[id,await rows])));
    signal?.throwIfAborted();
    let sliceStart=performance.now();
    for(const id of ids){
      const c=document.manifest.components[id];
      if(c.kind==='text'||c.kind==='statistical')continue;
      const rows=rowsById.get(id);
      if(signal&&performance.now()-sliceStart>=8){
        // Yield a task, not a microtask, so Worker cancel messages can run.
        await new Promise(resolve=>setTimeout(resolve,0));
        signal.throwIfAborted();sliceStart=performance.now();
      }
      const doc=scopedDocument(id,rows,filters);
      if(c.kind==='table'||c.family==='table'){
        const signature=JSON.stringify(filters.filter(f=>f.componentIds.includes(id)&&f.values.length));let cached=groupedCache.get(id);
        if(!cached||cached.source!==rows||cached.signature!==signature){cached={source:rows,signature,rows:tableRows(doc,id)};groupedCache.set(id,cached);}
        const state={page:1,pageSize:10,sortCol:null,sortDir:'asc',keyword:'',...c.presentation?.tableState,...c.config?.tableState,...args.tableStates?.[id]};
        let result=cached.rows;const columns=c.presentation?.columns||c.config?.columns||Object.entries(fieldsFor(datasetFor(id))).map(([key,field])=>({key,title:field.label||key,align:field.type==='number'?'right':'left'}));
        const fields=fieldsFor(datasetFor(id));
        result=sortRows(searchRows(result,state.keyword,fields),state.sortCol?[{field:state.sortCol,direction:state.sortDir}]:[],fields);
        if(args.export){const selected=args.export.columns||columns.map(c=>c.key);return {csv:csv(result.map(row=>Object.fromEntries(selected.map(key=>[args.export.fieldNames?key:columns.find(c=>c.key===key)?.title||key,row[key]])))),rowCount:result.length};}
        state.totalRows=result.length;state.pageSize=Math.max(1,Math.min(9999,Number(state.pageSize)||10));state.page=Math.max(1,Math.min(Number(state.page)||1,Math.max(1,Math.ceil(result.length/state.pageSize))));
        computed.components[id]={...c.presentation,...c.config,columns,rows:calculateTableRows(result.slice((state.page-1)*state.pageSize,state.page*state.pageSize),{...c.presentation,...c.config})};computed.tables[id]=state;
      }else if(c.kind==='chart')computed.grouped[id]=grouped(doc,id);
      else computed.components[id]=resolveOriginal(doc,id,args.granularities?.[id]||'month');
    }
    return {id:document.id,revision:document.revision,computed};
  }
  return {query};
}
