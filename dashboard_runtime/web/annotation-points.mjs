/* Public ECharts API only. Ambiguous/unsupported marks deliberately fall back
 * to a component annotation rather than persisting a dataIndex or pixels. */
let charts=null;
export function configureAnnotationCharts(api) { charts=api; }
const list=value=>Array.isArray(value)?value:value?[value]:[];
const scalar=value=>typeof value==='string'||typeof value==='number'||typeof value==='boolean';
const categoryValue=value=>value&&typeof value==='object'?value.value:value;
function keyOfSeries(series,all) {
  if (typeof series.id==='string' && series.id && !series.id.includes('\u0000') && all.filter(s=>s.id===series.id).length===1) return {kind:'id',value:series.id};
  if (typeof series.name==='string' && series.name && !series.name.includes('\u0000') && all.filter(s=>s.name===series.name).length===1) return {kind:'name',value:series.name};
  return all.length===1?{kind:'single',value:series.type}:null;
}
function equal(a,b) { return typeof a===typeof b && a===b; }
function counts(values) {
  const result=new Map();
  for(const value of values)if(scalar(value))result.set(value,(result.get(value)||0)+1);
  return result;
}
// The component ID lives on GridStack's outer item, while the original chart
// and element IDs live inside a child card's open ShadowRoot.
function rootsFor(host) {
  if(!host)return [];
  return [host,...host.querySelectorAll('*')].flatMap(element=>element.shadowRoot?[element,element.shadowRoot]:[element]);
}
export function findAnnotationElement(host,id) {
  for(const root of rootsFor(host)) {
    if(root.id===id)return root;
    const match=root.getElementById?.(id)||[...root.querySelectorAll('[id]')].find(n=>n.id===id);
    if(match)return match;
  }
  return null;
}
export function chartForAnnotation(host) {
  if (!charts||!host) return null;
  const id=host.dataset?.componentId||host.closest('[data-component-id]')?.dataset.componentId;
  const candidates=[host,findAnnotationElement(host,`original-${id}`)];
  for(const root of rootsFor(host))candidates.push(...root.querySelectorAll('.chart'));
  for (const element of new Set(candidates)) {
    if (!element) continue;
    const chart=charts.getInstanceByDom(element);
    if (chart&&!chart.isDisposed?.()) return chart;
  }
  return null;
}
function pointEntries(option) {
  const series=list(option.series),result=[];
  series.forEach((s,seriesIndex)=>{
    if (!['line','bar','scatter'].includes(s.type)||s.stack||s.encode||s.coordinateSystem&&s.coordinateSystem!=='cartesian2d'||!Array.isArray(s.data)||s.data.length>20000) return;
    const seriesKey=keyOfSeries(s,series);if(!seriesKey)return;
    const xAxis=list(option.xAxis)[s.xAxisIndex||0],yAxis=list(option.yAxis)[s.yAxisIndex||0];
    if (!xAxis||!yAxis) return;
    const axis=xAxis.type==='category'?'x':yAxis.type==='category'?'y':null;
    const categories=axis?list((axis==='x'?xAxis:yAxis).data).map(categoryValue):[];
    const objects=s.data.map(item=>item&&typeof item==='object'&&!Array.isArray(item)?item:null);
    const ids=counts(objects.map(item=>item?.id)),names=counts(objects.map(item=>item?.name)),labels=counts(categories);
    for(let index=0;index<Math.min(s.data.length,20000);index++) {
      const item=s.data[index],object=objects[index],value=object?object.value:item;
      let key=null,xy;
      if (object && scalar(object.id) && ids.get(object.id)===1) key={kind:'id',value:object.id};
      else if (object && typeof object.name==='string' && object.name && names.get(object.name)===1) key={kind:'name',value:object.name};
      else if (axis && !Array.isArray(value) && scalar(categories[index]) && labels.get(categories[index])===1) key={kind:'category',axis,value:categories[index]};
      if (!key) continue;
      if (axis) {
        if (Array.isArray(value)) {
          // Declarative encodings/datasets may have different dimensions: do not guess.
          if(value.length!==2)continue;
          xy=value;
        } else if (typeof value==='number' && Number.isFinite(value)) xy=axis==='x'?[index,value]:[value,index];
      } else if (Array.isArray(value)&&value.length>=2&&value.slice(0,2).every(v=>typeof v==='number'&&Number.isFinite(v))) xy=value.slice(0,2);
      if (!xy||xy.some(v=>v==null||v==='-'||typeof v==='number'&&!Number.isFinite(v))) continue;
      result.push({seriesIndex,seriesKey,key,xy,label:`${s.name||s.type}: ${key.value}`});
    }
  });
  return result;
}
function pixelFor(chart,entry) {
  let pixel;
  try { pixel=chart.convertToPixel({seriesIndex:entry.seriesIndex},entry.xy); } catch { return null; }
  if (!Array.isArray(pixel)||pixel.length<2||!pixel.slice(0,2).every(Number.isFinite)) return null;
  const width=chart.getWidth(),height=chart.getHeight();
  if (!(width>0&&height>0)||pixel[0]<0||pixel[1]<0||pixel[0]>width||pixel[1]>height) return null;
  if (typeof chart.containPixel==='function'&&!chart.containPixel({seriesIndex:entry.seriesIndex},pixel)) return null;
  const box=chart.getDom().getBoundingClientRect();
  return {left:box.left+pixel[0]*box.width/width,top:box.top+pixel[1]*box.height/height,width:0,height:0};
}
export function pickAnnotationPoint(chart,clientX,clientY,tolerance=14) {
  if (!chart) return null;
  let best=null,distance=tolerance;
  for (const entry of pointEntries(chart.getOption())) {
    const box=pixelFor(chart,entry);if(!box)continue;
    const current=Math.hypot(box.left-clientX,box.top-clientY);
    if(current<=distance) {distance=current;best={series:entry.seriesKey,key:entry.key,label:entry.label};}
  }
  return best;
}
export function resolveAnnotationPoint(chart,point) {
  if (!chart||!point||typeof point!=='object') return null;
  const matches=pointEntries(chart.getOption()).filter(e=>
    e.seriesKey.kind===point.series?.kind&&equal(e.seriesKey.value,point.series?.value)&&
    e.key.kind===point.key?.kind&&e.key.axis===point.key?.axis&&equal(e.key.value,point.key?.value));
  return matches.length===1?pixelFor(chart,matches[0]):null;
}
export function annotationFilterKey(doc) {
  const filters=doc?.manifest?.filters||[];
  return JSON.stringify(filters.filter(f=>f.values?.length).map(f=>({id:f.id,op:f.op,field:f.field,values:f.values,componentIds:f.componentIds})).sort((a,b)=>String(a.id).localeCompare(String(b.id))));
}
