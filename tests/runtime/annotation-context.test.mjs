import { test } from 'bun:test';
import assert from 'node:assert/strict';
import {supportsAnnotationContext,createAnnotationContext} from '../../dashboard_runtime/web/annotation-context.mjs';
const doc={id:'board',revision:29,manifest:{title:'看板',components:{chart:{title:'区域'}},filters:[{field:'month',values:['2026-10']}]}};
const note={componentId:'chart',anchor:{kind:'area',rect:{x:.1,y:.2,width:.3,height:.4},quote:'区域'},text:'检查'};
// @wu-test type=boundary | scope=composer capabilities | protects=未声明能力的宿主收到替换请求
test('only advertised composer extension enables replacement',()=>{
 assert.equal(supportsAnnotationContext({getHostCapabilities:()=>({updateModelContext:{text:{}}})}),false);
 assert.equal(supportsAnnotationContext({getHostCapabilities:()=>({experimental:{'openai/modelContext':{}},updateModelContext:{text:{}}})}),true);
});
// @wu-test type=integration | scope=annotation context | protects=位置筛选丢失或宿主移除后继续累积旧附件
test('attachments accumulate, preserve location and filters, and follow host removal',async()=>{
 const calls=[];const bridge=createAnnotationContext({getHostContext:()=>({}),sendMessage:()=>{assert.fail('Must not send a conversation request');},updateModelContext:async p=>{calls.push(p);return {};}});
 await Promise.all([bridge.attach(doc,note),bridge.attach(doc,note)]);
 assert.equal(calls[1].content.length,2);
 const context=JSON.parse(calls[0].content[0].text.split('\n').slice(1).join('\n'));
 assert.equal(context.comment,'检查');
 assert.deepEqual(context.filters,doc.manifest.filters);assert.deepEqual(context.anchor,note.anchor);
 bridge.sync({'openai/modelContext':null});await bridge.attach(doc,note);
 assert.equal(calls[2].content.length,1);
});
// @wu-test type=behavior | scope=annotation context | protects=失败附件在重试时重复出现
test('rejection does not mark failed attachment as accepted',async()=>{
 let fail=true;const calls=[];
 const bridge=createAnnotationContext({getHostContext:()=>({}),updateModelContext:async p=>{calls.push(p);return {isError:fail};}});
 await assert.rejects(bridge.attach(doc,note));fail=false;await bridge.attach(doc,note);
 assert.equal(calls[1].content.length,1);
});

// @wu-test type=behavior | scope=annotation context | protects=同 ID 看板引用错误项目
test('composer references identify the owning project when dashboard IDs repeat',async()=>{
 const calls=[];
 const bridge=createAnnotationContext({getHostContext:()=>({}),updateModelContext:async p=>{calls.push(p);return {};}});
 await bridge.attach({...doc,projectRoot:'/projects/first'},note);
 const context=JSON.parse(calls[0].content[0].text.split('\n').slice(1).join('\n'));
 assert.equal(context.projectRoot,'/projects/first');assert.equal(context.dashboardId,doc.id);
});
