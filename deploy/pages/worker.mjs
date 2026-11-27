const routes = [
  ["GET", /^\/$/],
  ["GET", /^\/(?:view|edit)\/[^/]+\/[^/]+$/],
  ["POST", /^\/api\/v1\/p\/[^/]+\/tools\/[a-z_0-9]+$/],
  ["GET", /^\/api\/v1\/p\/[^/]+\/annotations\/[^/]+$/],
  ["POST", /^\/api\/v1\/p\/[^/]+\/annotations\/[^/]+$/],
  ["GET", /^\/api\/v1\/p\/[^/]+\/publications\/[0-9a-f]{32}\/feedback$/],
  ["POST", /^\/api\/v1\/publications$/],
  ["GET", /^\/api\/v1\/publications\/[0-9a-f]{32}$/],
  ["DELETE", /^\/api\/v1\/publications\/[0-9a-f]{32}$/],
  ["GET", /^\/api\/v1\/p\/[^/]+\/content\/[^/]+\/[^/]+\/[^/]+\/[^/]+$/],
  ["POST", /^\/api\/v1\/(?:catalog|share)$/],
  ["GET", /^\/files\/[^/]+$/],
  ["GET", /^\/s\/[^/]+\/.*$/],
  ["POST", /^\/s\/[^/]+\/$/],
  ["POST", /^\/s\/[0-9a-f]{32}\/api\/annotations$/],
  ["GET", /^\/health$/],
];

const assets = new Set(["/assets/app.js", "/assets/app.css", "/assets/static-worker.js"]);

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    if (assets.has(incoming.pathname) && ["GET", "HEAD"].includes(request.method)) {
      return env.ASSETS.fetch(request);
    }
    const method = request.method === "HEAD" ? "GET" : request.method;
    if (/%(?:2f|5c|00)/i.test(incoming.pathname) ||
        !routes.some(([allowed, path]) => allowed === method && path.test(incoming.pathname))) {
      return new Response("Not found", { status: 404, headers: { "Cache-Control": "no-store" } });
    }

    let origin;
    try {
      origin = new URL(env.ORIGIN_URL);
      if (origin.protocol !== "https:" || origin.username || origin.password ||
          origin.pathname !== "/" || origin.search || origin.hash || !env.ORIGIN_TOKEN ||
          /[\r\n]/.test(env.ORIGIN_TOKEN)) throw new Error("Invalid origin");
    } catch {
      return new Response("Origin is not configured", { status: 503, headers: { "Cache-Control": "no-store" } });
    }

    const headers = new Headers(request.headers);
    headers.set("X-Origin-Token", env.ORIGIN_TOKEN);
    headers.set("Accept-Encoding", "identity");
    const target = origin.origin + incoming.pathname + incoming.search;
    const response = await fetch(new Request(target, { method: request.method, headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body, redirect: "manual", duplex: "half" }));
    const resultHeaders = new Headers(response.headers);
    resultHeaders.set("Cache-Control", "private, no-store");
    resultHeaders.delete("CDN-Cache-Control");
    resultHeaders.delete("Cloudflare-CDN-Cache-Control");

    const viewer = incoming.pathname === "/" || /^\/(?:view|edit)\/[^/]+\/[^/]+$/.test(incoming.pathname);
    if (viewer && request.method === "GET" && response.ok &&
        response.headers.get("content-type")?.includes("text/html")) {
      const html = await response.text();
      const style = /<style>[\s\S]*?<\/style>/;
      const script = /(<script>window\.__chartsBoot=[\s\S]*?<\/script>)<script>[\s\S]*?<\/script><\/body><\/html>$/;
      if (!style.test(html) || !script.test(html) || !html.includes("window.__chartsBoot=")) {
        return new Response("Unsupported viewer response", { status: 502, headers: { "Cache-Control": "no-store" } });
      }
      resultHeaders.delete("Content-Length");
      resultHeaders.delete("Content-Encoding");
      resultHeaders.delete("ETag");
      return new Response(html.replace(style, '<link rel="stylesheet" href="/assets/app.css">')
        .replace(script, '$1<script src="/assets/app.js"></script></body></html>'),
      { status: response.status, headers: resultHeaders });
    }
    return new Response(response.body, { status: response.status, statusText: response.statusText, headers: resultHeaders });
  },
};
