import {resolveOriginal} from './bindings.mjs';
import {visibleRows,csv,calculateTableRows,filterSignature,grouped} from './engine.mjs';
import {createRequestQueue} from './request-queue.mjs';
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
export function createStaticQuery(document,read){
  const queue=createRequestQueue(4),loaded=new Map(),scopes=new Map();
  const datasetFor=id=>document.manifest.components[id].datasetId||document.manifest.components[id].binding?.datasetId||document.staticComponentDatasets?.[id];
  const fieldsFor=key=>document.manifest.datasets[key]?.fields||document.staticDatasetFields?.[key]||{};
  function load(url){
    if(!loaded.has(url))loaded.set(url,queue(()=>read(url)).catch(error=>{loaded.delete(url);throw error;}));
    return loaded.get(url);
  }
  const scopedDocument=(id,rows,filters)=>({...document,computed:undefined,
    manifest:{...document.manifest,filters,components:{...document.manifest.components,
      [id]:{...document.manifest.components[id],datasetId:datasetFor(id)}}},
    snapshot:{...document.snapshot,datasets:{[datasetFor(id)]:rows}}});
  async function rowsFor(id,filters){
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
    const scope=JSON.stringify(urls);let cached=scopes.get(key);
    if(cached?.scope===scope)return cached.promise;
    const promise=Promise.all(urls.map(load)).then(parts=>{
      if(parts.every(Array.isArray))return parts.length===1?parts[0]:parts.flat();
      // Partition files retain original row positions so changing a filter
      // does not silently change unsorted details, grouping or export order.
      return parts.flatMap(part=>part.rows.map((row,index)=>({row,ordinal:part.ordinals[index]})))
        .sort((a,b)=>a.ordinal-b.ordinal).map(entry=>entry.row);
    }).catch(error=>{if(scopes.get(key)?.promise===promise)scopes.delete(key);throw error;});
    scopes.set(key,{scope,promise});return promise;
  }
  function* fieldValues(parts,field){
    for(const part of parts)for(const row of Array.isArray(part)?part:part.rows)yield row[field]??null;
  }
  async function optionsFor(filter){
    const prepared=document.staticFilterOptions?.[filter.id];
    if(Array.isArray(prepared))return prepared;
    const consumers=new Map(filter.componentIds.map(id=>[datasetFor(id),id]));
    const groups=await Promise.all([...consumers].map(async ([dataset,id])=>{
      const index=document.staticPartitionIndexes?.[dataset];
      if(index?.field===filter.field)return index.entries.map(entry=>entry.value);
      const source=document.staticOptions?.[dataset]?.[filter.field];
      if(typeof source==='string')return load(source);
      if(source){
        if(typeof source.field!=='string'||!Array.isArray(source.files))throw Error('筛选选项分片描述不完整');
        return fieldValues(await Promise.all(source.files.map(load)),source.field);
      }
      return fieldValues([await rowsFor(id,[])],filter.field);
    }));
    const values=new Map();
    for(const group of groups)for(const value of group)values.set(JSON.stringify(value),value);
    return [...values.values()];
  }
  function tableRows(doc,id,calculate){
    const c=doc.manifest.components[id],p={...c.presentation,...c.config};let rows=visibleRows(doc,id);
    if(p.groupBy){const groups=new Map();for(const row of rows){const key=JSON.stringify(p.groupBy.map(k=>row[k]??null));if(!groups.has(key))groups.set(key,Object.fromEntries([...p.groupBy.map(k=>[k,row[k]]),...(p.sumFields||[]).map(k=>[k,null])]));const target=groups.get(key);for(const k of p.sumFields||[])if(row[k]!=null)target[k]=(target[k]??0)+row[k];}rows=[...groups.values()];}
    return calculate?calculateTableRows(rows,p,false):rows;
  }
  // One recent query per component, with a bounded budget per immutable source.
  // A WeakMap lets obsolete partition scopes disappear with their row arrays.
  const rowQueryCache=new WeakMap(),rowBudget=8*1024*1024;
  function cachedRows(source,key,signature,compute){
    let cache=rowQueryCache.get(source);if(!cache){cache={entries:new Map(),bytes:0};rowQueryCache.set(source,cache);}
    let cached=cache.entries.get(key);
    if(cached){cache.entries.delete(key);cache.bytes-=cached.bytes;}
    if(!cached||cached.signature!==signature){
      const {rows,allocated=false}=compute();
      const bytes=rows===source?0:rows.length*(allocated?64+16*Object.keys(rows[0]||{}).length:8);
      cached={signature,rows,bytes};
    }
    if(cached.bytes<=rowBudget){
      cache.entries.set(key,cached);cache.bytes+=cached.bytes;
      while(cache.entries.size>16||cache.bytes>rowBudget){const first=cache.entries.keys().next().value;cache.bytes-=cache.entries.get(first).bytes;cache.entries.delete(first);}
    }
    return cached.rows;
  }
  async function query(args){
    const filters=args.filters||document.manifest.filters,computed={components:{},tables:{},grouped:{}};
    if(args.filterId){
      const filter=document.manifest.filters.find(f=>f.id===args.filterId);
      if(!filter||filter.op!=='in')throw Error('Unknown selection filter');
      const search=(args.search||'').toLocaleLowerCase();
      const matches=(await optionsFor(filter)).filter(v=>String(v).toLocaleLowerCase().includes(search)).sort(compareValue);
      const offset=args.offset||0,limit=args.limit||100;
      return {values:matches.slice(offset,offset+limit),offset,totalValues:matches.length,hasMore:offset+limit<matches.length};
    }
    if(args.detail){
      const id=args.componentId,rows=await rowsFor(id,filters);
      const doc=scopedDocument(id,rows,filters);
      const fields=fieldsFor(datasetFor(id));
      const signature=JSON.stringify([filterSignature(filters.filter(f=>f.componentIds.includes(id)&&f.values.length)),args.search||'',args.sort||[],fields]);
      const result=cachedRows(rows,'detail:'+id,signature,()=>({rows:sortRows(searchRows(visibleRows(doc,id),args.search,fields),args.sort,fields)}));
      if(args.export)return {csv:csv(result.map(row=>Object.fromEntries((args.columns||Object.keys(fields)).map(key=>[key,row[key]])))),rowCount:result.length};
      const offset=args.offset||0,limit=args.limit||10;
      return {rows:structuredClone(result.slice(offset,offset+limit)),fields:structuredClone(fields),totalRows:result.length,offset,limit,hasMore:offset+limit<result.length};
    }
    for(const id of args.componentIds||Object.keys(document.manifest.components)){
      const c=document.manifest.components[id];
      if(c.kind==='text'||c.kind==='statistical')continue;
      const rows=await rowsFor(id,filters);
      const doc=scopedDocument(id,rows,filters);
      if(c.kind==='table'||c.family==='table'){
        const state={page:1,pageSize:10,sortCol:null,sortDir:'asc',keyword:'',...c.presentation?.tableState,...c.config?.tableState,...args.tableStates?.[id]};
        const fields=fieldsFor(datasetFor(id));
        const columns=c.presentation?.columns||c.config?.columns||Object.entries(fields).map(([key,field])=>({key,title:field.label||key,align:field.type==='number'?'right':'left'}));
        const presentation={...c.presentation,...c.config},targets=new Set(Object.keys(presentation.calculatedColumns||{}));
        const rawSort=state.sortCol?'raw'+state.sortCol[0].toUpperCase()+state.sortCol.slice(1):null;
        const sortField=fields[state.sortCol]?.type==='string'&&fields[rawSort]?.type==='number'?rawSort:state.sortCol;
        // Search, calculated sorting and CSV need every derived value. Ordinary
        // paging only calculates its returned rows, preserving both numeric and
        // display passes (including calculated-column dependency order).
        const calculate=targets.size>0&&!!(args.export||state.keyword||targets.has(sortField));
        const signature=JSON.stringify([filterSignature(filters.filter(f=>f.componentIds.includes(id)&&f.values.length)),calculate,state.keyword,state.sortCol,state.sortDir,
          fields,presentation.groupBy,presentation.sumFields,presentation.calculatedColumns]);
        const result=cachedRows(rows,'table:'+id,signature,()=>({
          rows:sortRows(searchRows(tableRows(doc,id,calculate),state.keyword,fields),state.sortCol?[{field:state.sortCol,direction:state.sortDir}]:[],fields),
          allocated:!!presentation.groupBy||calculate,
        }));
        if(args.export){const selected=args.export.columns||columns.map(c=>c.key);return {csv:csv(result.map(row=>Object.fromEntries(selected.map(key=>[args.export.fieldNames?key:columns.find(c=>c.key===key)?.title||key,row[key]])))),rowCount:result.length};}
        state.totalRows=result.length;state.pageSize=Math.max(1,Math.min(9999,Number(state.pageSize)||10));state.page=Math.max(1,Math.min(Number(state.page)||1,Math.max(1,Math.ceil(result.length/state.pageSize))));
        let page=result.slice((state.page-1)*state.pageSize,state.page*state.pageSize);
        if(!calculate&&targets.size)page=calculateTableRows(page,presentation,false);
        // Isolate only the returned page and presentation, never the full dataset.
        computed.components[id]=structuredClone({...c.presentation,...c.config,columns,rows:calculateTableRows(page,presentation)});computed.tables[id]=state;
      }else if(c.kind==='chart')computed.grouped[id]=grouped(doc,id);
      else computed.components[id]=resolveOriginal(doc,id,args.granularities?.[id]||'month');
    }
    return {id:document.id,revision:document.revision,computed};
  }
  return {query};
}
