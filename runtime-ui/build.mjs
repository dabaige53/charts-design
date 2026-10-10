import { build } from 'esbuild';
import { parse } from 'acorn';
import postcss from 'postcss';
import tailwind from 'tailwindcss';
import fs from 'node:fs/promises';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
execFileSync(process.env.PYTHON||'python3',[path.join(root,'extract-original.py')],{stdio:'inherit'});
const raw=await fs.readFile(path.join(root,'generated/original-engine.raw.mjs'),'utf8');
const replacements=[];
function walk(node){
  if(!node||typeof node!=='object')return;
  if(node.type==='AssignmentExpression'&&node.operator==='='&&node.left.type==='MemberExpression'&&node.left.property.name==='innerHTML'){
    replacements.push([node.start,node.end,`setOriginalHtml(${raw.slice(node.left.object.start,node.left.object.end)}, ${raw.slice(node.right.start,node.right.end)})`]);return;
  }
  for(const val of Object.values(node)){if(Array.isArray(val))val.forEach(walk);else if(val&&typeof val==='object')walk(val);}
}
walk(parse(raw,{ecmaVersion:'latest',sourceType:'module'}));
let source=raw;for(const [start,end,value]of replacements.sort((a,b)=>b[0]-a[0]))source=source.slice(0,start)+value+source.slice(end);
await fs.writeFile(path.join(root,'generated/original-engine.mjs'),source);
const config={safelist:['text-left','text-right','text-center'],content:[path.join(root,'generated/original-engine.raw.mjs')],theme:{extend:{
  colors:{primary:'#123B5D','primary-strong':'#0B2A42','primary-soft':'#DCE8F0',ink:'#17212B','ink-muted':'#52606D','ink-subtle':'#7B8794',positive:'#A4453C',negative:'#2F6B55',attention:'#9A6A18',gridline:'#E6EAED',rule:'#C9D1D8'},
  fontFamily:{sans:['Inter','-apple-system','BlinkMacSystemFont','PingFang SC','Segoe UI','sans-serif'],mono:['JetBrains Mono','Menlo','Monaco','Consolas','monospace']},
  opacity:{6:'.06',8:'.08',15:'.15'},zIndex:{60:'60'},boxShadow:{'2xs':'0 1px 2px rgb(0 0 0 / 0.03)',xs:'0 1px 2px rgb(0 0 0 / 0.05)'}
}}};
const utilities=(await postcss([tailwind(config)]).process('@tailwind base;\n@tailwind components;\n@tailwind utilities;',{from:undefined})).css;
const base=await fs.readFile(path.join(root,'generated/original-base.css'),'utf8');
const adapt=await fs.readFile(path.join(root,'../dashboard_runtime/web/original-adapter.css'),'utf8');
await fs.writeFile(path.join(root,'generated/original-style.mjs'),'export default '+JSON.stringify(utilities+'\n'+base+'\n'+(await fs.readFile(path.join(root,'../dashboard_runtime/web/icons.css'),'utf8'))+'\n'+adapt)+';\n');
await build({entryPoints:[path.join(root,'entry.mjs')],bundle:true,format:'iife',target:['es2022'],
  outfile:path.join(root,'../dashboard_runtime/web/dist/app.js'),minify:true,legalComments:'eof',
  nodePaths:[path.join(root,'node_modules')],loader:{'.woff2':'dataurl','.woff':'dataurl'}});
console.log('Reused original sources; sanitized HTML sinks:',replacements.length);
