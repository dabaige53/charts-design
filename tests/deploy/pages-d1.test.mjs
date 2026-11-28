import { test } from "bun:test";
import { Database } from "bun:sqlite";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { deflateRawSync } from "node:zlib";
import worker from "../../deploy/pages/worker.mjs";
import { assetManifest, bundlePath, pagesAsset, releasePath } from "../../deploy/pages/deployment.mjs";

const origin = "https://shares.example";
const owner = "3eafce6c-040a-4609-b51f-416c882a97c1";
const requestId = "35a5c0a5-43a2-46af-9009-e447c70a22e4";
const token = "test-publication-credential-at-least-32-characters";
const d1 = () => {
  const sqlite = new Database(":memory:");
  sqlite.run(readFileSync(new URL("../../deploy/pages/schema.sql", import.meta.url), "utf8"));
  const db = {
    prepare: sql => ({
      bind: (...values) => ({
        run: () => sqlite.query(sql).run(...values.map(toSql)),
        first: () => sqlite.query(sql).get(...values.map(toSql)),
        all: () => ({ results: sqlite.query(sql).all(...values.map(toSql)) }),
      }),
      first: () => sqlite.query(sql).get(),
    }),
    batch: statements => sqlite.transaction(() => statements.map(statement => statement.run()))(),
  };
  return { sqlite, db };
};
const toSql = value => value instanceof ArrayBuffer ? new Uint8Array(value) : value;

function bundle() {
  const document = {schemaVersion: 2, id: 'sample', revision: 2,
    manifest: {title: 'Schedule', components: {total: {kind: 'kpi'}}, annotations: ['private']},
    staticFiles: {sales: ['data/sales-0.parquet']},
    staticFilterOptions: {month: ['2026-07', '2026-08']}, browserLinks: ['private']};
  const files = {'document.json': JSON.stringify(document),
    'export-manifest.json': JSON.stringify({dashboardId: 'sample', revision: 2}),
    'data/sales-0.parquet': 'PAR1 fixture bytes', 'app.js': 'not the trusted application'};
  const body = [], directory = []; let offset = 0;
  for (const [name, value] of Object.entries(files)) {
    const path = Buffer.from(name), raw = Buffer.from(value), compressed = deflateRawSync(raw);
    let crc = 0xffffffff;
    for (const byte of raw) { crc ^= byte; for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0); }
    crc = (crc ^ 0xffffffff) >>> 0;
    const local = Buffer.alloc(30); local.writeUInt32LE(0x04034b50); local.writeUInt16LE(20, 4);
    local.writeUInt16LE(8, 8); local.writeUInt32LE(crc, 14); local.writeUInt32LE(compressed.length, 18);
    local.writeUInt32LE(raw.length, 22); local.writeUInt16LE(path.length, 26);
    const central = Buffer.alloc(46); central.writeUInt32LE(0x02014b50); central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6); central.writeUInt16LE(8, 10); central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(compressed.length, 20); central.writeUInt32LE(raw.length, 24);
    central.writeUInt16LE(path.length, 28); central.writeUInt32LE(offset, 42);
    body.push(local, path, compressed); directory.push(central, path); offset += local.length + path.length + compressed.length;
  }
  const central = Buffer.concat(directory), end = Buffer.alloc(22); end.writeUInt32LE(0x06054b50);
  end.writeUInt16LE(directory.length / 2, 8); end.writeUInt16LE(directory.length / 2, 10);
  end.writeUInt32LE(central.length, 12); end.writeUInt32LE(offset, 16);
  return Buffer.concat([...body, central, end]);
}

// @wu-test type=integration | scope=Cloudflare Pages + D1 固定分享 | protects=重复发布、公开缓存分享数据、引用错误的应用版本或越权批注
test("publishes a fixed copy, serves trusted assets, and persists authorized annotations", async () => {
  const { sqlite, db } = d1();
  const webId = "a".repeat(16);
  const app = `/runtime/${webId}/app.js`;
  const env = { SHARE_DB: db, CHARTS_SHARE_SERVICE_TOKEN: token, CHARTS_SHARE_SIGNING_SECRET: "test-cookie-signing-secret-at-least-32-characters",
    ASSETS: { fetch: request => new URL(request.url).pathname.endsWith("/app.js") ? new Response("trusted app") : Response.json({ id: "test-runtime", webId }) } };
  const send = (path, args) => worker.fetch(new Request(origin + path, args), env);
  const headers = { "Authorization": "Bearer " + token, "Content-Type": "application/zip",
    "X-Charts-Source": owner, "X-Charts-Project": "project", "X-Charts-Request": requestId, "X-Charts-Annotation-Mode": "annotate" };
  const bytes = bundle();
  const publish = (extra = {}) => send("/api/v1/publications", { method: "POST", headers: { ...headers, ...extra }, body: bytes });
  assert.equal((await send("/mcp", { method: "POST" })).status, 404);
  assert.deepEqual(await (await send("/health")).json(), { ok: true, role: "sharing", storage: "d1", uiBuildId: "test-runtime" });
  assert.equal((await publish({ Authorization: "Bearer unauthorized" })).status, 401);
  const created = await publish();
  assert.equal(created.status, 200, await created.clone().text());
  const share = await created.json();
  assert.deepEqual(await (await publish()).json(), share);
  assert.equal((await publish({ "X-Charts-Expiration": "30d" })).status, 409);
  assert.equal(sqlite.query("SELECT count(*) AS n FROM publications").get().n, 1);
  const page = "/s/" + share.shareId + "/";
  assert.equal((await send(page + "data/sales-0.parquet")).status, 401);
  const shared = await send(app);
  assert.equal(await shared.text(), "trusted app");
  assert.equal(shared.headers.get("cache-control"), "public, max-age=31536000, immutable");
  assert.equal((await send(app.replace(webId, "b".repeat(16)))).status, 404);
  const login = (form, site = origin) => send(page, { method: "POST", body: new URLSearchParams(form), headers: { Origin: site } });
  assert.equal((await login({ accessKey: share.accessKey }, "https://other.example")).status, 403);
  const accepted = await login({ accessKey: share.accessKey });
  assert.equal(accepted.status, 303);
  const cookie = accepted.headers.get("set-cookie").split(";")[0];
  const reader = { Cookie: cookie };
  assert((await (await send(page, { headers: reader })).text()).includes(app));
  const content = await send(page + "document.json", { headers: reader });
  assert.equal(content.headers.get("cache-control"), "private, no-store");
  const document = await content.json();
  assert.deepEqual(document.staticFilterOptions.month, ["2026-07", "2026-08"]);
  assert.equal(document.browserLinks, undefined);
  assert.equal(document.manifest.annotations, undefined);
  assert.equal(await (await send(page + "app.js", { headers: reader })).text(), "trusted app");
  assert.equal(await (await send(page + "data/sales-0.parquet", { headers: reader })).text(), "PAR1 fixture bytes");
  const note = { id: "note", text: "Check", createdAt: "2026-11-27", componentId: "total",
    anchor: { scope: "component", kind: "element", quote: "Total" } };
  const annotate = (input = note, revision = 2, visitor = reader) => send(page + "api/annotations", {
    method: "POST", headers: { ...visitor, "Content-Type": "application/json", Origin: origin },
    body: JSON.stringify({ dashboardId: "sample", revision, append: input, authorName: "Reader" }),
  });
  assert.equal((await annotate(note, 1)).status, 409);
  assert.equal((await annotate({ ...note, anchor: { scope: "component", kind: "element", quote: "  " } })).status, 400);
  assert.equal((await annotate({ ...note, anchor: { scope: "component", kind: "area", quote: "Total" } })).status, 400);
  const saved = await annotate();
  assert.equal(saved.status, 200, await saved.clone().text());
  assert.deepEqual(await (await annotate()).json(), await saved.json());
  assert.equal((await annotate({ ...note, text: "Changed" })).status, 409);
  const path = "/api/v1/publications/" + share.shareId + "?source=" + owner + "&project=project&dashboardId=sample";
  const managed = { Authorization: headers.Authorization };
  assert.equal((await send(path.replace("project=project", "project=other"), { headers: managed })).status, 403);
  const feedback = await (await send(path, { headers: managed })).json();
  assert.equal(feedback.annotations.length, 1);
  const feedbackToken = new URLSearchParams(new URL(feedback.url).hash.slice(1)).get("feedback");
  const feedbackSession = await login({ feedbackToken });
  assert.equal(feedbackSession.status, 303);
  assert.equal((await annotate(note, 2, { Cookie: feedbackSession.headers.get("set-cookie").split(";")[0] })).status, 403);
  const deleted = await send(path, { method: "DELETE", headers: managed });
  assert.equal(deleted.status, 200);
  assert.equal((await deleted.json()).cleanupState, "complete");
  assert.equal((await send(page + "document.json", { headers: reader })).status, 410);
  assert.equal((await publish()).status, 410);
  assert.equal(sqlite.query("SELECT count(*) AS n FROM publication_chunks").get().n, 0);
  sqlite.close();
});

// @wu-test type=integration | scope=Pages生产快照发布与访问 | protects=回执丢失重复部署、有效旧分享消失、越权访问或撤销时误报资源已清理
test("deploys a new snapshot without losing earlier links or writing their data to D1", async () => {
  const { sqlite, db } = d1();
  const encode = new TextEncoder();
  const script = pagesAsset(bundlePath, encode.encode("Worker bundle"));
  const release = JSON.stringify(assetManifest([script]));
  const currentRelease = pagesAsset(releasePath, encode.encode(release));
  let current = { id: "runtime", latest_stage: { status: "success" },
    deployment_trigger: { metadata: { commit_message: "charts-runtime-" + currentRelease.key } } };
  let deployed = {};
  let deployCount = 0;
  const uploaded = new Map([[script.key, script.value]]);
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (location, options) => {
    const { pathname } = new URL(location);
    let value;
    if (pathname.endsWith("/upload-token")) value = { jwt: "asset-token" };
    else if (pathname.endsWith("/check-missing")) {
      value = JSON.parse(options.body).hashes.filter(hash => !uploaded.has(hash));
    } else if (pathname.endsWith("/assets/upload")) {
      for (const entry of JSON.parse(options.body)) uploaded.set(entry.key, entry.value);
    } else if (pathname.endsWith("/upsert-hashes")) value = null;
    else if (pathname.endsWith("/deployments") && options.method === "POST") {
      const form = options.body;
      deployed = JSON.parse(form.get("manifest"));
      assert.ok(Object.values(deployed).every(hash => uploaded.has(hash)));
      assert.deepEqual(JSON.parse(await form.get("_routes.json").text()).include, ["/*"]);
      current = { id: "deployment-" + ++deployCount, latest_stage: { status: "success" },
        deployment_trigger: { metadata: { commit_message: form.get("commit_message") } } };
      if (deployCount === 1) throw new TypeError("Simulated missing response after activation");
      value = current;
    } else if (pathname.endsWith("/deployments")) value = current ? [current] : [];
    else if (pathname.endsWith("/projects/charts-design")) {
      value = { production_branch: "main", deployment_configs: { production: { fail_open: false } },
        canonical_deployment: current, latest_deployment: current };
    } else throw Error("Unexpected Cloudflare API path");
    return Response.json({ success: true, result: value });
  };
  try {
    const env = { SHARE_DB: db, CHARTS_SHARE_SERVICE_TOKEN: token,
      CHARTS_SHARE_SIGNING_SECRET: "test-cookie-signing-secret-at-least-32-characters",
      CHARTS_PAGES_ACCOUNT: "a".repeat(32), CHARTS_PAGES_PROJECT: "charts-design", CHARTS_PAGES_BRANCH: "main",
      CHARTS_PAGES_DEPLOY_TOKEN: "pages-write-token",
      ASSETS: { fetch: request => {
        const path = new URL(request.url).pathname;
        if (path === releasePath) return new Response(release);
        if (path === bundlePath) return new Response("Worker bundle");
        const asset = uploaded.get(deployed[path]);
        return asset ? new Response(Uint8Array.from(atob(asset), c => c.charCodeAt(0))) : new Response(null, { status: 404 });
      } } };
    const send = (path, args) => worker.fetch(new Request(origin + path, args), env);
    const body = bundle();
    const publish = (id, expiration) => send("/api/v1/publications", { method: "POST", body, headers: {
      Authorization: "Bearer " + token, "Content-Type": "application/zip", "X-Charts-Source": owner,
      "X-Charts-Project": "project", "X-Charts-Request": id, "X-Charts-Expiration": expiration, "X-Charts-Annotation-Mode": "annotate",
    } });
    assert.equal((await publish(requestId, "never")).status, 503);
    const confirmed = await publish(requestId, "never");
    assert.equal(confirmed.status, 200, await confirmed.clone().text());
    const first = await confirmed.json();
    assert.equal(first.expiresAt, null);
    assert.equal(deployCount, 1);
    const next = await publish(crypto.randomUUID(), "7d");
    assert.equal(next.status, 200, await next.clone().text());
    assert.notEqual((await next.json()).shareId, first.shareId);
    assert.equal(deployCount, 2);
    const base = "/s/" + first.shareId + "/";
    const rawPath = "/snapshots/" + first.shareId + "/data/sales-0.parquet";
    assert.ok(deployed[rawPath]);
    assert.equal((await send(rawPath)).status, 404);
    assert.equal((await send(base + "data/sales-0.parquet")).status, 401);
    const session = await send(base, { method: "POST", headers: { Origin: origin },
      body: new URLSearchParams({ accessKey: first.accessKey }) });
    assert.equal(session.status, 303);
    const Cookie = session.headers.get("set-cookie").split(";")[0];
    const page = await send(base + "document.json", { headers: { Cookie } });
    assert.equal((await page.json()).publication.shareId, first.shareId);
    assert.equal(await (await send(base + "data/sales-0.parquet", { headers: { Cookie } })).text(), "PAR1 fixture bytes");
    const annotation = await send(base + "api/annotations", { method: "POST",
      headers: { Cookie, Origin: origin, "Content-Type": "application/json" },
      body: JSON.stringify({ revision: 2, append: { id: "snapshot-note", text: "Saved", createdAt: "2026-11-27",
        componentId: "total", anchor: { scope: "component", kind: "area", rect: { x: 0, y: 0, width: 0.5, height: 0.5 } } } }) });
    assert.equal(annotation.status, 200, await annotation.clone().text());
    assert.equal(sqlite.query("SELECT count(*) AS n FROM annotations").get().n, 1);
    assert.equal(sqlite.query("SELECT count(*) AS n FROM publication_chunks").get().n, 0);
    assert.equal(sqlite.query("SELECT count(*) AS n FROM publications WHERE document IS NOT NULL").get().n, 0);
    const managed = "/api/v1/publications/" + first.shareId + "?source=" + owner + "&project=project";
    const revoke = () => send(managed, { method: "DELETE", headers: { Authorization: "Bearer " + token } });
    const revoked = await revoke();
    assert.equal(revoked.status, 200);
    assert.deepEqual(await revoked.json(), { shareId: first.shareId, revoked: true, cleanupState: "pending", cleanupExecutor: "pages" });
    assert.equal((await (await revoke()).json()).cleanupState, "pending");
    assert.equal((await send(base + "data/sales-0.parquet", { headers: { Cookie } })).status, 410);
    assert.equal((await publish(requestId, "never")).status, 410);
    const latest = await publish(crypto.randomUUID(), "7d");
    assert.equal(latest.status, 200, await latest.clone().text());
    assert.equal(deployed[rawPath], undefined);
    assert.deepEqual(await (await revoke()).json(), { shareId: first.shareId, revoked: true, cleanupState: "complete", cleanupExecutor: "pages" });
  } finally {
    globalThis.fetch = realFetch;
    sqlite.close();
  }
});
