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
  node.innerHTML=DOMPurify.sanitize(String(markup??''),{ADD_TAGS:['dialog'],FORBID_TAGS:['script','iframe','object','embed','img','form'],ALLOW_DATA_ATTR:true});
}
const node=(tag,cls='',text='')=>{const e=document.createElement(tag);e.className=cls;e.textContent=text;return e;};
function action(label,html,run){const b=node('button','chart-action-btn catalog-source-btn');b.type='button';b.title=label;b.setAttribute('aria-label',label);if(html)setOriginalHtml(b,html);else b.textContent=label;b.addEventListener('click',e=>{e.stopPropagation();Promise.resolve().then(run).catch(error=>window.dispatchEvent(new CustomEvent('charts-error',{detail:error})));});return b;}
function download(name,body,type){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([body],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
const names={bar:'\u67f1\u72b6\u56fe',line:'\u6298\u7ebf\u56fe',area:'\u9762\u79ef\u56fe',pie:'\u73af\u5f62\u56fe',scatter:'\u6563\u70b9\u56fe',heatmap:'\u70ed\u529b\u56fe',funnel:'\u6f0f\u6597\u56fe',waterfall:'\u7011\u5e03\u56fe'};
let api=null;
export function initializeOriginal(echarts){api=createOriginalComponents(echarts,setOriginalHtml);const fallback=api.ChartDataToTableConverter.convert;api.ChartDataToTableConverter.convert=(inst,c)=>c?.resolvedTable?c.resolvedTable():fallback(inst,c);return api;}
export function mountOriginal(host,{doc,id,onInspect,onEdit,onType,onPresentation,editing=false,readOnly=false}){
  const c=doc.manifest.components[id],shadow=host.attachShadow({mode:'open'}),style=node('style');style.textContent=originalStyle;shadow.append(style);host.dataset.theme=doc.manifest.theme;
  const cfg={meta:{title:c.title},filters:[],kpis:[],charts:[],table:{columns:[],rows:[]},explanations:{...api.explanations}};
  let family=c.kind==='legacy'?(c.family||'chart'):c.kind;
  const key='original-'+id;let raw=c.config,rows=[];
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
    const builder=chart.optionBuilder,extractor=chart.tableDataExtractor;let selectedGranularity='month';if(extractor)chart.resolvedTable=()=>extractor(chart.data,selectedGranularity,chart);
    chart.optionBuilder=(...args)=>{
      selectedGranularity=args[1]||'month';const option=builder(...args);
      function protect(value){if(!value||typeof value!=='object')return;for(const [k,v]of Object.entries(value)){if(k==='tooltip'&&v&&typeof v==='object'&&typeof v.formatter==='function'){const formatter=v.formatter;v.formatter=(...a)=>DOMPurify.sanitize(String(formatter(...a)),{FORBID_TAGS:['img','iframe','script'],FORBID_ATTR:['src','href']});}else if(v&&typeof v==='object')protect(v);}}
      protect(option);return option;
    };
    cfg.charts=[chart];
    if(raw?.explanation)cfg.explanations[chart.explainKey||raw.code]=raw.explanation;
    const container=node('div');container.id='app-charts-grid';shadow.append(container);
  }else if(family==='kpi'){
    if(c.kind!=='legacy'){
      const m=doc.manifest.metrics[c.measures[0]],value=aggregate(visibleRows(doc,id),m);
      raw={...(c.presentation||{}),type:c.presentation?.type||'mc01',label:c.title,value:format(value,m),yoy:c.presentation?.yoy??'\u2014',statusBadge:m.status==='reviewed'?'\u5df2\u590d\u6838':'\u5f85\u590d\u6838',subLabel:c.presentation?.subLabel||'\u7edf\u8ba1\u53e3\u5f84',subVal:c.presentation?.subVal||({sum:'\u5408\u8ba1',ratio:'\u5206\u5b50 / \u5206\u6bcd',avg:'\u5e73\u5747',count:'\u8ba1\u6570'}[m.aggregation]||m.aggregation)};
      if(raw.type==='mc03'&&c.presentation?.timeField){const groups=new Map();for(const row of visibleRows(doc,id)){const k=row[c.presentation.timeField];if(!groups.has(k))groups.set(k,[]);groups.get(k).push(row);}raw.sparkMonths=[...groups.keys()];raw.sparkData=[...groups.values()].map(r=>{const v=aggregate(r,m);return m.format==='percent'&&v!=null?v*100:v;});}
      cfg.explanations[key]={title:m.label,overview:m.definition,type:raw.type,period:m.period||'\u5f53\u524d\u7b5b\u9009\u8303\u56f4',metrics:[{name:m.label,definition:m.definition,formula:m.aggregation==='ratio'?`SUM(${m.numerator}) / SUM(${m.denominator})`:`${m.aggregation.toUpperCase()}(${m.field||'*'})`,rule:'\u5c55\u793a\u6837\u5f0f\u4e0d\u4ee3\u8868\u6307\u6807\u5df2\u8ba4\u8bc1'}]};
    }
    cfg.kpis=[{...structuredClone(raw),sparkData:raw.sparkData??raw.sparkline,id:key,explainKey:raw.explainKey||key}];
    if(c.kind==='legacy')cfg.explanations[key]=raw.explanation||api.explanations[raw.type]||{title:c.title,overview:'\u539f\u59cb\u6307\u6807\u5361\u7247\u5feb\u7167'};
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
  if(family==='table'&&c.presentation?.visibleColumns){app.state.table.visibleCols=new Set(c.presentation.visibleColumns);app.renderColCheckboxes();app.renderTableEngine();}
  app.copyCell=text=>navigator.clipboard?.writeText(String(text??'')).then(()=>app.showToast('\u5df2\u590d\u5236')).catch(()=>app.showToast('\u6d4f\u89c8\u5668\u672a\u6388\u6743\u526a\u8d34\u677f'));
  if(family==='table'){
    app.exportTableToCSV=()=>{const cols=app.state.table.orderedColumns.filter(c=>app.state.table.visibleCols.has(c.key)),result=app.getFilteredTableRows().map(r=>Object.fromEntries(cols.map(col=>[col.title,r[col.key]])));download(c.title+'.csv',csv(result),'text/csv;charset=utf-8');};
    const search=node('input','catalog-search');search.placeholder='\u641c\u7d22\u660e\u7ec6';search.setAttribute('aria-label','\u641c\u7d22\u660e\u7ec6');search.oninput=()=>{app.state.keyword=search.value;app.state.table.page=1;app.renderTableEngine();};shadow.querySelector('#app-table-section>div:first-child').prepend(search);
  }
  const actions=shadow.querySelector('.card-header-wrap>div:last-child')||shadow.querySelector('.section-card>div:first-child>div:last-child')||shadow.querySelector('.section-card>div:first-child');
  if(actions){
    actions.append(action('SQL / \u8bed\u4e49',null,()=>onInspect(id)));
    if(family==='chart'&&c.kind!=='legacy'){
      const choice=node('select');choice.setAttribute('aria-label','Chart type');choice.disabled=readOnly;
      for(const t of chartTypes){const o=node('option','',names[t]);o.value=t;o.disabled=!!compatible(doc,c,t);choice.append(o);}choice.value=c.chartType;choice.onchange=()=>onType(id,choice.value);const wrap=node('span','catalog-actions');wrap.append(choice);actions.prepend(wrap);
    }
    if(editing)actions.append(action('\u7f16\u8f91\u7ec4\u4ef6',api.LUCIDE_ICONS.layers,()=>onEdit(id)));
  }
  if(family==='chart'){
    shadow.addEventListener('click',e=>{
      const csvButton=e.target.closest('.export-chart-btn'),copyButton=e.target.closest('.copy-chart-btn');
      if(csvButton){e.stopImmediatePropagation();const chart=app.config.charts[0],gran=app.state.chartGranularities[key],data=chart.tableDataExtractor(chart.data,gran,chart);download(c.title+'.csv',csv(data.rows.map(r=>Object.fromEntries(data.headers.map((h,i)=>[h,r[i]])))),'text/csv;charset=utf-8');}
      if(copyButton){e.stopImmediatePropagation();const url=app.state.chartInstances[key].getDataURL({pixelRatio:2,backgroundColor:'#fff'});fetch(url).then(r=>r.blob()).then(async blob=>{try{if(!navigator.clipboard?.write)throw Error();await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);app.showToast('\u5df2\u590d\u5236 2x PNG');}catch{const a=document.createElement('a');a.href=url;a.download=c.title+'.png';a.click();app.showToast('\u526a\u8d34\u677f\u4e0d\u53ef\u7528\uff0c\u5df2\u5bfc\u51fa PNG');}}).catch(error=>app.showToast(error.message));}
      const gran=e.target.closest('.granularity-tab-btn');if(gran&&onPresentation&&!readOnly)setTimeout(()=>onPresentation(id,{defaultGranularity:gran.dataset.granularity}),0);
    },{capture:true,signal:controller.signal});
    const saved=c.kind==='legacy'?raw.defaultGranularity:null;if(saved==='quarter'){app.state.chartGranularities[key]='quarter';shadow.querySelectorAll('.granularity-tab-btn').forEach(button=>{const active=button.dataset.granularity==='quarter';button.classList.toggle('bg-white',active);button.classList.toggle('font-semibold',active);button.classList.toggle('shadow-xs',active);button.classList.toggle('text-primary-strong',active);button.classList.toggle('text-ink-muted',!active);});const spec=app.config.charts[0];app.state.chartInstances[key]?.setOption(spec.optionBuilder(spec.data,'quarter',api.TOKENS,spec),true);}
  }
  const fullscreen=node('dialog');fullscreen.className='original-fullscreen';shadow.append(fullscreen);let placeholder=null;
  fullscreen.addEventListener('close',()=>{const card=fullscreen.querySelector('.section-card');if(card&&placeholder){card.classList.remove('card-fullscreen');placeholder.replaceWith(card);placeholder=null;const b=card.querySelector('.fullscreen-btn');if(b)setOriginalHtml(b,api.LUCIDE_ICONS.maximize);Object.values(app.state.chartInstances).forEach(i=>i.resize());}});
  shadow.addEventListener('click',e=>{const b=e.target.closest('.fullscreen-btn');if(!b)return;e.stopImmediatePropagation();if(fullscreen.open)fullscreen.close();else{const card=b.closest('.section-card');placeholder=document.createComment('original-card-position');card.replaceWith(placeholder);fullscreen.append(card);card.classList.add('card-fullscreen');setOriginalHtml(b,api.LUCIDE_ICONS.minimize);fullscreen.showModal();requestAnimationFrame(()=>Object.values(app.state.chartInstances).forEach(i=>i.resize()));}},{capture:true,signal:controller.signal});
  return {app,shadow,destroy(){controller.abort();if(fullscreen.open)fullscreen.close();app.destroy();}};
}
