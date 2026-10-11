/* Named, tree-shaken Lucide SVGs. No text glyphs or icon fonts. */
import {createElement, Pencil, Eye, Plus, Upload, Undo2, Redo2, RefreshCw, Download,
  Database, BookOpen, Settings2, Copy, Trash2, X, Check, Sun, Moon, GripVertical,
  ChartNoAxesCombined, Table2, CalendarDays, Columns3, Search, Maximize2,
  Minimize2, Image, Info, Ellipsis, ChevronLeft, ChevronRight, ListFilter,
  LayoutGrid, FileJson, History, Link2, SlidersHorizontal, ArrowUp, ArrowDown} from 'lucide';
const nodes={edit:Pencil,view:Eye,add:Plus,import:Upload,undo:Undo2,redo:Redo2,
  refresh:RefreshCw,export:Download,sql:Database,semantic:BookOpen,settings:Settings2,
  copy:Copy,remove:Trash2,close:X,save:Check,light:Sun,dark:Moon,drag:GripVertical,
  chart:ChartNoAxesCombined,table:Table2,calendar:CalendarDays,columns:Columns3,
  search:Search,maximize:Maximize2,minimize:Minimize2,image:Image,info:Info,
  more:Ellipsis,prev:ChevronLeft,next:ChevronRight,filter:ListFilter,catalog:LayoutGrid,
  json:FileJson,history:History,link:Link2,sliders:SlidersHorizontal,up:ArrowUp,down:ArrowDown};
export function icon(name){
  const svg=createElement(nodes[name]||nodes.settings);
  const attrs={'width':16,'height':16,'stroke-width':1.65,'aria-hidden':'true','focusable':'false','class':'ui-icon'};
  for(const [key,value]of Object.entries(attrs))svg.setAttribute(key,String(value));
  return svg;
}
function report(error){window.dispatchEvent(new CustomEvent('charts-error',{detail:error}));}
export function decorateButton(button,name,label){
  button.replaceChildren(icon(name));button.type='button';button.classList.add('icon-button');
  button.setAttribute('aria-label',label);button.title=label;button.dataset.tooltip=label;
  button.addEventListener('pointerenter',()=>tooltip(button));button.addEventListener('focus',()=>tooltip(button));
  button.addEventListener('pointerleave',hideTooltip);button.addEventListener('blur',hideTooltip);button.addEventListener('click',hideTooltip);return button;
}
export function iconButton(name,label,run){
  const b=decorateButton(document.createElement('button'),name,label);
  b.addEventListener('click',e=>{e.stopPropagation();Promise.resolve().then(()=>run?.(e)).catch(report);});return b;
}
let tip=null;
function hideTooltip(){tip?.remove();tip=null;}
function tooltip(button){
  if(button.disabled)return;hideTooltip();tip=document.createElement('div');tip.className='ui-tooltip';
  tip.role='tooltip';tip.textContent=button.dataset.tooltip;document.body.append(tip);
  const r=button.getBoundingClientRect();tip.style.top=Math.min(innerHeight-36,r.bottom+7)+'px';
  tip.style.left=Math.max(8,Math.min(innerWidth-tip.offsetWidth-8,r.right-tip.offsetWidth))+'px';
}
let activeMenu=null;
export function closeMenu(){activeMenu?.();}
export function openMenu(anchor,entries,{label='',content=null}={}){
  closeMenu();hideTooltip();const menu=document.createElement('div');menu.className='ui-menu';
  menu.setAttribute('popover','auto');menu.setAttribute('role',content?'dialog':'menu');
  if(label)menu.setAttribute('aria-label',label);
  const controller=new AbortController(),root=anchor.getRootNode();(root instanceof ShadowRoot?root:document.body).append(menu);
  let placeholder=null;if(content?.parentNode){placeholder=document.createComment('menu-content');content.before(placeholder);}
  const cleanup=()=>{controller.abort();if(placeholder?.parentNode)placeholder.replaceWith(content);menu.remove();anchor.setAttribute('aria-expanded','false');if(activeMenu===cleanup)activeMenu=null;};activeMenu=cleanup;anchor.setAttribute('aria-expanded','true');
  if(content)menu.append(content);
  for(const entry of entries||[]){
    const b=document.createElement('button');b.type='button';b.className='ui-menu-item';
    b.setAttribute('role',entry.checked==null?'menuitem':'menuitemradio');b.setAttribute('aria-label',entry.label);
    if(entry.checked!=null)b.setAttribute('aria-checked',String(entry.checked));
    b.append(icon(entry.icon||'settings'));const text=document.createElement('span');text.textContent=entry.label;b.append(text);
    if(entry.checked)b.append(icon('save'));b.disabled=!!entry.disabled;if(entry.reason)b.title=entry.reason;
    b.onclick=e=>{e.stopPropagation();cleanup();anchor.focus();Promise.resolve().then(entry.run).catch(report);};menu.append(b);
  }
  if(menu.showPopover)menu.showPopover();
  const rect=(anchor.hidden&&anchor._menuAnchor?anchor._menuAnchor:anchor).getBoundingClientRect();menu.style.left=Math.max(8,Math.min(innerWidth-menu.offsetWidth-8,rect.right-menu.offsetWidth))+'px';menu.style.top=Math.max(8,Math.min(innerHeight-menu.offsetHeight-8,rect.bottom+6))+'px';
  menu.addEventListener('toggle',e=>{if(e.newState==='closed')cleanup();},{signal:controller.signal});
  menu.addEventListener('keydown',e=>{
    if(e.key==='Escape'){e.preventDefault();cleanup();anchor.focus();return;}
    const items=[...menu.querySelectorAll('button:not(:disabled),input,select')],focused=root.activeElement||document.activeElement,index=items.indexOf(focused);
    if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?items.length-1:(index+(e.key==='ArrowDown'?1:-1)+items.length)%items.length;items[next]?.focus();}
  },{signal:controller.signal});
  document.addEventListener('pointerdown',e=>{if(!e.composedPath().includes(menu)&&!e.composedPath().includes(anchor))cleanup();},{capture:true,signal:controller.signal});
  menu.querySelector('input,button:not(:disabled),select')?.focus();return menu;
}
export function menuButton(name,label,entries){
  const b=iconButton(name,label,()=>openMenu(b,typeof entries==='function'?entries():entries,{label}));
  b.setAttribute('aria-haspopup','menu');b.setAttribute('aria-expanded','false');return b;
}
export function adaptiveActions(header,actions){
  const items=[...actions.children],more=menuButton('more','更多操作',()=>hidden.map(b=>({label:b.getAttribute('aria-label')||b.title,icon:b.dataset.icon||'settings',disabled:b.disabled,run:()=>b.click()})));
  let hidden=[];actions.append(more);
  const resize=()=>{const cap=header.clientWidth<320?2:header.clientWidth<520?4:99;hidden=[];items.forEach((b,i)=>{b._menuAnchor=more;const hide=i>=cap-1&&items.length>cap;b.hidden=hide;if(hide)hidden.push(b);});more.hidden=!hidden.length;};
  const observer=new ResizeObserver(resize);observer.observe(header);resize();return ()=>{observer.disconnect();closeMenu();hideTooltip();};
}
