/* Width-aware presentation fixes applied after every original option builder.
 *
 * The 40 original builders were tuned for wide two-column cards. Layout
 * templates now place charts in 4-, 6-, 8- and 12-column cells and on phones,
 * so each option is adjusted to its actual canvas width. Adjustments only
 * trigger when content would not fit, and never change data or series. */
let context=null;
export function textWidth(text,size=12,weight='normal'){
  const value=String(text??'');
  if(!context&&typeof document!=='undefined')context=document.createElement('canvas').getContext('2d');
  if(!context)return [...value].reduce((sum,ch)=>sum+(ch.charCodeAt(0)>255?size:size*0.6),0);
  context.font=`${weight} ${size}px Inter, "PingFang SC", "Segoe UI", sans-serif`;
  return context.measureText(value).width;
}
const list=value=>value==null?[]:Array.isArray(value)?value:[value];
function margin(value,width,fallback){
  if(typeof value==='number')return value;
  if(typeof value==='string'&&value.endsWith('%'))return width*parseFloat(value)/100;
  if(typeof value==='string'&&Number.isFinite(Number(value)))return Number(value);
  return fallback;
}
function label(value){return value&&typeof value==='object'?value.value??value.name??'':value;}

export function widthBucket(width){return width<400?'xs':width<560?'sm':width<760?'md':'lg';}

export function adaptOption(option,width){
  if(!option||typeof option!=='object'||!(width>0))return option;
  const grids=list(option.grid),xAxes=list(option.xAxis);
  // 1. Legacy containLabel contains tick labels but not axis names: an x-axis
  //    name at the end is clipped by the canvas unless the right margin fits it.
  for(const axis of xAxes){
    if(!axis||!axis.name||axis.show===false||!['end','max',undefined].includes(axis.nameLocation))continue;
    const grid=grids[axis.gridIndex||0];if(!grid||grid.containLabel!==true)continue;
    const style=axis.nameTextStyle||{};
    const need=Math.ceil(textWidth(axis.name,style.fontSize||12,style.fontWeight||'normal')+(axis.nameGap??15)+6);
    if(margin(grid.right,width,width*0.1)<need)grid.right=need;
  }
  // 2. Crowded category labels truncate (or rotate on very narrow slots) instead of overlapping.
  if(!option.dataZoom)for(const axis of xAxes){
    if(!axis||axis.type!=='category'||!Array.isArray(axis.data)||!axis.data.length||axis.axisLabel?.rotate)continue;
    const grid=grids[axis.gridIndex||0]||{};
    const plot=Math.max(80,width-margin(grid.left,width,width*0.1)-margin(grid.right,width,width*0.1));
    const slot=plot/axis.data.length,size=axis.axisLabel?.fontSize||12;
    const longest=Math.max(...axis.data.map(item=>textWidth(label(item),size)));
    if(longest<=slot-6)continue;
    const next={...(axis.axisLabel||{})};
    if(slot>=44)Object.assign(next,{width:Math.floor(slot-6),overflow:'truncate'});
    else Object.assign(next,{rotate:30,width:72,overflow:'truncate',hideOverlap:true,interval:'auto'});
    axis.axisLabel=next;
  }
  // 3. Legends that cannot fit on one line scroll instead of covering the plot.
  for(const legend of list(option.legend)){
    if(!legend||legend.show===false||legend.type==='scroll'||legend.orient==='vertical')continue;
    const series=list(option.series);
    const names=(legend.data?.map(item=>typeof item==='object'?item?.name:item))||(series.length===1&&['pie','funnel'].includes(series[0]?.type)?list(series[0].data).map(item=>item?.name):series.map(item=>item?.name)).filter(Boolean);
    const size=legend.textStyle?.fontSize||12;
    const total=names.reduce((sum,name)=>sum+textWidth(name,size)+(legend.itemWidth??25)+(legend.itemGap??10)+5,0);
    if(total>width-24)Object.assign(legend,{type:'scroll',pageIconSize:10,pageTextStyle:{fontSize:10}});
  }
  // 4. Value labels on narrow canvases hide when they would overlap.
  if(width<560)for(const series of list(option.series))if(series?.label?.show&&!series.labelLayout)series.labelLayout={hideOverlap:true};
  return option;
}
