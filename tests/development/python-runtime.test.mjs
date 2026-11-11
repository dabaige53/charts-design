import { test, afterEach } from 'bun:test';
import assert from 'node:assert/strict';
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import path from 'node:path';

const require = createRequire(import.meta.url);
const temporaryDirectories = [];
const originalPython = process.env.PYTHON;
afterEach(() => {
  if (originalPython === undefined) delete process.env.PYTHON;
  else process.env.PYTHON = originalPython;
  for (const dir of temporaryDirectories.splice(0)) rmSync(dir, { recursive: true, force: true });
});

function fixture(config) {
  const root = mkdtempSync(path.join(tmpdir(), 'charts-python-'));
  temporaryDirectories.push(root);
  mkdirSync(path.join(root, 'bin'));
  copyFileSync(new URL('../../bin/python-runtime.js', import.meta.url), path.join(root, 'bin/python-runtime.js'));
  if (config) writeFileSync(path.join(root, '.charts-runtime-env.json'), JSON.stringify(config));
  return { root, runtime: require(path.join(root, 'bin/python-runtime.js')).pythonRuntime };
}

// @wu-test type=boundary | scope=Python解释器选择 | protects=显式解释器被旧target依赖和禁用site选项污染
test('explicit interpreter does not inherit legacy dependency isolation', () => {
  const { runtime } = fixture({ python: '/legacy/python', dependencies: '.mcp-test-deps', isolated: true });
  process.env.PYTHON = '/selected/python';
  const result = runtime();
  assert.equal(result.python, '/selected/python');
  assert.equal(result.isolated, false);
  assert.equal(result.env.PYTHONPATH.includes('.mcp-test-deps'), false);
  assert.equal(result.env.PYTHON, '/selected/python');
});

// @wu-test type=behavior | scope=Python解释器选择 | protects=相对解释器路径随调用目录改变
test('configured interpreter paths resolve against the package root', () => {
  delete process.env.PYTHON;
  const { root, runtime } = fixture({ python: '.venv/bin/python' });
  assert.equal(runtime().python, path.join(root, '.venv/bin/python'));
});

// @wu-test type=boundary | scope=Python环境初始化 | protects=未安装环境时静默使用系统Python或忽略现有venv
test('clean checkouts require setup and use the project venv once present', () => {
  delete process.env.PYTHON;
  const { root, runtime } = fixture();
  assert.throws(runtime, /bun run setup/);
  const executable = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  mkdirSync(path.dirname(executable), { recursive: true });
  writeFileSync(executable, '');
  assert.equal(runtime().python, executable);
});
