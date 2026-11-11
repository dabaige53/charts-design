#!/usr/bin/env node
// Workspace data management; shared React preview is available through the runtime.
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const {pythonRuntime} = require('./python-runtime.js');
const workspaceTool = path.resolve(__dirname, '../skills/executive-charts/scripts/dashboard_workspace.py');
const catalogFile = path.resolve(__dirname, '../skills/executive-charts/references/chart_catalog.json');
const packageFile = path.resolve(__dirname, '../package.json');
const args = process.argv.slice(2);

function help() {
  console.log(`charts-design — workspace data management

Usage:
  charts-design doctor [--json]
  charts-design list
  charts-design dashboard init|import-csv|inspect|validate|meta|add|table ...

The native HTML generators and previous UI have been removed.
Use charts-design-runtime for React previews, exports, versioned data and MCP operations.`);
}

function main() {
  if (!args.length || ['--help', '-h'].includes(args[0])) return help();
  if (args[0] === 'list') {
    console.log(fs.readFileSync(catalogFile, 'utf8'));
    return;
  }
  if (args[0] === 'doctor') {
    const runtime = pythonRuntime();
    const uiBuild = path.resolve(__dirname, '../dashboard_runtime/web/dist/build.json');
    const build = fs.existsSync(uiBuild) ? JSON.parse(fs.readFileSync(uiBuild, 'utf8')) : null;
    const result = {ok: fs.existsSync(workspaceTool), version: JSON.parse(fs.readFileSync(packageFile, 'utf8')).version,
      runtime: {node: process.version, python: runtime.python, uiStatus: build ? 'built' : 'unavailable', uiBuildId: build?.id, offlineGeneration: false},
      paths: {workspaceTool}};
    console.log(args.includes('--json') ? JSON.stringify(result) : `charts-design ${result.version}\nWorkspace: ${result.ok ? 'ready' : 'missing'}\nUI: ${result.runtime.uiStatus}${build ? ' (' + build.id + ')' : ''}`);
    process.exitCode = result.ok ? 0 : 1;
    return;
  }
  if (['dashboard', 'dash'].includes(args[0]) && ['init', 'import-csv', 'inspect', 'validate', 'meta', 'add', 'table'].includes(args[1])) {
    const runtime = pythonRuntime();
    try {
      execFileSync(runtime.python, [...(runtime.isolated ? ['-S'] : []), workspaceTool, ...args.slice(1)],
        {stdio: 'inherit', env: runtime.env});
    } catch (error) {
      process.exitCode = error.status || 1;
    }
    return;
  }
  console.error('This command is unavailable. The native HTML generators and previous UI have been removed.');
  process.exitCode = 1;
}
main();
