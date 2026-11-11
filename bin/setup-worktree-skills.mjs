#!/usr/bin/env bun
// Restore local Codex skill links without copying skill implementations.
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const commonDir = execFileSync('git', ['rev-parse', '--path-format=absolute', '--git-common-dir'], {
  cwd: root, encoding: 'utf8',
}).trim();
const primaryRoot = path.dirname(commonDir);
const hostSkills = path.join(primaryRoot, '.agents', 'skills');
const source = fs.existsSync(hostSkills) ? hostSkills : path.join(root, 'skills');
const destination = path.join(root, '.agents', 'skills');

if (source !== hostSkills) console.log('首次检出：从仓库 skills/ 建立项目技能入口。');

const links = [];
for (const entry of fs.readdirSync(source, {withFileTypes: true})) {
  if (entry.name.startsWith('.')) continue;
  const original = path.join(source, entry.name);
  if (!entry.isDirectory() && !entry.isSymbolicLink()) continue;
  if (!fs.existsSync(path.join(original, 'SKILL.md'))) {
    console.warn(`未同步 ${entry.name}：缺少 SKILL.md 或链接已失效`);
    continue;
  }
  const resolved = fs.realpathSync(original);
  const relative = path.relative(primaryRoot, resolved);
  const inProject = relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
  const target = inProject && !relative.startsWith(`.agents${path.sep}`)
    ? path.join(root, relative)
    : resolved;
  if (!fs.existsSync(path.join(target, 'SKILL.md'))) {
    throw new Error(`当前 worktree 缺少技能源文件：${target}`);
  }
  const link = path.join(destination, entry.name);
  if (fs.existsSync(link) || fs.lstatSync(link, {throwIfNoEntry: false})) {
    if (fs.realpathSync(link) !== fs.realpathSync(target)) {
      throw new Error(`已有技能入口指向其他位置，请先检查：${link}`);
    }
    console.log(`已保留 ${entry.name}`);
    continue;
  }
  links.push({name: entry.name, link, target});
}

fs.mkdirSync(destination, {recursive: true});
for (const {name, link, target} of links) {
  fs.symlinkSync(path.relative(destination, target), link, 'dir');
  console.log(`已同步 ${name}`);
}
