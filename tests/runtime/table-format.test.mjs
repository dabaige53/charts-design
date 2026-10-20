import test from 'node:test';
import assert from 'node:assert/strict';
import {createOriginalComponents} from '../../runtime-ui/generated/original-engine.mjs';

Object.defineProperty(globalThis,'window',{value:{},configurable:true});
const api=createOriginalComponents({},(element,html)=>{element.innerHTML=html;});
Reflect.deleteProperty(globalThis,'window');
const cell=api.DashboardApp.prototype.formatTableCell;
const percent={format:'percent',scale:'percent',decimals:1};

test('percent points keep one decimal and are never multiplied twice',()=>{
  assert.equal(cell(8.333333333333334,percent),'8.3%');
  assert.equal(cell(5.555555555555555,percent),'5.6%');
  assert.equal(cell(50,percent),'50.0%');
  assert.equal(cell(0,percent),'0.0%');
  assert.equal(cell(0.5,{...percent,scale:'fraction'}),'50.0%');
});

test('missing values, comparisons, money and counts retain their own meaning',()=>{
  for(const value of [null,undefined,''])assert.equal(cell(value,percent),'—');
  assert.equal(cell(5.55,{...percent,signed:true}),'+5.6%');
  assert.equal(cell(-5.55,{...percent,signed:true}),'-5.6%');
  assert.equal(cell(-0.00001,{...percent,signed:true}),'0.0%');
  assert.equal(cell(0.5409,{format:'number',decimals:2}),'0.54');
  assert.equal(cell(1234,{format:'number',decimals:2}),'1,234.00');
  assert.equal(cell(1234,{format:'number',decimals:0}),'1,234');
  assert.equal(cell('2026-09',{}),'2026-09');
});

test('table rendering uses column precision while preserving source values',()=>{
  const row={share:8.333333333333334,revenue:0.5409};
  const nodes=new Map();
  const context={
    getById:id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);},
    state:{table:{orderedColumns:[{key:'share',title:'Share',align:'right',...percent},{key:'revenue',title:'Revenue',align:'right',format:'number',decimals:2}],visibleCols:new Set(['share','revenue']),page:1,pageSize:10}},
    config:{table:{}},getFilteredTableRows:()=>[row],formatTableCell:cell
  };
  api.DashboardApp.prototype.renderTableEngine.call(context);
  assert.match(nodes.get('main14ColTbody').innerHTML,/>8\.3%<\/td>/);
  assert.match(nodes.get('main14ColTbody').innerHTML,/>0\.54<\/td>/);
  assert.equal(row.share,8.333333333333334);
  assert.equal(row.revenue,0.5409);
});
