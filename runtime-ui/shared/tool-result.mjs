/* Decode one response once. Never trim trailing data to hide a transport error. */
export async function resolveToolResult(result, call) {
  let requestId='';const started=performance.now();
  try {
    const value=decodeToolResult(result), transfer=value?.transport;
    if(!transfer)return expandRecords(value);
    requestId=transfer.requestId;
    if(transfer.encoding!=='base64-json-v1'||!Number.isInteger(transfer.chunks)||transfer.chunks<1)throw Error('Invalid preview transport envelope');
    const pieces=new Array(transfer.chunks);let next=0;
    async function worker(){while(next<transfer.chunks){const index=next++;const part=decodeToolResult(await call('runtime_result_chunk',{requestId,index}));if(part.requestId!==requestId||part.index!==index||typeof part.data!=='string')throw Error('Preview chunk mismatch');pieces[index]=part.data;}}
    await Promise.all(Array.from({length:Math.min(4,transfer.chunks)},worker));
    const bytes=Uint8Array.from(atob(pieces.join('')),c=>c.charCodeAt(0));
    if(bytes.length!==transfer.bytes)throw Error('Preview response byte count mismatch');
    const decoded=expandRecords(JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes)));
    Promise.resolve().then(()=>call('runtime_report_error',{requestId,code:'CLIENT_DECODE_COMPLETE',durationMs:performance.now()-started})).catch(()=>{});
    return decoded;
  }catch(error){
    try{await call('runtime_report_error',{requestId,code:'CLIENT_DECODE_FAILED'});}catch{}
    throw Object.assign(Error(`${error.message}${requestId?` [请求 ${requestId}]`:''}`),
      {code:error.code,requestId:error.requestId||requestId});
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

export function expandRecords(value){
  const computed=value?.computed||value?.document?.computed;
  for(const component of Object.values(computed?.components||{})){
    const data=component.data,packed=data?.packedRecords;
    if(!packed)continue;
    data.records=packed.rows.map(row=>({category:row[0],series:row[1],values:Object.fromEntries(packed.keys.map((key,i)=>[key,row[i+2]]))}));
    delete data.packedRecords;
  }
  return value;
}
