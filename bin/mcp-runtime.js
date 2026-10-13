// Keep the host transport open while the Python worker sleeps between calls.
const {spawn} = require('node:child_process');
const {createInterface} = require('node:readline');
const {pythonRuntime} = require('./python-runtime.js');

function runMcp(args) {
  const {python, env, isolated} = pythonRuntime();
  let child = null, initialization = null, initialized = null, booting = false;
  let closing = false;
  const queued = [], pending = new Set();
  function write(line, track = true) {
    const message = JSON.parse(line);
    if (track && 'id' in message && message.method) pending.add(message.id);
    child.stdin.write(line + '\n');
  }
  function flush() { while (queued.length) write(queued.shift()); }
  function start() {
    child = spawn(python, [...(isolated ? ['-S'] : []), '-m', 'dashboard_runtime', ...args],
      {env, stdio: ['pipe', 'pipe', 'inherit']});
    const worker = child;
    booting = Boolean(initialization);
    const output = createInterface({input: worker.stdout});
    output.on('line', line => {
      let message;
      try { message = JSON.parse(line); } catch { return; }
      if (booting && message.id === initialization.id) {
        if (message.error) { console.error('MCP worker initialization failed'); worker.kill(); return; }
        booting = false;
        write(JSON.stringify(initialized || {jsonrpc:'2.0',method:'notifications/initialized'}));
        flush();
        return;
      }
      if ('id' in message && !message.method) pending.delete(message.id);
      process.stdout.write(line + '\n');
    });
    worker.on('error', error => { console.error(error.message); process.exitCode = 1; input.close(); });
    worker.stdin.on('error', error => { if (error.code !== 'EPIPE') console.error(error.message); });
    worker.on('exit', () => {
      child = null;
      for (const id of pending) process.stdout.write(JSON.stringify({jsonrpc:'2.0',id,
        error:{code:-32603,message:'MCP worker stopped before responding; reload the document before retrying'}}) + '\n');
      pending.clear();
      if (closing) return;
      if (queued.length) { start(); if (!booting) flush(); }
    });
    if (booting) write(JSON.stringify(initialization), false);
  }
  const input = createInterface({input: process.stdin});
  input.on('line', line => {
    let message;
    try { message = JSON.parse(line); } catch { return; }
    if (message.method === 'initialize') initialization = message;
    if (message.method === 'notifications/initialized') initialized = message;
    queued.push(line);
    // First initialize must be delivered once; later workers replay it privately.
    if (!child) {
      const first = message.method === 'initialize';
      if (first) { const saved = initialization; initialization = null; start(); initialization = saved; }
      else start();
    }
    if (!booting) flush();
  });
  function close() { closing = true; input.close(); child?.stdin.end(); }
  input.on('close', () => { closing = true; child?.stdin.end(); });
  process.on('SIGTERM', () => { close(); child?.kill(); });
  process.on('SIGINT', () => { close(); child?.kill(); });
}
module.exports = {runMcp};
