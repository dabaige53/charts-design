/* Additive review metadata; the canonical list remains manifest.annotations.
 * These helpers never mutate a document, metrics, filters or incoming notes. */
export const REVIEW_LIMITS = Object.freeze({notes:100, replies:50, text:4000, author:100});
export const REVIEW_CATEGORIES = Object.freeze(['explanation','insight','review']);
const copy = value => structuredClone(value);
const now = () => new Date().toISOString();
export function reviewId(prefix='note', cryptoAPI=globalThis.crypto) {
  if(typeof cryptoAPI?.randomUUID==='function')return `${prefix}-${cryptoAPI.randomUUID()}`;
  // randomUUID requires a secure context; getRandomValues also works on LAN HTTP.
  if(typeof cryptoAPI?.getRandomValues!=='function')throw new Error('Secure random IDs are not available.');
  const bytes=cryptoAPI.getRandomValues(new Uint8Array(16));
  bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=[...bytes].map(b=>b.toString(16).padStart(2,'0')).join('');
  return `${prefix}-${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}

export function reviewCategory(note) {
  return REVIEW_CATEGORIES.includes(note?.category) ? note.category : 'review';
}
export function reviewStatus(note) { return note?.status === 'resolved' ? 'resolved' : 'open'; }
export function reviewAuthor(value) {
  if (!value || !['human','ai'].includes(value.kind)) return {kind:'unknown',name:''};
  return {kind:value.kind,name:String(value.name || '').slice(0,REVIEW_LIMITS.author)};
}
export function reviewReplies(note) {
  return Array.isArray(note?.replies) ? note.replies.filter(item => item && typeof item.id === 'string' && typeof item.text === 'string').slice(0, REVIEW_LIMITS.replies) : [];
}
function editableReplies(note) {
  const replies=note.replies===undefined?[]:note.replies;
  if(!Array.isArray(replies)||replies.length>REVIEW_LIMITS.replies||replies.some(r=>!r||typeof r.id!=='string'||typeof r.text!=='string')||new Set(replies.map(r=>r.id)).size!==replies.length)
    throw new Error('Invalid reply history. Existing messages were not overwritten.');
  return replies;
}
function textOf(value) {
  if (typeof value !== 'string' || !value.trim() || [...value].length > REVIEW_LIMITS.text) throw new Error('Comment text must contain 1-4000 characters.');
  return value.trim();
}
function authorOf(value) {
  const author=reviewAuthor(value);
  if (author.kind === 'unknown') throw new Error('Declare whether the author is human or AI.');
  return author;
}
export function createReview(note, text, {category='review',author={kind:'human',name:''},at=now()}={}) {
  if (!REVIEW_CATEGORIES.includes(category)) throw new Error('Invalid comment category.');
  return {...copy(note),id:note.id || reviewId('note'),text:textOf(text),createdAt:note.createdAt || at,updatedAt:at,category,author:authorOf(author),status:'open',replies:[]};
}
export function appendReview(items, note) {
  if (items.length >= REVIEW_LIMITS.notes) throw new Error('At most 100 comments per document.');
  if (items.some(item => item.id === note.id)) throw new Error('Comment already exists.');
  return [...items,copy(note)];
}
export function changeReview(items, noteId, change) {
  if (!items.some(item => item.id === noteId)) throw new Error('Comment no longer exists. Reload before editing.');
  return items.map(note => note.id === noteId ? change(copy(note)) : note);
}
export function editReview(note, text, {expectedText=note.text,category=reviewCategory(note),at=now(),author={kind:'human',name:''}}={}) {
  if (note.text !== expectedText) throw new Error('This comment changed. Keep your draft and reload before editing.');
  if (!REVIEW_CATEGORIES.includes(category)) throw new Error('Invalid comment category.');
  const updated={...note,text:textOf(text),category,updatedAt:at,editedBy:authorOf(author)};
  if (note.agentRequest) updated.agentRequest={...note.agentRequest,status:'stale'};
  return updated;
}
export function addReviewReply(note, text, {author={kind:'human',name:''},at=now(),replyId=reviewId('reply')}={}) {
  const replies=editableReplies(note);
  if (replies.length >= REVIEW_LIMITS.replies) throw new Error('At most 50 replies per comment.');
  if (reviewStatus(note) === 'resolved') throw new Error('Reopen the comment before replying.');
  if (replies.some(reply => reply.id === replyId)) throw new Error('Reply already exists.');
  const result={...note,updatedAt:at,replies:[...replies,{id:replyId,text:textOf(text),createdAt:at,author:authorOf(author)}]};
  if (note.agentRequest) result.agentRequest={...note.agentRequest,status:'stale'};
  return result;
}
export function editReviewReply(note, replyId, text, {expectedText,at=now(),author={kind:'human',name:''}}={}) {
  let found=false;
  const replies=editableReplies(note).map(reply => {
    if (reply.id !== replyId) return reply;
    found=true;
    if (expectedText !== undefined && reply.text !== expectedText) throw new Error('This reply changed. Keep your draft and reload.');
    return {...reply,text:textOf(text),updatedAt:at,editedBy:authorOf(author)};
  });
  if (!found) throw new Error('Reply no longer exists.');
  return {...note,replies,updatedAt:at,...note.agentRequest ? {agentRequest:{...note.agentRequest,status:'stale'}} : {}};
}
export function deleteReviewReply(note, replyId, at=now()) {
  const replies=editableReplies(note);
  if (!replies.some(reply=>reply.id===replyId)) throw new Error('Reply no longer exists.');
  return {...note,replies:replies.filter(reply=>reply.id!==replyId),updatedAt:at,...note.agentRequest ? {agentRequest:{...note.agentRequest,status:'stale'}} : {}};
}
export function setReviewStatus(note, status, {at=now(),author={kind:'human',name:''}}={}) {
  if (!['open','resolved'].includes(status)) throw new Error('Invalid comment status.');
  const next={...note,status,updatedAt:at};
  if (status==='resolved') {
    next.resolvedAt=at;next.resolvedBy=authorOf(author);
    if (next.agentRequest) next.agentRequest={...next.agentRequest,status:'cancelled'};
  } else { delete next.resolvedAt;delete next.resolvedBy; }
  return next;
}
export function requestReviewAgent(note, at=now()) {
  if (reviewStatus(note)!=='open') throw new Error('Reopen the comment before requesting agent help.');
  if (note.agentRequest?.status==='requested') throw new Error('This request is already waiting for an agent.');
  return {...note,updatedAt:at,agentRequest:{status:'requested',requestedAt:at}};
}
export function reviewContextText(note) {
  return [note.text,...reviewReplies(note).map(reply=>`[${reviewAuthor(reply.author).kind}] ${reply.text}`)].join('\n\n');
}
// Group nearby pins instead of moving an individual pin away from its target.
export function clusterReviewPins(items, radius=28) {
  const groups=[];
  for (const item of items) {
    if (!Number.isFinite(item.x)||!Number.isFinite(item.y)) continue;
    const group=groups.find(group=>Math.hypot(group.x-item.x,group.y-item.y)<radius);
    if (group) group.items.push(item);else groups.push({x:item.x,y:item.y,items:[item]});
  }
  return groups;
}
