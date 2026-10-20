import test from 'node:test';
import assert from 'node:assert/strict';
import * as echarts from '../../runtime-ui/node_modules/echarts/index.js';
import {createOriginalComponents} from '../../runtime-ui/generated/original-engine.mjs';

// The factory registers its app lookup; this test exercises only the pure builder.
Object.defineProperty(globalThis,'window',{value:{},configurable:true});
const api=createOriginalComponents(echarts,()=>{});
Reflect.deleteProperty(globalThis,'window');
const builder=api.builders.c02;

for(const [code,count,visible]of [['c01',100,12],['t01',100,24]]){
  test(`${code} keeps a bounded window without discarding categories`,()=>{
    const labels=Array.from({length:count},(_,i)=>`Period ${i}`),values=Array.from({length:count},(_,i)=>count-i);
    const data=code==='c01'?{categories:labels,values}:{months:labels,rpk:values};
    const component=api.builders[code],option=component.optionBuilder(data,'month',api.TOKENS,component);
    const chart=echarts.init(null,null,{renderer:'svg',ssr:true,width:560,height:380});
    try{
      chart.setOption({...option,animation:false});
      const series=()=>chart.getModel().getSeriesByIndex(0).getData();
      assert.equal(series().count(),visible);
      assert.equal(series().getName(0),`Period ${code==='c01'?0:count-visible}`);
      chart.dispatchAction({type:'dataZoom',dataZoomIndex:1,startValue:0,endValue:visible-1});
      assert.equal(series().getName(0),'Period 0');
      assert.equal(values.length,count);assert.equal(labels.length,count);
    }finally{chart.dispose();}
  });
}

test('large rankings render a readable window and can reach the last category',()=>{
  const data={categories:Array.from({length:1000},(_,i)=>`Channel ${i}`),values:Array.from({length:1000},(_,i)=>1000-i)};
  const before=structuredClone(data);
  const option=builder.optionBuilder(data,'month',api.TOKENS,builder);
  const chart=echarts.init(null,null,{renderer:'svg',ssr:true,width:560,height:380});
  try{
    chart.setOption({...option,animation:false});
    const series=()=>chart.getModel().getSeriesByIndex(0).getData();
    assert.equal(series().count(),12);
    assert.equal(series().getName(0),'Channel 0');
    assert.ok(chart.renderToSVGString().includes('Channel 11'));
    assert.ok(!chart.renderToSVGString().includes('Channel 999'));
    chart.dispatchAction({type:'dataZoom',dataZoomIndex:1,startValue:988,endValue:999});
    assert.equal(series().count(),12);
    assert.equal(series().getName(11),'Channel 999');
    chart.dispatchAction({type:'dataZoom',dataZoomIndex:2,start:25,end:75});
    assert.equal(series().count(),12);
    assert.equal(builder.tableDataExtractor(data,'month',builder).rows.length,1000);
    assert.deepEqual(data,before);
    chart.dispatchAction({type:'restore'});
    assert.equal(series().getName(0),'Channel 0');
    assert.equal(series().count(),12);
  }finally{chart.dispose();}
});

test('small or filtered rankings show all remaining rows without a redundant slider',()=>{
  for(const count of [0,1,12]){
    const data={categories:Array.from({length:count},(_,i)=>`Channel ${i}`),values:Array(count).fill(1)};
    const option=builder.optionBuilder(data,'month',api.TOKENS,builder);
    assert.deepEqual(option.dataZoom,[]);
    assert.equal(option.toolbox.show,false);
    assert.equal(option.series[0].data.length,count);
  }
});
