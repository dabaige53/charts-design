import { test } from 'bun:test';
import assert from 'node:assert/strict';
import {createProjectContext} from '../../dashboard_runtime/web/project-context.mjs';
import {resolveToolResult} from '../../dashboard_runtime/web/tool-result.mjs';

// @wu-test type=boundary | scope=project context | protects=同ID看板跨项目请求或接受其他项目结果
test('two previews retain their projects for background, view, edit and annotation calls',async()=>{
  const calls=[];
  const send=async(name,args)=>{calls.push({name,args});return {};};
  const first=createProjectContext(send),second=createProjectContext(send);
  const waiting=first.call('runtime_info',{});
  await Promise.resolve();assert.equal(calls.length,0);
  first.accept({structuredContent:{projectRoot:'/project/first',document:{id:'same'}}});
  second.accept({structuredContent:{projectRoot:'/project/second',document:{id:'same'}}});
  await waiting;
  for(const name of ['dashboard_list','dashboard_view','dashboard_refresh','dashboard_patch','dashboard_annotations','runtime_keepalive']){
    await Promise.all([first.call(name,{dashboardId:'same'}),second.call(name,{dashboardId:'same'})]);
    assert.equal(calls.at(-2).args.projectRoot,'/project/first');
    assert.equal(calls.at(-1).args.projectRoot,'/project/second');
  }
  assert.throws(()=>first.accept({structuredContent:{projectRoot:'/project/second',document:{id:'same'}}}),/其他项目/);
  await assert.rejects(first.call('dashboard_get',{projectRoot:'/project/second'}),/切换项目/);
  await first.call('dashboard_get',{dashboardId:'same'});
  assert.equal(calls.at(-1).args.projectRoot,'/project/first');
});

// @wu-test type=integration | scope=project chunk transport | protects=首个分块请求发往错误项目
test('initial chunked result binds context before requesting chunks',async()=>{
  const value={projectRoot:'/project/chunked',document:{id:'same'}};
  const bytes=Buffer.from(JSON.stringify(value)),calls=[];
  const context=createProjectContext(async(name,args)=>{
    calls.push({name,args});assert.equal(args.projectRoot,value.projectRoot);
    return {structuredContent:{requestId:'chunks',index:0,data:bytes.toString('base64')}};
  });
  const envelope={structuredContent:{projectRoot:value.projectRoot,
    transport:{encoding:'base64-json-v1',requestId:'chunks',chunks:1,bytes:bytes.length}}};
  context.accept(envelope);
  const decoded=await resolveToolResult(envelope,(name,args)=>context.call(name,args));
  context.accept(decoded);
  assert.deepEqual(decoded,value);assert.equal(calls[0].name,'runtime_result_chunk');
});

// @wu-test type=behavior | scope=project context compatibility | protects=旧宿主请求形状变化或启动项目丢失
test('legacy hosts and startup project defaults retain their request shape',async()=>{
  const calls=[],legacy=createProjectContext(async(name,args)=>calls.push({name,args}));
  legacy.accept({content:[{type:'text',text:'{"document":{"id":"legacy"}}'}]});
  await legacy.call('dashboard_get',{dashboardId:'legacy'});
  assert.deepEqual(calls[0],{name:'dashboard_get',args:{dashboardId:'legacy'}});
  const scoped=createProjectContext(async(name,args)=>calls.push({name,args}));
  scoped.accept({structuredContent:{projectRoot:'/startup/default',document:{id:'same'}}});
  await scoped.call('dashboard_list',{});
  assert.equal(calls[1].args.projectRoot,'/startup/default');
});
