/* Plain-text editing only; saved values never become HTML. */
const controllers=new WeakMap();
export function clearInlineEdit(node){controllers.get(node)?.abort();controllers.delete(node);node.removeAttribute('contenteditable');node.removeAttribute('role');node.removeAttribute('aria-label');node.classList.remove('inline-edit');}
export function inlineEdit(node,{label,value='',maxLength=1000,save}){
  clearInlineEdit(node);const controller=new AbortController();controllers.set(node,controller);const options={signal:controller.signal};
  node.textContent=value;node.contentEditable='true';node.setAttribute('role','textbox');node.setAttribute('aria-label',label);node.dataset.placeholder=label;node.classList.add('inline-edit');
  let committed=value;
  node.addEventListener('paste',event=>{event.preventDefault();const text=event.clipboardData?.getData('text/plain')||'';document.execCommand('insertText',false,text);},options);
  node.addEventListener('keydown',event=>{if(event.key==='Escape'){node.textContent=committed;node.blur();}else if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();node.blur();}},options);
  node.addEventListener('blur',async()=>{const next=node.textContent.trim();if(next===committed)return;if(next.length>maxLength){node.textContent=committed;window.dispatchEvent(new CustomEvent('charts-error',{detail:Error(`最多 ${maxLength} 字符`)}));return;}node.contentEditable='false';try{await save(next);committed=next;}catch(error){node.textContent=committed;window.dispatchEvent(new CustomEvent('charts-error',{detail:error}));}finally{node.contentEditable='true';}},options);
}
