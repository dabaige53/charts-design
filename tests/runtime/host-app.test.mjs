import test from 'node:test';
import assert from 'node:assert/strict';
import {initializeResult} from '../../runtime-ui/host-app.mjs';
import {supportsAnnotationContext} from '../../dashboard_runtime/web/annotation-context.mjs';
test('real SDK initialization preserves composer capabilities',()=>{
 const parsed=initializeResult.parse({protocolVersion:'2026-01-26',hostInfo:{name:'test',version:'1'},hostCapabilities:{experimental:{'openai/modelContext':{}},updateModelContext:{text:{}}},hostContext:{}});
 assert.equal(supportsAnnotationContext({getHostCapabilities:()=>parsed.hostCapabilities}),true);
 assert.equal(supportsAnnotationContext({getHostCapabilities:()=>({updateModelContext:{text:{}}})}),false);
});
