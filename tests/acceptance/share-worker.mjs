import { Worker } from "node:worker_threads";
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const input = JSON.parse(readFileSync(0, "utf8"));
const script = readFileSync(input.worker, "utf8");
const bridge = `
const { parentPort, workerData } = require("node:worker_threads");
const fetchAsset = globalThis.fetch;
const fetched = [];
globalThis.fetch = async (url, options) => {
  const target = new URL(url);
  const origin = new URL(workerData.base);
  if (target.origin !== origin.origin || !target.pathname.startsWith(origin.pathname)) throw Error("Unexpected data URL");
  const start = performance.now();
  const response = await fetchAsset(target, { ...options, redirect: "error" });
  fetched.push({ headersMs: performance.now() - start, bytes: Number(response.headers.get("content-length")) });
  return response;
};
globalThis.self={postMessage:value=>{
  const requests = fetched.splice(0);
  parentPort.postMessage({...value, dataRequests:requests.length, dataBytes:requests.reduce((sum,item)=>sum+item.bytes,0),
    slowestDataHeadersMs: Math.max(0, ...requests.map(item=>item.headersMs))});
}};
parentPort.on("message", data=>self.onmessage({data}));
`;

function open() {
  const worker = new Worker(bridge + script, { eval: true,
    workerData: { base: input.base } });
  let sequence = 0;
  const call = (type, args) => new Promise((resolveCall, reject) => {
    const error = reason => { worker.off("message", reply); reject(reason); };
    const reply = message => {
      worker.off("error", error);
      if (message.error) reject(Error(message.error));
      else resolveCall(message);
    };
    worker.once("message", reply);
    worker.once("error", error);
    worker.postMessage({ id: ++sequence, type, args });
  });
  return { worker, call };
}

const result = { options: {} };
const init = client => client.call("init", { document: input.document, base: input.base, headers: input.headers });
for (const field of input.fields) {
  result.options[field] = [];
  for (let i = 0; i < input.samples; i++) {
    const start = performance.now();
    const client = open();
    try {
      await init(client);
      const ready = performance.now();
      const page = await client.call("query", { filterId: field, filters: [], limit: 100 });
      const end = performance.now();
      assert.equal(page.dataRequests, 0);
      assert.deepEqual(page.result.values, input.expected[field]);
      result.options[field].push({ queryMs: end - ready, bootAndQueryMs: end - start, dataRequests: page.dataRequests });
    } finally { await client.worker.terminate(); }
  }
}
const client = open();
try {
  await init(client);
  const request = { detail: true, componentId: input.table, limit: 10 };
  const start = performance.now();
  const first = await client.call("query", request);
  result.firstRows = { ms: performance.now() - start, dataRequests: first.dataRequests, dataBytes: first.dataBytes,
    slowestDataHeadersMs: first.slowestDataHeadersMs, rows: first.result.totalRows };
  assert.equal(first.result.totalRows, input.rows);
  assert.equal(first.result.rows.length, Math.min(input.rows, 10));
  const apply = performance.now();
  const filtered = await client.call("query", { ...request, filters: input.filters });
  result.applyFilter = { ms: performance.now() - apply, dataRequests: filtered.dataRequests, rows: filtered.result.totalRows };
  assert.equal(filtered.result.totalRows, input.filteredRows);
  const nextPage = await client.call("query", { ...request, offset: 10, filters: input.filters });
  assert.equal(nextPage.result.rows.length, Math.min(Math.max(input.filteredRows - 10, 0), 10));
  result.nextPage = { dataRequests: nextPage.dataRequests, rows: nextPage.result.rows.length };
} finally { await client.worker.terminate(); }
console.log(JSON.stringify(result));
