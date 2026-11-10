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
  const position=(point,params,dom,rect,size)=>{const [w,h]=size.contentSize,[vw,vh]=size.viewSize;let x=point[0]+16,y=point[1]-h-12;if(x+w>vw)x=point[0]-w-16;if(y<8)y=point[1]+16;return [Math.max(8,Math.min(x,vw-w-8)),Math.max(8,Math.min(y,vh-h-8))];};
  const base={animation:false,legend:{show:true,type:'scroll',top:0},tooltip:{show:true,trigger:'item',renderMode:'html',confine:true,position,backgroundColor:'#fff',borderColor:'#D6E1EB',padding:14,textStyle:{color:'#17212B',fontSize:13},extraCssText:'box-shadow:0 6px 20px #123b5d15;border-radius:10px;pointer-events:none;z-index:100;'},grid:{left:16,right:24,top:42,bottom:42,containLabel:true},graphic:[],title:[]};
  if(!records.length)return {...base,legend:{show:false},tooltip:{show:false},graphic:[{id:'empty-state',type:'text',left:'center',top:'middle',style:{text:e.emptyText||'当前筛选范围暂无数据',fill:'#7B8794',font:'13px sans-serif'}}],xAxis:{show:false},yAxis:{show:false},dataZoom:[],series:[]};
  if(c.config.code==='r02'){
    const groups=[...new Set(records.map(r=>e.colorBy?r.values[e.colorBy]:null))];
    return {...base,legend:{...base.legend,show:!!e.colorBy},xAxis:{show:true,type:'value',name:metric('x').label,nameLocation:'middle',nameGap:30,axisLabel:{formatter:v=>show('x',v)}},yAxis:{show:true,type:'value',name:metric('y').label,axisLabel:{formatter:v=>show('y',v)}},
      tooltip:{...base.tooltip,formatter:p=>{const r=p.data.record;return `<div style="font-weight:700;color:#123B5D;margin-bottom:8px">${escape(r.category)}</div>`+(e.tooltip||Object.keys(b.measures)).map(k=>`<div style="display:flex;justify-content:space-between;gap:24px;line-height:1.8"><span style="color:#7B8794">${escape(metric(k).label||k)}</span><strong>${escape(show(k,r.values[k]))}</strong></div>`).join('');}},series:groups.map((g,i)=>({name:e.colorBy?label(g):metric('y').label,type:'scatter',label:{show:e.showLabels??false,position:'top',fontSize:10,formatter:p=>label(p.value[3])},itemStyle:{color:color(g,i)},symbolSize:e.sizeBy?(v=>Math.max(4,Math.min(80,Math.sqrt(Math.max(0,v[2]))))):(e.symbolSize??18),data:records.filter(r=>(e.colorBy?r.values[e.colorBy]:null)===g&&r.values.x!=null&&r.values.y!=null).map(r=>({value:[r.values.x,r.values.y,e.sizeBy?r.values[e.sizeBy]:1,r.category],record:r}))}))};
  }
  if(c.config.code==='r03'){
    const categories=[...new Set(records.map(r=>r.category))].sort((a,b)=>label(a).localeCompare(label(b)));
    const groups=[...new Set([...(e.seriesOrder||[]),...records.map(r=>r.series)])];
    const lookup=new Map(records.map(r=>[JSON.stringify([r.category,r.series]),r]));
    const data=categories.flatMap((category,y)=>groups.map((series,x)=>{
      const r=lookup.get(JSON.stringify([category,series])),v=r?.values.value,den=r?.values.denominator;
      const missing=!r||v==null||den===0;
      return {value:[x,y,missing?0:v],record:r,label:{show:true,color:missing?'#969BA5':'#27272A',fontSize:12,lineHeight:23,formatter:missing?'无记录\n0 条':show('value',v)+'\n'+(r.values.numerator!=null?`高风险 ${show('numerator',r.values.numerator)} / ${show('denominator',den)}`:'')},itemStyle:{color:missing?'#F5F6F8':`rgba(239,68,68,${.07+Math.max(0,Math.min(1,v))*.4})`,borderColor:'#fff',borderWidth:7}};
    }));
    const count=e.visibleCount||8,zoom=categories.length>count;
    return {...base,legend:{show:false},grid:{left:75,right:zoom?30:12,top:28,bottom:20},xAxis:{type:'category',data:groups.map(label),position:'top',axisLine:{show:false},axisTick:{show:false}},yAxis:{type:'category',data:categories.map(label),inverse:true,axisLine:{show:false},axisTick:{show:false},axisLabel:{interval:0}},dataZoom:zoom?[{type:'slider',yAxisIndex:0,right:0,width:10,startValue:0,endValue:count-1,filterMode:'filter',showDetail:false},{type:'inside',yAxisIndex:0,startValue:0,endValue:count-1}]:[],tooltip:{...base.tooltip,formatter:p=>{const r=p.data.record;return r?escape(label(r.category)+' · '+label(r.series))+'<br>'+escape(show('value',r.values.value))+'<br>高风险 '+escape(show('numerator',r.values.numerator))+' / '+escape(show('denominator',r.values.denominator)):'无记录';}},series:[{type:'heatmap',data}]};
  }
  if(c.config.code==='k01'){
    return {...base,legend:{...base.legend,top:undefined,bottom:0},xAxis:{show:false},yAxis:{show:false},tooltip:{...base.tooltip,formatter:p=>escape(p.name)+'：'+escape(show('value',p.value))+'（'+p.percent+'%）'},series:[{type:'pie',radius:['43%','66%'],center:['50%','43%'],label:{show:true,formatter:'{b}\n{d}%',fontSize:11},labelLine:{length:8,length2:4},data:records.map((r,i)=>({name:label(r.category),value:r.values.value,itemStyle:{color:color(r.category,i)}}))}]};
  }
  if(c.config.code==='f02'){
    const categories=e.categoryOrder||[...new Set(records.map(r=>r.category))];
    const nodes=categories.map((category,i)=>{const r=records.find(r=>r.category===category),v=r?.values.value,d=r?.values.denominator;return {name:category,x:i*210,y:0,record:r,symbol:'roundRect',symbolSize:[150,112],itemStyle:{color:'#F5F8FC',borderColor:'#B8CADD',borderWidth:1.5},label:{show:true,color:'#123B5D',fontSize:12,lineHeight:24,formatter:category+'\n'+(r?.series||'')+'\n'+(d>0?show('value',v)+' / '+show('denominator',d):'—')}};});
    return {...base,legend:{show:false},xAxis:{show:false},yAxis:{show:false},tooltip:{...base.tooltip,formatter:p=>{const r=p.data.record;return r?escape(label(r.category))+'<br>'+escape(label(r.series))+'<br>'+escape(show('value',r.values.value))+' / '+escape(show('denominator',r.values.denominator)):'—';}},series:[{type:'graph',layout:'none',left:90,right:90,top:'44%',bottom:'44%',roam:false,silent:false,edgeSymbol:['none','arrow'],edgeSymbolSize:9,lineStyle:{color:'#8BA2B9',width:2,opacity:1},data:nodes,links:categories.slice(1).map((category,i)=>({source:categories[i],target:category,tooltip:{show:false}}))}]};
  }
  const categories=[...new Set(records.map(r=>r.category))];
  let groups=[...new Set(records.map(r=>r.series))];
  let keptByCategory=null;
  if(e.topSeries){
    const totals=new Map(groups.map(g=>[g,0]));for(const r of records)totals.set(r.series,totals.get(r.series)+(r.values.value??0));groups.sort((a,b)=>totals.get(b)-totals.get(a));
    const select=list=>{const pinned=(e.pinnedSeries||[]).filter(g=>list.includes(g));return [...pinned,...list.filter(g=>!pinned.includes(g))].slice(0,e.topSeries);};
    if(e.seriesRanking==='category'){
      keptByCategory=new Map();const values=new Map();
      for(const r of records){if(!values.has(r.category))values.set(r.category,new Map());const v=values.get(r.category);v.set(r.series,(v.get(r.series)||0)+(r.values.value??0));}
      for(const [category,v]of values)keptByCategory.set(category,new Set(select([...v.keys()].sort((a,b)=>v.get(b)-v.get(a)||String(a).localeCompare(String(b))))));
      groups=groups.filter(g=>[...keptByCategory.values()].some(set=>set.has(g)));
    }else groups=select(groups);
  }
  if(e.otherSeriesLabel&&e.topSeries){
    const kept=new Set(groups),other=new Map(),isKept=r=>(keptByCategory?.get(r.category)||kept).has(r.series);
    for(const r of records){if(isKept(r))continue;const item=other.get(r.category)||{category:r.category,series:e.otherSeriesLabel,values:{value:0}};item.values.value+=r.values.value??0;other.set(r.category,item);}
    if(other.size){records=[...records.filter(isKept),...other.values()];groups=[...groups,e.otherSeriesLabel];}
  }
  const lookup=new Map(records.map(r=>[JSON.stringify([r.category,r.series]),r]));
  if(b.orderBy){const sign=b.orderBy.direction==='desc'?-1:1,totals=new Map();for(const r of records)totals.set(r.category,(totals.get(r.category)||0)+(r.values[b.orderBy.target]??0));categories.sort((a,z)=>sign*((totals.get(a)||0)-(totals.get(z)||0)));}
  const additive=['sum','count'].includes(metric('value').aggregation);
  const totalsByCategory=new Map();
  for(const r of records)totalsByCategory.set(r.category,(totalsByCategory.get(r.category)||0)+(r.values.value??0));
  const grandTotal=[...totalsByCategory.values()].reduce((a,v)=>a+v,0);
  const percent=(value,total)=>total?`${(value/total*100).toFixed(1)}%`:'—';
  const stackTooltip=params=>{
    const items=Array.isArray(params)?params:[params],record=items.find(p=>p.data?.record)?.data.record;
    if(!record)return '暂无数据';
    const total=totalsByCategory.get(record.category)||0;
    const heading=`<div style="font-size:14px;font-weight:700;color:#123B5D;white-space:normal;overflow-wrap:anywhere;margin-bottom:6px">${escape(label(record.category))}</div>`;
    const summary=!additive?'':`<div style="color:#7B8794;margin-bottom:8px;white-space:normal">${escape(c.config.presentation?.tooltipTotalLabel||'合计')}: <strong style="color:#123B5D;font-family:monospace">${escape(show('value',total))}</strong>（占当前范围 ${percent(total,grandTotal)}）</div>`;
    const rows=groups.map((g,i)=>{const r=lookup.get(JSON.stringify([record.category,g]));if(!r||r.values.value==null)return '';const value=r.values.value,emphasis=(e.pinnedSeries||[]).includes(g),ink=emphasis?color(g,i):'#17212B';return `<div style="display:flex;align-items:center;justify-content:space-between;gap:28px;line-height:1.9"><span style="display:flex;align-items:center;gap:9px;color:#7B8794"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${escape(color(g,i))}"></span>${escape(label(g))}</span><strong style="color:${escape(ink)};font-family:monospace;font-variant-numeric:tabular-nums;white-space:nowrap">${escape(show('value',value))}${additive?'（'+percent(value,total)+'）':''}</strong></div>`;}).join('');
    const gradeText=b.attributes?.grade?groups.filter(g=>g==='HO').map(g=>{const r=lookup.get(JSON.stringify([record.category,g]));return r?escape(label(g))+': '+escape(r.values.grade||'多种评级'):'';}).filter(Boolean).join('；'):'';
    const hoRecord=lookup.get(JSON.stringify([record.category,'HO']));
    let connectionText='';
    if(b.attributes?.connectionKey&&hoRecord){const key=hoRecord.values.connectionKey;if(key==null)connectionText='HO：所选行程未形成可服务衔接';else{const wait=Math.floor(key/1000000),period=String(key%1000000),grade=wait<=240?'优质':wait<=360?'良好':wait<=480?'一般':'较差';connectionText=`${escape(b.attributes.connectionKey.label||'HO计划衔接')}：${wait} 分钟 · ${grade} · ${period.slice(0,4)}-${period.slice(4)} · 中转 ${escape(hoRecord.values.selectedHub||'多个中转点（请先选择B→C）')}`;}}
    return `<div style="min-width:260px;max-width:520px">${heading}${summary}${rows}${connectionText?'<div style="margin-top:8px;white-space:normal">'+connectionText+'</div>':''}${gradeText?'<div style="margin-top:8px;white-space:normal">HO 衔接评级：'+gradeText+'</div>':''}</div>`;
  };
  const categoryAxis={show:true,type:'category',data:categories.map(label),axisLabel:{width:180,overflow:'truncate',interval:0},inverse:e.orientation==='horizontal'};
  const valueAxis={show:true,type:'value',axisLabel:{formatter:v=>show('value',v)}};
  const count=e.visibleCount||10,horizontal=e.orientation==='horizontal',zoom=categories.length>count;
  return {...base,grid:{...base.grid,right:horizontal&&zoom?48:24,bottom:!horizontal&&zoom?68:42},dataZoom:zoom?[{id:'category-window',type:'slider',...(horizontal?{yAxisIndex:0,right:8,width:12}:{xAxisIndex:0,bottom:8,height:12}),startValue:0,endValue:count-1,rangeMode:['value','value'],minSpan:0,showDetail:false,filterMode:'filter'},{id:'category-inside',type:'inside',...(horizontal?{yAxisIndex:0}:{xAxisIndex:0}),startValue:0,endValue:count-1,rangeMode:['value','value'],minSpan:0}]:[],xAxis:e.orientation==='horizontal'?valueAxis:categoryAxis,yAxis:e.orientation==='horizontal'?categoryAxis:valueAxis,
    tooltip:{...base.tooltip,trigger:'axis',axisPointer:{type:'shadow'},formatter:stackTooltip},series:groups.map((g,i)=>({name:label(g),type:'bar',stack:e.stacked?'total':undefined,itemStyle:{color:color(g,i)},barMaxWidth:e.barWidth||14,barGap:'15%',barCategoryGap:'30%',data:categories.map(k=>{const r=lookup.get(JSON.stringify([k,g]));return {value:r?.values.value??null,record:r};})}))};
}
