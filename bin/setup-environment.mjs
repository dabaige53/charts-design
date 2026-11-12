#!/usr/bin/env bun
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync, copyFileSync, mkdtempSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { tmpdir } from 'node:os';

const root = fileURLToPath(new URL('..', import.meta.url));
const version = readFileSync(path.join(root, '.bun-version'), 'utf8').trim();
if (process.versions.bun !== version) throw Error(`项目需要 Bun ${version}，当前为 ${process.versions.bun ?? '非 Bun 运行时'}。`);
const env = { ...process.env, UV_CACHE_DIR: path.join(root, '.runtime-cache/uv'),
  BUN_INSTALL_CACHE_DIR: path.join(root, '.runtime-cache/bun') };
mkdirSync(env.UV_CACHE_DIR, { recursive: true });
mkdirSync(env.BUN_INSTALL_CACHE_DIR, { recursive: true });
const run = (command, args, cwd = root) => execFileSync(command, args, { cwd, env, stdio: 'inherit' });
run('uv', ['sync', '--locked', '--all-extras', '--no-install-project', '--python', readFileSync(path.join(root, '.python-version'), 'utf8').trim()]);
run(process.execPath, ['install', '--frozen-lockfile']);
run(process.execPath, ['install', '--frozen-lockfile'], path.join(root, 'runtime-ui'));
const configPath = path.join(root, '.charts-runtime-env.json');
const previous = existsSync(configPath) ? JSON.parse(readFileSync(configPath, 'utf8')) : {};
const config = { ...previous, python: process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python',
  isolated: false, cache: '.runtime-cache' };
delete config.dependencies;
if (JSON.stringify(config) !== JSON.stringify(previous)) {
  if (existsSync(configPath)) {
    const backup = mkdtempSync(path.join(process.platform === 'darwin' ? '/private/tmp' : tmpdir(), 'charts-environment-'));
    copyFileSync(configPath, path.join(backup, '.charts-runtime-env.json'));
    console.log(`原本机配置保存在 ${backup}`);
  }
  writeFileSync(configPath, JSON.stringify(config, null, 2) + '\n');
}
console.log('项目依赖已安装：Python 使用 .venv，JavaScript/TypeScript 使用 Bun；未运行测试或 UI 构建。');
