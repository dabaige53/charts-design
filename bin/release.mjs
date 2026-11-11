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
  const tag = `v${version}`;
  if (git('status', '--porcelain')) throw new Error('请先提交全部待发布代码；发布脚本不会代为提交工作区改动。');
  git('symbolic-ref', '--quiet', 'HEAD');
  if (git('tag', '--list', tag) || git('ls-remote', '--tags', 'origin', `refs/tags/${tag}`)) {
    throw new Error(`标签 ${tag} 已存在；请使用新版本号。`);
  }
  if (!git('ls-files', '.github/workflows/cloudbase-release.yml')) {
    throw new Error('请先提交 CloudBase 发布工作流。');
  }
  console.log(`${dryRun ? '预览' : '发布'} ${tag}：更新 package.json → 创建提交与标签 → 推送标签 → GitHub CI 部署。`);
  if (dryRun) return;
  pkg.version = version;
  writeFileSync(packagePath, `${JSON.stringify(pkg, null, 2)}\n`);
  git('add', '--', 'package.json');
  git('commit', '-m', `release: ${tag}`, '--', 'package.json');
  git('tag', '-a', tag, '-m', `Release ${tag}`);
  try {
    // Only the tag is pushed: a branch push would also trigger the general test workflow.
    git('push', 'origin', `refs/tags/${tag}`);
  } catch {
    throw new Error(`标签已在本地创建，推送未确认成功。检查远端后重试：git push origin refs/tags/${tag}`);
  }
  console.log(`已推送 ${tag}。请在 GitHub Actions 的 CloudBase release 查看部署结果。`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { release(resolve(fileURLToPath(new URL('..', import.meta.url))), process.argv.slice(2)); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
