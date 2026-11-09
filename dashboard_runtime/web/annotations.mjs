import {reviewId,REVIEW_LIMITS,reviewCategory,reviewStatus,reviewAuthor,reviewReplies,createReview,appendReview,changeReview,editReview,addReviewReply,editReviewReply,deleteReviewReply,setReviewStatus,requestReviewAgent,reviewContextText,clusterReviewPins} from './review-state.mjs';
import {findAnnotationElement,chartForAnnotation,pickAnnotationPoint,resolveAnnotationPoint,annotationFilterKey} from './annotation-points.mjs';

const L={
  title:'\u6279\u6ce8',panel:'\u6279\u6ce8\u9762\u677f',add:'\u65b0\u589e\u6279\u6ce8',save:'\u4fdd\u5b58\u6279\u6ce8',attach:'\u9644\u5230\u5bf9\u8bdd',
  close:'\u5173\u95ed\u6279\u6ce8\u9762\u677f',back:'\u8fd4\u56de\u5217\u8868',empty:'\u6682\u65e0\u6279\u6ce8\u3002\u70b9\u51fb\u5143\u7d20\u6216\u62d6\u9009\u533a\u57df\u5f00\u59cb\u3002',
  hint:'\u70b9\u51fb\u5143\u7d20\u6216\u62d6\u9009\u533a\u57df\u6dfb\u52a0\u6279\u6ce8 \u00b7 Esc \u9000\u51fa',page:'\u9875\u9762',
  open:'\u672a\u89e3\u51b3',resolved:'\u5df2\u89e3\u51b3',all:'\u5168\u90e8',resolve:'\u6807\u8bb0\u5df2\u89e3\u51b3',reopen:'\u91cd\u65b0\u6253\u5f00',
  explanation:'\u6570\u636e\u89e3\u91ca',insight:'\u5206\u6790\u6d1e\u5bdf',review:'\u5ba1\u9605\u6279\u6ce8',human:'\u4eba\u5de5',ai:'AI',unknown:'\u6765\u6e90\u672a\u6807\u6ce8',
  reply:'\u56de\u590d',edit:'\u4fee\u6539',remove:'\u5220\u9664',deleteNote:'\u5220\u9664\u6279\u6ce8',content:'\u4f4d\u7f6e\u6279\u6ce8\u5185\u5bb9',newContent:'\u65b0\u589e\u4f4d\u7f6e\u6279\u6ce8',
  unavailable:'\u539f\u4f4d\u7f6e\u5df2\u5931\u6548\uff0c\u6279\u6ce8\u5df2\u4fdd\u7559',filtersChanged:'\u5f53\u524d\u7b5b\u9009\u4e0e\u6279\u6ce8\u65f6\u4e0d\u540c',
  request:'\u8bf7\u6c42 Agent \u5904\u7406',requested:'\u5f85 Agent \u8bfb\u53d6\uff08\u672a\u81ea\u52a8\u53d1\u9001\uff09',
  agentHelp:'\u6b64\u64cd\u4f5c\u53ea\u8bb0\u5f55\u5904\u7406\u8bf7\u6c42\uff0c\u4e0d\u4f1a\u81ea\u52a8\u542f\u52a8 Agent\u3002\u8bf7\u5728\u5bf9\u8bdd\u4e2d\u8981\u6c42 Agent \u8bfb\u53d6 dashboard_annotations\u3002',
  discard:'\u653e\u5f03\u5c1a\u672a\u4fdd\u5b58\u7684\u4fee\u6539\uff1f',confirmDelete:'\u786e\u8ba4\u5220\u9664\u8fd9\u6761\u6279\u6ce8\u53ca\u5176\u56de\u590d\uff1f',
  confirmReplyDelete:'\u786e\u8ba4\u5220\u9664\u8fd9\u6761\u56de\u590d\uff1f',input:'\u8bf7\u8f93\u5165\u6279\u6ce8',limit:'\u5df2\u8fbe\u5230\u6570\u91cf\u4e0a\u9650',
  restore:'\u6062\u590d\u672a\u4fdd\u5b58\u8349\u7a3f',missingDraft:'\u539f\u6279\u6ce8\u5df2\u5220\u9664\uff0c\u8349\u7a3f\u4ec5\u4f9b\u590d\u5236',
  point:'\u6570\u636e\u70b9',category:'\u6279\u6ce8\u7c7b\u578b',thread:'\u56de\u590d\u7ebf\u7a0b',sourceNotice:'\u6765\u6e90\u4e3a\u58f0\u660e\u4fe1\u606f\uff0c\u4e0d\u4ee3\u8868\u8d26\u53f7\u8eab\u4efd\u8ba4\u8bc1\u3002'
};
const node=(tag,cls='',text='')=>{const n=document.createElement(tag);n.className=cls;n.textContent=text;return n;};
const clamp=n=>Math.max(0,Math.min(1,Number.isFinite(n)?n:0));
export function relativeRect(rect,base){
  if(!(base.width>0&&base.height>0))return {x:0,y:0,width:0,height:0};
  const x=clamp((rect.left-base.left)/base.width),y=clamp((rect.top-base.top)/base.height);
  return {x,y,width:Math.min(1-x,clamp(rect.width/base.width)),height:Math.min(1-y,clamp(rect.height/base.height))};
}
export function absoluteRect(rect,base){return {left:base.left+rect.x*base.width,top:base.top+rect.y*base.height,width:rect.width*base.width,height:rect.height*base.height};}
const textBlocks='p,h1,h2,h3,h4,li,blockquote,td,th,.text-block,.dashboard-description';
const quote=n=>(n?.textContent||'').trim().slice(0,1000);
const editable=element=>element?.closest?.('input,textarea,select,[contenteditable=""],[contenteditable="true"],[role="textbox"]');

export function createAnnotations({root,getDocument,save,readOnly,onError=console.error,onMode=()=>{},iconButton,attachContext=null}){
  const layer=node('div','annotation-layer'),outline=node('div','annotation-outline'),pins=node('div','annotation-pins'),panel=node('aside','annotation-panel'),hint=node('div','annotation-hint',L.hint);
  panel.setAttribute('aria-label',L.panel);layer.append(outline,pins,hint,panel);
  const disposers=[],drafts=new Map();
  let active=false,selected=null,draft=null,gesture=null,frame=0,pageId=null,saving=false,opener=null,dirty=false,mounted=false,destroyed=false,filter='open',pinSignature='';
  let rootArea=null,categorySelect=null,replyArea=null,currentNew=false,editingReply=null,replyEditor=null;
  const notes=()=>getDocument()?.manifest.annotations||[];
  const board=()=>getDocument()?.id;
  const hostFor=id=>[...root.querySelectorAll('[data-component-id]')].find(n=>n.dataset.componentId===id);
  const current=id=>notes().find(note=>note.id===id);
  function targetFor(note){
    if(note.componentId)return hostFor(note.componentId)||null;
    if(note.anchor?.scope==='text')return [...root.querySelectorAll(textBlocks)].filter(n=>quote(n)===note.anchor.quote)[note.anchor.occurrence||0]||null;
    return root;
  }
  function filterMismatch(note){return note.anchor?.point&&note.anchor.filterKey!==undefined&&note.anchor.filterKey!==annotationFilterKey(getDocument());}
  function bounds(note){
    const target=targetFor(note);if(!target)return null;
    if(note.anchor?.point)return filterMismatch(note)?null:resolveAnnotationPoint(chartForAnnotation(target),note.anchor.point);
    if(note.anchor?.kind==='element'&&note.anchor.elementId){
      const element=findAnnotationElement(target,note.anchor.elementId);
      return element?.getBoundingClientRect()||null;
    }
    const base=target.getBoundingClientRect();
    if(!(base.width>0&&base.height>0))return null;
    return note.anchor?.rect?absoluteRect(note.anchor.rect,base):{left:base.left+8,top:base.top+8,width:0,height:0};
  }
  function setOutline(rect){outline.hidden=!rect;if(rect)Object.assign(outline.style,{left:rect.left+'px',top:rect.top+'px',width:Math.max(2,rect.width)+'px',height:Math.max(2,rect.height)+'px'});}
  function schedule(){if(active&&!frame)frame=requestAnimationFrame(()=>{frame=0;paint();});}
  function visibleNotes(){return notes().filter(note=>filter==='all'||reviewStatus(note)===filter);}
  function paint(){
    layer.hidden=!active;if(!active)return;
    const entries=[];
    visibleNotes().forEach(note=>{const rect=bounds(note);if(!rect)return;
      if(rect.top<8||rect.top>innerHeight-10||rect.left<8||rect.left>innerWidth-10)return;
      const panelBox=panel.hidden?null:panel.getBoundingClientRect();
      if(panelBox&&rect.left>=panelBox.left&&rect.left<=panelBox.right&&rect.top>=panelBox.top&&rect.top<=panelBox.bottom)return;
      entries.push({note,x:rect.left,y:rect.top,index:notes().indexOf(note)+1});
    });
    const signature=JSON.stringify(entries.map(e=>[e.note.id,e.note.updatedAt,e.note.text,e.note.status,e.x,e.y]));
    if(signature!==pinSignature){
      pinSignature=signature;pins.replaceChildren();
      for(const group of clusterReviewPins(entries)){
        const first=group.items[0],count=group.items.length,pin=node('button','annotation-pin',count>1?String(count):String(first.index));
        pin.type='button';pin.dataset.cluster=String(count>1);pin.dataset.status=reviewStatus(first.note);
        pin.title=group.items.map(item=>`${item.index}. ${item.note.text}`).join('\n').slice(0,4000);
        pin.setAttribute('aria-label',count>1?`${L.title} ${count}`:`${L.title} ${first.index}: ${first.note.text}`);
        Object.assign(pin.style,{left:group.x+'px',top:group.y+'px'});
        pin.onclick=()=>{if(discard())count>1?showList(group.items.map(item=>item.note.id)):openNote(current(first.note.id)||first.note);};
        pins.append(pin);
      }
    }
    if(!gesture)setOutline(selected?bounds(selected):draft?bounds(draft):null);
  }
  function remember(){
    const note=draft||selected;
    if(dirty&&note&&rootArea)drafts.set(pageId||board(),{note:structuredClone(note),text:rootArea.value,category:categorySelect?.value||reviewCategory(note),reply:replyArea?.value||'',isNew:currentNew,editingReply,replyEditText:replyEditor?.value});
  }
  function discard(){return !saving&&(!dirty||window.confirm(L.discard));}
  function listen(target,type,fn,options){target.addEventListener(type,fn,options);disposers.push(()=>target.removeEventListener(type,fn,options));}
  function mount(){
    if(mounted||destroyed)return;mounted=true;document.body.append(layer);
    listen(root,'pointerdown',pointerDown,true);listen(root,'pointermove',pointerMove,true);listen(root,'pointerup',pointerUp,true);
    listen(root,'pointercancel',()=>{gesture=null;paint();},true);
    for(const type of ['click','dblclick','mousedown'])listen(root,type,e=>{if(active&&!readOnly&&pick(e))stop(e);},{capture:true,passive:false});
    listen(document,'keydown',e=>{
      if(e.isComposing)return;
      if(active&&e.key==='Escape'){if(discard()){stop(e);setActive(false);}return;}
      const source=e.composedPath().find(n=>n instanceof Element);
      if(e.key.toLowerCase()==='c'&&!e.metaKey&&!e.ctrlKey&&!e.altKey&&!e.shiftKey&&!editable(source)){
        const toggle=root.querySelector('.annotation-toggle');
        if(toggle&&!toggle.disabled&&!toggle.hidden&&discard()){e.preventDefault();setActive(!active);}
      }
    },true);
    listen(window,'scroll',schedule,true);listen(window,'resize',schedule);listen(window,'pagehide',()=>reset());
    const resized=new ResizeObserver(schedule);resized.observe(root);disposers.push(()=>resized.disconnect());
    const mutated=new MutationObserver(schedule);mutated.observe(root,{childList:true,subtree:true,characterData:true});disposers.push(()=>mutated.disconnect());
  }
  function closePanel(){panel.hidden=true;root.classList.remove('review-panel-open');selected=null;draft=null;dirty=false;paint();}
  function setActive(value){
    mount();active=value;gesture=null;selected=null;draft=null;dirty=false;panel.replaceChildren();panel.hidden=true;hint.hidden=readOnly;pinSignature='';
    root.classList.toggle('is-annotating',active);root.classList.remove('review-panel-open');
    if(active)opener=document.activeElement;else if(opener?.isConnected)opener.focus();
    onMode(active);if(active)showList();paint();
  }
  function reset(){
    remember();active=false;gesture=null;selected=null;draft=null;dirty=false;root.classList.remove('is-annotating','review-panel-open');onMode(false);
    if(frame){cancelAnimationFrame(frame);frame=0;}
    disposers.splice(0).forEach(dispose=>dispose());layer.hidden=true;panel.hidden=true;layer.remove();mounted=false;pinSignature='';
  }
  function action(label,run){const b=node('button','',label);b.type='button';b.onclick=()=>Promise.resolve().then(run).catch(onError);return b;}
  function header(title){
    panel.replaceChildren();panel.hidden=false;root.classList.add('review-panel-open');
    const h=node('header'),close=()=>{if(discard())closePanel();};
    h.append(node('strong','',title),iconButton?iconButton('close',L.close,close):action(L.close,close));panel.append(h);
    rootArea=null;categorySelect=null;replyArea=null;editingReply=null;replyEditor=null;dirty=false;
  }
  function provenance(item){const author=reviewAuthor(item.author),text=[L[author.kind],author.name].filter(Boolean).join(' \u00b7 ');return node('span','annotation-source',text);}
  function showList(ids=null){
    selected=null;draft=null;header(`${L.title}\uff08${notes().length}\uff09`);
    const tabs=node('div','annotation-filters');
    for(const value of ['open','resolved','all']){const b=action(L[value],()=>{filter=value;showList();});b.setAttribute('aria-pressed',String(value===filter));tabs.append(b);}panel.append(tabs);
    const list=node('div','annotation-panel-list'),items=ids?notes().filter(n=>ids.includes(n.id)):visibleNotes();
    if(!items.length)list.append(node('p','muted',L.empty));
    for(const note of items){
      const item=action(`${notes().indexOf(note)+1}. ${note.text}`,()=>{const target=targetFor(note);target?.scrollIntoView({block:'start',behavior:'smooth'});openNote(note);});
      item.className='annotation-list-entry';
      item.append(node('span','annotation-label',`${L[reviewCategory(note)]} \u00b7 ${L[reviewStatus(note)]}`),provenance(note));
      if(reviewReplies(note).length)item.append(node('span','muted',`${L.reply} ${reviewReplies(note).length}`));
      if(!bounds(note))item.append(node('span','annotation-location-warning',filterMismatch(note)?L.filtersChanged:L.unavailable));
      list.append(item);
    }
    panel.append(list);
    const saved=drafts.get(board());
    if(saved)panel.append(action(L.restore,()=>{
      const found=current(saved.note.id);
      if(!saved.isNew&&!found){header(L.missingDraft);const text=node('textarea');text.value=saved.text+'\n\n'+saved.reply;panel.append(text,action(L.back,()=>showList()));return;}
      openNote(found||saved.note,saved.isNew,saved);
    }));
    paint();
  }
  async function commit(transform){
    if(saving||readOnly)return false;saving=true;
    const controls=[...panel.querySelectorAll('button,textarea,select')].map(n=>[n,n.disabled]);controls.forEach(([n])=>n.disabled=true);
    try{await save(transform);dirty=false;drafts.delete(board());return true;}
    finally{saving=false;controls.forEach(([n,disabled])=>n.disabled=disabled);}
  }
  function openNote(note,isNew=false,restored=null){
    note=structuredClone(note); // Compare edits against an immutable opening snapshot.
    selected=isNew?null:note;draft=isNew?note:null;currentNew=isNew;header(isNew?L.add:L.title);
    const label=note.componentId?getDocument()?.manifest.components[note.componentId]?.title:L.page;
    panel.append(node('p','muted annotation-context',!isNew&&!bounds(note)?(filterMismatch(note)?L.filtersChanged:L.unavailable):(note.anchor?.point?.label||note.anchor?.quote||label||L.page)));
    const info=node('div','annotation-meta');info.append(provenance(note),node('span','annotation-label',L[reviewStatus(note)]));panel.append(info);
    const category=node('select');category.setAttribute('aria-label',L.category);
    for(const value of ['explanation','insight','review']){const option=node('option','',L[value]);option.value=value;category.append(option);}
    category.value=restored?.category||reviewCategory(note);category.disabled=readOnly;categorySelect=category;panel.append(category);
    const area=node('textarea');area.value=restored?.text??(isNew?'':note.text);area.maxLength=REVIEW_LIMITS.text;area.setAttribute('aria-label',isNew?L.newContent:L.content);area.disabled=readOnly;rootArea=area;panel.append(area);
    const error=node('p','annotation-error');error.setAttribute('role','alert');panel.append(error);
    const execute=async fn=>{error.textContent='';try{await fn();}catch(e){error.textContent=e.message||String(e);remember();}};
    const controls=node('div','annotation-panel-actions');
    if(!readOnly){
      const submit=action(attachContext?L.attach:L.save,()=>execute(async()=>{
        if(saving)return;
        if(!area.value.trim()){error.textContent=L.input;area.focus();return;}
        if(attachContext){
          saving=true;submit.disabled=true;
          try{await attachContext({...note,text:reviewContextText({...note,text:area.value.trim()}),category:category.value});dirty=false;drafts.delete(board());closePanel();}
          finally{saving=false;submit.disabled=false;}
        }else{
          if((replyArea?.value.trim()||replyEditor)&&!window.confirm(L.discard))return;
          const text=area.value,kind=category.value;
          const success=await commit(items=>isNew?appendReview(items,createReview(note,text,{category:kind})):changeReview(items,note.id,n=>editReview(n,text,{expectedText:note.text,category:kind})));
          if(success)openNote(current(note.id));
        }
      }));controls.append(submit);
      area.onkeydown=e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){e.preventDefault();submit.click();}};
    }
    controls.append(action(L.back,()=>{if(discard())showList();}));panel.append(controls);
    if(!isNew){
      const thread=node('section','annotation-thread');thread.setAttribute('aria-label',L.thread);
      for(const message of reviewReplies(note)){
        const entry=node('article','annotation-message'),meta=node('div','annotation-meta');meta.append(provenance(message));
        const time=node('time','muted',message.createdAt||'');if(message.createdAt)time.dateTime=message.createdAt;meta.append(time);entry.append(meta,node('p','',message.text));
        if(!readOnly&&!attachContext){
          const tools=node('div','annotation-message-actions');
          tools.append(action(L.edit,()=>{
            if(!discard())return;const editor=node('textarea');editor.value=message.text;editor.maxLength=REVIEW_LIMITS.text;editor.setAttribute('aria-label',`${L.edit}${L.reply}`);editingReply=message.id;replyEditor=editor;entry.replaceChildren(meta,editor);
            editor.oninput=()=>{dirty=true;};
            entry.append(action(L.save,()=>execute(async()=>{if(await commit(items=>changeReview(items,note.id,n=>editReviewReply(n,message.id,editor.value,{expectedText:message.text}))))openNote(current(note.id));})));
          }),action(L.remove,()=>execute(async()=>{if(discard()&&window.confirm(L.confirmReplyDelete)&&await commit(items=>changeReview(items,note.id,n=>deleteReviewReply(n,message.id))))openNote(current(note.id));})));
          entry.append(tools);
        }
        thread.append(entry);
      }
      panel.append(thread);
      if(!readOnly&&!attachContext){
        if(reviewStatus(note)==='open'&&reviewReplies(note).length<REVIEW_LIMITS.replies){
          const reply=node('textarea');reply.placeholder=L.reply;reply.setAttribute('aria-label',L.reply);reply.maxLength=REVIEW_LIMITS.text;reply.value=restored?.reply||'';replyArea=reply;
          const send=action(L.reply,()=>execute(async()=>{if(!reply.value.trim()){reply.focus();return;}if((area.value!==note.text||category.value!==reviewCategory(note)||replyEditor)&&!window.confirm(L.discard))return;if(await commit(items=>changeReview(items,note.id,n=>addReviewReply(n,reply.value))))openNote(current(note.id));}));
          reply.onkeydown=e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){e.preventDefault();send.click();}};panel.append(reply,send);
        }
        const management=node('div','annotation-panel-actions');
        management.append(action(reviewStatus(note)==='resolved'?L.reopen:L.resolve,()=>execute(async()=>{if(discard()&&await commit(items=>changeReview(items,note.id,n=>setReviewStatus(n,reviewStatus(n)==='resolved'?'open':'resolved'))))openNote(current(note.id));})));
        if(reviewStatus(note)==='open'){
          const request=action(note.agentRequest?.status==='requested'?L.requested:L.request,()=>execute(async()=>{if(discard()&&await commit(items=>changeReview(items,note.id,n=>requestReviewAgent(n))))openNote(current(note.id));}));
          request.disabled=note.agentRequest?.status==='requested';management.append(request);panel.append(node('p','muted annotation-agent-help',L.agentHelp));
        }
        management.append(action(L.deleteNote,()=>execute(async()=>{if(discard()&&window.confirm(L.confirmDelete)&&await commit(items=>items.filter(n=>n.id!==note.id)))showList();})));
        panel.append(management);
      }
    }
    panel.append(node('p','muted annotation-source-notice',L.sourceNotice));
    for(const control of panel.querySelectorAll('textarea,select'))control.addEventListener('input',()=>{dirty=true;});
    if(restored?.replyEditText!==undefined){
      const recovered=node('textarea');recovered.value=restored.replyEditText;recovered.readOnly=true;recovered.setAttribute('aria-label','Recovered reply draft');
      panel.append(node('p','muted',L.restore+' ('+L.reply+')'),recovered);
    }
    dirty=Boolean(restored);paint();if(!readOnly)area.focus();
  }
  function pick(event){
    const path=event.composedPath(),element=path.find(n=>n instanceof Element),component=path.find(n=>n instanceof Element&&root.contains(n)&&n.hasAttribute('data-component-id'));
    if(!element||!root.contains(event.target)||path.some(n=>n instanceof Element&&n.matches('.toolbar,.markdown-toolbar,.markdown-editor-pane,.page-switch')))return null;
    let target=component||element.closest(textBlocks)||element;
    if(!component&&(!target.matches(textBlocks)||!quote(target)))target=root;
    const scope=component?'component':target===root?'page':'text',anchor={scope,quote:scope==='text'?quote(target):quote(element)};
    if(scope==='text')anchor.occurrence=[...root.querySelectorAll(textBlocks)].filter(n=>quote(n)===anchor.quote).indexOf(target);
    return {target,element,componentId:component?.dataset.componentId||null,anchor};
  }
  function stop(e,allowScroll=false){if(!allowScroll)e.preventDefault();e.stopImmediatePropagation();}
  function pointerDown(e){
    if(!active||readOnly||saving||!e.isPrimary||e.button!==0)return;
    const hit=pick(e);if(!hit||!discard())return;
    stop(e,e.pointerType==='touch');gesture={...hit,x:e.clientX,y:e.clientY,pointerId:e.pointerId};root.setPointerCapture(e.pointerId);
  }
  function pointerMove(e){
    if(!active||readOnly)return;
    if(gesture){stop(e,e.pointerType==='touch');setOutline({left:Math.min(e.clientX,gesture.x),top:Math.min(e.clientY,gesture.y),width:Math.abs(e.clientX-gesture.x),height:Math.abs(e.clientY-gesture.y)});}
    else if(!draft&&!selected){const hit=pick(e);setOutline(hit?.element.getBoundingClientRect());}
  }
  function pointerUp(e){
    if(!gesture)return;stop(e);const g=gesture;gesture=null;if(root.hasPointerCapture(g.pointerId))root.releasePointerCapture(g.pointerId);
    if(notes().length>=REVIEW_LIMITS.notes&&!attachContext){onError(Error(L.limit));return;}
    const dragging=Math.hypot(e.clientX-g.x,e.clientY-g.y)>6;
    let rect=dragging?{left:Math.min(e.clientX,g.x),top:Math.min(e.clientY,g.y),width:Math.abs(e.clientX-g.x),height:Math.abs(e.clientY-g.y)}:g.element.getBoundingClientRect();
    const base=g.target.getBoundingClientRect();
    if(dragging&&(rect.left<base.left||rect.top<base.top||rect.left+rect.width>base.right||rect.top+rect.height>base.bottom)){g.target=root;g.componentId=null;g.anchor={scope:'page',quote:''};}
    if(!dragging&&g.componentId){
      const component=getDocument()?.manifest.components[g.componentId];
      if(component?.kind==='chart'||component?.kind==='legacy'&&(component.family||'chart')==='chart'){
        const chart=chartForAnnotation(g.target),point=pickAnnotationPoint(chart,e.clientX,e.clientY);
        if(point){g.anchor.point=point;g.anchor.filterKey=annotationFilterKey(getDocument());rect=resolveAnnotationPoint(chart,point)||rect;}
      }
      if(!g.anchor.point&&g.element.id&&g.element!==g.target)g.anchor.elementId=g.element.id;
    }
    g.anchor.rect=relativeRect(rect,g.target.getBoundingClientRect());g.anchor.kind=dragging?'area':'element';
    openNote({id:reviewId('note'),componentId:g.componentId,text:'',createdAt:new Date().toISOString(),anchor:g.anchor},true);
  }
  layer.hidden=true;panel.hidden=true;outline.hidden=true;mount();
  return {
    get active(){return active;},toggle(){if(discard())setActive(!active);},reset,
    refresh(){const id=board();if(pageId&&id!==pageId)reset();pageId=id;mount();schedule();},
    destroy(){reset();destroyed=true;drafts.clear();}
  };
}
