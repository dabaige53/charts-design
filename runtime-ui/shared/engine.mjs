/* Pure field mapping and aggregation; shared by every browser delivery surface. */
export const chartTypes = ['bar','line','area','pie','scatter','heatmap','funnel','waterfall'];
// Row arrays are immutable snapshots. Share only the latest filter scope per dataset.
const filteredCache=new WeakMap(),aggregateCache=new WeakMap(),groupCache=new WeakMap();
const MAX_AGGREGATE_ENTRIES=256,MAX_GROUP_ENTRIES=8,MAX_GROUP_BYTES=8*1024*1024;
const scalarKey=value=>value===null?'null':typeof value==='number'?(Number.isNaN(value)?'number:NaN':'number:'+value):typeof value+':'+JSON.stringify(value);
export function filterSignature(filters){
  // AND order, labels and consumer IDs do not change the selected rows. Keep
  // scalar types (including missing versus null) distinct in membership tests.
  return JSON.stringify([...new Set(filters.map(f=>JSON.stringify([f.field,f.op,
    f.op==='in'?[...new Set(f.values.map(scalarKey))].sort():f.values.map(scalarKey)])))].sort());
}
function metricKey(metric){
  return JSON.stringify([metric.aggregation,...(metric.aggregation==='count'?[]:
    metric.aggregation==='entity_ratio'?[metric.entityField,metric.numerator,metric.denominator]:
    metric.aggregation==='ratio'?[metric.numerator,metric.denominator]:[metric.field]).map(scalarKey)]);
}
function remember(cache,key,value){
  cache.set(key,value);
  while(cache.size>MAX_AGGREGATE_ENTRIES)cache.delete(cache.keys().next().value);
  return value;
}
export function visibleRows(doc,id){
  const c=doc.manifest.components[id],rows=doc.snapshot.datasets[c.datasetId]||[];
  const filters=doc.manifest.filters.filter(f=>f.componentIds.includes(id)&&f.values.length);
  if(!filters.length)return rows;
  const key=JSON.stringify([doc.dataVersion,filterSignature(filters)]);
  const cached=filteredCache.get(rows);if(cached?.key===key)return cached.rows;
  const tests=filters.map(f=>{
    if(f.op==='in'){const values=new Set(f.values);return row=>values.has(row[f.field]);}
    if(f.op==='contains'){const needle=f.values[0].toLocaleLowerCase();return row=>String(row[f.field]??'').toLocaleLowerCase().includes(needle);}
    return row=>row[f.field]!=null&&row[f.field]>=f.values[0]&&row[f.field]<=f.values[1];
  });
  const result=rows.filter(row=>tests.every(test=>test(row)));
  filteredCache.set(rows,{key,rows:result});return result;
}
export function aggregate(rows,metric){
  let cache=aggregateCache.get(rows);if(!cache){cache=new Map();aggregateCache.set(rows,cache);}
  const key=metricKey(metric);if(cache.has(key))return cache.get(key);
  return remember(cache,key,calculateAggregate(rows,metric));
}
function calculateAggregate(rows,metric){
  if(metric.aggregation==='count')return rows.length;
  if(metric.aggregation==='entity_ratio'){
    const entities=new Map();
    for(const row of rows){const key=row[metric.entityField];if(key==null)continue;
      if(!entities.has(key))entities.set(key,{n:0,d:0});const entry=entities.get(key);
      for(const [part,field]of [['n',metric.numerator],['d',metric.denominator]]){const v=row[field];if(typeof v==='number'&&Number.isFinite(v))entry[part]+=v;}
    }
    let n=0,d=0;for(const e of entities.values()){if(e.n>0)n++;if(e.d>0)d++;}return d?n/d:null;
  }
  const stats=field=>{
    const key='field:'+field;if(cacheForRows.has(key))return cacheForRows.get(key);
    let sum=0,count=0,min=Infinity,max=-Infinity;
    for(const row of rows){const v=row[field];if(typeof v!=='number'||!Number.isFinite(v))continue;sum+=v;count++;if(v<min)min=v;if(v>max)max=v;}
    return remember(cacheForRows,key,{sum,count,min,max});
  };
  const cacheForRows=aggregateCache.get(rows);
  if(metric.aggregation==='ratio'){const n=stats(metric.numerator),d=stats(metric.denominator);return n.count&&d.count&&d.sum!==0?n.sum/d.sum:null;}
  const values=stats(metric.field);if(!values.count)return null;
  switch(metric.aggregation){case 'sum':return values.sum;case 'avg':return values.sum/values.count;case 'min':return values.min;case 'max':return values.max;default:throw Error('Unsupported metric aggregation');}
}

function emptyStats(){return {sum:0,count:0,min:Infinity,max:-Infinity};}
function addValue(stats,value){
  if(typeof value!=='number'||!Number.isFinite(value))return;
  stats.sum+=value;stats.count++;
  if(value<stats.min)stats.min=value;if(value>stats.max)stats.max=value;
}
function period(value,grain){
  if(typeof value!=='string'||!/^\d{4}-\d{2}/.test(value))throw Error('Time binding requires ISO dates');
  return grain==='quarter'?value.slice(0,4)+' Q'+Math.ceil(Number(value.slice(5,7))/3):value.slice(0,7);
}
function groupedValue(group,metric){
  if(metric.aggregation==='count')return group.count;
  if(metric.aggregation==='entity_ratio')return group.ratios.get(metricKey(metric));
  if(metric.aggregation==='unique'){const value=group.uniques.get(metric.field);return value.conflict?null:value.value;}
  if(metric.aggregation==='ratio'){
    const n=group.stats.get(metric.numerator),d=group.stats.get(metric.denominator);
    return n.count&&d.count&&d.sum!==0?n.sum/d.sum:null;
  }
  const value=group.stats.get(metric.field);if(!value.count)return null;
  switch(metric.aggregation){case 'sum':return value.sum;case 'avg':return value.sum/value.count;
    case 'min':return value.min;case 'max':return value.max;default:throw Error('Unsupported metric aggregation');}
}
function groupBytes(state){
  let bytes=256;
  for(const group of state.groups.values()){
    bytes+=160+group.keys.reduce((n,key)=>n+(typeof key==='string'?key.length*2:16),0)
      +group.stats.size*96+group.ratios.size*48;
    for(const unique of group.uniques.values())bytes+=64+(typeof unique.value==='string'?unique.value.length*2:16);
  }
  return bytes;
}

// Keep statistics, not per-group row arrays. A later metric can reuse each
// field's sum/count/min/max; labels and formatting are applied by the caller.
export function aggregateGroups(rows,fields,metrics,{nulls=false,skipNull=false,timeGrain=null}={}){
  const signature=JSON.stringify([fields.map(scalarKey),nulls,skipNull,timeGrain]);
  let cache=groupCache.get(rows);
  if(!cache){cache={entries:new Map(),bytes:0};groupCache.set(rows,cache);}
  let state=cache.entries.get(signature);
  if(state){cache.entries.delete(signature);cache.bytes-=state.bytes;}
  else state={groups:new Map(),fields:new Set(),uniques:new Set(),ratios:new Set(),built:false,bytes:0};
  const numeric=new Set(),unique=new Set(),ratios=new Map();
  for(const metric of Object.values(metrics)){
    if(metric.aggregation==='count')continue;
    if(metric.aggregation==='entity_ratio'){const key=metricKey(metric);if(!state.ratios.has(key))ratios.set(key,metric);}
    else if(metric.aggregation==='unique'){if(!state.uniques.has(metric.field))unique.add(metric.field);}
    else for(const field of metric.aggregation==='ratio'?[metric.numerator,metric.denominator]:[metric.field]){
      if(!state.fields.has(field))numeric.add(field);
    }
  }
  if(!state.built||numeric.size||unique.size||ratios.size){
    const entityTotals=new Map();
    for(const row of rows){
      let key,keys;
      if(fields.length===1&&!nulls){
        key=timeGrain?period(row[fields[0]],timeGrain):row[fields[0]];
        if(skipNull&&key==null)continue;
      }else{
        keys=fields.map((field,index)=>{
          const value=index===0&&timeGrain?period(row[field],timeGrain):row[field];
          return nulls?value??null:value;
        });
        if(skipNull&&keys.some(value=>value==null))continue;
        key=JSON.stringify(keys);
      }
      let group=state.groups.get(key);
      if(!group){group={keys:keys||[key===0?0:key],count:0,stats:new Map(),uniques:new Map(),ratios:new Map()};state.groups.set(key,group);}
      if(!state.built)group.count++;
      for(const field of numeric){
        let stats=group.stats.get(field);
        if(!stats){stats=emptyStats();group.stats.set(field,stats);}addValue(stats,row[field]);
      }
      for(const field of unique){
        const value=row[field]??null,previous=group.uniques.get(field);
        if(!previous)group.uniques.set(field,{value,conflict:false});
        else if(previous.value!==value&&!(Number.isNaN(previous.value)&&Number.isNaN(value)))previous.conflict=true;
      }
      if(ratios.size){
        let pending=entityTotals.get(group);
        if(!pending){pending=new Map([...ratios.keys()].map(key=>[key,new Map()]));entityTotals.set(group,pending);}
        for(const [key,metric]of ratios){
          const entity=row[metric.entityField];if(entity==null)continue;
          const entities=pending.get(key);let sums=entities.get(entity);
          if(!sums){sums={n:0,d:0};entities.set(entity,sums);}
          const n=row[metric.numerator],d=row[metric.denominator];
          if(typeof n==='number'&&Number.isFinite(n))sums.n+=n;
          if(typeof d==='number'&&Number.isFinite(d))sums.d+=d;
        }
      }
    }
    for(const [group,pending]of entityTotals)for(const [key,entities]of pending){
      let n=0,d=0;for(const sums of entities.values()){if(sums.n>0)n++;if(sums.d>0)d++;}
      group.ratios.set(key,d?n/d:null);
    }
    for(const field of numeric)state.fields.add(field);
    for(const field of unique)state.uniques.add(field);
    for(const key of ratios.keys())state.ratios.add(key);
    state.built=true;state.bytes=groupBytes(state);
  }
  const result=[...state.groups.values()].map(group=>({keys:[...group.keys],
    values:Object.fromEntries(Object.entries(metrics).map(([key,metric])=>[key,groupedValue(group,metric)]))}));
  // High-cardinality results remain complete, but are not retained in a cache.
  if(state.bytes<=MAX_GROUP_BYTES){
    cache.entries.set(signature,state);cache.bytes+=state.bytes;
    while(cache.entries.size>MAX_GROUP_ENTRIES||cache.bytes>MAX_GROUP_BYTES){
      const key=cache.entries.keys().next().value;cache.bytes-=cache.entries.get(key).bytes;cache.entries.delete(key);
    }
  }
  return result;
}
export function grouped(doc, id) {
  if(doc.computed?.grouped?.[id])return doc.computed.grouped[id];
  const c=doc.manifest.components[id],metrics=Object.fromEntries(c.measures.map(mid=>[mid,doc.manifest.metrics[mid]]));
  return aggregateGroups(visibleRows(doc,id),[c.x,...(c.series?[c.series]:[])],metrics,{nulls:true})
    .map(group=>({x:group.keys[0],group:c.series?group.keys[1]:null,values:group.values}));
}
export function compatible(doc, c, type) {
  if (!chartTypes.includes(type)) return 'Unsupported chart type';
  if (!c.x) return 'Choose an X/category field';
  if (['pie','funnel','waterfall','heatmap','scatter'].includes(type) && c.measures.length !== 1) return 'This chart requires exactly one measure';
  const units=new Set(c.measures.map(mid=>JSON.stringify([doc.manifest.metrics[mid].unit||'',doc.manifest.metrics[mid].format||'number'])));
  if(units.size>1)return 'Mixed units require separate charts or an explicitly configured legacy dual-axis chart';
  if(['pie','funnel'].includes(type)&&!['sum','count'].includes(doc.manifest.metrics[c.measures[0]].aggregation))return 'Pie/funnel requires an additive sum or count measure';
  if (type === 'scatter' && doc.manifest.datasets[c.datasetId].fields[c.x].type !== 'number') return 'Scatter requires a numeric X field';
  if (type === 'heatmap' && !c.series) return 'Heatmap requires a second categorical field (series)';
  if (['pie','funnel','waterfall'].includes(type) && c.series) return 'Remove the series grouping for this chart';
  const metric = doc.manifest.metrics[c.measures[0]];
  if (type === 'waterfall' && (metric.semantic !== 'delta' || metric.aggregation !== 'sum')) return 'Waterfall requires an additive delta metric; it is not a generic bar chart';
  return null;
}
export function format(value, metric = {}) {
  if (value == null || !Number.isFinite(value)) return '\u2014';
  const digits = metric.decimals ?? 2;
  if (metric.format === 'percent') return new Intl.NumberFormat('zh-CN',{style:'percent',maximumFractionDigits:digits}).format(value);
  return new Intl.NumberFormat('zh-CN',{maximumFractionDigits:digits}).format(value) + (metric.unit ? ` ${metric.unit}` : '');
}
// Round through the metric formatter first: a displayed zero must stay neutral.
export function formatComparison(value, metric = {}) {
  const shown = format(value, metric);
  const number = shown.match(/^-?[\d,.]+/);
  if (!number) return shown;
  if (Number(number[0].replaceAll(',', '')) === 0) return shown.replace(/^-/, '');
  return value > 0 ? '+' + shown : shown;
}
export function chartTable(doc,id) {
  const c=doc.manifest.components[id];
  return grouped(doc,id).map(d=>Object.fromEntries([[c.x,d.x],...(c.series?[[c.series,d.group]]:[]),...c.measures.map(mid=>[doc.manifest.metrics[mid].label,d.values[mid]])]));
}
export function csv(rows) {
  const keys=[...new Set(rows.flatMap(r=>Object.keys(r)))];
  const cell=v=>{let s=String(v??''); if (/^[=+\-@\t\r]/.test(s) && typeof v!=='number') s="'"+s; return '"'+s.replaceAll('"','""')+'"';};
  return '\ufeff'+[keys,...rows.map(r=>keys.map(k=>r[k]))].map(r=>r.map(cell).join(',')).join('\r\n');
}

// Ratios are calculated from grouped totals; missing/zero denominators stay missing.
export function calculateTableRows(rows,presentation,display=true){
  const specs=presentation?.calculatedColumns;if(!specs)return rows;
  return rows.map(source=>{const row={...source};for(const [target,spec]of Object.entries(specs)){
    const n=row[spec.numerator],d=row[spec.denominator],unit=row[spec.unitField],digits=spec.decimals??1;
    const value=n==null||!(d>0)?null:n/d;
    row[target]=!display?value:value==null?'—':unit==='%'?`${(100*value).toFixed(digits)}%`:`${value.toFixed(digits)} ${unit}`.trimEnd();
  }return row;});
}
