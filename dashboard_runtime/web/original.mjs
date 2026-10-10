import {resolveOriginal} from './bindings.mjs';
import {installChrome} from './chrome.mjs';
/* Original components are extracted at build time, never reauthored as lookalikes. */
import DOMPurify from 'dompurify';
import {createOriginalComponents} from '../../runtime-ui/generated/original-engine.mjs';
import originalStyle from '../../runtime-ui/generated/original-style.mjs';
import catalog from '../../runtime-ui/generated/catalog.json';
import {aggregate,visibleRows,format,optionFor,chartTable,csv,chartTypes,compatible} from './engine.mjs';

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
function action(label,html,run){const b=node('button','chart-action-btn catalog-source-btn');b.type='button';b.title=label;b.setAttribute('aria-label',label);if(html)setOriginalHtml(b,html);else b.textContent=label;b.addEventListener('click',e=>{e.stopPropagation();Promise.resolve().then(run).catch(error=>window.dispatchEvent(new CustomEvent('charts-error',{detail:error})));});return b;}
function download(name,body,type){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([body],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
const names={bar:'柱状图',line:'折线图',area:'面积图',pie:'环形图',scatter:'散点图',heatmap:'热力图',funnel:'漏斗图',waterfall:'瀑布图'};
let api=null;
export function initializeOriginal(echarts){api=createOriginalComponents(echarts,setOriginalHtml);const fallback=api.ChartDataToTableConverter.convert;api.ChartDataToTableConverter.convert=(inst,c)=>c?.resolvedTable?c.resolvedTable():fallback(inst,c);return api;}
export function mountOriginal(host,{doc,id,onInspect,onEdit,onType,onPresentation,onBinding,editing=false,readOnly=false}){
  const c=doc.manifest.components[id],shadow=host.attachShadow({mode:'open'}),style=node('style');style.textContent=originalStyle;shadow.append(style);host.dataset.theme=doc.manifest.theme;
  const cfg={meta:{title:c.title},filters:[],kpis:[],charts:[],table:{columns:[],rows:[]},explanations:{...api.explanations}};
  let family=c.kind==='legacy'?(c.family||'chart'):c.kind;
  const key='original-'+id;let raw=c.kind==='legacy'?resolveOriginal(doc,id,c.config.defaultGranularity||'month'):c.config,rows=[];
  if(family==='chart'){
    let chart;
    if(c.kind==='legacy'){
      if(!api.builders[raw.code])throw Error('Unknown original chart code: '+raw.code);
      chart={...api.builders[raw.code],...structuredClone(raw),id:key,instanceId:key,title:c.title};
      chart.data=structuredClone(raw.data);chart.presentation=structuredClone(raw.presentation);
    }else{
      chart={id:key,instanceId:key,code:c.chartType,title:c.title,subtitle:c.subtitle||'',hasGranularity:false,
        data:{},optionBuilder:()=>optionFor(doc,id),tableDataExtractor:()=>{const values=chartTable(doc,id),headers=Object.keys(values[0]||{});return {headers,rows:values.map(row=>headers.map(h=>row[h]))};}};
    }
    const builder=chart.optionBuilder,extractor=chart.tableDataExtractor;let selectedGranularity='month';if(extractor)chart.resolvedTable=()=>extractor(chart.data,c.binding?'month':selectedGranularity,chart);
    chart.optionBuilder=(...args)=>{
      selectedGranularity=args[1]||'month';if(c.binding){chart.data=resolveOriginal(doc,id,selectedGranularity).data;args[0]=chart.data;args[1]='month';}const option=builder(...args);
      function protect(value){if(!value||typeof value!=='object')return;for(const [k,v]of Object.entries(value)){if(k==='tooltip'&&v&&typeof v==='object'&&typeof v.formatter==='function'){const formatter=v.formatter;v.formatter=(...a)=>DOMPurify.sanitize(String(formatter(...a)),{FORBID_TAGS:['img','iframe','script'],FORBID_ATTR:['src','href']});}else if(v&&typeof v==='object')protect(v);}}
      protect(option);return option;
    };
    cfg.charts=[chart];
    if(raw?.explanation)cfg.explanations[chart.explainKey||raw.code]=raw.explanation;
    const container=node('div');container.id='app-charts-grid';shadow.append(container);
  }else if(family==='kpi'){
    if(c.kind!=='legacy'){
      const m=doc.manifest.metrics[c.measures[0]],value=aggregate(visibleRows(doc,id),m);
      raw={...(c.presentation||{}),type:c.presentation?.type||'mc01',label:c.title,value:format(value,m),yoy:c.presentation?.yoy??'—',statusBadge:m.status==='reviewed'?'已复核':'待复核',subLabel:c.presentation?.subLabel||'统计口径',subVal:c.presentation?.subVal||({sum:'合计',ratio:'分子 / 分母',avg:'平均',count:'计数'}[m.aggregation]||m.aggregation)};
      if(raw.type==='mc03'&&c.presentation?.timeField){const groups=new Map();for(const row of visibleRows(doc,id)){const k=row[c.presentation.timeField];if(!groups.has(k))groups.set(k,[]);groups.get(k).push(row);}raw.sparkMonths=[...groups.keys()];raw.sparkData=[...groups.values()].map(r=>{const v=aggregate(r,m);return m.format==='percent'&&v!=null?v*100:v;});}
      cfg.explanations[key]={title:m.label,overview:m.definition,type:raw.type,period:m.period||'当前筛选范围',metrics:[{name:m.label,definition:m.definition,formula:m.aggregation==='ratio'?`SUM(${m.numerator}) / SUM(${m.denominator})`:`${m.aggregation.toUpperCase()}(${m.field||'*'})`,rule:'展示样式不代表指标已认证'}]};
    }
    cfg.kpis=[{...structuredClone(raw),sparkData:raw.sparkData??raw.sparkline,id:key,explainKey:raw.explainKey||key}];
    if(c.kind==='legacy')cfg.explanations[key]=raw.explanation||api.explanations[raw.type]||{title:c.title,overview:'原始指标卡片快照'};
    const container=node('div');container.id='app-kpis';shadow.append(container);
  }else if(family==='table'){
    rows=c.kind==='legacy'?raw.rows:visibleRows(doc,id);
    cfg.table={...(raw||c.presentation||{}),id:key,title:c.title,rows,columns:raw?.columns||c.presentation?.columns||Object.entries(doc.manifest.datasets[c.datasetId].fields).map(([key,meta])=>({key,title:meta.label||key,align:meta.type==='number'?'right':'left'}))};
    const container=node('section','section-card');container.id='app-table-section';shadow.append(container);
  }
  const overlay=node('dialog','explanation-dialog');overlay.id='app-explain-dialog';shadow.append(overlay);
  const feedback=node('div');feedback.id='app-toast-container';shadow.append(feedback);
  const app=new api.DashboardApp(cfg,shadow);const controller=new AbortController();
  for(const event of ['click','change','input','keydown','focus','mouseenter','mouseleave'])shadow.addEventListener(event,e=>{
    const target=e.target.closest?.('[data-original-'+event+']');if(!target)return;
    try{const call=JSON.parse(target.getAttribute('data-original-'+event));if(!methods.has(call.method))return;const args=call.args.map(a=>'literal'in a?a.literal:({'event':e,'this.value':target.value,'this.checked':target.checked,'true':true,'false':false}[a.ref]));app[call.method](...args);}catch(error){app.showToast(error.message);}
  },{signal:controller.signal,capture:event==='focus'||event==='mouseenter'||event==='mouseleave'});
  app.setTableCrossFilter=()=>{};
  app.init();
  if(family==='table'){
    const saved=(c.kind==='legacy'?c.config:c.presentation)?.tableState;
    if(saved){if(Array.isArray(saved.columns))app.state.table.orderedColumns=saved.columns.map(k=>cfg.table.columns.find(col=>col.key===k)).filter(Boolean);
      if(Array.isArray(saved.visible))app.state.table.visibleCols=new Set(saved.visible);
      if(saved.pageSize)app.state.table.pageSize=saved.pageSize;if(saved.page)app.state.table.page=saved.page;
      if(saved.sortCol){app.state.table.sortCol=saved.sortCol;app.state.table.sortDir=saved.sortDir;}
      app.renderColCheckboxes();app.renderTableEngine();}
    let persistTimer;const originalRender=app.renderTableEngine.bind(app);
    app.renderTableEngine=(...args)=>{const result=originalRender(...args);clearTimeout(persistTimer);
      if(onPresentation&&!readOnly)persistTimer=setTimeout(()=>onPresentation(id,{tableState:{columns:app.state.table.orderedColumns.map(x=>x.key),visible:[...app.state.table.visibleCols],page:app.state.table.page,pageSize:app.state.table.pageSize,sortCol:app.state.table.sortCol,sortDir:app.state.table.sortDir}}),350);
      return result;};controller.signal.addEventListener('abort',()=>clearTimeout(persistTimer));
  }
  app.copyCell=text=>navigator.clipboard?.writeText(String(text??'')).then(()=>app.showToast('已复制')).catch(()=>app.showToast('浏览器未授权剪贴板'));
  if(family==='table'){
    app.exportTableToCSV=()=>{const cols=app.state.table.orderedColumns.filter(c=>app.state.table.visibleCols.has(c.key)),result=app.getFilteredTableRows().map(r=>Object.fromEntries(cols.map(col=>[col.title,r[col.key]])));download(c.title+'.csv',csv(result),'text/csv;charset=utf-8');};
    const search=node('input','catalog-search');search.placeholder='搜索明细';search.setAttribute('aria-label','搜索明细');search.oninput=()=>{app.state.keyword=search.value;app.state.table.page=1;app.renderTableEngine();};shadow.querySelector('#app-table-section>div:first-child').prepend(search);
  }
  const actions=shadow.querySelector('.card-header-wrap>div:last-child')||shadow.querySelector('.section-card>div:first-child>div:last-child')||shadow.querySelector('.section-card>div:first-child');
  if(actions){
    actions.append(action('SQL / 语义',null,()=>onInspect(id)));
    if(family==='chart'&&c.kind!=='legacy'){
      const choice=node('select');choice.setAttribute('aria-label','Chart type');choice.disabled=readOnly;
      for(const t of chartTypes){const o=node('option','',names[t]);o.value=t;o.disabled=!!compatible(doc,c,t);choice.append(o);}choice.value=c.chartType;choice.onchange=()=>onType(id,choice.value);const wrap=node('span','catalog-actions');wrap.append(choice);actions.prepend(wrap);
    }
    if(editing)actions.append(action('编辑组件',api.LUCIDE_ICONS.layers,()=>onEdit(id)));
  }
  if(family==='chart'){
    shadow.addEventListener('click',e=>{
      const csvButton=e.target.closest('.export-chart-btn'),copyButton=e.target.closest('.copy-chart-btn');
      if(csvButton){e.stopImmediatePropagation();const chart=app.config.charts[0],gran=app.state.chartGranularities[key],data=chart.tableDataExtractor(chart.data,c.binding?'month':gran,chart);download(c.title+'.csv',csv(data.rows.map(r=>Object.fromEntries(data.headers.map((h,i)=>[h,r[i]])))),'text/csv;charset=utf-8');}
      if(copyButton){e.stopImmediatePropagation();const url=app.state.chartInstances[key].getDataURL({pixelRatio:2,backgroundColor:'#fff'});fetch(url).then(r=>r.blob()).then(async blob=>{try{if(!navigator.clipboard?.write)throw Error();await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);app.showToast('已复制 2x PNG');}catch{const a=document.createElement('a');a.href=url;a.download=c.title+'.png';a.click();app.showToast('剪贴板不可用，已导出 PNG');}}).catch(error=>app.showToast(error.message));}
      const gran=e.target.closest('.granularity-tab-btn');if(gran&&onPresentation&&!readOnly)setTimeout(()=>onPresentation(id,{defaultGranularity:gran.dataset.granularity}),0);
    },{capture:true,signal:controller.signal});
    const saved=c.kind==='legacy'?raw.defaultGranularity:null;if(saved==='quarter'){app.state.chartGranularities[key]='quarter';shadow.querySelectorAll('.granularity-tab-btn').forEach(button=>{const active=button.dataset.granularity==='quarter';button.classList.toggle('bg-white',active);button.classList.toggle('font-semibold',active);button.classList.toggle('shadow-xs',active);button.classList.toggle('text-primary-strong',active);button.classList.toggle('text-ink-muted',!active);});const spec=app.config.charts[0];app.state.chartInstances[key]?.setOption(spec.optionBuilder(spec.data,'quarter',api.TOKENS,spec),true);}
  }
  const fullscreen=node('dialog');fullscreen.className='original-fullscreen';shadow.append(fullscreen);let placeholder=null;
  fullscreen.addEventListener('close',()=>{const card=fullscreen.querySelector('.section-card');if(card&&placeholder){card.classList.remove('card-fullscreen');placeholder.replaceWith(card);placeholder=null;const b=card.querySelector('.fullscreen-btn');if(b)setOriginalHtml(b,api.LUCIDE_ICONS.maximize);Object.values(app.state.chartInstances).forEach(i=>i.resize());}});
  shadow.addEventListener('click',e=>{const b=e.target.closest('.fullscreen-btn');if(!b)return;e.stopImmediatePropagation();if(fullscreen.open)fullscreen.close();else{const card=b.closest('.section-card');placeholder=document.createComment('original-card-position');card.replaceWith(placeholder);fullscreen.append(card);card.classList.add('card-fullscreen');setOriginalHtml(b,api.LUCIDE_ICONS.minimize);fullscreen.showModal();requestAnimationFrame(()=>Object.values(app.state.chartInstances).forEach(i=>i.resize()));}},{capture:true,signal:controller.signal});
  const disposeChrome=installChrome({shadow,app,component:c,family,id,editing,onInspect,onEdit,onBinding});
  return {app,shadow,destroy(){disposeChrome();controller.abort();if(fullscreen.open)fullscreen.close();app.destroy();}};
}
