import { boundedBody, check, CHUNK_SIZE, inflated, MAX_ARCHIVE, publicationBundle, ShareError } from "./publication-zip.mjs";
import { activeSnapshotAssets, assetManifest, bundlePath, jsonAsset, pagesAsset, pagesClient, releasePath,
  withPagesDeployment } from "./deployment.mjs";

const identifier = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const seconds = () => Math.floor(Date.now() / 1000);
const encode = new TextEncoder();
const json = (data, options = {}) => Response.json(data, options);
const secure = {
  "Cache-Control": "private, no-store",
  "Referrer-Policy": "same-origin",
  "X-Content-Type-Options": "nosniff",
  "Content-Security-Policy": "frame-ancestors 'self'; object-src 'none'; base-uri 'none'",
};
const ui = new Set(["app.js", "app.css", "static-worker.js"]);
const sharedUi = /^\/runtime\/([0-9a-f]{16})\/(app\.(?:js|css)|static-worker\.js|fonts\/[0-9a-f]{16}\.(?:woff2?|ttf))$/;
const name = "访客";
const author = { name, verified: false };
const life = { "7d": 604800, "30d": 2592000, never: null };
const pagePath = id => "/s/" + id + "/";
const snapshotPath = (id, name) => "/snapshots/" + id + "/" + name;
const b64 = bytes => btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const fromB64 = value => Uint8Array.from(atob(value.replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
const hex = bytes => Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
const digest = async input => hex(new Uint8Array(await crypto.subtle.digest("SHA-256", input)));
const hmac = async (key, value) => new Uint8Array(await crypto.subtle.sign("HMAC", key, encode.encode(value)));
const sign = async (key, payload) => {
  const value = b64(encode.encode(JSON.stringify(payload)));
  return value + "." + b64(await hmac(key, "session:" + value));
};
async function verify(key, token, kind, id) {
  const match = /^([A-Za-z0-9_-]{1,512})\.([A-Za-z0-9_-]{43})$/.exec(token ?? "");
  if (!match) return null;
  try {
    const [, value, signature] = match;
    if (!await crypto.subtle.verify("HMAC", key, fromB64(signature), encode.encode("session:" + value))) return null;
    const payload = JSON.parse(new TextDecoder().decode(fromB64(value)));
    return payload.kind === kind && payload.id === id && payload.exp > seconds() ? payload : null;
  } catch {
    return null;
  }
}

async function storage(env) {
  check(typeof env.CHARTS_SHARE_SERVICE_TOKEN === "string" && env.CHARTS_SHARE_SERVICE_TOKEN.length >= 32 &&
    typeof env.CHARTS_SHARE_SIGNING_SECRET === "string" && env.CHARTS_SHARE_SIGNING_SECRET.length >= 32,
    503, "CLOUD_SHARE_NOT_CONFIGURED", "Configure the publication and signing secrets");
  const key = await crypto.subtle.importKey("raw", encode.encode(env.CHARTS_SHARE_SIGNING_SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
  return { db: env.SHARE_DB, key, env };
}

async function ownerOf(request, url, env, context) {
  const supplied = request.headers.get("Authorization")?.match(/^Bearer ([^\s]{1,512})$/)?.[1];
  check(supplied && await crypto.subtle.verify("HMAC", context.key, await hmac(context.key, "authorize:" + supplied),
    encode.encode("authorize:" + env.CHARTS_SHARE_SERVICE_TOKEN)), 401, "UNAUTHORIZED", "Invalid publication credential");
  const posting = request.method === "POST";
  const project = posting ? request.headers.get("x-charts-project") : url.searchParams.get("project");
  const source = posting ? request.headers.get("x-charts-source") : url.searchParams.get("source");
  check(project && identifier.test(project) && source && uuid.test(source), 400, "INVALID_ARGUMENT", "Invalid publication source");
  return digest(encode.encode(project + ":" + source));
}

async function accessKey(key, id) {
  const bytes = await hmac(key, "access:" + id);
  return String(new DataView(bytes.buffer).getUint32(0) % 100000000).padStart(8, "0");
}
function live(share) {
  check(share && !share.revoked && (share.expires_at === null || share.expires_at > seconds()),
    410, "SHARE_UNAVAILABLE", "分享不存在、已过期或已撤销");
  return share;
}
async function publication(db, id, columns = "") {
  return db.prepare("SELECT p.id,owner,fingerprint,board,revision,mode,expires_at,revoked," +
    "s.title AS snapshot_title,s.deployment_id" + columns +
    " FROM publications p LEFT JOIN pages_snapshots s ON s.share_id=p.id WHERE p.id=?").bind(id).first();
}
function ready(share) {
  live(share);
  check(share.snapshot_title === null || share.deployment_id, 503, "PAGES_DEPLOY_PENDING", "此分享正在发布，请稍后重试");
  return share;
}
const publicIdentity = share => ({ shareId: share.id, dashboardId: share.board, revision: share.revision });
const bodyType = (request, mime) => check(request.headers.get("Content-Type")?.split(";")[0].trim() === mime,
  415, "CONTENT_TYPE", "Use " + mime);

async function cleanExpired(db) {
  // Keep the identity as a tombstone so a late retry cannot reopen a retired share.
  const due = "SELECT id FROM publications WHERE document IS NOT NULL AND expires_at<=? ORDER BY expires_at LIMIT 20";
  const now = seconds();
  await db.batch([
    db.prepare("DELETE FROM publication_chunks WHERE share_id IN (" + due + ")").bind(now),
    db.prepare("DELETE FROM annotations WHERE share_id IN (" + due + ")").bind(now),
    db.prepare("UPDATE publications SET document=NULL,files=NULL WHERE id IN (" + due + ")").bind(now),
    db.prepare("DELETE FROM annotations WHERE share_id IN (SELECT id FROM publications WHERE expires_at<=? AND id IN (SELECT share_id FROM pages_snapshots))").bind(now),
    db.prepare("UPDATE pages_snapshots SET assets='{}',title='' WHERE assets<>'{}' AND share_id IN (SELECT id FROM publications WHERE expires_at<=?)").bind(now),
    db.prepare("DELETE FROM access_attempts WHERE window<?").bind(Math.floor(now / 600) - 1),
  ]);
}

async function storedAsset(env, url, path) {
  const response = await env.ASSETS.fetch(new Request(new URL(path, url)));
  check(response.ok, 503, "PAGES_ASSET_UNAVAILABLE", "A Pages snapshot asset is unavailable");
  return response;
}

async function publishSnapshot(db, env, url, fields, archive) {
  const { id, owner, fingerprint, mode, expiration } = fields;
  return withPagesDeployment(db, async assertLock => {
    const prior = await publication(db, id);
    if (prior) {
      check(prior.fingerprint === fingerprint, 409, "IDEMPOTENCY_CONFLICT", "This request already identifies a different publication");
      live(prior);
      if (prior.deployment_id || prior.snapshot_title === null) return prior;
    }
    const bundle = await publicationBundle(archive, { pages: true });
    const { document } = bundle;
    const assets = [jsonAsset(snapshotPath(id, "document.json"), document)];
    for await (const [name, bytes] of bundle.assets()) assets.push(pagesAsset(snapshotPath(id, name), bytes));
    const snapshot = assetManifest(assets);
    if (!prior) {
      const expiry = life[expiration] === null ? null : seconds() + life[expiration];
      await db.batch([
        db.prepare("INSERT INTO publications(id,owner,fingerprint,board,revision,mode,expires_at) VALUES(?,?,?,?,?,?,?)")
          .bind(id, owner, fingerprint, document.id, document.revision, mode, expiry),
        db.prepare("INSERT INTO pages_snapshots(share_id,assets,title) VALUES(?,?,?)")
          .bind(id, JSON.stringify(snapshot), document.manifest.title),
      ]);
    }
    const release = await storedAsset(env, url, releasePath);
    const releaseAsset = pagesAsset(releasePath, new Uint8Array(await release.arrayBuffer()));
    const runtime = JSON.parse(atob(releaseAsset.value));
    const worker = new Uint8Array(await (await storedAsset(env, url, bundlePath)).arrayBuffer());
    const pages = pagesClient({ account: env.CHARTS_PAGES_ACCOUNT, project: env.CHARTS_PAGES_PROJECT,
      branch: env.CHARTS_PAGES_BRANCH, token: env.CHARTS_PAGES_DEPLOY_TOKEN });
    const manifest = { ...runtime, [releasePath]: releaseAsset.key, ...await activeSnapshotAssets(db, seconds()), ...snapshot };
    const deployment = await pages.deploy({ assets: [...assets, releaseAsset], manifest, worker,
      marker: "charts-share-" + id + "-" + releaseAsset.key, requiredRelease: releaseAsset.key,
      assertLock, restore: async path => pagesAsset(path, new Uint8Array(await (await storedAsset(env, url, path)).arrayBuffer())) });
    await assertLock();
    await db.prepare("UPDATE pages_snapshots SET deployment_id=? WHERE share_id=?").bind(deployment, id).run();
    return publication(db, id);
  });
}

async function publish(request, url, owner, { db, key, env }) {
  bodyType(request, "application/zip");
  const requestId = request.headers.get("x-charts-request");
  const mode = request.headers.get("x-charts-annotation-mode") ?? "view";
  const expiration = request.headers.get("x-charts-expiration") ?? "7d";
  check(requestId && uuid.test(requestId) && ["view", "annotate"].includes(mode) && Object.hasOwn(life, expiration),
    400, "INVALID_ARGUMENT", "Invalid publication parameters");
  const id = hex((await hmac(key, "publication:" + owner + ":" + requestId)).subarray(0, 16));
  const archive = await boundedBody(request, MAX_ARCHIVE);
  const fingerprint = JSON.stringify([await digest(archive), mode, expiration]);
  let share = await publication(db, id, ",document");
  if (env.CHARTS_PAGES_PROJECT && (!share || share.snapshot_title !== null && !share.deployment_id)) {
    share = await publishSnapshot(db, env, url, { id, owner, fingerprint, mode, expiration }, archive);
    await cleanExpired(db);
  } else if (!share) {
    const { document, files, packed } = await publicationBundle(archive);
    const expiry = life[expiration] === null ? null : seconds() + life[expiration];
    const statements = [db.prepare("INSERT OR IGNORE INTO publications(id,owner,fingerprint,board,revision,mode,expires_at,document,files) VALUES(?,?,?,?,?,?,?,?,?)")
      .bind(id, owner, fingerprint, document.id, document.revision, mode, expiry, JSON.stringify(document), JSON.stringify(files))];
    for (let offset = 0; offset < packed.length; offset += CHUNK_SIZE) {
      const bytes = packed.slice(offset, offset + CHUNK_SIZE);
      statements.push(db.prepare("INSERT OR IGNORE INTO publication_chunks(share_id,part,contents) SELECT id,?,? FROM publications WHERE id=? AND fingerprint=? AND revoked=0 AND document IS NOT NULL")
        .bind(offset / CHUNK_SIZE, bytes.buffer, id, fingerprint));
    }
    await db.batch(statements);
    share = await publication(db, id, ",document");
    await cleanExpired(db);
  }
  check(share?.fingerprint === fingerprint, 409, "IDEMPOTENCY_CONFLICT", "This request already identifies a different publication");
  ready(share);
  const access = await accessKey(key, id);
  const location = url.origin + pagePath(id);
  const title = share.snapshot_title ?? JSON.parse(share.document).manifest.title;
  return json({ ...publicIdentity(share), url: location, accessUrl: location + "#key=" + access, accessKey: access,
    annotationMode: share.mode, expiresAt: share.expires_at,
    pages: [{ id: share.board, title, path: "document.json", revision: share.revision }] });
}

async function noteList(db, share) {
  const { results } = await db.prepare("SELECT payload FROM annotations WHERE share_id=? ORDER BY received_at,id").bind(share.id).all();
  const annotations = results.map(entry => JSON.parse(entry.payload));
  return { ...publicIdentity(share), annotations, count: annotations.length, independentSave: true,
    canAnnotate: share.mode === "annotate", canManageAnnotations: false, author };
}

async function manage(request, url, id, owner, { db, key, env }) {
  const share = await publication(db, id);
  check(share?.owner === owner, 403, "FORBIDDEN", "Share belongs to another author project");
  if (request.method === "DELETE") {
    await db.batch([
      db.prepare("UPDATE publications SET revoked=1,document=NULL,files=NULL WHERE id=?").bind(id),
      db.prepare("DELETE FROM publication_chunks WHERE share_id=?").bind(id),
      db.prepare("UPDATE pages_snapshots SET assets='{}',title='' WHERE share_id=?").bind(id),
      db.prepare("DELETE FROM annotations WHERE share_id=?").bind(id),
      db.prepare("DELETE FROM access_attempts WHERE share_id=?").bind(id),
    ]);
    if (share.snapshot_title === null) return json({ shareId: id, revoked: true, cleanupState: "complete", cleanupExecutor: "d1" });
    // The snapshot tombstone preserves its storage type across repeated revokes.
    const asset = await env.ASSETS.fetch(new Request(new URL(snapshotPath(id, "document.json"), url), { method: "HEAD" }));
    await asset.body?.cancel();
    return json({ shareId: id, revoked: true, cleanupState: asset.status === 404 ? "complete" : "pending",
      cleanupExecutor: "pages" });
  }
  ready(share);
  check(!url.searchParams.get("dashboardId") || url.searchParams.get("dashboardId") === share.board,
    403, "FORBIDDEN", "Dashboard does not belong to this share");
  const expiresAt = Math.min(seconds() + 900, share.expires_at ?? Infinity);
  const token = await sign(key, { id, kind: "feedback", exp: expiresAt });
  return json({ ...await noteList(db, share), canAnnotate: false, expiresAt,
    url: url.origin + pagePath(id) + "?dashboardId=" + encodeURIComponent(share.board) + "#feedback=" + token });
}

const accessHtml = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Charts Design</title><body><main><form method="post"><label>访问密钥 <input name="accessKey" inputmode="numeric" pattern="[0-9]{8}" required></label> <button>打开分享</button></form></main><script>
const p=new URLSearchParams(location.hash.slice(1)),f=document.querySelector('form');
if(p.has('key')||p.has('feedback')){const field=p.has('feedback')?'feedbackToken':'accessKey';const input=document.createElement('input');input.type='hidden';input.name=field;input.value=p.get(field==='accessKey'?'key':'feedback');f.append(input);if(field==='accessKey')f.querySelector('[name="accessKey"]').remove();history.replaceState(null,'',location.pathname+location.search);f.submit();}
</script></body></html>`;
const readerHtml = base => `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Charts Design</title><link rel="stylesheet" href="${base}app.css"><body><div id="root"></div><script>window.__chartsBoot={mode:"static",assetBase:"${base}"};const p=new URLSearchParams(location.hash.slice(1));if(p.has('key')||p.has('feedback')){const form=document.createElement('form'),i=document.createElement('input');form.method='post';i.type='hidden';i.name=p.has('feedback')?'feedbackToken':'accessKey';i.value=p.get(p.has('feedback')?'feedback':'key');form.append(i);document.body.append(form);history.replaceState(null,'',location.pathname+location.search);form.submit();}else{const s=document.createElement('script');s.src='${base}app.js';document.body.append(s);}</script></body></html>`;
const html = text => new Response(text, { headers: { "Content-Type": "text/html; charset=utf-8" } });

async function uiBuild(env, url) {
  const response = await env.ASSETS.fetch(new Request(new URL("/runtime/build.json", url)));
  check(response.ok, 503, "UI_UNAVAILABLE", "Runtime assets are unavailable");
  return response.json();
}

async function getSession(request, id, key) {
  const cookie = request.headers.get("Cookie")?.split(";").map(value => value.trim()).find(value => value.startsWith("charts-share-" + id + "="));
  return verify(key, cookie?.split("=")[1], "reader", id);
}
async function login(request, url, share, { db, key }) {
  check(request.headers.get("Origin") === url.origin, 403, "FORBIDDEN", "请重新打开分享链接");
  bodyType(request, "application/x-www-form-urlencoded");
  const form = new URLSearchParams(new TextDecoder().decode(await boundedBody(request, 2048)));
  const { id } = share;
  const feedback = await verify(key, form.get("feedbackToken"), "feedback", id);
  if (!feedback) {
    const window = Math.floor(seconds() / 600);
    const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
    const client = hex((await hmac(key, "attempt:" + ip)).subarray(0, 16));
    const row = await db.prepare("INSERT INTO access_attempts VALUES(?,?,?,1) ON CONFLICT(share_id,client,window) DO UPDATE SET attempts=attempts+1 RETURNING attempts")
      .bind(id, client, window).first();
    check(row.attempts <= 8, 429, "SHARE_RATE_LIMITED", "尝试次数过多，请稍后再试");
    check(form.get("accessKey") === await accessKey(key, id), 401, "INVALID_ACCESS_KEY", "访问密钥错误");
    await db.prepare("DELETE FROM access_attempts WHERE share_id=? AND client=? AND window=?").bind(id, client, window).run();
  }
  const exp = Math.min(seconds() + 86400, share.expires_at ?? Infinity, feedback?.exp ?? Infinity);
  const token = await sign(key, { kind: "reader", id, exp, feedback: !!feedback });
  return new Response(null, { status: 303, headers: {
    Location: pagePath(id),
    "Set-Cookie": "charts-share-" + id + "=" + token + "; Path=" + pagePath(id) + "; Secure; HttpOnly; SameSite=Strict; Max-Age=" + (exp - seconds()),
  } });
}

function selectDocument(document, share, session) {
  document.publication = { shareId: share.id, revision: share.revision };
  document.annotationAccess = { endpoint: pagePath(share.id) + "api/annotations", canRead: true,
    canAnnotate: share.mode === "annotate" && !session.feedback, canManageAnnotations: false,
    scope: "share:" + share.id, author };
  if (session.feedback) document.annotationsOpen = true;
  return document;
}

async function readDocument(env, url, share) {
  if (!share.deployment_id) return JSON.parse(share.document);
  return (await storedAsset(env, url, snapshotPath(share.id, "document.json"))).json();
}

async function assetFor(db, share, name) {
  const files = JSON.parse(share.files);
  check(Object.hasOwn(files, name), 404, "NOT_FOUND", "Resource not found");
  const file = files[name];
  let offset = file.packed;
  const end = offset + file.compressed;
  const stream = new ReadableStream({
    async pull(controller) {
      if (offset >= end) return controller.close();
      const part = Math.floor(offset / CHUNK_SIZE);
      const start = offset % CHUNK_SIZE;
      const size = Math.min(end - offset, CHUNK_SIZE - start);
      const row = await db.prepare("SELECT substr(contents,?,?) AS data FROM publication_chunks WHERE share_id=? AND part=?")
        .bind(start + 1, size, share.id, part).first();
      check(row?.data?.length === size, 410, "SHARE_UNAVAILABLE", "Resource is unavailable");
      controller.enqueue(Uint8Array.from(row.data));
      offset += size;
    },
  });
  return new Response(inflated(stream, file.method), { headers: {
    "Content-Type": name.endsWith(".gz") ? "application/gzip" : "application/octet-stream",
    "Content-Length": String(file.size),
  } });
}

function normalizedAnnotation(body, share, document) {
  const { append: note, authorName } = body ?? {};
  check(note && typeof note.id === "string" && identifier.test(note.id) && typeof note.text === "string" && note.text.trim() && note.text.length <= 4000 &&
    typeof note.createdAt === "string" && note.createdAt.length > 0 && note.createdAt.length <= 100 &&
    (authorName == null || typeof authorName === "string" && authorName.length <= 80),
    400, "INVALID_ARGUMENT", "批注内容或署名无效");
  const { componentId, anchor, view } = note;
  check(componentId == null || typeof componentId === "string" && Object.hasOwn(document.manifest.components, componentId),
    400, "INVALID_ARGUMENT", "此位置不属于分享版本");
  check(anchor && ["component", "text", "page"].includes(anchor.scope) && ["element", "area"].includes(anchor.kind),
    400, "INVALID_ARGUMENT", "批注位置无效");
  check(!anchor.rect || ["x", "y", "width", "height"].every(key => Number.isFinite(anchor.rect[key]) && anchor.rect[key] >= 0 && anchor.rect[key] <= 1),
    400, "INVALID_ARGUMENT", "批注坐标无效");
  check(anchor.quote === undefined || typeof anchor.quote === "string" && anchor.quote.length <= 1000, 400, "INVALID_ARGUMENT", "引文无效");
  check(anchor.rect || anchor.kind === "element" && anchor.quote?.trim(), 400, "INVALID_ARGUMENT", "批注需要坐标或引文");
  check(anchor.occurrence === undefined || Number.isSafeInteger(anchor.occurrence) && anchor.occurrence >= 0, 400, "INVALID_ARGUMENT", "引文位置无效");
  check(view?.revision === undefined || view.revision === share.revision, 409, "REVISION_CONFLICT", "批注版本不匹配");
  const filters = view?.filters ?? [];
  check(Array.isArray(filters), 400, "INVALID_ARGUMENT", "筛选状态无效");
  const cleanAnchor = Object.fromEntries(["scope", "kind", "quote", "occurrence"].filter(key => anchor[key] !== undefined).map(key => [key, anchor[key]]));
  if (anchor.rect) cleanAnchor.rect = Object.fromEntries(["x", "y", "width", "height"].map(key => [key, anchor.rect[key]]));
  return { id: note.id, componentId: componentId ?? null, text: note.text, createdAt: note.createdAt, anchor: cleanAnchor,
    view: { revision: share.revision, filters }, author: { name: authorName?.trim() || name, verified: false } };
}
async function annotations(request, url, share, session, { db, env }) {
  if (request.method === "GET") {
    check((!url.searchParams.has("revision") || url.searchParams.get("revision") === String(share.revision)) &&
      (!url.searchParams.has("dashboardId") || url.searchParams.get("dashboardId") === share.board),
      409, "REVISION_CONFLICT", "批注版本不匹配");
    return json({ ...await noteList(db, share), canAnnotate: share.mode === "annotate" && !session.feedback });
  }
  check(share.mode === "annotate" && !session.feedback && (!request.headers.has("Origin") || request.headers.get("Origin") === url.origin),
    403, "FORBIDDEN", "此链接没有批注权限");
  bodyType(request, "application/json");
  let body;
  try { body = JSON.parse(new TextDecoder().decode(await boundedBody(request, 40 * 1024))); }
  catch (error) { if (error instanceof ShareError) throw error; throw new ShareError(400, "INVALID_ARGUMENT", "Invalid annotation JSON"); }
  check((body?.revision === undefined || body.revision === share.revision) && (body?.dashboardId === undefined || body.dashboardId === share.board),
    409, "REVISION_CONFLICT", "批注版本不匹配");
  const note = normalizedAnnotation(body, share, await readDocument(env, url, share));
  const fingerprint = await digest(encode.encode(JSON.stringify(note)));
  note.context = { shareId: share.id, designRevision: share.revision, filters: note.view.filters };
  note.receivedAt = new Date().toISOString();
  await db.prepare("INSERT OR IGNORE INTO annotations(share_id,id,received_at,fingerprint,payload) SELECT id,?,?,?,? FROM publications WHERE id=? AND revoked=0 AND (expires_at IS NULL OR expires_at>?) AND (SELECT count(*) FROM annotations WHERE share_id=?)<100")
    .bind(note.id, Date.now(), fingerprint, JSON.stringify(note), share.id, seconds(), share.id).run();
  live(await publication(db, share.id));
  const row = await db.prepare("SELECT payload,fingerprint FROM annotations WHERE share_id=? AND id=?").bind(share.id, note.id).first();
  check(row, 409, "ANNOTATION_LIMIT", "此分享最多 100 条批注");
  check(row.fingerprint === fingerprint, 409, "ANNOTATION_CONFLICT", "此批注编号已用于其他内容");
  return json({ ...publicIdentity(share), annotation: JSON.parse(row.payload), independentSave: true });
}

async function route(request, env) {
  const url = new URL(request.url), path = url.pathname, method = request.method;
  const shared = sharedUi.exec(path);
  if (shared && method === "GET") {
    const build = await uiBuild(env, url);
    check(shared[1] === build.webId && (ui.has(shared[2]) || build.fonts?.includes(shared[2])), 404, "NOT_FOUND", "Not found");
    return env.ASSETS.fetch(new Request(new URL(path, url)));
  }
  if (path === "/health" && method === "GET") {
    await storage(env);
    await env.SHARE_DB.prepare("SELECT id FROM publications LIMIT 1").first();
    const build = await uiBuild(env, url);
    return json({ ok: true, role: "sharing", storage: env.CHARTS_PAGES_PROJECT ? "pages+d1" : "d1", uiBuildId: build.id });
  }
  const managed = /^\/api\/v1\/publications\/([0-9a-f]{32})$/.exec(path);
  if (path === "/api/v1/publications" && method === "POST" || managed && ["GET", "DELETE"].includes(method)) {
    const context = await storage(env);
    const owner = await ownerOf(request, url, env, context);
    return managed ? manage(request, url, managed[1], owner, context) : publish(request, url, owner, context);
  }
  const match = /^\/s\/([0-9a-f]{32})\/(|index\.html|(?:app|document|static-worker)\.(?:js|css|json)|data\/[a-zA-Z0-9_-]+\.(?:parquet|json\.gz)|api\/annotations)$/.exec(path);
  check(match && (method === "GET" || method === "POST" && ["", "api/annotations"].includes(match[2])), 404, "NOT_FOUND", "Not found");
  const [, id, resource] = match;
  const context = await storage(env);
  const { db, key } = context;
  const share = ready(await publication(db, id, resource === "document.json" || resource === "api/annotations" && method === "POST" ? ",document" :
    resource.startsWith("data/") ? ",files,s.assets AS snapshot_assets" : ""));
  if (!resource && method === "POST") return login(request, url, share, context);
  const session = await getSession(request, id, key);
  if (resource === "" || resource === "index.html") {
    if (!session) return html(accessHtml);
    const { webId } = await uiBuild(env, url);
    return html(readerHtml(/^[0-9a-f]{16}$/.test(webId ?? "") ? `/runtime/${webId}/` : ""));
  }
  check(session, 401, "INVALID_ACCESS_KEY", "请先输入访问密钥");
  if (resource === "api/annotations") return annotations(request, url, share, session, context);
  if (resource === "document.json") return json(selectDocument(await readDocument(env, url, share), share, session));
  if (ui.has(resource)) return env.ASSETS.fetch(new Request(new URL("/runtime/" + resource, url)));
  if (resource.startsWith("data/")) {
    if (!share.deployment_id) return assetFor(db, share, resource);
    const path = snapshotPath(id, resource);
    check(Object.hasOwn(JSON.parse(share.snapshot_assets), path), 404, "NOT_FOUND", "Resource not found");
    return storedAsset(env, url, path);
  }
  return json({ error: { code: "NOT_FOUND", message: "Not found" } }, { status: 404 });
}

export async function sharing(request, env) {
  try {
    const response = await route(request, env);
    const headers = new Headers(response.headers);
    for (const [key, value] of Object.entries(secure)) headers.set(key, value);
    if (response.ok && sharedUi.test(new URL(request.url).pathname)) {
      headers.set("Cache-Control", "public, max-age=31536000, immutable");
    }
    return new Response(response.body, { status: response.status, headers });
  } catch (error) {
    if (!(error instanceof ShareError)) console.error("Pages sharing failed", error.name, error.message);
    return json({ error: { code: error instanceof ShareError ? error.code : "SHARE_SERVICE_FAILED",
      message: error instanceof ShareError ? error.message : "Sharing service unavailable" } },
    { status: error instanceof ShareError ? error.status : 503, headers: secure });
  }
}
