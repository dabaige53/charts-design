import test from 'node:test';
import assert from 'node:assert/strict';
import {singleFilter,clearFilterValues,pagedFilter} from '../../dashboard_runtime/web/local-filter.mjs';

function withDocument(run){
  const previous=Object.getOwnPropertyDescriptor(globalThis,'document');
  const createElement=tag=>({tagName:tag,children:[],attributes:{},value:'',disabled:false,
    append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=[...nodes];},setAttribute(key,value){this.attributes[key]=value;}});
  Object.defineProperty(globalThis,'document',{value:{createElement},configurable:true});
  return Promise.resolve().then(run).finally(()=>{if(previous)Object.defineProperty(globalThis,'document',previous);else Reflect.deleteProperty(globalThis,'document');});
}

test('office dropdown replaces one office at a time and supports all offices',async()=>withDocument(async()=>{
  const changes=[];
  const filter={id:'office',field:'office',label:'国内营业部',values:[]};
  let choices;
  const trigger=singleFilter({filter,values:['西安营业部','江苏（南京）'],openMenu:(_anchor,entries)=>{choices=entries;},icon:()=>({}),onApply:values=>changes.push(values),onError:error=>{throw error;}});
  assert.equal(trigger.tagName,'button');
  assert.equal(trigger.attributes['aria-label'],'国内营业部：全部');
  trigger.onclick();
  await choices[1].run();await choices[2].run();await choices[0].run();
  assert.deepEqual(changes,[['西安营业部'],['江苏（南京）'],[]]);
  assert.deepEqual(filter.values,[]);
}));

test('clear all removes every condition and preserves its definition',()=>{
  const filters=[{id:'office',selectionMode:'single',values:['西安营业部']},{id:'period',values:['2026-09']},{id:'region',values:['欧洲']},{id:'channel',values:['普通代理']},{id:'search',op:'contains',values:['代理']}];
  const result=clearFilterValues(filters);
  assert.ok(result.every(filter=>filter.values.length===0));
  assert.equal(result[0].selectionMode,'single');
  assert.deepEqual(filters[0].values,['西安营业部']);
});

test('exported current-view HTML does not enable incomplete local filtering',async()=>withDocument(()=>{
  const label=singleFilter({filter:{field:'office',values:[]},values:['西安营业部'],disabled:true,icon:()=>({}),onApply:()=>{},onError:()=>{}});
  assert.equal(label.disabled,true);
}));

test('a filter can cancel all draft checks, pick one value, or select all',async()=>withDocument(async()=>{
  const changes=[];
  const panel=pagedFilter({filter:{label:'区域',values:[]},firstPage:{values:['欧洲','日韩'],offset:0,totalValues:2,hasMore:false},load:async()=>{throw Error('No paging needed');},onApply:values=>changes.push(values),onError:error=>{throw error;}});
  const list=panel.children[2],[all,clear,apply]=panel.children[4].children;
  assert.equal(clear.textContent,'取消全选');
  assert.ok(list.children.every(label=>label.children[0].checked));
  clear.onclick();
  assert.ok(list.children.every(label=>!label.children[0].checked));
  assert.equal(apply.disabled,true);
  await apply.onclick();assert.deepEqual(changes,[]);
  const check=list.children[0].children[0];check.checked=true;check.onchange();
  await apply.onclick();assert.deepEqual(changes,[['欧洲']]);
  all.onclick();await apply.onclick();assert.deepEqual(changes,[['欧洲'],[]]);
}));

test('cancel all also clears selected values on unloaded pages',async()=>withDocument(async()=>{
  const changes=[];
  const panel=pagedFilter({filter:{label:'目的地',values:['A','C']},firstPage:{values:['A','B'],offset:0,totalValues:3,hasMore:true},load:async()=>({values:['C'],offset:2,totalValues:3,hasMore:false}),onApply:values=>changes.push(values),onError:error=>{throw error;}});
  panel.children[4].children[1].onclick();
  await panel.children[3].onclick();
  assert.ok(panel.children[2].children.every(label=>!label.children[0].checked));
  const check=panel.children[2].children[2].children[0];check.checked=true;check.onchange();
  await panel.children[4].children[2].onclick();assert.deepEqual(changes,[['C']]);
}));

test('excluding one value from all retains the values on unseen pages',async()=>withDocument(async()=>{
  const changes=[];
  const pages=[{values:['A','B'],offset:0,totalValues:3,hasMore:true},{values:['C'],offset:2,totalValues:3,hasMore:false}];
  const panel=pagedFilter({filter:{label:'目的地',values:[]},firstPage:pages[0],load:async(_search,offset)=>pages[offset===0?0:1],onApply:values=>changes.push(values),onError:error=>{throw error;}});
  const check=panel.children[2].children[0].children[0];check.checked=false;check.onchange();
  await panel.children[4].children[2].onclick();assert.deepEqual(changes,[['B','C']]);
}));
