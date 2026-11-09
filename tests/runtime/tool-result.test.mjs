import test from 'node:test';
import assert from 'node:assert/strict';
import {decodeToolResult,resolveToolResult} from '../../dashboard_runtime/web/tool-result.mjs';

// @wu-test type=integration | scope=chunk decoding | protects=大响应丢行或Unicode损坏
test('large text-only chunk transport preserves Unicode and every row',async()=>{
 const original={document:{rows:Array.from({length:30000},(_,i)=>({id:i,name:'真实机场😀"\\\n'}))}};
 const bytes=Buffer.from(JSON.stringify(original)),encoded=bytes.toString('base64'),parts=encoded.match(/.{1,24000}/g);
 const envelope={transport:{encoding:'base64-json-v1',requestId:'test',chunks:parts.length,bytes:bytes.length}};
 const response=await resolveToolResult({content:[{type:'text',text:JSON.stringify(envelope)}]},async(name,args)=>({content:[{type:'text',text:JSON.stringify({requestId:'test',index:args.index,data:parts[args.index]})}]}));
 assert.deepEqual(response,original);
});
// @wu-test type=boundary | scope=chunk decoding | protects=错误分块被接受或诊断泄漏内容
test('corrupt chunk fails explicitly and records a metadata-only event',async()=>{
 const calls=[];
 await assert.rejects(resolveToolResult({structuredContent:{transport:{encoding:'base64-json-v1',requestId:'bad',chunks:1,bytes:20}}},async(name,args)=>{calls.push({name,args});return {structuredContent:{requestId:'other',index:0,data:'e30='}};}),/chunk mismatch.*bad/);
 assert.deepEqual(calls.at(-1),{name:'runtime_report_error',args:{requestId:'bad',code:'CLIENT_DECODE_FAILED'}});
});

// @wu-test type=behavior | scope=tool result decoding | protects=已有结构化结果被摘要覆盖
test('structured results do not parse the summary or malformed text',()=>{
 const value={document:{id:'board'}};
 assert.equal(decodeToolResult({structuredContent:value,content:[{type:'text',text:'{} trailing'}]}),value);
});
// @wu-test type=behavior | scope=tool result compatibility | protects=旧版纯文本JSON无法读取
test('legacy text-only JSON remains supported',()=>{
 assert.deepEqual(decodeToolResult({content:[{type:'text',text:'{"document":{"id":"legacy"}}'}]}),{document:{id:'legacy'}});
});
// @wu-test type=boundary | scope=tool result decoding | protects=截断解析或隐藏无效尾随字符
test('invalid JSON reports input length without swallowing trailing characters',()=>{
 assert.throws(()=>decodeToolResult({content:[{type:'text',text:'{} {}'}]}),/文本 5 字符/);
});
// @wu-test type=boundary | scope=tool result decoding | protects=缺失结构化数据或工具错误被当成功
test('missing structured artifact and tool errors are explicit',()=>{
 assert.throws(()=>decodeToolResult({content:[{type:'text',text:'{"artifactLocation":"structuredContent.document"}'}]}),/缺少 structuredContent/);
 assert.throws(()=>decodeToolResult({isError:true,content:[{type:'text',text:'Revision conflict'}]}),/Revision conflict/);
});

 // @wu-test type=behavior | scope=tool result errors | protects=版本冲突代码丢失导致无法重试
 test('structured revision errors retain their code for a fresh definition retry',()=>{
   assert.throws(()=>decodeToolResult({isError:true,structuredContent:{error:{code:'REVISION_CONFLICT',message:'Reload'}}}),error=>error.code==='REVISION_CONFLICT'&&error.message==='Reload');
   assert.throws(()=>decodeToolResult({content:[{type:'text',text:'{"artifactLocation":"structuredContent"}'}]}),/缺少 structuredContent/);
 });
