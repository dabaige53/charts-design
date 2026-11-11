import assert from 'node:assert/strict';
import { test } from 'node:test';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { release, releaseVersion } from '../../bin/release.mjs';
import { cloudrunDeployArgs, completedGrayRelease, includeSource, matchesRelease, runtimeConfig, taskReady, validateTag } from '../../bin/cloudbase-deploy.mjs';

// @wu-test type=boundary | scope=releaseVersion | protects=重复降级或非法版本创建发布标签
test('release version must be a newer stable semantic version', () => {
  assert.equal(releaseVersion('v1.3.0', '1.2.9'), '1.3.0');
  for (const value of ['1.2.9', '1.2.8', '01.3.0', '1.3.0-beta', '1.3', '1.3.0;echo']) {
    assert.throws(() => releaseVersion(value, '1.2.9'));
  }
});

// @wu-test type=boundary | scope=validateTag | protects=标签与构建版本不一致仍进入部署
test('deployment only accepts an exact stable package version tag', () => {
  assert.equal(validateTag('v1.2.1', '1.2.1'), 'v1.2.1');
  for (const value of ['main', '1.2.1', 'v1.2.0', 'v1.2.1-rc.1']) {
    assert.throws(() => validateTag(value, '1.2.1'));
  }
});

// @wu-test type=boundary | scope=CloudBase源码包 | protects=本地凭据缓存及设计归档进入云端源码包
test('source package excludes private configuration and generated files', () => {
  for (const name of ['runtime-ui/.env', 'bin/dev.env.local', 'bin/key.pem',
    'runtime-ui/node_modules/a.js', 'runtime-ui/dist/app.js', 'docs/design-system/tokens.json',
    '.git/config', 'boards/data.csv', 'dashboard_runtime/__pycache__/a.pyc']) {
    assert.equal(includeSource(name), false, name);
  }
  for (const name of ['runtime-ui/pnpm-lock.yaml', 'runtime-ui/src/main.tsx',
    'dashboard_runtime/server.py', 'package.json', 'skills/executive-charts/SKILL.md']) {
    assert.equal(includeSource(name), true, name);
  }
});

// @wu-test type=behavior | scope=CloudBase发布健康检查 | protects=旧实例健康响应被当作新版本部署成功
test('health check requires both the release version and exact commit', () => {
  const health = { ok: true, release: { version: '1.2.1', commit: 'abc' } };
  assert.equal(matchesRelease(health, '1.2.1', 'abc'), true);
  assert.equal(matchesRelease(health, '1.2.1', 'old'), false);
  assert.equal(matchesRelease(health, '1.2.2', 'abc'), false);
  assert.equal(matchesRelease({ ok: true }, '1.2.1', 'abc'), false);
});

// @wu-test type=behavior | scope=CloudBase环境配置 | protects=发布覆盖线上密钥存储参数或保留旧版本标记
test('deployment preserves runtime settings and replaces release identity', () => {
  const existing = { CHARTS_STORAGE_BACKEND: 'cloudbase', CHARTS_SERVER_SECRET: 'example-secret',
    CUSTOM_SETTING: 'retained', CHARTS_RELEASE_VERSION: 'old' };
  const result = runtimeConfig({ ServerConfig: { EnvParams: JSON.stringify(existing) } }, '1.2.1', 'abc');
  assert.deepEqual(result, { ...existing, CHARTS_RELEASE_VERSION: '1.2.1', CHARTS_RELEASE_COMMIT: 'abc' });
  assert.equal(existing.CHARTS_RELEASE_VERSION, 'old');
  assert.throws(() => runtimeConfig({ ServerConfig: { EnvParams: '{"CHARTS_STORAGE_BACKEND":"local"}' } }, '1.2.1', 'abc'));
});

// @wu-test type=boundary | scope=CloudBase灰度发布检查 | protects=自动完成尚在构建或只承接部分流量的版本
test('only a healthy completed gray release serving all traffic may be finalized', () => {
  const order = { IsReleasing: true, GrayStatus: 'success', TrafficType: 'FLOW', FlowRatio: 100,
    ReleaseVersion: { VersionName: 'service-009', Status: 'normal' } };
  const online = [{ VersionName: 'service-009', FlowRatio: '100' }];
  assert.equal(completedGrayRelease(order, online), true);
  assert.equal(completedGrayRelease({ IsReleasing: false }, online), false);
  assert.throws(() => completedGrayRelease({ ...order, FlowRatio: 50 }, online));
  assert.throws(() => completedGrayRelease({ ...order, GrayStatus: 'running' }, online));
  assert.throws(() => completedGrayRelease(order, [{ ...online[0], VersionName: 'service-007' }]));
});

// @wu-test type=boundary | scope=CloudBase发布任务检查 | protects=新发布取消尚在构建的任务或其他灰度版本
test('active tasks block deployment except the exact completed gray version', () => {
  const task = { Status: 'running', ReleaseType: 'GRAY', VersionName: 'service-009',
    Steps: [{ Name: 'CreateVersion', Status: 'finished' }, { Name: 'GrayRelease', Status: 'running' }] };
  assert.equal(taskReady(task), false);
  assert.equal(taskReady(task, 'service-009'), true);
  assert.equal(taskReady(task, 'service-007'), false);
  assert.equal(taskReady({ ...task, Steps: [{ Name: 'CreateVersion', Status: 'running' }] }, 'service-009'), false);
  assert.equal(taskReady({ Status: 'finished' }), true);
  assert.equal(taskReady(undefined), false);
});

// @wu-test type=regression | scope=CloudBase CI 发布参数 | protects=CI-42976060980 中已有服务的灰度确认提示使无终端发布中断
test('full deployment selects the noninteractive CLI path', () => {
  const args = cloudrunDeployArgs('charts-design-mcp', '/tmp/source', { EXAMPLE: 'value' }, 0, 1);
  assert.ok(args.includes('--yes'), 'CloudBase CLI must skip its separate gray-release prompt');
  assert.ok(args.includes('--force'));
  assert.ok(args.includes('--wait'));
});

function repository(t) {
  const base = mkdtempSync(join(process.platform === 'darwin' ? '/private/tmp' : tmpdir(), 'charts-release-test-'));
  t.after(() => rmSync(base, { recursive: true, force: true }));
  const root = join(base, 'work');
  const remote = join(base, 'remote.git');
  mkdirSync(root);
  const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
  const hooks = join(base, 'hooks');
  mkdirSync(hooks);
  // Synthetic repositories must not execute the developer's machine-wide Git hooks.
  git('-c', `core.hooksPath=${hooks}`, 'init', '--initial-branch=main');
  git('config', 'core.hooksPath', hooks);
  git('config', 'user.email', 'test@example.invalid');
  git('config', 'user.name', 'Release Test');
  git('config', 'commit.gpgsign', 'false');
  git('config', 'tag.gpgsign', 'false');
  git('-c', `core.hooksPath=${hooks}`, 'init', '--bare', remote);
  git('--git-dir', remote, 'config', 'core.hooksPath', hooks);
  git('remote', 'add', 'origin', remote);
  mkdirSync(join(root, '.github/workflows'), { recursive: true });
  writeFileSync(join(root, '.github/workflows/cloudbase-release.yml'), 'name: fixture\n');
  writeFileSync(join(root, 'package.json'), '{"version":"1.2.0"}\n');
  git('add', '.'); git('commit', '-m', 'initial');
  return { root, git };
}

// @wu-test type=integration | scope=版本发布脚本 | protects=发布遗漏版本提交或误推分支触发全量测试
test('release publishes a tag pointing to the version commit, without pushing a branch', t => {
  const { root, git } = repository(t);
  release(root, ['1.2.1']);
  assert.equal(JSON.parse(readFileSync(join(root, 'package.json'))).version, '1.2.1');
  assert.equal(git('rev-parse', 'v1.2.1^{commit}'), git('rev-parse', 'HEAD'));
  assert.match(git('ls-remote', '--tags', 'origin'), /refs\/tags\/v1\.2\.1/);
  assert.equal(git('ls-remote', '--heads', 'origin'), '');
  assert.equal(git('status', '--porcelain'), '');
});

// @wu-test type=boundary | scope=版本发布脚本 | protects=预览修改仓库或未提交代码被静默遗漏
test('dry run leaves Git unchanged and dirty worktree blocks release', t => {
  const { root, git } = repository(t);
  const initial = git('rev-parse', 'HEAD');
  release(root, ['1.2.1', '--dry-run']);
  assert.equal(git('rev-parse', 'HEAD'), initial);
  assert.equal(git('tag', '--list'), '');
  assert.equal(git('status', '--porcelain'), '');
  writeFileSync(join(root, 'unfinished.txt'), 'work');
  assert.throws(() => release(root, ['1.2.1']), /先提交/);
  assert.equal(git('tag', '--list'), '');
});
