import test from 'node:test';
import assert from 'node:assert/strict';
import {adaptOption,widthBucket,textWidth} from '../../dashboard_runtime/web/adaptive.mjs';

const bars=(extra={})=>({grid:{left:48,right:24,top:40,bottom:40,containLabel:true},
  xAxis:{type:'category',name:'基地名称',data:['华东','华南']},yAxis:{type:'value',name:'收入'},
  series:[{type:'bar',data:[1,2],label:{show:true}}],...extra});

test('legacy containLabel grids make room for an end-placed x-axis name',()=>{
  const option=adaptOption(bars(),420);
  assert.ok(option.grid.right>=Math.ceil(textWidth('基地名称')+15+6));
  const untouched=bars();untouched.grid.containLabel=false;
  assert.equal(adaptOption(untouched,420).grid.right,24);
  const middle=bars();middle.xAxis.nameLocation='middle';
  assert.equal(adaptOption(middle,420).grid.right,24);
});

test('crowded category labels truncate, and rotate only when slots are tiny',()=>{
  const long=Array.from({length:6},(_,i)=>'华东大区基地运营中心'+i);
  const wide=adaptOption(bars({xAxis:{type:'category',data:long.slice(0,3)}}),420).xAxis.axisLabel;
  assert.equal(wide.overflow,'truncate');assert.ok(wide.width>=38);assert.equal(wide.rotate,undefined);
  const tiny=adaptOption(bars({xAxis:{type:'category',data:long}}),300).xAxis.axisLabel;
  assert.equal(tiny.rotate,30);assert.equal(tiny.hideOverlap,true);
  const roomy=adaptOption(bars({xAxis:{type:'category',data:['A','B']}}),900).xAxis.axisLabel;
  assert.equal(roomy,undefined);
  const zoomed=adaptOption(bars({xAxis:{type:'category',data:long},dataZoom:[{type:'slider'}]}),300).xAxis.axisLabel;
  assert.equal(zoomed,undefined);
});

test('legends scroll when they cannot fit, and narrow value labels avoid overlap',()=>{
  const names=['预算收入','实际收入','上年同期','行业基准','滚动预测'];
  const option=adaptOption({legend:{data:names},series:names.map(name=>({type:'bar',name,data:[1],label:{show:true}}))},360);
  assert.equal(option.legend.type,'scroll');
  assert.deepEqual(option.series[0].labelLayout,{hideOverlap:true});
  const roomy=adaptOption({legend:{},series:[{type:'bar',name:'收入',data:[1]}]},900);
  assert.equal(roomy.legend.type,undefined);
});

test('width buckets and degenerate input',()=>{
  assert.deepEqual([399,400,559,560,759,760].map(widthBucket),['xs','sm','sm','md','md','lg']);
  assert.equal(adaptOption(null,500),null);
  const option=bars();assert.equal(adaptOption(option,0),option);
});
