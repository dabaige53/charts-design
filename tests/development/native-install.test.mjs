import assert from 'node:assert/strict';
import { afterEach, test } from 'bun:test';
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { installNative, nativeRelease } from '../../bin/install-native.mjs';

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
    : new Response(new ReadableStream({ cancel() { cancelled = true; } }), { headers: { 'Content-Length': String(33 * 1024 * 1024) } }),
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
    ['linux', 'x64', 'x86_64-unknown-linux-musl'], ['linux', 'arm64', 'aarch64-unknown-linux-musl'],
    ['darwin', 'x64', 'x86_64-apple-darwin'], ['darwin', 'arm64', 'aarch64-apple-darwin'],
    ['win32', 'x64', 'x86_64-pc-windows-msvc'],
  ]) {
    const release = nativeRelease(root, platform, arch);
    assert.equal(release.target, target);
    assert.equal(release.url.endsWith('/native-v0.1.0'), true);
    assert.equal(release.executable.endsWith('.exe'), platform === 'win32');
    assert.equal(path.basename(release.destination), `${platform}-${arch}`);
  }
  assert.throws(() => nativeRelease(root, 'linux', 'riscv64'), /native:build/);
});
