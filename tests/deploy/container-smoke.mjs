/**
 * Exercise a deployed image or an existing server with the real HTTP and MCP
 * protocols, then run its downloaded static Worker against its Parquet shards.
 *
 * bun tests/deploy/container-smoke.mjs --image charts-design:ci
 * bun tests/deploy/container-smoke.mjs --url http://127.0.0.1:8000 --token TOKEN
 */
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {mkdtempSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createServer} from 'node:net';
import {parseArgs} from 'node:util';
import {pathToFileURL} from 'node:url';
import {Mcp} from '../fixtures/mcp-client.mjs';
import {entries as zipEntries, entryBytes as unzipEntry} from '../../deploy/pages/publication-zip.mjs';

const PROJECT = 'smoke', BOARD = 'ops';

async function http(method, url, body, headers = {}, timeout = 60000) {
  const response = await fetch(url, {method, headers, body: body == null ? undefined : JSON.stringify(body), redirect: 'error',
    signal: AbortSignal.timeout(timeout)});
  return {status: response.status, headers: response.headers, raw: new Uint8Array(await response.arrayBuffer())};
}
const json = raw => JSON.parse(new TextDecoder().decode(raw));
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

async function waitHealthy(base, seconds = 90) {
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    try {
      const response = await http('GET', `${base}/health`, undefined, {}, 5000);
      if (response.status === 200 && json(response.raw).ok) return;
    } catch { /* The image can still be starting. */ }
    await delay(1000);
  }
  throw Error(`${base}/health did not become healthy within ${seconds}s`);
}

function downloadUrl(url, base) {
  const result = new URL(url), host = new URL(base);
  result.protocol = host.protocol; result.host = host.host;
  return result.href;
}

// @wu-test type=integration | scope=部署镜像 | protects=鉴权失效或无法保存或只读令牌可写或原生网页缺少完整数据
export async function runChecks(base, token) {
  await waitHealthy(base);
  const denied = await http('POST', `${base}/mcp`, {}, {'Content-Type': 'application/json'});
  assert.equal(denied.status, 401, '/mcp must reject an absent author token');
  console.log('ok  health and bearer enforcement');

  const client = new Mcp(base, token, PROJECT);
  await client.initialize();
  const names = new Set((await client.request('tools/list')).tools.map(tool => tool.name));
  for (const name of ['dashboard_submit', 'dashboard_get', 'dashboard_list', 'dashboard_export']) {
    assert(names.has(name), `Missing author tool: ${name}`);
  }
  for (const name of ['dashboard_export_open', 'dashboard_patch', 'dashboard_share']) {
    assert(!names.has(name), `Non-public tool was advertised: ${name}`);
  }
  console.log(`ok  MCP initialize (${client.protocol}) and ${names.size} tools`);

  const outside = await client.request('tools/call', {name: 'dashboard_list', arguments: {projectRoot: '/etc'}});
  assert(outside.isError, 'MCP accepted a path outside the workspace');
  const resource = await client.request('resources/read', {uri: 'charts://examples/operations-scorecard'});
  const operations = JSON.parse(resource.contents[0].text).operations;
  const submitted = await client.tool('dashboard_submit', {dashboardId: BOARD, createTitle: 'Smoke', operations});
  const revision = submitted.revision;
  assert.equal(submitted.checkpoint.revision, revision, 'Submission did not save its revision');
  const saved = await client.tool('dashboard_get', {dashboardId: BOARD});
  assert.equal(Object.keys(saved.document.manifest.components).length, 10, 'Authored dashboard is incomplete');
  console.log(`ok  authored ${BOARD} through dashboard_submit (revision ${revision})`);

  const author = {'Content-Type': 'application/json', Authorization: `Bearer ${token}`};
  const sharing = await http('POST', `${base}/api/v1/share`, {project: PROJECT, dashboardId: BOARD, access: 'view'}, author);
  assert.equal(sharing.status, 200, 'Creating a viewer link failed');
  const share = new URLSearchParams(new URL(json(sharing.raw).url).hash.slice(1)).get('token');
  assert(share, 'Viewer URL has no scoped token');
  const api = `${base}/api/v1/p/${PROJECT}/tools/`;
  const viewer = {'Content-Type': 'application/json', Authorization: `Bearer ${share}`};
  const viewed = await http('POST', `${api}dashboard_view`, {dashboardId: BOARD}, viewer);
  assert.equal(viewed.status, 200, 'Scoped viewer cannot read its dashboard');
  assert(Object.keys(json(viewed.raw).document.computed.components).length >= 9, 'Viewer lost computed components');
  const write = await http('POST', `${api}dashboard_patch`, {dashboardId: BOARD, expectedRevision: revision,
    operations: [{op: 'set_title', value: 'x'}]}, viewer);
  assert.equal(write.status, 403, 'Read-only viewer can write');
  const exported = (await client.tool('dashboard_export', {dashboardId: BOARD, format: 'json'})).export;
  const downloaded = await http('GET', downloadUrl(exported.downloadUrl, base));
  assert.equal(downloaded.status, 200, 'Signed document download failed');
  assert.equal(json(downloaded.raw).id, BOARD, 'Signed document download selected another dashboard');
  console.log('ok  scoped viewer API and signed download');

  const site = (await client.tool('dashboard_export_site', {dashboardId: BOARD})).export;
  const archive = await http('GET', downloadUrl(site.downloadUrl, base));
  assert.equal(archive.status, 200, 'Signed static site download failed');
  const expectedRows = Object.fromEntries(operations.filter(operation => operation.op === 'put_dataset')
    .map(operation => [operation.id, operation.rows]));
  await checkStaticSite(archive.raw, expectedRows, revision);
  console.log('ok  native Parquet export and downloaded Worker preserve all source rows');
}

// @wu-test type=integration | scope=容器独立网页数据 | protects=静默退回JSON或ZIP分片不能由随包Worker恢复
export async function checkStaticSite(raw, expectedRows, revision) {
  assert(raw.length <= 64 * 1024 * 1024, 'Static fixture archive exceeds 64 MiB');
  const entries = zipEntries(raw);
  const read = async name => {
    const entry = entries.get(name);
    assert(entry && entry.size <= 24 * 1024 * 1024, `Missing or oversized ZIP entry: ${name}`);
    return unzipEntry(raw, entry);
  };
  const manifest = json(await read('export-manifest.json'));
  assert.equal(manifest.dataFormat, 'parquet', 'Deployed image did not select native Parquet');
  assert.equal(manifest.revision, revision, 'Static export selected the wrong saved revision');
  const document = json(await read('document.json'));
  assert(Object.keys(document.staticFiles ?? {}).length, 'Static export has no datasets');
  const files = {};
  for (const [dataset, names] of Object.entries(document.staticFiles)) {
    assert(Object.hasOwn(expectedRows, dataset), `Unexpected exported dataset: ${dataset}`);
    for (const name of names) {
      assert(/^data\/[a-zA-Z0-9_-]+\.parquet$/.test(name), `Static export has an invalid Parquet path: ${name}`);
      files[name] = Buffer.from(await read(name)).toString('base64');
    }
  }
  const directory = mkdtempSync(path.join(tmpdir(), 'charts-site-smoke-'));
  try {
    const worker = path.join(directory, 'static-worker.mjs');
    writeFileSync(worker, await read('static-worker.js'));
    const script = `
const input = await Bun.stdin.json();
let receipt;
globalThis.self = {postMessage: value => {receipt = value;}};
globalThis.fetch = async url => {
  const name = new URL(url).pathname.slice('/site/'.length);
  if (!Object.hasOwn(input.files, name)) throw Error('Unexpected static dependency: ' + name);
  return new Response(Buffer.from(input.files[name], 'base64'));
};
await import(input.worker);
const restored = {};
for (const [dataset, names] of Object.entries(input.document.staticFiles)) {
  const document = {id:'smoke',revision:input.document.revision,manifest:{filters:[],
    datasets:input.document.manifest.datasets,components:{probe:{kind:'table',datasetId:dataset}}},
    snapshot:{datasets:{}},staticFiles:{[dataset]:names}};
  await self.onmessage({data:{id:1,type:'init',args:{document,base:'https://offline.example/site/'}}});
  if (receipt.error) throw Error(receipt.error);
  await self.onmessage({data:{id:2,type:'query',args:{detail:true,componentId:'probe',limit:100000}}});
  if (receipt.error) throw Error(receipt.error);
  restored[dataset] = receipt.result.rows;
}
process.stdout.write(JSON.stringify(restored));
`;
    const result = execFileSync(process.execPath, ['-e', script], {input: JSON.stringify({
      worker: pathToFileURL(worker).href, document, files}), encoding: 'utf8', timeout: 60000,
      maxBuffer: 64 * 1024 * 1024});
    const restored = JSON.parse(result);
    assert.deepEqual(Object.keys(restored).sort(), Object.keys(document.staticFiles).sort());
    for (const [dataset, rows] of Object.entries(restored)) {
      assert.deepEqual(rows, expectedRows[dataset], `Downloaded Worker changed dataset rows: ${dataset}`);
    }
  } finally { rmSync(directory, {recursive: true, force: true}); }
}

// @wu-test type=boundary | scope=Docker镜像内容 | protects=令牌配置或本地业务目录被带入运行镜像
function checkImageFiles(container) {
  const forbidden = ['deploy/charts.env', '.env', 'runtime-core/.env', 'runtime-ui/local.env',
    '.git', '.codex', '.aws', 'boards'];
  const found = execFileSync('docker', ['exec', container, 'sh', '-c',
    'for p do if [ -e "/app/$p" ]; then printf "%s\\n" "$p"; fi; done', 'private-input-probe', ...forbidden],
    {encoding: 'utf8'}).trim();
  assert.equal(found, '', `Runtime image contains private build inputs: ${found}`);
  console.log('ok  image excludes environment files and local workspaces');
}

async function freePort() {
  const server = createServer();
  await new Promise((resolve, reject) => {server.once('error', reject); server.listen(0, '127.0.0.1', resolve);});
  const port = server.address().port;
  await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  return port;
}

async function main() {
  const {values} = parseArgs({options: {image: {type: 'string'}, url: {type: 'string'}, token: {type: 'string'}}});
  assert(Boolean(values.image) !== Boolean(values.url), 'Specify exactly one of --image or --url');
  if (values.url) {
    assert(values.token, '--token is required with --url');
    await runChecks(values.url.replace(/\/$/, ''), values.token);
    return;
  }
  const token = randomBytes(32).toString('base64url'), port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  const container = execFileSync('docker', ['run', '-d', '-p', `127.0.0.1:${port}:8000`,
    '-e', `CHARTS_SERVER_TOKENS=${token}`, '-e', `CHARTS_PUBLIC_URL=${base}`, values.image], {encoding: 'utf8'}).trim();
  try {
    checkImageFiles(container);
    const user = execFileSync('docker', ['exec', container, 'id', '-u'], {encoding: 'utf8'}).trim();
    assert.notEqual(user, '0', 'Container runs as root');
    await runChecks(base, token);
    console.log(`ok  container runs as uid ${user}`);
  } catch (error) {
    try { console.error(execFileSync('docker', ['logs', container], {encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe']}).slice(-4000)); }
    catch (logs) { console.error(String(logs.stderr ?? logs.message).slice(-4000)); }
    throw error;
  } finally { execFileSync('docker', ['rm', '-f', container], {stdio: 'ignore'}); }
}

if (import.meta.main) await main();
