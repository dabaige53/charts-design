import {aggregate,visibleRows} from './engine.mjs';
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
