#!/usr/bin/env bun
import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=fileURLToPath(new URL('..',import.meta.url));
const args=process.argv.slice(2);
if(args.includes('--help')){
  console.log('Usage: bun run setup [--backend-only] [--full]\nPrepares locked Rust and Bun dependencies. --backend-only skips UI packages; --full includes deployment tooling.');
  process.exit(0);
}
if(args.some(arg=>!['--backend-only','--full'].includes(arg)))throw Error('Run bun run setup -- --help for options.');
const version=readFileSync(path.join(root,'.bun-version'),'utf8').trim();
if(process.versions.bun!==version)throw Error(`项目需要 Bun ${version}。`);
const run=(command,argv,cwd=root)=>execFileSync(command,argv,{cwd,stdio:'inherit'});
run('cargo',['fetch','--locked','--manifest-path',path.join(root,'runtime-core/Cargo.toml')]);
run(process.execPath,['install','--frozen-lockfile','--ignore-scripts',...(args.includes('--full')?[]:['--production'])]);
if(!args.includes('--backend-only'))run(process.execPath,['run','ui:install']);
console.log('依赖已准备。运行 bun run native:build；需要网页预览时运行 bun run ui:prepare。');
