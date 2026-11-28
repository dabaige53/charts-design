import assert from 'node:assert/strict';
import { test, afterEach } from 'bun:test';
const temporaryDirectories = [];
afterEach(() => { for (const dir of temporaryDirectories.splice(0)) rmSync(dir, { recursive: true, force: true }); });
import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { release, releaseVersion } from '../../bin/release.mjs';

// @wu-test type=boundary | scope=releaseVersion | protects=重复降级或非法版本创建发布标签
test('release version must be a newer stable semantic version', () => {
  assert.equal(releaseVersion('v1.3.0', '1.2.9'), '1.3.0');
  for (const value of ['1.2.9', '1.2.8', '01.3.0', '1.3.0-beta', '1.3', '1.3.0;echo']) {
    assert.throws(() => releaseVersion(value, '1.2.9'));
  }
});

function repository() {
  const base = mkdtempSync(join(process.platform === 'darwin' ? '/private/tmp' : tmpdir(), 'charts-release-test-'));
  temporaryDirectories.push(base);
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
  for (const name of ['native-release.yml', 'server-release.yml']) {
    writeFileSync(join(root, '.github/workflows', name), 'name: fixture\n');
  }
  writeFileSync(join(root, 'package.json'), '{"version":"1.2.0"}\n');
  mkdirSync(join(root, 'runtime-core'));
  writeFileSync(join(root, 'runtime-core/Cargo.toml'), '[package]\nname = "charts-design-core"\nversion = "1.2.0"\n');
  writeFileSync(join(root, 'runtime-core/Cargo.lock'), 'version = 4\n\n[[package]]\nname = "charts-design-core"\nversion = "1.2.0"\n');
  git('add', '.'); git('commit', '-m', 'initial');
  return { root, git };
}

// @wu-test type=integration | scope=版本发布脚本 | protects=原生和服务器发布指向不同版本或误推分支触发通用 CI
test('release publishes native and server tags at the same version commit, without pushing a branch', () => {
  const { root, git } = repository();
  release(root, ['1.2.1']);
  assert.equal(JSON.parse(readFileSync(join(root, 'package.json'))).version, '1.2.1');
  assert.match(readFileSync(join(root, 'runtime-core/Cargo.toml'), 'utf8'), /version = "1\.2\.1"/);
  assert.match(readFileSync(join(root, 'runtime-core/Cargo.lock'), 'utf8'), /name = "charts-design-core"\nversion = "1\.2\.1"/);
  assert.equal(git('rev-parse', 'v1.2.1^{commit}'), git('rev-parse', 'HEAD'));
  assert.equal(git('rev-parse', 'server-v1.2.1^{commit}'), git('rev-parse', 'HEAD'));
  const remoteTags = git('ls-remote', '--refs', '--tags', 'origin').split('\n').map(line => line.split('\t')[1]);
  assert.deepEqual(remoteTags, ['refs/tags/server-v1.2.1', 'refs/tags/v1.2.1']);
  assert.equal(git('ls-remote', '--heads', 'origin'), '');
  assert.equal(git('status', '--porcelain'), '');
});

// @wu-test type=boundary | scope=product version | protects=npm downloads a different native runtime after a release
test('release rejects divergent npm and Rust versions before changing files', () => {
  const {root, git} = repository();
  writeFileSync(join(root, 'runtime-core/Cargo.toml'), '[package]\nname = "charts-design-core"\nversion = "0.1.1"\n');
  git('add', '.'); git('commit', '-m', 'divergent version');
  assert.throws(() => release(root, ['1.2.1']), /同一产品版本/);
  assert.equal(JSON.parse(readFileSync(join(root, 'package.json'))).version, '1.2.0');
  assert.equal(git('tag', '--list'), '');
});

// @wu-test type=boundary | scope=版本发布脚本 | protects=预览修改仓库或未提交代码被静默遗漏
test('dry run leaves Git unchanged and dirty worktree blocks release', () => {
  const { root, git } = repository();
  const initial = git('rev-parse', 'HEAD');
  release(root, ['1.2.1', '--dry-run']);
  assert.equal(git('rev-parse', 'HEAD'), initial);
  assert.equal(git('tag', '--list'), '');
  assert.equal(git('status', '--porcelain'), '');
  writeFileSync(join(root, 'unfinished.txt'), 'work');
  assert.throws(() => release(root, ['1.2.1']), /先提交/);
  assert.equal(git('tag', '--list'), '');
});
