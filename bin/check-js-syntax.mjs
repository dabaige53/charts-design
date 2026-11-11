#!/usr/bin/env bun
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const parser = new Bun.Transpiler({ loader: 'js' });
for (const directory of ['bin', 'runtime-ui/scripts']) {
  for (const file of readdirSync(path.join(root, directory))) {
    if (!/\.[cm]?js$/.test(file)) continue;
    const name = path.join(directory, file);
    try { parser.transformSync(readFileSync(path.join(root, name), 'utf8')); }
    catch (error) { throw new Error(`JavaScript syntax: ${name}`, { cause: error }); }
  }
}
console.log('JavaScript syntax parsed without executing project scripts.');
