import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { isCurrent } from './build-state.mjs';

const root = fileURLToPath(new URL('../..', import.meta.url));
const args = process.argv.slice(2);
if (args.some(arg => arg !== '--force')) throw Error('Usage: npm run ui:prepare -- [--force]');
if (args.includes('--force') || !isCurrent(root)) {
  console.log('UI sources or outputs changed; building once for this local delivery.');
  execFileSync('npm', ['run', 'ui:build'], { cwd: root, stdio: 'inherit' });
} else {
  console.log('UI build matches current sources; reusing existing resources.');
}
execFileSync('npm', ['run', 'ui:package'], { cwd: root, stdio: 'inherit' });
