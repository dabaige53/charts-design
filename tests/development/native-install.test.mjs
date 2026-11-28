import assert from 'node:assert/strict';
import { afterEach, test } from 'bun:test';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ensureNative, installNative, nativeRelease } from '../../bin/install-native.mjs';
import { nativeCommand, nativeRuntime } from '../../bin/native-runtime.js';

const directories = [];
afterEach(() => { for (const dir of directories.splice(0)) rmSync(dir, { recursive: true, force: true }); });

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), 'charts-native-install-'));
  directories.push(root);
  mkdirSync(path.join(root, 'runtime-core'));
  writeFileSync(path.join(root, 'runtime-core/Cargo.toml'), '[package]\nname = "charts-design-core"\nversion = "0.1.0"\n\n[dependencies]\n');
  const release = nativeRelease(root);
  mkdirSync(release.destination, { recursive: true });
  const binary = path.join(release.destination, release.executable);
  writeFileSync(binary, 'previous working binary');
  const body = Buffer.from('verified native artifact');
  const checksum = createHash('sha256').update(body).digest('hex');
  const requests = [];
  const fetcher = async url => {
    requests.push(url);
    assert.ok(url.startsWith(release.url + '/'));
    return new Response(url.endsWith('/SHA256SUMS') ? `${checksum}  ${release.asset}\n` : body);
  };
  return { root, release, binary, body, checksum, requests, fetcher };
}

// @wu-test type=integration | scope=原生程序安装 | protects=下载错误平台或未校验二进制即替换原安装
test('pinned platform artifact is verified before atomic installation', async () => {
  const f = fixture();
  let verified = false;
  const result = await installNative({ root: f.root, fetcher: f.fetcher, verify: (candidate, version) => {
    assert.deepEqual(readFileSync(candidate), f.body);
    assert.equal(readFileSync(f.binary, 'utf8'), 'previous working binary');
    assert.equal(version, '0.1.0');
    verified = true;
  } });
  assert.equal(verified, true);
  assert.deepEqual(readFileSync(f.binary), f.body);
  assert.equal(result.sha256, f.checksum);
  assert.deepEqual(readdirSync(f.release.destination), [f.release.executable]);
  assert.deepEqual(f.requests, [f.release.url + '/SHA256SUMS', f.release.url + '/' + f.release.asset]);
});

// @wu-test type=boundary | scope=原生安装失败恢复 | protects=发布不存在下载损坏或程序不可执行时破坏现有安装
test('download and execution failures preserve the previous installation', async () => {
  const f = fixture();
  let executed = false;
  await assert.rejects(installNative({ root: f.root, fetcher: async () => new Response('', { status: 404 }),
    verify: () => { executed = true; } }), /HTTP 404/);
  await assert.rejects(installNative({ root: f.root, fetcher: async url => url.endsWith('/SHA256SUMS')
    ? f.fetcher(url) : new Response('corrupt'), verify: () => { executed = true; } }), /SHA-256/);
  assert.equal(executed, false);
  await assert.rejects(installNative({ root: f.root, fetcher: f.fetcher,
    verify: () => { throw Error('wrong version or architecture'); } }), /wrong version/);
  let cancelled = false;
  await assert.rejects(installNative({ root: f.root, fetcher: async url => url.endsWith('/SHA256SUMS') ? f.fetcher(url)
    : new Response(new ReadableStream({ cancel() { cancelled = true; } }), { headers: { 'Content-Length': String(257 * 1024 * 1024) } }),
    verify: () => { executed = true; } }), /下载大小异常/);
  assert.equal(cancelled, true);
  assert.equal(executed, false);
  assert.equal(readFileSync(f.binary, 'utf8'), 'previous working binary');
  assert.deepEqual(readdirSync(f.release.destination), [f.release.executable]);
});

// @wu-test type=boundary | scope=原生发布选择 | protects=使用可变latest版本或把错误体系结构程序交付给用户
test('all supported platforms map to fixed release assets and unknown architectures fail', () => {
  const { root } = fixture();
  for (const [platform, arch, target] of [
    ['linux', 'x64', 'x86_64-unknown-linux-gnu'], ['linux', 'arm64', 'aarch64-unknown-linux-gnu'],
    ['darwin', 'x64', 'x86_64-apple-darwin'], ['darwin', 'arm64', 'aarch64-apple-darwin'],
    ['win32', 'x64', 'x86_64-pc-windows-msvc'],
  ]) {
    const release = nativeRelease(root, platform, arch);
    assert.equal(release.target, target);
    assert.equal(release.url.endsWith('/v0.1.0'), true);
    assert.equal(release.executable.endsWith('.exe'), platform === 'win32');
    assert.equal(path.basename(release.destination), `${platform}-${arch}`);
  }
  assert.throws(() => nativeRelease(root, 'linux', 'riscv64'), /native:build/);
});

// @wu-test type=behavior | scope=npm安装生命周期 | protects=重复安装仍下载程序或忽略操作员选择的已验证二进制
test('package installation reuses a matching binary and honors explicit source setup', async () => {
  const f = fixture();
  const noDownload = async () => {throw Error('Unexpected download');};
  const verified = [];
  const verify = (binary, version) => {verified.push(binary); assert.equal(version, '0.1.0');};
  const existing = await ensureNative({root: f.root, env: {}, fetcher: noDownload, verify});
  assert.equal(existing.reused, true);
  assert.deepEqual(verified, [f.binary]);
  const selected = await ensureNative({root: f.root, env: {CHARTS_CORE_BIN: f.binary}, platform: 'unsupported',
    fetcher: noDownload, verify});
  assert.equal(selected.binary, f.binary);
  const skipped = await ensureNative({root: f.root, env: {CHARTS_SKIP_NATIVE_INSTALL: '1'}, fetcher: noDownload,
    verify: () => {throw Error('Source setup must not execute a binary');}});
  assert.equal(skipped.skipped, true);
  await assert.rejects(ensureNative({root: f.root, env: {CHARTS_CORE_BIN: f.binary}, fetcher: noDownload,
    verify: () => {throw Error('Selected binary has the wrong version');}}), /wrong version/);
});

// @wu-test type=boundary | scope=CLI transport selection | protects=名为mcp的看板或路径误启动stdio代理且help挂起
test('only the command token selects MCP after global options', () => {
  for (const args of [
    ['mcp'], ['--project-root', 'mcp', 'mcp'], ['--runtime-root=mcp', 'mcp'],
    ['--root', 'mcp', '--sources=source.json', 'mcp'],
  ]) assert.equal(nativeCommand(args), 'mcp', JSON.stringify(args));
  for (const args of [
    ['get', 'mcp'], ['init', 'mcp'], ['--project-root', 'mcp', 'list'],
    ['--runtime-root', 'mcp', 'list'], ['--root=mcp', 'list'],
    ['--sources', 'mcp', 'catalog'], ['--sources=mcp', 'contract'],
    ['--sources', 'mcp'], ['--', 'mcp'], ['--unknown', 'mcp'],
    ['mcp', '--help'], ['--help', 'mcp'], ['mcp', '-h'],
  ]) assert.notEqual(nativeCommand(args), 'mcp', JSON.stringify(args));
});

// @wu-test type=integration | scope=installed CLI launcher | protects=普通get命令因参数mcp而未启动程序并丢失结果
test('a normal command with the board named mcp executes and returns its output', () => {
  const directory = mkdtempSync(path.join(tmpdir(), 'charts-launcher-'));
  directories.push(directory);
  writeFileSync(path.join(directory, 'get'), 'console.log(JSON.stringify(process.argv.slice(2)));\n');
  const launcher = fileURLToPath(new URL('../../bin/dashboard-runtime.js', import.meta.url));
  const output = execFileSync(process.execPath, [launcher, 'get', 'mcp'], {
    cwd: directory, env: {...process.env, CHARTS_CORE_BIN: process.execPath},
    encoding: 'utf8', input: '', timeout: 10000,
  });
  assert.deepEqual(JSON.parse(output), ['mcp']);
});

// @wu-test type=integration | scope=explicit native binary | protects=安装通过的相对程序路径在启动时转为PATH查找而失效
test('a selected binary basename resolves exactly as the installer does', () => {
  const originalDirectory = process.cwd(), originalBinary = process.env.CHARTS_CORE_BIN;
  try {
    process.chdir(path.dirname(process.execPath));
    process.env.CHARTS_CORE_BIN = path.basename(process.execPath);
    const runtime = nativeRuntime();
    assert.equal(runtime.binary, path.resolve(process.execPath));
    assert.equal(path.isAbsolute(runtime.binary), true);
    const version = execFileSync(runtime.binary, ['--version'], {
      cwd: tmpdir(), env: runtime.env, encoding: 'utf8', timeout: 10000,
    });
    assert.ok(version.trim());
  } finally {
    process.chdir(originalDirectory);
    if (originalBinary === undefined) delete process.env.CHARTS_CORE_BIN;
    else process.env.CHARTS_CORE_BIN = originalBinary;
  }
});
