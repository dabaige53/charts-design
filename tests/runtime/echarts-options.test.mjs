import test from 'node:test';
import assert from 'node:assert/strict';
import * as echarts from '../../runtime-ui/echarts.mjs';
import {applyEChartsOptions} from '../../dashboard_runtime/web/echarts-options.mjs';
import {resolveOriginal} from '../../dashboard_runtime/web/bindings.mjs';
import {createOriginalComponents} from '../../runtime-ui/generated/original-engine.mjs';

Object.defineProperty(globalThis,'window',{value:{},configurable:true});
const api=createOriginalComponents(echarts,()=>{});
Reflect.deleteProperty(globalThis,'window');

test('native overrides preserve preset data/functions and accept extra fields',()=>{
  const formatter=value=>String(value),preset={tooltip:{formatter},series:[{id:'bars',type:'bar',data:[1,2],label:{show:false,color:'#123B5D'}},{id:'line',type:'line',data:[3,4]}],xAxis:{type:'category',data:['A','B']}};
  const override={series:[{id:'line',lineStyle:{width:4}}],xAxis:[{axisLabel:{rotate:30}}],futureComponent:{nested:[1,2]},color:['#123B5D']};
  const result=applyEChartsOptions(preset,override);
  assert.deepEqual(result.series[0],preset.series[0]);
  assert.deepEqual(result.series[1].data,[3,4]);
  assert.equal(result.series[1].lineStyle.width,4);
  assert.equal(result.tooltip.formatter,formatter);
  assert.deepEqual(result.xAxis[0].data,['A','B']);
  assert.equal(result.xAxis[0].axisLabel.rotate,30);
  assert.deepEqual(result.futureComponent,override.futureComponent);
  result.series[0].data.push(9);assert.deepEqual(preset.series[0].data,[1,2]);
  assert.deepEqual(applyEChartsOptions(preset,{series:[]}).series,[]);
  assert.equal(applyEChartsOptions(preset,{series:null}).series,null);
  assert.deepEqual(applyEChartsOptions(preset,{series:{data:[7]}}).series[0].data,[7]);
});

function render(option,check){
  const chart=echarts.init(null,null,{renderer:'svg',ssr:true,width:640,height:420});
  try{chart.setOption({...option,animation:false});check(chart,chart.renderToSVGString());}finally{chart.dispose();}
}

test('column preset renders native colors, labels and axis options',()=>{
  const cfg={...api.builders.c01,data:{categories:['A','B'],values:[12,8]}};
  const preset=cfg.optionBuilder(cfg.data,'month',api.TOKENS,cfg);
  const option=applyEChartsOptions(preset,{color:['#123B5D','#A17B45'],series:[{colorBy:'data',itemStyle:{color:null},label:{show:true,formatter:'{b}: {c}'}}],xAxis:{axisLabel:{rotate:20}},graphic:[{type:'text',left:30,top:20,style:{text:'Native option'}}]});
  render(option,(chart,svg)=>{
    const data=chart.getModel().getSeriesByIndex(0).getData();
    assert.equal(data.getItemVisual(0,'style').fill,'#123B5D');
    assert.equal(data.getItemVisual(1,'style').fill,'#A17B45');
    assert.equal(chart.getOption().xAxis[0].axisLabel.rotate,20);
    assert.ok(svg.includes('A: 12')&&svg.includes('Native option'));
  });
});

test('bubble visualMap category colors stay stable after filtering',()=>{
  const cfg={...api.builders.r02,data:{clusters:[[1,2,10,'Agent A'],[3,4,20,'Agent B']]}};
  const override={series:[{itemStyle:{color:null}}],visualMap:{type:'piecewise',dimension:3,categories:['Agent A','Agent B'],inRange:{color:['#123B5D','#A17B45']}}};
  for(const points of [cfg.data.clusters,cfg.data.clusters.slice(1)]){
    const preset=cfg.optionBuilder({clusters:points},'month',api.TOKENS,cfg);
    render(applyEChartsOptions(preset,override),(chart)=>{
      const data=chart.getModel().getSeriesByIndex(0).getData();
      assert.equal(data.getItemVisual(points.length-1,'style').fill,'#A17B45');
      assert.ok(data.getItemVisual(0,'symbolSize')>0);
    });
  }
});

test('full runtime registers native custom rendering and brush modules',()=>{
  render({xAxis:{},yAxis:{},brush:{toolbox:['rect'],xAxisIndex:0},series:[{type:'custom',data:[[1,2]],renderItem:()=>({type:'rect',shape:{x:30,y:30,width:40,height:20},style:{fill:'#A17B45'}})}]},(chart,svg)=>{
    assert.equal(chart.getModel().getSeriesByIndex(0).subType,'custom');
    assert.ok(chart.getModel().getComponent('brush'));
    assert.ok(svg.includes('#A17B45'));
  });
});

test('bound recomputation retains option overrides without replacing computed values',()=>{
  const doc={manifest:{components:{bar:{kind:'legacy',family:'chart',datasetId:'facts',config:{code:'c01',data:{categories:['old'],values:[999]},echarts:{series:[{label:{show:false}}]}},binding:{datasetId:'facts',categoryField:'region',categoryTarget:'categories',measures:{values:'amount'}}}},metrics:{amount:{aggregation:'sum',field:'amount'}},filters:[{field:'region',op:'in',values:['A'],componentIds:['bar']}]},snapshot:{datasets:{facts:[{region:'A',amount:12},{region:'B',amount:8}]}}};
  const raw=resolveOriginal(doc,'bar'),builder=api.builders.c01;
  const option=applyEChartsOptions(builder.optionBuilder(raw.data,'month',api.TOKENS,builder),raw.echarts);
  assert.deepEqual(option.series[0].data,[12]);assert.equal(option.series[0].label.show,false);
  assert.deepEqual(doc.manifest.components.bar.config.data.values,[999]);
});
