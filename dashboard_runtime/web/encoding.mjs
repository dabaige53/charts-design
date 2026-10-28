import {aggregate,visibleRows,format} from './engine.mjs';
export function encodingRecords(doc,id){
  const c=doc.manifest.components[id],b=c.binding,groups=new Map();
  for(const row of visibleRows(doc,id)){
    const category=row[b.categoryField]??null,series=b.seriesField?(row[b.seriesField]??null):null,key=JSON.stringify([category,series]);
    if(!groups.has(key))groups.set(key,{category,series,rows:[]});groups.get(key).rows.push(row);
  }
  return [...groups.values()].map(g=>{
    const values=Object.fromEntries(Object.entries(b.measures).map(([k,mid])=>[k,aggregate(g.rows,doc.manifest.metrics[mid])]));
    for(const [k,a] of Object.entries(b.attributes||{})){
      const vs=g.rows.map(r=>r[a.field]??null);
      values[k]=a.aggregation==='unique'?(new Set(vs).size===1?vs[0]:null):aggregate(g.rows,a);
    }
    return {category:g.category,series:g.series,values};
  });
}
export function encodingTable(doc,id,records){
  const c=doc.manifest.components[id],b=c.binding,keys=[...Object.keys(b.measures),...Object.keys(b.attributes||{})];
  return {headers:[b.categoryField,...(b.seriesField?[b.seriesField]:[]),...keys.map(k=>doc.manifest.metrics[b.measures[k]]?.label||b.attributes?.[k]?.label||k)],rows:records.map(r=>[r.category,...(b.seriesField?[r.series]:[]),...keys.map(k=>r.values[k])])};
}
export function encodingOption(doc,id,records){
  const c=doc.manifest.components[id],b=c.binding,e=c.config.encoding;
  const label=v=>v==null?'缺失':String(v),palette=['#123B5D','#4A709C','#7B8FA1','#A6B4C2','#638878','#8D7F9D'];
  const color=(k,i)=>e.colors?.[label(k)]||palette[i%palette.length];
  const metric=k=>doc.manifest.metrics[b.measures[k]]||b.attributes?.[k]||{};
  const show=(k,v)=>typeof v==='number'?format(v,metric(k)):label(v);
  const tooltip=r=>[label(r.category),...(e.tooltip||Object.keys(b.measures)).map(k=>`${metric(k).label||k}: ${show(k,r.values[k])}`)].join('\n');
  const base={animation:false,legend:{type:'scroll',top:0},tooltip:{trigger:'item',renderMode:'richText',confine:true},grid:{left:16,right:24,top:42,bottom:42,containLabel:true}};
  if(!records.length)return {...base,title:{text:'当前筛选无数据',left:'center',top:'middle'},xAxis:{show:false},yAxis:{show:false},series:[]};
  if(c.config.code==='r02'){
    const groups=[...new Set(records.map(r=>e.colorBy?r.values[e.colorBy]:null))];
    return {...base,legend:{...base.legend,show:!!e.colorBy},xAxis:{type:'value',name:metric('x').label,nameLocation:'middle',nameGap:30,axisLabel:{formatter:v=>show('x',v)}},yAxis:{type:'value',name:metric('y').label,axisLabel:{formatter:v=>show('y',v)}},
      tooltip:{...base.tooltip,formatter:p=>tooltip(p.data.record)},series:groups.map((g,i)=>({name:e.colorBy?label(g):metric('y').label,type:'scatter',label:{show:e.showLabels??false,position:'top',fontSize:10,formatter:p=>label(p.value[3])},itemStyle:{color:color(g,i)},symbolSize:e.sizeBy?(v=>Math.max(4,Math.min(80,Math.sqrt(Math.max(0,v[2]))))):(e.symbolSize??18),data:records.filter(r=>(e.colorBy?r.values[e.colorBy]:null)===g&&r.values.x!=null&&r.values.y!=null).map(r=>({value:[r.values.x,r.values.y,e.sizeBy?r.values[e.sizeBy]:1,r.category],record:r}))}))};
  }
  const categories=[...new Set(records.map(r=>r.category))],groups=[...new Set(records.map(r=>r.series))];
  const lookup=new Map(records.map(r=>[JSON.stringify([r.category,r.series]),r]));
  if(b.orderBy){const sign=b.orderBy.direction==='desc'?-1:1;const total=k=>records.filter(r=>r.category===k).reduce((s,r)=>s+(r.values[b.orderBy.target]??0),0);categories.sort((a,z)=>sign*(total(a)-total(z)));}
  const categoryAxis={type:'category',data:categories.map(label),axisLabel:{width:180,overflow:'truncate',interval:0},inverse:e.orientation==='horizontal'};
  const valueAxis={type:'value',axisLabel:{formatter:v=>show('value',v)}};
  return {...base,xAxis:e.orientation==='horizontal'?valueAxis:categoryAxis,yAxis:e.orientation==='horizontal'?categoryAxis:valueAxis,
    tooltip:{...base.tooltip,formatter:p=>p.data.record?`${label(p.data.record.series)}\n${tooltip(p.data.record)}`:'缺失'},series:groups.map((g,i)=>({name:label(g),type:'bar',stack:e.stacked?'total':undefined,itemStyle:{color:color(g,i)},barMaxWidth:40,data:categories.map(k=>{const r=lookup.get(JSON.stringify([k,g]));return {value:r?.values.value??null,record:r};})}))};
}
