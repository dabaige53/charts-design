/* Pure field mapping and aggregation; shared by every browser delivery surface. */
export const chartTypes = ['bar','line','area','pie','scatter','heatmap','funnel','waterfall'];
// Row arrays are immutable snapshots. Share only the latest filter scope per dataset.
const filteredCache=new WeakMap(),aggregateCache=new WeakMap();
export function visibleRows(doc,id){
  const c=doc.manifest.components[id],rows=doc.snapshot.datasets[c.datasetId]||[];
  const filters=doc.manifest.filters.filter(f=>f.componentIds.includes(id)&&f.values.length);
  if(!filters.length)return rows;
  const key=JSON.stringify([doc.dataVersion,filters.map(f=>[f.field,f.op,f.values])]);
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
  const key=JSON.stringify(metric);if(cache.has(key))return cache.get(key);
  const result=calculateAggregate(rows,metric);cache.set(key,result);return result;
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
    const result={sum,count,min,max};cacheForRows.set(key,result);return result;
  };
  const cacheForRows=aggregateCache.get(rows);
  if(metric.aggregation==='ratio'){const n=stats(metric.numerator),d=stats(metric.denominator);return n.count&&d.count&&d.sum!==0?n.sum/d.sum:null;}
  const values=stats(metric.field);if(!values.count)return null;
  switch(metric.aggregation){case 'sum':return values.sum;case 'avg':return values.sum/values.count;case 'min':return values.min;case 'max':return values.max;default:throw Error('Unsupported metric aggregation');}
}
export function grouped(doc, id) {
  if(doc.computed?.grouped?.[id])return doc.computed.grouped[id];
  const c = doc.manifest.components[id], groups = new Map();
  for (const row of visibleRows(doc,id)) {
    const x = row[c.x] ?? null, group = c.series ? row[c.series] ?? null : null;
    const key = JSON.stringify([x,group]);
    if (!groups.has(key)) groups.set(key, {x,group,rows:[]});
    groups.get(key).rows.push(row);
  }
  return [...groups.values()].map(g => ({x:g.x, group:g.group,
    values:Object.fromEntries(c.measures.map(mid => [mid,aggregate(g.rows,doc.manifest.metrics[mid])]))}));
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
