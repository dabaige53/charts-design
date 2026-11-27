import { sharing } from "./sharing.mjs";

const routes = [
  ["POST", /^\/api\/v1\/publications$/],
  ["GET", /^\/api\/v1\/publications\/[0-9a-f]{32}$/],
  ["DELETE", /^\/api\/v1\/publications\/[0-9a-f]{32}$/],
  ["GET", /^\/s\/[^/]+\/.*$/],
  ["POST", /^\/s\/[^/]+\/$/],
  ["POST", /^\/s\/[0-9a-f]{32}\/api\/annotations$/],
  ["GET", /^\/health$/],
];

export default {
  async fetch(request, env) {
    if (env.SHARE_DB) {
      if (request.method !== "HEAD") return sharing(request, env);
      const response = await sharing(new Request(request, { method: "GET" }), env);
      await response.body?.cancel();
      return new Response(null, { status: response.status, headers: response.headers });
    }
    const incoming = new URL(request.url);
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

    return new Response(response.body, { status: response.status, statusText: response.statusText, headers: resultHeaders });
  },
};
