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

export function mountStatisticalImage(card,component,artifact){
  const node=(tag,cls,text='')=>{const n=document.createElement(tag);n.className=cls;n.textContent=text;return n;};
  const figure=node('figure','statistical-figure');card.append(figure);
  const fail=message=>{const warning=node('p','statistical-error error',message);warning.setAttribute('role','alert');figure.append(warning);};
  const source=statisticalImageSource(artifact?.dataUri);
  if(artifact?.error)fail('统计图暂不可用：'+artifact.error);
  else if(!artifact)fail('统计图暂不可用：此快照未包含生成的图片，请在服务端生成后重新读取或导出。');
  else if(!source)fail('统计图暂不可用：图片格式无效，仅接受内嵌的 SVG / PNG Base64 图片。');
  else{
    const image=node('img','statistical-image');image.alt=component.title;image.decoding='async';
    image.addEventListener('error',()=>{image.remove();fail('统计图暂不可用：内嵌图片无法加载，请重新生成。');},{once:true});
    image.src=source;figure.append(image);
  }
  if(artifact?.caption)figure.append(node('figcaption','statistical-caption',artifact.caption));
}
