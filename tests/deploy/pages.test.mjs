import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import worker from "../../deploy/pages/worker.mjs";

const env = { ORIGIN_URL: "https://backend.example", ORIGIN_TOKEN: "origin-secret" };

// @wu-test type=integration | scope=deploy/pages/build.mjs | protects=Pages 包仍依赖作者 UI 构建或绕过分享代理
test("build packages the share proxy independently from the author UI", async () => {
  const temporary = await mkdtemp(join(tmpdir(), "charts-pages-test-"));
  const output = join(temporary, "pages");
  try {
    execFileSync(process.execPath, ["deploy/pages/build.mjs", output]);
    assert.deepEqual((await readdir(output)).sort(), ["_routes.json", "_worker.js"]);
    assert.deepEqual(JSON.parse(await readFile(join(output, "_routes.json"), "utf8")),
      { version: 1, include: ["/*"], exclude: [] });
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
});

// @wu-test type=boundary | scope=deploy/pages/worker.mjs | protects=作者入口仍暴露在 Pages 或代理接受伪造的源站令牌
test("only known paths reach the configured HTTPS origin", async () => {
  const original = globalThis.fetch;
  let forwarded;
  globalThis.fetch = async request => { forwarded = request; return new Response("ok", { headers: { "CDN-Cache-Control": "public" } }); };
  try {
    const denied = [
      ["GET", "/"], ["POST", "/mcp"], ["POST", "/unified/mcp"],
      ["GET", "/edit/demo/board"], ["GET", "/view/demo/board"], ["GET", "/assets/app.js"],
      ["POST", "/api/v1/p/demo/tools/dashboard_get"], ["GET", "/api/v1/p/demo/annotations/board"],
      ["GET", "/api/v1/p/demo/publications/" + "a".repeat(32) + "/feedback"], ["GET", "/s/a%2fb/"],
    ];
    for (const [method, path] of denied) {
      assert.equal((await worker.fetch(new Request("https://pages.example" + path, { method }), env)).status, 404, path);
    }
    assert.equal(forwarded, undefined);
    assert.equal((await worker.fetch(new Request("https://pages.example/health"), { ...env, ORIGIN_URL: "http://backend.example" })).status, 503);
    const request = new Request("https://pages.example/s/abc/?signature=a%2Bb", {
      method: "POST", body: "accessKey=12345678",
      headers: { Origin: "https://pages.example", Cookie: "charts-share-abc=value",
        Authorization: "Bearer signed-link", "X-Origin-Token": "spoofed" },
    });
    const response = await worker.fetch(request, env);
    assert.equal(forwarded.url, "https://backend.example/s/abc/?signature=a%2Bb");
    assert.equal(forwarded.headers.get("origin"), "https://pages.example");
    assert.equal(forwarded.headers.get("cookie"), "charts-share-abc=value");
    assert.equal(forwarded.headers.get("authorization"), "Bearer signed-link");
    assert.equal(forwarded.headers.get("x-origin-token"), "origin-secret");
    assert.equal(await forwarded.text(), "accessKey=12345678");
    assert.equal(forwarded.redirect, "manual");
    assert.equal(response.headers.get("cache-control"), "private, no-store");
    assert.equal(response.headers.get("cdn-cache-control"), null);
  } finally { globalThis.fetch = original; }
});

// @wu-test type=behavior | scope=deploy/pages/worker.mjs | protects=lost share session cookies and redirects
test("share redirects and cookies are returned without following redirects", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(null, { status: 303,
    headers: { Location: "/s/abc/", "Set-Cookie": "charts-share-abc=secret; Path=/s/abc/; Secure; HttpOnly" } });
  try {
    const response = await worker.fetch(new Request("https://pages.example/s/abc/", { method: "POST", body: "key" }), env);
    assert.equal(response.status, 303);
    assert.equal(response.headers.get("location"), "/s/abc/");
    assert.match(response.headers.get("set-cookie"), /charts-share-abc=secret/);
  } finally { globalThis.fetch = original; }
});

// @wu-test type=boundary | scope=Pages publication annotation gateway | protects=批注和本机发布被静态代理拦截或意外开放任意分享写接口
test("reader annotations and publication transfer reach the sharing origin", async () => {
  const original = globalThis.fetch;
  const forwarded = [];
  globalThis.fetch = async request => { forwarded.push(request); return new Response("ok"); };
  const share = "a".repeat(32);
  try {
    for (const [method, path] of [
      ["POST", `/s/${share}/api/annotations`],
      ["GET", `/s/${share}/api/annotations?dashboardId=board`],
      ["POST", "/api/v1/publications"],
      ["GET", `/api/v1/publications/${share}`],
      ["DELETE", `/api/v1/publications/${share}`],
    ]) {
      const response = await worker.fetch(new Request(`https://pages.example${path}`, { method }), env);
      assert.equal(response.status, 200, path);
      assert.equal(forwarded.at(-1).url, `https://backend.example${path}`);
    }
    assert.equal((await worker.fetch(new Request(`https://pages.example/s/${share}/api/edit`, { method: "POST" }), env)).status, 404);
    assert.equal((await worker.fetch(new Request("https://pages.example/api/v1/publications/not-a-share", { method: "DELETE" }), env)).status, 404);
  } finally { globalThis.fetch = original; }
});
