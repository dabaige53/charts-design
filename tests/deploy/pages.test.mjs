import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import worker from "../../deploy/pages/worker.mjs";

const env = { ORIGIN_URL: "https://backend.example", ORIGIN_TOKEN: "origin-secret",
  ASSETS: { fetch: async () => new Response("static asset") } };

// @wu-test type=integration | scope=deploy/pages/build.mjs | protects=missing viewer assets in the deployable Pages bundle
test("build copies backend UI resources into the Pages bundle", async () => {
  const temporary = await mkdtemp(join(tmpdir(), "charts-pages-test-"));
  const source = process.env.PAGES_TEST_DIST || join(temporary, "dist");
  const output = join(temporary, "pages");
  const assets = ["app.js", "app.css", "static-worker.js"];
  try {
    if (!process.env.PAGES_TEST_DIST) {
      await mkdir(source);
      await writeFile(join(source, "build.json"), JSON.stringify({ id: "pages-test" }));
      await Promise.all(assets.map(name => writeFile(join(source, name), `fixture: ${name}`)));
    }
    execFileSync(process.execPath, ["deploy/pages/build.mjs", source, output]);
    for (const name of assets) {
      assert.deepEqual(await readFile(join(output, "assets", name)), await readFile(resolve(source, name)));
    }
    assert.match(await readFile(join(output, "_worker.js"), "utf8"), /ORIGIN_TOKEN/);
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
});

// @wu-test type=integration | scope=deploy/pages/worker.mjs | protects=viewer boot state being detached from deployed static resources
test("viewer keeps backend boot state and uses Pages assets", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response('<html><head><style>css</style></head><body><script>window.__chartsBoot={"projectRoot":"demo"}</script><script>application</script></body></html>', { headers: { "content-type": "text/html", "cache-control": "public" } });
  try {
    const response = await worker.fetch(new Request("https://pages.example/view/demo/board"), env);
    const html = await response.text();
    assert.match(html, /window\.__chartsBoot={"projectRoot":"demo"}/);
    assert.match(html, /href="\/assets\/app.css"/);
    assert.match(html, /src="\/assets\/app.js"/);
    assert.equal(response.headers.get("cache-control"), "private, no-store");
    assert.equal(await (await worker.fetch(new Request("https://pages.example/assets/app.js"), env)).text(), "static asset");
  } finally { globalThis.fetch = original; }
});

// @wu-test type=boundary | scope=deploy/pages/worker.mjs | protects=arbitrary proxy access and origin token spoofing
test("only known paths reach the configured HTTPS origin", async () => {
  const original = globalThis.fetch;
  let forwarded;
  globalThis.fetch = async request => { forwarded = request; return new Response("ok", { headers: { "CDN-Cache-Control": "public" } }); };
  try {
    for (const path of ["/mcp", "/admin", "/api/v1/p/a/tools/x%2fadmin", "/s/a%2fb/"]) {
      assert.equal((await worker.fetch(new Request("https://pages.example" + path), env)).status, 404);
    }
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
test("annotation and author publication routes reach the existing origin", async () => {
  const original = globalThis.fetch;
  const forwarded = [];
  globalThis.fetch = async request => { forwarded.push(request); return new Response("ok"); };
  const share = "a".repeat(32);
  try {
    for (const [method, path] of [
      ["POST", `/s/${share}/api/annotations`],
      ["GET", `/s/${share}/api/annotations?dashboardId=board`],
      ["GET", "/api/v1/p/demo/annotations/board"],
      ["POST", "/api/v1/p/demo/annotations/board"],
      ["POST", "/api/v1/publications"],
      ["GET", `/api/v1/publications/${share}`],
      ["DELETE", `/api/v1/publications/${share}`],
      ["GET", `/api/v1/p/demo/publications/${share}/feedback`],
    ]) {
      const response = await worker.fetch(new Request(`https://pages.example${path}`, { method }), env);
      assert.equal(response.status, 200, path);
      assert.equal(forwarded.at(-1).url, `https://backend.example${path}`);
    }
    assert.equal((await worker.fetch(new Request(`https://pages.example/s/${share}/api/edit`, { method: "POST" }), env)).status, 404);
    assert.equal((await worker.fetch(new Request("https://pages.example/api/v1/publications/not-a-share", { method: "DELETE" }), env)).status, 404);
  } finally { globalThis.fetch = original; }
});
