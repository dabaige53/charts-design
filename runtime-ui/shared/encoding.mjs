import {aggregateGroups,visibleRows} from './engine.mjs';
export function encodingRecords(doc,id){
  const b=doc.manifest.components[id].binding;
  const metrics={...Object.fromEntries(Object.entries(b.measures).map(([key,mid])=>[key,doc.manifest.metrics[mid]])),...b.attributes};
  return aggregateGroups(visibleRows(doc,id),[b.categoryField,...(b.seriesField?[b.seriesField]:[])],metrics,{nulls:true})
    .map(group=>({category:group.keys[0],series:b.seriesField?group.keys[1]:null,values:group.values}));
}
export function encodingTable(doc,id,records){
  const c=doc.manifest.components[id],b=c.binding,keys=[...Object.keys(b.measures),...Object.keys(b.attributes||{})];
  return {headers:[b.categoryField,...(b.seriesField?[b.seriesField]:[]),...keys.map(k=>doc.manifest.metrics[b.measures[k]]?.label||b.attributes?.[k]?.label||k)],rows:records.map(r=>[r.category,...(b.seriesField?[r.series]:[]),...keys.map(k=>r.values[k])])};
}
