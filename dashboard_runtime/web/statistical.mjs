// Statistical plots are derived images, never executable chart options or remote URLs.
export function statisticalImageSource(value){
  if(typeof value!=='string'||!/^data:image\/(?:svg\+xml|png);base64,[A-Za-z0-9+/]+={0,2}(?![\s\S])/.test(value))return null;
  return value.slice(value.indexOf(',')+1).length%4===0?value:null;
}

export function updateStatisticalArtifacts(current,result){
  if(!result||(!result.document&&!Object.hasOwn(result,'statisticalArtifacts')))return current;
  const source=result.statisticalArtifacts,next=Object.create(null);
  if(source&&typeof source==='object'&&!Array.isArray(source)){
    for(const [id,value] of Object.entries(source)){
      if(!value||typeof value!=='object'||Array.isArray(value))continue;
      next[id]=Object.fromEntries(['dataUri','caption','error'].filter(key=>typeof value[key]==='string').map(key=>[key,value[key]]));
    }
  }
  const keys=Object.keys(next);
  return keys.length===Object.keys(current).length&&keys.every(id=>Object.hasOwn(current,id)&&['dataUri','caption','error'].every(key=>next[id][key]===current[id][key]))?current:next;
}
