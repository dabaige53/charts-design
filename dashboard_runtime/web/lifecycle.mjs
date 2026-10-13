// Background and closed previews must stop renewing the local process lifetime.
export function whileVisible(callback, interval, doc=document, win=window){
  let timer=null,closed=false;
  const stop=()=>{if(timer!==null)win.clearInterval(timer);timer=null;};
  const resume=()=>{stop();if(!closed&&doc.visibilityState==='visible'){callback();timer=win.setInterval(callback,interval);}};
  const hide=()=>{closed=true;stop();};
  const show=()=>{closed=false;resume();};
  doc.addEventListener('visibilitychange',resume);
  win.addEventListener('pagehide',hide);
  win.addEventListener('pageshow',show);
  resume();
  return ()=>{stop();doc.removeEventListener('visibilitychange',resume);win.removeEventListener('pagehide',hide);win.removeEventListener('pageshow',show);};
}
