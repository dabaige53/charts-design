import test from 'node:test';
import assert from 'node:assert/strict';
import {decodeToolResult} from '../../dashboard_runtime/web/tool-result.mjs';

test('structured results do not parse the summary or malformed text',()=>{
 const value={document:{id:'board'}};
 assert.equal(decodeToolResult({structuredContent:value,content:[{type:'text',text:'{} trailing'}]}),value);
});
test('legacy text-only JSON remains supported',()=>{
 assert.deepEqual(decodeToolResult({content:[{type:'text',text:'{"document":{"id":"legacy"}}'}]}),{document:{id:'legacy'}});
});
test('invalid JSON reports input length without swallowing trailing characters',()=>{
 assert.throws(()=>decodeToolResult({content:[{type:'text',text:'{} {}'}]}),/文本 5 字符/);
});
test('missing structured artifact and tool errors are explicit',()=>{
 assert.throws(()=>decodeToolResult({content:[{type:'text',text:'{"artifactLocation":"structuredContent.document"}'}]}),/缺少 structuredContent/);
 assert.throws(()=>decodeToolResult({isError:true,content:[{type:'text',text:'Revision conflict'}]}),/Revision conflict/);
});

 test('structured revision errors retain their code for a fresh definition retry',()=>{
   assert.throws(()=>decodeToolResult({isError:true,structuredContent:{error:{code:'REVISION_CONFLICT',message:'Reload'}}}),error=>error.code==='REVISION_CONFLICT'&&error.message==='Reload');
   assert.throws(()=>decodeToolResult({content:[{type:'text',text:'{"artifactLocation":"structuredContent"}'}]}),/缺少 structuredContent/);
 });
