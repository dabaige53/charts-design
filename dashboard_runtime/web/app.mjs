import {initializeOriginal,mountOriginal,catalog} from './original.mjs';
import {aggregate,visibleRows,format,optionFor,chartTable,csv,chartTypes,compatible} from './engine.mjs';

const T={edit:'\u7f16\u8f91',view:'\u9605\u8bfb',add:'\u6dfb\u52a0\u7ec4\u4ef6',import:'\u5bfc\u5165\u6570\u636e',undo:'\u64a4\u9500',redo:'\u91cd\u505a',reload:'\u91cd\u65b0\u8bfb\u53d6',export:'\u5bfc\u51fa',close:'\u5173\u95ed',save:'\u4fdd\u5b58',data:'\u6570\u636e',semantic:'\u6307\u6807\u8bed\u4e49',settings:'\u56fe\u8868\u8bbe\u7f6e',source:'\u67e5\u8be2\u6765\u6e90',remove:'\u5220\u9664',copy:'\u590d\u5236',empty:'\u5bfc\u5165\u6570\u636e\uff0c\u6216\u901a\u8fc7 CLI / MCP \u6dfb\u52a0\u7ec4\u4ef6\u3002'};
const el=(tag,cls='',text='')=>{const n=document.createElement(tag);n.className=cls;n.textContent=text;return n;};
const button=(label,fn,cls='')=>{const b=el('button',cls,label);b.type='button';b.onclick=()=>Promise.resolve().then(fn).catch(showError);return b;};
function showError(error){const n=document.getElementById('notice');if(n){n.textContent=error.message||String(error);n.className='notice error';}else console.error(error);}
function download(name,body,type='application/json'){const a=el('a');a.href=URL.createObjectURL(new Blob([body],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
function field(label,node){const wrap=el('label','field');wrap.append(el('span','',label),node);return wrap;}
function input(value='',kind='text'){const n=el('input');n.type=kind;n.value=value;return n;}
function select(options,value){const n=el('select');for(const [key,label] of options){const o=el('option','',label);o.value=key;n.append(o);}n.value=value??options[0]?.[0]??'';return n;}
function textarea(value){const n=el('textarea');n.value=typeof value==='string'?value:JSON.stringify(value,null,2);n.spellcheck=false;return n;}
function dialog(title){const d=el('dialog','inspector');const head=el('header');head.append(el('h2','',title),button(T.close,()=>d.close()));const body=el('div','inspector-body');d.append(head,body);d.addEventListener('close',()=>d.remove());document.body.append(d);d.showModal();return {d,body};}
function table(rows){
  const wrap=el('div','data-table'), controls=el('div','table-controls'), body=el('div','table-scroll');
  let page=0,sortKey=null,asc=true;const size=20;const keys=[...new Set(rows.flatMap(r=>Object.keys(r)))];
  function render(){body.replaceChildren();controls.replaceChildren();const data=[...rows];
    if(sortKey)data.sort((a,b)=>{const x=a[sortKey],y=b[sortKey];return (typeof x==='number'&&typeof y==='number'?x-y:String(x??'').localeCompare(String(y??''),'zh-CN',{numeric:true}))*(asc?1:-1);});
    const t=el('table'),tr=el('tr');for(const key of keys){const th=el('th');th.append(button(key+(sortKey===key?(asc?' \u2191':' \u2193'):''),()=>{asc=sortKey===key?!asc:true;sortKey=key;page=0;render();}));tr.append(th);}const thead=el('thead');thead.append(tr);t.append(thead);
    const tbody=el('tbody');for(const row of data.slice(page*size,(page+1)*size)){const r=el('tr');for(const key of keys)r.append(el('td','',String(row[key]??'\u2014')));tbody.append(r);}t.append(tbody);body.append(t);
    const prev=button('\u2190',()=>{page--;render();}),next=button('\u2192',()=>{page++;render();});prev.disabled=page===0;next.disabled=(page+1)*size>=rows.length;
    controls.append(el('span','muted',`${rows.length} rows / ${page+1}`),prev,next,button('CSV',()=>download('data.csv',csv(rows),'text/csv;charset=utf-8')));
  }wrap.append(body,controls);render();return wrap;
}

export async function start({echarts,GridStack,App}){
  initializeOriginal(echarts);
  const boot=window.__DASHBOARD_BOOT__||{},root=el('div','workspace');document.body.append(root);
  const top=el('header','topbar'),brand=el('div','brand','CHARTS / WORKSPACE'),title=input('Dashboard'),toolbar=el('div','toolbar'),notice=el('div','notice'),filters=el('div','filters'),canvas=el('main','canvas'),gridEl=el('div','grid-stack');
  notice.id='notice';title.className='dashboard-title';title.setAttribute('aria-label','Dashboard title');top.append(brand,title,toolbar);canvas.append(gridEl);root.append(top,notice,filters,canvas);
  let doc=null,editing=false,grid=null,charts=[],observers=[],undo=[],redo=[],queue=Promise.resolve(),busy=0,layoutTimer=null,app=null;
  let lastBreakpoint=null,tableViews=new Set(),transport,originalInstances=[];
  const bp=()=>window.innerWidth<650?'mobile':window.innerWidth<1050?'tablet':'desktop';
  const status=text=>{notice.textContent=text;notice.className='notice';};
  const accept=result=>{if(result?.error)throw Error(result.error.message);if(result?.isError)throw Error(result.content?.[0]?.text||'Tool failed');return result;};
  const unpack=result=>accept(result.structuredContent || (result.content?.[0]?.text?JSON.parse(result.content[0].text):result));
  if(boot.mode==='mcp'){
    app=new App({name:'Charts Design Dashboard',version:'0.1.0'},{},{autoResize:true});
    app.ontoolresult=result=>{try{const value=unpack(result);if(value.document){doc=value.document;render();}}catch(e){showError(e);}};
    transport=async(name,args)=>unpack(await app.callServerTool({name,arguments:args}));
    await app.connect();
  }else if(boot.mode==='offline'){
    doc=boot.document;
    transport=async()=>{throw Error('Offline snapshot: use Export JSON and import it through CLI to persist server-side changes.');};
    editing=false;
  }else{
    let token=location.hash.slice(1);
    if(token){try{sessionStorage.setItem('charts-runtime-token',token);}catch{}history.replaceState(null,'',location.pathname+location.search);}
    else{try{token=sessionStorage.getItem('charts-runtime-token')||'';}catch{}}
    const authHeaders={'Content-Type':'application/json','Authorization':'Bearer '+token};
    transport=async(name,args)=>{const response=await fetch('/api/tools/'+name,{method:'POST',headers:authHeaders,body:JSON.stringify(args)});const result=await response.json();return accept(result);};
    boot.exportFile=async id=>{const r=await fetch('/api/export/'+encodeURIComponent(id),{headers:authHeaders});if(!r.ok)throw Error((await r.json()).error?.message||'Export failed');download(id+'.html',await r.text(),'text/html');};
    const id=new URLSearchParams(location.search).get('board');
    if(id)doc=(await transport('dashboard_get',{dashboardId:id})).document;
    else{const boards=(await transport('dashboard_list',{})).dashboards;if(boards.length)doc=(await transport('dashboard_get',{dashboardId:boards[0].id})).document;}
  }
  async function mutate(name,args,pushUndo=true){
    if(!doc)throw Error('Create a dashboard first');
    const run=async()=>{busy++;const previous=doc.revision;try{const result=await transport(name,{...args,dashboardId:doc.id,expectedRevision:doc.revision});if(result.document){if(pushUndo){undo.push(previous);redo=[];}doc=result.document;render();}return result;}catch(e){render();showError(e);throw e;}finally{busy--;}};
    const next=queue.then(run,run);queue=next.catch(()=>{});return next;
  }
  const patch=operations=>mutate('dashboard_patch',{operations});
  async function restore(direction){const from=direction==='undo'?undo:redo,to=direction==='undo'?redo:undo;if(!from.length)return;const target=from.pop(),current=doc.revision;try{await mutate('dashboard_restore',{revision:target},false);to.push(current);render();}catch(e){from.push(target);throw e;}}
  async function reload(){if(!doc)return;const next=(await transport('dashboard_get',{dashboardId:doc.id})).document;if(next.revision!==doc.revision){undo=[];redo=[];}doc=next;render();}
  title.onchange=()=>patch([{op:'set_title',value:title.value}]).catch(showError);

  function render(){
    if(!doc){status('Create a dashboard with CLI / MCP, then reload this page.');return;}
    document.documentElement.dataset.theme=doc.manifest.theme;document.title=doc.manifest.title;title.value=doc.manifest.title;title.disabled=!editing;
    toolbar.replaceChildren();
    const edit=button(editing?T.view:T.edit,()=>{editing=!editing;render();});edit.disabled=boot.mode==='offline';toolbar.append(edit);
    if(editing){const u=button(T.undo,()=>restore('undo')),r=button(T.redo,()=>restore('redo'));u.disabled=!undo.length;r.disabled=!redo.length;toolbar.append(button(T.add,()=>componentEditor()),button('\u539f\u7248\u7ec4\u4ef6',catalogDialog),button(T.import,importData),u,r);}
    if(boot.mode!=='offline')toolbar.append(button('SQL',queryEditor),button(doc.manifest.theme==='dark'?'Light':'Dark',()=>patch([{op:'set_theme',value:doc.manifest.theme==='dark'?'light':'dark'}])),button(T.reload,reload));toolbar.append(button(T.export,exportDialog));
    status(`${boot.mode==='offline'?'OFFLINE SNAPSHOT / ':''}${doc.snapshot.status.toUpperCase()}  /  v${doc.revision}  /  ${doc.snapshot.updatedAt}  ${doc.snapshot.status==='fixture'?' / DEMO DATA':''}`);
    filters.replaceChildren();
    for(const f of doc.manifest.filters){const c=doc.manifest.components[f.componentIds[0]],rows=doc.snapshot.datasets[c.datasetId];
      if(f.op==='in'){const values=[...new Map(rows.map(r=>[JSON.stringify(r[f.field]),r[f.field]])).values()];const options=[['','\u5168\u90e8'],...values.map((v,i)=>[String(i),String(v)])];const s=select(options,f.values.length?String(values.findIndex(v=>v===f.values[0])):'');s.disabled=boot.mode==='offline';s.onchange=()=>{const fs=structuredClone(doc.manifest.filters);fs.find(v=>v.id===f.id).values=s.value===''?[]:[values[Number(s.value)]];patch([{op:'set_filters',value:fs}]).catch(showError);};filters.append(field(f.label||f.field,s));}
      else{const a=input(f.values[0]??''),b=input(f.values[1]??'');const numeric=doc.manifest.datasets[c.datasetId].fields[f.field].type==='number';const apply=()=>{const fs=structuredClone(doc.manifest.filters);fs.find(v=>v.id===f.id).values=a.value===''||b.value===''?[]:[numeric?Number(a.value):a.value,numeric?Number(b.value):b.value];return patch([{op:'set_filters',value:fs}]);};filters.append(field(f.label||f.field,a),b,button('\u5e94\u7528',apply));}}
    if(editing)filters.append(button('\u7b5b\u9009\u8bbe\u7f6e',()=>jsonEditor('Filters',doc.manifest.filters,value=>patch([{op:'set_filters',value}]))));
    if(layoutTimer){clearTimeout(layoutTimer);layoutTimer=null;}
    charts.forEach(c=>c.dispose());charts=[];observers.forEach(o=>o.disconnect());observers=[];
    originalInstances.forEach(x=>x.destroy());originalInstances=[];
    if(grid)grid.destroy(false);gridEl.replaceChildren();
    const breakpoint=bp();lastBreakpoint=breakpoint;const columns={desktop:12,tablet:8,mobile:4}[breakpoint];
    grid=GridStack.init({column:columns,cellHeight:48,margin:8,float:true,disableDrag:!editing,disableResize:!editing,
      draggable:{handle:'.layout-handle',cancel:'input,select,textarea,a'},resizable:{handles:'e,se,s,sw,w'},minRow:1},gridEl);
    for(const position of doc.manifest.layout[breakpoint]){
      const id=position.id,c=doc.manifest.components[id],item=el('div','grid-stack-item'),card=el('section','grid-stack-item-content card original-host');
      item.dataset.componentId=id;item.append(card);gridEl.append(item);
      if(editing){const handle=el('button','drag-handle layout-handle','\u283f');handle.title='\u62d6\u52a8\u7ec4\u4ef6';handle.setAttribute('aria-label','\u62d6\u52a8\u7ec4\u4ef6');item.append(handle);}
      grid.makeWidget(item,{...position,minW:2,minH:c.kind==='kpi'||c.family==='kpi'?3:5});
      try{
        if(c.kind==='text'){card.append(el('h2','text-heading',c.title),el('div','text-block',c.text));if(editing)card.append(button(T.edit,()=>componentEditor(id)));}
        else originalInstances.push(mountOriginal(card,{doc,id,editing,readOnly:boot.mode==='offline',
          onInspect:inspect,onEdit:componentEditor,onType:(id,chartType)=>patch([{op:'set_chart',id,chartType}]).catch(showError),
          onPresentation:(id,changes)=>{const old=doc.manifest.components[id];if(old.kind==='legacy'&&old.config.defaultGranularity!==changes.defaultGranularity)return patch([{op:'put_component',id,value:{...old,config:{...old.config,...changes}}}]).catch(showError);}
        }));
      }catch(error){card.append(el('p','error',error.message));}
    }
    if(!Object.keys(doc.manifest.components).length)gridEl.append(el('div','empty',T.empty));
    grid.on('change',()=>{if(!editing)return;clearTimeout(layoutTimer);const value=grid.engine.nodes.map(n=>({id:String(n.id),x:n.x,y:n.y,w:n.w,h:n.h}));layoutTimer=setTimeout(()=>{layoutTimer=null;patch([{op:'set_layout',breakpoint,value}]).catch(showError);},250);});
  }
  function jsonEditor(name,value,save){const {d,body}=dialog(name),area=textarea(value);body.append(area,button(T.save,async()=>{await save(JSON.parse(area.value));d.close();}));}
  function componentEditor(id){
    const old=id?doc.manifest.components[id]:null,{d,body}=dialog(old?T.settings:T.add),key=input(id||'card-'+Date.now().toString(36)),kind=select(['chart','kpi','table','text','legacy'].map(v=>[v,v]),old?.kind||'chart'),name=input(old?.title||'New chart');key.disabled=!!id;
    const datasets=Object.keys(doc.manifest.datasets),ds=select(datasets.map(v=>[v,v]),old?.datasetId),mapping=el('div');
    let x,group,measures,type,text,config,family,presentation;
    function fields(){mapping.replaceChildren();const selected=ds.value,meta=doc.manifest.datasets[selected];
      if(kind.value==='text'){text=textarea(old?.text||'');mapping.append(field('Text',text));return;}
      if(kind.value==='legacy'){family=select([['chart','\u539f\u7248\u56fe\u8868'],['kpi','\u539f\u7248 KPI'],['table','\u539f\u7248\u660e\u7ec6\u8868']],old?.family||'chart');mapping.append(field('\u7ec4\u4ef6\u7c7b\u578b',family));config=textarea(old?.config||{code:'c01',title:name.value,unit:'',data:{categories:[],values:[]},presentation:{axisLabels:{x:'Value',y:'Category'},seriesLabels:['Value'],tooltipValueLabels:['Value'],units:[''],tableHeaders:['Category','Value']}});mapping.append(field('Complete legacy chart config (no sample data fallback)',config));return;}
      if(!meta){mapping.append(el('p','error','Import a dataset first.'));return;}
      if(kind.value==='chart'){type=select(chartTypes.map(v=>[v,v]),old?.chartType||'bar');x=select(Object.keys(meta.fields).map(v=>[v,meta.fields[v].label||v]),old?.x);group=select([['','None'],...Object.keys(meta.fields).map(v=>[v,v])],old?.series||'');mapping.append(field('Chart type',type),field('X / category',x),field('Series / heatmap Y',group));}
      if(['chart','kpi'].includes(kind.value)){measures=select(Object.entries(doc.manifest.metrics).filter(([,m])=>m.datasetId===selected).map(([k,m])=>[k,m.label]),old?.measures?.[0]);measures.multiple=kind.value==='chart';measures.size=4;if(old?.measures)for(const o of measures.options)o.selected=old.measures.includes(o.value);mapping.append(field('Measures',measures));}
    }kind.onchange=fields;ds.onchange=fields;body.append(field('Component ID',key),field('Kind',kind),field('Title',name),field('Dataset',ds),mapping);fields();
    if(old&&old.kind!=='legacy'&&old.kind!=='text'){presentation=textarea(old.presentation||{});mapping.append(field('\u663e\u793a\u8bbe\u7f6e\uff08\u4fdd\u7559\u539f\u7248 KPI / \u8868\u683c\u53c2\u6570\uff09',presentation));}
    body.append(button(T.save,async()=>{let value={...(old||{}),kind:kind.value,title:name.value};if(kind.value==='text')value.text=text.value;else if(kind.value==='legacy'){value.family=family.value;value.config=JSON.parse(config.value);if(family.value==='kpi')value.config.label=name.value;else value.config.title=name.value;}else{value.datasetId=ds.value;if(measures)value.measures=[...measures.selectedOptions].map(o=>o.value);if(kind.value==='chart'){value.chartType=type.value;value.x=x.value;if(group.value)value.series=group.value;else delete value.series;}}if(presentation)value.presentation=JSON.parse(presentation.value);await patch([{op:'put_component',id:key.value,value}]);d.close();}));
    if(id){body.append(button(T.copy,async()=>{await patch([{op:'put_component',id:id+'-'+Date.now().toString(36),value:structuredClone(old)}]);d.close();}),button(T.remove,async()=>{if(!confirm('Remove this component?'))return;await patch([{op:'remove_component',id}]);d.close();},'danger'));}
  }
  async function inspect(id){
    const c=doc.manifest.components[id],{body}=dialog(c.title),tabs=el('nav','tabs'),content=el('div');body.append(tabs,content);
    async function display(tab){content.replaceChildren();
      if(tab==='data'){let rows=visibleRows(doc,id);if(c.kind==='legacy'){const instance=originalInstances.find(i=>i.app.config.charts.some(ch=>ch.instanceId==='original-'+id));if(c.family==='table')rows=c.config.rows;else if(instance){const ch=instance.app.config.charts[0],data=ch.resolvedTable?.();if(data)rows=data.rows.map(r=>Object.fromEntries(data.headers.map((h,i)=>[h,r[i]])));}else rows=[{value:c.config.value,unit:c.config.unit||''}];}content.append(el('p','muted',`Snapshot: ${rows.length} rows`),table(rows));}
      if(tab==='source'){const result=boot.mode==='offline'?{source:doc.manifest.sources[doc.manifest.datasets[c.datasetId]?.sourceId||c.sourceId]}:await transport('query_inspect',{dashboardId:doc.id,componentId:id});content.append(el('pre','code',JSON.stringify(result,null,2)));}
      if(tab==='semantic'){for(const mid of c.measures||[]){const metric=doc.manifest.metrics[mid];content.append(el('h3','',metric.label),el('pre','code',JSON.stringify(metric,null,2)));if(editing)content.append(button(T.edit,()=>jsonEditor(mid,metric,value=>patch([{op:'put_metric',id:mid,value}]))));}if(!c.measures?.length){content.append(el('p','muted','\u539f\u7248\u7ec4\u4ef6\u5feb\u7167\uff1a\u5c55\u793a\u8bf4\u660e\u4e0e\u5df2\u8ba4\u8bc1\u6307\u6807\u662f\u4e24\u4ef6\u4e8b\u3002'),el('pre','code',JSON.stringify(c.config?.explanation||c.config?.presentation||c.config||{},null,2)));}}
      if(tab==='settings')content.append(button(T.settings,()=>componentEditor(id)),el('pre','code',JSON.stringify(c,null,2)));
    }
    for(const tab of ['data','source','semantic','settings'])tabs.append(button(T[tab],()=>display(tab)));await display('semantic');
  }
  function catalogDialog(){
    const {body}=dialog('\u539f\u7248\u7ec4\u4ef6\u76ee\u5f55'),search=input(''),list=el('div','catalog-list');search.placeholder='\u641c\u7d22\u56fe\u8868\u540d\u79f0\u3001\u7f16\u53f7';
    body.append(el('p','muted','40 \u6b3e\u539f\u7248\u56fe\u8868 + 9 \u7c7b KPI\u3002\u4f7f\u7528\u539f\u7248\u7ec4\u4ef6 JSON \u6216\u5bfc\u5165 Workspace\uff0c\u4e0d\u7528\u901a\u7528\u56fe\u8868\u66ff\u6362\u539f\u914d\u7f6e\u3002'),search,list);
    const all=Array.isArray(catalog)?catalog:Object.entries(catalog).map(([code,v])=>({code,...v}));
    function draw(){list.replaceChildren();for(const entry of all.filter(e=>JSON.stringify(e).toLowerCase().includes(search.value.toLowerCase()))){const row=el('div','catalog-row');row.append(el('strong','',entry.code||entry.id||''),el('span','',entry.nameZh||entry.title||entry.name||''),button('\u67e5\u770b\u5951\u7ea6',()=>{const {body}=dialog(entry.nameZh||entry.title||entry.name||entry.id||entry.code);body.append(el('pre','code',JSON.stringify(entry,null,2)));}));list.append(row);}for(let i=1;i<=9;i++){const row=el('div','catalog-row');row.append(el('strong','','mc0'+i),el('span','',['\u6807\u51c6\u6307\u6807','\u540c\u6bd4 / \u73af\u6bd4','\u8ff7\u4f60\u8d8b\u52bf','\u76ee\u6807\u8fdb\u5ea6','\u534a\u73af\u4eea\u8868','\u53cc\u6307\u6807','\u6392\u540d\u5206\u5c42','\u9608\u503c\u9884\u8b66','\u5206\u7ec4\u62c6\u89e3'][i-1]));list.append(row);}}
    search.oninput=draw;draw();
  }
  function importData(){const {d,body}=dialog(T.import),name=input('dataset-'+Date.now().toString(36)),area=textarea('[]'),file=input('','file'),formatSelect=select([['json','JSON rows'],['csv','CSV']],'json');file.accept='.json,.csv';file.onchange=async()=>{area.value=await file.files[0].text();formatSelect.value=file.files[0].name.endsWith('.csv')?'csv':'json';};body.append(field('Dataset ID',name),file,formatSelect,area,button(T.save,async()=>{await mutate('dataset_import',{datasetId:name.value,...(formatSelect.value==='csv'?{csvText:area.value}:{rows:JSON.parse(area.value)}),name:file.files[0]?.name||name.value});d.close();}));}
  function queryEditor(){const {d,body}=dialog('SQL / read-only'),alias=input('analytics'),ds=input('query-result'),sql=textarea('SELECT * FROM your_table LIMIT 100'),params=textarea('{}');body.append(el('p','muted','Only explicitly configured SQLite aliases are executable. No query runs on preview or chart switching.'),field('Connection alias',alias),field('Dataset ID',ds),field('SQL',sql),field('Parameters',params),button('\u6267\u884c\u53ea\u8bfb\u67e5\u8be2',async()=>{if(!confirm('Execute this read-only query and save a new snapshot?'))return;await mutate('query_execute',{connection:alias.value,datasetId:ds.value,sql:sql.value,parameters:JSON.parse(params.value)});d.close();}));}
  function exportDialog(){const {body}=dialog(T.export);body.append(button('JSON artifact',()=>download(doc.id+'.json',JSON.stringify(doc,null,2))));if(boot.exportFile)body.append(button('Self-contained HTML',()=>boot.exportFile(doc.id)));body.append(button('Version history',async()=>{const result=await transport('dashboard_history',{dashboardId:doc.id});body.append(el('pre','code',JSON.stringify(result,null,2)));}));}
  window.addEventListener('resize',()=>{if(doc&&bp()!==lastBreakpoint&&!layoutTimer&&!busy)render();});
  if(boot.mode==='web')setInterval(async()=>{if(!doc||busy||layoutTimer||document.querySelector('dialog[open]'))return;try{const current=(await transport('dashboard_get',{dashboardId:doc.id})).document;if(current.revision!==doc.revision){doc=current;undo=[];redo=[];render();}}catch(e){showError(e);}},5000);
  window.addEventListener('charts-error',event=>showError(event.detail));
  render();
}
