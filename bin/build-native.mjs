#!/usr/bin/env bun
import { execFileSync } from 'node:child_process';
import { copyFileSync, mkdirSync, chmodSync, mkdtempSync, renameSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { nativeVersion } from './install-native.mjs';

const root = fileURLToPath(new URL('..', import.meta.url));
const native = path.join(root, 'runtime-core');
const target = path.join(native, 'target');
const messages = execFileSync('cargo', ['build', '--release', '--locked', '--target-dir', target, '--message-format=json'],
  { cwd: native, env: {...process.env, CARGO_BUILD_JOBS: process.env.CARGO_BUILD_JOBS || '2',
    ...(process.platform !== 'win32' ? {CXXFLAGS: process.env.CXXFLAGS || '-g0'} : {})},
    encoding: 'utf8', maxBuffer: 8 * 1024 * 1024, stdio: ['inherit', 'pipe', 'inherit'] });
const artifact = messages.trim().split('\n').map(line => JSON.parse(line)).findLast(message =>
  message.reason === 'compiler-artifact' && message.target?.name === 'charts-design-core' && message.executable);
if (!artifact) throw Error('Cargo 未返回可执行程序；原安装保持不变。');
const name = 'charts-design-core' + (process.platform === 'win32' ? '.exe' : '');
const destination = path.join(root, 'runtime-core/native', `${process.platform}-${process.arch}`);
mkdirSync(destination, { recursive: true });
const staging = mkdtempSync(path.join(destination, '.build-'));
try {
  const candidate = path.join(staging, name);
  copyFileSync(artifact.executable, candidate);
  chmodSync(candidate, 0o755);
  const reported = execFileSync(candidate, ['--version'], { encoding: 'utf8', timeout: 10_000 }).trim();
  if (reported !== `charts-design-core ${nativeVersion(root)}`) throw Error('原生构建版本不匹配，原安装保持不变。');
  renameSync(candidate, path.join(destination, name));
} finally { rmSync(staging, { recursive: true, force: true }); }
console.log('Rust Runtime已准备；Runtime 会直接使用该二进制，不在请求中运行 Cargo。');
