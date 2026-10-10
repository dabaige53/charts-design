#!/usr/bin/env node
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const root=path.resolve(__dirname,'..');
const child=spawnSync(process.env.PYTHON || 'python3',['-m','dashboard_runtime',...process.argv.slice(2)],{
  stdio:'inherit',env:{...process.env,PYTHONPATH:[root,process.env.PYTHONPATH].filter(Boolean).join(path.delimiter)}
});
if(child.error){console.error(child.error.message);process.exit(1);}
process.exit(child.status ?? 1);
