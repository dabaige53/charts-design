import test from 'node:test';
import assert from 'node:assert/strict';
import {whileVisible} from '../../dashboard_runtime/web/lifecycle.mjs';

test('visible preview renews; hidden or closed preview stops; restored page resumes',()=>{
  const doc=new EventTarget(),win=new EventTarget(),timers=new Map();let next=0,calls=0;
  doc.visibilityState='visible';
  win.setInterval=callback=>{timers.set(++next,callback);return next;};
  win.clearInterval=id=>timers.delete(id);
  const dispose=whileVisible(()=>calls++,20000,doc,win);
  assert.equal(calls,1);assert.equal(timers.size,1);
  doc.visibilityState='hidden';doc.dispatchEvent(new Event('visibilitychange'));
  assert.equal(timers.size,0);assert.equal(calls,1);
  doc.visibilityState='visible';doc.dispatchEvent(new Event('visibilitychange'));
  assert.equal(timers.size,1);assert.equal(calls,2);
  win.dispatchEvent(new Event('pagehide'));assert.equal(timers.size,0);
  win.dispatchEvent(new Event('pageshow'));assert.equal(timers.size,1);assert.equal(calls,3);
  dispose();assert.equal(timers.size,0);
  doc.dispatchEvent(new Event('visibilitychange'));assert.equal(calls,3);
});
