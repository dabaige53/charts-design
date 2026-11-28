import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { activeSnapshotAssets, assetManifest, bundlePath, pagesAsset, pagesClient, releasePath,
  withPagesDeployment } from "./pages/deployment.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const mode = process.argv[2];
const plan = process.argv.includes("--plan");
const env = process.env;

function command(args, options = {}) {
  const result = Bun.spawnSync(args, { cwd: root, stdout: "inherit", stderr: "inherit", ...options });
  if (result.exitCode !== 0) throw Error(args.slice(0, 3).join(" ") + " failed");
}

function setting(key, { min = 1 } = {}) {
  const value = env[key];
  if (!value || value.length < min || /[\r\n]/.test(value)) throw Error("Set " + key);
  return value;
}

async function health(origin, role, build) {
  for (let attempt = 0; attempt < 18; attempt++) {
    try {
      const response = await fetch(new URL("/health", origin), {
        headers: { "User-Agent": "Charts-Design-Deployment/1" }, signal: AbortSignal.timeout(5000),
      });
      const result = await response.json();
      if (response.ok && result.ok && result.role === role && (!build || result.storage === "pages+d1" && result.uiBuildId === build)) {
        console.log(JSON.stringify({ origin, ...result }));
        return;
      }
    } catch (error) {
      if (attempt === 17) throw error;
    }
    await Bun.sleep(1500);
  }
  throw Error("Health verification did not reach the expected current build at " + origin);
}

async function author(validateOnly = false) {
  const file = resolve(env.CHARTS_AUTHOR_ENV_FILE || join(root, "deploy/charts.env"));
  const port = env.CHARTS_AUTHOR_PORT || "8000";
  if (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535) throw Error("Invalid CHARTS_AUTHOR_PORT");
  const options = { ...env, CHARTS_AUTHOR_ENV_FILE: file, CHARTS_AUTHOR_PORT: port };
  if (plan) {
    console.log(JSON.stringify({ target: "author", file, health: "http://127.0.0.1:" + port + "/health" }));
    return;
  }
  const input = Bun.file(file);
  if (!await input.exists()) throw Error("Copy deploy/environment.example to " + file + " and configure the author URL and token.");
  const config = await input.text();
  if (/replace-with-a-long-random-value|https:\/\/charts\.example\.com/.test(config)) throw Error("Replace the example values in " + file);
  if (!Bun.which("docker")) throw Error("Install Docker with the Compose plugin to initialize the author");
  const args = ["docker", "compose", "--env-file", file, "-f", "deploy/docker-compose.yml"];
  if (validateOnly) {
    command([...args, "config", "--quiet"], { env: options });
    return;
  }
  command([...args, "up", "-d", "--build", "--wait"], { env: options });
  await health("http://127.0.0.1:" + port, "workspace");
}

async function pages() {
  const name = env.CHARTS_PAGES_PROJECT || "charts-design";
  const databaseName = env.CHARTS_D1_DATABASE || name + "-shares";
  const branch = env.CHARTS_PAGES_BRANCH || "main";
  if (!/^[a-z0-9](?:[a-z0-9-]{0,56}[a-z0-9])?$/.test(name) ||
      !/^[a-z0-9](?:[a-z0-9-]{0,56}[a-z0-9])?$/.test(databaseName) || !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$/.test(branch))
    throw Error("Invalid Pages project, D1 database or branch name");
  if (plan) {
    console.log(JSON.stringify({ target: "pages", name, databaseName, branch }));
    return;
  }
  const account = setting("CLOUDFLARE_ACCOUNT_ID");
  if (!/^[0-9a-f]{32}$/.test(account)) throw Error("Invalid CLOUDFLARE_ACCOUNT_ID");
  const apiToken = setting("CLOUDFLARE_API_TOKEN");
  const snapshotToken = setting("CHARTS_PAGES_DEPLOY_TOKEN");
  if (snapshotToken === apiToken) throw Error("Use a separate Pages-only snapshot deployment token");
  const serviceToken = setting("CHARTS_SHARE_SERVICE_TOKEN", { min: 32 });
  const signingSecret = setting("CHARTS_SHARE_SIGNING_SECRET", { min: 32 });
  if (serviceToken === signingSecret) throw Error("Use distinct publication and signing secrets");
  const api = "https://api.cloudflare.com/client/v4/accounts/" + account;
  async function request(method, path, data, absent = false) {
    const response = await fetch(api + path, {
      method, headers: { Authorization: "Bearer " + apiToken, "Content-Type": "application/json" },
      body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(30000),
    });
    if (response.status === 404 && absent) return null;
    const body = await response.json();
    if (!response.ok || !body.success) throw Error(method + " " + path + " failed (Cloudflare HTTP " + response.status + ")");
    return body.result;
  }
  const projectPath = "/pages/projects/" + name;
  let project = await request("GET", projectPath, undefined, true);
  if (!project) project = await request("POST", "/pages/projects", { name, production_branch: branch });
  if (project.production_branch !== branch) throw Error("Set CHARTS_PAGES_BRANCH to this project's production branch: " + project.production_branch);
  const current = project.deployment_configs?.production ?? {};
  const found = await request("GET", "/d1/database?name=" + databaseName);
  const existing = found.find(db => db.name === databaseName);
  if (current.d1_databases?.SHARE_DB && current.d1_databases.SHARE_DB.id !== existing?.uuid)
    throw Error("Existing SHARE_DB belongs to a different database");
  const db = existing || await request("POST", "/d1/database", { name: databaseName });
  const schema = await Bun.file(join(root, "deploy/pages/schema.sql")).text();
  const dbPath = "/d1/database/" + db.uuid + "/query";
  await request("POST", dbPath, { sql: schema });
  const database = {
    prepare: sql => ({ bind: (...params) => {
      const execute = async () => (await request("POST", dbPath, { sql, params }))[0];
      return { run: execute, all: execute, first: async () => (await execute()).results[0] };
    } }),
  };
  const secrets = Object.fromEntries(Object.entries({
    CHARTS_SHARE_SERVICE_TOKEN: serviceToken, CHARTS_SHARE_SIGNING_SECRET: signingSecret, CHARTS_PAGES_DEPLOY_TOKEN: snapshotToken,
  }).filter(([key]) => !current.env_vars?.[key]).map(([key, value]) => [key, { type: "secret_text", value }]));
  const config = Object.fromEntries(Object.entries({
    CHARTS_PAGES_ACCOUNT: account, CHARTS_PAGES_PROJECT: name, CHARTS_PAGES_BRANCH: branch,
  }).map(([key, value]) => [key, { type: "plain_text", value }]));
  const temporary = await mkdtemp(join(tmpdir(), "charts-pages-init-"));
  try {
    command(["bun", "run", "ui:install"]);
    command(["bun", "run", "ui:prepare"]);
    const output = join(temporary, "dist");
    command(["bun", "deploy/pages/build.mjs", output, "--d1"]);
    await withPagesDeployment(database, async assertLock => {
      await request("PATCH", projectPath, { deployment_configs: { production: {
        fail_open: false, d1_databases: { SHARE_DB: { id: db.uuid } }, env_vars: { ...config, ...secrets },
      } } });
      const release = await Bun.file(output + releasePath).json();
      const names = [...Object.keys(release), releasePath];
      const assets = await Promise.all(names.map(async path => pagesAsset(path, new Uint8Array(await Bun.file(output + path).arrayBuffer()))));
      const runtime = assetManifest(assets);
      await pagesClient({ account, project: name, branch, token: snapshotToken }).deploy({
        assets, manifest: { ...runtime, ...await activeSnapshotAssets(database, Math.floor(Date.now() / 1000)) },
        worker: new Uint8Array(await Bun.file(output + bundlePath).arrayBuffer()),
        marker: "charts-runtime-" + runtime[releasePath], assertLock,
      });
    });
    const build = (await Bun.file(join(output, "runtime/build.json")).json()).id;
    if (!project.subdomain) project = await request("GET", projectPath);
    const origin = new URL(env.CHARTS_PAGES_URL || "https://" + project.subdomain);
    if (origin.protocol !== "https:" || origin.username || origin.password) throw Error("CHARTS_PAGES_URL must use HTTPS");
    await health(origin, "sharing", build);
    const missing = new URL("/api/v1/publications/" + "0".repeat(32), origin);
    missing.search = new URLSearchParams({ project: "deployment-check", source: crypto.randomUUID() });
    const authenticated = await fetch(missing, { headers: { Authorization: "Bearer " + serviceToken,
      "User-Agent": "Charts-Design-Deployment/1" }, signal: AbortSignal.timeout(12000) });
    const reply = await authenticated.json();
    if (authenticated.status !== 403 || reply.error?.code !== "FORBIDDEN")
      throw Error("The configured publication token does not match the active Pages deployment");
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

if (!["author", "pages", "all"].includes(mode) || process.argv.slice(3).some(value => value !== "--plan")) {
  console.log("Usage: bun run deploy:init -- author|pages|all [--plan]");
  process.exitCode = mode && mode !== "--help" ? 1 : 0;
} else {
  if (mode === "all" && !plan) await author(true);
  if (mode !== "author") await pages();
  if (mode !== "pages") await author();
}
