// Resolve the one native runtime. Installation and builds are explicit operations.
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
function nativeCommand(args) {
  if (args.some(arg => arg === '--help' || arg === '-h')) return null;
  const globals = new Set(['--project-root', '--runtime-root', '--root', '--sources']);
  for (let index = 0; index < args.length; index++) {
    const argument = args[index];
    if (argument === '--') return null;
    const option = argument.split('=', 1)[0];
    if (globals.has(option)) {
      if (!argument.includes('=')) index++;
      continue;
    }
    return argument;
  }
  return null;
}
function nativeRuntime() {
  const root = path.resolve(__dirname, '..');
  const name = `charts-design-core${process.platform === 'win32' ? '.exe' : ''}`;
  const binary = process.env.CHARTS_CORE_BIN ? path.resolve(process.env.CHARTS_CORE_BIN)
    : path.join(root, 'runtime-core/native', `${process.platform}-${process.arch}`, name);
  if (!fs.existsSync(binary)) throw Error('Rust Runtime 尚未安装。运行 charts-design-runtime install-native，源码开发运行 bun run native:build。');
  return {binary, env: {...process.env, CHARTS_PACKAGE_ROOT: root,
    CHARTS_UI_DIST: process.env.CHARTS_UI_DIST || path.join(root, 'runtime-ui/dist')}};
}
function runNative(args) {
  const {binary, env} = nativeRuntime();
  const child = spawn(binary, args, {env, stdio: 'inherit'});
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
  child.on('error', error => {console.error(error.message); process.exitCode = 1;});
  child.on('exit', (code, signal) => {process.exitCode = code ?? (signal ? 1 : 0);});
}
module.exports = {nativeCommand, nativeRuntime, runNative};
