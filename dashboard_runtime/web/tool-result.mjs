/* Decode one response once. Never trim trailing data to hide a transport error. */
export async function resolveToolResult(result, call) {
  let requestId='';
  try {
    const value=decodeToolResult(result), transfer=value?.transport;
    if(!transfer)return value;
    requestId=transfer.requestId;
    if(transfer.encoding!=='base64-json-v1'||!Number.isInteger(transfer.chunks)||transfer.chunks<1)throw Error('Invalid preview transport envelope');
    const pieces=[];
    for(let index=0;index<transfer.chunks;index++){
      const part=decodeToolResult(await call('runtime_result_chunk',{requestId,index}));
      if(part.requestId!==requestId||part.index!==index||typeof part.data!=='string')throw Error('Preview chunk mismatch');
      pieces.push(part.data);
    }
    const bytes=Uint8Array.from(atob(pieces.join('')),c=>c.charCodeAt(0));
    if(bytes.length!==transfer.bytes)throw Error('Preview response byte count mismatch');
    return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
  }catch(error){
    try{await call('runtime_report_error',{requestId,code:'CLIENT_DECODE_FAILED'});}catch{}
    throw Error(`${error.message}${requestId?` [请求 ${requestId}]`:''}`);
  }
}
export function decodeToolResult(result) {
  if (result?.isError) {
    let detail=result.structuredContent;
    const text=result.content?.find(block=>block.type==='text')?.text;
    if(!detail&&text){try{detail=JSON.parse(text);}catch{}}
    const request=detail?.error?.requestId;
    throw Object.assign(Error((detail?.error?.message||text||'Tool failed')+(request?` [请求 ${request}]`:'')),{code:detail?.error?.code,requestId:request});
  }
  if (result?.structuredContent) return result.structuredContent;
  const text = result?.content?.find(block=>block.type==='text')?.text;
  if (!text) return result;
  let value;
  try { value = JSON.parse(text); }
  catch (error) { throw Error(`预览响应解析失败（文本 ${text.length} 字符）：${error.message}`); }
  if (['structuredContent.document','structuredContent'].includes(value?.artifactLocation)) {
    throw Error('预览响应缺少 structuredContent，无法读取完整看板；请检查宿主是否保留结构化结果。');
  }
  return value;
}
