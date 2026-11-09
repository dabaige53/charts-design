import test from 'node:test';
import assert from 'node:assert/strict';
import {pickAnnotationPoint,resolveAnnotationPoint,annotationFilterKey} from '../../dashboard_runtime/web/annotation-points.mjs';
function mock(option) {
 return {getOption:()=>option,getWidth:()=>400,getHeight:()=>300,getDom:()=>({getBoundingClientRect:()=>({left:100,top:200,width:400,height:300})}),convertToPixel:(_,value)=>[Number(value[0])*50+30,280-Number(value[1])*10],containPixel:()=>true};
}
const options=()=>({xAxis:[{type:'category',data:['Jan','Feb','Mar']}],yAxis:[{type:'value'}],series:[{name:'Revenue',type:'line',data:[10,12,15]}]});
// @wu-test type=behavior | scope=annotation-points.test | protects=category anchor survives reordering, without storing dataIndex
test('category anchor survives reordering, without storing dataIndex',()=>{
 const option=options(),chart=mock(option),point=pickAnnotationPoint(chart,180,360);
 assert.equal(point.key.value,'Feb');assert.equal(JSON.stringify(point).includes('dataIndex'),false);
 option.xAxis[0].data=['Feb','Jan','Mar'];option.series[0].data=[12,10,15];assert.equal(resolveAnnotationPoint(chart,point).left,130);
});
// @wu-test type=behavior | scope=annotation-points.test | protects=numeric scatter requires a stable item identity
test('numeric scatter requires a stable item identity',()=>{
 const o={xAxis:{type:'value'},yAxis:{type:'value'},series:[{id:'stable',type:'scatter',data:[{id:'p1',value:[2,10]}]}]},c=mock(o),p=pickAnnotationPoint(c,230,380);
 assert.equal(p.key.value,'p1');o.series[0].data[0].value=[3,9];assert.equal(resolveAnnotationPoint(c,p).left,280);
 o.series[0].data=[[2,10]];assert.equal(resolveAnnotationPoint(c,p),null);assert.equal(pickAnnotationPoint(c,230,380),null);
});
// @wu-test type=behavior | scope=annotation-points.test | protects=duplicate category, name or series identity falls back safely
test('duplicate category, name or series identity falls back safely',()=>{
 const o=options();o.xAxis[0].data=['Jan','Jan','Mar'];assert.equal(pickAnnotationPoint(mock(o),130,380),null);
 o.series.push({...o.series[0]});assert.equal(pickAnnotationPoint(mock(o),230,330),null);
});
// @wu-test type=behavior | scope=annotation-points.test | protects=point no longer visible or deleted resolves to no position
test('point no longer visible or deleted resolves to no position',()=>{
 const o=options(),c=mock(o),p=pickAnnotationPoint(c,180,360);o.xAxis[0].data=['Jan','Mar'];assert.equal(resolveAnnotationPoint(c,p),null);
 o.xAxis[0].data=['Jan','Feb','Mar'];c.containPixel=()=>false;assert.equal(resolveAnnotationPoint(c,p),null);
});
// @wu-test type=behavior | scope=annotation-points.test | protects=stacked, pie, dataset and explicit encoding are not guessed
test('stacked, pie, dataset and explicit encoding are not guessed',()=>{
 for(const update of [{stack:'total'},{type:'pie'},{data:undefined,datasetIndex:0},{encode:{x:1,y:0}}]){const o=options();Object.assign(o.series[0],update);assert.equal(pickAnnotationPoint(mock(o),180,360),null);}
});
// @wu-test type=behavior | scope=annotation-points.test | protects=zero-size, offscreen and malformed coordinates are rejected
test('zero-size, offscreen and malformed coordinates are rejected',()=>{
 const o=options(),c=mock(o);c.getWidth=()=>0;assert.equal(pickAnnotationPoint(c,180,360),null);
 c.getWidth=()=>400;c.convertToPixel=()=>[NaN,12];assert.equal(pickAnnotationPoint(c,180,360),null);
 c.convertToPixel=()=>[-1,12];assert.equal(pickAnnotationPoint(c,180,360),null);
});
// @wu-test type=behavior | scope=annotation-points.test | protects=filter key is stable to filter order but changes with values
test('filter key is stable to filter order but changes with values',()=>{
 const a={id:'a',values:['East'],field:'region',componentIds:['k']},b={id:'b',values:[1],field:'period',componentIds:['k']};
 assert.equal(annotationFilterKey({manifest:{filters:[a,b]}}),annotationFilterKey({manifest:{filters:[b,a]}}));
 assert.notEqual(annotationFilterKey({manifest:{filters:[a]}}),annotationFilterKey({manifest:{filters:[{...a,values:['West']}]}}));
});
// @wu-test type=behavior | scope=annotation-points.test | protects=20,000-point candidate scan remains linear and bounded
test('20,000-point candidate scan remains linear and bounded',()=>{
 const o={xAxis:{type:'category',data:Array.from({length:20000},(_,i)=>String(i))},yAxis:{type:'value'},series:[{type:'line',data:Array(20000).fill(1)}]};
 const started=performance.now();assert.ok(pickAnnotationPoint(mock(o),130,470));assert.ok(performance.now()-started<2000);
});
