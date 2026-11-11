#!/usr/bin/env bun
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');

function pythonRuntime() {
  const configPath = path.join(root, '.charts-runtime-env.json');
  const config = fs.existsSync(configPath) ? JSON.parse(fs.readFileSync(configPath, 'utf8')) : {};
  const projectPython = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const configuredPython = config.python && (config.python.includes('/') || config.python.includes('\\'))
    ? path.resolve(root, config.python) : config.python;
  const python = process.env.PYTHON || configuredPython || (fs.existsSync(projectPython) ? projectPython : null);
  if (!python) throw Error('Python 环境未准备。请在仓库运行 bun run setup；安装包需显式设置 PYTHON。');
  // An explicit interpreter owns its dependencies; never mix it with legacy target installs.
  const dependencies = !process.env.PYTHON && config.dependencies ? path.resolve(root, config.dependencies) : null;
  const env = {...process.env, PYTHON: python, PYTHONNOUSERSITE: '1',
    PYTHONPATH: [root, dependencies, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter)};
  if (config.cache) {
    const cache = path.resolve(root, config.cache);
    env.MPLCONFIGDIR ||= path.join(cache, 'matplotlib');
    env.XDG_CACHE_HOME ||= cache;
  }
  if (config.browsers) env.PLAYWRIGHT_BROWSERS_PATH ||= path.resolve(root, config.browsers);
  return {python, env, isolated: Boolean(config.isolated && dependencies)};
}

function runPython(args) {
  const {python, env, isolated} = pythonRuntime();
  const child = spawnSync(python, [...(isolated ? ['-S'] : []), ...args], {stdio: 'inherit', env});
  if (child.error) { console.error(child.error.message); process.exit(1); }
  process.exit(child.status ?? 1);
}

module.exports = {pythonRuntime, runPython};
if (require.main === module) runPython(process.argv.slice(2));
