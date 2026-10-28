import {createProgressiveLoader} from './progressive.mjs';
import {createAnnotations} from './annotations.mjs';
import {inlineEdit,clearInlineEdit} from './inline-edit.mjs';
import {reportMarkdown,renderReport} from './report.mjs';
import {whileVisible} from './lifecycle.mjs';
import {icon,iconButton,openMenu,closeMenu,adaptiveActions} from './icons.mjs';
import {initializeOriginal,mountOriginal,appendOriginalStyle,catalog} from './original.mjs';
import {visibleRows,csv,chartTypes} from './engine.mjs';
import {mountStatisticalImage,updateStatisticalArtifacts} from './statistical.mjs';
import {decodeToolResult,resolveToolResult} from './tool-result.mjs';
import {pagedFilter,singleFilter,clearFilterValues} from './local-filter.mjs';
import {linkageValue,linkagePoint} from './linkage.mjs';
const T={edit:'编辑',view:'退出编辑',add:'添加组件',import:'导入数据',undo:'撤销',redo:'重做',reload:'重新读取',export:'导出',close:'关闭',save:'保存',data:'数据',semantic:'指标语义',settings:'图表设置',source:'查询来源',remove:'删除',copy:'复制',empty:'导入数据，或通过 CLI / MCP 添加组件。'};
const el=(tag,cls='',text='')=>{const n=document.createElement(tag);n.className=cls;n.textContent=text;return n;};
const button=(label,fn,cls='')=>{const b=el('button',cls,label);b.type='button';b.onclick=()=>Promise.resolve().then(fn).catch(showError);return b;};
function showError(error){const n=document.getElementById('notice');if(n){if(n.closest('.toolbar'))document.querySelector('.dashboard-heading')?.append(n);n.textContent=error.message||String(error);n.className='notice error';n.hidden=false;}else console.error(error);}
function download(name,body,type='application/json'){const a=el('a');a.href=URL.createObjectURL(new Blob([body],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
function field(label,node){const wrap=el('label','field');wrap.append(el('span','',label),node);return wrap;}
function input(value='',kind='text'){const n=el('input');n.type=kind;n.value=value;return n;}
function select(options,value){const n=el('select');for(const [key,label] of options){const o=el('option','',label);o.value=key;n.append(o);}n.value=value??options[0]?.[0]??'';return n;}
function textarea(value){const n=el('textarea');n.value=typeof value==='string'?value:JSON.stringify(value,null,2);n.spellcheck=false;return n;}
function dialog(title){const d=el('dialog','inspector'),head=el('header'),body=el('div','inspector-body');head.append(el('h2','',title),iconButton('close',T.close,()=>d.close()));d.append(head,body);d.addEventListener('close',()=>d.remove());document.body.append(d);d.showModal();return {d,body};}
function table(rows,{paginate=true,labels={}}={}){
  const wrap=el('div','data-table'),controls=el('div','table-controls'),body=el('div','table-scroll');
  let page=0,sortKey=null,asc=true;const size=paginate?20:Math.max(rows.length,1),keys=[...new Set(rows.flatMap(r=>Object.keys(r)))];
  function render(){body.replaceChildren();controls.replaceChildren();const data=[...rows];
    if(sortKey)data.sort((a,b)=>{const x=a[sortKey],y=b[sortKey];return (typeof x==='number'&&typeof y==='number'?x-y:String(x??'').localeCompare(String(y??''),'zh-CN',{numeric:true}))*(asc?1:-1);});
    const t=el('table'),tr=el('tr');for(const key of keys){const th=el('th'),sort=button(labels[key]||key,()=>{asc=sortKey===key?!asc:true;sortKey=key;page=0;render();});if(sortKey===key)sort.append(icon(asc?'up':'down'));th.setAttribute('aria-sort',sortKey===key?(asc?'ascending':'descending'):'none');th.append(sort);tr.append(th);}const thead=el('thead');thead.append(tr);t.append(thead);
    const tbody=el('tbody');for(const row of data.slice(page*size,(page+1)*size)){const r=el('tr');for(const key of keys)r.append(el('td','',String(row[key]??'—')));tbody.append(r);}t.append(tbody);body.append(t);
    const prev=iconButton('prev','上一页',()=>{page--;render();}),next=iconButton('next','下一页',()=>{page++;render();});prev.disabled=page===0;next.disabled=(page+1)*size>=rows.length;
    controls.append(el('span','muted',paginate?`共 ${rows.length} 条 · 第 ${page+1} 页 · 每页最多 20 行`:`当前数据：${rows.length} 条`));if(paginate)controls.append(prev,next);controls.append(iconButton('export','CSV',()=>download('data.csv',csv(rows),'text/csv;charset=utf-8')));
  }wrap.append(controls,body);render();return wrap;
}
export async function start({echarts,GridStack,App}){
  initializeOriginal(echarts);
  const boot=window.__DASHBOARD_BOOT__||{},root=el('div','workspace');document.body.append(root);
  const top=el('header','topbar'),title=input('Dashboard'),toolbar=el('div','toolbar'),notice=el('div','notice'),filters=el('div','filters'),canvas=el('main','canvas'),gridEl=el('div','grid-stack');
  notice.id='notice';title.className='dashboard-title';title.setAttribute('aria-label','Dashboard title');const description=el('div','dashboard-description'),context=el('div','dashboard-context'),badge=el('span','dashboard-status'),heading=el('div','dashboard-heading'),mark=el('div','document-mark');mark.append(icon('chart'));heading.append(mark,title,description,context,notice);top.append(heading,badge,toolbar);filters.setAttribute('role','region');filters.setAttribute('aria-label','筛选条件');canvas.append(gridEl);root.append(top,filters,canvas);toolbar.setAttribute('role','toolbar');toolbar.setAttribute('aria-label','Dashboard actions');
  let doc=boot.document||null,editing=false,grid=null,undo=[],redo=[],queue=Promise.resolve(),busy=0,layoutTimer=null,pendingLayout=null,dragging=false,renderQueued=false,linkage=null,app=null;
  let lastBreakpoint=null,transport,originalInstances=[],disposeToolbar=null,disposeReport=null;
  let renderedPage=null,renderedMode=null,reportEditing=null,reconciling=false,annotations=null;
  let progressiveLoader=null,progressiveKey='',editBatch=null;
  const fetched=new Set(),visibleComponents=new Set();
  const dataObserver=typeof IntersectionObserver==='undefined'?null:new IntersectionObserver(entries=>{for(const entry of entries){const id=entry.target.dataset.loadId;if(entry.isIntersecting){visibleComponents.add(id);progressiveLoader?.visible();}else visibleComponents.delete(id);}},{rootMargin:'300px'});
  const cards=new Map(),controllers=new Map(),reportHosts=new Map(),pendingMounts=new Map();
  const observer=typeof IntersectionObserver==='undefined'?null:new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){const run=pendingMounts.get(entry.target);if(run){pendingMounts.delete(entry.target);observer.unobserve(entry.target);run();}}},{rootMargin:'300px'});
  let viewTables={},viewGranularities={},viewRequest=0,refreshing=false,lastRefresh=null;
  let pages=[],switchRequest=0,switching=false,pendingView=null,viewRunning=false,viewAbort=null,lastLinkage=null,requestedFilters=null,dirtyViewIds=new Set();
  const titleRow=el('div','dashboard-title-row'),pageSwitch=button('切换页面',showPages,'page-switch');
  title.before(titleRow);titleRow.append(title,pageSwitch);pageSwitch.hidden=true;
  pageSwitch.setAttribute('aria-label','切换页面');pageSwitch.setAttribute('aria-haspopup','menu');pageSwitch.setAttribute('aria-expanded','false');
  const updateNotice=el('div','runtime-update-notice');updateNotice.hidden=true;updateNotice.setAttribute('role','status');top.after(updateNotice);
  let statisticalArtifacts=updateStatisticalArtifacts(Object.create(null),boot),renderedStatisticalArtifacts=null;
  const reportDrafts=new Map();
  const currentDraft=()=>{let draft=reportDrafts.get(doc.id);if(!draft){draft={text:reportMarkdown(doc),saved:reportMarkdown(doc),dirty:false,revision:doc.revision};reportDrafts.set(doc.id,draft);}return draft;};
  const bp=()=>window.innerWidth<650?'mobile':window.innerWidth<1050?'tablet':'desktop';
  const status=text=>{notice.textContent=text;notice.className='notice';};
  const accept=(result,defer=false)=>{if(result?.error)throw Object.assign(Error(result.error.message),{code:result.error.code});if(result?.isError)throw Error(result.content?.[0]?.text||'Tool failed');if(!defer&&!result?.componentIds)statisticalArtifacts=updateStatisticalArtifacts(statisticalArtifacts,result);return result;};
  const unpack=(result,defer=false)=>accept(decodeToolResult(result),defer);
  const deferredResult=name=>['dashboard_get','dashboard_view','dashboard_refresh'].includes(name);
  if(boot.mode==='mcp'){
    app=new App({name:'Charts Design Dashboard',version:'0.6.0'},{},{autoResize:true});
    app.ontoolresult=async result=>{try{
      const incoming=await resolveToolResult(result,(name,args)=>app.callServerTool({name,arguments:args}));
      if(incoming.document&&doc&&incoming.document.id===doc.id&&incoming.document.revision<doc.revision)return;
      const previous=statisticalArtifacts,value=accept(incoming);
      if(value.document){if(doc?.id!==value.document.id){switchRequest++;resetPageState();}if(doc&&(doc.id!==value.document.id||doc.revision!==value.document.revision)){undo=[];redo=[];}doc=value.document;}
      if(value.document&&!doc.computed){await refreshLocal();return;}
      if(value.document||previous!==statisticalArtifacts)render();
    }catch(e){showError(e);}};
    app.onhostcontextchanged=context=>{if(doc&&context.displayMode)render();};
    transport=async(name,args)=>accept(await resolveToolResult(await app.callServerTool({name,arguments:args}),(name,args)=>app.callServerTool({name,arguments:args})),deferredResult(name));await app.connect();
  }else if(boot.mode==='offline'){
    doc=boot.document;transport=async()=>{throw Error('Offline snapshot: use Export JSON and import it through CLI to persist server-side changes.');};editing=false;
  }else{
    const fragment=location.hash.slice(1);let token='';try{token=sessionStorage.getItem('charts-runtime-token')||'';}catch{}
    const explicit=fragment.startsWith('token=');
    // New links identify credentials explicitly. Existing sessions keep document anchors inert.
    if(explicit||(!token&&fragment&&!/^(fig-|report-)/.test(fragment))){token=explicit?decodeURIComponent(fragment.slice(6)):fragment;try{sessionStorage.setItem('charts-runtime-token',token);}catch{}history.replaceState(null,'',location.pathname+location.search);}
    const authHeaders={'Content-Type':'application/json','Authorization':'Bearer '+token};
    transport=async(name,args,options={})=>{const response=await fetch('/api/tools/'+name,{method:'POST',headers:authHeaders,body:JSON.stringify(args),signal:options.signal});return accept(await response.json(),deferredResult(name));};
    const id=new URLSearchParams(location.search).get('board');
    if(id)doc=accept(await transport('dashboard_get',{dashboardId:id,dataMode:'local'})).document;
    else{const boards=(await transport('dashboard_list',{})).dashboards;if(boards.length)doc=accept(await transport('dashboard_get',{dashboardId:boards[0].id,dataMode:'local'})).document;}
  }
  function resetPageState(){progressiveLoader?.stop();progressiveLoader=null;progressiveKey='';fetched.clear();visibleComponents.clear();dataObserver?.disconnect();annotations?.reset();viewAbort?.abort();viewRequest++;requestedFilters=null;dirtyViewIds=new Set();viewTables={};viewGranularities={};linkage=null;undo=[];redo=[];lastRefresh=null;editing=false;}
  function renderPageSwitch(){
    const available=pages.filter(page=>page.id!==doc?.id);
    pageSwitch.hidden=boot.mode==='offline'||!doc||!available.length;
    pageSwitch.disabled=switching;pageSwitch.replaceChildren();
    if(!editing&&doc)pageSwitch.append(el('span','page-switch-title',doc.manifest.title));
    pageSwitch.append(icon('chevronDown'));title.hidden=!pageSwitch.hidden&&!editing;
  }
  async function refreshPages(){
    pages=(await transport('dashboard_list',{})).dashboards;renderPageSwitch();
  }
  async function showPages(){
    await refreshPages();
    if(pageSwitch.hidden)return;
    const current={id:doc.id,title:doc.manifest.title};
    openMenu(pageSwitch,[current,...pages.filter(page=>page.id!==current.id)].map(page=>({label:page.title,icon:'chart',checked:page.id===doc.id,run:()=>switchPage(page.id)})),{label:'切换页面',align:'start'});
  }
  async function switchPage(id){
    if(id===doc?.id)return;
    const request=++switchRequest;switching=true;renderPageSwitch();
    try{
      saveLayout();await queue;
      const result=await transport('dashboard_get',{dashboardId:id,dataMode:'local'});
      if(request!==switchRequest)return;
      resetPageState();doc=accept(result).document;render();
      if(boot.mode!=='mcp'){const url=new URL(location.href);url.searchParams.set('board',id);history.replaceState(null,'',url);}
    }finally{switching=false;renderPageSwitch();}
  }
  async function mutate(name,args,pushUndo=true,rerender=true){
    if(!doc)throw Error('Create a dashboard first');
    const run=async()=>{busy++;const previous=doc.revision;try{const request=typeof args==='function'?args():args;const result=await transport(name,{...request,dataMode:'local',dashboardId:doc.id,expectedRevision:request.expectedRevision??doc.revision});if(result.document){if(pushUndo&&!doc.progressive){undo.push(previous);redo=[];}doc=result.document;requestedFilters=null;const pending=reportDrafts.get(doc.id);if(pending&&reportMarkdown(doc)===pending.saved)pending.revision=doc.revision;if(rerender)render();else{statusLine();const u=toolbar.querySelector('[aria-label="'+T.undo+'"]'),r=toolbar.querySelector('[aria-label="'+T.redo+'"]');if(u)u.disabled=!undo.length;if(r)r.disabled=!redo.length;}}return result;}catch(e){showError(e);throw e;}finally{busy--;}};
    const next=queue.then(run,run);queue=next.catch(()=>{});return next;
  }
  function ensureProgressive(){
    const key=doc.id+':'+doc.revision+':'+doc.dataVersion;
    if(progressiveKey===key)return;
    progressiveLoader?.stop();progressiveKey=key;fetched.clear();
    progressiveLoader=createProgressiveLoader({delay:doc.loading?.debounceMs??150,concurrency:doc.loading?.maxConcurrent??4,
      visible:id=>!dataObserver||visibleComponents.has(id),
      loading:(id,value)=>{const card=cards.get(id)?.card||reportHosts.get(id);if(card){card.setAttribute('aria-busy',String(value));card.dataset.loading=value?'true':'false';}},
      query:async(id,sequence)=>{
        const current=doc.id,base=requestedFilters||doc.manifest.filters,filters=linkage&&!editing?[...base.filter(f=>f.id!=='runtime-linkage'),...viewDoc().manifest.filters.filter(f=>f.id==='runtime-linkage')]:base;
        const result=await transport('dashboard_view',{dashboardId:current,responseMode:'patch',componentIds:[id],expectedRevision:doc.revision,dataVersion:doc.dataVersion,filterSequence:sequence,filters,tableStates:viewTables,granularities:viewGranularities});
        return result;
      },
      apply:(id,result)=>{
        if(progressiveKey!==key||result.revision!==doc.revision)return;
        const computed={...doc.computed};for(const map of ['components','tables','grouped','filterOptions','filterPages'])computed[map]={...computed[map],...result.computed?.[map]};
        doc={...doc,computed};fetched.add(id);statisticalArtifacts=updateStatisticalArtifacts(statisticalArtifacts,{statisticalArtifacts:{...statisticalArtifacts,...result.statisticalArtifacts}});
        const card=cards.get(id)?.card||reportHosts.get(id);if(card){card.querySelector('.component-load-error')?.remove();mountComponent(card,id,false,true);}
        transport('runtime_report_error',{dashboardId:doc.id,revision:doc.revision,requestId:result.requestId||'',code:'CLIENT_DATA_APPLIED'}).catch(()=>{});
      },
      failed:(id,error)=>{const card=cards.get(id)?.card||reportHosts.get(id);if(card){card.querySelector('.component-load-error')?.remove();const message=el('div','component-load-error',error.message);message.append(button('重试',()=>progressiveLoader.need(id)));card.append(message);}if(error.code==='REVISION_CONFLICT')reload().catch(showError);}
    });
  }
  function refreshLocal(filters=requestedFilters||doc.manifest.filters,componentIds=null){
    if(doc.progressive){ensureProgressive();requestedFilters=filters;doc.manifest.filters=filters;progressiveLoader.invalidate(componentIds||Object.keys(doc.manifest.components));render();return Promise.resolve();}
    requestedFilters=filters;if(componentIds===null)dirtyViewIds=null;else if(dirtyViewIds)componentIds.forEach(id=>dirtyViewIds.add(id));componentIds=dirtyViewIds?[...dirtyViewIds]:null;
    const request=++viewRequest,id=doc.id;
    return new Promise((resolve,reject)=>{
      const waiters=pendingView?.waiters||[];waiters.push({resolve,reject});
      // A pending full/filter update subsumes a subsequent table-only update.
      const ids=pendingView?(pendingView.componentIds===null||componentIds===null?null:[...new Set([...pendingView.componentIds,...componentIds])]):componentIds;
      pendingView={request,id,filters,componentIds:ids,waiters};queueMicrotask(drainViews);
    });
  }
  async function drainViews(){
    if(viewRunning)return;viewRunning=true;
    try{while(pendingView){
      const job=pendingView;pendingView=null;const {request,id,componentIds,waiters}=job;
      try{
        if(doc.id!==id){waiters.forEach(w=>w.resolve());continue;}
        const base=job.filters.filter(f=>f.id!=='runtime-linkage'),active=linkage&&!editing?viewDoc().manifest.filters.filter(f=>f.id==='runtime-linkage'):[];
        viewAbort=new AbortController();
        const args={dashboardId:id,responseMode:'patch',expectedRevision:doc.revision,filters:[...base,...active],tableStates:viewTables,granularities:viewGranularities,...(componentIds?{componentIds}:{})};
        let result;
        try{result=await transport('dashboard_view',args,{signal:viewAbort.signal});}
        catch(error){
          if(error.code!=='REVISION_CONFLICT')throw error;
          result=await transport('dashboard_refresh',{dashboardId:id,dataMode:'local',filters:args.filters,tableStates:viewTables,granularities:viewGranularities},{signal:viewAbort.signal});
        }
        if(request===viewRequest&&doc.id===id){
          if(result.document){doc=accept(result).document;doc.manifest.filters=doc.manifest.filters.filter(f=>f.id!=='runtime-linkage');requestedFilters=doc.manifest.filters;}
          else if(result.revision===doc.revision){
            const computed={...doc.computed};
            for(const map of ['components','tables','grouped','filterOptions','filterPages'])computed[map]={...computed[map],...result.computed?.[map]};
            computed.diagnostics=result.computed?.diagnostics||computed.diagnostics;
            doc={...doc,computed,manifest:{...doc.manifest,filters:base}};
            statisticalArtifacts=updateStatisticalArtifacts(statisticalArtifacts,{statisticalArtifacts:{...statisticalArtifacts,...result.statisticalArtifacts}});
          }else {pendingView={...job,request:++viewRequest};continue;}
          dirtyViewIds=new Set();render();
        }
        waiters.forEach(w=>w.resolve());
      }catch(error){if(error.name==='AbortError')waiters.forEach(w=>w.resolve());else waiters.forEach(w=>w.reject(error));}
    }}finally{viewRunning=false;viewAbort=null;}
  }
  function applyFilters(value){
    if(editing)return patch([{op:'set_filters',value}]);viewTables={};
    if(doc.computed&&boot.mode!=='offline'){
      const changed=new Set();for(const f of [...doc.manifest.filters,...value]){const before=doc.manifest.filters.find(x=>x.id===f.id),after=value.find(x=>x.id===f.id);if(JSON.stringify(before)!==JSON.stringify(after))for(const id of f.componentIds)changed.add(id);}
      // Clearing linkage also changes its consumers.
      if(lastLinkage)for(const id of Object.keys(doc.manifest.components))changed.add(id);
      return refreshLocal(value,[...changed]);
    }
    doc={...doc,manifest:{...doc.manifest,filters:value}};render();return Promise.resolve();
  }
  function localQuery(id,changes){if(changes.tableState)viewTables={...viewTables,[id]:changes.tableState};if(changes.granularity)viewGranularities={...viewGranularities,[id]:changes.granularity};return refreshLocal(requestedFilters||doc.manifest.filters,[id]);}
  const localExport=(id,options)=>transport('dataset_export',{dashboardId:doc.id,componentId:id,filters:viewDoc().manifest.filters,...options});
  function clearLinkage(){linkage=null;if(doc.computed&&boot.mode!=='offline')return refreshLocal().catch(showError);render();}
  const patch=(operations,rerender=true)=>mutate('dashboard_patch',()=>({operations:typeof operations==='function'?operations():operations}),true,rerender);
  // The grid already shows the dropped layout; re-rendering would tear down GridStack under the pointer.
  // Click-to-link is a reading aid: a temporary filter derived from the clicked category, never saved.
  // Components that cannot compute that field stay visible but are greyed out with the reason.
  function linkStatus(id){
    const c=doc.manifest.components[id];
    if(c.kind==='text')return null;
    if(!linkage||id===linkage.sourceId)return {ok:true};
    if(c.kind==='statistical')return {ok:false,reason:'统计图基于原始观测，不支持筛选'};
    const ds=c.kind==='legacy'?c.binding?.datasetId:c.datasetId;
    if(!ds)return {ok:false,reason:'未绑定数据'};
    if((ds!==linkage.datasetId&&!(c.linkGroup&&c.linkGroup===doc.manifest.components[linkage.sourceId]?.linkGroup))||!doc.manifest.datasets[ds]?.fields?.[linkage.field])return {ok:false,reason:`数据中没有「${linkage.label}」字段`};
    return {ok:true};
  }
  function viewDoc(){
    if(!linkage||editing)return doc;
    const ids=Object.keys(doc.manifest.components).filter(id=>id!==linkage.sourceId&&linkStatus(id)?.ok);
    return {...doc,manifest:{...doc.manifest,filters:[...doc.manifest.filters,{id:'runtime-linkage',label:linkage.label,field:linkage.field,op:linkage.op,values:linkage.values,componentIds:ids}]}};
  }
  function toggleLinkage(id,category){
    if(linkage?.sourceId===id&&linkage.category===category){clearLinkage();return;}
    const b=doc.manifest.components[id].binding,field=b.categoryField,declared=doc.manifest.filters.find(f=>f.field===field);
    let op='in',values=[category];
    if(b.timeGrain){const q=/^(\d{4}) Q([1-4])$/.exec(category),pad=n=>String(n).padStart(2,'0');op='range';
      values=q?[`${q[1]}-${pad(q[2]*3-2)}`,`${q[1]}-${pad(q[2]*3)}\uffff`]:[category,category+'\uffff'];}
    const label=declared?.label||doc.manifest.datasets[b.datasetId]?.fields?.[field]?.label||field;
    linkage={docId:doc.id,sourceId:id,datasetId:b.datasetId,field,label,category,op,values};if(doc.computed){refreshLocal().catch(showError);return;}render();
  }
  const linkageListeners=new WeakMap(),linkageSeries=new WeakMap();
  function wireLinkage(id,instance){
    const c=doc.manifest.components[id];
    if(!instance)return;const old=linkageListeners.get(instance);if(old)instance.off('click',old);
    const series=linkageSeries.get(instance);if(series){instance.setOption({series});linkageSeries.delete(instance);}
    if(editing||c.kind!=='legacy'||c.family!=='chart'||!c.binding?.categoryField)return;
    const bubble=c.config.code==='r02';
    const handler=params=>{const selected=linkageValue(params,bubble);if(selected!=null&&selected!=='')toggleLinkage(id,String(selected));};linkageListeners.set(instance,handler);instance.on('click',handler);
    if(linkage?.sourceId!==id)return;
    const option=instance.getOption(),axis=[...(option.xAxis||[]),...(option.yAxis||[])].find(a=>a.type==='category'),categories=(axis?.data||[]).map(v=>typeof v==='object'&&v?v.value:v).map(String);
    linkageSeries.set(instance,(option.series||[]).map(series=>({data:series.data})));
    instance.setOption({series:(option.series||[]).map(series=>({data:(series.data||[]).map((point,i)=>linkagePoint(point,i,categories,linkage.category,bubble))}))});
  }
  // The whole card is the drag surface; presses on controls (also inside original shadow roots) stay with the control.
  const CONTROLS='button,a,input,select,textarea,label,summary,[contenteditable],[role=button],[role=tab],[role=menuitem]';
  function keepControlsInteractive(e){if(e.composedPath().some(n=>n instanceof Element&&n.matches(CONTROLS)))e.stopPropagation();}
  function saveLayout(rerender=false){clearTimeout(layoutTimer);layoutTimer=null;const pending=pendingLayout;pendingLayout=null;if(!pending||pending.dashboardId!==doc?.id)return false;patch([{op:'set_layout',breakpoint:pending.breakpoint,value:pending.value}],rerender).catch(showError);return true;}
  async function restore(direction){const from=direction==='undo'?undo:redo,to=direction==='undo'?redo:undo;if(!from.length)return;const target=from.pop(),current=doc.revision;try{await mutate('dashboard_restore',{revision:target},false,false);to.push(current);render();}catch(e){from.push(target);throw e;}}
  async function reload(){if(!doc)return;if(reportDrafts.get(doc.id)?.dirty&&!confirm('重新读取会放弃未保存的 Markdown，继续？'))return;const next=accept(await transport('dashboard_get',{dashboardId:doc.id,dataMode:'local'})).document;reportDrafts.delete(doc.id);if(next.revision!==doc.revision){undo=[];redo=[];}doc=next;render();}
  async function refreshReport(force=false){
    if(!doc||refreshing||switching||editing||busy||pendingLayout||boot.mode==='offline')return;
    refreshing=true;
    try{
      const id=doc.id,[,info]=await Promise.all([refreshPages(),transport('runtime_info',{dashboardId:id})]);
      const changed=Boolean(boot.uiBuildId&&info.uiBuildId&&boot.uiBuildId!==info.uiBuildId);
      updateNotice.hidden=!changed;updateNotice.textContent=changed?'界面已有新版，请重新打开最新预览。报表数据仍可刷新。':'';
      if(doc.id!==id||(!force&&info.dashboardRevision<=doc.revision))return;
      const seq=++viewRequest,previous=doc.revision;
      const result=await transport('dashboard_refresh',{dashboardId:id,dataMode:'local',filters:viewDoc().manifest.filters,tableStates:viewTables,granularities:viewGranularities});
      if(seq!==viewRequest||doc.id!==id)return;
      doc=accept(result).document;doc.manifest.filters=doc.manifest.filters.filter(f=>f.id!=='runtime-linkage');requestedFilters=doc.manifest.filters;
      if(doc.revision!==previous){undo=[];redo=[];}
      lastRefresh=new Date().toLocaleTimeString('zh-CN',{hour12:false});render();
    }finally{refreshing=false;const refresh=toolbar.querySelector('[aria-label="刷新报表"]');if(refresh)refresh.disabled=false;}
  }
  title.onchange=()=>patch([{op:'set_title',value:title.value}]).catch(showError);
  function statusLine(){notice.title=doc.snapshot.updatedAt;status(`${boot.mode==='offline'?'离线快照 · ':''}版本 v${doc.revision}`);}
  function render(){
    annotations?.refresh();
    // Never rebuild GridStack mid-drag; flush an unsaved drop before replacing the grid.
    if(dragging){renderQueued=true;return;}renderQueued=false;
    if(pendingLayout&&saveLayout(true))return;
    if(linkage&&(editing||!doc||linkage.docId!==doc.id||!doc.manifest.components[linkage.sourceId]))linkage=null;
    if(!doc){status(boot.mode==='mcp'?'正在等待图表数据…':'请创建或打开仪表盘。');return;}
    viewTables=Object.fromEntries(Object.entries(viewTables).filter(([id])=>doc.manifest.components[id]));
    viewGranularities=Object.fromEntries(Object.entries(viewGranularities).filter(([id])=>doc.manifest.components[id]));
    if(dirtyViewIds)dirtyViewIds=new Set([...dirtyViewIds].filter(id=>doc.manifest.components[id]));
    // Only a page/view replacement empties the canvas. Incremental updates must
    // not restore an old scroll position over a subsequent reader interaction.
    const replacingPage=renderedPage!==doc.id||renderedMode!==(doc.manifest.viewMode==='report'?'report':'grid');
    if(replacingPage){const keepY=window.scrollY;canvas.style.minHeight=canvas.offsetHeight+'px';requestAnimationFrame(()=>requestAnimationFrame(()=>{canvas.style.minHeight='';if(Math.abs(window.scrollY-keepY)>1)window.scrollTo(0,keepY);}));}
    if(doc.progressive)ensureProgressive();
    renderedStatisticalArtifacts=statisticalArtifacts;lastLinkage=linkage;
    root.classList.toggle('paper-reading',doc.manifest.viewMode==='report'&&!editing);root.classList.toggle('report-page',doc.manifest.viewMode==='report');document.documentElement.dataset.theme='light';document.title=doc.manifest.title;title.value=doc.manifest.title;title.disabled=!editing;
    renderPageSwitch();
    const meta=doc.manifest.meta??doc.manifest.originalWorkspace?.meta??{};
    description.textContent=meta.subtitle||'';description.hidden=!description.textContent&&!editing;notice.hidden=!editing;
    clearInlineEdit(description);if(editing)inlineEdit(description,{label:'页面描述',value:meta.subtitle||'',save:value=>patch([{op:'set_meta',value:{...meta,subtitle:value}}])});
    clearInlineEdit(badge);context.replaceChildren();if(editing){const setMeta=key=>value=>patch([{op:'set_meta',value:{...meta,[key]:value}}]);const org=el('span'),system=el('span');inlineEdit(org,{label:'组织',value:meta.org||'',save:setMeta('org')});inlineEdit(system,{label:'系统',value:meta.system||'',save:setMeta('system')});context.append(org,el('span','context-separator',' · '),system);context.hidden=false;inlineEdit(badge,{label:'状态标签',value:meta.statusText||'',save:setMeta('statusText')});badge.hidden=false;}else{context.textContent=[meta.org,meta.system].filter(Boolean).join(' · ');context.hidden=!context.textContent;badge.textContent=meta.statusText||'';badge.hidden=!badge.textContent;}mark.replaceChildren(icon(meta.iconKey==='plane'?'plane':'chart'));
    disposeToolbar?.();toolbar.replaceChildren();
    const edit=iconButton(editing?'view':'edit',editing?T.view:T.edit,async()=>{if(editing&&currentDraft().dirty&&!confirm('仍有未保存的 Markdown，退出编辑？'))return;if(doc.progressive){if(!editing){editBatch=await transport('dashboard_edit_begin',{dashboardId:doc.id,expectedRevision:doc.revision});}else if(editBatch){const done=await transport('dashboard_edit_finish',{dashboardId:doc.id,expectedRevision:doc.revision,batchId:editBatch.batch_id});if(!done.ok){showError(Error('检查未通过，请查看诊断'));return;}editBatch=null;}}annotations?.reset();editing=!editing;render();});edit.disabled=boot.mode==='offline';edit.classList.remove('icon-button');edit.classList.add('mode-toggle');edit.append(el('span','',editing?T.view:T.edit));toolbar.append(edit);
    const annotate=iconButton('comment',annotations?.active?'退出批注':'批注',()=>{if(editing){if(currentDraft().dirty&&!confirm('仍有未保存的 Markdown，退出编辑并开始批注？'))return;editing=false;render();}annotations.toggle();});annotate.classList.add('annotation-toggle');annotate.setAttribute('aria-pressed',String(Boolean(annotations?.active)));toolbar.append(annotate);
    if(editing)toolbar.append(iconButton('comment','页面批注',()=>annotationDialog(null)));
    if(editing){const u=iconButton('undo',T.undo,()=>restore('undo')),r=iconButton('redo',T.redo,()=>restore('redo'));u.disabled=!undo.length;r.disabled=!redo.length;toolbar.append(u,r);}
    if(boot.mode!=='offline'){
      if(doc.progressive)toolbar.append(iconButton('history','版本历史',async()=>{const {body}=dialog('版本历史');let offset=0;const show=async()=>{const result=await transport('dashboard_history',{dashboardId:doc.id,offset,limit:20});body.replaceChildren();for(const item of result.history){const row=el('div','field');row.append(el('span','',`v${item.revision} ${item.name||item.action}${item.published?' · 已发布':''}`),button('恢复',async()=>{await mutate('dashboard_restore',{revision:item.revision});}),button('命名／发布标记',()=>{const {d,body:form}=dialog('版本标记');const name=input(item.name||''),published=input('','checkbox');published.checked=Boolean(item.published);form.append(field('版本名称',name),field('发布版本',published),button('保存',async()=>{await transport('dashboard_version_label',{dashboardId:doc.id,expectedRevision:doc.revision,revision:item.revision,name:name.value,published:published.checked});d.close();await show();}));}),button('与当前比较',async()=>{const diff=await transport('dashboard_history_diff',{dashboardId:doc.id,fromRevision:item.revision,toRevision:doc.revision});const {body:detail}=dialog('版本差异');detail.append(el('pre','',diff.diff));}));body.append(row);}body.append(button('上一页',()=>{offset=Math.max(0,offset-20);return show();}),button('下一页',()=>{offset+=20;return show();}));};await show();}));
      toolbar.append(iconButton('info','运行诊断',async()=>{const {body}=dialog('运行诊断');const report=await transport('dashboard_doctor',{dashboardId:doc.id,mode:'full'});body.append(el('p','',report.passed?'检查通过':'检查未通过'),button('复制请求编号',()=>navigator.clipboard.writeText(report.requestId)),table(report.checks));const logs=await transport('runtime_diagnostics',{dashboardId:doc.id,limit:30});body.append(table(logs.events));}));
      const refresh=iconButton('refresh','刷新报表',()=>refreshReport(true));refresh.disabled=refreshing||editing||Boolean(busy);toolbar.append(refresh);
      if(lastRefresh){const time=el('span','refresh-time','更新于 '+lastRefresh);toolbar.append(time);}
    }


    if(app){const context=app.getHostContext(),full=context?.displayMode==='fullscreen',mode=full?'inline':'fullscreen';
      if(!editing&&context?.availableDisplayModes?.includes(mode))toolbar.append(iconButton(full?'minimize':'maximize',full?'返回对话':'全屏查看',async()=>{await app.requestDisplayMode({mode});render();}));}
    if(!editing)toolbar.append(iconButton('export',T.export,exportDialog));disposeToolbar=adaptiveActions(top,toolbar);statusLine();
    // The version sits inline beside the edit toggle; long error messages keep their own line under the heading.
    if(editing&&!notice.classList.contains('error'))toolbar.prepend(notice);else heading.append(notice);
    filters.replaceChildren();filters.hidden=doc.manifest.viewMode==='report'||(!doc.manifest.filters.length&&!linkage&&!editing);
    for(const f of doc.manifest.filters){const c=doc.manifest.components[f.componentIds[0]],rows=f.componentIds.flatMap(id=>doc.snapshot.datasets[doc.manifest.components[id].datasetId]||[]);
      if(f.op==='in'){
        if(f.selectionMode==='single'){
          const values=doc.computed?.filterOptions?.[f.id]??[...new Map(rows.map(r=>[JSON.stringify(r[f.field]),r[f.field]])).values()];
          filters.append(singleFilter({filter:f,values,load:doc.progressive?((search,offset)=>transport('dashboard_filter_options',{dashboardId:doc.id,filterId:f.id,search,offset})):null,openMenu,closeMenu,icon,disabled:boot.mode==='offline',onApply:values=>{const fs=structuredClone(doc.manifest.filters);fs.find(item=>item.id===f.id).values=values;return applyFilters(fs);},onError:showError}));continue;
        }
        const values=doc.computed?.filterOptions?.[f.id]??[...new Map(rows.map(r=>[JSON.stringify(r[f.field]),r[f.field]])).values()];
        const firstPage=doc.computed?.filterPages?.[f.id]??{values,offset:0,totalValues:values.length,hasMore:false};
        const load=async(search,offset)=>{if(doc.computed)return transport('dashboard_filter_options',{dashboardId:doc.id,filterId:f.id,search,offset});const matches=values.filter(value=>String(value??'').toLowerCase().includes(search.toLowerCase()));return {values:matches.slice(offset,offset+100),offset,totalValues:matches.length,hasMore:offset+100<matches.length};};
        const group=pagedFilter({filter:f,firstPage,disabled:boot.mode==='offline',load,onApply:values=>{const fs=structuredClone(doc.manifest.filters);fs.find(item=>item.id===f.id).values=values;return applyFilters(fs);},onError:showError});
        const summary=f.values.length?(f.values.length===1?String(f.values[0]):`已选 ${f.values.length} 项`):'全部',trigger=button((f.label||f.field)+'：'+summary,()=>{if(doc.progressive)group.loadFirst();return openMenu(trigger,[],{label:f.label||f.field,content:group,align:'start'});},'filter-trigger');trigger.setAttribute('aria-haspopup','dialog');trigger.title=trigger.textContent;trigger.append(icon('down'));filters.append(trigger);
      }else if(f.op==='contains'){const search=input(f.values[0]??''),wrap=el('div','filter-search');search.placeholder=f.label||'搜索';search.setAttribute('aria-label',f.label||f.field);search.disabled=boot.mode==='offline';const apply=()=>{const fs=structuredClone(doc.manifest.filters);fs.find(v=>v.id===f.id).values=search.value.trim()?[search.value.trim()]:[];return applyFilters(fs);};search.onkeydown=e=>{if(e.key==='Enter')apply().catch(showError);};const submit=iconButton('search','应用搜索',apply);submit.disabled=boot.mode==='offline';wrap.append(search,submit);filters.append(wrap);
      }else{
        const a=input(f.values[0]??''),b=input(f.values[1]??''),fieldType=doc.manifest.datasets[c.datasetId].fields[f.field].type,numeric=fieldType==='number';
        const apply=()=>{const fs=structuredClone(doc.manifest.filters);fs.find(v=>v.id===f.id).values=a.value===''||b.value===''?[]:[numeric?Number(a.value):a.value,numeric?Number(b.value):b.value];return applyFilters(fs);};
        const submit=button('应用范围',apply,'filter-apply'),reset=button('重置筛选',()=>{a.value=b.value='';return apply();},'filter-clear');a.disabled=b.disabled=submit.disabled=reset.disabled=boot.mode==='offline';
        const range=el('div','filter-panel'),heading=el('div','filter-panel-heading'),fields=el('div','filter-range-fields'),actions=el('div','filter-actions');heading.append(el('strong','',f.label||f.field));
        a.setAttribute('aria-label',(f.label||f.field)+'起始');b.setAttribute('aria-label',(f.label||f.field)+'结束');if(fieldType==='date'){a.type=b.type='date';}else if(numeric){a.type=b.type='number';}
        for(const [caption,control] of [['起始',a],['结束',b]]){const label=el('label','filter-range-field');label.append(el('span','',caption),control);fields.append(label);}
        actions.append(reset,submit);range.append(heading,fields,actions);const summary=f.values.length?f.values.join(' — '):(fieldType==='date'?'全部月份':'全部'),trigger=button((f.label||f.field)+'：'+summary,()=>openMenu(trigger,[],{label:f.label||f.field,content:range,align:'start'}),'filter-trigger');trigger.setAttribute('aria-haspopup','dialog');trigger.append(icon('down'));filters.append(trigger);
      }
    }
    if(doc.manifest.filters.length||linkage){
      const active=doc.manifest.filters.filter(f=>f.values.length).length+(linkage?1:0),overview=el('div','filter-overview'),summary=el('span','filter-summary','已生效条件：'+active);
      const clear=button('清除所有筛选',()=>{linkage=null;return applyFilters(clearFilterValues(doc.manifest.filters));},'filter-clear-all');
      clear.disabled=boot.mode==='offline'||!active;overview.append(summary,clear);filters.append(overview);
    }

    root.querySelector('.linkage-chip')?.remove();
    if(linkage){const chip=el('div','linkage-chip');chip.setAttribute('role','status');
      chip.append(icon('link'),el('span','',`联动：${linkage.label} = ${linkage.category}`),iconButton('close','取消联动',clearLinkage));root.append(chip);}
    const mode=doc.manifest.viewMode==='report'?'report':'grid';
    if(renderedPage!==doc.id||renderedMode!==mode){
      for(const host of [...controllers.keys(),...pendingMounts.keys()])unmountComponent(host);
      cards.clear();reportHosts.clear();disposeReport?.();disposeReport=null;
      if(grid){grid.destroy(false);grid=null;}gridEl.replaceChildren();canvas.querySelector('.markdown-workspace')?.remove();
      renderedPage=doc.id;renderedMode=mode;
    }
    canvas.classList.toggle('report-canvas',mode==='report');gridEl.hidden=mode==='report';
    if(mode==='report'){
      lastBreakpoint=bp();const draft=currentDraft();if(!draft.dirty){draft.text=reportMarkdown(doc);draft.saved=draft.text;draft.revision=doc.revision;}
      if(disposeReport&&reportEditing===editing){disposeReport.update(doc);return;}
      disposeReport?.();canvas.querySelector('.markdown-workspace')?.remove();reportEditing=editing;
      disposeReport=renderReport({host:canvas,doc,editing,mountedCharts:reportHosts,mount:(card,id)=>mountComponent(card,id,true),unmount:unmountComponent,draft,onChange:text=>{draft.text=text;draft.dirty=text!==draft.saved;},onSave:saveMarkdown,onDiscard:()=>{draft.text=reportMarkdown(doc);draft.saved=draft.text;draft.dirty=false;draft.revision=doc.revision;disposeReport.update(doc);},onDownload:text=>download(doc.id+'.md',text,'text/markdown;charset=utf-8')});return;
    }
    const breakpoint=bp(),columns={desktop:12,tablet:8,mobile:4}[breakpoint];
    reconciling=true;
    if(!grid){
      grid=GridStack.init({column:columns,cellHeight:48,margin:12,float:false,disableDrag:!editing,disableResize:true,draggable:{handle:'.grid-stack-item-content'},resizable:{handles:'e,se,s,sw,w'},minRow:1},gridEl);
      grid.on('dragstart',()=>{dragging=true;});
      grid.on('dragstop',()=>{dragging=false;if(renderQueued)setTimeout(render);});
      grid.on('change',()=>{if(!editing||reconciling)return;clearTimeout(layoutTimer);pendingLayout={dashboardId:doc.id,breakpoint:bp(),value:grid.engine.nodes.map(n=>({id:String(n.id),x:n.x,y:n.y,w:n.w,h:n.h}))};layoutTimer=setTimeout(()=>saveLayout(),250);});
    }
    grid.batchUpdate();if(lastBreakpoint!==breakpoint)grid.column(columns,'none');lastBreakpoint=breakpoint;
    const positions=doc.manifest.layout[breakpoint],wanted=new Set(positions.map(p=>p.id));
    for(const [id,{item,card}] of cards)if(!wanted.has(id)){unmountComponent(card);grid.removeWidget(item);cards.delete(id);}
    gridEl.querySelector('.empty')?.remove();
    for(const position of positions){
      const id=position.id,c=doc.manifest.components[id];let record=cards.get(id);
      if(!record){const item=el('div','grid-stack-item'),card=el('section','grid-stack-item-content card original-host');item.dataset.componentId=id;item.append(card);gridEl.append(item);for(const type of ['mousedown','touchstart'])item.addEventListener(type,keepControlsInteractive,true);grid.makeWidget(item,{...position,minW:2,minH:c.kind==='kpi'||c.family==='kpi'?3:5});record={item,card};cards.set(id,record);}
      else {const n=record.item.gridstackNode;if(['x','y','w','h'].some(k=>n[k]!==position[k]))grid.update(record.item,position);}
      const {item,card}=record;card.classList.toggle('is-editing',editing);item.classList.toggle('is-draggable',editing);
      item.querySelector('.linkage-off-note')?.remove();const link=linkage&&!editing?linkStatus(id):null;item.classList.toggle('linkage-off',Boolean(link&&!link.ok));
      if(link&&!link.ok){const note=el('div','linkage-off-note'),tag=el('span','','未参与联动');tag.title=link.reason;tag.setAttribute('aria-label',`${c.title||id}未参与联动：${link.reason}`);note.append(tag);item.append(note);}
      item.classList.toggle('linkage-source',linkage?.sourceId===id&&!editing);
    }
    grid.enableMove(editing);grid.batchUpdate(false);reconciling=false;
    for(const {card,item} of cards.values())mountComponent(card,item.dataset.componentId);
    if(!Object.keys(doc.manifest.components).length)gridEl.append(el('div','empty',T.empty));
  }
  function unmountComponent(card){
    observer?.unobserve(card);dataObserver?.unobserve(card);pendingMounts.delete(card);const instance=controllers.get(card);instance?.destroy();controllers.delete(card);
    if(instance)originalInstances=originalInstances.filter(item=>item!==instance);card.replaceChildren();
  }

  function mountComponent(card,id,quiet=false,immediate=false){
    if(doc.progressive&&doc.manifest.components[id].kind!=='text'){
      card.dataset.loadId=id;dataObserver?.observe(card);
      const rect=card.getBoundingClientRect();if(rect.top<window.innerHeight+300&&rect.bottom>=-300)visibleComponents.add(id);
      if(!fetched.has(id)){
        progressiveLoader?.need(id);
        if(!controllers.has(card)){card.replaceChildren(el('h2','',doc.manifest.components[id].title||''),el('p','muted','等待加载…'));return;}
      }
    }
    let previous=controllers.get(card);
    if(previous){
      const plot=previous.app?.state.chartInstances['original-'+id],series=plot&&linkageSeries.get(plot);if(series){plot.setOption({series});linkageSeries.delete(plot);}
      const oldConfig=previous.app?.config;
      try{if(previous.update(quiet?doc:viewDoc(),quiet?false:editing,quiet||!editing||boot.mode==='offline')){if(quiet&&oldConfig!==previous.app?.config)quietPlot(previous,doc.manifest.components[id]);if(!quiet)wireLinkage(id,previous.app?.state.chartInstances['original-'+id]);return previous;}}catch(error){unmountComponent(card);const target=card.shadowRoot||card;target.replaceChildren(el('p','error',`${id}: ${error.message}`));return;}
      unmountComponent(card);if(card.shadowRoot){card.shadowRoot.replaceChildren();card.shadowRoot.adoptedStyleSheets=[];}
    }
    pendingMounts.delete(card);observer?.unobserve(card);
    const c=doc.manifest.components[id],rect=card.getBoundingClientRect(),deferChart=!immediate&&observer&&!window.__CHARTS_PDF_EXPORT__&&!editing&&(rect.top>window.innerHeight+300||rect.bottom < -300)&&(c.kind==='chart'||c.family==='chart');card.classList.remove('text-card','statistical-card');
    try{
        if(c.kind==='text'||c.kind==='statistical'){
          if(card.shadowRoot){card.shadowRoot.replaceChildren(document.createElement('slot'));card.shadowRoot.adoptedStyleSheets=[];}
          const statistical=c.kind==='statistical';card.classList.add(statistical?'statistical-card':'text-card');
          if(!quiet){const h=el('div','text-card-header'),heading=el('div','text-card-heading'),name=el('h2','text-heading',c.title),subtitle=el('p','component-description',c.subtitle||''),actions=el('div','text-card-actions');heading.append(name);if(c.subtitle||editing)heading.append(subtitle);actions.append(iconButton('info','指标定义与语义',()=>inspect(id)));if(editing){inlineEdit(name,{label:'图表标题',value:c.title,maxLength:240,save:value=>updateText(id,{title:value})});inlineEdit(subtitle,{label:'图表描述',value:c.subtitle||'',save:value=>updateText(id,{subtitle:value})});actions.append(iconButton('comment','图表批注',()=>annotationDialog(id)));}h.append(heading,actions);card.append(h);}
          if(statistical)mountStatisticalImage(card,c,statisticalArtifacts[id]);else card.append(el('div','text-block',c.text));
          let signature=JSON.stringify([c,statisticalArtifacts[id],editing]);
          controllers.set(card,{id,update(nextDoc,nextEditing){const next=nextDoc.manifest.components[id];if(next.kind!==c.kind)return false;const changed=JSON.stringify([next,statisticalArtifacts[id],nextEditing]);if(changed!==signature){signature=changed;controllers.delete(card);card.replaceChildren();mountComponent(card,id,quiet,true);}return true;},destroy(){}});

        }
        else {const instance=mountOriginal(card,{deferChart,onReady:()=>{if(!quiet)wireLinkage(id,controllers.get(card)?.app.state.chartInstances['original-'+id]);else quietPlot(controllers.get(card),c);},doc:quiet?doc:viewDoc(),id,editing:quiet?false:editing,readOnly:quiet||!editing||boot.mode==='offline',onInspect:inspect,onEdit:componentEditor,onAnnotate:annotationDialog,onText:updateText,onLocalQuery:boot.mode==='offline'?null:localQuery,onLocalExport:localExport,onType:(id,code)=>patch([{op:'set_original_chart',id,code}]).catch(showError),
          onPresentation:(id,changes)=>{const old=doc.manifest.components[id],base=old.kind==='legacy'?old.config:old.presentation||{};
            if(Object.keys(changes).some(k=>JSON.stringify(base[k])!==JSON.stringify(changes[k]))){const value=old.kind==='legacy'?{...old,config:{...base,...changes}}:{...old,presentation:{...base,...changes}};return mutate('dashboard_patch',{operations:[{op:'put_component',id,value}]},true,false).catch(showError);}}
        });controllers.set(card,instance);originalInstances.push(instance);if(deferChart){pendingMounts.set(card,()=>{pendingMounts.delete(card);observer.unobserve(card);instance.ensure();});observer.observe(card);}}
      if(!quiet&&c.kind==='legacy')wireLinkage(id,originalInstances.at(-1)?.app.state.chartInstances['original-'+id]);
      if(quiet&&card.shadowRoot){appendOriginalStyle(card.shadowRoot,'.component-actions,.component-header,.component-details{display:none!important}.section-card{box-shadow:none!important;border:0!important;border-radius:0!important;padding:0!important;background:transparent!important}.card-body-wrap{height:100%!important;margin:0!important}');quietPlot(controllers.get(card),c);}
      }catch(error){(card.shadowRoot||card).replaceChildren(el('p','error',`${id}: ${error.message}`));}
  }
  function quietPlot(entry,c){if(c.kind==='chart'&&['bar','line'].includes(c.chartType)){const instance=entry?.app.state.chartInstances['original-'+entry.id];if(instance){const option=instance.getOption();instance.setOption({color:['#444444','#999999','#666666','#bbbbbb'],textStyle:{fontFamily:'Noto Serif CJK SC, Songti SC, serif',color:'#444'},legend:{show:(option.series||[]).length>1},series:(option.series||[]).map((series,index)=>({type:series.type,label:{show:['line','bar'].includes(series.type),color:'#444',position:'top',fontFamily:'Noto Serif CJK SC, serif'},lineStyle:{color:['#444','#999','#666','#bbb'][index%4],width:2},itemStyle:{color:['#444','#999','#666','#bbb'][index%4]},symbolSize:6}))});}}}
  function updateText(id,changes){return patch(()=>{const old=doc.manifest.components[id],value={...old,...changes};if(old.kind==='legacy'){value.config={...old.config};if('title'in changes){value.config.title=changes.title;if(old.family==='kpi')value.config.label=changes.title;}if('subtitle'in changes){value.config.subtitle=changes.subtitle;if('description'in value.config)value.config.description=changes.subtitle;}}return [{op:'put_component',id,value}];});}
  async function saveMarkdown(source){
    const draft=currentDraft();
    await mutate('dashboard_patch',()=>({expectedRevision:draft.revision,operations:[{op:'set_report_markdown',value:source}]}),true,false);
    draft.saved=source;draft.dirty=draft.text!==source;draft.revision=doc.revision;
  }
  function jsonEditor(name,value,save){const {d,body}=dialog(name),area=textarea(value);body.append(area,button(T.save,async()=>{await save(JSON.parse(area.value));d.close();}));}
  function pageEditor(){
    const meta=doc.manifest.meta??doc.manifest.originalWorkspace?.meta??{}, {d,body}=dialog('页面标题与描述'),name=input(doc.manifest.title),subtitle=textarea(meta.subtitle||''),org=input(meta.org||''),system=input(meta.system||'');
    name.maxLength=240;subtitle.maxLength=1000;name.setAttribute('aria-label','页面标题');subtitle.setAttribute('aria-label','页面描述');
    body.append(field('标题',name),field('描述',subtitle),field('机构',org),field('系统',system),button(T.save,async()=>{const value=Object.fromEntries(Object.entries(meta).filter(([key])=>['subtitle','org','system','statusText','iconKey'].includes(key)));await patch([{op:'set_title',value:name.value},{op:'set_meta',value:{...value,subtitle:subtitle.value,org:org.value,system:system.value}}]);d.close();}));
  }
  function componentEditor(id){
    const old=doc.manifest.components[id];if(!old)return;
    const {d,body}=dialog('标题与描述'),name=input(old.title),subtitle=textarea(old.subtitle??old.config?.subtitle??old.config?.description??'');name.maxLength=240;subtitle.maxLength=1000;name.setAttribute('aria-label','图表标题');subtitle.setAttribute('aria-label','图表描述');
    body.append(field('标题',name),field('描述',subtitle),button(T.save,async()=>{await patch(()=>{const current=doc.manifest.components[id],value={...current,title:name.value,subtitle:subtitle.value};if(current.kind==='legacy'){value.config={...current.config,title:name.value,subtitle:subtitle.value};if(current.family==='kpi')value.config.label=name.value;}return [{op:'put_component',id,value}];});d.close();}));
  }
  function annotationDialog(componentId){
    const {body}=dialog(componentId?'图表批注':'页面批注'),list=el('div','annotation-list'),draft=textarea('');draft.setAttribute('aria-label','新增批注');draft.maxLength=4000;
    const writable=editing&&boot.mode!=='offline';
    const update=async transform=>{await patch(()=>[{op:'set_annotations',value:transform(doc.manifest.annotations||[])}]);draw();};
    function draw(){list.replaceChildren();const notes=(doc.manifest.annotations||[]).filter(n=>n.componentId===componentId);if(!notes.length)list.append(el('p','muted','暂无批注'));
      for(const note of notes){const row=el('section','annotation-item'),area=textarea(note.text);area.setAttribute('aria-label','批注内容');area.maxLength=4000;area.disabled=!writable;row.append(el('p','muted',new Date(note.createdAt).toLocaleString('zh-CN')),area);if(writable)row.append(button('保存批注',()=>update(notes=>notes.map(n=>n.id===note.id?{...n,text:area.value}:n))),button('删除批注',()=>update(notes=>notes.filter(n=>n.id!==note.id))));list.append(row);}
    }
    body.append(list);if(writable)body.append(field('新增批注',draft),button('添加批注',async()=>{if(!draft.value.trim())throw Error('请输入批注');await update(notes=>[...notes,{id:'note-'+crypto.randomUUID(),componentId,text:draft.value.trim(),createdAt:new Date().toISOString()}]);draft.value='';}));draw();
  }
  async function inspect(id){
    const c=doc.manifest.components[id],{d,body}=dialog(c.title),content=el('div','inspector-content');
    d.classList.add('inspector-single-page');body.classList.add('inspector-reference');body.append(content);
    d.addEventListener('click',event=>{if(event.target===d){const r=d.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)d.close();}});
    const instance=originalInstances.find(i=>i.shadow.host.closest('[data-component-id]')?.dataset.componentId===id),config=c.config||{},binding=c.binding;
    const datasetId=c.datasetId||binding?.datasetId,dataset=doc.manifest.datasets[datasetId];
    const explainKey=instance?.app.config.kpis?.[0]?.explainKey||instance?.app.config.charts?.[0]?.explainKey||config.code||config.type;
    const metricIds=[...new Set([...(c.measures||[]),...Object.values(binding?.measures||{})])],metrics=metricIds.map(mid=>({id:mid,...doc.manifest.metrics[mid]}));
    // Bound business metrics take precedence over catalog example explanations.
    const explanation=config.explanation||(!metrics.length?instance?.app.config.explanations?.[explainKey]:null)||{};
    const labels={name:'名称',definition:'业务定义',formula:'计算公式',rule:'判定规则',desc:'说明',meaning:'业务含义',range:'范围',xAxis:'横轴',yAxis:'纵轴',series:'系列',type:'图表类型',period:'统计周期',comparison:'对比基准',structure:'图表结构'};
    function prose(value){const node=el('div','inspector-prose');if(Array.isArray(value)){for(const item of value)node.append(prose(item));}else if(value&&typeof value==='object'){const list=el('dl','inspector-fields');for(const [key,item] of Object.entries(value)){const detail=el('dd');detail.append(['formula','计算公式'].includes(key)?el('code','inspector-formula',String(item??'')):prose(item));list.append(el('dt','',labels[key]||key),detail);}node.append(list);}else node.textContent=String(value??'');return node;}
    function section(label,parent=content){const node=el('section','inspector-section'),heading=el('div','inspector-section-heading');heading.append(el('h3','',label));node.append(heading);parent.append(node);return node;}
    function paragraph(label,value,parent=content){if(value==null||value==='')return;const node=section(label,parent);node.append(prose(value));return node;}
    const formula=m=>m.aggregation==='entity_ratio'?`先按 ${m.entityField} 汇总；COUNT(SUM(${m.numerator}) > 0) / NULLIF(COUNT(SUM(${m.denominator}) > 0), 0)`:m.aggregation==='ratio'?`SUM(${m.numerator}) / SUM(${m.denominator})`:m.aggregation==='count'?'COUNT(*)':`${m.aggregation.toUpperCase()}(${m.field})`;
    const unit=m=>m.unit||(m.format==='percent'?'百分比':'无单位');
    function businessFormula(m){const fields=doc.manifest.datasets[m.datasetId]?.fields||{},name=key=>fields[key]?.label;let text;if(m.aggregation==='entity_ratio')text=`先按${name(m.entityField)||'主体'}汇总净值，再用${name(m.numerator)||'分子'}合计大于零的去重主体数 ÷ ${name(m.denominator)||'分母'}合计大于零的去重主体数`;else if(m.aggregation==='ratio')text=`${name(m.numerator)||'分子'}合计 ÷ ${name(m.denominator)||'分母'}合计`;else if(m.aggregation==='count')text='记录条数（按记录计数，未去重）';else text=`${name(m.field)||m.label||m.id}${{sum:'合计',avg:'的算术平均值',min:'的最小值',max:'的最大值'}[m.aggregation]||''}`;return text+(m.format==='percent'?'（按百分比显示）':'');}
    const overview=paragraph('业务说明',explanation.overview||c.subtitle||config.subtitle||'暂无业务说明');overview.classList.add('inspector-overview');
    const specs=el('dl','inspector-fields inspector-specs');for(const [key,label] of [['type','图表类型'],['period','统计周期'],['comparison','对比基准']])if(explanation[key])specs.append(el('dt','',label),el('dd','',String(explanation[key])));if(specs.childNodes.length)overview.append(specs);
    const axesLabels=config.presentation?.axisLabels;
    const structureValue=explanation.structure||(axesLabels?{
      xAxis:{name:axesLabels.x||'横轴',meaning:binding?.categoryField?`${dataset?.fields[binding.categoryField]?.label||binding.categoryField}（${binding.categoryField}）`:axesLabels.x},
      yAxis:{name:axesLabels.y||[axesLabels.leftY,axesLabels.rightY].filter(Boolean).join(' / '),meaning:metrics.length?metrics.map(m=>`${m.label||m.id}（${unit(m)}）`).join('；'):axesLabels.y},
      series:config.presentation.seriesLabels?.map(name=>({name}))
    }:null);
    if(structureValue){const structure=section('坐标系维度与数据序列架构'),axes=el('div','inspector-axis-grid');for(const [key,label] of [['xAxis','X 轴'],['yAxis','Y 轴']]){const axis=structureValue[key];if(axis){const cell=el('div','inspector-axis-cell'),fields={};if(axis.meaning)fields['业务含义']=axis.meaning;if(axis.range)fields['范围']=axis.range;cell.append(el('h4','',`${label} · ${axis.name||''}`),prose(fields));axes.append(cell);}}if(axes.childNodes.length)structure.append(axes);if(Array.isArray(structureValue.series)){const series=el('div','inspector-series');for(const item of structureValue.series)series.append(el('span','',typeof item==='string'?item:`${item.name||''}${item.desc?'（'+item.desc+'）':''}`));structure.append(series);}else if(structureValue.series)structure.append(prose({'系列':structureValue.series}));const extra=Object.fromEntries(Object.entries(structureValue).filter(([key])=>!['xAxis','yAxis','series'].includes(key)));if(Object.keys(extra).length)structure.append(prose(extra));}
    const definitions=section('核心指标业务口径与数学公式');
    function metricCard(name,fields){const card=el('div','inspector-metric-card');card.append(el('h4','',name),prose(fields));definitions.append(card);}
    if(metrics.length){for(const m of metrics)metricCard(m.label||m.id,{'业务定义':m.definition||'未提供指标定义','计算公式':businessFormula(m),'单位':unit(m)});}
    else if(c.kind==='statistical')metricCard('指标定义',{'业务定义':c.analysis?.definition||'未提供指标定义','单位':c.analysis?.unit});
    else if(Array.isArray(explanation.metrics)&&explanation.metrics.length){for(const m of explanation.metrics){const {name,...fields}=m;const match=typeof fields.formula==='string'&&fields.formula.match(/^\s*(SUM|AVG|MIN|MAX|COUNT)\(\s*[\"`]?([\w]+|\*)[\"`]?\s*\)\s*$/i);if(match){const [,aggregation,key]=match;fields.formula=businessFormula({datasetId,field:key,aggregation:aggregation.toLowerCase(),label:name,unit:m.unit});}metricCard(name||'指标定义',fields);}}
    else definitions.append(prose(explanation.metrics||'此组件尚未提供指标定义。'));
    for(const [key,label] of [['interpretation','解读方法'],['notes','注意事项'],['limitations','局限']])paragraph(label,explanation[key]);
    const extra=Object.fromEntries(Object.entries(explanation).filter(([key])=>!['title','overview','metrics','interpretation','notes','limitations','type','period','comparison','structure','sql','query','parameters'].includes(key)));if(Object.keys(extra).length)paragraph('补充说明',extra);
    for(const note of doc.manifest.annotations||[])if(note.componentId===id)content.append(el('p','inspector-note',note.text));
    const semantics=section('查看语义');
    if(c.kind==='statistical')semantics.append(prose({'统计口径':c.analysis?.definition,'单位':c.analysis?.unit}));
    else{
      for(const m of metrics){const card=el('div','inspector-metric-card');card.append(el('h4','',m.label||m.id),prose({'指标标识':m.id,'数据集':m.datasetId,'计算方式':formula(m),'数值格式':m.format==='percent'?'百分比（比例值 × 100%）':'数值','单位':unit(m)}));semantics.append(card);}
      if(!metrics.length)semantics.append(prose('未配置指标计算口径'));
      const fields={};if(binding?.categoryField){const key=binding.categoryField;fields['分组字段']=`${dataset?.fields[key]?.label||key}（${key}）`;}
      if(binding?.timeGrain)fields['时间粒度']=instance?.app.state.chartGranularities['original-'+id]==='quarter'?'季度':'月度';
      if(binding?.scale)fields['展示换算']=Object.entries(binding.scale).map(([target,scale])=>`${doc.manifest.metrics[binding.measures[target]]?.label||target} × ${scale}`).join('；');
      const filters=doc.manifest.filters.filter(f=>f.componentIds.includes(id));fields['筛选范围']=filters.length?filters.map(f=>`${f.label||f.field}：${f.values.length?f.values.join(f.op==='range'?' 至 ':'、'):'全部'}`).join('；'):'未绑定页面筛选';semantics.append(prose(fields));
    }
    const sources=section('SQL 与来源'),sourceContent=el('div');sourceContent.append(el('p','muted','正在读取来源…'));sources.append(sourceContent);
    const dataSection=section('数据'),dataContent=el('div');dataSection.append(dataContent);
    async function loadData(){
      try{
        let rows=[];const local=boot.mode!=='offline'&&(doc.snapshot.datasetRefs?.[datasetId]||doc.snapshot.componentDataRefs?.[id]);
        if(local){
          const request={dashboardId:doc.id,componentId:id,expectedRevision:doc.revision,filters:viewDoc().manifest.filters,limit:20};
          const controls=el('div','table-controls'),content=el('div','table-scroll'),search=input(''),count=el('span','muted');
          search.placeholder='搜索数据';search.setAttribute('aria-label','搜索组件数据');let offset=0,total=0,sort=[],generation=0,searchTimer;
          const prev=iconButton('prev','数据上一页',()=>{offset=Math.max(0,offset-20);return load();}),next=iconButton('next','数据下一页',()=>{offset+=20;return load();});
          controls.append(search,count,prev,next,iconButton('export','导出完整数据 CSV',async()=>{const result=await transport('dataset_export',{dashboardId:request.dashboardId,componentId:id,filters:request.filters,sort,search:search.value});count.textContent=`已导出 ${result.export.rowCount} 条到本机：${result.export.path}`;}));dataContent.replaceChildren(controls,content);
          async function load(){const seq=++generation;prev.disabled=next.disabled=true;
            try{const result=await transport('component_data',{...request,offset,sort,search:search.value});if(!d.isConnected||seq!==generation)return;total=result.totalRows;count.textContent=`共 ${total} 条 · 第 ${Math.floor(offset/20)+1} 页 · 每页最多 20 行`;
              const keys=Object.keys(dataset?.fields||result.rows[0]||{}),t=el('table'),head=el('thead'),tr=el('tr');
              for(const key of keys){const th=el('th');th.append(button(dataset?.fields[key]?.label||key,()=>{sort=[{field:key,direction:sort[0]?.field===key&&sort[0].direction==='asc'?'desc':'asc'}];offset=0;return load();}));th.setAttribute('aria-sort',sort[0]?.field===key?(sort[0].direction==='asc'?'ascending':'descending'):'none');tr.append(th);}head.append(tr);t.append(head);const body=el('tbody');for(const row of result.rows){const tr=el('tr');for(const key of keys)tr.append(el('td','',String(row[key]??'—')));body.append(tr);}t.append(body);content.replaceChildren(t);
              prev.disabled=offset===0;next.disabled=offset+20>=total;
            }catch(error){if(seq===generation)content.replaceChildren(el('p','error',`数据读取失败：${error.message}`));}
          }
          search.oninput=()=>{generation++;clearTimeout(searchTimer);searchTimer=setTimeout(()=>{offset=0;load();},200);};d.addEventListener('close',()=>{generation++;clearTimeout(searchTimer);},{once:true});await load();return;
        }else{
          rows=visibleRows(viewDoc(),id);
          if(c.kind==='legacy'&&!binding){if(c.family==='table')rows=config.rows;else if(c.family==='chart'&&instance){const data=instance.app.config.charts[0].resolvedTable?.();if(data)rows=data.rows.map(r=>Object.fromEntries(data.headers.map((h,i)=>[h,r[i]])));}else rows=[{value:config.value,unit:config.unit||''}];}
        }
        if(d.isConnected)dataContent.replaceChildren(table(rows||[],{paginate:true,labels:Object.fromEntries(Object.entries(dataset?.fields||{}).map(([key,value])=>[key,value.label||key]))}));
      }catch(error){dataContent.replaceChildren(el('p','error',`数据读取失败：${error.message||error}`));}
    }
    const dataReady=loadData();
    try{
      const result=boot.mode==='offline'?{source:doc.manifest.sources[dataset?.sourceId||c.sourceId]}:await transport('query_inspect',{dashboardId:doc.id,componentId:id});
      const source=result.source;sourceContent.replaceChildren(prose({'数据来源':source?.name||'未提供来源说明'}));
      const componentSql=typeof explanation.sql==='string'?explanation.sql:explanation.query?.sql;
      const sourceSql=source?.query?.sql;
      if(componentSql)sourceContent.append(el('h4','','组件计算 SQL'),el('pre','code inspector-sql',componentSql));
      if(sourceSql&&sourceSql!==componentSql)sourceContent.append(el('h4','',componentSql?'数据来源 SQL':'查询 SQL'),el('pre','code inspector-sql',sourceSql));
      if(!componentSql&&!sourceSql)sourceContent.append(el('p','muted','未记录 SQL'));
      const componentParameters=explanation.parameters||explanation.query?.parameters;if(componentParameters)sourceContent.append(prose({'组件查询参数':componentParameters}));
      const componentQuery=explanation.query&&Object.fromEntries(Object.entries(explanation.query).filter(([key])=>!['sql','parameters'].includes(key)));if(componentQuery&&Object.keys(componentQuery).length)sourceContent.append(prose({'组件查询记录':componentQuery}));
      const sourceFields=source?Object.fromEntries(Object.entries(source).filter(([key])=>!['name','query'].includes(key))):{};
      if(source?.query){const queryFields=Object.fromEntries(Object.entries(source.query).filter(([key])=>key!=='sql'));if(Object.keys(queryFields).length)sourceFields['查询参数与配置']=queryFields;}
      if(result.snapshotUpdatedAt)sourceFields['数据快照时间']=result.snapshotUpdatedAt;
      if(Object.keys(sourceFields).length){sourceContent.append(el('h4','','来源记录'),prose(sourceFields));}
    }catch(error){sourceContent.replaceChildren(el('p','error',`来源读取失败：${error.message||error}`));}
    await dataReady;
  }
  function catalogDialog(){
    const {body}=dialog('原版组件目录'),search=input(''),list=el('div','catalog-list');search.placeholder='搜索图表名称、编号';body.append(el('p','muted','40 款原版图表 + 9 类 KPI。使用原版组件 JSON 或导入 Workspace，不用通用图表替换原配置。'),search,list);
    const all=Array.isArray(catalog)?catalog:Object.entries(catalog).map(([code,v])=>({code,...v}));
    function draw(){list.replaceChildren();for(const entry of all.filter(e=>JSON.stringify(e).toLowerCase().includes(search.value.toLowerCase()))){const row=el('div','catalog-row');row.append(el('strong','',entry.code||entry.id||''),el('span','',entry.nameZh||entry.title||entry.name||''),button('查看契约',()=>{const {body}=dialog(entry.nameZh||entry.title||entry.name||entry.id||entry.code);body.append(el('pre','code',JSON.stringify(entry,null,2)));}));list.append(row);}for(let i=1;i<=9;i++){const row=el('div','catalog-row');row.append(el('strong','','mc0'+i),el('span','',['标准指标','同比 / 环比','迷你趋势','目标进度','半环仪表','双指标','排名分层','阈值预警','分组拆解'][i-1]));list.append(row);}}
    search.oninput=draw;draw();
  }
  function bindingEditor(id){
    const c=doc.manifest.components[id],{d,body}=dialog('数据绑定 / '+c.title);
    const targets={c01:['categories','values'],c02:['categories','values'],c03:['clusters','budget','actual'],c04:['fleets','deviations'],c06:['hubs','offSeason','peakSeason'],c07:['clusters','base2024','curr2025'],c08:['categories','domestic','intl'],t01:['months','rpk'],t02:['quarters','actual','forecast'],t04:['quarters','premium','economy','cargo','ancillary'],t06:['categories','revenue','yieldGrowth'],d01:['brackets','counts'],fn02:['quarters','revenue','cost'],fn03:['variables','negative','positive'],r02:['clusters','x','y','size']};
    const shape=targets[c.config.code],template={datasetId:'',measures:{}};
    if(c.family==='chart'&&shape){template.categoryField='';template.categoryTarget=shape[0];template.measures=Object.fromEntries(shape.slice(1).map(k=>[k,'']));}
    if(c.family==='kpi'){template.measures=c.config.type==='mc06'?{leftVal:'',rightVal:''}:{value:''};if(c.config.type==='mc03')template.timeField='';}
    const area=textarea(c.binding||template);
    body.append(el('p','muted','引用已有 Dataset 和指标 ID，不改变原组件设计。比例按分子、分母重算；缺少映射会拒绝保存。'),area,el('pre','code',JSON.stringify({datasets:Object.fromEntries(Object.entries(doc.manifest.datasets).map(([k,v])=>[k,v.fields])),metrics:doc.manifest.metrics},null,2)),button(T.save,async()=>{await patch([{op:'put_component',id,value:{...c,binding:JSON.parse(area.value)}}]);d.close();}));
    if(c.binding)body.append(button('移除绑定',async()=>{const value={...c};delete value.binding;delete value.datasetId;delete value.measures;const filters=doc.manifest.filters.map(f=>({...f,componentIds:f.componentIds.filter(k=>k!==id)})).filter(f=>f.componentIds.length);await patch([{op:'put_component',id,value},{op:'set_filters',value:filters}]);d.close();}));
  }
  function importData(){const {d,body}=dialog(T.import),name=input('dataset-'+Date.now().toString(36)),area=textarea('[]'),file=input('','file'),formatSelect=select([['json','JSON rows'],['csv','CSV']],'json');file.accept='.json,.csv';file.onchange=async()=>{area.value=await file.files[0].text();formatSelect.value=file.files[0].name.endsWith('.csv')?'csv':'json';};body.append(field('Dataset ID',name),file,formatSelect,area,button(T.save,async()=>{await mutate('dataset_import',{datasetId:name.value,...(formatSelect.value==='csv'?{csvText:area.value}:{rows:JSON.parse(area.value)}),name:file.files[0]?.name||name.value});d.close();}));}
  function queryEditor(){const {d,body}=dialog('SQL / read-only'),alias=input('analytics'),ds=input('query-result'),sql=textarea('SELECT * FROM your_table LIMIT 100'),params=textarea('{}');body.append(el('p','muted','Only explicitly configured SQLite aliases are executable. No query runs on preview or chart switching.'),field('Connection alias',alias),field('Dataset ID',ds),field('SQL',sql),field('Parameters',params),button('执行只读查询',async()=>{if(!confirm('Execute this read-only query and save a new snapshot?'))return;await mutate('query_execute',{connection:alias.value,datasetId:ds.value,sql:sql.value,parameters:JSON.parse(params.value)});d.close();}));}
  function exportDialog(){
    const {d,body}=dialog(T.export);d.classList.add('export-dialog');
    body.append(el('p','export-intro','选择文件格式，保存当前看板。'));
    const choices=el('div','export-choices'),feedback=el('p','export-feedback'),savedFile=el('div','export-saved');feedback.setAttribute('role','status');
    const options=[['pdf','PDF','完整图表与筛选后全部明细'],['html','HTML','离线打开，保留当前视图'],['json','JSON','看板配置与本地数据引用']];
    for(const [format,label,hint]of options){
      const b=button('',async()=>{
        const buttons=choices.querySelectorAll('button');buttons.forEach(n=>n.disabled=true);savedFile.replaceChildren();feedback.textContent=`正在生成 ${label}…`;
        try{
          if(boot.mode==='offline'){
            if(format==='pdf'){d.close();window.print();return;}
            if(format==='json')download(doc.id+'.json',JSON.stringify(doc,null,2));
            else {
              const shell=document.documentElement.cloneNode(true);shell.querySelectorAll('.workspace,dialog,.ui-tooltip').forEach(n=>n.remove());
              const script=[...shell.querySelectorAll('script')].find(n=>n.textContent.startsWith('window.__DASHBOARD_BOOT__='));
              if(!script)throw Error('未找到离线看板内容');
              script.textContent='window.__DASHBOARD_BOOT__='+JSON.stringify({...boot,mode:'offline',document:doc}).replace(/</g,'\\u003c')+';';
              download(doc.id+'.html','<!doctype html>'+shell.outerHTML,'text/html;charset=utf-8');
            }
          }else{
            const filters=viewDoc().manifest.filters;
            const result=await transport('dashboard_export',{dashboardId:doc.id,format,filters,tableStates:viewTables,granularities:viewGranularities});
            const file=result.export;
            const localAction=(action,text)=>button(text,async()=>{
              try{await transport('dashboard_export_open',{dashboardId:doc.id,exportId:file.id,format,action});feedback.textContent=action==='open'?'已请求打开文件':'已在文件夹中显示';}
              catch(error){feedback.textContent=error.message||String(error);}
            },'export-file-action');
            const actions=el('div','export-file-actions');actions.append(localAction('open','打开文件'),localAction('reveal','在文件夹中显示'));
            savedFile.append(el('span','export-filename',file.filename),actions,el('p','export-path',file.path));
            feedback.textContent=`${label} 已保存到本机`;
            if(app){
              try{
                const saved=await app.downloadFile({contents:[{type:'resource',resource:{uri:'file://'+file.path,mimeType:file.mimeType,blob:file.content}}]});
                if(!saved.isError)feedback.textContent=`${label} 已保存，可打开本机文件或使用下载副本`;
              }catch(error){/* The managed local file is already saved; host downloads are optional. */}
            }else download(file.filename,Uint8Array.from(atob(file.content),c=>c.charCodeAt(0)),file.mimeType);
            return;
          }
          feedback.textContent=`${label} 已生成`;
        }catch(error){feedback.textContent='导出失败：'+(error.message||error);}
        finally{buttons.forEach(n=>n.disabled=false);}
      },'export-choice');b.setAttribute('aria-label','导出 '+label);
      const mark=el('span','export-format-icon');mark.append(icon(format));
      b.append(mark,el('strong','',label),el('span','export-hint',hint),icon('export'));choices.append(b);
    }
    body.append(choices,el('p','export-scope','PDF 包含当前筛选下的全部明细，表格自动分页。HTML 保存当前视图；CSV 可单独导出完整明细。'),feedback,savedFile);
  }
  window.addEventListener('keydown',e=>{if(e.key==='Escape'&&linkage&&!document.querySelector('dialog[open]'))clearLinkage();});
  window.addEventListener('resize',()=>{if(doc&&bp()!==lastBreakpoint&&!pendingLayout&&!dragging&&!busy)render();});
  if(boot.mode!=='offline')whileVisible(async()=>{if(!doc||editing||annotations?.active||busy||pendingLayout||dragging||reportDrafts.get(doc.id)?.dirty||document.querySelector('dialog[open]'))return;try{await refreshReport();}catch(e){showError(e);}},5000);
  if(boot.mode!=='offline')whileVisible(async()=>{try{await transport('runtime_keepalive',{});}catch(e){showError(e);}},Math.min(20000,(boot.idleTimeout||60)*1000/3));
  window.addEventListener('beforeunload',event=>{if([...reportDrafts.values()].some(draft=>draft.dirty)){event.preventDefault();event.returnValue='';}});
  window.__chartsReady=async()=>{
    for(const run of [...pendingMounts.values()])run();await document.fonts.ready;
    const images=[...document.querySelectorAll('img')];await Promise.all(images.map(img=>img.decode?.().catch(()=>{})));
    await Promise.all(originalInstances.flatMap(item=>Object.values(item.app.state.chartInstances)).map(chart=>new Promise(resolve=>{
      if(chart.isDisposed()){resolve();return;}const zr=chart.getZr();if(zr.animation.isFinished()){chart.resize();requestAnimationFrame(()=>resolve());return;}
      const done=()=>{chart.off('finished',done);resolve();};chart.on('finished',done);chart.resize();
    })));
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  };
  window.addEventListener('beforeprint',()=>{for(const run of [...pendingMounts.values()])run();});
  annotations=createAnnotations({root,iconButton,getDocument:()=>doc,readOnly:boot.mode==='offline',save:transform=>patch(()=>[{op:'set_annotations',value:transform(doc.manifest.annotations||[])}]),onError:showError,onMode:active=>{const b=toolbar.querySelector('.annotation-toggle');if(b){b.setAttribute('aria-pressed',String(active));b.setAttribute('aria-label',active?'退出批注':'批注');b.title=active?'退出批注':'批注';b.dataset.tooltip=b.title;}}});
  window.addEventListener('charts-error',event=>showError(event.detail));render();

}
