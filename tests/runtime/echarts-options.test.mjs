import test from 'node:test';
import assert from 'node:assert/strict';
import {applyEChartsOptions} from '../../dashboard_runtime/web/echarts-options.mjs';
import {resolveOriginal} from '../../dashboard_runtime/web/bindings.mjs';

// @wu-test type=behavior | scope=ECharts option merging | protects=覆盖配置丢失原数据或函数
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

// @wu-test type=integration | scope=binding ECharts options | protects=筛选重算丢失配置覆盖或修改原始快照
test('bound recomputation retains overrides and the original snapshot',()=>{
  const doc={manifest:{components:{bar:{kind:'legacy',family:'chart',datasetId:'facts',config:{code:'c01',data:{categories:['old'],values:[999]},echarts:{series:[{label:{show:false}}]}},binding:{datasetId:'facts',categoryField:'region',categoryTarget:'categories',measures:{values:'amount'}}}},metrics:{amount:{aggregation:'sum',field:'amount'}},filters:[{field:'region',op:'in',values:['A'],componentIds:['bar']}]},snapshot:{datasets:{facts:[{region:'A',amount:12},{region:'B',amount:8}]}}};
  const result=resolveOriginal(doc,'bar');
  assert.deepEqual(result.data,{categories:['A'],values:[12]});
  assert.deepEqual(result.echarts,{series:[{label:{show:false}}]});
  assert.deepEqual(doc.manifest.components.bar.config.data.values,[999]);
});
