import test from 'node:test';
import assert from 'node:assert/strict';
import {relativeRect,absoluteRect} from '../../dashboard_runtime/web/annotations.mjs';

test('annotation follows a moved and resized component',()=>{
  const saved=relativeRect({left:150,top:240,width:100,height:60},{left:100,top:200,width:400,height:300});
  assert.deepEqual(absoluteRect(saved,{left:600,top:100,width:200,height:150}),{left:625,top:120,width:50,height:30});
});
test('selection stays within target bounds',()=>{
  assert.deepEqual(relativeRect({left:90,top:190,width:600,height:500},{left:100,top:200,width:400,height:300}),{x:0,y:0,width:1,height:1});
});
