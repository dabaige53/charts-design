// Data contents do not belong in a component's refresh signature. Immutable
// snapshot array identity plus dataVersion detects a replacement in O(1).
const identities=new WeakMap();let nextIdentity=0;
function identity(value){
  if(value===null||typeof value!=='object')return value;
  if(!identities.has(value))identities.set(value,++nextIdentity);
  return identities.get(value);
}
export function componentInputSignature(doc,id){
  const c=doc.manifest.components[id],dataset=c.datasetId||c.binding?.datasetId;
  return JSON.stringify([c,doc.dataVersion,doc.computed?.components?.[id],doc.computed?.tables?.[id],doc.computed?.grouped?.[id],doc.manifest.metrics,doc.manifest.datasets,doc.manifest.filters.filter(f=>f.componentIds.includes(id)),doc.computed?null:identity(doc.snapshot.datasets[dataset]),doc.computed?null:doc.snapshot.componentData?.[id]],(key,item)=>['durationMs','totalDurationMs','cacheHits','responseBytes'].includes(key)?undefined:item);
}
