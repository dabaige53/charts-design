import {aggregate,visibleRows,format} from './engine.mjs';
// Metric precision is part of the metric definition: round once here so labels, tooltips and tables agree.
function rounded(value,metric){return value==null?null:Number(value.toFixed(metric?.decimals??2));}
function period(value,grain){
  if(typeof value!=='string'||!/^\d{4}-\d{2}/.test(value))throw Error('Time binding requires ISO dates');
  return grain==='quarter'?value.slice(0,4)+' Q'+Math.ceil(Number(value.slice(5,7))/3):value.slice(0,7);
}
export function resolveOriginal(doc,id,granularity='month'){
  const c=doc.manifest.components[id],b=c.binding,raw=structuredClone(c.config);
  if(!b)return raw;
  const rows=visibleRows(doc,id),metrics=doc.manifest.metrics;
  if(c.family==='table'){raw.rows=rows;return raw;}
  if(c.family==='kpi'){
    for(const target of ['yoy','mom','subVal','leftVal','rightVal'])if(target in raw&&!b.measures[target])raw[target]='\u2014';
    for(const [target,mid]of Object.entries(b.measures)){
      const metric=metrics[mid],n=aggregate(rows,metric),scaled=n==null?null:n*(b.scale?.[target]??1);const shown=target==='percent'?rounded(scaled,metric):scaled;
      raw[target]=target==='percent'?shown:format(scaled,metric);
    }
    if(raw.type==='mc03'){
      const groups=new Map();for(const r of rows){const k=r[b.timeField];if(!groups.has(k))groups.set(k,[]);groups.get(k).push(r);}
      const keys=[...groups.keys()].sort((a,b)=>String(a).localeCompare(String(b),undefined,{numeric:true}));
      raw.sparkMonths=keys;raw.sparkData=keys.map(k=>rounded(aggregate(groups.get(k),metrics[b.measures.value]),metrics[b.measures.value]));
    }
    return raw;
  }
  const groups=new Map();
  for(const row of rows){const category=b.timeGrain?period(row[b.categoryField],granularity):row[b.categoryField];
    if(category==null)continue;if(!groups.has(category))groups.set(category,[]);groups.get(category).push(row);}
  const keys=[...groups.keys()];if(b.timeGrain)keys.sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
  if(raw.code==='t06')raw.data={};
  raw.data[b.categoryTarget]=keys;
  for(const [target,mid]of Object.entries(b.measures))raw.data[target]=keys.map(k=>{const value=aggregate(groups.get(k),metrics[mid]);return value==null?null:rounded(value*(b.scale?.[target]??1),metrics[mid]);});
  if(raw.code==='t06')raw.data={month:raw.data,quarter:structuredClone(raw.data)};
  raw.hasGranularity=!!b.timeGrain;return raw;
}
