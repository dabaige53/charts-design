/* Decode one response once. Never trim trailing data to hide a transport error. */
export function decodeToolResult(result) {
  if (result?.isError) throw Error(result.content?.find(block=>block.type==='text')?.text || 'Tool failed');
  if (result?.structuredContent) return result.structuredContent;
  const text = result?.content?.find(block=>block.type==='text')?.text;
  if (!text) return result;
  let value;
  try { value = JSON.parse(text); }
  catch (error) { throw Error(`预览响应解析失败（文本 ${text.length} 字符）：${error.message}`); }
  if (value?.artifactLocation === 'structuredContent.document') {
    throw Error('预览响应缺少 structuredContent，无法读取完整看板；请检查宿主是否保留结构化结果。');
  }
  return value;
}
