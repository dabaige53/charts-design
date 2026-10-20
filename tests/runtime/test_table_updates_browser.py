"""Reader table queries must not remount charts or interrupt the search input."""
import importlib.util
from pathlib import Path
import threading

from playwright.sync_api import expect, sync_playwright

from dashboard_runtime.http_server import RuntimeHTTPServer

spec = importlib.util.spec_from_file_location('table_benchmark', Path(__file__).with_name('benchmark_local.py'))
assert spec is not None and spec.loader is not None
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_table_queries_keep_grid_charts_columns_and_search_focus(tmp_path):
    service, *_ = benchmark.attach(tmp_path, 240)
    server = RuntimeHTTPServer(service, 0, 'table-updates')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1100})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/?board=acceptance#token=table-updates')
            table = page.locator('[data-component-id="details"]')
            expect(table.locator('#tablePageIndicator')).to_have_text('1 / 24')
            page.evaluate('''()=>{
              window.initialGrid=document.querySelector('.grid-stack').gridstack;
              window.initialHosts=[...document.querySelectorAll('.card.original-host')];
              window.initialCharts=initialHosts.flatMap(h=>Object.values(h.shadowRoot?.__dashboardApp?.state.chartInstances||{}));
              window.initialSearch=document.querySelector('[data-component-id="details"] .card').shadowRoot.querySelector('.catalog-search');
            }''')
            table.get_by_role('button', name='下一页', exact=True).click()
            expect(table.locator('#tablePageIndicator')).to_have_text('2 / 24')
            assert page.evaluate('initialHosts.every(h=>h.isConnected)&&document.querySelector(".grid-stack").gridstack===initialGrid')
            assert page.evaluate('initialCharts.length>0&&initialCharts.every(chart=>!chart.isDisposed())')
            table.get_by_role('button', name='下一页', exact=True).click()
            expect(table.locator('#tablePageIndicator')).to_have_text('3 / 24')
            table.get_by_role('button', name='上一页', exact=True).click()
            expect(table.locator('#tablePageIndicator')).to_have_text('2 / 24')
            table.locator('th').filter(has_text='rowId').click()
            expect(table.locator('tbody tr').first.locator('td').first).to_have_text('239')
            table.locator('th').filter(has_text='rowId').click()
            expect(table.locator('tbody tr').first.locator('td').first).to_have_text('0')
            search = table.get_by_label('搜索明细', exact=True)
            search.fill('Agent-17')
            expect(table.locator('#tablePaginationInfo')).to_contain_text('共 3 条')
            expect(search).to_be_focused()
            assert page.evaluate('initialSearch.isConnected&&initialSearch.selectionStart===8')
            search.fill('no-match')
            expect(table.locator('tbody')).to_contain_text('暂无符合筛选条件的数据记录')
            search.fill('')
            expect(table.locator('#tablePaginationInfo')).to_contain_text('共 240 条')
            assert page.evaluate('initialCharts.every(chart=>!chart.isDisposed())')
            assert service.store.get('acceptance', hydrate=False)['revision'] == 3
            # A concurrent document edit must still refresh definitions, rather than hiding it.
            service.store.mutate('acceptance', 3, [{'op': 'set_title', 'value': 'Updated definition'}])
            table.get_by_role('button', name='下一页', exact=True).click()
            expect(page.get_by_label('Dashboard title', exact=True)).to_have_value('Updated definition')
            expect(table.locator('#tablePageIndicator')).to_have_text('2 / 24')
            assert page.evaluate('initialCharts.every(chart=>!chart.isDisposed())')
            page.get_by_role('button', name='编辑', exact=True).click()
            title = page.get_by_label('Dashboard title', exact=True)
            title.fill('Edited title')
            title.press('Tab')
            expect(page.locator('#notice')).to_contain_text('v5')
            page.evaluate('''()=>{
              const app=document.querySelector('.card.original-host').shadowRoot.__dashboardApp;
              const proto=Object.getPrototypeOf(app),destroy=proto.destroy;
              window.destroyCount=0;
              proto.destroy=function(){window.destroyCount++;return destroy.call(this);};
            }''')
            page.get_by_role('button', name='撤销', exact=True).click()
            expect(title).to_have_value('Updated definition')
            assert page.evaluate('destroyCount') == 0
            page.get_by_role('button', name='重做', exact=True).click()
            expect(title).to_have_value('Edited title')
            assert page.evaluate('destroyCount') == 0
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
