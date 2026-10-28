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
  const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const tooltip=r=>[label(r.category),...(e.tooltip||Object.keys(b.measures)).map(k=>`${metric(k).label||k}: ${show(k,r.values[k])}`)].join('\n');
  const position=(point,params,dom,rect,size)=>{const [w,h]=size.contentSize,[vw,vh]=size.viewSize;let x=point[0]+16,y=point[1]-h-12;if(x+w>vw)x=point[0]-w-16;if(y<8)y=point[1]+16;return [Math.max(8,Math.min(x,vw-w-8)),Math.max(8,Math.min(y,vh-h-8))];};
  const base={animation:false,legend:{show:true,type:'scroll',top:0},tooltip:{show:true,trigger:'item',renderMode:'html',confine:true,position,backgroundColor:'#fff',borderColor:'#D6E1EB',padding:14,textStyle:{color:'#17212B',fontSize:13},extraCssText:'box-shadow:0 6px 20px #123b5d15;border-radius:10px;pointer-events:none;z-index:100;'},grid:{left:16,right:24,top:42,bottom:42,containLabel:true},graphic:[],title:[]};
  if(!records.length)return {...base,legend:{show:false},tooltip:{show:false},graphic:[{id:'empty-state',type:'text',left:'center',top:'middle',style:{text:e.emptyText||'当前筛选范围暂无数据',fill:'#7B8794',font:'13px sans-serif'}}],xAxis:{show:false},yAxis:{show:false},dataZoom:[],series:[]};
  if(c.config.code==='r02'){
    const groups=[...new Set(records.map(r=>e.colorBy?r.values[e.colorBy]:null))];
    return {...base,legend:{...base.legend,show:!!e.colorBy},xAxis:{show:true,type:'value',name:metric('x').label,nameLocation:'middle',nameGap:30,axisLabel:{formatter:v=>show('x',v)}},yAxis:{show:true,type:'value',name:metric('y').label,axisLabel:{formatter:v=>show('y',v)}},
      tooltip:{...base.tooltip,formatter:p=>{const r=p.data.record;return `<div style="font-weight:700;color:#123B5D;margin-bottom:8px">${escape(r.category)}</div>`+(e.tooltip||Object.keys(b.measures)).map(k=>`<div style="display:flex;justify-content:space-between;gap:24px;line-height:1.8"><span style="color:#7B8794">${escape(metric(k).label||k)}</span><strong>${escape(show(k,r.values[k]))}</strong></div>`).join('');}},series:groups.map((g,i)=>({name:e.colorBy?label(g):metric('y').label,type:'scatter',label:{show:e.showLabels??false,position:'top',fontSize:10,formatter:p=>label(p.value[3])},itemStyle:{color:color(g,i)},symbolSize:e.sizeBy?(v=>Math.max(4,Math.min(80,Math.sqrt(Math.max(0,v[2]))))):(e.symbolSize??18),data:records.filter(r=>(e.colorBy?r.values[e.colorBy]:null)===g&&r.values.x!=null&&r.values.y!=null).map(r=>({value:[r.values.x,r.values.y,e.sizeBy?r.values[e.sizeBy]:1,r.category],record:r}))}))};
  }
  const categories=[...new Set(records.map(r=>r.category))];
  let groups=[...new Set(records.map(r=>r.series))];
  if(e.topSeries){const totals=new Map(groups.map(g=>[g,0]));for(const r of records)totals.set(r.series,totals.get(r.series)+(r.values.value??0));groups.sort((a,b)=>totals.get(b)-totals.get(a));const pinned=(e.pinnedSeries||[]).filter(g=>groups.includes(g));groups=[...pinned,...groups.filter(g=>!pinned.includes(g))].slice(0,e.topSeries);}
  const lookup=new Map(records.map(r=>[JSON.stringify([r.category,r.series]),r]));
  if(b.orderBy){const sign=b.orderBy.direction==='desc'?-1:1;const total=k=>records.filter(r=>r.category===k).reduce((s,r)=>s+(r.values[b.orderBy.target]??0),0);categories.sort((a,z)=>sign*(total(a)-total(z)));}
  const categoryAxis={show:true,type:'category',data:categories.map(label),axisLabel:{width:180,overflow:'truncate',interval:0},inverse:e.orientation==='horizontal'};
  const valueAxis={show:true,type:'value',axisLabel:{formatter:v=>show('value',v)}};
  const count=e.visibleCount||10,horizontal=e.orientation==='horizontal',zoom=categories.length>count;
  return {...base,grid:{...base.grid,right:horizontal&&zoom?48:24,bottom:!horizontal&&zoom?68:42},dataZoom:zoom?[{id:'category-window',type:'slider',...(horizontal?{yAxisIndex:0,right:8,width:12}:{xAxisIndex:0,bottom:8,height:12}),start:0,end:Math.min(100,count/categories.length*100),showDetail:false,filterMode:'filter'},{id:'category-inside',type:'inside',...(horizontal?{yAxisIndex:0}:{xAxisIndex:0}),start:0,end:Math.min(100,count/categories.length*100)}]:[],xAxis:e.orientation==='horizontal'?valueAxis:categoryAxis,yAxis:e.orientation==='horizontal'?categoryAxis:valueAxis,
    tooltip:{...base.tooltip,formatter:p=>p.data.record?`${escape(label(p.data.record.series))}<br>${escape(tooltip(p.data.record)).replaceAll('\n','<br>')}`:'缺失'},series:groups.map((g,i)=>({name:label(g),type:'bar',stack:e.stacked?'total':undefined,itemStyle:{color:color(g,i)},barWidth:e.barWidth||14,data:categories.map(k=>{const r=lookup.get(JSON.stringify([k,g]));return {value:r?.values.value??null,record:r};})}))};
}
