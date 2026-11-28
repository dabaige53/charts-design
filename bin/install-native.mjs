#!/usr/bin/env bun
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repository = 'https://github.com/dabaige53/charts-design/releases/download';
const targets = {
  'linux-x64': 'x86_64-unknown-linux-gnu',
  'linux-arm64': 'aarch64-unknown-linux-gnu',
  'darwin-x64': 'x86_64-apple-darwin',
  'darwin-arm64': 'aarch64-apple-darwin',
  'win32-x64': 'x86_64-pc-windows-msvc',
};

export function nativeVersion(root) {
  const manifest = readFileSync(path.join(root, 'runtime-core/Cargo.toml'), 'utf8');
  const section = manifest.split(/^\[package\]\r?$/m)[1]?.split(/^\[/m)[0];
  const version = section?.match(/^version\s*=\s*"(\d+\.\d+\.\d+)"\s*$/m)?.[1];
  if (!version) throw Error('runtime-core/Cargo.toml 缺少有效版本，不能确定原生程序。');
  return version;
}

export function nativeRelease(root, platform = process.platform, arch = process.arch) {
  const version = nativeVersion(root);
  const target = targets[`${platform}-${arch}`];
  if (!target) throw Error(`没有 ${platform}/${arch} 的预编译程序；请检出项目源码并运行 bun run native:build。`);
  const executable = `charts-design-core${platform === 'win32' ? '.exe' : ''}`;
  return { version, target, executable, asset: `charts-design-core-${target}${platform === 'win32' ? '.exe' : ''}`,
    url: `${repository}/v${version}`, destination: path.join(root, 'runtime-core/native', `${platform}-${arch}`) };
}

async function download(url, limit, fetcher) {
  const response = await fetcher(url, { signal: AbortSignal.timeout(120_000) });
  if (!response.ok) throw Error(`原生程序下载失败（HTTP ${response.status}）：${url}`);
  if (!response.body) throw Error('原生程序下载大小异常。');
  if (Number(response.headers.get('content-length')) > limit) {
    await response.body.cancel().catch(() => {});
    throw Error('原生程序下载大小异常。');
  }
  const chunks = [];
  const reader = response.body.getReader();
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) throw Error('原生程序下载超过大小限制。');
      chunks.push(Buffer.from(value));
    }
  } finally { await reader.cancel().catch(() => {}); }
  return Buffer.concat(chunks, size);
}

function verifyBinary(file, version) {
  const reported = execFileSync(file, ['--version'], { encoding: 'utf8', timeout: 10_000 }).trim();
  if (reported !== `charts-design-core ${version}`) throw Error(`原生程序版本不匹配：${reported}`);
}

export async function installNative({ root, platform = process.platform, arch = process.arch, fetcher = fetch, verify = verifyBinary }) {
  const release = nativeRelease(root, platform, arch);
  const checksums = (await download(`${release.url}/SHA256SUMS`, 32 * 1024, fetcher)).toString('utf8');
  const matches = checksums.split(/\r?\n/).map(line => line.match(/^([a-f0-9]{64})  (\S+)$/))
    .filter(match => match?.[2] === release.asset);
  if (matches.length !== 1) throw Error('发布校验文件没有唯一匹配的原生程序。');
  const bytes = await download(`${release.url}/${release.asset}`, 256 * 1024 * 1024, fetcher);
  const sha256 = createHash('sha256').update(bytes).digest('hex');
  if (sha256 !== matches[0][1]) throw Error('原生程序 SHA-256 校验失败；原安装保持不变。');
  mkdirSync(release.destination, { recursive: true });
  const staging = mkdtempSync(path.join(release.destination, '.install-'));
  try {
    const candidate = path.join(staging, release.executable);
    writeFileSync(candidate, bytes, { mode: 0o755 });
    chmodSync(candidate, 0o755);
    verify(candidate, release.version);
    const binary = path.join(release.destination, release.executable);
    // A download or verification failure must never remove an existing working binary.
    renameSync(candidate, binary);
    return { version: release.version, target: release.target, binary, sha256, bytes: bytes.length };
  } finally { rmSync(staging, { recursive: true, force: true }); }
}

// Installation may run more than once. A working, matching binary needs no network.
export async function ensureNative({root, env = process.env, platform = process.platform, arch = process.arch,
  fetcher = fetch, verify = verifyBinary}) {
  if (env.CHARTS_SKIP_NATIVE_INSTALL === '1') return {skipped: true, reason: 'CHARTS_SKIP_NATIVE_INSTALL'};
  const version = nativeVersion(root);
  if (env.CHARTS_CORE_BIN) {
    const binary = path.resolve(env.CHARTS_CORE_BIN);
    verify(binary, version);
    return {version, binary, reused: true};
  }
  const release = nativeRelease(root, platform, arch);
  const binary = path.join(release.destination, release.executable);
  if (existsSync(binary)) {
    try { verify(binary, version); return {...release, binary, reused: true}; }
    catch { /* Replace an incompatible binary only after a verified download. */ }
  }
  return installNative({root, platform, arch, fetcher, verify});
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    if (process.argv.length > 2) throw Error('用法：bun run native:install（版本随当前安装包固定）');
    const receipt = await ensureNative({ root: fileURLToPath(new URL('..', import.meta.url)) });
    console.log(receipt.skipped ? '已按 CHARTS_SKIP_NATIVE_INSTALL 跳过原生安装。'
      : `Rust Runtime ${receipt.reused ? '已就绪' : '已安装'}：${receipt.version}\n${receipt.binary}`);
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
