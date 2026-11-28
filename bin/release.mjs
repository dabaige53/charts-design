#!/usr/bin/env bun
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export function releaseVersion(input, current) {
  const version = input?.replace(/^v/, '');
  const pattern = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
  if (!pattern.test(version ?? '') || !pattern.test(current)) {
    throw new Error('版本号必须为正式版本，例如 1.2.1。');
  }
  const next = version.split('.').map(BigInt);
  const previous = current.split('.').map(BigInt);
  const difference = next.findIndex((part, index) => part !== previous[index]);
  if (difference < 0 || next[difference] < previous[difference]) {
    throw new Error(`新版本必须高于 ${current}。`);
  }
  return version;
}

export function release(root, args) {
  const dryRun = args.includes('--dry-run');
  const positional = args.filter(arg => arg !== '--dry-run');
  if (positional.length !== 1) throw new Error('用法：bun run release -- 1.2.1 [--dry-run]');
  const git = (...argv) => execFileSync('git', argv, { cwd: root, encoding: 'utf8' }).trim();
  const packagePath = resolve(root, 'package.json');
  const pkg = JSON.parse(readFileSync(packagePath, 'utf8'));
  const version = releaseVersion(positional[0], pkg.version);
  const cargoPath = resolve(root, 'runtime-core/Cargo.toml');
  const lockPath = resolve(root, 'runtime-core/Cargo.lock');
  const cargo = readFileSync(cargoPath, 'utf8');
  const lock = readFileSync(lockPath, 'utf8');
  const packageVersion = /(\[package\][\s\S]*?\nversion\s*=\s*")([^"]+)(")/;
  const lockedVersion = /(\[\[package\]\]\s*\nname = "charts-design-core"\s*\nversion = ")([^"]+)(")/;
  if (cargo.match(packageVersion)?.[2] !== pkg.version || lock.match(lockedVersion)?.[2] !== pkg.version) {
    throw new Error('package.json、Cargo.toml 和 Cargo.lock 必须使用同一产品版本。');
  }
  const tag = `v${version}`;
  const tags = [tag, `server-${tag}`];
  const refs = tags.map(name => `refs/tags/${name}`);
  if (git('status', '--porcelain')) throw new Error('请先提交全部待发布代码；发布脚本不会代为提交工作区改动。');
  git('symbolic-ref', '--quiet', 'HEAD');
  if (git('tag', '--list', ...tags) || git('ls-remote', '--tags', 'origin', ...refs)) {
    throw new Error(`标签 ${tags.join(' 或 ')} 已存在。请使用新版本号。`);
  }
  for (const workflow of ['native-release.yml', 'server-release.yml']) {
    if (!git('ls-files', `.github/workflows/${workflow}`)) {
      throw new Error(`请先提交发布工作流 ${workflow}。`);
    }
  }
  console.log(`${dryRun ? '预览' : '发布'} ${tags.join('、')}。GitHub Actions 将构建原生安装包和自有服务器镜像。`);
  if (dryRun) return;
  pkg.version = version;
  writeFileSync(packagePath, `${JSON.stringify(pkg, null, 2)}\n`);
  writeFileSync(cargoPath, cargo.replace(packageVersion, (_, prefix, _old, suffix) => prefix + version + suffix));
  writeFileSync(lockPath, lock.replace(lockedVersion, (_, prefix, _old, suffix) => prefix + version + suffix));
  const files = ['package.json', 'runtime-core/Cargo.toml', 'runtime-core/Cargo.lock'];
  git('add', '--', ...files);
  git('commit', '-m', `release: ${tag}`, '--', ...files);
  for (const name of tags) git('tag', '-a', name, '-m', `Release ${name}`);
  try {
    // Publish both tags together without triggering the branch workflow.
    git('push', '--atomic', 'origin', ...refs);
  } catch {
    throw new Error(`标签已在本地创建。检查远端后重试：git push --atomic origin ${refs.join(' ')}`);
  }
  console.log(`已推送 ${tags.join('、')}。请在 GitHub Actions 查看原生安装包和自有服务器镜像的构建结果。`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { release(resolve(fileURLToPath(new URL('..', import.meta.url))), process.argv.slice(2)); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
