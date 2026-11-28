#!/usr/bin/env bun
/** Synthetic end-to-end acceptance through the shipped native CLI, MCP and HTTP contracts. */
import assert from 'node:assert/strict';
import {spawn, spawnSync} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {createServer} from 'node:net';
import {tmpdir} from 'node:os';
import {dirname, join, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Database} from 'bun:sqlite';
import native from '../../bin/native-runtime.js';
import {Mcp} from '../fixtures/mcp-client.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const DIST = resolve(process.env.CHARTS_UI_DIST || join(ROOT, 'runtime-ui/dist'));
const env = {...process.env, CHARTS_STORAGE_BACKEND: 'local', CHARTS_PACKAGE_ROOT: ROOT, CHARTS_UI_DIST: DIST};
const resolvedRuntime = native.nativeRuntime();
const binary = {command: resolvedRuntime.binary, env: {...resolvedRuntime.env, ...env}};
const save = (path, value) => writeFileSync(path, JSON.stringify(value, null, 2) + '\n');
const read = path => JSON.parse(readFileSync(path, 'utf8'));
const round = number => Math.round(number * 1000) / 1000;
const wait = ms => new Promise(resolveWait => setTimeout(resolveWait, ms));
const headers = token => ({Authorization: `Bearer ${token}`});
const checked = value => {
  assert(!value.error && value.ok !== false, JSON.stringify(value.error ?? value));
  return value;
};
const fixedFilters = ['department', 'month'];
const components = ['total', 'rate', 'category', 'details'];
const fields = Object.fromEntries(Object.entries({rowId: 'number', department: 'string', month: 'date',
  agent: 'string', amount: 'number', numerator: 'number', denominator: 'number'}).map(([key, type]) => [key, {type}]));

function options(argv) {
  const args = {mode: argv.shift(), rows: 48, samples: 5};
  assert(['seed', 'verify', 'perf'].includes(args.mode), 'Choose seed, verify or perf');
  while (argv.length) {
    const flag = argv.shift();
    if (['--online', '--ci-server', '--keep-share'].includes(flag)) args[flag.slice(2)] = true;
    else if (['--rows', '--samples', '--output'].includes(flag)) {
      const value = argv.shift(); assert(value && !value.startsWith('--'), `${flag} needs a value`);
      args[flag.slice(2)] = flag === '--output' ? resolve(value) : Number(value);
    } else throw Error(`Unknown option: ${flag}`);
  }
  assert(Number.isSafeInteger(args.rows) && args.rows >= 48 && Number.isInteger(args.samples)
    && args.samples >= 1 && args.samples <= 30, 'Use at least 48 rows and 1–30 samples');
  assert(!args['keep-share'] || args.online, '--keep-share requires --online');
  assert(!args.online || (env.CHARTS_SHARE_SERVICE_URL && env.CHARTS_SHARE_SERVICE_TOKEN),
    '--online requires CHARTS_SHARE_SERVICE_URL and CHARTS_SHARE_SERVICE_TOKEN');
  assert(!env.CHARTS_TEST_MCP_URL || (env.CHARTS_TEST_MCP_TOKEN && env.CHARTS_TEST_MCP_PROJECT),
    'Remote MCP acceptance requires its URL, token and project');
  args.output ??= mkdtempSync(join(tmpdir(), 'charts-acceptance-'));
  return args;
}

function cli(root, args, input) {
  const result = spawnSync(binary.command, ['--project-root', join(root, 'project'), '--runtime-root', join(root, 'runtime'),
    ...(existsSync(join(root, 'sources.json')) ? ['--sources', join(root, 'sources.json')] : []), ...args],
  {cwd: ROOT, env: binary.env, input: input === undefined ? undefined : JSON.stringify(input),
    encoding: 'utf8', timeout: 240000, maxBuffer: 32 * 1024 * 1024});
  assert.equal(result.status, 0, result.error?.message ?? result.stderr);
  return checked(JSON.parse(result.stdout));
}
const call = (root, name, args = {}) => cli(root, ['call', name, '--json-file', '-'], args);
async function measured(action) {
  const start = performance.now(); const value = await action();
  return [value, round(performance.now() - start)];
}
function summary(samples) {
  const sorted = samples.toSorted((a, b) => a - b), middle = Math.floor(sorted.length / 2);
  return {medianMs: round(sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2),
    ...(sorted.length >= 20 ? {p95Ms: sorted[Math.ceil(sorted.length * .95) - 1]} : {}), samplesMs: samples};
}
function record(index) {
  return {rowId: index, department: `Department-${index % 4}`,
    month: `2026-${String(Math.floor(index / 4) % 12 + 1).padStart(2, '0')}-01`,
    agent: `Agent-${String(index % 97).padStart(2, '0')}`, amount: index % 101 + 1,
    numerator: index % 19 + 1, denominator: index % 23 + 20};
}
function operations(totals) {
  const metrics = {amount: {field: 'amount', aggregation: 'sum', label: 'Amount'},
    count: {aggregation: 'count', label: 'Records'},
    rate: {aggregation: 'ratio', numerator: 'numerator', denominator: 'denominator', label: 'Rate', format: 'percent', scale: 'fraction'}};
  const cards = {
    total: {kind: 'legacy', family: 'kpi', title: 'Amount', config: {type: 'mc02', label: 'Amount', value: '0', subVal: '0'},
      binding: {datasetId: 'facts', measures: {value: 'amount', subVal: 'count'}}},
    rate: {kind: 'kpi', title: 'Rate', datasetId: 'facts', measures: ['rate']},
    category: {kind: 'legacy', family: 'chart', title: 'Amount by department',
      config: {code: 'c01', unit: '', data: {categories: [0, 1, 2, 3].map(i => `Department-${i}`), values: totals.categories},
        presentation: {axisLabels: {x: 'Department', y: 'Amount'}, seriesLabels: ['Amount'], tooltipValueLabels: ['Amount'],
          units: ['units'], tableHeaders: ['Department', 'Amount']}},
      binding: {datasetId: 'facts', categoryField: 'department', categoryTarget: 'categories', measures: {values: 'amount'}}},
    details: {kind: 'table', title: 'Details', datasetId: 'facts'},
  };
  return [...Object.entries(metrics).map(([id, metric]) => ({op: 'put_metric', id,
    value: {...metric, datasetId: 'facts', definition: 'Independent integer acceptance fixture', unit: '', decimals: 2}})),
  ...Object.entries(cards).map(([id, value]) => ({op: 'put_component', id, value})),
  {op: 'set_filters', value: fixedFilters.map(id => ({id, field: id, label: id, op: 'in', values: [], componentIds: components}))}];
}

// @wu-test type=integration | scope=native authoring fixture | protects=initialization silently loses data or requires an interpreter
function seed(root, rows) {
  const path = join(root, 'fixture.json');
  if (existsSync(path)) {
    const fixture = read(path);
    assert.equal(fixture.rows, rows, 'Existing fixture has a different row count; choose a new --output');
    assert.equal(fixture.format, 2, 'Existing fixture has a different schema; choose a new --output');
    return fixture;
  }
  assert(!existsSync(join(root, 'project')), 'Existing project needs its original fixture.json; choose a new --output');
  mkdirSync(root, {recursive: true});
  const source = join(root, 'source.sqlite3'), db = new Database(source, {create: true});
  const totals = {amount: 0, numerator: 0, denominator: 0, categories: [0, 0, 0, 0]};
  try {
    db.exec('CREATE TABLE facts (rowId INTEGER, department TEXT, month TEXT, agent TEXT, amount INTEGER, numerator INTEGER, denominator INTEGER)');
    const insert = db.prepare('INSERT INTO facts VALUES (?,?,?,?,?,?,?)');
    db.transaction(() => {
      for (let i = 0; i < rows; i++) {
        const row = record(i); insert.run(...Object.values(row));
        for (const key of ['amount', 'numerator', 'denominator']) totals[key] += row[key];
        totals.categories[i % 4] += row.amount;
      }
    })();
  } finally { db.close(); }
  save(join(root, 'sources.json'), {benchmark: {engine: 'sqlite', path: source}});
  const board = 'acceptance';
  call(root, 'dashboard_create', {dashboardId: board, title: 'Synthetic acceptance'});
  const attached = call(root, 'dataset_attach', {dashboardId: board, expectedRevision: 1,
    datasetId: 'facts', connection: 'benchmark', table: 'facts', fields});
  assert.equal(attached.document.snapshot.datasetRefs.facts.rowCount, rows);
  const submitted = call(root, 'dashboard_submit', {dashboardId: board,
    expectedRevision: attached.document.revision, operations: operations(totals)});
  assert.equal(submitted.doctor.passed, true);
  const boards = [board];
  if (rows === 48) {
    for (const caseId of ['executive-dashboard', 'operations-scorecard', 'academic-report', 'filtered-report']) {
      const example = call(root, 'generation_examples', {caseId});
      const saved = call(root, 'dashboard_submit', {dashboardId: caseId, createTitle: caseId, operations: example.operations});
      assert.equal(saved.doctor.passed, true); boards.push(caseId);
    }
  }
  const fixture = {format: 2, rows, boards, board, dataset: 'facts', filters: fixedFilters,
    selection: {department: 'Department-1', month: '2026-01-01'}, filteredRows: Math.floor((rows - 2) / 48) + 1, totals};
  save(path, fixture); return fixture;
}

async function request(url, options = {}) {
  return fetch(url, {redirect: 'error', signal: AbortSignal.timeout(120000), ...options});
}
async function json(url, options) {
  const response = await request(url, options), text = await response.text();
  assert(response.ok, `${response.status}: ${text.slice(0, 1500)}`);
  return checked(JSON.parse(text));
}
async function download(url, extra = {}) {
  const start = performance.now(), response = await request(url, {headers: extra});
  assert(response.ok, `${url}: HTTP ${response.status}`);
  const headersMs = round(performance.now() - start), body = Buffer.from(await response.arrayBuffer());
  return [body, {headersMs, bodyMs: round(performance.now() - start),
    wireBytes: Number(response.headers.get('content-length')) || null, decodedBytes: body.length}];
}
const post = (url, token, value) => json(url, {method: 'POST', headers: {...headers(token), 'Content-Type': 'application/json'},
  body: JSON.stringify(value)});
async function stop(child) {
  if (child.exitCode !== null || child.signalCode) return;
  child.kill('SIGTERM');
  let timer;
  await Promise.race([new Promise(resolveExit => child.once('exit', resolveExit)),
    new Promise(resolveTimeout => { timer = setTimeout(resolveTimeout, 3000); })]).finally(() => clearTimeout(timer));
  if (child.exitCode === null && !child.signalCode) { child.kill('SIGKILL'); await new Promise(resolveExit => child.once('exit', resolveExit)); }
}
function launch(root, args) {
  const child = spawn(binary.command, args, {cwd: ROOT, env: binary.env, stdio: ['pipe', 'pipe', 'pipe']});
  let errors = '';
  child.stderr.on('data', value => { errors = (errors + value).slice(-8192); });
  child.on('error', error => { errors += error.message; });
  return {child, error: () => errors, root};
}
async function local(root, fixture) {
  const run = launch(root, ['--project-root', join(root, 'project'), '--runtime-root', join(root, 'local'),
    'serve', '--port', '0', '--idle-timeout', '300', '--dashboard', fixture.board]);
  try {
    const info = await new Promise((resolveLine, reject) => {
      let buffer = ''; const timer = setTimeout(() => reject(Error(`Native preview startup timed out: ${run.error()}`)), 15000);
      run.child.once('exit', code => { clearTimeout(timer); reject(Error(`Native preview exited ${code}: ${run.error()}`)); });
      run.child.stdout.on('data', chunk => {
        buffer += chunk;
        if (buffer.includes('\n')) { clearTimeout(timer); try { resolveLine(JSON.parse(buffer.split('\n')[0])); } catch (error) { reject(error); } }
      });
    });
    const url = new URL(info.url), token = new URLSearchParams(url.hash.slice(1)).get('token');
    assert(token, 'Native preview returned no author token');
    const links = await json(`${url.origin}/api/browser-links/${fixture.board}`, {headers: headers(token)});
    return {...run, origin: url.origin, token, links};
  } catch (error) { await stop(run.child); throw error; }
}
function selected(fixture, doc) {
  return doc.manifest.filters.map(entry => entry.id in fixture.selection ? {...entry, values: [fixture.selection[entry.id]]} : entry);
}
function pageCall(origin, api, token, board) {
  assert(api.startsWith('/') && !api.startsWith('//') && api.endsWith('/'));
  return (name, args = {}) => post(new URL(api + name, origin), token, {dashboardId: board, ...args});
}

// @wu-test type=performance | scope=preview data and filter options | protects=fast HTML hides slow or incorrect first data reads
async function authorPages(links, fixture, samples, expected, modes = ['edit', 'preview']) {
  const pages = {};
  for (const [name, key, readOnly] of [['edit', 'editUrl', false], ['preview', 'viewUrl', true]]) {
    if (!modes.includes(name)) continue;
    const url = new URL(links[key]), token = new URLSearchParams(url.hash.slice(1)).get('token');
    assert(token); const [html, shell] = await download(url);
    const bootText = html.toString().split('window.__chartsBoot=')[1]?.split(';</script>')[0];
    assert(bootText, 'Preview does not contain its boot contract');
    const boot = JSON.parse(bootText); assert.equal(boot.dashboardId, fixture.board); assert.equal(boot.readOnly, readOnly);
    const tool = pageCall(url.origin, boot.apiBase || '/api/tools/', token, fixture.board);
    const [opened, documentMs] = await measured(() => tool(readOnly ? 'dashboard_preview' : 'dashboard_get'));
    const doc = opened.document; assert.equal(doc.snapshot.datasetRefs[fixture.dataset].rowCount, fixture.rows);
    const context = {expectedRevision: doc.revision, dataVersion: doc.dataVersion};
    const [patch, firstComponentMs] = await measured(() => tool('dashboard_view', {...context,
      responseMode: 'patch', componentIds: components, tableStates: {details: {page: 1, pageSize: 10}}}));
    assert.equal(patch.id, fixture.board); assert.equal(patch.revision, doc.revision);
    assert.equal(patch.computed.components.total.value, fixture.totals.amount.toLocaleString('en-US'));
    assert.equal(patch.computed.components.rate.value,
      `${(fixture.totals.numerator / fixture.totals.denominator * 100).toFixed(2)}%`);
    assert.deepEqual(patch.computed.components.category.data.values, fixture.totals.categories);
    const options = {}, candidates = {};
    for (const filterId of fixture.filters) {
      const timings = [];
      for (let i = 0; i < samples; i++) {
        const [page, ms] = await measured(() => tool('dashboard_filter_options', {...context, filterId, limit: 100, offset: 0, search: ''}));
        timings.push(ms); candidates[filterId] = page.values;
      }
      options[filterId] = summary(timings);
    }
    const independent = {department: [0, 1, 2, 3].map(i => `Department-${i}`),
      month: Array.from({length: 12}, (_, i) => `2026-${String(i + 1).padStart(2, '0')}-01`)};
    assert.deepEqual(candidates, independent);
    expected ??= candidates; assert.deepEqual(candidates, expected);
    const base = {...context, componentId: 'details', limit: 10}, filters = selected(fixture, doc);
    const [first, firstRowsMs] = await measured(() => tool('component_data', base));
    assert.equal(first.totalRows, fixture.rows); assert.deepEqual(first.rows, Array.from({length: 10}, (_, i) => record(i)));
    const [filtered, applyFilterMs] = await measured(() => tool('component_data', {...base, filters}));
    assert.equal(filtered.totalRows, fixture.filteredRows);
    assert.deepEqual(filtered.rows, Array.from({length: Math.min(10, fixture.filteredRows)}, (_, i) => record(i * 48 + 1)));
    const [next, nextPageMs] = await measured(() => tool('component_data', {...base, filters, offset: 10}));
    assert.equal(next.rows.length, Math.min(10, Math.max(0, fixture.filteredRows - 10)));
    pages[name] = {html: shell, documentMs, firstComponentMs, options, firstRowsMs, applyFilterMs, nextPageMs,
      revision: doc.revision, firstResponseBytes: Buffer.byteLength(JSON.stringify(first))};
  }
  return [pages, expected];
}

export async function checkStdio(root, fixture) {
  const run = launch(root, ['--project-root', join(root, 'project'), 'mcp', '--idle-timeout', '30']);
  let sequence = 0, buffer = ''; const pending = new Map();
  run.child.stdout.on('data', chunk => {
    buffer += chunk;
    while (buffer.includes('\n')) {
      const end = buffer.indexOf('\n'), line = buffer.slice(0, end); buffer = buffer.slice(end + 1);
      if (!line.trim()) continue;
      try { const value = JSON.parse(line); pending.get(value.id)?.(value); } catch { /* startup failure is reported by the timeout */ }
    }
  });
  async function rpc(method, params = {}) {
    const id = ++sequence;
    const reply = new Promise((resolveReply, reject) => {
      const timeout = setTimeout(() => { pending.delete(id); reject(Error(`Stdio MCP ${method} timed out: ${run.error()}`)); }, 15000);
      pending.set(id, value => { clearTimeout(timeout); pending.delete(id); resolveReply(value); });
    });
    run.child.stdin.write(JSON.stringify({jsonrpc: '2.0', id, method, params}) + '\n');
    const response = await reply; assert(!response.error, JSON.stringify(response.error)); return response.result;
  }
  try {
    await rpc('initialize', {protocolVersion: '2025-06-18', capabilities: {}, clientInfo: {name: 'native-acceptance', version: '1'}});
    run.child.stdin.write(JSON.stringify({jsonrpc: '2.0', method: 'notifications/initialized'}) + '\n');
    const tools = (await rpc('tools/list')).tools.map(tool => tool.name);
    for (const name of ['dashboard_get', 'dashboard_list', 'dashboard_submit']) assert(tools.includes(name));
    const response = await rpc('tools/call', {name: 'dashboard_list', arguments: {projectRoot: join(root, 'project')}});
    assert(!response.isError);
    const value = response.structuredContent ?? JSON.parse(response.content.find(item => item.type === 'text').text);
    for (const board of fixture.boards) assert(value.dashboards.some(item => item.id === board));
    return true;
  } finally { run.child.stdin.end(); await stop(run.child); }
}
const note = () => ({id: 'note-' + randomUUID(), text: '验收批注：核对筛选后的明细行数。', componentId: 'details',
  createdAt: new Date().toISOString(), anchor: {scope: 'component', kind: 'area', quote: '', rect: {x: .1, y: .1, width: .2, height: .1}}});

// @wu-test type=integration | scope=versions and reader annotations | protects=drafts leak into previews or a reader gains design permissions
export async function checkVersions(root, fixture) {
  const run = await local(root, fixture);
  try {
    const viewer = new URLSearchParams(new URL(run.links.viewUrl).hash.slice(1)).get('token');
    const author = pageCall(run.origin, '/api/tools/', run.token, fixture.board);
    const view = pageCall(run.origin, '/api/tools/', viewer, fixture.board);
    const status = await author('dashboard_version_status'), saved = status.savedRevision;
    const draft = (await author('dashboard_patch', {expectedRevision: status.draftRevision,
      operations: [{op: 'set_title', value: 'Synthetic version acceptance'}]})).document.revision;
    assert.equal((await view('dashboard_get')).document.revision, saved);
    const denied = await request(`${run.origin}/api/tools/dashboard_patch`, {
      method: 'POST',
      headers: {...headers(viewer), 'Content-Type': 'application/json'},
      body: JSON.stringify({dashboardId: fixture.board, expectedRevision: draft,
        operations: [{op: 'set_title', value: 'Disallowed reader edit'}]}),
    });
    assert.equal(denied.status, 403);
    const endpoint = `${run.origin}/api/annotations/${fixture.board}`, annotation = note(), args = {revision: saved, append: annotation};
    const first = await post(endpoint, viewer, args); assert.equal(first.targetRevision, saved);
    await post(endpoint, viewer, args);
    const stored = await json(endpoint + `?revision=${saved}`, {headers: headers(run.token)});
    assert.equal(stored.annotations.filter(item => item.id === annotation.id).length, 1);
    assert.equal((await author('dashboard_version_status')).draftRevision, draft);
    await author('dashboard_submit', {expectedRevision: draft});
    assert.equal((await view('dashboard_get')).document.revision, draft);
    assert.equal((await author('dashboard_version_status')).publishedRevision, status.publishedRevision);
    await author('dashboard_version_publish', {expectedRevision: draft, revision: draft});
    assert.equal((await author('dashboard_version_status')).publishedRevision, draft);
    return {draftIsolation: true, idempotentAnnotations: true, savedRevision: draft, publishedRevision: draft};
  } finally { await stop(run.child); }
}

async function shareDownloads(base, extra = {}) {
  const [, html] = await download(base, extra), assets = {}; let document, worker;
  for (const name of ['app.js', 'app.css', 'document.json', 'static-worker.js']) {
    const [bytes, timing] = await download(new URL(name, base), extra); assets[name] = timing;
    if (name === 'document.json') document = JSON.parse(bytes);
    if (name === 'static-worker.js') worker = bytes;
  }
  return {document, worker, html, assets};
}
async function worker(fixture, document, expected, filters, samples, base, source, extra = {}) {
  const payload = {document, worker: source, base, headers: extra, fields: fixture.filters, samples, expected,
    table: 'details', rows: fixture.rows, filteredRows: fixture.filteredRows, filters};
  const remote = new URL(base).hostname !== '127.0.0.1';
  const keep = ['PATH', 'SYSTEMROOT', 'WINDIR', ...(remote ? ['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY',
    'http_proxy', 'https_proxy', 'no_proxy', 'NODE_EXTRA_CA_CERTS', 'SSL_CERT_FILE', 'SSL_CERT_DIR'] : [])];
  const processEnv = Object.fromEntries(keep.filter(key => process.env[key]).map(key => [key, process.env[key]]));
  processEnv.NODE_USE_ENV_PROXY = remote ? '1' : '0';
  const child = spawn('node', [join(ROOT, 'tests/acceptance/share-worker.mjs')], {env: processEnv, stdio: ['pipe', 'pipe', 'pipe']});
  let output = '', error = ''; child.stdout.on('data', data => { output += data; }); child.stderr.on('data', data => { error += data; });
  child.stdin.end(JSON.stringify(payload));
  const timer = setTimeout(() => child.kill('SIGKILL'), 240000);
  const code = await new Promise((resolveExit, reject) => { child.once('exit', resolveExit); child.once('error', reject); }).finally(() => clearTimeout(timer));
  assert.equal(code, 0, error.slice(-2000));
  const result = JSON.parse(output);
  result.options = Object.fromEntries(Object.entries(result.options).map(([field, samples]) => [field, {
    query: summary(samples.map(item => item.queryMs)), bootAndQuery: summary(samples.map(item => item.bootAndQueryMs)),
    dataRequests: Math.max(...samples.map(item => item.dataRequests))}]));
  return result;
}
async function freePort() {
  const socket = createServer(); await new Promise(resolveListen => socket.listen(0, '127.0.0.1', resolveListen));
  const port = socket.address().port; await new Promise(resolveClose => socket.close(resolveClose)); return port;
}
async function serverPages(url, token, project, fixture, samples, expected, loopback = false) {
  const endpoint = new URL(url);
  assert((loopback ? endpoint.protocol === 'http:' && endpoint.hostname === '127.0.0.1' : endpoint.protocol === 'https:')
    && !endpoint.username && !endpoint.password && !endpoint.hash && !endpoint.search, 'Invalid MCP endpoint');
  const mcp = new Mcp(endpoint.href.replace(/\/mcp\/?$/, ''), token, project); await mcp.initialize();
  const tools = (await mcp.request('tools/list')).tools.map(item => item.name);
  for (const name of ['dashboard_get', 'dashboard_list', 'dashboard_submit']) assert(tools.includes(name));
  const boards = (await mcp.tool('dashboard_list')).dashboards; assert(boards.some(item => item.id === fixture.board));
  const links = (await mcp.tool('dashboard_preview', {dashboardId: fixture.board})).browserLinks;
  for (const key of ['editUrl', 'viewUrl']) assert.equal(new URL(links[key]).origin, endpoint.origin);
  const [pages] = await authorPages(links, fixture, samples, expected);
  return {pages, discovery: {project, boards: boards.length}};
}
async function ciServer(root, fixture, samples, expected) {
  const port = await freePort(), origin = `http://127.0.0.1:${port}`, token = randomUUID();
  const run = launch(root, ['server', '--workspace', root, '--runtime-root', join(root, 'remote'),
    '--default-project', 'project', '--host', '127.0.0.1', '--port', String(port), '--public-url', origin, '--token', token]);
  try {
    let ready = false;
    for (let i = 0; i < 150; i++) {
      if (run.child.exitCode !== null) throw Error(run.error());
      try { if ((await request(origin + '/health', {signal: AbortSignal.timeout(500)})).ok) { ready = true; break; } } catch { /* process is starting */ }
      await wait(100);
    }
    assert(ready, `Author server startup timed out: ${run.error()}`);
    return await serverPages(origin + '/mcp', token, 'project', fixture, samples, expected, true);
  } finally { await stop(run.child); }
}

async function online(root, fixture, run, doc, expected, filters, args) {
  const tool = pageCall(run.origin, '/api/tools/', run.token, fixture.board), pending = join(root, 'share-pending.json');
  const publish = existsSync(pending) ? read(pending) : {revision: doc.revision, expiration: '7d', annotationMode: 'annotate', requestId: randomUUID()};
  assert.equal(publish.revision, doc.revision, 'Pending share belongs to another revision'); save(pending, publish);
  const [receipt, publishMs] = await measured(() => tool('dashboard_share_publish', publish));
  const share = receipt.share ?? receipt;
  const again = await tool('dashboard_share_publish', publish); assert.equal((again.share ?? again).shareId, share.shareId);
  const url = new URL(share.url); assert.equal(url.protocol, 'https:');
  const [accessPage, accessHtml] = await download(url); assert(accessPage.includes('accessKey'));
  let cookie;
  async function login(form) {
    const response = await request(url, {method: 'POST', redirect: 'manual', headers: {Origin: url.origin,
      'Content-Type': 'application/x-www-form-urlencoded'}, body: new URLSearchParams(form)});
    assert.equal(response.status, 303); cookie = response.headers.get('set-cookie')?.split(';')[0]; assert(cookie);
    await response.body?.cancel();
  }
  const [, loginMs] = await measured(() => login({accessKey: share.accessKey}));
  const loading = await shareDownloads(url.href, {Cookie: cookie});
  assert.equal(loading.document.publication.revision, doc.revision);
  for (const field of fixture.filters) assert.deepEqual(loading.document.staticFilterOptions[field], expected[field]);
  assert(loading.worker.equals(readFileSync(join(DIST, 'static-worker.js'))), 'Published Worker differs from the trusted build');
  const endpoint = new URL('api/annotations', url), annotation = {...note(), id: 'note-' + publish.requestId, createdAt: '2026-01-01T00:00:00Z'};
  const body = {dashboardId: fixture.board, revision: doc.revision, append: annotation, authorName: '验收脚本'};
  const append = () => json(endpoint, {method: 'POST', headers: {Cookie: cookie, Origin: url.origin, 'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const first = await append(); assert.deepEqual(await append(), first);
  assert.equal(first.annotation.context.designRevision, doc.revision);
  await login({accessKey: share.accessKey});
  const feedbackPath = endpoint.href + `?dashboardId=${fixture.board}&revision=${doc.revision}`;
  const readback = await json(feedbackPath, {headers: {Cookie: cookie}});
  assert.equal(readback.annotations.filter(item => item.id === annotation.id).length, 1);
  const measuredWorker = await worker(fixture, loading.document, expected, filters, args.samples,
    url.href, join(DIST, 'static-worker.js'), {Cookie: cookie});
  const feedback = await json(`${run.origin}/api/publications/${share.shareId}/feedback?dashboardId=${fixture.board}`, {headers: headers(run.token)});
  assert.equal(feedback.canAnnotate, false); assert.deepEqual(feedback.annotations, readback.annotations);
  const token = new URLSearchParams(new URL(feedback.url).hash.slice(1)).get('feedback'); assert(token);
  await login({feedbackToken: token});
  assert.equal((await request(endpoint, {method: 'POST', headers: {Cookie: cookie, Origin: url.origin,
    'Content-Type': 'application/json'}, body: JSON.stringify(body)})).status, 403);
  if (!args['keep-share']) { assert((await tool('dashboard_share_delete', {shareId: share.shareId})).revoked); rmSync(pending); }
  return {...measuredWorker, shareUrl: share.url, retained: Boolean(args['keep-share']), publishMs, accessHtml, loginMs,
    html: loading.html, assets: loading.assets, annotationId: annotation.id};
}

async function main() {
  const args = options(process.argv.slice(2)), root = args.output; mkdirSync(root, {recursive: true});
  const report = {runtime: 'Rust', rows: args.rows, samples: args.samples, checks: {}};
  const phase = name => { report.phase = name; save(join(root, 'report.json'), report); console.log(`[${name}] ${root}`); };
  try {
    phase('preflight');
    if (args.mode !== 'seed') {
      const node = spawnSync('node', ['-p', 'process.versions.node'], {encoding: 'utf8'});
      assert(node.status === 0 && Number(node.stdout.split('.')[0]) >= 24, 'Node.js 24 or later is required for the real share Worker');
      for (const file of ['build.json', 'app.js', 'app.css', 'static-worker.js']) assert(existsSync(join(DIST, file)), 'Run bun run ui:prepare first');
    }
    phase('seed');
    const [fixture, seedMs] = await measured(() => seed(root, args.rows)); Object.assign(report, {fixture, seedMs});
    if (args.mode === 'seed') { phase('complete'); return; }
    if (args.mode === 'verify') {
      phase('functional'); report.checks.localMcp = await checkStdio(root, fixture);
      const d1 = spawnSync(process.execPath, ['test', 'tests/deploy/pages-d1.test.mjs'], {cwd: ROOT, stdio: 'inherit'});
      assert.equal(d1.status, 0);
      const temporary = mkdtempSync(join(root, 'functional-'));
      try { Object.assign(report.checks, await checkVersions(temporary, seed(temporary, 48))); }
      finally { rmSync(temporary, {recursive: true, force: true}); }
    }
    phase('local-author'); report.localAuthor = {}; let expected;
    for (const mode of ['edit', 'preview']) {
      const run = await local(root, fixture);
      try {
        const [pages, options] = await authorPages(run.links, fixture, args.samples, expected, [mode]);
        Object.assign(report.localAuthor, pages); expected = options;
      } finally { await stop(run.child); }
    }
    const doc = call(root, 'dashboard_preview', {dashboardId: fixture.board}).document, filters = selected(fixture, doc);
    phase('parquet-export');
    const [exported, parquetExportMs] = await measured(() => call(root, 'dashboard_export_site', {dashboardId: fixture.board, dataFormat: 'parquet'}));
    const archive = exported.export; Object.assign(report, {parquetExportMs, zipBytes: archive.bytes});
    const directory = resolve(archive.directory);
    phase('local-share');
    const server = Bun.serve({hostname: '127.0.0.1', port: 0, fetch(request) {
      const path = resolve(directory, '.' + new URL(request.url).pathname.replace(/\/$/, '/index.html'));
      if (!path.startsWith(directory + sep)) return new Response('Forbidden', {status: 403});
      return new Response(Bun.file(path));
    }});
    try {
      const base = server.url.href, loading = await shareDownloads(base);
      const measuredWorker = await worker(fixture, loading.document, expected, filters, args.samples,
        base, join(directory, 'static-worker.js'));
      // Exercise the normal distributable site, including its bounded Parquet shards.
      // The independent single-file encoder is covered by runtime-core/tests/export.rs.
      const shards = loading.document.staticFiles[fixture.dataset];
      assert(shards.length > 0 && shards.every(file => file.endsWith('.parquet')));
      assert.equal(measuredWorker.firstRows.dataRequests, shards.length, 'Each required shard must be fetched exactly once');
      assert.equal(measuredWorker.applyFilter.dataRequests, 0, 'Filtering must reuse decoded data');
      assert.equal(measuredWorker.nextPage.dataRequests, 0, 'Paging must reuse decoded data');
      report.localShare = {parquetShards: shards.length, html: loading.html, assets: loading.assets, ...measuredWorker};
    } finally { await server.stop(true); }
    if (args['ci-server']) { phase('ci-author-server'); const remote = await ciServer(root, fixture, args.samples, expected);
      report.ciAuthorServer = remote.pages; report.checks.ciMcp = remote.discovery; }
    if (env.CHARTS_TEST_MCP_URL) { phase('remote-author-server'); const remote = await serverPages(env.CHARTS_TEST_MCP_URL,
      env.CHARTS_TEST_MCP_TOKEN, env.CHARTS_TEST_MCP_PROJECT, fixture, args.samples, expected);
    report.serverAuthor = remote.pages; report.checks.remoteMcp = remote.discovery; }
    if (args.online) { phase('online-share'); const run = await local(root, fixture);
      try { report.onlineShare = await online(root, fixture, run, doc, expected, filters, args); } finally { await stop(run.child); } }
    phase('complete');
  } catch (error) { report.error = error.message; save(join(root, 'report.json'), report); throw error; }
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main();
