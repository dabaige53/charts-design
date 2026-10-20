"""Real browser contracts for keyed updates, bounded inspectors and queued reads."""
import importlib.util
from pathlib import Path
import threading
import time

from playwright.sync_api import expect, sync_playwright
from dashboard_runtime.http_server import RuntimeHTTPServer

spec = importlib.util.spec_from_file_location('incremental_fixture', Path(__file__).with_name('benchmark_local.py'))
assert spec is not None and spec.loader is not None
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def test_reconcile_modes_resize_refresh_and_repeated_pages(tmp_path):
    service, *_ = fixture.attach(tmp_path, 240)
    server = RuntimeHTTPServer(service, 0, 'incremental-test')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1100})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            requests = []
            page.on('request', lambda request: requests.append(request.post_data_json) if request.url.endswith('/dashboard_view') else None)
            page.goto(f'http://127.0.0.1:{server.server_port}/?board=acceptance#token=incremental-test')
            page.wait_for_function('typeof window.__chartsReady === "function"')
            page.evaluate('window.__chartsReady()')
            page.evaluate('''()=>{
              window.hosts=[...document.querySelectorAll('.card.original-host')];
              window.plots=hosts.flatMap(h=>Object.values(h.shadowRoot?.__dashboardApp?.state.chartInstances||{}));
              window.oldGrid=document.querySelector('.grid-stack').gridstack;
              window.domCounts=[];
            }''')
            for _ in range(3):
                page.get_by_role('button', name='编辑', exact=True).click()
                page.get_by_role('button', name='退出编辑', exact=True).click()
            for width in (900, 390, 1440):
                page.set_viewport_size({'width': width, 'height': 1100})
                page.wait_for_function('(width)=>document.querySelector(".grid-stack").gridstack.getColumn()===(width<650?4:width<1050?8:12)', arg=width)
            page.get_by_role('button', name='刷新报表', exact=True).click()
            expect(page.locator('.refresh-time')).to_be_visible()
            assert page.evaluate('hosts.every(h=>h.isConnected)&&plots.every(p=>!p.isDisposed())&&oldGrid===document.querySelector(".grid-stack").gridstack')
            table = page.locator('[data-component-id="details"]')
            page.evaluate('''()=>{
              window.forcedScrolls=0;const scrollTo=window.scrollTo.bind(window);
              window.scrollTo=(...args)=>{forcedScrolls++;scrollTo(...args);};
            }''')
            for index in range(100):
                table.get_by_role('button', name='下一页' if index % 2 == 0 else '上一页', exact=True).click()
                expect(table.locator('#tablePageIndicator')).to_have_text('2 / 24' if index % 2 == 0 else '1 / 24')
                if index in (9, 99):
                    page.evaluate('domCounts.push(hosts.reduce((n,h)=>n+h.shadowRoot.querySelectorAll("*").length,0))')
            assert requests and all(r['responseMode'] == 'patch' and r['componentIds'] == ['details'] for r in requests)
            assert page.evaluate('plots.every(p=>!p.isDisposed())&&domCounts[0]===domCounts[1]')
            assert page.evaluate('forcedScrolls') == 0
            table.get_by_role('button', name='指标定义与语义', exact=True).click()
            panel = page.get_by_role('dialog')
            expect(panel.locator('tbody tr')).to_have_count(20)
            expect(panel.locator('tbody tr').first.locator('td').first).to_have_text('0')
            panel.get_by_role('button', name='数据下一页', exact=True).click()
            expect(panel.locator('tbody tr').first.locator('td').first).to_have_text('20')
            panel.get_by_label('搜索组件数据').fill('Agent-17')
            expect(panel.locator('tbody tr')).to_have_count(3)
            assert service.store.get('acceptance', hydrate=False)['revision'] == 3
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_latest_search_wins_with_one_active_read(tmp_path):
    service, *_ = fixture.attach(tmp_path, 240)
    call = service.call
    active = 0
    peak = 0
    entered = threading.Event()

    def delayed(name, args):
        nonlocal active, peak
        if name != 'dashboard_view':
            return call(name, args)
        active += 1
        peak = max(peak, active)
        try:
            if args.get('tableStates', {}).get('details', {}).get('keyword') == 'Agent-17':
                entered.set()
                time.sleep(0.5)
            return call(name, args)
        finally:
            active -= 1

    service.call = delayed
    server = RuntimeHTTPServer(service, 0, 'latest-test')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1100})
            page.goto(f'http://127.0.0.1:{server.server_port}/?board=acceptance#token=latest-test')
            table = page.locator('[data-component-id="details"]')
            search = table.get_by_label('搜索明细', exact=True)
            search.fill('Agent-17')
            assert entered.wait(3)
            search.fill('no-match')
            expect(table.locator('tbody')).to_contain_text('暂无符合筛选条件的数据记录')
            expect(search).to_have_value('no-match')
            expect(search).to_be_focused()
            assert peak == 1
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
