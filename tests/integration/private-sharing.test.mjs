import {test} from 'bun:test';
import assert from 'node:assert/strict';
import {execFileSync, spawn} from 'node:child_process';
import {randomBytes, randomUUID} from 'node:crypto';
import {existsSync, mkdtempSync, readFileSync, readdirSync, rmSync} from 'node:fs';
import {createServer} from 'node:net';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {entries as zipEntries, entryBytes as unzipEntry} from '../../deploy/pages/publication-zip.mjs';

const root = fileURLToPath(new URL('../..', import.meta.url));
const binary = process.env.CHARTS_CORE_BIN;
const nativeTest = binary ? test : test.skip;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

function native(args, env, input) {
  return JSON.parse(execFileSync(binary, args, {env, input: input == null ? undefined : JSON.stringify(input),
    encoding: 'utf8', timeout: 30000, maxBuffer: 16 * 1024 * 1024}));
}
function cleanEnvironment() {
  const env = {...process.env};
  for (const key of Object.keys(env)) if (/^(CHARTS_|CLOUDBASE_|TENCENTCLOUD_|COS_|NEON_|PG|DATABASE_URL$)/.test(key)) delete env[key];
  return {...env, CHARTS_PACKAGE_ROOT: root, CHARTS_UI_DIST: process.env.CHARTS_UI_DIST || path.join(root, 'runtime-ui/dist')};
}
async function availablePort() {
  const server = createServer();
  await new Promise((resolve, reject) => {server.once('error', reject); server.listen(0, '127.0.0.1', resolve);});
  const port = server.address().port;
  await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  return port;
}
async function startServer(env) {
  const port = await availablePort(), base = `http://127.0.0.1:${port}`;
  const child = spawn(binary, ['server', '--host', '127.0.0.1', '--port', String(port)],
    {env, stdio: ['ignore', 'pipe', 'pipe']});
  let logs = '', closed = false;
  child.stdout.on('data', data => {logs += data;}); child.stderr.on('data', data => {logs += data;});
  const exited = new Promise(resolve => child.once('exit', code => {closed = true; resolve(code);}));
  const stop = async () => {
    if (closed) return;
    child.kill('SIGTERM');
    const timer = setTimeout(() => child.kill('SIGKILL'), 5000);
    await exited; clearTimeout(timer);
  };
  try {
    for (let attempts = 0; attempts < 100; attempts++) {
      if (closed) throw Error(`Sharing server exited: ${logs.slice(-2000)}`);
      try {
        const response = await fetch(`${base}/health`, {redirect: 'error', signal: AbortSignal.timeout(1000)});
        if (response.ok && (await response.json()).role === 'sharing') return {base, stop};
      } catch { /* Wait briefly for the listener. */ }
      await pause(50);
    }
    throw Error(`Sharing server did not become healthy: ${logs.slice(-2000)}`);
  } catch (error) {await stop(); throw error;}
}
function files(directory) {
  return existsSync(directory) ? readdirSync(directory, {withFileTypes: true}).flatMap(entry =>
    entry.isDirectory() ? files(path.join(directory, entry.name)) : [path.join(directory, entry.name)]) : [];
}
function note(revision, id = 'reader-note') {
  return {id, componentId: null, text: '请核对这项结果', createdAt: '2026-11-27T01:00:00Z',
    anchor: {scope: 'text', kind: 'element', quote: '报告段落', occurrence: 0, rect: {x: .1, y: .1, width: .2, height: .2}},
    view: {revision, filters: []}};
}

// @wu-test type=integration | scope=独立固定分享完整生命周期 | protects=作者删除后副本失效、重试重复发布、反馈可写或撤销清理后旧密钥复活
nativeTest('native fixed publication survives its author and enforces keys, feedback, retries and retirement', async () => {
  const directory = mkdtempSync(path.join(tmpdir(), 'charts-private-sharing-'));
  let server;
  try {
    const author = path.join(directory, 'author'), authorRuntime = path.join(directory, 'author-runtime');
    const authorEnv = {...cleanEnvironment(), CHARTS_STORAGE_BACKEND: 'local'};
    const call = (tool, args) => native(['--project-root', author, '--runtime-root', authorRuntime,
      'call', tool, '--json-file', '-'], authorEnv, args);
    const created = call('dashboard_submit', {dashboardId: 'frozen', createTitle: 'Frozen report', operations: [
      {op: 'put_source', id: 'fixture', value: {kind: 'fixture', name: 'Synthetic publication fixture'}},
      {op: 'put_dataset', id: 'sales', meta: {sourceId: 'fixture', fields: {region: {type: 'string'}, amount: {type: 'number'}}},
        rows: [{region: 'East', amount: 12}, {region: 'South', amount: 34}, {region: 'West', amount: null}]},
      {op: 'put_component', id: 'rows', value: {kind: 'table', title: 'Synthetic rows', datasetId: 'sales'}},
      {op: 'set_report_markdown', value: '# Frozen report\n\n报告段落：以下仅为合成数据。\n\n```chart\n{"componentId":"rows"}\n```\n'},
      {op: 'set_view_mode', value: 'report'},
    ]});
    assert.equal(created.ok, true);
    const revision = created.revision;
    call('dashboard_annotations_update', {dashboardId: 'frozen', append: note(revision, 'private-author-note')});
    const exported = call('dashboard_export_site', {dashboardId: 'frozen'}).export;
    const archive = new Uint8Array(readFileSync(exported.path)), entries = zipEntries(archive);
    const originalDocument = JSON.parse(new TextDecoder().decode(await unzipEntry(archive, entries.get('document.json'))));
    assert.equal(originalDocument.revision, revision);
    assert.equal(originalDocument.manifest.annotations, undefined);

    const token = randomBytes(32).toString('base64url'), source = randomUUID(), requestId = randomUUID();
    const runtime = path.join(directory, 'sharing-runtime');
    const sharingEnv = {...cleanEnvironment(), CHARTS_STORAGE_BACKEND: 'cloudflare', CHARTS_SERVER_ROLE: 'sharing',
      CHARTS_RUNTIME_ROOT: runtime, CHARTS_WORKSPACE: path.join(directory, 'sharing-workspace'),
      CHARTS_PUBLIC_URL: 'https://charts.example', CHARTS_SERVER_TOKENS: token,
      CHARTS_SERVER_SECRET: randomBytes(32).toString('hex'), CLOUDBASE_API_KEY: 'unused'};
    assert.deepEqual(native(['cleanup'], sharingEnv).failed, []);
    server = await startServer(sharingEnv);
    const http = (resource, options = {}) => fetch(new URL(resource, server.base),
      {...options, redirect: 'manual', signal: AbortSignal.timeout(15000)});
    const authorHeaders = {Authorization: `Bearer ${token}`};
    const publicationHeaders = {...authorHeaders, 'Content-Type': 'application/zip', 'X-Charts-Project': 'default',
      'X-Charts-Source': source, 'X-Charts-Request': requestId, 'X-Charts-Annotation-Mode': 'annotate', 'X-Charts-Expiration': '7d'};
    const publish = (headers = publicationHeaders) => http('/api/v1/publications', {method: 'POST', headers, body: archive});
    const response = await publish();
    assert.equal(response.status, 200, await response.clone().text());
    const receipt = await response.json();
    assert.match(receipt.accessKey, /^\d{8}$/);
    assert.equal(receipt.revision, revision);
    assert.deepEqual(await (await publish()).json(), receipt, 'Repeated import changed the identity or access key');
    const conflict = await publish({...publicationHeaders, 'X-Charts-Annotation-Mode': 'view'});
    assert.equal((await conflict.json()).error.code, 'REVISION_CONFLICT');
    const entry = `/s/${receipt.shareId}/`, owner = `/api/v1/publications/${receipt.shareId}?project=default&source=${source}&dashboardId=frozen`;
    const denied = await http(`${entry}document.json`);
    assert.equal((await denied.json()).error.code, 'INVALID_ACCESS_KEY');
    const wrongOwner = await http(owner.replace(source, randomUUID()), {headers: authorHeaders});
    assert.equal((await wrongOwner.json()).error.code, 'FORBIDDEN');
    const wrongOrigin = await http(entry, {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded', Origin: 'https://unrelated.example'},
      body: new URLSearchParams({accessKey: receipt.accessKey})});
    assert.equal(wrongOrigin.status, 403);
    const login = async form => {
      const result = await http(entry, {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded', Origin: sharingEnv.CHARTS_PUBLIC_URL},
        body: new URLSearchParams(form)});
      assert.equal(result.status, 303, await result.clone().text());
      const cookie = result.headers.get('set-cookie');
      assert(cookie && /; Secure(?:;|$)/.test(cookie) && /; HttpOnly(?:;|$)/.test(cookie) && /; SameSite=Strict(?:;|$)/.test(cookie));
      assert(cookie.includes(`Path=${entry};`));
      // The deployed cookie requires HTTPS; the loopback test sends it explicitly.
      return cookie.split(';')[0];
    };
    const cookie = await login({accessKey: receipt.accessKey});
    const read = async (resource, selected = cookie) => {
      const result = await http(resource, {headers: {Cookie: selected}});
      assert.equal(result.status, 200, await result.clone().text());
      return result;
    };
    const frozen = await (await read(`${entry}document.json`)).json();
    assert.equal(frozen.revision, revision);
    assert.equal(frozen.manifest.annotations, undefined);
    assert.equal(frozen.annotationAccess.canAnnotate, true);
    for (const names of Object.values(frozen.staticFiles)) for (const name of names) {
      const data = new Uint8Array(await (await read(`${entry}${name}`)).arrayBuffer());
      assert.deepEqual(data, await unzipEntry(archive, entries.get(name)), `Published bytes changed: ${name}`);
    }
    rmSync(author, {recursive: true, force: true}); rmSync(authorRuntime, {recursive: true, force: true});
    await server.stop(); server = await startServer(sharingEnv);
    assert.deepEqual(await (await publish()).json(), receipt, 'Restart or author removal changed the publication');
    assert.equal((await (await read(`${entry}document.json`)).json()).revision, revision);

    const annotation = {dashboardId: 'frozen', revision, authorName: 'Reader', append: note(revision)};
    const append = (body = annotation, selected = cookie) => http(`${entry}api/annotations`, {method: 'POST',
      headers: {'Content-Type': 'application/json', Cookie: selected, Origin: sharingEnv.CHARTS_PUBLIC_URL}, body: JSON.stringify(body)});
    const saved = await (await append()).json();
    assert.deepEqual(saved.annotation.author, {name: 'Reader', verified: false});
    assert.equal(saved.annotation.context.shareId, receipt.shareId);
    assert.equal(saved.annotation.context.designRevision, revision);
    assert.deepEqual(await (await append()).json(), saved, 'Annotation retry wrote a duplicate');
    const changed = await append({...annotation, append: {...annotation.append, text: 'Changed content'}});
    assert.equal((await changed.json()).error.code, 'ANNOTATION_CONFLICT');
    const notes = await (await read(`${entry}api/annotations?dashboardId=frozen`)).json();
    assert.equal(notes.count, 1);
    assert.equal(notes.annotations[0].id, 'reader-note');
    assert.equal((await (await read(`${entry}document.json`)).json()).revision, revision);

    const feedbackResponse = await http(owner, {headers: authorHeaders});
    assert.equal(feedbackResponse.status, 200);
    const feedback = await feedbackResponse.json();
    assert.equal(feedback.count, 1);
    assert.equal(feedback.canAnnotate, false);
    const feedbackToken = new URLSearchParams(new URL(feedback.url).hash.slice(1)).get('feedback');
    assert(feedbackToken);
    const feedbackCookie = await login({feedbackToken});
    const feedbackDocument = await (await read(`${entry}document.json`, feedbackCookie)).json();
    assert.equal(feedbackDocument.annotationAccess.canAnnotate, false);
    assert.equal(feedbackDocument.annotationsOpen, true);
    const forbidden = await append({...annotation, append: note(revision, 'feedback-write')}, feedbackCookie);
    assert.equal((await forbidden.json()).error.code, 'FORBIDDEN');

    const revoked = await http(owner, {method: 'DELETE', headers: authorHeaders});
    assert.equal((await revoked.json()).revoked, true);
    for (const resource of [`${entry}document.json`, `${entry}api/annotations?dashboardId=frozen`]) {
      const stale = await http(resource, {headers: {Cookie: cookie}});
      assert.equal((await stale.json()).error.code, 'SHARE_EXPIRED');
    }
    const cleaned = native(['cleanup'], sharingEnv);
    assert.deepEqual(cleaned.failed, []);
    assert.equal(cleaned.removed, 1);
    assert.deepEqual(files(path.join(runtime, 'private-shares/shares', receipt.shareId)), []);
    assert(existsSync(path.join(runtime, 'private-shares/retired', receipt.shareId)));
    assert.equal((await (await publish()).json()).error.code, 'SHARE_EXPIRED', 'Retired request resurrected the old key');
    const retired = await http(`${entry}document.json`, {headers: {Cookie: feedbackCookie}});
    assert.equal((await retired.json()).error.code, 'SHARE_EXPIRED');
  } finally {
    await server?.stop();
    rmSync(directory, {recursive: true, force: true});
  }
}, 60000);
