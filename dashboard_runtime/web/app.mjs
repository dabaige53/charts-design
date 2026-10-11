import {reportMarkdown,renderReport} from './report.mjs';
import {icon,iconButton,openMenu,adaptiveActions} from './icons.mjs';
import {initializeOriginal,mountOriginal,catalog} from './original.mjs';
import {visibleRows,csv,chartTypes} from './engine.mjs';
const T={edit:'编辑',view:'阅读',add:'添加组件',import:'导入数据',undo:'撤销',redo:'重做',reload:'重新读取',export:'导出',close:'关闭',save:'保存',data:'数据',semantic:'指标语义',settings:'图表设置',source:'查询来源',remove:'删除',copy:'复制',empty:'导入数据，或通过 CLI / MCP 添加组件。'};
const el=(tag,cls='',text='')=>{const n=document.createElement(tag);n.className=cls;n.textContent=text;return n;};
const button=(label,fn,cls='')=>{const b=el('button',cls,label);b.type='button';b.onclick=()=>Promise.resolve().then(fn).catch(showError);return b;};
function showError(error){const n=document.getElementById('notice');if(n){n.textContent=error.message||String(error);n.className='notice error';}else console.error(error);}
function download(name,body,type='application/json'){const a=el('a');a.href=URL.createObjectURL(new Blob([body],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
function field(label,node){const wrap=el('label','field');wrap.append(el('span','',label),node);return wrap;}
function input(value='',kind='text'){const n=el('input');n.type=kind;n.value=value;return n;}
function select(options,value){const n=el('select');for(const [key,label] of options){const o=el('option','',label);o.value=key;n.append(o);}n.value=value??options[0]?.[0]??'';return n;}
function textarea(value){const n=el('textarea');n.value=typeof value==='string'?value:JSON.stringify(value,null,2);n.spellcheck=false;return n;}
function dialog(title){const d=el('dialog','inspector'),head=el('header'),body=el('div','inspector-body');head.append(el('h2','',title),iconButton('close',T.close,()=>d.close()));d.append(head,body);d.addEventListener('close',()=>d.remove());document.body.append(d);d.showModal();return {d,body};}
function table(rows){
  const wrap=el('div','data-table'),controls=el('div','table-controls'),body=el('div','table-scroll');
  let page=0,sortKey=null,asc=true;const size=20,keys=[...new Set(rows.flatMap(r=>Object.keys(r)))];
  function render(){body.replaceChildren();controls.replaceChildren();const data=[...rows];
    if(sortKey)data.sort((a,b)=>{const x=a[sortKey],y=b[sortKey];return (typeof x==='number'&&typeof y==='number'?x-y:String(x??'').localeCompare(String(y??''),'zh-CN',{numeric:true}))*(asc?1:-1);});
    const t=el('table'),tr=el('tr');for(const key of keys){const th=el('th'),sort=button(key,()=>{asc=sortKey===key?!asc:true;sortKey=key;page=0;render();});if(sortKey===key)sort.append(icon(asc?'up':'down'));th.setAttribute('aria-sort',sortKey===key?(asc?'ascending':'descending'):'none');th.append(sort);tr.append(th);}const thead=el('thead');thead.append(tr);t.append(thead);
    const tbody=el('tbody');for(const row of data.slice(page*size,(page+1)*size)){const r=el('tr');for(const key of keys)r.append(el('td','',String(row[key]??'—')));tbody.append(r);}t.append(tbody);body.append(t);
    const prev=iconButton('prev','上一页',()=>{page--;render();}),next=iconButton('next','下一页',()=>{page++;render();});prev.disabled=page===0;next.disabled=(page+1)*size>=rows.length;
    controls.append(el('span','muted',`${rows.length} rows / ${page+1}`),prev,next,iconButton('export','CSV',()=>download('data.csv',csv(rows),'text/csv;charset=utf-8')));
  }wrap.append(controls,body);render();return wrap;
}
export async function start({echarts,GridStack,App}){
  initializeOriginal(echarts);
  const boot=window.__DASHBOARD_BOOT__||{},root=el('div','workspace');document.body.append(root);
  const top=el('header','topbar'),brand=el('div','brand','CHARTS / WORKSPACE'),title=input('Dashboard'),toolbar=el('div','toolbar'),notice=el('div','notice'),filters=el('div','filters'),canvas=el('main','canvas'),gridEl=el('div','grid-stack');
  notice.id='notice';title.className='dashboard-title';title.setAttribute('aria-label','Dashboard title');const heading=el('div','dashboard-heading'),hidden=el('div');hidden.hidden=true;heading.append(brand,title,notice);top.append(heading,toolbar);hidden.append(filters);canvas.append(gridEl);root.append(top,hidden,canvas);toolbar.setAttribute('role','toolbar');toolbar.setAttribute('aria-label','Dashboard actions');
  let doc=null,editing=false,grid=null,undo=[],redo=[],queue=Promise.resolve(),busy=0,layoutTimer=null,app=null;
  let lastBreakpoint=null,transport,originalInstances=[],disposeToolbar=null,disposeReport=null;
  const reportDrafts=new Map();
  const currentDraft=()=>{let draft=reportDrafts.get(doc.id);if(!draft){draft={text:reportMarkdown(doc),saved:reportMarkdown(doc),dirty:false,revision:doc.revision};reportDrafts.set(doc.id,draft);}return draft;};
  const bp=()=>window.innerWidth<650?'mobile':window.innerWidth<1050?'tablet':'desktop';
  const status=text=>{notice.textContent=text;notice.className='notice';};
  const accept=result=>{if(result?.error)throw Error(result.error.message);if(result?.isError)throw Error(result.content?.[0]?.text||'Tool failed');return result;};
  const unpack=result=>accept(result.structuredContent || (result.content?.[0]?.text?JSON.parse(result.content[0].text):result));
  if(boot.mode==='mcp'){
    app=new App({name:'Charts Design Dashboard',version:'0.4.0'},{},{autoResize:true});
    app.ontoolresult=result=>{try{const value=unpack(result);if(value.document){doc=value.document;render();}}catch(e){showError(e);}};
    transport=async(name,args)=>unpack(await app.callServerTool({name,arguments:args}));await app.connect();
  }else if(boot.mode==='offline'){
    doc=boot.document;transport=async()=>{throw Error('Offline snapshot: use Export JSON and import it through CLI to persist server-side changes.');};editing=false;
  }else{
    const fragment=location.hash.slice(1);let token='';try{token=sessionStorage.getItem('charts-runtime-token')||'';}catch{}
    const explicit=fragment.startsWith('token=');
    // New links identify credentials explicitly. Existing sessions keep document anchors inert.
    if(explicit||(!token&&fragment&&!/^(fig-|report-)/.test(fragment))){token=explicit?decodeURIComponent(fragment.slice(6)):fragment;try{sessionStorage.setItem('charts-runtime-token',token);}catch{}history.replaceState(null,'',location.pathname+location.search);}
    const authHeaders={'Content-Type':'application/json','Authorization':'Bearer '+token};
    transport=async(name,args)=>{const response=await fetch('/api/tools/'+name,{method:'POST',headers:authHeaders,body:JSON.stringify(args)});return accept(await response.json());};
    boot.exportFile=async id=>{const r=await fetch('/api/export/'+encodeURIComponent(id),{headers:authHeaders});if(!r.ok)throw Error((await r.json()).error?.message||'Export failed');download(id+'.html',await r.text(),'text/html');};
    const id=new URLSearchParams(location.search).get('board');
    if(id)doc=(await transport('dashboard_get',{dashboardId:id})).document;
    else{const boards=(await transport('dashboard_list',{})).dashboards;if(boards.length)doc=(await transport('dashboard_get',{dashboardId:boards[0].id})).document;}
  }
  async function mutate(name,args,pushUndo=true,rerender=true){
    if(!doc)throw Error('Create a dashboard first');
    const run=async()=>{busy++;const previous=doc.revision;try{const request=typeof args==='function'?args():args;const result=await transport(name,{...request,dashboardId:doc.id,expectedRevision:request.expectedRevision??doc.revision});if(result.document){if(pushUndo){undo.push(previous);redo=[];}doc=result.document;const pending=reportDrafts.get(doc.id);if(pending&&reportMarkdown(doc)===pending.saved)pending.revision=doc.revision;if(rerender)render();else{statusLine();const u=toolbar.querySelector('[aria-label="'+T.undo+'"]');if(u)u.disabled=!undo.length;}}return result;}catch(e){render();showError(e);throw e;}finally{busy--;}};
    const next=queue.then(run,run);queue=next.catch(()=>{});return next;
  }
  const patch=operations=>mutate('dashboard_patch',()=>({operations:typeof operations==='function'?operations():operations}));
  async function restore(direction){const from=direction==='undo'?undo:redo,to=direction==='undo'?redo:undo;if(!from.length)return;const target=from.pop(),current=doc.revision;try{await mutate('dashboard_restore',{revision:target},false);to.push(current);render();}catch(e){from.push(target);throw e;}}
  async function reload(){if(!doc)return;if(reportDrafts.get(doc.id)?.dirty&&!confirm('重新读取会放弃未保存的 Markdown，继续？'))return;const next=(await transport('dashboard_get',{dashboardId:doc.id})).document;reportDrafts.delete(doc.id);if(next.revision!==doc.revision){undo=[];redo=[];}doc=next;render();}
  title.onchange=()=>patch([{op:'set_title',value:title.value}]).catch(showError);
  function statusLine(){status(`${doc.snapshot.status==='fixture'?'示例数据 / ':''}${boot.mode==='offline'?'离线快照 / ':''}v${doc.revision} / ${doc.snapshot.updatedAt}`);}
  function render(){
    if(!doc){status('Create a dashboard with CLI / MCP, then reload this page.');return;}
    root.classList.toggle('paper-reading',doc.manifest.viewMode==='report'&&!editing);document.documentElement.dataset.theme=doc.manifest.theme;document.title=doc.manifest.title;title.value=doc.manifest.title;title.disabled=!editing;
    disposeToolbar?.();toolbar.replaceChildren();
    const oldSwitch=heading.querySelector('.view-switch');oldSwitch?.remove();const modes=el('nav','view-switch');modes.setAttribute('aria-label','呈现模式');for(const [mode,label,glyph] of [['dashboard','仪表盘','catalog'],['report','分析报告','semantic']]){const b=button(label,()=>switchMode(mode));b.prepend(icon(glyph));b.setAttribute('aria-pressed',String((doc.manifest.viewMode||'dashboard')===mode));modes.append(b);}heading.append(modes);
    const edit=iconButton(editing?'view':'edit',editing?T.view:T.edit,()=>{if(editing&&currentDraft().dirty&&!confirm('仍有未保存的 Markdown。离开编辑模式？原文会保留。'))return;editing=!editing;render();});edit.disabled=boot.mode==='offline';toolbar.append(edit);
    if(editing&&doc.manifest.viewMode!=='report'){const u=iconButton('undo',T.undo,()=>restore('undo')),r=iconButton('redo',T.redo,()=>restore('redo'));u.disabled=!undo.length;r.disabled=!redo.length;toolbar.append(iconButton('add',T.add,()=>componentEditor()),iconButton('catalog','原版组件',catalogDialog),iconButton('import',T.import,importData),u,r);}
    if(doc.manifest.filters.length||editing){const f=iconButton('filter','筛选',()=>openMenu(f,[],{label:'筛选',content:filters}));toolbar.append(f);}
    if(boot.mode!=='offline')toolbar.append(iconButton('sql','SQL',queryEditor),iconButton(doc.manifest.theme==='dark'?'light':'dark',doc.manifest.theme==='dark'?'Light':'Dark',()=>patch([{op:'set_theme',value:doc.manifest.theme==='dark'?'light':'dark'}])),iconButton('refresh',T.reload,reload));
    toolbar.append(iconButton('export',T.export,exportDialog));disposeToolbar=adaptiveActions(top,toolbar);statusLine();
    filters.replaceChildren();
    for(const f of doc.manifest.filters){const c=doc.manifest.components[f.componentIds[0]],rows=doc.snapshot.datasets[c.datasetId];
      if(f.op==='in'){
        const values=[...new Map(rows.map(r=>[JSON.stringify(r[f.field]),r[f.field]])).values()],group=el('fieldset','filter-options'),legend=el('legend','',f.label||f.field),choices=[];
        group.append(legend);for(const value of values){const label=el('label','filter-choice'),check=input('','checkbox');check.checked=f.values.length===0||f.values.some(v=>JSON.stringify(v)===JSON.stringify(value));check.disabled=boot.mode==='offline';label.append(check,el('span','',String(value??'—')));group.append(label);choices.push({check,value});}
        const apply=iconButton('save','应用筛选',()=>{const selected=choices.filter(v=>v.check.checked).map(v=>v.value);if(!selected.length)throw Error('至少选择一项，或使用重置恢复全部');const fs=structuredClone(doc.manifest.filters);fs.find(v=>v.id===f.id).values=selected.length===values.length?[]:selected;return patch([{op:'set_filters',value:fs}]);});
        const reset=iconButton('refresh','重置筛选',()=>{const fs=structuredClone(doc.manifest.filters);fs.find(v=>v.id===f.id).values=[];return patch([{op:'set_filters',value:fs}]);});apply.disabled=reset.disabled=boot.mode==='offline';const actions=el('div','filter-actions');actions.append(reset,apply);group.append(actions);filters.append(group);
      }else{const a=input(f.values[0]??''),b=input(f.values[1]??''),numeric=doc.manifest.datasets[c.datasetId].fields[f.field].type==='number';const apply=()=>{const fs=structuredClone(doc.manifest.filters);fs.find(v=>v.id===f.id).values=a.value===''||b.value===''?[]:[numeric?Number(a.value):a.value,numeric?Number(b.value):b.value];return patch([{op:'set_filters',value:fs}]);};const submit=iconButton('save','应用范围',apply);a.disabled=b.disabled=submit.disabled=boot.mode==='offline';filters.append(field(f.label||f.field,a),b,submit);}
    }
    if(editing)filters.append(button('筛选设置',()=>jsonEditor('Filters',doc.manifest.filters,value=>patch([{op:'set_filters',value}]))));
    if(layoutTimer){clearTimeout(layoutTimer);layoutTimer=null;}
    originalInstances.forEach(x=>x.destroy());originalInstances=[];
    if(grid){grid.destroy(false);grid=null;}gridEl.replaceChildren();disposeReport?.();disposeReport=null;canvas.querySelector('.markdown-workspace')?.remove();canvas.classList.toggle('report-canvas',doc.manifest.viewMode==='report');
    if(doc.manifest.viewMode==='report'){lastBreakpoint=bp();const draft=currentDraft();if(!draft.dirty){draft.text=reportMarkdown(doc);draft.saved=draft.text;draft.revision=doc.revision;}disposeReport=renderReport({host:canvas,doc,editing,mount:(card,id)=>mountComponent(card,id,true),draft,onChange:text=>{draft.text=text;draft.dirty=text!==draft.saved;},onSave:saveMarkdown,onDiscard:()=>{draft.text=reportMarkdown(doc);draft.saved=draft.text;draft.dirty=false;draft.revision=doc.revision;render();},onDownload:text=>download(doc.id+'.md',text,'text/markdown;charset=utf-8'),onDisposeCharts:()=>{originalInstances.forEach(x=>x.destroy());originalInstances=[];}});return;}
    const breakpoint=bp();lastBreakpoint=breakpoint;const columns={desktop:12,tablet:8,mobile:4}[breakpoint];
    grid=GridStack.init({column:columns,cellHeight:48,margin:8,float:true,disableDrag:!editing,disableResize:!editing,draggable:{handle:'.layout-handle',cancel:'input,select,textarea,a'},resizable:{handles:'e,se,s,sw,w'},minRow:1},gridEl);
    for(const position of doc.manifest.layout[breakpoint]){
      const id=position.id,c=doc.manifest.components[id],item=el('div','grid-stack-item'),card=el('section','grid-stack-item-content card original-host');
      item.dataset.componentId=id;card.classList.toggle('is-editing',editing);item.append(card);gridEl.append(item);
      if(editing){const handle=iconButton('drag','拖动组件');handle.classList.add('drag-handle','layout-handle');item.append(handle);}
      grid.makeWidget(item,{...position,minW:2,minH:c.kind==='kpi'||c.family==='kpi'?3:5});
      mountComponent(card,id);
    }
    if(!Object.keys(doc.manifest.components).length)gridEl.append(el('div','empty',T.empty));
    grid.on('change',()=>{if(!editing)return;clearTimeout(layoutTimer);const value=grid.engine.nodes.map(n=>({id:String(n.id),x:n.x,y:n.y,w:n.w,h:n.h}));layoutTimer=setTimeout(()=>{layoutTimer=null;patch([{op:'set_layout',breakpoint,value}]).catch(showError);},250);});
  }

  function mountComponent(card,id,quiet=false){
    const c=doc.manifest.components[id];
    try{
        if(c.kind==='text'){card.classList.add('text-card');const h=el('div','text-card-header'),text=el('div','text-card-heading'),actions=el('div','text-card-actions');text.append(el('h2','text-heading',c.title));if(c.subtitle)text.append(el('p','component-description',c.subtitle));if(editing)actions.append(iconButton('edit',T.edit,()=>componentEditor(id)));h.append(text,actions);card.append(h,el('div','text-block',c.text));}
        else originalInstances.push(mountOriginal(card,{doc,id,editing:quiet?false:editing,readOnly:quiet||boot.mode==='offline',onInspect:inspect,onEdit:componentEditor,onBinding:bindingEditor,onType:(id,chartType)=>patch([{op:'set_chart',id,chartType}]).catch(showError),
          onPresentation:(id,changes)=>{const old=doc.manifest.components[id],base=old.kind==='legacy'?old.config:old.presentation||{};
            if(Object.keys(changes).some(k=>JSON.stringify(base[k])!==JSON.stringify(changes[k]))){const value=old.kind==='legacy'?{...old,config:{...base,...changes}}:{...old,presentation:{...base,...changes}};return mutate('dashboard_patch',{operations:[{op:'put_component',id,value}]},true,false).catch(showError);}}
        }));
      if(quiet&&card.shadowRoot){const style=el('style');style.textContent='.component-actions,.component-header{display:none!important}.section-card{box-shadow:none!important;border:0!important;border-radius:0!important;padding:0!important;background:transparent!important}.card-body-wrap{height:100%!important;margin:0!important}';card.shadowRoot.append(style);if(c.kind==='chart'&&['bar','line'].includes(c.chartType)){const instance=originalInstances.at(-1)?.app.state.chartInstances['original-'+id];if(instance){const option=instance.getOption();instance.setOption({color:['#444444','#999999','#666666','#bbbbbb'],textStyle:{fontFamily:'Noto Serif CJK SC, Songti SC, serif',color:'#444'},legend:{show:(option.series||[]).length>1},series:(option.series||[]).map((series,index)=>({type:series.type,label:{show:['line','bar'].includes(series.type),color:'#444',position:'top',fontFamily:'Noto Serif CJK SC, serif'},lineStyle:{color:['#444','#999','#666','#bbb'][index%4],width:2},itemStyle:{color:['#444','#999','#666','#bbb'][index%4]},symbolSize:6}))});}}}
      }catch(error){card.append(el('p','error',error.message));}
  }
  async function switchMode(mode){
    if(mode===(doc.manifest.viewMode||'dashboard'))return;
    if(boot.mode==='offline'){doc.manifest.viewMode=mode;render();return;}
    await patch([{op:'set_view_mode',value:mode}]);
  }
  async function saveMarkdown(source){
    const draft=currentDraft();
    await mutate('dashboard_patch',()=>({expectedRevision:draft.revision,operations:[{op:'set_report_markdown',value:source}]}),true,false);
    draft.saved=source;draft.dirty=draft.text!==source;draft.revision=doc.revision;
  }
  function jsonEditor(name,value,save){const {d,body}=dialog(name),area=textarea(value);body.append(area,button(T.save,async()=>{await save(JSON.parse(area.value));d.close();}));}
  function componentEditor(id){
    const old=id?doc.manifest.components[id]:null,{d,body}=dialog(old?T.settings:T.add),key=input(id||'card-'+Date.now().toString(36)),kind=select(['chart','kpi','table','text','legacy'].map(v=>[v,v]),old?.kind||'chart'),name=input(old?.title||'New chart'),subtitle=input(old?.subtitle||old?.config?.subtitle||'');key.disabled=!!id;
    const datasets=Object.keys(doc.manifest.datasets),ds=select(datasets.map(v=>[v,v]),old?.datasetId),mapping=el('div');
    let x,group,measures,type,text,config,family,presentation;
    function fields(){mapping.replaceChildren();const selected=ds.value,meta=doc.manifest.datasets[selected];
      if(kind.value==='text'){text=textarea(old?.text||'');mapping.append(field('Text',text));return;}
      if(kind.value==='legacy'){family=select([['chart','原版图表'],['kpi','原版 KPI'],['table','原版明细表']],old?.family||'chart');mapping.append(field('组件类型',family));config=textarea(old?.config||{code:'c01',title:name.value,unit:'',data:{categories:[],values:[]},presentation:{axisLabels:{x:'Value',y:'Category'},seriesLabels:['Value'],tooltipValueLabels:['Value'],units:[''],tableHeaders:['Category','Value']}});mapping.append(field('Complete legacy chart config (no sample data fallback)',config));return;}
      if(!meta){mapping.append(el('p','error','Import a dataset first.'));return;}
      if(kind.value==='chart'){type=select(chartTypes.map(v=>[v,v]),old?.chartType||'bar');x=select(Object.keys(meta.fields).map(v=>[v,meta.fields[v].label||v]),old?.x);group=select([['','None'],...Object.keys(meta.fields).map(v=>[v,v])],old?.series||'');mapping.append(field('Chart type',type),field('X / category',x),field('Series / heatmap Y',group));}
      if(['chart','kpi'].includes(kind.value)){measures=select(Object.entries(doc.manifest.metrics).filter(([,m])=>m.datasetId===selected).map(([k,m])=>[k,m.label]),old?.measures?.[0]);measures.multiple=kind.value==='chart';measures.size=4;if(old?.measures)for(const o of measures.options)o.selected=old.measures.includes(o.value);mapping.append(field('Measures',measures));}
    }
    kind.onchange=fields;ds.onchange=fields;body.append(field('Component ID',key),field('Kind',kind),field('Title',name),field('Description',subtitle),field('Dataset',ds),mapping);fields();
    if(old&&old.kind!=='legacy'&&old.kind!=='text'){presentation=textarea(old.presentation||{});mapping.append(field('显示设置（保留原版 KPI / 表格参数）',presentation));}
    body.append(button(T.save,async()=>{let value={...(old||{}),kind:kind.value,title:name.value,subtitle:subtitle.value};if(kind.value==='text')value.text=text.value;else if(kind.value==='legacy'){value.family=family.value;value.config=JSON.parse(config.value);if(family.value==='kpi')value.config.label=name.value;else value.config.title=name.value;value.config.subtitle=subtitle.value;}else{value.datasetId=ds.value;if(measures)value.measures=[...measures.selectedOptions].map(o=>o.value);if(kind.value==='chart'){value.chartType=type.value;value.x=x.value;if(group.value)value.series=group.value;else delete value.series;}}if(presentation)value.presentation=JSON.parse(presentation.value);await patch([{op:'put_component',id:key.value,value}]);d.close();}));
    if(id)body.append(button(T.copy,async()=>{await patch([{op:'put_component',id:id+'-'+Date.now().toString(36),value:structuredClone(old)}]);d.close();}),button(T.remove,async()=>{if(!confirm('Remove this component?'))return;await patch([{op:'remove_component',id}]);d.close();},'danger'));
  }
  async function inspect(id){
    const c=doc.manifest.components[id],{body}=dialog(c.title),tabs=el('nav','tabs'),content=el('div');body.append(tabs,content);
    async function display(tab){content.replaceChildren();
      if(tab==='data'){let rows=visibleRows(doc,id);if(c.kind==='legacy'&&!c.binding){const instance=originalInstances.find(i=>i.app.config.charts.some(ch=>ch.instanceId==='original-'+id));if(c.family==='table')rows=c.config.rows;else if(instance){const ch=instance.app.config.charts[0],data=ch.resolvedTable?.();if(data)rows=data.rows.map(r=>Object.fromEntries(data.headers.map((h,i)=>[h,r[i]])));}else rows=[{value:c.config.value,unit:c.config.unit||''}];}content.append(el('p','muted',`Snapshot: ${rows.length} rows`),table(rows));}
      if(tab==='source'){const result=boot.mode==='offline'?{source:doc.manifest.sources[doc.manifest.datasets[c.datasetId]?.sourceId||c.sourceId]}:await transport('query_inspect',{dashboardId:doc.id,componentId:id});content.append(el('pre','code',JSON.stringify(result,null,2)));}
      if(tab==='semantic'){for(const mid of c.measures||[]){const metric=doc.manifest.metrics[mid];content.append(el('h3','',metric.label),el('pre','code',JSON.stringify(metric,null,2)));if(editing)content.append(button(T.edit,()=>jsonEditor(mid,metric,value=>patch([{op:'put_metric',id:mid,value}]))));}if(!c.measures?.length)content.append(el('p','muted','原版组件快照：展示说明与已认证指标是两件事。'),el('pre','code',JSON.stringify(c.config?.explanation||c.config?.presentation||c.config||{},null,2)));}
      if(tab==='settings')content.append(button(T.settings,()=>componentEditor(id)),el('pre','code',JSON.stringify(c,null,2)));
    }
    for(const tab of ['data','source','semantic','settings'])tabs.append(button(T[tab],()=>display(tab)));await display('semantic');
  }
  function catalogDialog(){
    const {body}=dialog('原版组件目录'),search=input(''),list=el('div','catalog-list');search.placeholder='搜索图表名称、编号';body.append(el('p','muted','40 款原版图表 + 9 类 KPI。使用原版组件 JSON 或导入 Workspace，不用通用图表替换原配置。'),search,list);
    const all=Array.isArray(catalog)?catalog:Object.entries(catalog).map(([code,v])=>({code,...v}));
    function draw(){list.replaceChildren();for(const entry of all.filter(e=>JSON.stringify(e).toLowerCase().includes(search.value.toLowerCase()))){const row=el('div','catalog-row');row.append(el('strong','',entry.code||entry.id||''),el('span','',entry.nameZh||entry.title||entry.name||''),button('查看契约',()=>{const {body}=dialog(entry.nameZh||entry.title||entry.name||entry.id||entry.code);body.append(el('pre','code',JSON.stringify(entry,null,2)));}));list.append(row);}for(let i=1;i<=9;i++){const row=el('div','catalog-row');row.append(el('strong','','mc0'+i),el('span','',['标准指标','同比 / 环比','迷你趋势','目标进度','半环仪表','双指标','排名分层','阈值预警','分组拆解'][i-1]));list.append(row);}}
    search.oninput=draw;draw();
  }
  function bindingEditor(id){
    const c=doc.manifest.components[id],{d,body}=dialog('数据绑定 / '+c.title);
    const targets={c01:['categories','values'],c02:['categories','values'],c03:['clusters','budget','actual'],c04:['fleets','deviations'],c06:['hubs','offSeason','peakSeason'],c07:['clusters','base2024','curr2025'],c08:['categories','domestic','intl'],t01:['months','rpk'],t02:['quarters','actual','forecast'],t04:['quarters','premium','economy','cargo','ancillary'],t06:['categories','revenue','yieldGrowth'],d01:['brackets','counts'],fn02:['quarters','revenue','cost'],fn03:['variables','negative','positive']};
    const shape=targets[c.config.code],template={datasetId:'',measures:{}};
    if(c.family==='chart'&&shape){template.categoryField='';template.categoryTarget=shape[0];template.measures=Object.fromEntries(shape.slice(1).map(k=>[k,'']));}
    if(c.family==='kpi'){template.measures=c.config.type==='mc06'?{leftVal:'',rightVal:''}:{value:''};if(c.config.type==='mc03')template.timeField='';}
    const area=textarea(c.binding||template);
    body.append(el('p','muted','引用已有 Dataset 和指标 ID，不改变原组件设计。比例按分子、分母重算；缺少映射会拒绝保存。'),area,el('pre','code',JSON.stringify({datasets:Object.fromEntries(Object.entries(doc.manifest.datasets).map(([k,v])=>[k,v.fields])),metrics:doc.manifest.metrics},null,2)),button(T.save,async()=>{await patch([{op:'put_component',id,value:{...c,binding:JSON.parse(area.value)}}]);d.close();}));
    if(c.binding)body.append(button('移除绑定',async()=>{const value={...c};delete value.binding;delete value.datasetId;delete value.measures;const filters=doc.manifest.filters.map(f=>({...f,componentIds:f.componentIds.filter(k=>k!==id)})).filter(f=>f.componentIds.length);await patch([{op:'put_component',id,value},{op:'set_filters',value:filters}]);d.close();}));
  }
  function importData(){const {d,body}=dialog(T.import),name=input('dataset-'+Date.now().toString(36)),area=textarea('[]'),file=input('','file'),formatSelect=select([['json','JSON rows'],['csv','CSV']],'json');file.accept='.json,.csv';file.onchange=async()=>{area.value=await file.files[0].text();formatSelect.value=file.files[0].name.endsWith('.csv')?'csv':'json';};body.append(field('Dataset ID',name),file,formatSelect,area,button(T.save,async()=>{await mutate('dataset_import',{datasetId:name.value,...(formatSelect.value==='csv'?{csvText:area.value}:{rows:JSON.parse(area.value)}),name:file.files[0]?.name||name.value});d.close();}));}
  function queryEditor(){const {d,body}=dialog('SQL / read-only'),alias=input('analytics'),ds=input('query-result'),sql=textarea('SELECT * FROM your_table LIMIT 100'),params=textarea('{}');body.append(el('p','muted','Only explicitly configured SQLite aliases are executable. No query runs on preview or chart switching.'),field('Connection alias',alias),field('Dataset ID',ds),field('SQL',sql),field('Parameters',params),button('执行只读查询',async()=>{if(!confirm('Execute this read-only query and save a new snapshot?'))return;await mutate('query_execute',{connection:alias.value,datasetId:ds.value,sql:sql.value,parameters:JSON.parse(params.value)});d.close();}));}
  function exportDialog(){const {body}=dialog(T.export);body.append(button('JSON artifact',()=>download(doc.id+'.json',JSON.stringify(doc,null,2))));if(boot.exportFile)body.append(button('Self-contained HTML',()=>boot.exportFile(doc.id)));if(boot.mode!=='offline')body.append(button('Version history',async()=>{const result=await transport('dashboard_history',{dashboardId:doc.id});body.append(el('pre','code',JSON.stringify(result,null,2)));}));}
  window.addEventListener('resize',()=>{if(doc&&bp()!==lastBreakpoint&&!layoutTimer&&!busy)render();});
  if(boot.mode==='web')setInterval(async()=>{if(!doc||busy||layoutTimer||reportDrafts.get(doc.id)?.dirty||document.querySelector('dialog[open]'))return;try{const current=(await transport('dashboard_get',{dashboardId:doc.id})).document;if(current.revision!==doc.revision){doc=current;undo=[];redo=[];render();}}catch(e){showError(e);}},5000);
  window.addEventListener('beforeunload',event=>{if(doc&&reportDrafts.get(doc.id)?.dirty){event.preventDefault();event.returnValue='';}});
  window.addEventListener('charts-error',event=>showError(event.detail));render();
}
