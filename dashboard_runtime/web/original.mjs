import {resolveOriginal} from './bindings.mjs';
import {installChrome} from './chrome.mjs';
/* Original components are extracted at build time, never reauthored as lookalikes. */
import DOMPurify from 'dompurify';
import {createOriginalComponents} from '../../runtime-ui/generated/original-engine.mjs';
import originalStyle from '../../runtime-ui/generated/original-style.mjs';
import catalog from '../../runtime-ui/generated/catalog.json';
import {aggregate,visibleRows,format,optionFor,chartTable,csv} from './engine.mjs';

export {catalog};
const methods=new Set(['onColumnVisibilityChange','onTablePageSizeChange','resetDefaultColumns','sortTable','toggleColumnDrawer','prevTablePage','nextTablePage','copyCell','exportTableToCSV','onTableRowHover','onTableRowLeave','onSearchInput','onSearchKeyDown','showSearchSuggestions','applySearchKeyword','clearSearchKeyword']);
function trustedCall(expression){
  const match=/^window\.getDashboardAppForElement\(this\)\.([A-Za-z]+)\((.*)\)$/.exec(expression);
  if(!match||!methods.has(match[1]))return null;
  const args=[],input=match[2];let at=0;
  while(at<input.length){const found=/^\s*('(?:\\.|[^'\\])*'|true|false|event|this\.value|this\.checked)\s*(,|$)/.exec(input.slice(at));if(!found)return null;
    const value=found[1];args.push(value.startsWith("'")?{literal:value.slice(1,-1).replace(/\\(['\\])/g,'$1')}:{ref:value});at+=found[0].length;}
  return {method:match[1],args};
}
DOMPurify.addHook('uponSanitizeAttribute',(node,data)=>{
  if(/^on/.test(data.attrName)){
    const event=data.attrName.slice(2),call=trustedCall(data.attrValue);
    if(call&&['click','change','input','keydown','focus','mouseenter','mouseleave'].includes(event))node.setAttribute('data-original-'+event,JSON.stringify(call));
    data.keepAttr=false;
  }
  if(['src','href','xlink:href','formaction'].includes(data.attrName))data.keepAttr=false;
  if(data.attrName==='style'&&/url\s*\(|expression\s*\(|@import/i.test(data.attrValue))data.keepAttr=false;
});
function setOriginalHtml(node,markup){
  const options={ADD_TAGS:['dialog'],FORBID_TAGS:['script','iframe','object','embed','img','form'],ALLOW_DATA_ATTR:true,RETURN_DOM_FRAGMENT:true};
  const text=String(markup??''),tag=node.tagName?.toLowerCase();
  const wrappers={table:['<table>','</table>','table'],thead:['<table><thead>','</thead></table>','thead'],tbody:['<table><tbody>','</tbody></table>','tbody'],tfoot:['<table><tfoot>','</tfoot></table>','tfoot'],tr:['<table><tbody><tr>','</tr></tbody></table>','tr'],colgroup:['<table><colgroup>','</colgroup></table>','colgroup']};
  const wrap=wrappers[tag];
  if(wrap){const fragment=DOMPurify.sanitize(wrap[0]+text+wrap[1],options);const context=fragment.querySelector(wrap[2]);node.replaceChildren(...(context?Array.from(context.childNodes):[]));}
  else node.replaceChildren(DOMPurify.sanitize(text,options));
}
const node=(tag,cls='',text='')=>{const e=document.createElement(tag);e.className=cls;e.textContent=text;return e;};
function download(name,body,type){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([body],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
let api=null;
const sharedStyles=new Map();
export function appendOriginalStyle(shadow,text){
  if('adoptedStyleSheets' in shadow&&typeof CSSStyleSheet!=='undefined'&&CSSStyleSheet.prototype.replaceSync){
    let sheet=sharedStyles.get(text);
    if(!sheet){sheet=new CSSStyleSheet();sheet.replaceSync(text);sharedStyles.set(text,sheet);}
    shadow.adoptedStyleSheets=[...shadow.adoptedStyleSheets,sheet];
  }else{const style=node('style');style.textContent=text;shadow.append(style);}
}
export function initializeOriginal(echarts){api=createOriginalComponents(echarts,setOriginalHtml);const fallback=api.ChartDataToTableConverter.convert;api.ChartDataToTableConverter.convert=(inst,c)=>c?.resolvedTable?c.resolvedTable():fallback(inst,c);return api;}
function originalConfig(doc,id){
  const c=doc.manifest.components[id];
  const cfg={meta:{title:c.title},filters:[],kpis:[],charts:[],table:{columns:[],rows:[]},explanations:{...api.explanations}};
  let family=c.kind==='legacy'?(c.family||'chart'):c.kind;
  const key='original-'+id;let raw=doc.computed?.components?.[id]??(c.kind==='legacy'?resolveOriginal(doc,id,c.config.defaultGranularity||'month'):c.config),rows=[];
  if(family==='chart'){
    let chart;
    if(c.kind==='legacy'){
      if(!api.builders[raw.code])throw Error('Unknown original chart code: '+raw.code);
      chart={...api.builders[raw.code],...structuredClone(raw),id:key,instanceId:key,title:c.title,subtitle:c.subtitle??raw.subtitle??''};
      chart.data=structuredClone(raw.data);chart.presentation=structuredClone(raw.presentation);
    }else{
      chart={id:key,instanceId:key,code:c.chartType,title:c.title,subtitle:c.subtitle||'',hasGranularity:false,
        data:{resolved:optionFor(doc,id)},optionBuilder:data=>data.resolved,tableDataExtractor:()=>{const values=chartTable(doc,id),headers=Object.keys(values[0]||{});return {headers,rows:values.map(row=>headers.map(h=>row[h]))};}};
    }
    const builder=chart.optionBuilder,extractor=chart.tableDataExtractor;let selectedGranularity='month';if(extractor)chart.resolvedTable=()=>extractor(chart.data,c.binding?'month':selectedGranularity,chart);
    chart.optionBuilder=(...args)=>{
      selectedGranularity=args[1]||'month';if(c.binding){chart.data=resolveOriginal(doc,id,selectedGranularity).data;args[0]=chart.data;args[1]='month';}const option=builder(...args);
      function protect(value){if(!value||typeof value!=='object')return;for(const [k,v]of Object.entries(value)){if(k==='tooltip'&&v&&typeof v==='object'&&typeof v.formatter==='function'){const formatter=v.formatter;v.formatter=(...a)=>DOMPurify.sanitize(String(formatter(...a)),{FORBID_TAGS:['img','iframe','script'],FORBID_ATTR:['src','href']});}else if(v&&typeof v==='object')protect(v);}}
      protect(option);return option;
    };
    cfg.charts=[chart];
    if(raw?.explanation)cfg.explanations[chart.explainKey||raw.code]=raw.explanation;
  }else if(family==='kpi'){
    if(c.kind!=='legacy'&&!doc.computed?.components?.[id]){
      const m=doc.manifest.metrics[c.measures[0]],value=aggregate(visibleRows(doc,id),m);
      raw={...(c.presentation||{}),type:c.presentation?.type||'mc01',label:c.title,value:format(value,m),yoy:c.presentation?.yoy??'—',statusBadge:m.status==='reviewed'?'已复核':'待复核',subLabel:c.presentation?.subLabel||'统计口径',subVal:c.presentation?.subVal||({sum:'合计',ratio:'分子 / 分母',avg:'平均',count:'计数'}[m.aggregation]||m.aggregation)};
      if(doc.manifest.filters.some(f=>f.componentIds.includes(id)&&f.values.length)){for(const key of ['yoy','mom','subVal','leftVal','rightVal','trendLabel','gaugeSub'])if(key in raw)raw[key]='—';raw.subLabel='当前筛选范围';}
      if(raw.type==='mc03'&&c.presentation?.timeField){const groups=new Map();for(const row of visibleRows(doc,id)){const k=row[c.presentation.timeField];if(!groups.has(k))groups.set(k,[]);groups.get(k).push(row);}raw.sparkMonths=[...groups.keys()];raw.sparkData=[...groups.values()].map(r=>{const v=aggregate(r,m);return m.format==='percent'&&v!=null?v*100:v;});}
      cfg.explanations[key]={title:m.label,overview:m.definition,type:raw.type,period:m.period||'当前筛选范围',metrics:[{name:m.label,definition:m.definition,formula:m.aggregation==='ratio'?`SUM(${m.numerator}) / SUM(${m.denominator})`:`${m.aggregation.toUpperCase()}(${m.field||'*'})`,rule:'展示样式不代表指标已认证'}]};
    }
    cfg.kpis=[{...structuredClone(raw),sparkData:raw.sparkData??raw.sparkline,id:key,explainKey:raw.explainKey||key}];
    if(c.kind==='legacy')cfg.explanations[key]=raw.explanation||api.explanations[raw.type]||{title:c.title,overview:'原始指标卡片快照'};
  }else if(family==='table'){
    rows=doc.computed?.components?.[id]?.rows??(c.kind==='legacy'?raw.rows:visibleRows(doc,id));
    cfg.table={...(raw||c.presentation||{}),id:key,title:c.title,rows,columns:raw?.columns||c.presentation?.columns||Object.entries(doc.manifest.datasets[c.datasetId].fields).map(([key,meta])=>({key,title:meta.label||key,align:meta.type==='number'?'right':'left'}))};
    cfg.table.columns=cfg.table.columns.map(col=>({...col,title:col.title??col.label??col.key}));
    if(doc.computed?.tables?.[id])cfg.table.remotePage=doc.computed.tables[id];
  }
  return {cfg,c,family,raw};
}
export function mountOriginal(host,{doc,id,onInspect,onEdit,onType,onPresentation,onBinding,onAnnotate,onText,onLocalQuery,onLocalExport,editing=false,readOnly=false,deferChart=false,onReady}){
  const shadow=host.shadowRoot||host.attachShadow({mode:'open'});shadow.replaceChildren();shadow.adoptedStyleSheets=[];appendOriginalStyle(shadow,originalStyle);host.dataset.theme='light';
  let {cfg,c,family,raw}=originalConfig(doc,id);const key='original-'+id;
  const container=node(family==='table'?'section':'div',family==='table'?'section-card':'');container.id={chart:'app-charts-grid',kpi:'app-kpis',table:'app-table-section'}[family];shadow.append(container);
  const overlay=node('dialog','explanation-dialog');overlay.id='app-explain-dialog';shadow.append(overlay);
  const feedback=node('div');feedback.id='app-toast-container';shadow.append(feedback);
  const app=new api.DashboardApp(cfg,shadow);const controller=new AbortController();
  for(const event of ['click','change','input','keydown','focus','mouseenter','mouseleave'])shadow.addEventListener(event,e=>{
    const target=e.target.closest?.('[data-original-'+event+']');if(!target)return;
    try{const call=JSON.parse(target.getAttribute('data-original-'+event));if(!methods.has(call.method))return;const args=call.args.map(a=>'literal'in a?a.literal:({'event':e,'this.value':target.value,'this.checked':target.checked,'true':true,'false':false}[a.ref]));app[call.method](...args);}catch(error){app.showToast(error.message);}
  },{signal:controller.signal,capture:event==='focus'||event==='mouseenter'||event==='mouseleave'});
  app.setTableCrossFilter=()=>{};
  let deferred=deferChart&&family==='chart';const initCharts=app.initCharts.bind(app);
  app.initCharts=()=>{if(!deferred)initCharts();};
  const ensure=()=>{if(!deferred)return;deferred=false;initCharts();onReady?.();};
  shadow.addEventListener('click',ensure,{capture:true,signal:controller.signal});
  app.init();
  if(family==='kpi'&&['mc01','mc02','mc03','mc04','mc05'].includes(raw.type)){for(const span of shadow.querySelectorAll('#app-kpis span'))if(span.textContent.trim()==='—'&&!span.classList.contains('text-2xl'))span.hidden=true;}

  let updateTable=null,renderTableRows=null;
  if(family==='table'){
    const remote=doc.computed?.tables?.[id];
    const saved={...(c.kind==='legacy'?c.config:c.presentation)?.tableState,...(remote||{})};
    if(saved){if(Array.isArray(saved.columns))app.state.table.orderedColumns=saved.columns.map(k=>cfg.table.columns.find(col=>col.key===k)).filter(Boolean);
      if(Array.isArray(saved.visible))app.state.table.visibleCols=new Set(saved.visible);
      if(saved.pageSize)app.state.table.pageSize=saved.pageSize;if(saved.page)app.state.table.page=saved.page;
      if(saved.sortCol){app.state.table.sortCol=saved.sortCol;app.state.table.sortDir=saved.sortDir;}
      app.renderColCheckboxes();app.renderTableEngine();}
    let persistTimer;const originalRender=app.renderTableEngine.bind(app);renderTableRows=originalRender;
    app.renderTableEngine=(...args)=>{const result=originalRender(...args);clearTimeout(persistTimer);
      if(onPresentation&&!readOnly)persistTimer=setTimeout(()=>onPresentation(id,{tableState:{columns:app.state.table.orderedColumns.map(x=>x.key),visible:[...app.state.table.visibleCols],page:app.state.table.page,pageSize:app.state.table.pageSize,sortCol:app.state.table.sortCol,sortDir:app.state.table.sortDir}}),350);
      return result;};controller.signal.addEventListener('abort',()=>clearTimeout(persistTimer));
  }
  app.copyCell=text=>navigator.clipboard?.writeText(String(text??'')).then(()=>app.showToast('已复制')).catch(()=>app.showToast('浏览器未授权剪贴板'));
  if(family==='table'){
    app.exportTableToCSV=()=>{const cols=app.state.table.orderedColumns.filter(c=>app.state.table.visibleCols.has(c.key)),result=app.getFilteredTableRows().map(r=>Object.fromEntries(cols.map(col=>[col.title,r[col.key]])));download(c.title+'.csv',csv(result),'text/csv;charset=utf-8');};
    const search=node('input','catalog-search');search.placeholder='搜索明细';search.setAttribute('aria-label','搜索明细');search.oninput=()=>{app.state.keyword=search.value;app.state.table.page=1;app.renderTableEngine();};shadow.querySelector('#app-table-section>div:first-child').prepend(search);
    if(cfg.table.remotePage&&onLocalQuery){
      const remote=cfg.table.remotePage;
      updateTable=(data,state)=>{
        if(!state||!Array.isArray(data?.rows))return false;
        cfg.table.rows=data.rows;Object.assign(remote,state);
        Object.assign(app.state.table,{page:state.page,pageSize:state.pageSize,sortCol:state.sortCol,sortDir:state.sortDir});
        app.state.keyword=state.keyword||'';
        const size=shadow.querySelector('select[data-original-change]');if(size)size.value=state.pageSize===9999?'all':String(state.pageSize);
        renderTableRows();return true;
      };
      const request=changes=>onLocalQuery(id,{tableState:{...remote,...changes}}).catch(error=>app.showToast(error.message));
      app.prevTablePage=()=>remote.page>1&&request({page:remote.page-1});
      app.nextTablePage=()=>remote.page*remote.pageSize<remote.totalRows&&request({page:remote.page+1});
      app.onTablePageSizeChange=value=>request({page:1,pageSize:value==='all'?9999:Number(value)});
      app.sortTable=field=>request({page:1,sortCol:field,sortDir:remote.sortCol===field&&remote.sortDir==='desc'?'asc':'desc'});
      search.value=remote.keyword||'';let searchTimer;
      search.oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>request({page:1,keyword:search.value}),200);};
      controller.signal.addEventListener('abort',()=>clearTimeout(searchTimer));
      const all=shadow.querySelector('select[data-original-change] option[value="all"]');if(all)all.textContent='9999 条';
      app.exportTableToCSV=()=>onLocalExport?.(id,{columns:app.state.table.orderedColumns.filter(col=>app.state.table.visibleCols.has(col.key)).map(col=>col.key),sort:remote.sortCol?[{field:remote.sortCol,direction:remote.sortDir}]:[],search:remote.keyword||''}).then(result=>app.showToast(`已导出 ${result.export.rowCount} 条到本机：${result.export.path}`)).catch(error=>app.showToast(error.message));
    }else if(cfg.table.remotePage){
      const message='当前页快照；完整明细请在本机看板中导出';
      const notice=node('p','component-snapshot-notice',message);shadow.querySelector('#app-table-section>div:first-child').append(notice);
      search.disabled=true;
      app.prevTablePage=app.nextTablePage=app.onTablePageSizeChange=app.sortTable=app.exportTableToCSV=()=>app.showToast(message);
      for(const control of shadow.querySelectorAll('#app-table-section select'))control.disabled=true;
    }
  }
  const actions=shadow.querySelector('.card-header-wrap>div:last-child')||shadow.querySelector('.section-card>div:first-child>div:last-child')||shadow.querySelector('.section-card>div:first-child');
  if(actions){
    if(family==='chart'&&c.kind==='legacy'){
      const choice=node('select');choice.setAttribute('aria-label','Chart type');choice.disabled=readOnly;
      const compatible=['c01','c02'].includes(raw.code)?['c01','c02']:[raw.code];
      for(const code of compatible){const option=node('option','',catalog.find(entry=>entry.id===code)?.nameZh||'当前图表');option.value=code;choice.append(option);}
      if(compatible.length===1){const unavailable=node('option','','暂无兼容类型，保留当前数据结构');unavailable.value='';unavailable.disabled=true;choice.append(unavailable);}
      choice.value=raw.code;choice.onchange=()=>onType(id,choice.value);actions.prepend(choice);
    }
  }
  if(family==='chart'){
    shadow.addEventListener('click',e=>{
      const csvButton=e.target.closest('.export-chart-btn'),copyButton=e.target.closest('.copy-chart-btn');
      if(csvButton){e.stopImmediatePropagation();const chart=app.config.charts[0],gran=app.state.chartGranularities[key],data=chart.tableDataExtractor(chart.data,c.binding?'month':gran,chart);download(c.title+'.csv',csv(data.rows.map(r=>Object.fromEntries(data.headers.map((h,i)=>[h,r[i]])))),'text/csv;charset=utf-8');}
      if(copyButton){e.stopImmediatePropagation();const url=app.state.chartInstances[key].getDataURL({pixelRatio:2,backgroundColor:'#fff'});fetch(url).then(r=>r.blob()).then(async blob=>{try{if(!navigator.clipboard?.write)throw Error();await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);app.showToast('已复制 2x PNG');}catch{const a=document.createElement('a');a.href=url;a.download=c.title+'.png';a.click();app.showToast('剪贴板不可用，已导出 PNG');}}).catch(error=>app.showToast(error.message));}
      const gran=e.target.closest('.granularity-tab-btn');if(gran&&doc.computed&&c.binding?.timeGrain&&onLocalQuery){e.stopImmediatePropagation();onLocalQuery(id,{granularity:gran.dataset.granularity}).catch(error=>app.showToast(error.message));return;}if(gran&&onPresentation&&!readOnly)setTimeout(()=>onPresentation(id,{defaultGranularity:gran.dataset.granularity}),0);
    },{capture:true,signal:controller.signal});
    const saved=c.kind==='legacy'?raw.defaultGranularity:null;if(saved==='quarter'){app.state.chartGranularities[key]='quarter';shadow.querySelectorAll('.granularity-tab-btn').forEach(button=>{const active=button.dataset.granularity==='quarter';button.classList.toggle('bg-white',active);button.classList.toggle('font-semibold',active);button.classList.toggle('shadow-xs',active);button.classList.toggle('text-primary-strong',active);button.classList.toggle('text-ink-muted',!active);});const spec=app.config.charts[0];app.state.chartInstances[key]?.setOption(spec.optionBuilder(spec.data,'quarter',api.TOKENS,spec),true);}
  }
  const fullscreen=node('dialog');fullscreen.className='original-fullscreen';shadow.append(fullscreen);let placeholder=null;
  fullscreen.addEventListener('close',()=>{const card=fullscreen.querySelector('.section-card');if(card&&placeholder){card.classList.remove('card-fullscreen');placeholder.replaceWith(card);placeholder=null;const b=card.querySelector('.fullscreen-btn');if(b)setOriginalHtml(b,api.LUCIDE_ICONS.maximize);Object.values(app.state.chartInstances).forEach(i=>i.resize());}});
  shadow.addEventListener('click',e=>{const b=e.target.closest('.fullscreen-btn');if(!b)return;e.stopImmediatePropagation();if(fullscreen.open)fullscreen.close();else{const card=b.closest('.section-card');placeholder=document.createComment('original-card-position');card.replaceWith(placeholder);fullscreen.append(card);card.classList.add('card-fullscreen');setOriginalHtml(b,api.LUCIDE_ICONS.minimize);fullscreen.showModal();requestAnimationFrame(()=>Object.values(app.state.chartInstances).forEach(i=>i.resize()));}},{capture:true,signal:controller.signal});
  let disposeChrome=installChrome({shadow,app,component:c,family,id,editing,onInspect,onEdit,onBinding,onAnnotate,onText});
  const signature=value=>JSON.stringify(value,(key,item)=>['durationMs','totalDurationMs','cacheHits','responseBytes'].includes(key)?undefined:item);
  const inputs=value=>signature([value.manifest.components[id],value.computed?.components?.[id],value.computed?.tables?.[id],value.computed?.grouped?.[id],value.manifest.metrics,value.manifest.datasets,value.manifest.filters.filter(f=>f.componentIds.includes(id)),value.computed?null:value.snapshot.datasets,value.computed?null:value.snapshot.componentData]);
  let inputSignature=inputs(doc);
  let configSignature=signature(cfg),chromeSignature=signature([c.title,c.subtitle,c.config?.description,editing,raw?.statusBadge]);
  function update(nextDoc,nextEditing=false,nextReadOnly=false){
    const nextInput=inputs(nextDoc);if(nextInput===inputSignature&&nextEditing===editing&&nextReadOnly===readOnly){doc=nextDoc;return true;}
    inputSignature=nextInput;const next=originalConfig(nextDoc,id);
    if(next.family!==family||(family==='chart'&&next.cfg.charts[0].code!==cfg.charts[0].code)||(family==='kpi'&&next.raw.type!==raw.type))return false;
    doc=nextDoc;c=next.c;raw=next.raw;editing=nextEditing;readOnly=nextReadOnly;
    const nextSignature=signature(next.cfg);
    if(nextSignature!==configSignature){
      if(family==='chart'&&next.raw?.defaultGranularity){const granularity=next.raw.defaultGranularity;app.state.chartGranularities[key]=granularity;shadow.querySelectorAll('.granularity-tab-btn').forEach(button=>{const active=button.dataset.granularity===granularity;for(const cls of ['bg-white','font-semibold','shadow-xs','text-primary-strong'])button.classList.toggle(cls,active);button.classList.toggle('text-ink-muted',!active);});}

      if(family==='table'&&cfg.table.remotePage&&next.cfg.table.remotePage){
        const previousColumns=signature(cfg.table.columns);cfg.table.columns=next.cfg.table.columns;
        if(previousColumns!==signature(cfg.table.columns)){app.state.table.orderedColumns=cfg.table.columns;app.state.table.visibleCols=new Set(cfg.table.columns.map(col=>col.key));app.renderColCheckboxes();}
        updateTable?.(next.cfg.table,next.cfg.table.remotePage);
      }else {app.updateConfig(next.cfg);cfg=app.config;}
      configSignature=nextSignature;
    }
    const nextChrome=signature([c.title,c.subtitle,c.config?.description,editing,raw?.statusBadge]);
    if(nextChrome!==chromeSignature){
      const choice=shadow.querySelector('select[aria-label="Chart type"]');if(choice)choice.disabled=readOnly;
      disposeChrome();disposeChrome=installChrome({shadow,app,component:c,family,id,editing,onInspect,onEdit,onBinding,onAnnotate,onText});chromeSignature=nextChrome;
    }
    return true;
  }
  return {id,app,shadow,ensure,update,updateTable,destroy(){disposeChrome();controller.abort();if(fullscreen.open)fullscreen.close();app.destroy();}};
}
