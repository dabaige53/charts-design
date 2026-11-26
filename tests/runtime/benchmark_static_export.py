#!/usr/bin/env python3
"""Profile a synthetic Service static export and check its worker over plain HTTP.

  .venv/bin/python tests/runtime/benchmark_static_export.py --output /tmp/static-export.json

One run per cache state; use the data-only benchmark for repeated encoder measurements.
The synthetic project remains in the reported temporary workspace for inspection.
"""
import functools
import argparse
from contextlib import nullcontext
import http.server
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from unittest.mock import patch
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
parser.add_argument('--bun', type=Path, default=shutil.which('bun'))
parser.add_argument('--rows', type=int, default=100_000)
parser.add_argument('--temp-root', type=Path, default=Path(tempfile.gettempdir()))
parser.add_argument('--label', default='ui-template-cache')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
if args.rows < 1:
    parser.error('rows must be positive')
if not args.bun:
    parser.error('Bun is required; use --bun or put bun on PATH')
REPO = args.repo.resolve()
BUN = args.bun.resolve()
sys.path.insert(0, str(REPO))
from dashboard_runtime.demo import executive_document
from dashboard_runtime.service import Service
from dashboard_runtime import columnar, deployment, statistical


# @wu-test type=integration | scope=独立静态包端到端测量 | protects=编码优化后实际ZIP仍慢或普通HTTP部署依赖MCP后端
def main():
    work = Path(tempfile.mkdtemp(prefix='charts-export-audit-', dir=args.temp_root))
    service = Service(work / 'runtime', project_root=work / 'project')
    doc = executive_document('audit')
    fields = doc['manifest']['datasets']['sales']['fields']
    row_count = args.rows
    rows = ({'month': f'2026-{i%12+1:02d}-01', 'region': ['华东','华北','西南'][i%3],
             'revenue': (i%10000)/4, 'passengers': i%100+1, 'seats': 120,
             'budget': 1500, 'yieldBase': 1000, 'yieldDelta': (i%10000)/4-1000} for i in range(row_count))
    ref = service.store.data.import_rows(rows, fields)
    doc['snapshot']['datasets'] = {}
    doc['snapshot']['datasetRefs'] = {'sales': ref}
    service.call('dashboard_create', {'dashboardId': 'audit', 'document': doc})
    exports = []
    for label in ('cache_miss', 'cache_hit'):
        timings = []
        stack = []

        def measured(name, function):
            @functools.wraps(function)
            def wrapper(*args, **kwargs):
                parent = stack[-1] if stack else None
                stack.append(name)
                started = time.perf_counter()
                try:
                    return function(*args, **kwargs)
                finally:
                    elapsed = time.perf_counter() - started
                    stack.pop()
                    timings.append({'stage': name, 'parent': parent, 'seconds': elapsed,
                                    **({'file': str(args[1])} if name == 'zip.write' and len(args) > 1 else {})})
            return wrapper

        with patch.object(service.store, 'readable', measured('read_saved', service.store.readable)), \
             patch.object(service.store, 'compact', measured('compact', service.store.compact)), \
             patch.object(service.store, 'statistical_document', measured('statistical_document', service.store.statistical_document)), \
             patch.object(statistical, 'statistical_artifacts', measured('statistical_artifacts', statistical.statistical_artifacts)), \
             patch.object(columnar, 'write_parquet', measured('write_parquet', columnar.write_parquet)), \
             patch.object(deployment.shutil, 'copyfile', measured('copy_file', deployment.shutil.copyfile)), \
             (patch.object(deployment, '_prepare_archive', measured('prepare_ui_archive', deployment._prepare_archive))
              if hasattr(deployment, '_prepare_archive') else nullcontext()), \
             patch.object(zipfile.ZipFile, 'write', measured('zip.write', zipfile.ZipFile.write)), \
             patch.object(zipfile.ZipFile, 'close', measured('zip.close', zipfile.ZipFile.close)):
            started = time.perf_counter()
            result = service.call('dashboard_export_site', {'dashboardId': 'audit', 'dataFormat': 'parquet'})['export']
            total = time.perf_counter() - started
        summaries = {}
        for item in timings:
            key = item['stage'] + (f" (inside {item['parent']})" if item['parent'] else '')
            summary = summaries.setdefault(key, {'calls':0,'seconds':0})
            summary['calls'] += 1
            summary['seconds'] += item['seconds']
        with zipfile.ZipFile(result['path']) as archive:
            entries = [{'name': item.filename, 'rawBytes': item.file_size, 'zipBytes': item.compress_size} for item in archive.infolist()]
            assert archive.testzip() is None
        exports.append({'label':label, 'totalSeconds':total, 'stages':summaries,
                        'zipBytes':result['bytes'], 'entries':entries, 'manifest':result['manifest'],
                        'site':result['directory'], 'archive':result['path']})
        print(json.dumps({'stage':label, 'totalSeconds':total, 'timings':summaries}),flush=True)

    # Only a standard static HTTP server is started; there is no MCP/Charts HTTP backend.
    site = Path(exports[-1]['site'])
    parent = site.parent
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    handler = functools.partial(QuietHandler, directory=parent)
    server = http.server.ThreadingHTTPServer(('127.0.0.1',0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}/site/'
    try:
        fetched = []
        for name in ('index.html','document.json','app.js','app.css','static-worker.js','export-manifest.json'):
            with urllib.request.urlopen(base+name) as response:
                data = response.read()
                fetched.append({'path':name,'status':response.status,'bytes':len(data),'contentType':response.headers.get('Content-Type')})
        worker = work / 'http-worker-check.ts'
        worker.write_text('''
import { Worker } from 'node:worker_threads';
const base = process.argv[2];
const doc = await (await fetch(new URL('document.json',base))).json();
const script = await (await fetch(new URL('static-worker.js',base))).text();
const bridge = `const {parentPort}=require('node:worker_threads');globalThis.self={postMessage:value=>parentPort.postMessage(value)};parentPort.on('message',data=>self.onmessage({data}));`;
const worker = new Worker(bridge + script,{eval:true});
const call = (id,type,args) => new Promise((resolve,reject)=>{worker.once('message',value=>value.error?reject(Error(value.error)):resolve(value.result));worker.once('error',reject);worker.postMessage({id,type,args});});
await call(1,'init',{document:doc,base});
const view = await call(2,'query',{componentIds:['total','load','details']});
const detail = await call(3,'query',{detail:true,componentId:'details',offset:Number(process.argv[3])-1,limit:1});
await worker.terminate();
console.log(JSON.stringify({view,detail}));
''', encoding='utf-8')
        process = subprocess.run([str(BUN), str(worker), base, str(row_count)],check=True,capture_output=True,text=True,cwd=REPO)
        checked = json.loads(process.stdout)
        assert checked['detail']['totalRows'] == row_count
        assert len(checked['detail']['rows']) == 1
        expected_revenue = sum((i % 10000)/4 for i in range(row_count))
        expected_label = f'{expected_revenue:,.2f}'.rstrip('0').rstrip('.') + ' 万元'
        assert checked['view']['computed']['components']['total']['value'] == expected_label
        assert checked['detail']['rows'][0]['revenue'] == ((row_count-1) % 10000)/4
        print(json.dumps({'stage':'static-http-worker-complete','totalRows':checked['detail']['totalRows']}),flush=True)
    finally:
        server.shutdown()
        server.server_close()
    report = {'label':args.label, 'environment':{'python':platform.python_version(),'platform':platform.platform(),
                                              'logicalCpuCount':os.cpu_count(),
                                              'bun':subprocess.check_output([str(BUN),'--version'],text=True).strip()},
              'rows':row_count, 'components':['4 bound KPI','2 bound charts','details table'],
              'work':str(work),'exports':exports,'http':fetched,'workerResult':checked,
              'scope':'One run per cache state; plain local HTTP at a subpath and real packaged worker; no browser or MCP server. Stage timings are inclusive when parent is shown.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
