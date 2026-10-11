import test from 'node:test';
import assert from 'node:assert/strict';
import {statisticalImageSource,updateStatisticalArtifacts,mountStatisticalImage} from '../../dashboard_runtime/web/statistical.mjs';

const svg='data:image/svg+xml;base64,PHN2Zy8+';
const png='data:image/png;base64,YQ==';

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

test('Artifact records are isolated own properties and accept only string display fields',()=>{
  const result=updateStatisticalArtifacts(Object.create(null),{statisticalArtifacts:JSON.parse('{"__proto__":{"caption":"Safe"},"invalid":null,"plot":{"caption":42,"dataUri":false,"error":"Unavailable","extra":"ignored"}}')});
  assert.equal(Object.getPrototypeOf(result),null);
  assert.equal(result.__proto__.caption,'Safe');assert.deepEqual(result.plot,{error:'Unavailable'});
  assert.equal(Object.hasOwn(result,'invalid'),false);
});

// A tiny DOM fixture keeps mount tests dependency-free. Full browser integration
// additionally verifies image decoding, layout, transport and editor behavior.
function withDocument(run){
  const previous=globalThis.document;
  const createElement=tag=>({tagName:tag,className:'',textContent:'',children:[],attributes:{},listeners:{},
    append(child){child.parent=this;this.children.push(child);},
    setAttribute(name,value){this.attributes[name]=value;},
    addEventListener(name,listener){this.listeners[name]=listener;},
    remove(){this.parent.children=this.parent.children.filter(child=>child!==this);}
  });
  globalThis.document={createElement};
  try{run(createElement('section'));}finally{if(previous===undefined)delete globalThis.document;else globalThis.document=previous;}
}

test('Statistical mount creates an inert image with title alt and literal caption',()=>withDocument(card=>{
  const caption='<img src=x onerror=alert(1)>; n = 3';
  mountStatisticalImage(card,{title:'Distribution'},{dataUri:svg,caption});
  const [figure]=card.children,[image,text]=figure.children;
  assert.equal(figure.tagName,'figure');assert.equal(image.tagName,'img');
  assert.equal(image.src,svg);assert.equal(image.alt,'Distribution');
  assert.equal(text.tagName,'figcaption');assert.equal(text.textContent,caption);
  assert.equal(text.children.length,0);
  image.listeners.error();
  assert.equal(figure.children.some(child=>child.tagName==='img'),false);
  assert.match(figure.children.at(-1).textContent,/无法加载/);
  assert.equal(figure.children.at(-1).attributes.role,'alert');
}));

test('Missing, failed and remote artifacts show clear errors without assigning image URLs',()=>{
  for(const [artifact,expected] of [
    [undefined,/未包含生成的图片/],
    [{error:'Backend unavailable <script>',dataUri:svg},/Backend unavailable <script>/],
    [{dataUri:'https://example.com/plot.svg'},/图片格式无效/]
  ])withDocument(card=>{
    mountStatisticalImage(card,{title:'Distribution'},artifact);
    const [figure]=card.children;
    assert.equal(figure.children.some(child=>child.tagName==='img'),false);
    assert.match(figure.children[0].textContent,expected);
    assert.equal(figure.children[0].attributes.role,'alert');
  });
});
