import MarkdownIt from 'markdown-it';
import markdownItFootnote from 'markdown-it-footnote';
const escape=MarkdownIt().utils.escapeHtml;
// Named notes use the parser's token stream, so code and escaped Markdown stay
// literal. IDs are generated from numeric positions, never from authored labels.
function reportFootnotes(md){
  md.use(markdownItFootnote);
  md.inline.ruler.disable('footnote_inline');
  md.inline.ruler.after('footnote_ref','report_missing_footnote',(state,silent)=>{
    if(silent)return false;
    const match=/^\[\^([^\]\s]+)\]/.exec(state.src.slice(state.pos,state.posMax));
    if(!match)return false;
    const warning=`未定义注释：${match[1]}`;
    state.env.reportWarnings??=[];
    if(!state.env.reportWarnings.includes(warning))state.env.reportWarnings.push(warning);
    state.push('text','',0).content=match[0];state.pos+=match[0].length;return true;
  });
  md.core.ruler.before('footnote_tail','report_note_code',state=>{
    let depth=0;
    for(const token of state.tokens){
      if(token.type==='footnote_reference_open')depth++;
      else if(token.type==='footnote_reference_close')depth--;
      else if(depth>0&&token.type==='fence')token.meta={...token.meta,reportNote:true};
    }
  });
  const number=(tokens,index)=>tokens[index].meta.id+1;
  const referenceId=(tokens,index)=>`fnref-report-${number(tokens,index)}${tokens[index].meta.subId>0?'-'+tokens[index].meta.subId:''}`;
  md.renderer.rules.footnote_ref=(tokens,index)=>{
    const n=number(tokens,index);
    return `<sup class="footnote-ref"><a href="#fn-report-${n}" id="${referenceId(tokens,index)}" role="doc-noteref" aria-label="注释 ${n}">[${n}]</a></sup>`;
  };
  md.renderer.rules.footnote_block_open=()=>'<section class="footnotes" role="doc-endnotes" aria-labelledby="report-notes-heading">\n<h2 id="report-notes-heading">注释</h2>\n<ol class="footnotes-list">\n';
  md.renderer.rules.footnote_open=(tokens,index)=>`<li id="fn-report-${number(tokens,index)}" class="footnote-item">`;
  md.renderer.rules.footnote_anchor=(tokens,index)=>{
    const n=number(tokens,index),occurrence=tokens[index].meta.subId+1;
    return ` <a href="#${referenceId(tokens,index)}" class="footnote-backref" role="doc-backlink" aria-label="返回正文注释 ${n}（第 ${occurrence} 处）">↩︎${occurrence>1?`<sup>${occurrence}</sup>`:''}</a>`;
  };
}
/** Markdown is content, never executable code. HTML is disabled. */
export function parseReportMarkdown(source,components={}){
  const charts=[],lines=source.replace(/\r\n?/g,'\n').split('\n');const md=new MarkdownIt({html:false,linkify:false,typographer:false,breaks:false});
  reportFootnotes(md);
  const ordinary=md.renderer.rules.fence;
  md.renderer.rules.fence=(tokens,index,options,env,renderer)=>{
    const token=tokens[index];if(token.info.trim()!=='chart'||token.meta?.reportNote)return ordinary(tokens,index,options,env,renderer);
    const slot=charts.length;let componentId=null,error=null,caption=null,sourceNote=null;
    try{if(token.level!==0)throw Error('chart 围栏请单独放在顶层，不放在列表或引用内部。');const closing=lines[(token.map?.[1]||0)-1]||'',marker=token.markup[0];if(!new RegExp('^ {0,3}'+(marker==='`'?'`':'~')+'{'+token.markup.length+',}[ \t]*$').test(closing))throw Error('chart 代码块缺少结束围栏。');const spec=JSON.parse(token.content);const keys=[...token.content.matchAll(/"(?:[^"\\]|\\.)*"/g)].filter(match=>token.content.slice(match.index+match[0].length).trimStart().startsWith(':'));const keyNames=keys.map(k=>JSON.parse(k[0]));if(new Set(keyNames).size!==keyNames.length)throw Error('chart JSON 不允许重复键。');if(!spec||Array.isArray(spec)||typeof spec!=='object'||Object.keys(spec).some(k=>!['componentId','caption','source'].includes(k))||typeof spec.componentId!=='string')throw Error('使用 componentId 引用图表，可选 caption 和 source。');for(const [key,max] of [['caption',500],['source',1000]])if(key in spec&&(typeof spec[key]!=='string'||Array.from(spec[key]).length>max))throw Error(key+' 必须是最多 '+max+' 字的文本。');caption=spec.caption??null;sourceNote=spec.source??null;componentId=spec.componentId;if(!Object.hasOwn(components,componentId))throw Error(`找不到图表：${componentId}`);if(components[componentId].kind==='text')throw Error('chart 代码块只能引用图表、KPI 或明细表。');}
    catch(e){error=e instanceof SyntaxError?'chart 代码块不是有效 JSON。':e.message;}
    charts.push({slot,componentId,error,caption,source:sourceNote});return `<figure class="markdown-chart-slot" data-chart-slot="${slot}">${error?`<p class="markdown-error">${escape(error)}</p>`:''}</figure>`;
  };
  const env={},html=md.render(source,env);return {html,charts,errors:charts.filter(c=>c.error).map(c=>c.error),warnings:env.reportWarnings||[]};
}
const literal=text=>String(text||'').replace(/[\\`*_{}\[\]()#+.!>|~-]/g,'\\$&');
export function reportMarkdown(doc){
  if(typeof doc.manifest.report?.markdown==='string')return doc.manifest.report.markdown;
  const report=doc.manifest.report||{subtitle:'',blocks:[...doc.manifest.layout.desktop].sort((a,b)=>a.y-b.y||a.x-b.x).map(p=>({id:p.id,componentId:p.id}))};
  const parts=['# '+literal(doc.manifest.title)];if(report.subtitle)parts.push(literal(report.subtitle));
  for(const b of report.blocks){const c=doc.manifest.components[b.componentId];if(!c)continue;if(c.kind==='text'){if(c.title)parts.push('## '+literal(c.title));if(c.subtitle)parts.push(literal(c.subtitle));parts.push(literal(c.text));}else parts.push('```chart\n'+JSON.stringify({componentId:b.componentId})+'\n```');}
  return parts.join('\n\n')+'\n';
}
