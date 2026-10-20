/* Decode one response once. Never trim trailing data to hide a transport error. */
export function decodeToolResult(result) {
  if (result?.isError) {
    let detail=result.structuredContent;
    const text=result.content?.find(block=>block.type==='text')?.text;
    if(!detail&&text){try{detail=JSON.parse(text);}catch{}}
    throw Object.assign(Error(detail?.error?.message||text||'Tool failed'),{code:detail?.error?.code});
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
