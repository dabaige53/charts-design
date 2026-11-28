// Verify the single UI artifact used by local, MCP, npm and container hosts.
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {brotliDecompressSync, gunzipSync} from 'node:zlib';
const dist=fileURLToPath(new URL('../dist/',import.meta.url));
const names=['app.js','app.css','static-worker.js'];
const [js,css,worker,manifest]=await Promise.all([...names,'build.json'].map(name=>readFile(path.join(dist,name))));
const id=createHash('sha256').update(js).update(css).update(worker).digest('hex').slice(0,16);
const builds = JSON.parse(manifest);
if(builds.id!==id)throw Error('构建资源不完整，请重新构建。');
if (builds.webId) {
  const web = path.join(dist, 'web');
  const hash = createHash('sha256');
  for (const name of names) {
    const file = path.join(web, name);
    const [body, br, gzip] = await Promise.all([file, file + '.br', file + '.gz'].map(file => readFile(file)));
    if (!body.equals(brotliDecompressSync(br)) || !body.equals(gunzipSync(gzip))) throw Error('预压缩资源不匹配：' + name);
    hash.update(body);
  }
  if (hash.digest('hex').slice(0, 16) !== builds.webId) throw Error('浏览器资源不匹配。');
  for (const font of builds.fonts) {
    const match = /^fonts\/([0-9a-f]{16})\.(woff2?|ttf)$/.exec(font);
    if (!match || createHash('sha256').update(await readFile(path.join(web, font))).digest('hex').slice(0, 16) !== match[1]) {
      throw Error('浏览器字体不匹配：' + font);
    }
  }
}
console.log(JSON.stringify({directory:dist,id,files:[...names,'build.json']}));
