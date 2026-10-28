const node=(tag,cls='',text='')=>{const n=document.createElement(tag);n.className=cls;n.textContent=text;return n;};
const clamp=n=>Math.max(0,Math.min(1,n));
export function relativeRect(rect,base){
  const x=clamp((rect.left-base.left)/base.width),y=clamp((rect.top-base.top)/base.height);
  return {x,y,width:Math.min(1-x,Math.max(0,rect.width/base.width)),height:Math.min(1-y,Math.max(0,rect.height/base.height))};
}
export function absoluteRect(rect,base){return {left:base.left+rect.x*base.width,top:base.top+rect.y*base.height,width:rect.width*base.width,height:rect.height*base.height};}
const textBlocks='p,h1,h2,h3,h4,li,blockquote,td,th,.text-block,.dashboard-description';
const quote=n=>(n?.textContent||'').trim().slice(0,1000);
export function createAnnotations({root,getDocument,save,readOnly,onError,onMode,iconButton}){
  const layer=node('div','annotation-layer'),outline=node('div','annotation-outline'),pins=node('div','annotation-pins'),panel=node('aside','annotation-panel'),hint=node('div','annotation-hint','点击元素或拖选区域添加批注 · Esc 退出');
  panel.setAttribute('aria-label','批注面板');layer.append(outline,pins,hint,panel);document.body.append(layer);
  let active=false,selected=null,draft=null,gesture=null,frame=0,pageId=null,saving=false,opener=null;
  const notes=()=>getDocument()?.manifest.annotations||[];
  const hostFor=id=>[...root.querySelectorAll('[data-component-id]')].find(n=>n.dataset.componentId===id);
  function targetFor(note){
    const anchor=note.anchor;
    if(note.componentId)return hostFor(note.componentId)||null;
    if(anchor?.scope==='text')return [...root.querySelectorAll(textBlocks)].filter(n=>quote(n)===anchor.quote)[anchor.occurrence||0]||null;
    return root;
  }
  function bounds(note){const target=targetFor(note);if(!target)return null;const base=target.getBoundingClientRect();return note.anchor?.rect?absoluteRect(note.anchor.rect,base):{left:base.left+8,top:base.top+8,width:0,height:0};}
  function setOutline(rect){outline.hidden=!rect;if(rect)Object.assign(outline.style,{left:rect.left+'px',top:rect.top+'px',width:Math.max(2,rect.width)+'px',height:Math.max(2,rect.height)+'px'});}
  function schedule(){if(!frame)frame=requestAnimationFrame(()=>{frame=0;paint();});}
  function paint(){
    layer.hidden=!active;if(!active)return;
    pins.replaceChildren();notes().forEach((note,index)=>{const rect=bounds(note);if(!rect)return;const pin=node('button','annotation-pin',String(index+1));pin.type='button';pin.setAttribute('aria-label',`批注 ${index+1}：${note.text}`);pin.title=note.text;Object.assign(pin.style,{left:Math.max(14,Math.min(innerWidth-18,rect.left))+'px',top:rect.top+'px'});pin.onclick=()=>openNote(note);pins.append(pin);});
    if(!gesture)setOutline(selected?bounds(selected):draft?bounds(draft):null);
  }
  function setActive(value){active=value;gesture=null;selected=null;draft=null;panel.replaceChildren();panel.hidden=true;hint.hidden=readOnly;root.classList.toggle('is-annotating',active);if(active)opener=document.activeElement;else opener?.focus?.();onMode(active);if(active)showList();paint();}
  function action(label,run){const b=node('button','',label);b.type='button';b.onclick=()=>Promise.resolve().then(run).catch(onError);return b;}
  function header(title){panel.replaceChildren();panel.hidden=false;const h=node('header');h.append(node('strong','',title),iconButton('close','关闭批注面板',()=>{panel.hidden=true;selected=null;draft=null;paint();}));panel.append(h);}
  function showList(){
    selected=null;draft=null;header(`批注（${notes().length}）`);const list=node('div','annotation-panel-list');
    if(!notes().length)list.append(node('p','muted','暂无批注。点击页面元素或拖选区域开始。'));
    notes().forEach((note,index)=>{const item=action(`${index+1}. ${note.text}`,()=>{const target=targetFor(note);target?.scrollIntoView({block:'center',behavior:'smooth'});openNote(note);});item.className='annotation-list-entry';if(!targetFor(note))item.append(node('span','muted','原位置已失效'));list.append(item);});panel.append(list);paint();
  }
  async function commit(transform){if(saving)return false;saving=true;panel.querySelectorAll('button,textarea').forEach(n=>n.disabled=true);try{await save(transform);return true;}finally{saving=false;panel.querySelectorAll('button,textarea').forEach(n=>n.disabled=false);}}
  function openNote(note,isNew=false){
    selected=isNew?null:note;draft=isNew?note:null;header(isNew?'新增批注':'批注');
    const label=note.componentId?getDocument().manifest.components[note.componentId]?.title:'页面';
    panel.append(node('p','muted',isNew||targetFor(note)?(note.anchor?.quote||label||'页面'):'原位置已失效，批注已保留'));
    const area=node('textarea');area.value=isNew?'':note.text;area.maxLength=4000;area.setAttribute('aria-label',isNew?'新增位置批注':'位置批注内容');area.disabled=readOnly;panel.append(area);
    const error=node('p','annotation-error');error.setAttribute('role','alert');panel.append(error);
    const controls=node('div','annotation-panel-actions');
    if(!readOnly){const submit=action('保存批注',async()=>{const text=area.value.trim();if(!text){error.textContent='请输入批注';area.focus();return;}try{if(await commit(items=>isNew?[...items,{...note,text}]:items.map(n=>n.id===note.id?{...n,text}:n)))showList();}catch(e){error.textContent=e.message;}});controls.append(submit);
      if(!isNew)controls.append(action('删除批注',async()=>{if(await commit(items=>items.filter(n=>n.id!==note.id)))showList();}));
      area.onkeydown=e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){e.preventDefault();submit.click();}};
    }
    controls.append(action('返回列表',showList));panel.append(controls);paint();area.focus();
  }
  function pick(event){
    const path=event.composedPath(),element=path.find(n=>n instanceof Element),component=path.find(n=>n instanceof Element&&root.contains(n)&&n.hasAttribute('data-component-id'));
    if(!element||!root.contains(event.target)||path.some(n=>n instanceof Element&&n.matches('.toolbar,.markdown-toolbar,.markdown-editor-pane,.page-switch')))return null;
    let target=component||element.closest(textBlocks)||element;
    if(!component&&(!target.matches(textBlocks)||!quote(target)))target=root;
    const scope=component?'component':target===root?'page':'text';
    const anchor={scope,quote:scope==='text'?quote(target):quote(element)};
    if(scope==='text')anchor.occurrence=[...root.querySelectorAll(textBlocks)].filter(n=>quote(n)===anchor.quote).indexOf(target);
    return {target,element,componentId:component?.dataset.componentId||null,anchor};
  }
  function stop(e){e.preventDefault();e.stopImmediatePropagation();}
  root.addEventListener('pointerdown',e=>{if(!active||readOnly||saving||!e.isPrimary||e.button!==0)return;const hit=pick(e);if(!hit)return;stop(e);gesture={...hit,x:e.clientX,y:e.clientY,pointerId:e.pointerId};root.setPointerCapture(e.pointerId);},true);
  root.addEventListener('pointermove',e=>{
    if(!active||readOnly)return;
    if(gesture){stop(e);setOutline({left:Math.min(e.clientX,gesture.x),top:Math.min(e.clientY,gesture.y),width:Math.abs(e.clientX-gesture.x),height:Math.abs(e.clientY-gesture.y)});}
    else if(!draft&&!selected){const hit=pick(e);setOutline(hit?.element.getBoundingClientRect());}
  },true);
  root.addEventListener('pointerup',e=>{
    if(!gesture)return;stop(e);const g=gesture;gesture=null;root.releasePointerCapture(g.pointerId);
    const dragging=Math.hypot(e.clientX-g.x,e.clientY-g.y)>6;
    const rect=dragging?{left:Math.min(e.clientX,g.x),top:Math.min(e.clientY,g.y),width:Math.abs(e.clientX-g.x),height:Math.abs(e.clientY-g.y)}:g.element.getBoundingClientRect();
    // A selection crossing a component boundary belongs to the page.
    const base=g.target.getBoundingClientRect();if(dragging&&(rect.left<base.left||rect.top<base.top||rect.left+rect.width>base.right||rect.top+rect.height>base.bottom)){g.target=root;g.componentId=null;g.anchor={scope:'page',quote:''};}
    g.anchor.rect=relativeRect(rect,g.target.getBoundingClientRect());g.anchor.kind=dragging?'area':'element';
    openNote({id:'note-'+crypto.randomUUID(),componentId:g.componentId,text:'',createdAt:new Date().toISOString(),anchor:g.anchor},true);
  },true);
  root.addEventListener('pointercancel',()=>{gesture=null;paint();},true);
  for(const type of ['click','dblclick','mousedown','touchstart'])root.addEventListener(type,e=>{if(active&&!readOnly&&pick(e))stop(e);},{capture:true,passive:false});
  document.addEventListener('keydown',e=>{if(active&&e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();setActive(false);}},true);
  window.addEventListener('scroll',schedule,true);window.addEventListener('resize',schedule);
  new ResizeObserver(schedule).observe(root);new MutationObserver(schedule).observe(root,{childList:true,subtree:true,characterData:true});
  layer.hidden=true;panel.hidden=true;outline.hidden=true;
  return {get active(){return active;},toggle(){setActive(!active);},reset(){if(active)setActive(false);},refresh(){const id=getDocument()?.id;if(pageId&&id!==pageId)setActive(false);pageId=id;schedule();}};
}
