// Build freshness is checked only when a local preview or installation needs UI.
import { createHash } from 'node:crypto';
import { readdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../..', import.meta.url));

function files(directory) {
  return readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name, 'en')).flatMap(entry => {
    const full = path.join(directory, entry.name);
    return entry.isDirectory() ? files(full) : [full];
  });
}

export function sourceId(repository) {
  const ui = path.join(repository, 'runtime-ui');
  const inputs = [
    ...['src', 'scripts', 'fixtures'].flatMap(dir => files(path.join(ui, dir))),
    ...readdirSync(ui).filter(name => /\.(json|yaml|[cm]?js|ts)$/.test(name)).map(name => path.join(ui, name)),
    ...files(path.join(repository, 'dashboard_runtime/web')).filter(name => name.endsWith('.mjs') && !name.includes(`${path.sep}dist${path.sep}`)),
  ].sort();
  const hash = createHash('sha256');
  for (const file of inputs) hash.update(path.relative(repository, file)).update('\0').update(readFileSync(file)).update('\0');
  return hash.digest('hex');
}

function outputIds(repository) {
  const dist = path.join(repository, 'runtime-ui/dist');
  return Object.fromEntries(files(dist).filter(file => path.basename(file) !== 'build-state.json')
    .map(file => [path.relative(dist, file), createHash('sha256').update(readFileSync(file)).digest('hex')]));
}

export function recordBuild(repository) {
  const state = { sourceId: sourceId(repository), outputs: outputIds(repository) };
  writeFileSync(path.join(repository, 'runtime-ui/dist/build-state.json'), JSON.stringify(state, null, 2) + '\n');
}

export function isCurrent(repository) {
  const statePath = path.join(repository, 'runtime-ui/dist/build-state.json');
  if (!existsSync(statePath)) return false;
  const state = JSON.parse(readFileSync(statePath, 'utf8'));
  if (state.sourceId !== sourceId(repository)) return false;
  return JSON.stringify(state.outputs) === JSON.stringify(outputIds(repository));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv[2] !== '--record') throw Error('Use --record after a successful complete build.');
  recordBuild(root);
}
