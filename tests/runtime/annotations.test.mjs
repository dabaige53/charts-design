import test from 'node:test';
import assert from 'node:assert/strict';
import {relativeRect,absoluteRect} from '../../dashboard_runtime/web/annotations.mjs';
// @wu-test type=behavior | scope=annotations.test | protects=annotation follows a moved and resized component
test('annotation follows a moved and resized component',()=>{
 const saved=relativeRect({left:150,top:240,width:100,height:60},{left:100,top:200,width:400,height:300});
 assert.deepEqual(absoluteRect(saved,{left:600,top:100,width:200,height:150}),{left:625,top:120,width:50,height:30});
});
// @wu-test type=behavior | scope=annotations.test | protects=selection stays within target bounds
test('selection stays within target bounds',()=>{
 assert.deepEqual(relativeRect({left:90,top:190,width:600,height:500},{left:100,top:200,width:400,height:300}),{x:0,y:0,width:1,height:1});
});
// @wu-test type=behavior | scope=annotations.test | protects=collapsed targets do not create NaN or Infinity coordinates
test('collapsed targets do not create NaN or Infinity coordinates',()=>{
 assert.deepEqual(relativeRect({left:0,top:0,width:2,height:2},{left:0,top:0,width:0,height:0}),{x:0,y:0,width:0,height:0});
});
