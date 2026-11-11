// Validate local links and heading anchors in every maintained Markdown file.
// AGENTS.md asks documentation changes to keep local links and section anchors
// working; check-skill-links.js only covers the two skill entry points.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
// Fenced examples (any fence length) are not links; the closing fence repeats the opening run.
const FENCE = /^ {0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?^ {0,3}\1[ \t]*$/gm;
const skip = new Set(['node_modules', 'examples', 'dist', 'generated', 'component-review', 'boards']);

function markdownFiles(dir) {
  const found = [];
  for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
    if (entry.name.startsWith('.') || skip.has(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) found.push(...markdownFiles(full));
    else if (entry.name.endsWith('.md')) found.push(full);
  }
  return found;
}

// GitHub heading slugs: lower case, drop punctuation, spaces become hyphens.
function slug(text) {
  return text.trim().toLowerCase()
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/<[^>]+>/g, '')
    .replace(/[^\p{L}\p{M}\p{N}\p{Pc} -]/gu, '')
    .replace(/ /g, '-');
}

const anchorCache = new Map();
function anchors(file) {
  if (!anchorCache.has(file)) {
    const seen = new Map(), result = new Set();
    const text = fs.readFileSync(file, 'utf8').replace(FENCE, '');
    for (const match of text.matchAll(/^#{1,6}[ \t]+(.+?)[ \t#]*$/gm)) {
      const base = slug(match[1]), count = seen.get(base) || 0;
      seen.set(base, count + 1);
      result.add(count ? `${base}-${count}` : base);
    }
    for (const match of text.matchAll(/<a\s+(?:name|id)="([^"]+)"/g)) result.add(match[1]);
    anchorCache.set(file, result);
  }
  return anchorCache.get(file);
}

let checked = 0;
const failures = [];
for (const entry of fs.readdirSync(path.join(root, 'docs'), {withFileTypes: true})) {
  if (entry.isFile() && entry.name !== 'README.md') {
    failures.push(`docs/${entry.name}: put topic documents and evidence in the directory defined by docs/agent/file-management.md`);
  }
}
const files = [path.join(root, 'README.md'), path.join(root, 'AGENTS.md'), ...markdownFiles(path.join(root, 'docs')), ...markdownFiles(path.join(root, 'skills'))];
for (const file of files) {
  const text = fs.readFileSync(file, 'utf8').replace(FENCE, '').replace(/`[^`\n]*`/g, '');
  for (const match of text.matchAll(/\[[^\]\n]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g)) {
    const raw = match[1].replace(/^<|>$/g, '');
    if (/^[a-z][a-z\d+.-]*:/i.test(raw)) continue;
    checked++;
    const [target, fragment] = raw.split('#');
    const resolved = target ? path.resolve(path.dirname(file), decodeURIComponent(target)) : file;
    const label = path.relative(root, file);
    if (!fs.existsSync(resolved)) { failures.push(`${label}: missing ${raw}`); continue; }
    if (fragment && resolved.endsWith('.md') && !anchors(resolved).has(decodeURIComponent(fragment).toLowerCase())) {
      failures.push(`${label}: missing anchor #${fragment} in ${path.relative(root, resolved)}`);
    }
  }
}
if (failures.length) {
  console.error(failures.join('\n'));
  process.exitCode = 1;
} else console.log(`Documentation links passed (${checked} links in ${files.length} files, anchors checked).`);
