#!/usr/bin/env bun
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, copyFileSync, mkdtempSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { tmpdir } from 'node:os';

const root = fileURLToPath(new URL('..', import.meta.url));
const args = process.argv.slice(2);
if (args.includes('--help')) {
  console.log('Usage: bun run setup [--backend-only] [--full]\n--backend-only skips UI packages. --full adds optional Python backends and the CloudBase CLI.');
  process.exit(0);
}
if (args.some(arg => !['--full', '--backend-only'].includes(arg))) throw Error('Run bun run setup -- --help for options.');
const full = args.includes('--full');
const backendOnly = args.includes('--backend-only');
const version = readFileSync(path.join(root, '.bun-version'), 'utf8').trim();
if (process.versions.bun !== version) throw Error(`项目需要 Bun ${version}，当前为 ${process.versions.bun ?? '非 Bun 运行时'}。`);
if (!Bun.which('uv')) throw Error('请安装 pyproject.toml 指定版本的 uv，再运行 bun run setup。');
const configPath = path.join(root, '.charts-runtime-env.json');
const previous = existsSync(configPath) ? JSON.parse(readFileSync(configPath, 'utf8')) : {};
const env = {
  ...process.env,
  BUN_INSTALL_CACHE_DIR: process.env.BUN_INSTALL_CACHE_DIR || path.join(root, '.runtime-cache', 'bun'),
};
if (process.platform === 'darwin') env.TMPDIR = '/private/tmp';
const run = (command, args, cwd = root) => execFileSync(command, args, { cwd, stdio: 'inherit', env });
const extras = full ? ['--all-extras'] : ['--extra', 'mcp', '--extra', 'test', '--inexact'];
console.log('准备锁定的 Python 环境。');
run('uv', ['sync', '--locked', ...extras, '--no-install-project', '--python', readFileSync(path.join(root, '.python-version'), 'utf8').trim()]);
console.log('准备锁定的 Bun 依赖。');
run(process.execPath, ['install', '--frozen-lockfile', '--ignore-scripts', ...(full ? [] : ['--production'])]);
if (!backendOnly) run(process.execPath, ['run', 'ui:install']);
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
console.log('开发环境准备完成。按需运行 bun run ui:prepare。');
