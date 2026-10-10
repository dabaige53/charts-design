/* Layout/chrome adapter only. Plot builders and KPI bodies remain original. */
import {icon,iconButton,decorateButton,menuButton,openMenu,adaptiveActions} from './icons.mjs';
const text=(tag,cls,value)=>{const n=document.createElement(tag);n.className=cls;n.textContent=value||'';return n;};
export function installChrome({shadow,app,component:c,family,onInspect,onEdit,onBinding,id,editing=false}){
  const card=shadow.querySelector('.section-card');if(!card)return ()=>{};
  const old=card.querySelector('.card-header-wrap')||card.firstElementChild;
  const header=text('div','component-header card-header-wrap'),heading=text('div','component-heading'),titleRow=text('div','component-title-row');
  titleRow.append(text('h3','component-title',c.title));heading.append(titleRow);
  const description=c.subtitle||c.config?.subtitle||c.config?.description||'';
  if(description)heading.append(text('p','component-description',description));
  if(family==='chart'&&c.config?.code)titleRow.append(text('span','component-code',c.config.code.toUpperCase()));
  const statusBadge=family==='kpi'&&c.config?.statusBadge;if(statusBadge)heading.append(text('span','component-status',statusBadge));
  const actions=text('div','component-actions');actions.setAttribute('role','toolbar');actions.setAttribute('aria-label','组件操作');
  const storage=text('div','component-storage');storage.hidden=true;shadow.append(storage);
  const use=(b,name,label)=>{if(!b)return;decorateButton(b,name,label||b.getAttribute('aria-label')||b.title);b.dataset.icon=name;actions.append(b);return b;};
  const menu=(name,label,items)=>{const b=menuButton(name,label,items);b.dataset.icon=name;actions.append(b);return b;};
  if(family==='chart'){
    const tabs=[...old.querySelectorAll('.granularity-tab-btn')];
    if(tabs.length){storage.append(...tabs);menu('calendar','时间粒度',()=>tabs.map(b=>({icon:'calendar',label:b.dataset.granularity==='quarter'?'季度':'月度',checked:app.state.chartGranularities['original-'+id]===b.dataset.granularity,run:()=>b.click()})));}
    const select=old.querySelector('select[aria-label="Chart type"]');
    if(select){storage.append(select);menu('chart','切换图表',()=>[...select.options].map(o=>({icon:'chart',label:o.textContent,disabled:select.disabled||o.disabled,checked:o.value===select.value,run:()=>{select.value=o.value;select.dispatchEvent(new Event('change'));}})));}
    use(old.querySelector('.view-toggle-btn'),'table');
  }
  for(const b of [...old.querySelectorAll('.catalog-source-btn')])if(b.getAttribute('aria-label')==='SQL / 语义')use(b,'sql');
  if(family==='table'){
    const search=shadow.querySelector('.catalog-search');if(search){storage.append(search);menu('search','搜索明细',[]).onclick=e=>{e.stopPropagation();openMenu(e.currentTarget,[],{label:'搜索明细',content:search});};}
    const col=old.querySelector('#colDrawerBtn'),drawer=old.querySelector('#colDrawerMenu');
    if(col&&drawer){col.removeAttribute('data-original-click');use(col,'columns','列设置');drawer.className='column-content';storage.append(drawer);
      col.addEventListener('click',e=>{e.stopPropagation();openMenu(col,[],{label:'列设置',content:drawer});});
      const reset=drawer.querySelector('button');if(reset)decorateButton(reset,'refresh','恢复默认');}
    use(old.querySelector('[data-original-click*="exportTableToCSV"]'),'export','导出表格 CSV');
    const prev=shadow.querySelector('#tablePrevBtn'),next=shadow.querySelector('#tableNextBtn'),pageSize=shadow.querySelector('select[data-original-change]');
    const pagination=shadow.querySelector('#tablePaginationInfo'),indicator=shadow.querySelector('#tablePageIndicator');
    const footer=prev?.parentElement?.parentElement;
    if(pagination){const metadata=text('div','component-metadata');metadata.append(pagination);if(indicator)metadata.append(text('span','',' / '),indicator);heading.append(metadata);}
    if(pageSize){storage.append(pageSize);menu('sliders','每页条数',()=>[...pageSize.options].map(o=>({icon:'table',label:o.textContent,checked:o.value===pageSize.value,run:()=>{pageSize.value=o.value;pageSize.dispatchEvent(new Event('change',{bubbles:true}));}})));}
    use(prev,'prev','上一页');use(next,'next','下一页');footer?.remove();
  }
  if(family==='chart'){
    use(old.querySelector('.copy-chart-btn'),'image');use(old.querySelector('.export-chart-btn'),'export');use(old.querySelector('.fullscreen-btn'),'maximize');
  }
  use(old.querySelector('.chart-explain-btn'),'info');
  for(const b of [...old.querySelectorAll('.catalog-source-btn')])use(b,'edit');
  if(editing&&c.kind==='legacy'&&onBinding)use(iconButton('link','数据绑定',()=>onBinding(id)),'link','数据绑定');
  header.id=old.id;header.append(heading,actions);old.replaceWith(header);
  card.classList.add('component-'+family);card.dataset.chrome='icons-v1';
  const refreshIcons=()=>{
    for(const b of actions.querySelectorAll('button.icon-button'))if(!b.querySelector('svg.ui-icon')){
      const isFull=b.classList.contains('fullscreen-btn')&&shadow.querySelector('.original-fullscreen[open]');
      b.replaceChildren(icon(isFull?'minimize':b.dataset.icon));}
    for(const b of shadow.querySelectorAll('#closeExplainModalBtn'))if(!b.classList.contains('icon-button'))decorateButton(b,'close','关闭');
    for(const th of shadow.querySelectorAll('#main14ColThead th'))for(const span of th.querySelectorAll('span'))if(/^[\s\u2191\u2193\u2195\u21c5\u25b2\u25bc]+$/.test(span.textContent)&&span.textContent.trim()){
      const direction=span.textContent.includes('\u2193')||span.textContent.includes('\u25bc')?'down':'up';span.replaceChildren(icon(direction));}
  };
  const observer=new MutationObserver(refreshIcons);observer.observe(shadow,{childList:true,subtree:true});refreshIcons();
  const dispose=adaptiveActions(header,actions);
  return ()=>{observer.disconnect();dispose();};
}
