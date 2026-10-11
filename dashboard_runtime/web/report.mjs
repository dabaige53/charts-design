import DOMPurify from 'dompurify';
import {parseReportMarkdown,reportMarkdown} from '../../runtime-ui/report-markdown.mjs';
export {reportMarkdown};
// Isolated purifier: original chart adapter has stricter link-removal hooks.
const reportPurifier=DOMPurify(window);
const node=(tag,cls='',text='')=>{const e=document.createElement(tag);e.className=cls;e.textContent=text;return e;};
export function renderReport({host,doc,editing,mount,draft,onSave,onChange,onDiscard,onDownload,onDisposeCharts}){
  const shell=node('div','markdown-workspace'+(editing?' is-writing':'')),bar=node('div','markdown-toolbar'),label=node('div','markdown-label',editing?'MARKDOWN / 写作与预览':'分析报告 / 阅读'),state=node('span','markdown-save-state'),preview=node('article','markdown-preview');
  bar.append(label,state);shell.append(bar);host.append(shell);
  let timer=null,disposed=false,saving=false,warnings=[];
  const button=(text,run)=>{const b=node('button','',text);b.type='button';b.onclick=run;return b;};
  const download=button('导出 .md',()=>onDownload(draft.text));bar.append(download);
  let area,save,cancel;
  if(editing){
    const panes=node('div','markdown-panes'),editor=node('section','markdown-editor-pane'),head=node('div','markdown-pane-label','源文件 .md');area=node('textarea','markdown-source');area.value=draft.text;area.spellcheck=false;area.setAttribute('aria-label','Markdown 源文档');
    const picker=node('select');picker.setAttribute('aria-label','插入图表代码块');const option=node('option','','插入图表代码块…');option.value='';picker.append(option);
    for(const [id,c] of Object.entries(doc.manifest.components)){if(c.kind==='text')continue;const o=node('option','',c.title+' · '+id);o.value=id;picker.append(o);}
    picker.onchange=()=>{if(!picker.value)return;const block='\n\n```chart\n'+JSON.stringify({componentId:picker.value})+'\n```\n\n';area.setRangeText(block,area.selectionStart,area.selectionEnd,'end');picker.value='';changed();area.focus();};
    head.append(picker);editor.append(head,area,node('div','markdown-editor-hint','标准 Markdown；chart 围栏引用已有图表。用 [^note] 和 [^note]: 说明添加文末注释。普通代码块只显示源码。'));
    const right=node('section','markdown-preview-pane');right.append(node('div','markdown-pane-label','实时预览'),preview);panes.append(editor,right);shell.append(panes);
    save=button('保存文档',async()=>{if(save.disabled)return;saving=true;save.disabled=true;state.textContent='保存中…';const source=area.value;try{await onSave(source);saving=false;if(!disposed)status();}catch(e){saving=false;if(!disposed){state.textContent=e.message;save.disabled=false;state.classList.add('error');}}});save.setAttribute('aria-label','保存 Markdown');cancel=button('放弃修改',()=>onDiscard());bar.append(cancel,save);
    area.oninput=changed;
  }else shell.append(preview);
  function changed(){onChange(area.value);status();clearTimeout(timer);timer=setTimeout(draw,180);}
  function status(){state.textContent=(saving?'保存中…':draft.dirty?'未保存修改':`已保存 · v${draft.revision}`)+(warnings.length?` · ${warnings.length} 个注释引用未定义`:'');state.title=warnings.join('\n');state.classList.remove('error');state.classList.toggle('warning',warnings.length>0);if(save)save.disabled=saving||!draft.dirty;if(cancel)cancel.disabled=!draft.dirty;}
  function draw(){if(disposed)return;onDisposeCharts();const result=parseReportMarkdown(draft.text,doc.manifest.components);warnings=result.warnings;preview.innerHTML=reportPurifier.sanitize(result.html,{FORBID_TAGS:['img','iframe','object','embed','form','style'],FORBID_ATTR:['style'],ALLOW_DATA_ATTR:true});
    for(const a of preview.querySelectorAll('a')){if(!a.getAttribute('href')?.startsWith('#')){a.rel='noopener noreferrer';a.target='_blank';}}
    let sectionNumber=0;for(const h of preview.querySelectorAll(':scope > h2')){if(!/^(摘要|关键词|Abstract|Keywords)$/i.test(h.textContent.trim())){sectionNumber++;if(!/^\d+[.、．\s]/.test(h.textContent))h.prepend(node('span','paper-section-number',sectionNumber+'　'));}}
    for(const p of preview.querySelectorAll(':scope > p')){if(/^摘要[：:]/.test(p.textContent.trim()))p.classList.add('paper-abstract');if(/^关键词[：:]/.test(p.textContent.trim()))p.classList.add('paper-keywords');}
    const subtitle=preview.querySelector(':scope > h1 + p');if(subtitle?.children.length===1&&subtitle.firstElementChild.tagName==='EM')subtitle.classList.add('paper-subtitle');
    const figureNumbers=new Map();for(const [index,ch] of result.charts.entries())if(!ch.error&&!figureNumbers.has(ch.componentId))figureNumbers.set(ch.componentId,index+1);
    for(const a of preview.querySelectorAll('a[href^="#fig-"]')){const target=a.getAttribute('href').slice(5),number=figureNumbers.get(target);if(number){if(a.textContent.trim()==='图')a.textContent='图 '+number;a.classList.add('paper-figure-ref');}else{a.classList.add('markdown-error');a.textContent='未找到图引用：'+target;result.errors.push('未找到图引用：'+target);}}
    for(const chart of result.charts){if(chart.error)continue;const slot=preview.querySelector(`[data-chart-slot="${chart.slot}"]`),c=doc.manifest.components[chart.componentId];if(!preview.querySelector('#fig-'+chart.componentId))slot.id='fig-'+chart.componentId;slot.classList.add('paper-figure');const host=node('div','original-host markdown-chart');host.style.height=c.kind==='statistical'?'auto':(c.kind==='kpi'||c.family==='kpi'?180:c.kind==='table'||c.family==='table'?340:250)+'px';slot.append(host);try{mount(host,chart.componentId);}catch(e){slot.append(node('p','markdown-error',e.message));}slot.append(node('figcaption','paper-caption',`图 ${chart.slot+1}　${chart.caption??c.title}`));if(chart.source)slot.append(node('div','paper-source',chart.source));}
    if(!draft.text.trim())preview.append(node('p','markdown-placeholder','从一个标题开始写，然后在文字之间插入图表。'));
    if(result.errors.length){state.textContent=`${result.errors.length} 个图表代码块需要修正 · 原文已保留`;if(save)save.disabled=true;}else status();
  }
  status();draw();return ()=>{disposed=true;clearTimeout(timer);};
}
