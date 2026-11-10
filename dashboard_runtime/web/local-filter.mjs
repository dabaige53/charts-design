export function staticFilterPage(values,search='',offset=0,size=100){
  const query=search.toLocaleLowerCase(),matches=query?values.filter(value=>String(value??'').toLocaleLowerCase().includes(query)):values;
  return {values:matches.slice(offset,offset+size),offset,totalValues:matches.length,hasMore:offset+size<matches.length};
}
export function clearFilterValues(filters){return filters.map(filter=>({...filter,values:filter.required?[...filter.values]:[]}));}
