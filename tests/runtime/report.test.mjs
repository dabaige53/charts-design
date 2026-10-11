import test from 'node:test';
import assert from 'node:assert/strict';
import {parseReportMarkdown,reportMarkdown} from '../../runtime-ui/report-markdown.mjs';
const components={trend:{kind:'chart',title:'Revenue'},note:{kind:'text',title:'Note',text:'Keep *literal* text'}};
test('Markdown prose surrounds inline chart fences, while ordinary code stays code',()=>{
 const text='# Analysis\n\n**Observation**\n\n- One\n- Two\n\n```chart\n{"componentId":"trend"}\n```\n\n## Next\n\n```js\nalert(1)\n```';
 const parsed=parseReportMarkdown(text,components);assert.equal(parsed.charts.length,1);assert.equal(parsed.errors.length,0);assert.match(parsed.html,/<h1>Analysis<\/h1>/);assert.match(parsed.html,/<strong>Observation<\/strong>/);assert.match(parsed.html,/<ul>/);assert.match(parsed.html,/language-js/);assert.ok(parsed.html.indexOf('markdown-chart-slot')<parsed.html.indexOf('<h2>Next'));
});
test('Invalid and missing chart references are inline errors, not execution',()=>{
 for(const payload of ['invalid','{"componentId":"missing"}','{"componentId":"note"}','{"componentId":"__proto__"}','{"componentId":"trend","code":"evil"}'])assert.equal(parseReportMarkdown('```chart\n'+payload+'\n```',components).errors.length,1);
 const result=parseReportMarkdown('<script>alert(1)</script>\n\n[jump](javascript:alert(1))',components);assert.ok(!result.html.includes('<script>'));assert.ok(!result.html.includes('href="javascript:'));
});
test('Legacy migration preserves order and canonical Markdown is returned byte-for-byte',()=>{
 const doc={manifest:{title:'Review',components,report:{subtitle:'Synthetic',blocks:[{id:'n',componentId:'note'},{id:'c',componentId:'trend'}]}}};const value=reportMarkdown(doc);assert.match(value,/Keep \\\*literal\\\* text/);assert.ok(value.indexOf('Note')<value.indexOf('```chart'));doc.manifest.report.markdown='# Exact\r\n\nend ';assert.equal(reportMarkdown(doc),'# Exact\r\n\nend ');
});
test('Paper captions and source notes are plain data with strict bounds',()=>{
 const spec={componentId:'trend',caption:'月度收入："观察"',source:'合成数据；单位：万元'};
 const result=parseReportMarkdown('```chart\n'+JSON.stringify(spec)+'\n```',components);
 assert.deepEqual(result.errors,[]);assert.equal(result.charts[0].caption,spec.caption);assert.equal(result.charts[0].source,spec.source);
 for(const bad of [{...spec,caption:null},{...spec,source:2},{...spec,caption:'x'.repeat(501)},{...spec,unknown:'x'}])assert.equal(parseReportMarkdown('```chart\n'+JSON.stringify(bad)+'\n```',components).errors.length,1);
});
test('Footnotes are numbered by first citation and collected after all prose',()=>{
 const text='指标[^metric]，来源[^source]。\n\n[^source]: [数据说明](https://example.com/source)\n[^metric]: **加权口径**。\n\n    第二段说明。\n\n## 附录\n\n最后一段。';
 const {html,errors,warnings}=parseReportMarkdown(text,components);
 assert.deepEqual(errors,[]);assert.deepEqual(warnings,[]);
 assert.match(html,/<a href="#fn-report-1" id="fnref-report-1"[^>]*>\[1\]<\/a>/);
 assert.match(html,/<a href="#fn-report-2" id="fnref-report-2"[^>]*>\[2\]<\/a>/);
 assert.match(html,/<section class="footnotes" role="doc-endnotes"[^>]*>\n<h2 id="report-notes-heading">注释<\/h2>/);
 assert.ok(html.indexOf('最后一段。')<html.indexOf('<section class="footnotes"'));
 assert.match(html,/<li id="fn-report-1" class="footnote-item"><p><strong>加权口径<\/strong>/);
 assert.match(html,/<p>第二段说明。/);
 assert.match(html,/<li id="fn-report-2" class="footnote-item"><p><a href="https:\/\/example.com\/source">数据说明<\/a>/);
 assert.match(html,/<\/ol>\n<\/section>\n$/);
});
test('Repeated note references retain one number and return to every occurrence',()=>{
 const {html}=parseReportMarkdown('第一次[^n]、第二次[^n]、第三次[^n]。\n\n[^n]: 一个说明。');
 assert.equal((html.match(/class="footnote-item"/g)||[]).length,1);
 assert.equal((html.match(/href="#fn-report-1"/g)||[]).length,3);
 assert.equal((html.match(/>\[1\]<\/a>/g)||[]).length,3);
 for(const suffix of ['','-1','-2']){
   assert.ok(html.includes(`id="fnref-report-1${suffix}"`));
   assert.ok(html.includes(`href="#fnref-report-1${suffix}"`));
 }
 assert.match(html,/aria-label="返回正文注释 1（第 3 处）"/);
 const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]);assert.equal(ids.length,new Set(ids).size);
});
test('Missing note references remain literal with a deduplicated nonblocking warning',()=>{
 const {html,errors,warnings}=parseReportMarkdown('缺失[^missing]、重复[^missing]，有效[^ok]。\n\n[^ok]: 完整说明。');
 assert.deepEqual(errors,[]);assert.deepEqual(warnings,['未定义注释：missing']);
 assert.match(html,/缺失\[\^missing\]、重复\[\^missing\]/);
 assert.equal((html.match(/class="footnote-ref"/g)||[]).length,1);
 assert.match(html,/id="fnref-report-1"/);
 const none=parseReportMarkdown('缺失[^only]\n\n[^unused]: 未引用。');
 assert.ok(!none.html.includes('class="footnotes"'));assert.ok(!none.html.includes('href="#fn'));
});
test('Code blocks, inline code, escaped references and note labels are never executable',()=>{
 const text='`[^inline]` 与 \\[^escaped]。\n\n```markdown\n[^fenced]\n[^definition]: 示例而已。\n```\n\n    [^indented]\n\n^[未启用的内联注释]';
 const {html,charts,errors,warnings}=parseReportMarkdown(text,components);
 assert.deepEqual(charts,[]);assert.deepEqual(errors,[]);assert.deepEqual(warnings,[]);
 assert.ok(!html.includes('class="footnotes"'));assert.match(html,/<code>\[\^inline\]<\/code>/);assert.match(html,/\[\^escaped\]/);
 assert.match(html,/class="language-markdown">\[\^fenced\]/);assert.match(html,/\[\^definition\]: 示例而已。/);
});
test('Note bodies keep safe Markdown links and escape HTML and unsafe URL schemes',()=>{
 const text='说明[^x"onclick="bad]。\n\n[^x"onclick="bad]: <script>alert(1)</script> <img src=x onerror=alert(1)>\n\n    [安全](https://example.com/?a=1&b=2) [危险](javascript:alert(1)) [文件](file:///etc/passwd) [数据](data:text/html,evil)';
 const {html,errors,warnings}=parseReportMarkdown(text);
 assert.deepEqual(errors,[]);assert.deepEqual(warnings,[]);
 assert.match(html,/id="fn-report-1"/);assert.ok(!html.includes('id="x'));
 assert.ok(!html.includes('<script'));assert.ok(!html.includes('<img'));assert.ok(!html.includes(' onclick="'));
 assert.match(html,/&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
 assert.match(html,/href="https:\/\/example.com\/\?a=1&amp;b=2"/);
 assert.ok(!/href="(?:javascript:|data:|file:)/i.test(html));
});
test('Chart-looking code inside notes is inert while top-level charts retain validation',()=>{
 for(const body of ['详情。\n\n    ```chart\n    {"componentId":"missing"}\n    ```','```chart\n    {"componentId":"trend"}\n    ```']){
   const source='正文[^n]。\n\n```chart\n{"componentId":"trend"}\n```\n\n[^n]: '+body;
   const {html,charts,errors}=parseReportMarkdown(source,components);
   assert.equal(charts.length,1);assert.equal(charts[0].componentId,'trend');assert.deepEqual(errors,[]);
   assert.equal((html.match(/class="markdown-chart-slot"/g)||[]).length,1);assert.match(html,/class="language-chart"/);
 }
 for(const source of ['> ```chart\n> {"componentId":"trend"}\n> ```','- ```chart\n  {"componentId":"trend"}\n  ```'])assert.equal(parseReportMarkdown(source,components).errors.length,1);
});
test('Footnote render state never leaks to a later report or changes canonical source',()=>{
 parseReportMarkdown('First[^one]\n\n[^one]: Note');
 const source='# 精确原文\r\n\r\n第二份[^two]。\r\n\r\n[^two]: 说明。  \r\n';
 const doc={manifest:{report:{markdown:source}}};
 assert.equal(reportMarkdown(doc),source);const parsed=parseReportMarkdown(source);
 assert.match(parsed.html,/id="fnref-report-1"/);assert.ok(!parsed.html.includes('id="fnref-report-2"'));
 assert.equal(reportMarkdown(doc),source);
});
