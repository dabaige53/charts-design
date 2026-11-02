// Validate local Markdown file links in the two skill entrypoints and shared workflow.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const files = [
  'skills/executive-charts/SKILL.md',
  'skills/analytical-reports/SKILL.md',
  'skills/executive-charts/references/mcp-delivery.md',
];
let checked = 0;
const failures = [];
for (const file of files) {
  const text = fs.readFileSync(path.join(root, file), 'utf8').replace(/```[^\n]*\n[\s\S]*?```/g, '');
  for (const match of text.matchAll(/\[[^\]\n]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g)) {
    const target = match[1].replace(/^<|>$/g, '').split('#')[0];
    if (!target || /^[a-z][a-z\d+.-]*:/i.test(target)) continue;
    checked++;
    const resolved = path.resolve(root, path.dirname(file), decodeURIComponent(target));
    if (!fs.existsSync(resolved)) failures.push(`${file}: missing ${target}`);
  }
}
if (failures.length) {
  console.error(failures.join('\n'));
  process.exitCode = 1;
} else console.log(`Skill file links passed (${checked} links; anchors not checked).`);
