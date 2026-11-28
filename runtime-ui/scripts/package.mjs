// Verify the single UI artifact used by local, MCP, npm and container hosts.
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {createHash} from 'node:crypto';
const dist=fileURLToPath(new URL('../dist/',import.meta.url));
const names=['app.js','app.css','static-worker.js'];
const [js,css,worker,manifest]=await Promise.all([...names,'build.json'].map(name=>readFile(path.join(dist,name))));
const id=createHash('sha256').update(js).update(css).update(worker).digest('hex').slice(0,16);
if(JSON.parse(manifest).id!==id)throw Error('构建资源不完整，请重新构建。');
console.log(JSON.stringify({directory:dist,id,files:[...names,'build.json']}));
