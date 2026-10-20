"""Optional million-row/40-chart browser benchmark; creates only synthetic data.

node bin/python-runtime.js tests/runtime/benchmark_incremental.py --output /tmp/charts-performance.json
"""
from __future__ import annotations
import argparse
import copy
import json
import importlib
from pathlib import Path
import runpy
import statistics
import sys
import tempfile
import threading

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
RuntimeHTTPServer = importlib.import_module('dashboard_runtime.http_server').RuntimeHTTPServer
Service = importlib.import_module('dashboard_runtime.service').Service
sync_playwright = importlib.import_module('playwright.sync_api').sync_playwright


def run(output: Path, existing_root: Path | None = None):
    fixture = runpy.run_path(str(Path(__file__).with_name('benchmark_local.py')))
    if existing_root:
        service = Service(existing_root / 'store', existing_root / 'sources.json')
    else:
        root = Path(tempfile.mkdtemp(prefix='charts-million40-'))
        service, *_ = fixture['attach'](root, 1_000_000)
        doc = service.store.get('acceptance', hydrate=False)
        operations = [{'op': 'put_component', 'id': f'chart-{i}', 'value': copy.deepcopy(doc['manifest']['components']['category'])} for i in range(1, 40)]
        filters = fixture['filters']()
        for item in filters:
            item['componentIds'] += [f'chart-{i}' for i in range(1, 40)]
        service.store.mutate('acceptance', 3, [*operations, {'op': 'set_filters', 'value': filters}])
    document = service.store.get('acceptance', hydrate=False)
    assert document['snapshot']['datasetRefs']['facts']['rowCount'] == 1_000_000
    assert sum(c.get('family') == 'chart' for c in document['manifest']['components'].values()) == 40
    server = RuntimeHTTPServer(service, 0, 'benchmark-local', idle_timeout=600)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    report = {'rows': 1_000_000, 'charts': 40, 'viewport': [1440, 1100], 'browser': 'Chromium', 'samples': 100}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1100})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            loads = []
            for _ in range(3):
                page.goto(f'http://127.0.0.1:{server.server_port}/?board=acceptance#token=benchmark-local')
                page.locator('[data-component-id="category"] canvas').first.wait_for()
                loads.append(page.evaluate('performance.now()'))
            report['coldFirstChartMs'] = loads[0]
            report['warmFirstChartMedianMs'] = statistics.median(loads[1:])
            report['initialComponentShells'] = page.evaluate('document.querySelectorAll(".card.original-host").length')
            report['initialEChartsInstances'] = page.evaluate('[...document.querySelectorAll(".card.original-host")].reduce((n,h)=>n+Object.keys(h.shadowRoot?.__dashboardApp?.state.chartInstances||{}).length,0)')
            page.evaluate('window.__chartsReady()')
            page.evaluate('''()=>{window.plots=[...document.querySelectorAll('.card.original-host')].flatMap(h=>Object.values(h.shadowRoot?.__dashboardApp?.state.chartInstances||{}));}''')
            session = page.context.new_cdp_session(page)
            session.send('HeapProfiler.collectGarbage')
            before = session.send('Runtime.getHeapUsage')['usedSize']
            before_dom = session.send('Memory.getDOMCounters')
            samples = page.evaluate('''async()=>{
              const shadow=document.querySelector('[data-component-id="details"] .card').shadowRoot;
              const samples=[];performance.setResourceTimingBufferSize(500);
              for(let i=0;i<100;i++){
                const expected=i%2===0?'2 / 100000':'1 / 100000',start=performance.now();
                await new Promise(resolve=>{const indicator=shadow.querySelector('#tablePageIndicator');const observer=new MutationObserver(()=>{if(indicator.textContent!==expected)return;observer.disconnect();requestAnimationFrame(()=>requestAnimationFrame(resolve));});observer.observe(indicator,{childList:true,subtree:true,characterData:true});shadow.querySelector(i%2===0?'#tableNextBtn':'#tablePrevBtn').click();});
                const response=performance.getEntriesByType('resource').filter(r=>r.name.endsWith('/dashboard_view')).at(-1);
                samples.push({totalMs:performance.now()-start,afterResponseMs:performance.now()-response.responseEnd});
              }
              return samples;
            }''')
            session.send('HeapProfiler.collectGarbage')
            after = session.send('Runtime.getHeapUsage')['usedSize']
            after_dom = session.send('Memory.getDOMCounters')
            report['heapBeforeBytes'], report['heapAfterBytes'] = before, after
            report['domBefore'], report['domAfter'] = before_dom, after_dom
            report['retainedChartInstances'] = page.evaluate('plots.filter(p=>!p.isDisposed()).length')
            assert report['retainedChartInstances'] == 40
            assert after - before < max(20 * 1024 * 1024, before * .1)
            assert after_dom['jsEventListeners'] <= before_dom['jsEventListeners'] + 5
            for key in ('totalMs', 'afterResponseMs'):
                values = sorted(sample[key] for sample in samples)
                report[key] = {'median': statistics.median(values), 'p95': values[94], 'max': values[-1]}
            report['targetsMet'] = report['totalMs']['p95'] <= 250 and report['afterResponseMs']['p95'] <= 100
            report['pageErrors'] = errors
            assert not errors
            report['status'] = 'passed'
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--existing-root', type=Path, help='Reuse only an explicitly supplied synthetic benchmark fixture')
    arguments = parser.parse_args()
    run(arguments.output, arguments.existing_root)
