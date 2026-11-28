// Native ECharts options extend a preset; this is a merge policy, not an option whitelist.
const componentArrays=new Set(['series','dataset','xAxis','yAxis','grid','legend','dataZoom','visualMap','title','tooltip','toolbox','polar','radiusAxis','angleAxis','radar','geo','calendar','parallel','parallelAxis','singleAxis','timeline','matrix']);
const plain=value=>value!==null&&typeof value==='object'&&(Object.getPrototypeOf(value)===Object.prototype||Object.getPrototypeOf(value)===null);
function clone(value){
  if(Array.isArray(value))return value.map(clone);
  if(plain(value))return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,clone(item)]));
  return value; // Preset formatters and ECharts objects retain their native identity.
}
function merge(base,override,key=''){
  if(override===undefined)return clone(base);
  if(override===null)return null;
  if(componentArrays.has(key)&&(Array.isArray(base)||Array.isArray(override))){
    const previous=Array.isArray(base)?base:base==null?[]:[base];
    const changes=Array.isArray(override)?override:[override];
    if(!changes.length)return [];
    const result=previous.map(clone);
    changes.forEach((item,index)=>{
      const matched=item?.id!=null?previous.findIndex(entry=>entry?.id===item.id):-1;
      const at=matched<0?index:matched;
      result[at]=merge(previous[at],item);
    });
    return result;
  }
  if(plain(override)){
    const old=plain(base)?base:{};
    return Object.fromEntries([...new Set([...Object.keys(old),...Object.keys(override)])].map(name=>[
      name,merge(Object.hasOwn(old,name)?old[name]:undefined,Object.hasOwn(override,name)?override[name]:undefined,name)
    ]));
  }
  return clone(override);
}
export function applyEChartsOptions(preset,override){
  if(override===undefined)return preset;
  if(!plain(override))throw Error('config.echarts must be an ECharts option object');
  return merge(preset,override);
}
