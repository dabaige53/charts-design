import { test } from "bun:test";
import { Database } from "bun:sqlite";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import worker from "../../deploy/pages/worker.mjs";

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
  return execFileSync("python3", ["-c", `
import sys, json, zipfile
from io import BytesIO
doc = dict(schemaVersion=2, id='sample', revision=2,
           manifest=dict(title='Schedule', components={'total': {'kind':'kpi'}}, annotations=['private']),
           staticFiles={'sales':['data/sales-0.parquet']},
           staticFilterOptions={'month':['2026-07','2026-08']}, browserLinks=['private'])
out = BytesIO()
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
    archive.writestr('document.json',json.dumps(doc))
    archive.writestr('export-manifest.json',json.dumps(dict(dashboardId='sample',revision=2)))
    archive.writestr('data/sales-0.parquet',b'PAR1 fixture bytes')
    archive.writestr('app.js',b'not the trusted application')
sys.stdout.buffer.write(out.getvalue())
`]);
}

// @wu-test type=integration | scope=Cloudflare Pages + D1 固定分享 | protects=同请求重复发布、筛选候选项丢失、匿名读取数据和越权批注
test("publishes a fixed copy, serves trusted assets, and persists authorized annotations", async () => {
  const { sqlite, db } = d1();
  const env = { SHARE_DB: db, CHARTS_SHARE_SERVICE_TOKEN: token, CHARTS_SHARE_SIGNING_SECRET: "test-cookie-signing-secret-at-least-32-characters",
    ASSETS: { fetch: request => new URL(request.url).pathname === "/runtime/app.js" ? new Response("trusted app") : Response.json({ id: "test-runtime" }) } };
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
  const login = (form, site = origin) => send(page, { method: "POST", body: new URLSearchParams(form), headers: { Origin: site } });
  assert.equal((await login({ accessKey: share.accessKey }, "https://other.example")).status, 403);
  const accepted = await login({ accessKey: share.accessKey });
  assert.equal(accepted.status, 303);
  const cookie = accepted.headers.get("set-cookie").split(";")[0];
  const reader = { Cookie: cookie };
  const document = await (await send(page + "document.json", { headers: reader })).json();
  assert.deepEqual(document.staticFilterOptions.month, ["2026-07", "2026-08"]);
  assert.equal(document.browserLinks, undefined);
  assert.equal(document.manifest.annotations, undefined);
  assert.equal(await (await send(page + "app.js", { headers: reader })).text(), "trusted app");
  assert.equal(await (await send(page + "data/sales-0.parquet", { headers: reader })).text(), "PAR1 fixture bytes");
  const note = { id: "note", text: "Check", createdAt: "2026-11-27", componentId: "total", anchor: { scope: "component", kind: "element" } };
  const annotate = (input = note, revision = 2, visitor = reader) => send(page + "api/annotations", {
    method: "POST", headers: { ...visitor, "Content-Type": "application/json", Origin: origin },
    body: JSON.stringify({ dashboardId: "sample", revision, append: input, authorName: "Reader" }),
  });
  assert.equal((await annotate(note, 1)).status, 409);
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
  assert.equal((await send(path, { method: "DELETE", headers: managed })).status, 200);
  assert.equal((await send(page + "document.json", { headers: reader })).status, 410);
  assert.equal((await publish()).status, 410);
  assert.equal(sqlite.query("SELECT count(*) AS n FROM publication_chunks").get().n, 0);
  sqlite.close();
});
