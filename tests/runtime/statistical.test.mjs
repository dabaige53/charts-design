import { test } from 'bun:test';
import assert from 'node:assert/strict';
import {statisticalImageSource,updateStatisticalArtifacts} from '../../dashboard_runtime/web/statistical.mjs';

const svg='data:image/svg+xml;base64,PHN2Zy8+';
const png='data:image/png;base64,YQ==';

// @wu-test type=boundary | scope=statistical image source | protects=远程危险或错误格式图片URL被接受
test('Statistical image sources allow only exact embedded SVG/PNG Base64 URLs',()=>{
  for(const value of [svg,png])assert.equal(statisticalImageSource(value),value);
  for(const value of [undefined,null,{},'',
    'https://example.com/plot.png','javascript:alert(1)','file:///tmp/plot.svg','blob:plot',
    'data:text/html;base64,YQ==','data:image/jpeg;base64,YQ==','data:image/svg+xml,<svg/>',
    'data:image/svg+xml;utf8;base64,YQ==','data:image/SVG+xml;base64,YQ==',
    'data:image/png;base64,YQ=','data:image/png;base64,Y Q==','data:image/png;base64,YQ==#x',
    'data:image/png;base64,',' data:image/png;base64,YQ==','data:image/png;base64,YQ==\n',
    'data:image/png;base64,YQ=\n','data:image/png;base64,YQ\r\n']){
    assert.equal(statisticalImageSource(value),null,String(value));
  }
});

// @wu-test type=behavior | scope=statistical artifacts | protects=切换文档后显示旧统计图
test('Derived artifacts refresh on responses and clear instead of leaking across documents',()=>{
  const initial=Object.create(null),artifact={dataUri:svg,caption:'One raw observation per row.'};
  const first=updateStatisticalArtifacts(initial,{document:{id:'first'},statisticalArtifacts:{plot:artifact}});
  assert.notEqual(first,initial);assert.deepEqual(first.plot,artifact);
  assert.equal(updateStatisticalArtifacts(first,{source:{}}),first);
  assert.equal(updateStatisticalArtifacts(first,{statisticalArtifacts:{plot:{...artifact}}}),first);
  const changed=updateStatisticalArtifacts(first,{statisticalArtifacts:{plot:{...artifact,caption:'Updated'}}});
  assert.notEqual(changed,first);assert.equal(changed.plot.caption,'Updated');
  assert.deepEqual(Object.keys(updateStatisticalArtifacts(changed,{document:{id:'second'}})),[]);
  for(const value of [null,[],{},'invalid'])assert.deepEqual(Object.keys(updateStatisticalArtifacts(first,{statisticalArtifacts:value})),[]);
});

// @wu-test type=boundary | scope=statistical artifacts | protects=原型污染或非法字段进入展示
test('Artifact records are isolated own properties and accept only string display fields',()=>{
  const result=updateStatisticalArtifacts(Object.create(null),{statisticalArtifacts:JSON.parse('{"__proto__":{"caption":"Safe"},"invalid":null,"plot":{"caption":42,"dataUri":false,"error":"Unavailable","extra":"ignored"}}')});
  assert.equal(Object.getPrototypeOf(result),null);
  assert.equal(result.__proto__.caption,'Safe');assert.deepEqual(result.plot,{error:'Unavailable'});
  assert.equal(Object.hasOwn(result,'invalid'),false);
});
