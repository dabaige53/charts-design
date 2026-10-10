import { build } from 'esbuild';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
await build({entryPoints:[path.join(root,'entry.mjs')],bundle:true,format:'iife',target:['es2022'],
  outfile:path.join(root,'../dashboard_runtime/web/dist/app.js'),minify:true,legalComments:'eof',
  nodePaths:[path.join(root,'node_modules')],loader:{'.woff2':'dataurl','.woff':'dataurl'}});
