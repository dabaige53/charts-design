#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');

function pythonRuntime() {
  const configPath = path.join(root, '.charts-runtime-env.json');
  const config = fs.existsSync(configPath) ? JSON.parse(fs.readFileSync(configPath, 'utf8')) : {};
  const python = process.env.PYTHON || config.python || 'python3';
  const dependencies = config.dependencies ? path.resolve(root, config.dependencies) : null;
  const env = {...process.env, PYTHONPATH: [root, dependencies, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter)};
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
