import {encodingRecords} from './encoding.mjs';
import {aggregate,aggregateGroups,visibleRows,format,formatComparison} from './engine.mjs';
// Metric precision is part of the metric definition: round once here so labels, tooltips and tables agree.
function rounded(value,metric){return value==null?null:Number(value.toFixed(metric?.decimals??2));}
// Geometry targets (ring, bullet, paired bars) stay numeric; others are formatted text.
const NUMERIC_TARGETS=new Set(['percent','actual','target','currentValue','priorValue']);
export function resolveOriginal(doc,id,granularity='month'){
  if(doc.computed?.components?.[id])return structuredClone(doc.computed.components[id]);
  const c=doc.manifest.components[id],b=c.binding,raw=structuredClone(c.config||c.presentation||{});
  if(c.kind==='kpi'){
    const metric=doc.manifest.metrics[c.measures[0]],rows=visibleRows(doc,id),active=doc.manifest.filters.some(f=>f.componentIds.includes(id)&&f.values.length);
    raw.type=raw.type||'mc01';raw.label=c.title;raw.value=format(aggregate(rows,metric),metric);
    if(active){for(const target of ['yoy','mom','subVal','leftVal','rightVal','trendLabel','gaugeSub'])if(target in raw)raw[target]='—';for(const target of ['percent','actual','target','currentValue','priorValue','stats','items'])delete raw[target];}
    if(['mc03','mc12'].includes(raw.type)&&raw.timeField){
      const groups=new Map(aggregateGroups(rows,[raw.timeField],{value:metric}).map(group=>[group.keys[0],group.values.value]));
      raw.sparkMonths=[...groups.keys()].sort();raw.sparkData=raw.sparkMonths.map(key=>groups.get(key));
    }
    return raw;
  }
  if(!b)return raw;
  if(raw.encoding){raw.data={records:encodingRecords(doc,id)};return raw;}
  const rows=visibleRows(doc,id),metrics=doc.manifest.metrics;
  if(c.family==='table'){raw.rows=rows;return raw;}
  if(c.family==='kpi'){
    for(const target of ['yoy','mom','subVal','leftVal','rightVal'])if(target in raw&&!b.measures[target])raw[target]='\u2014';
    for(const [target,mid]of Object.entries(b.measures)){
      const metric=metrics[mid],n=aggregate(rows,metric),scaled=n==null?null:n*(b.scale?.[target]??1),numeric=NUMERIC_TARGETS.has(target);const shown=numeric?rounded(scaled,metric):scaled;
      raw[target]=numeric?shown:(['yoy','mom'].includes(target)?formatComparison(scaled,metric):format(scaled,metric));
    }
    for(const [target,comparison] of Object.entries(b.comparisons||{})){const current=aggregate(rows,metrics[b.measures[comparison.current]]),baseline=aggregate(rows,metrics[b.measures[comparison.baseline]]);raw[target]=formatComparison(current!=null&&baseline!=null&&baseline!==0?(current-baseline)/baseline:null,{format:'percent',scale:'fraction',decimals:1,unit:''});}
    if(raw.type==='mc03'||raw.type==='mc12'){
      const groups=new Map(aggregateGroups(rows,[b.timeField],{value:metrics[b.measures.value]}).map(group=>[group.keys[0],group.values.value]));
      const keys=[...groups.keys()].sort((a,b)=>String(a).localeCompare(String(b),undefined,{numeric:true}));
      raw.sparkMonths=keys;raw.sparkData=keys.map(k=>rounded(groups.get(k),metrics[b.measures.value]));
    }
    return raw;
  }
  const definitions=Object.fromEntries(Object.values(b.measures).map(mid=>[mid,metrics[mid]]));
  const groups=new Map(aggregateGroups(rows,[b.categoryField],definitions,{skipNull:true,timeGrain:b.timeGrain?granularity:null})
    .map(group=>[group.keys[0],group.values]));
  const keys=[...groups.keys()];if(b.timeGrain)keys.sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
  if(b.orderBy){const mid=b.measures[b.orderBy.target],sign=b.orderBy.direction==='desc'?-1:1;
    keys.sort((a,c)=>{const av=groups.get(a)[mid],cv=groups.get(c)[mid];
      return av==null?(cv==null?String(a).localeCompare(String(c)):1):cv==null?-1:sign*(av-cv)||String(a).localeCompare(String(c));});}
  if(raw.code==='r02'){
    raw.data.clusters=keys.flatMap(k=>{
      const values=['x','y','size'].map(target=>{const mid=b.measures[target],value=groups.get(k)[mid];return value==null?null:rounded(value*(b.scale?.[target]??1),metrics[mid]);});
      return k!==''&&values.every(v=>v!=null)&&values[2]>=0?[[...values,k]]:[];
    });
    return raw;
  }
  if(raw.code==='t06')raw.data={};
  raw.data[b.categoryTarget]=keys;
  for(const [target,mid]of Object.entries(b.measures))raw.data[target]=keys.map(k=>{const value=groups.get(k)[mid];return value==null?null:rounded(value*(b.scale?.[target]??1),metrics[mid]);});
  if(raw.code==='t06')raw.data={month:raw.data,quarter:structuredClone(raw.data)};
  raw.hasGranularity=!!b.timeGrain;return raw;
}
