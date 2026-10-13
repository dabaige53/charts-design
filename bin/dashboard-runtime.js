#!/usr/bin/env node
const {runPython} = require('./python-runtime.js');
const args = process.argv.slice(2);
if (args.includes('mcp')) require('./mcp-runtime.js').runMcp(args);
else runPython(['-m', 'dashboard_runtime', ...args]);
