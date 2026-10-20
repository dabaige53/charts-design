/* Layout/chrome adapter only. Plot builders and KPI bodies remain original. */
import {inlineEdit} from './inline-edit.mjs';
import {icon,iconButton,decorateButton,menuButton,openMenu,closeMenu} from './icons.mjs';
const text=(tag,cls,value)=>{const n=document.createElement(tag);n.className=cls;n.textContent=value||'';return n;};
export function installChrome({shadow,app,component:c,family,onInspect,onEdit,onBinding,onAnnotate,onText,id,editing=false}){
  const card=shadow.querySelector('.section-card');if(!card)return ()=>{};
  const old=card.querySelector('.card-header-wrap')||card.firstElementChild;
  const header=text('div','component-header card-header-wrap'),heading=text('div','component-heading'),titleRow=text('div','component-title-row');
  const title=text('h3','component-title',c.title);titleRow.append(title);heading.append(titleRow);if(editing&&onText)inlineEdit(title,{label:'图表标题',value:c.title,maxLength:240,save:value=>onText(id,{title:value})});
  const description=c.subtitle||c.config?.subtitle||c.config?.description||'';
  if(description||editing){const subtitle=text('p','component-description component-subtitle',description);heading.append(subtitle);if(editing&&onText)inlineEdit(subtitle,{label:'图表描述',value:description,save:value=>onText(id,{subtitle:value})});}
  const statusBadge=family==='kpi'&&app.config.kpis?.[0]?.statusBadge;if(statusBadge&&app.config.kpis?.[0]?.type==='mc01')titleRow.append(text('span','component-status',statusBadge));
  const actions=text('div','component-actions');actions.setAttribute('role','toolbar');actions.setAttribute('aria-label','组件操作');
  const storage=text('div','component-storage');storage.hidden=true;heading.append(storage);
  const use=(b,name,label)=>{if(!b)return;decorateButton(b,name,label||b.getAttribute('aria-label')||b.title);b.dataset.icon=name;actions.append(b);return b;};
  const menu=(name,label,items)=>{const b=menuButton(name,label,items);b.dataset.icon=name;actions.append(b);return b;};
  if(family==='chart'){
    const tabs=[...old.querySelectorAll('.granularity-tab-btn')];
    if(tabs.length){const controls=text('div','component-granularity');for(const b of tabs){b.setAttribute('aria-label',b.dataset.granularity==='quarter'?'季度':'月度');controls.append(b);}actions.append(controls);}
    const select=old.querySelector('select[aria-label="Chart type"]');
    if(select){storage.append(select);if(editing)menu('chart','切换图表类型',()=>[...select.options].map(o=>({icon:'chart',label:o.textContent,disabled:select.disabled||o.disabled,checked:o.value===select.value,run:()=>{if(o.value===select.value)return;select.value=o.value;select.dispatchEvent(new Event('change'));}})));}
    use(old.querySelector('.view-toggle-btn'),'table');
  }
  if(family==='table'){
    const notice=old.querySelector('.component-snapshot-notice');if(notice)heading.append(notice);
    const search=shadow.querySelector('.catalog-search');if(search){search.title='仅搜索本表明细；全页搜索请使用页面筛选栏';heading.append(search);}
    const col=old.querySelector('#colDrawerBtn'),drawer=old.querySelector('#colDrawerMenu');
    if(col&&drawer){col.removeAttribute('data-original-click');col.textContent='自定义列配置';col.setAttribute('aria-label','列配置');col.className='component-text-button';actions.append(col);drawer.className='column-content';storage.append(drawer);
      col.onclick=e=>{e.stopPropagation();drawer.classList.remove('hidden');const popup=openMenu(col,[],{label:'列设置',content:drawer});popup.id='colDrawerWrap';};
      const reset=drawer.querySelector('button');if(reset)decorateButton(reset,'refresh','恢复默认');}
    const exportButton=old.querySelector('[data-original-click*="exportTableToCSV"]');if(exportButton){exportButton.textContent='导出 Excel (CSV)';exportButton.setAttribute('aria-label','导出表格 CSV');exportButton.className='component-text-button';actions.append(exportButton);}
    const pageSize=shadow.querySelector('select[data-original-change]');if(pageSize){pageSize.setAttribute('aria-label','每页条数');pageSize.value=app.state.table.pageSize===9999?'all':String(app.state.table.pageSize);}
    const footer=shadow.querySelector('#tablePrevBtn')?.parentElement?.parentElement;if(footer)footer.classList.add('component-pagination');
  }
  if(family==='chart'){
    for(const [selector,label,name] of [['.export-chart-btn','导出数据','export'],['.copy-chart-btn','复制图片','copy'],['.fullscreen-btn','全屏查看','maximize']])use(old.querySelector(selector),name,label);
  }
  const details=iconButton('info','指标定义与语义',()=>onInspect?.(id));details.classList.add('chart-explain-btn');actions.append(details);
  if(editing&&onAnnotate)use(iconButton('comment','图表批注',()=>onAnnotate(id)),'comment','图表批注');
  header.id=old.id;header.append(heading,actions);old.replaceWith(header);
  card.classList.add('component-'+family);card.dataset.chrome='icons-v1';
  if(family==='table'){const table=card.querySelector('#main14ColTable'),body=[...card.children].find(child=>child!==header&&child.contains(table));body?.classList.add('component-table-body');}
  if(!card.classList.contains('kpi-aligned')&&family==='kpi'&&['mc01','mc02','mc03','mc04'].includes(app.config.kpis?.[0]?.type)){
    const sections=[...card.children].filter(n=>n!==header),value=sections.shift(),footer=sections.pop(),aux=text('div','kpi-aux');aux.append(...sections);if(value)value.classList.add('kpi-headline');if(footer)footer.classList.add('kpi-footer');card.replaceChildren(header,...(value?[value]:[]),aux,...(footer?[footer]:[]));card.classList.add('kpi-aligned');
  }

  const refreshIcons=()=>{
    for(const b of actions.querySelectorAll('button.icon-button'))if(!b.querySelector('svg.ui-icon')){
      const isFull=b.classList.contains('fullscreen-btn')&&shadow.querySelector('.original-fullscreen[open]');
      b.replaceChildren(icon(isFull?'minimize':b.dataset.icon));if(b.classList.contains('fullscreen-btn')){const label=isFull?'退出全屏':'全屏查看';b.setAttribute('aria-label',label);b.title=label;b.dataset.tooltip=label;}}
    for(const b of shadow.querySelectorAll('#closeExplainModalBtn'))if(!b.classList.contains('icon-button'))decorateButton(b,'close','关闭');
    for(const th of shadow.querySelectorAll('#main14ColThead th'))for(const span of th.querySelectorAll('span'))if(/^[\s\u2191\u2193\u2195\u21c5\u25b2\u25bc]+$/.test(span.textContent)&&span.textContent.trim()){
      const direction=span.textContent.includes('\u2193')||span.textContent.includes('\u25bc')?'down':'up';span.replaceChildren(icon(direction));}
  };
  const observer=new MutationObserver(refreshIcons);observer.observe(shadow,{childList:true,subtree:true});refreshIcons();
  return ()=>{observer.disconnect();closeMenu();};
}
