import { test } from 'bun:test';
import assert from 'node:assert/strict';
import {clearFilterValues} from '../../dashboard_runtime/web/local-filter.mjs';

// @wu-test type=behavior | scope=clear filters | protects=清除条件破坏筛选定义或原数据
test('clear all removes every condition and preserves its definition',()=>{
  const filters=[{id:'office',selectionMode:'single',values:['西安营业部']},{id:'period',values:['2026-09']},{id:'region',values:['欧洲']},{id:'channel',values:['普通代理']},{id:'search',op:'contains',values:['代理']}];
  const result=clearFilterValues(filters);
  assert.ok(result.every(filter=>filter.values.length===0));
  assert.equal(result[0].selectionMode,'single');
  assert.deepEqual(filters[0].values,['西安营业部']);
});

// @wu-test type=boundary | scope=required month filter | protects=清除筛选时丢失必选月份
test('clear preserves the required month',()=>{
  const filters=[{id:'period',field:'month',selectionMode:'single',required:true,values:['2026-08']},{id:'office',values:['上海营业部']}];
  assert.deepEqual(clearFilterValues(filters).map(filter=>filter.values),[['2026-08'],[]]);
  assert.deepEqual(filters[1].values,['上海营业部']);
});
