/* High-cardinality filters page options; the selection still addresses all rows. */
export function clearFilterValues(filters){return filters.map(filter=>({...filter,values:[]}));}

export function singleFilter({filter,values,load,onApply,onError,openMenu,closeMenu,icon,disabled=false}){
  const trigger=document.createElement('button'),caption=filter.label||filter.field;
  trigger.type='button';trigger.className='filter-trigger';trigger.disabled=disabled;
  trigger.textContent=caption+'：'+(filter.values.length?String(filter.values[0]):'全部');
  trigger.setAttribute('aria-label',trigger.textContent);trigger.setAttribute('aria-haspopup','menu');
  trigger.append(icon('down'));
  trigger.onclick=async()=>{
    if(load){
      const panel=document.createElement('div'),search=document.createElement('input'),list=document.createElement('div'),more=document.createElement('button');
      search.placeholder='搜索全部选项';search.setAttribute('aria-label',caption+'搜索选项');more.textContent='加载更多';let page,seq=0,timer;
      const choose=value=>{closeMenu();Promise.resolve(onApply(value===undefined?[]:[value])).catch(onError);};
      const item=(label,value)=>{const b=document.createElement('button');b.type='button';b.className='ui-menu-item';b.setAttribute('role','menuitemradio');b.setAttribute('aria-checked',String(value===undefined?!filter.values.length:JSON.stringify(value)===JSON.stringify(filter.values[0])));b.textContent=label;b.onclick=()=>choose(value);return b;};
      async function fetchPage(offset){const request=++seq;more.disabled=true;try{const result=await load(search.value,offset);if(request!==seq)return;page=result;if(!offset)list.replaceChildren(item('全部',undefined));for(const value of result.values)list.append(item(String(value??'—'),value));more.hidden=!result.hasMore;}catch(error){onError(error);}finally{if(request===seq)more.disabled=false;}}
      search.oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>fetchPage(0),150);};more.onclick=()=>fetchPage(page.offset+page.values.length);panel.append(search,list,more);openMenu(trigger,[],{label:caption,content:panel,align:'start'});await fetchPage(0);return;
    }
    const entries=[{label:'全部',value:undefined},...values.map(value=>({label:String(value??'—'),value}))].map(({label,value})=>({
      label,checked:value===undefined?!filter.values.length:JSON.stringify(filter.values[0])===JSON.stringify(value),
      run:()=>Promise.resolve(onApply(value===undefined?[]:[value])).catch(onError),
    }));
    return openMenu(trigger,entries,{label:caption,align:'start'});
  };
  return trigger;
}

export function pagedFilter({filter,firstPage,load,onApply,onError,disabled=false}){
  const node=(tag,cls='',text='')=>{const n=document.createElement(tag);n.className=cls;n.textContent=text;return n;};
  const panel=node('div','filter-panel'),heading=node('div','filter-panel-heading'),count=node('span','filter-count'),search=node('input','catalog-search'),list=node('div','filter-choice-list'),more=node('button','filter-clear','加载更多'),actions=node('div','filter-actions'),apply=node('button','filter-apply','应用'),reset=node('button','filter-clear','全选'),clear=node('button','filter-clear','取消全选');
  search.placeholder='搜索全部选项';search.setAttribute('aria-label',(filter.label||filter.field)+'搜索选项');
  search.hidden=firstPage.totalValues<=12;
  heading.append(node('strong','',filter.label||filter.field),count);actions.append(reset,clear,apply);panel.append(heading,search,list,more,actions);
  const selected=new Map(filter.values.map(value=>[JSON.stringify(value),value]));
  const excluded=new Set(),checks=new Map();
  let all=filter.values.length===0,page=firstPage,values=[],timer,request=0,loading=false;
  const status=()=>{count.textContent=all?`已选全部${excluded.size?'，排除 '+excluded.size+' 项':''}`:`已选 ${selected.size} 项`;apply.disabled=disabled||loading||(!all&&!selected.size)||(all&&firstPage.totalValues>0&&excluded.size>=firstPage.totalValues);reset.disabled=clear.disabled=disabled||loading;more.hidden=!page.hasMore;more.disabled=disabled||loading;};
  const sync=()=>{for(const [key,check]of checks)check.checked=all?!excluded.has(key):selected.has(key);status();};
  function draw(incoming,append=false){page=incoming;if(!append){list.replaceChildren();values=[];checks.clear();}
    for(const value of incoming.values){const key=JSON.stringify(value);if(values.includes(key))continue;values.push(key);const label=node('label','filter-choice'),check=node('input');check.type='checkbox';check.checked=all?!excluded.has(key):selected.has(key);check.disabled=disabled;checks.set(key,check);label.append(check,node('span','',String(value??'—')));check.onchange=()=>{if(all){if(check.checked)excluded.delete(key);else excluded.add(key);}else if(check.checked)selected.set(key,value);else selected.delete(key);status();};list.append(label);}status();}
  async function fetchPage(offset){const seq=++request;loading=true;status();try{const result=await load(search.value,offset);if(seq===request)draw(result,offset>0);}catch(error){onError(error);}finally{if(seq===request){loading=false;status();}}}
  more.type=apply.type=reset.type=clear.type='button';search.disabled=disabled;
  more.onclick=()=>fetchPage(page.offset+page.values.length);
  search.oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>fetchPage(0),200);};
  apply.onclick=async()=>{
    if(apply.disabled)return;
    const useAll=all,omit=new Set(excluded),picked=[...selected.values()];
    loading=true;status();
    try{
      let result=picked;
      if(useAll&&!omit.size)result=[];
      else if(useAll){
        result=[];let offset=0;
        while(true){const batch=await load('',offset);result.push(...batch.values.filter(value=>!omit.has(JSON.stringify(value))));if(!batch.hasMore)break;if(!batch.values.length)throw Error('筛选选项加载不完整，请重试');offset=batch.offset+batch.values.length;}
        if(!result.length)return;
      }
      await onApply(result);
    }catch(error){onError(error);}finally{loading=false;status();}
  };
  reset.onclick=()=>{all=true;selected.clear();excluded.clear();sync();};
  clear.onclick=()=>{all=false;selected.clear();excluded.clear();sync();};
  panel.loadFirst=()=>fetchPage(0);
  draw(firstPage);return panel;
}
