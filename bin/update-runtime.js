#!/usr/bin/env bun
// Publish an explicit, reviewed file set; signal workers only after completion.
const fs=require('node:fs');
const path=require('node:path');
const {randomUUID}=require('node:crypto');
const [target,...files]=process.argv.slice(2);
const source=path.resolve(__dirname,'..');
if(!target||!files.length)throw Error('Usage: bun bin/update-runtime.js INSTALL_ROOT FILE...');
const root=path.resolve(target);
if(root===source)throw Error('Installation must differ from source');
if(JSON.parse(fs.readFileSync(path.join(root,'package.json'))).name!=='charts-design')throw Error('Not a charts-design installation');
for(const file of files){
  if(path.isAbsolute(file)||file.split(/[\\/]/).includes('..'))throw Error('Expected package-relative file: '+file);
  if(!fs.statSync(path.join(source,file)).isFile())throw Error('Expected file: '+file);
}
for(const file of files){
  const dest=path.join(root,file);
  fs.mkdirSync(path.dirname(dest),{recursive:true});
  fs.copyFileSync(path.join(source,file),dest);
}
const generation=randomUUID();
const temp=path.join(root,'.runtime-generation.next');
fs.writeFileSync(temp,generation+'\n');
fs.renameSync(temp,path.join(root,'.runtime-generation'));
console.log(JSON.stringify({installation:root,files:files.length,generation}));
