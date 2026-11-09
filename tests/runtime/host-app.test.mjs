import test from 'node:test';
import assert from 'node:assert/strict';
import {initializeResult} from '../../runtime-ui/host-app.mjs';
import {supportsAnnotationContext} from '../../dashboard_runtime/web/annotation-context.mjs';
// @wu-test type=integration | scope=host SDK initialization | protects=SDK解析后丢失composer能力
test('real SDK initialization preserves composer capabilities',()=>{
 const parsed=initializeResult.parse({protocolVersion:'2026-01-26',hostInfo:{name:'test',version:'1'},hostCapabilities:{experimental:{'openai/modelContext':{}},updateModelContext:{text:{}}},hostContext:{}});
 assert.equal(supportsAnnotationContext({getHostCapabilities:()=>parsed.hostCapabilities}),true);
 assert.equal(supportsAnnotationContext({getHostCapabilities:()=>({updateModelContext:{text:{}}})}),false);
});
