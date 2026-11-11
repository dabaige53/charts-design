import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// Unknown paths run the full workflow. Only documentation-only changes skip it.
export function requiresTests(paths) {
  return paths.some(file => !file.startsWith('docs/') && !['README.md', 'AGENTS.md', 'LICENSE'].includes(file));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const paths = readFileSync(0, 'utf8').split('\0').filter(Boolean);
  console.log(`tests=${requiresTests(paths)}`);
}
