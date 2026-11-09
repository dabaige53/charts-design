import test from 'node:test';
import assert from 'node:assert/strict';
import {encodingRecords,encodingOption} from '../../dashboard_runtime/web/encoding.mjs';
const metric=(field)=>({field,aggregation:'sum',label:field});
function fixture(){return {manifest:{filters:[],metrics:{market:metric('market'),ho:metric('ho'),share:{aggregation:'ratio',numerator:'ho',denominator:'market'}},components:{plot:{config:{code:'r02',encoding:{symbolSize:18,colorBy:'grade',tooltip:['x','y','share','grade']}},datasetId:'d',binding:{categoryField:'od',measures:{x:'market',y:'ho',share:'share'},attributes:{grade:{field:'grade',aggregation:'unique'}}}}}},snapshot:{datasets:{d:[{od:'A',market:100,ho:10,grade:'好'},{od:'A',market:900,ho:180,grade:'好'},{od:'B',market:0,ho:0,grade:null}]}}};}
// @wu-test type=behavior | scope=scatter encoding | protects=比例缺失值或空筛选结果错误
test('scatter ratio, fixed size, null and filtering',()=>{const d=fixture();let records=encodingRecords(d,'plot');assert.equal(records[0].values.share,.19);assert.equal(records[1].values.share,null);let o=encodingOption(d,'plot',records);assert.ok(o.series.every(s=>s.symbolSize===18));assert.ok(o.tooltip.formatter({data:o.series[0].data[0]}).includes('0.19'));d.manifest.filters=[{field:'od',op:'in',values:['absent'],componentIds:['plot']}];assert.equal(encodingRecords(d,'plot').length,0);assert.equal(encodingOption(d,'plot',[]).series.length,0);});
// @wu-test type=behavior | scope=stacked encoding | protects=分类排序堆叠或缺失组合错误
test('dynamic horizontal stack and missing pairs',()=>{const d=fixture(),c=d.manifest.components.plot;c.config={code:'c03',encoding:{orientation:'horizontal',stacked:true,colors:{HO:'#A4453C'}}};c.binding={categoryField:'od',seriesField:'carrier',measures:{value:'market'},orderBy:{target:'value',direction:'desc'}};d.snapshot.datasets.d=[{od:'A long label',carrier:'HO',market:100},{od:'A long label',carrier:'MU',market:50},{od:'B',carrier:'CA',market:200}];const o=encodingOption(d,'plot',encodingRecords(d,'plot'));assert.equal(o.series.length,3);assert.equal(o.yAxis.data[0],'B');assert.ok(o.series.every(s=>s.stack==='total'));assert.equal(o.series[0].itemStyle.color,'#A4453C');assert.equal(o.series[0].data[0].value,null);assert.equal(o.series[0].data[1].value,100);});
// @wu-test type=behavior | scope=dynamic grouping | protects=更换维度或筛选后系列错误
test('retail region × product supports changing group dimension and filtered series',()=>{const d=fixture(),c=d.manifest.components.plot;c.config={code:'c03',encoding:{orientation:'vertical',stacked:false}};c.binding={categoryField:'region',seriesField:'product',measures:{value:'market'}};d.snapshot.datasets.d=[{region:'North',product:'Coffee',agent:'Store A',market:0},{region:'South',product:'Tea',agent:'Store B',market:24},{region:null,product:'Cocoa',agent:'Store B',market:12}];let o=encodingOption(d,'plot',encodingRecords(d,'plot'));assert.equal(o.series.length,3);assert.deepEqual(o.xAxis.data,['North','South','缺失']);c.binding.categoryField='agent';d.manifest.filters=[{field:'agent',op:'in',values:['Store B'],componentIds:['plot']}];o=encodingOption(d,'plot',encodingRecords(d,'plot'));assert.equal(o.series.length,2);assert.deepEqual(o.xAxis.data,['Store B']);assert.equal(o.series[0].data[0].value,24);});
// @wu-test type=behavior | scope=scatter attributes | protects=冲突属性被误展示或尺寸编码失效 | debt=D7
test('attribute conflicts return null and size encoding is opt-in',()=>{const d=fixture();d.snapshot.datasets.d[1].grade='different';const rs=encodingRecords(d,'plot');assert.equal(rs[0].values.grade,null);d.manifest.components.plot.config.encoding.sizeBy='x';assert.equal(typeof encodingOption(d,'plot',rs).series[0].symbolSize,'function');});

// @wu-test type=behavior | scope=top-series encoding | protects=其他系列合并后总量或顺序错误
test('top-series remainder keeps total bar lengths and descending category order',()=>{
  const d=fixture(),c=d.manifest.components.plot;
  c.config={code:'c03',encoding:{orientation:'horizontal',stacked:true,topSeries:2,pinnedSeries:['HO'],otherSeriesLabel:'其他航司'}};
  c.binding={categoryField:'od',seriesField:'carrier',measures:{value:'market'},orderBy:{target:'value',direction:'desc'}};
  d.snapshot.datasets.d=[{od:'A',carrier:'HO',market:10},{od:'A',carrier:'MU',market:100},{od:'B',carrier:'CA',market:120},{od:'B',carrier:'MU',market:10}];
  const o=encodingOption(d,'plot',encodingRecords(d,'plot'));
  assert.deepEqual(o.yAxis.data,['B','A']);
  assert.deepEqual(o.series.map(s=>s.name),['HO','CA','其他航司']);
  assert.deepEqual(o.yAxis.data.map((_,i)=>o.series.reduce((sum,s)=>sum+(s.data[i].value??0),0)),[130,110]);
  assert.ok(o.tooltip.formatter(o.series.map(s=>({data:s.data[0]}))).includes('130'));
  d.manifest.filters=[{field:'carrier',op:'in',values:['MU'],componentIds:['plot']}];
  const filtered=encodingOption(d,'plot',encodingRecords(d,'plot'));
  assert.deepEqual(filtered.yAxis.data,['A','B']);
  assert.deepEqual(filtered.series[0].data.map(x=>x.value),[100,10]);
});

// @wu-test type=behavior | scope=per-category ranking | protects=不同类别共用错误的前五系列
test('each category selects its own top five and merges the remainder',()=>{
 const d=fixture(),c=d.manifest.components.plot;
 c.config={code:'c03',encoding:{orientation:'horizontal',stacked:true,topSeries:5,seriesRanking:'category',pinnedSeries:[],otherSeriesLabel:'其他航司'}};
 c.binding={categoryField:'od',seriesField:'carrier',measures:{value:'market'},orderBy:{target:'value',direction:'desc'}};
 d.snapshot.datasets.d=['A','B'].flatMap((od,i)=>['HO','MU','CA','CZ','AY','A3','SN'].map((carrier,j)=>({od,carrier,market:i?j+1:7-j})));
 const o=encodingOption(d,'plot',encodingRecords(d,'plot'));
 assert.deepEqual(o.yAxis.data,['A','B']);
 const nonOther=i=>o.series.filter(s=>s.name!=='其他航司'&&s.data[i].value!=null).map(s=>s.name).sort();
 assert.deepEqual(nonOther(0),['AY','CA','CZ','HO','MU']);
 assert.deepEqual(nonOther(1),['A3','AY','CA','CZ','SN']);
 assert.deepEqual(o.series.find(s=>s.name==='其他航司').data.map(x=>x.value),[3,3]);
 assert.deepEqual([0,1].map(i=>o.series.reduce((sum,s)=>sum+(s.data[i].value??0),0)),[28,28]);
});

// @wu-test type=behavior | scope=ratio tooltip | protects=比例或均值被相加并显示虚假份额
test('non-additive bars show values without totals or shares',()=>{
 const d=fixture(),c=d.manifest.components.plot;c.config={code:'c03',encoding:{orientation:'horizontal'}};c.binding={categoryField:'od',seriesField:'carrier',measures:{value:'share'}};
 d.snapshot.datasets.d=[{od:'A',carrier:'HO',ho:1,market:2},{od:'A',carrier:'MU',ho:2,market:8}];
 const o=encodingOption(d,'plot',encodingRecords(d,'plot')),text=o.tooltip.formatter(o.series.map(s=>({data:s.data[0]})));
 assert.ok(!text.includes('合计'));assert.ok(!text.includes('占当前范围'));assert.ok(!text.includes('（'));assert.equal(o.series[0].barWidth,undefined);
});
// @wu-test type=behavior | scope=matrix encoding | protects=矩阵变为条形或缺失组合伪造零比例
test('matrix retains four columns and distinguishes zero from no record',()=>{
 const d=fixture(),c=d.manifest.components.plot;c.config={code:'r03',encoding:{seriesOrder:['D-D','D-I','I-D','I-I']}};c.binding={categoryField:'od',seriesField:'carrier',measures:{value:'share',numerator:'ho',denominator:'market'}};
 d.snapshot.datasets.d=[{od:'A',carrier:'D-D',ho:0,market:10}];const o=encodingOption(d,'plot',encodingRecords(d,'plot'));
 assert.equal(o.series[0].type,'heatmap');assert.equal(o.xAxis.data.length,4);assert.match(o.series[0].data[0].label.formatter,/0/);assert.match(o.series[0].data[1].label.formatter,/无记录/);assert.notEqual(o.series[0].data[0].itemStyle.color,o.series[0].data[1].itemStyle.color);
});
// @wu-test type=behavior | scope=ordered flow encoding | protects=流程阶段顺序被数量排序或无记录变成零达标
test('flow preserves every ordered stage and arrow without inventing conversion counts',()=>{
 const d=fixture(),c=d.manifest.components.plot;c.config={code:'f02',encoding:{categoryOrder:['识别','始发准备','航中联动']}};c.binding={categoryField:'od',seriesField:'carrier',measures:{value:'ho',denominator:'market'}};
 d.snapshot.datasets.d=[{od:'始发准备',carrier:'排座达标率',ho:2,market:8},{od:'识别',carrier:'识别覆盖率',ho:1,market:10}];const o=encodingOption(d,'plot',encodingRecords(d,'plot'));
 assert.equal(o.series[0].type,'graph');assert.deepEqual(o.series[0].data.map(n=>n.name),['识别','始发准备','航中联动']);assert.equal(o.series[0].links.length,2);assert.ok(o.series[0].data[2].label.formatter.endsWith('—'));assert.ok(o.series[0].links.every(l=>!('value'in l)));
});
// @wu-test type=behavior | scope=ring encoding | protects=风险分层在原生预览中退化为条形图
test('ring uses current filtered categories and values',()=>{
 const d=fixture(),c=d.manifest.components.plot;c.config={code:'k01',encoding:{}};c.binding={categoryField:'od',measures:{value:'market'}};
 const o=encodingOption(d,'plot',encodingRecords(d,'plot'));assert.equal(o.series[0].type,'pie');assert.equal(o.series[0].data[0].value,1000);
});
