"""Exercise the packaged browser worker without a browser or a network service."""
import base64
import json
import subprocess

from dashboard_runtime.assets import DIST


def worker_rows(raw, name):
    script = '''
const input = JSON.parse(await new Response(Bun.stdin.stream()).text());
let receipt;
globalThis.self = {postMessage: value => {receipt = value;}};
globalThis.fetch = async () => new Response(Buffer.from(input.content, 'base64'));
await import(input.worker);
const document = {id:'fixture',revision:1,manifest:{filters:[],datasets:{data:{fields:{}}},
  components:{rows:{kind:'table',datasetId:'data'}}},snapshot:{datasets:{}},staticFiles:{data:[input.name]}};
await self.onmessage({data:{id:1,type:'init',args:{document,base:'https://offline.example/subpath/'}}});
if (receipt.error) throw Error(receipt.error);
await self.onmessage({data:{id:2,type:'query',args:{detail:true,componentId:'rows',limit:100000}}});
if (receipt.error) throw Error(receipt.error);
process.stdout.write(JSON.stringify(receipt.result.rows));
'''
    result = subprocess.run(['bun', '-e', script], input=json.dumps({
        'worker': (DIST / 'static-worker.js').as_uri(), 'name': name,
        'content': base64.b64encode(raw).decode(),
    }), capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def worker_query(document, files, queries):
    """Run a real publication description and track each query's data requests."""
    script = '''
const input = JSON.parse(await new Response(Bun.stdin.stream()).text());
let receipt;
const loaded = [];
globalThis.self = {postMessage: value => {receipt = value;}};
globalThis.fetch = async url => {
  const name = new URL(url).pathname.slice('/subpath/'.length);
  if (!(name in input.files)) throw Error('Unexpected data file: ' + name);
  loaded.push(name);
  return new Response(Buffer.from(input.files[name], 'base64'));
};
await import(input.worker);
await self.onmessage({data:{id:1,type:'init',args:{document:input.document,base:'https://offline.example/subpath/'}}});
if (receipt.error) throw Error(receipt.error);
const results = [];
for (const [index,args] of input.queries.entries()) {
  const start = loaded.length;
  await self.onmessage({data:{id:index+2,type:'query',args}});
  if (receipt.error) throw Error(receipt.error);
  results.push({result:receipt.result,files:loaded.slice(start)});
}
process.stdout.write(JSON.stringify(results));
'''
    result = subprocess.run(['bun', '-e', script], input=json.dumps({
        'worker': (DIST / 'static-worker.js').as_uri(), 'document': document, 'queries': queries,
        'files': {name: base64.b64encode(raw).decode() for name, raw in files.items()},
    }), capture_output=True, text=True, check=True)
    return json.loads(result.stdout)
