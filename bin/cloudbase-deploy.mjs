#!/usr/bin/env node
import { execFileSync, spawn } from 'node:child_process';
import { appendFileSync, copyFileSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
export const CLI_VERSION = '3.9.1';
export function validateTag(tag, version) {
  if (!/^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(tag ?? '') || tag !== `v${version}`) {
    throw new Error('发布标签必须为 vX.Y.Z，且与 package.json.version 一致。');
  }
  return tag;
}

export function includeSource(path) {
  if (path.split('/').some(part => /^(node_modules|dist|generated|__pycache__)$/.test(part)
    || part.startsWith('.') || /\.(pyc|pem|key|pfx)$/.test(part) || /\.env($|\.)/.test(part))) return false;
  if (/^docs\/(design-system|design-canvas|images)\//.test(path)) return false;
  return /^(dashboard_runtime|runtime-ui|bin|docs)\//.test(path)
    || /^skills\/(executive-charts|analytical-reports)\//.test(path)
    || /^(package\.json|pyproject\.toml|README\.md)$/.test(path);
}

export function matchesRelease(health, version, commit) {
  return health?.ok === true && health.release?.version === version && health.release?.commit === commit;
}

export function runtimeConfig(detail, version, commit) {
  const config = detail.ServerConfig;
  if (!config?.EnvParams) throw new Error('未找到现有服务配置；此脚本用于更新已部署的服务。');
  let existing;
  try { existing = typeof config.EnvParams === 'string' ? JSON.parse(config.EnvParams) : config.EnvParams; }
  catch { throw new Error('线上环境变量格式无效；请检查服务配置。'); }
  if (existing.CHARTS_STORAGE_BACKEND !== 'cloudbase') throw new Error('线上服务未使用 CloudBase 持久存储，停止更新。');
  return { ...existing, CHARTS_RELEASE_VERSION: version, CHARTS_RELEASE_COMMIT: commit };
}

export function completedGrayRelease(order, online) {
  if (!order?.IsReleasing) return false;
  const target = order.ReleaseVersion;
  if (order.GrayStatus === 'success' && order.TrafficType === 'FLOW' && Number(order.FlowRatio) === 100
    && target?.Status === 'normal' && online.length === 1
    && online[0].VersionName === target.VersionName && Number(online[0].FlowRatio) === 100) return true;
  throw new Error('存在未结束的灰度发布；请先完成或撤回该发布，再重跑 CI。');
}

export function taskReady(task, completedGrayVersion) {
  if (!task) return false;
  if (['finished', 'failed', 'stopped', 'notInvolve'].includes(task.Status)) return true;
  return Boolean(completedGrayVersion && task.ReleaseType === 'GRAY' && task.VersionName === completedGrayVersion
    && task.Steps?.length && task.Steps.every(step => step.Name === 'GrayRelease'
      || ['finished', 'notInvolve'].includes(step.Status)));
}

export function cloudrunDeployArgs(service, stage, runtimeEnv, minNum, maxNum) {
  return ['cloudrun', 'deploy', '--service-name', service, '--source', stage,
    '--port', '8000', '--open-access-types', 'PUBLIC', '--env-params', JSON.stringify(runtimeEnv),
    '--min-num', String(minNum), '--max-num', String(maxNum), '--force', '--wait', '--yes'];
}

function parseOutput(output) {
  // CLI progress precedes its JSON result. Never print raw service configuration.
  for (let index = 0; index < output.length; index++) {
    if (output[index] !== '{') continue;
    try { return JSON.parse(output.slice(index)); } catch { /* Continue to the JSON result. */ }
  }
  throw new Error('CloudBase CLI 未返回可解析的 JSON。');
}

export async function deploy() {
  const env = process.env;
  for (const name of ['CLOUDBASE_API_KEY', 'CLOUDBASE_ENV_ID', 'CLOUDBASE_SERVICE', 'CLOUDBASE_REGION', 'CLOUDBASE_SERVICE_URL']) {
    if (!env[name]) throw new Error(`缺少 ${name}。`);
  }
  const pkg = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
  const tag = validateTag(process.argv[2], pkg.version);
  const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim();
  const commit = git('rev-parse', 'HEAD');
  if (git('rev-parse', `${tag}^{commit}`) !== commit) throw new Error('工作区不是指定标签的提交。');
  if (git('status', '--porcelain')) throw new Error('部署要求干净的 Git 工作区。');
  const endpoint = new URL(env.CLOUDBASE_SERVICE_URL);
  if (endpoint.protocol !== 'https:' || endpoint.username || endpoint.password || endpoint.search || endpoint.hash) {
    throw new Error('CLOUDBASE_SERVICE_URL 必须是无凭据的 HTTPS 地址。');
  }
  const moduleRoot = execFileSync('npm', ['root', '-g'], { encoding: 'utf8' }).trim();
  const installed = JSON.parse(readFileSync(join(moduleRoot, '@cloudbase/cli/package.json'), 'utf8'));
  if (installed.version !== CLI_VERSION) throw new Error(`请安装 @cloudbase/cli@${CLI_VERSION}。`);
  const stage = mkdtempSync(join(process.platform === 'darwin' ? '/private/tmp' : tmpdir(), 'charts-cloudbase-'));
  const cli = (args, json = false) => new Promise((accept, reject) => {
    const child = spawn(process.execPath, [join(root, 'deploy/cloudbase-cli.cjs'), moduleRoot], {
      cwd: stage, env: { ...env, CI: '1', CLOUDBASE_CI: '1', TCB_IS_INTL: 'false' },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    let output = '';
    child.stdout.on('data', data => { output += data.toString(); });
    // Raw CLI output can contain URLs and environment credentials. Only report operation/status.
    child.stderr.resume();
    const heartbeat = setInterval(() => console.log(`CloudBase ${args.slice(0, 2).join(' ')} 执行中…`), 30_000);
    const timeout = setTimeout(() => child.kill('SIGTERM'), 32 * 60_000);
    child.on('error', () => {
      clearInterval(heartbeat); clearTimeout(timeout);
      reject(new Error('无法启动 CloudBase CLI。'));
    });
    child.on('close', (code, signal) => {
      clearInterval(heartbeat); clearTimeout(timeout);
      if (code !== 0) return reject(new Error(`CloudBase ${args.slice(0, 2).join(' ')} 失败（${signal ? `信号 ${signal}` : `退出码 ${code}`}）；请查看云端构建记录。`));
      try { accept(json ? parseOutput(output) : undefined); } catch (error) { reject(error); }
    });
    child.stdin.on('error', () => { /* Process exit supplies the failure above. */ });
    child.stdin.end(JSON.stringify({ args: [...args, '--env-id', env.CLOUDBASE_ENV_ID, '--region', env.CLOUDBASE_REGION, '--json'] }));
  });
  const serviceArgs = ['--service-name', env.CLOUDBASE_SERVICE];
  try {
    await cli(['login', '--cloudbase-api-key', env.CLOUDBASE_API_KEY]);
    const response = await cli(['cloudrun', 'detail', ...serviceArgs], true);
    const detail = response.data ?? response;
    if (detail.BaseInfo?.Status !== 'normal') throw new Error('线上服务尚未处于 normal 状态，请等待现有任务结束。');
    const runtimeEnv = runtimeConfig(detail, pkg.version, commit);
    const apiBody = { EnvId: env.CLOUDBASE_ENV_ID, ServerName: env.CLOUDBASE_SERVICE };
    const readTask = async () => {
      const result = await cli(['api', 'tcbr', 'DescribeServerManageTask', '--api-version', '2022-02-17',
        '--body', JSON.stringify({ ...apiBody, TaskId: 0 })], true);
      return (result.data ?? result).Task;
    };
    const orderResponse = await cli(['api', 'tcbr', 'DescribeReleaseOrder', '--api-version', '2022-02-17',
      '--body', JSON.stringify(apiBody)], true);
    const order = (orderResponse.data ?? orderResponse).ReleaseOrderInfo;
    const finishGray = completedGrayRelease(order, detail.OnlineVersionInfos ?? []);
    if (!taskReady(await readTask(), finishGray ? order.ReleaseVersion.VersionName : undefined)) {
      throw new Error('云端仍有发布任务或无法确认任务状态；停止提交，避免取消其他发布。');
    }
    if (finishGray) {
      const health = await fetch(new URL('health', `${endpoint.href.replace(/\/$/, '')}/`), { signal: AbortSignal.timeout(15_000) });
      if (!health.ok || (await health.json()).ok !== true) throw new Error('现有版本健康检查未通过，停止发布。');
      console.log('现有灰度版本已正常承接 100% 流量，完成其发布状态。');
      await cli(['cloudrun', 'traffic', 'promote', ...serviceArgs]);
      let ready = false;
      for (let attempt = 0; attempt < 30; attempt++) {
        if (taskReady(await readTask())) { ready = true; break; }
        await delay(3000);
      }
      if (!ready) throw new Error('灰度收尾尚未完成；请等待云端任务结束后重跑 CI。');
    }
    const files = git('ls-files', '-z').split('\0').filter(includeSource);
    for (const name of files) {
      const source = join(root, name);
      if (!lstatSync(source).isFile()) throw new Error(`构建源不允许符号链接：${name}`);
      const content = readFileSync(source);
      for (const value of [env.CLOUDBASE_API_KEY, runtimeEnv.CHARTS_SERVER_SECRET, runtimeEnv.CHARTS_SERVER_TOKENS]) {
        if (value && content.includes(Buffer.from(value))) throw new Error(`构建源包含凭据：${name}`);
      }
      mkdirSync(dirname(join(stage, name)), { recursive: true });
      copyFileSync(source, join(stage, name));
    }
    const dockerfile = readFileSync(join(root, 'deploy/Dockerfile'), 'utf8');
    writeFileSync(join(stage, 'Dockerfile'), `${dockerfile}\nENV CHARTS_RELEASE_VERSION=${pkg.version} CHARTS_RELEASE_COMMIT=${commit}\n`);
    console.log(`提交 ${tag}（${commit.slice(0, 12)}），${files.length} 个源文件；云端构建并发布。`);
    await cli(cloudrunDeployArgs(env.CLOUDBASE_SERVICE, stage, runtimeEnv,
      detail.ServerConfig.MinNum, detail.ServerConfig.MaxNum));
    const healthUrl = new URL('health', `${endpoint.href.replace(/\/$/, '')}/`);
    for (let attempt = 0; attempt < 18; attempt++) {
      try {
        const result = await fetch(healthUrl, { signal: AbortSignal.timeout(10_000), cache: 'no-store' });
        if (result.ok && matchesRelease(await result.json(), pkg.version, commit)) {
          console.log(`部署成功：${tag}，健康检查及提交号一致。`);
          if (env.GITHUB_STEP_SUMMARY) appendFileSync(env.GITHUB_STEP_SUMMARY,
            `## CloudBase 发布成功\n\n- 版本：${tag}\n- 提交：${commit}\n- 服务：${env.CLOUDBASE_SERVICE}\n- 健康检查：通过\n`);
          return;
        }
      } catch { /* A cold start or traffic switch may temporarily interrupt health checks. */ }
      await delay(10_000);
    }
    throw new Error('部署后未检查到目标版本。请检查 CloudBase 构建与流量状态；本脚本不会自动回滚数据库。');
  } finally { rmSync(stage, { recursive: true, force: true }); }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  deploy().catch(error => { console.error(error.message); process.exitCode = 1; });
}
