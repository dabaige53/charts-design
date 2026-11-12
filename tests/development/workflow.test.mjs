import assert from 'node:assert/strict';
import { test, afterEach } from 'bun:test';
const temporaryDirectories = [];
afterEach(() => { for (const dir of temporaryDirectories.splice(0)) rmSync(dir, { recursive: true, force: true }); });
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { requiresTests } from '../../bin/ci-scope.mjs';
import { isCurrent, recordBuild } from '../../runtime-ui/scripts/build-state.mjs';

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), 'charts-build-'));
  temporaryDirectories.push(root);
  for (const dir of ['runtime-ui/src', 'runtime-ui/scripts', 'runtime-ui/fixtures', 'runtime-ui/dist', 'dashboard_runtime/web']) {
    mkdirSync(path.join(root, dir), { recursive: true });
  }
  writeFileSync(path.join(root, 'runtime-ui/src/app.ts'), 'export const value = 1;');
  writeFileSync(path.join(root, 'runtime-ui/bun.lock'), '{}');
  writeFileSync(path.join(root, 'runtime-ui/dist/app.js'), 'compiled');
  return root;
}

// @wu-test type=behavior | scope=CI范围 | protects=纯文档触发构建或源码变更跳过测试
test('only documentation changes skip the complete checks', () => {
  assert.equal(requiresTests(['docs/operations/testing.md', 'README.md']), false);
  for (const file of ['runtime-ui/src/app.tsx', 'dashboard_runtime/service.py', 'skills/analytical-reports/SKILL.md', '.github/workflows/dashboard-runtime.yml', 'new-config.json']) {
    assert.equal(requiresTests(['docs/README.md', file]), true, file);
  }
});

// @wu-test type=behavior | scope=UI资源复用 | protects=无改动或仅后端改动时重复构建UI
test('complete unchanged resources survive unrelated backend edits', () => {
  const root = fixture();
  assert.equal(isCurrent(root), false);
  recordBuild(root);
  writeFileSync(path.join(root, 'dashboard_runtime/service.py'), '# backend only');
  assert.equal(isCurrent(root), true);
});

// @wu-test type=boundary | scope=UI资源复用 | protects=源码锁文件或共享Worker变更后复用旧UI
test('build inputs invalidate existing resources', () => {
  const root = fixture();
  for (const file of ['runtime-ui/src/app.ts', 'runtime-ui/bun.lock', 'dashboard_runtime/web/worker.mjs', 'runtime-ui/scripts/build.mjs']) {
    recordBuild(root);
    writeFileSync(path.join(root, file), `changed ${file}`);
    assert.equal(isCurrent(root), false, file);
  }
});

// @wu-test type=boundary | scope=UI资源复用 | protects=产物缺失或被改写后继续交付
test('missing or changed output requires a rebuild', () => {
  const root = fixture();
  recordBuild(root);
  writeFileSync(path.join(root, 'runtime-ui/dist/app.js'), 'damaged');
  assert.equal(isCurrent(root), false);
  recordBuild(root);
  rmSync(path.join(root, 'runtime-ui/dist/app.js'));
  assert.equal(isCurrent(root), false);
});
