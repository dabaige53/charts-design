/* Pure field mapping and aggregation; shared by every browser delivery surface. */
export const chartTypes = ['bar','line','area','pie','scatter','heatmap','funnel','waterfall'];
export function visibleRows(doc, id) {
  const c = doc.manifest.components[id];
  const rows = doc.snapshot.datasets[c.datasetId] || [];
  const filters = doc.manifest.filters.filter(f => f.componentIds.includes(id) && f.values.length);
  return rows.filter(row => filters.every(f => f.op === 'in' ? f.values.some(v => v === row[f.field]) : f.op === 'contains' ? String(row[f.field]??'').toLocaleLowerCase().includes(f.values[0].toLocaleLowerCase()) : row[f.field] != null && row[f.field] >= f.values[0] && row[f.field] <= f.values[1]));
}
export function aggregate(rows, metric) {
  const numbers = key => rows.map(r => r[key]).filter(v => typeof v === 'number' && Number.isFinite(v));
  const total = values => values.reduce((a,b) => a+b, 0);
  if (metric.aggregation === 'count') return rows.length;
  if (metric.aggregation === 'entity_ratio') {
    const entities=new Map();
    for(const row of rows){const key=row[metric.entityField];if(key==null)continue;
      if(!entities.has(key))entities.set(key,{n:[],d:[]});const entry=entities.get(key);
      for(const [part,field] of [['n',metric.numerator],['d',metric.denominator]]){
        const value=row[field];if(typeof value==='number'&&Number.isFinite(value))entry[part].push(value);
      }
    }
    let n=0,d=0;for(const entry of entities.values()){
      if(entry.n.length&&total(entry.n)>0)n++;
      if(entry.d.length&&total(entry.d)>0)d++;
    }
    return d?n/d:null;
  }
  if (metric.aggregation === 'ratio') {
    const numerator = numbers(metric.numerator), denominator = numbers(metric.denominator);
    if (!numerator.length || !denominator.length) return null;
    const d = total(denominator);
    return d === 0 ? null : total(numerator) / d;
  }
  const values = numbers(metric.field);
  if (!values.length) return null;
  switch (metric.aggregation) {
    case 'sum': return total(values);
    case 'avg': return total(values) / values.length;
    case 'min': return Math.min(...values);
    case 'max': return Math.max(...values);
    default: throw Error('Unsupported metric aggregation');
  }
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
export function optionFor(doc, id) {
  const c = doc.manifest.components[id], data = grouped(doc,id), type = c.chartType;
  const reason = compatible(doc,c,type); if (reason) throw Error(reason);
  const dark = false;
  const colors = ['#123b5d','#628ea8','#a17b45','#638878','#a65d58','#8d7f9d'];
  const text = dark ? '#e4e9ed' : '#293440', line = dark ? '#35404c' : '#e8edf1';
  const base = {animation:false,color:colors,textStyle:{fontFamily:'system-ui',color:text},
    tooltip:{trigger:'item',confine:true,renderMode:'richText'},
    legend:{top:0,textStyle:{color:text},type:'scroll'},
    grid:{left:12,right:20,top:42,bottom:12,containLabel:true}};
  const xs = [...new Set(data.map(d => d.x))], groups = [...new Set(data.map(d => d.group))];
  const metric = doc.manifest.metrics[c.measures[0]];
  const yAxis = {type:'value',axisLabel:{color:text,formatter:v=>format(v,{...metric,unit:''})},splitLine:{lineStyle:{color:line}}};
  const xAxis = {type:'category',data:xs,axisLabel:{color:text,hideOverlap:true},axisLine:{lineStyle:{color:line}}};
  if (['pie','funnel'].includes(type)) {
    const values = data.map(d => ({name:String(d.x ?? '\u672a\u77e5'),value:d.values[c.measures[0]]})).filter(v=>v.value!=null);
    if (values.some(v=>v.value<0)) throw Error('Pie/funnel cannot display negative values; choose a bar chart.');
    return {...base,series:[{type,radius:['40%','72%'],top:45,bottom:15,label:{color:text},data:values}]};
  }
  if (type === 'scatter') return {...base,xAxis:{...yAxis,name:c.x},yAxis,series:[{type:'scatter',name:metric.label,symbolSize:10,data:data.map(d=>[d.x,d.values[c.measures[0]]])}]};
  if (type === 'heatmap') {
    const values = data.map(d=>[xs.indexOf(d.x),groups.indexOf(d.group),d.values[c.measures[0]]]).filter(v=>v[2]!=null);
    const range = values.map(v=>v[2]);
    return {...base,grid:{...base.grid,bottom:60},xAxis,yAxis:{type:'category',data:groups,axisLabel:{color:text}},
      visualMap:{min:Math.min(0,...range),max:Math.max(1,...range),orient:'horizontal',left:'center',bottom:0,textStyle:{color:text},inRange:{color:['#e8f0f5','#123b5d']}},series:[{type:'heatmap',data:values}]};
  }
  if (type === 'waterfall') {
    let running=0;
    const values=data.map((d,index)=>{const delta=d.values[c.measures[0]]??0;const start=running;running+=delta;return [index,start,running,delta];});
    return {...base,legend:{show:false},xAxis,yAxis,
      tooltip:{...base.tooltip,formatter:p=>String(xs[p.value[0]])+'\n'+format(p.value[3],metric)},
      series:[{type:'custom',name:metric.label,encode:{x:0,y:[1,2]},data:values,
        renderItem:(params,api)=>{const a=api.coord([api.value(0),api.value(1)]),b=api.coord([api.value(0),api.value(2)]),width=api.size([1,0])[0]*0.65;
          return {type:'rect',shape:{x:a[0]-width/2,y:Math.min(a[1],b[1]),width,height:Math.max(1,Math.abs(a[1]-b[1]))},style:{fill:api.value(3)>=0?colors[0]:colors[4]}};}}]};
  }
  const series=[];
  for (const mid of c.measures) for (const group of groups) {
    const name=doc.manifest.metrics[mid].label+(c.series?` / ${String(group)}`:'');
    const lookup=new Map(data.filter(d=>d.group===group).map(d=>[d.x,d.values[mid]]));
    series.push({name,type:type==='bar'?'bar':'line',showSymbol:false,connectNulls:false,
      ...(type==='area'?{areaStyle:{opacity:0.15}}:{}),data:xs.map(x=>lookup.get(x)??null),barMaxWidth:52});
  }
  return {...base,tooltip:{...base.tooltip,trigger:'axis'},xAxis,yAxis,series};
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
