import { blake3 } from "@noble/hashes/blake3";
import { check } from "./publication-zip.mjs";

const api = "https://api.cloudflare.com/client/v4";
const routes = JSON.stringify({ version: 1, include: ["/*"], exclude: [] });
const utf8 = new TextEncoder();
const mime = pathname =>
  pathname.endsWith(".json") ? "application/json" :
  pathname.endsWith(".js") ? "text/javascript" :
  pathname.endsWith(".css") ? "text/css" : "application/octet-stream";

export const releasePath = "/runtime/deployment.json";
export const bundlePath = "/runtime/redeploy.bin";

function base64(bytes) {
  if (typeof bytes.toBase64 === "function") return bytes.toBase64();
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 16_384) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 16_384));
  }
  return btoa(binary);
}

export function pagesAsset(path, bytes) {
  const value = base64(bytes);
  // Use the same content and extension identity as Wrangler Pages Direct Upload.
  const hash = blake3.create({ dkLen: 16 }).update(value).update(path.slice(path.lastIndexOf(".") + 1)).digest();
  return { path, key: Array.from(hash, byte => byte.toString(16).padStart(2, "0")).join(""),
    value, metadata: { contentType: mime(path) }, base64: true };
}

export const assetManifest = assets => Object.fromEntries(assets.map(({ path, key }) => [path, key]));

export async function workerBundle(bytes) {
  const form = new FormData();
  form.set("metadata", JSON.stringify({ main_module: "_worker.js" }));
  form.set("_worker.js", new Blob([bytes], { type: "application/javascript+module" }), "_worker.js");
  return new Uint8Array(await new Response(form).arrayBuffer());
}

export function pagesClient({ account, project, branch, token }) {
  check(/^[0-9a-f]{32}$/.test(account) && /^[a-z0-9-]+$/.test(project) && branch && token,
    503, "CLOUD_SHARE_NOT_CONFIGURED", "Configure the Pages snapshot publisher");
  const path = "/accounts/" + account + "/pages/projects/" + project;
  async function request(endpoint, { method = "GET", value, credential = token } = {}) {
    const headers = { Authorization: "Bearer " + credential };
    let body = value;
    if (value !== undefined && !(value instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(value);
    }
    const response = await fetch(api + endpoint, { method, headers, body, signal: AbortSignal.timeout(25000) });
    const result = await response.json();
    check(response.ok && result.success, 503, "PAGES_DEPLOY_FAILED",
      "Cloudflare Pages rejected a deployment request (HTTP " + response.status + ")");
    return result.result;
  }
  return {
    async deploy({ assets, manifest, worker, marker, requiredRelease, restore, assertLock }) {
      const detail = await request(path);
      check(detail.production_branch === branch && detail.deployment_configs?.production?.fail_open === false,
        503, "CLOUD_SHARE_NOT_CONFIGURED", "The Pages snapshot project must use fail-closed production routing");
      const current = detail.canonical_deployment;
      const latest = (await request(path + "/deployments?env=production&per_page=1"))[0];
      check(!latest || ["success", "failure", "canceled", "skipped"].includes(latest.latest_stage?.status),
        503, "PAGES_DEPLOY_PENDING", "A Pages deployment is still in progress. Retry with the same request ID.");
      const currentMarker = current?.deployment_trigger?.metadata?.commit_message;
      check(!requiredRelease || currentMarker?.endsWith("-" + requiredRelease), 503, "PAGES_DEPLOY_PENDING",
        "The Pages runtime has changed. Retry with the same request ID.");
      if (currentMarker === marker && current.latest_stage?.status === "success") return current.id;
      const hashes = [...new Set(Object.values(manifest))];
      check(Object.keys(manifest).length <= 20_000, 409, "PAGES_ASSET_LIMIT", "The Pages deployment exceeds 20,000 assets");
      const { jwt } = await request(path + "/upload-token");
      const missing = await request("/pages/assets/check-missing", { method: "POST", credential: jwt, value: { hashes } });
      const available = new Map(assets.map(asset => [asset.key, asset]));
      const paths = new Map(Object.entries(manifest).map(([name, hash]) => [hash, name]));
      for (const hash of missing) {
        const asset = available.get(hash) ?? await restore?.(paths.get(hash));
        check(asset?.key === hash, 503, "PAGES_ASSET_UNAVAILABLE", "A current Pages asset could not be recovered");
        const { path: _path, ...payload } = asset;
        await request("/pages/assets/upload", { method: "POST", credential: jwt, value: [payload] });
      }
      await request("/pages/assets/upsert-hashes", { method: "POST", credential: jwt, value: { hashes } });
      const form = new FormData();
      form.set("manifest", JSON.stringify(manifest));
      form.set("branch", branch);
      form.set("commit_message", marker);
      form.set("_worker.bundle", new Blob([worker]), "_worker.bundle");
      form.set("_routes.json", new Blob([routes]), "_routes.json");
      await assertLock();
      const deployment = await request(path + "/deployments", { method: "POST", value: form });
      for (let attempt = 0; attempt < 24; attempt++) {
        const project = await request(path);
        if (project.canonical_deployment?.id === deployment.id && project.canonical_deployment.latest_stage?.status === "success")
          return deployment.id;
        const stage = project.latest_deployment?.id === deployment.id && project.latest_deployment.latest_stage;
        check(!stage || !["failure", "canceled", "skipped"].includes(stage.status), 503, "PAGES_DEPLOY_FAILED",
          "Cloudflare could not activate the Pages deployment");
        await new Promise(resolve => setTimeout(resolve, 1500));
      }
      check(false, 503, "PAGES_DEPLOY_PENDING", "Pages has not activated the deployment. Retry with the same request ID.");
    },
  };
}

export async function withPagesDeployment(db, callback) {
  const token = crypto.randomUUID();
  const now = Math.floor(Date.now() / 1000);
  const lock = await db.prepare("INSERT INTO pages_deployment_lock(id,token,expires_at) VALUES(1,?,?) " +
    "ON CONFLICT(id) DO UPDATE SET token=excluded.token,expires_at=excluded.expires_at " +
    "WHERE pages_deployment_lock.expires_at<=? RETURNING token").bind(token, now + 180, now).first();
  check(lock?.token === token, 503, "PAGES_DEPLOY_PENDING", "A Pages deployment is in progress. Retry with the same request ID.");
  const assertLock = async () => {
    const row = await db.prepare("SELECT token FROM pages_deployment_lock WHERE id=1 AND expires_at>?")
      .bind(Math.floor(Date.now() / 1000)).first();
    check(row?.token === token, 503, "PAGES_DEPLOY_PENDING", "The Pages deployment lock expired. Retry with the same request ID.");
  };
  try {
    return await callback(assertLock);
  } finally {
    await db.prepare("DELETE FROM pages_deployment_lock WHERE id=1 AND token=?").bind(token).run();
  }
}

export async function activeSnapshotAssets(db, now) {
  const { results } = await db.prepare("SELECT s.assets FROM pages_snapshots s JOIN publications p ON p.id=s.share_id " +
    "WHERE s.deployment_id IS NOT NULL AND p.revoked=0 AND (p.expires_at IS NULL OR p.expires_at>?)").bind(now).all();
  const manifest = {};
  for (const row of results) Object.assign(manifest, JSON.parse(row.assets));
  return manifest;
}

export const jsonAsset = (path, value) => pagesAsset(path, utf8.encode(JSON.stringify(value)));
