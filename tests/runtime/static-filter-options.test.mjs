import test from 'node:test';import assert from 'node:assert/strict';
import {staticFilterPage} from '../../dashboard_runtime/web/local-filter.mjs';
test('static filter supports search, later pages and clearing search with no server',()=>{
 const values=Array.from({length:230},(_,i)=>'代理'+i);const first=staticFilterPage(values);assert.equal(first.values.length,100);assert.equal(first.totalValues,230);assert.equal(first.hasMore,true);
 const last=staticFilterPage(values,'',200);assert.equal(last.values.length,30);assert.equal(last.hasMore,false);
 assert.deepEqual(staticFilterPage(values,'代理229').values,['代理229']);assert.equal(staticFilterPage(values,'不存在').totalValues,0);assert.equal(staticFilterPage(values).totalValues,230);
});
test('single office options and carrier text match without changing their exact values',()=>{
 assert.deepEqual(staticFilterPage(['上海营业部','深圳营业部'],'深圳').values,['深圳营业部']);assert.deepEqual(staticFilterPage(['HO','MU',null],'ho').values,['HO']);assert.deepEqual(staticFilterPage([]),{values:[],offset:0,totalValues:0,hasMore:false});
});
