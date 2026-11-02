import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import {EventEmitter} from 'node:events';
test('update drains in-flight request and replays initialization before queued request',()=>{
 let generation='old';const input=new EventEmitter(),workers=[],results=[];
 const process=new EventEmitter();process.stdin={};process.stdout={write:s=>results.push(JSON.parse(s))};
 const modules={
  'node:path':path,'node:fs':{readFileSync:()=>generation},
  './python-runtime.js':{pythonRuntime:()=>({python:'python',env:{}})},
  'node:readline':{createInterface:({input:i})=>i===process.stdin?input:i},
  'node:child_process':{spawn:()=>{const w=new EventEmitter();w.stdout=new EventEmitter();w.stdin=new EventEmitter();w.sent=[];w.stdin.write=s=>w.sent.push(JSON.parse(s));w.stdin.end=()=>{w.ended=true;};workers.push(w);return w;}}
 };
 const context={require:n=>modules[n],module:{exports:{}},__dirname:'/package/bin',process,console};
 vm.runInNewContext(fs.readFileSync(new URL('../../bin/mcp-runtime.js',import.meta.url),'utf8'),context);
 context.module.exports.runMcp([]);
 const send=m=>input.emit('line',JSON.stringify(m));
 const reply=(w,m)=>w.stdout.emit('line',JSON.stringify(m));
 send({id:1,method:'initialize'});reply(workers[0],{id:1,result:{}});
 send({method:'notifications/initialized'});
 send({id:2,method:'tools/call'});generation='new';send({id:3,method:'tools/call'});
 assert.equal(workers[0].ended,undefined);
 assert.equal(workers[0].sent.some(x=>x.id===3),false);
 reply(workers[0],{id:2,result:{ok:true}});assert.equal(workers[0].ended,true);
 workers[0].emit('exit');assert.equal(workers.length,2);
 assert.equal(workers[1].sent.length,1);assert.equal(workers[1].sent[0].method,'initialize');
 reply(workers[1],{id:1,result:{}});
 assert.equal(workers[1].sent[1].method,'notifications/initialized');
 assert.equal(workers[1].sent[2].id,3);
 reply(workers[1],{id:3,result:{ok:true}});
 assert.deepEqual(results.map(x=>x.id),[1,2,3]);
});
