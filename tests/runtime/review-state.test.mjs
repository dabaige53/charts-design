import test from 'node:test';
import assert from 'node:assert/strict';
import * as r from '../../dashboard_runtime/web/review-state.mjs';
const at='2026-11-09T12:00:00Z';
const note=()=>r.createReview({id:'note-a',componentId:'revenue'},'Check denominator',{at});
// @wu-test type=behavior | scope=review-state.test | protects=legacy notes remain open reviews with unknown provenance
test('legacy notes remain open reviews with unknown provenance',()=>{
 const old={id:'old',text:'Old',createdAt:at};assert.equal(r.reviewStatus(old),'open');assert.equal(r.reviewCategory(old),'review');assert.deepEqual(r.reviewAuthor(old.author),{kind:'unknown',name:''});assert.deepEqual(r.reviewReplies(old),[]);
});
// @wu-test type=behavior | scope=review-state.test | protects=new notes declare category, source, status without changing anchor
test('new notes declare category, source, status without changing anchor',()=>{
 const original={id:'note-a',anchor:{scope:'component',rect:{x:0,y:0,width:1,height:1}}};
 const created=r.createReview(original,'  Comment  ',{category:'insight',author:{kind:'ai',name:'Analyst'},at});
 assert.equal(created.text,'Comment');assert.equal(created.author.kind,'ai');assert.deepEqual(created.anchor,original.anchor);assert.equal(original.status,undefined);created.anchor.rect.x=1;assert.equal(original.anchor.rect.x,0);
});
// @wu-test type=behavior | scope=review-state.test | protects=each mutation preserves unrelated fields and documents
test('each mutation preserves unrelated fields and documents',()=>{
 const source=[{...note(),extra:{a:2}},{id:'other',text:'Unchanged'}],before=structuredClone(source);
 const updated=r.changeReview(source,'note-a',n=>r.addReviewReply(n,'Reply',{at,replyId:'reply-a'}));
 assert.deepEqual(source,before);assert.deepEqual(updated[0].extra,{a:2});assert.equal(updated[0].replies.length,1);assert.equal(updated[1],source[1]);
});
// @wu-test type=behavior | scope=review-state.test | protects=text validation rejects empty/oversized values and retains plain markup
test('text validation rejects empty/oversized values and retains plain markup',()=>{
 for(const text of ['', ' ', 'a'.repeat(4001),null])assert.throws(()=>r.createReview({},text));
 assert.equal(r.createReview({},'<img src=x onerror=alert(1)>').text,'<img src=x onerror=alert(1)>');
 assert.doesNotThrow(()=>r.createReview({},'a'.repeat(4000)));
});
// @wu-test type=behavior | scope=review-state.test | protects=category and provenance must be declared values
test('category and provenance must be declared values',()=>{
 assert.throws(()=>r.createReview({},'a',{category:'bad'}));assert.throws(()=>r.createReview({},'a',{author:{kind:'robot'}}));
 assert.equal(r.reviewAuthor({kind:'human',name:'a'.repeat(200)}).name.length,100);
});
// @wu-test type=behavior | scope=review-state.test | protects=cannot append duplicate notes or exceed note limit
test('cannot append duplicate notes or exceed note limit',()=>{
 assert.throws(()=>r.appendReview([note()],note()));assert.throws(()=>r.appendReview(Array.from({length:100},(_,i)=>({id:'n'+i})),note()));
 assert.equal(r.appendReview([],note()).length,1);
});
// @wu-test type=behavior | scope=review-state.test | protects=missing and concurrently edited comments fail instead of overwriting
test('missing and concurrently edited comments fail instead of overwriting',()=>{
 assert.throws(()=>r.changeReview([],'note-a',n=>n));assert.throws(()=>r.editReview(note(),'New',{expectedText:'Stale'}));
 assert.equal(r.editReview(note(),'New',{expectedText:note().text,at}).text,'New');
});
// @wu-test type=behavior | scope=review-state.test | protects=reply add/edit/delete preserves source, IDs and audit timestamps
test('reply add/edit/delete preserves source, IDs and audit timestamps',()=>{
 const added=r.addReviewReply(note(),'Reply',{author:{kind:'ai',name:'Bot'},at,replyId:'reply-a'});
 const edited=r.editReviewReply(added,'reply-a','New',{expectedText:'Reply',at});
 assert.equal(added.replies[0].text,'Reply');assert.equal(edited.replies[0].author.kind,'ai');assert.equal(edited.replies[0].editedBy.kind,'human');
 assert.equal(r.deleteReviewReply(edited,'reply-a').replies.length,0);
 assert.throws(()=>r.editReviewReply(added,'reply-a','New',{expectedText:'Stale'}));assert.throws(()=>r.deleteReviewReply(added,'missing'));
});
// @wu-test type=behavior | scope=review-state.test | protects=reply count and identity are bounded
test('reply count and identity are bounded',()=>{
 let n=note();for(let i=0;i<50;i++)n=r.addReviewReply(n,'a',{replyId:'r'+i});
 assert.throws(()=>r.addReviewReply(n,'a'));assert.throws(()=>r.addReviewReply({...note(),replies:[{id:'r',text:'a'}]},'b',{replyId:'r'}));
});
// @wu-test type=behavior | scope=review-state.test | protects=malformed reply histories are not silently truncated on write
test('malformed reply histories are not silently truncated on write',()=>{
 for(const replies of [null,{},[null],[{id:'x',text:'a'},{id:'x',text:'b'}],Array.from({length:51},(_,i)=>({id:'r'+i,text:'a'}))]){
  const n={...note(),replies};assert.throws(()=>r.addReviewReply(n,'New'));assert.deepEqual(n.replies,replies);
 }
});
// @wu-test type=behavior | scope=review-state.test | protects=resolve, reopen and agent requests have explicit non-dispatch semantics
test('resolve, reopen and agent requests have explicit non-dispatch semantics',()=>{
 const requested=r.requestReviewAgent(note(),at);assert.deepEqual(requested.agentRequest,{status:'requested',requestedAt:at});assert.throws(()=>r.requestReviewAgent(requested));
 const resolved=r.setReviewStatus(requested,'resolved',{at});assert.equal(resolved.agentRequest.status,'cancelled');assert.equal(resolved.resolvedBy.kind,'human');
 assert.throws(()=>r.addReviewReply(resolved,'a'));assert.throws(()=>r.requestReviewAgent(resolved));
 const reopened=r.setReviewStatus(resolved,'open',{at});assert.equal(reopened.resolvedAt,undefined);assert.equal(r.requestReviewAgent(reopened).agentRequest.status,'requested');
});
// @wu-test type=behavior | scope=review-state.test | protects=editing requested content makes the request stale
test('editing requested content makes the request stale',()=>{
 const requested=r.requestReviewAgent(note());assert.equal(r.editReview(requested,'New').agentRequest.status,'stale');
 const reply=r.addReviewReply(requested,'Reply',{replyId:'r'});assert.equal(reply.agentRequest.status,'stale');
 assert.equal(r.editReviewReply({...reply,agentRequest:{status:'requested'}},'r','Edited').agentRequest.status,'stale');
 assert.equal(r.deleteReviewReply({...reply,agentRequest:{status:'requested'}},'r').agentRequest.status,'stale');
});
// @wu-test type=behavior | scope=review-state.test | protects=context includes replies and sources, not only the root text
test('context includes replies and sources, not only the root text',()=>{
 const n=r.addReviewReply(note(),'Done',{author:{kind:'ai'},replyId:'r'});assert.equal(r.reviewContextText(n),'Check denominator\n\n[ai] Done');
});
// @wu-test type=behavior | scope=review-state.test | protects=IDs work without randomUUID on non-secure LAN origins
test('IDs work without randomUUID on non-secure LAN origins',()=>{
 const fallback={getRandomValues:bytes=>globalThis.crypto.getRandomValues(bytes)};
 const ids=Array.from({length:100},()=>r.reviewId('note',fallback));assert.equal(new Set(ids).size,100);
 assert.ok(ids.every(id=>/^note-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id)));
 assert.throws(()=>r.reviewId('note',{}));
});
