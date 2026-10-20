import test from 'node:test';
import assert from 'node:assert/strict';
import {aggregate} from '../../dashboard_runtime/web/engine.mjs';
test('entity ratio nets rows by channel before counting and preserves missing',()=>{
  const metric={aggregation:'entity_ratio',entityField:'agent',numerator:'ho',denominator:'market'};
  const rows=[{agent:'A',ho:3,market:10},{agent:'A',ho:-3,market:10},
    {agent:'B',ho:0,market:5},{agent:'C',ho:2,market:3}];
  assert.equal(aggregate(rows,metric),1/3);
  assert.equal(aggregate([],metric),null);
  assert.equal(aggregate([{agent:'A',ho:null,market:null}],metric),null);
});
