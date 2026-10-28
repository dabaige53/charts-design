"""Product-level retail fixture: real ECharts, filters, dynamic series and drilldown."""
import threading
from dashboard_runtime.model import new_document, apply_operations
from dashboard_runtime.service import Service
from dashboard_runtime.http_server import RuntimeHTTPServer


def retail_document():
    rows = [{'store': 'North', 'product': 'Coffee', 'sales': 100, 'units': 20, 'rating': 'A'}, {'store': 'North', 'product': 'Tea', 'sales': 50, 'units': 10, 'rating': 'A'}, {'store': 'South', 'product': 'Cocoa', 'sales': 200, 'units': 40, 'rating': 'B'}]
    fields = {k: {'type': 'number' if k in ('sales', 'units') else 'string'} for k in rows[0]}
    ops = [{'op': 'put_source', 'id': 'fixture', 'value': {'kind': 'fixture'}}, {'op': 'put_dataset', 'id': 'retail', 'meta': {'sourceId': 'fixture', 'fields': fields}, 'rows': rows}]
    for key in ('sales', 'units'):
        ops.append({'op': 'put_metric', 'id': key, 'value': {'datasetId': 'retail', 'aggregation': 'sum', 'field': key, 'label': key, 'unit': '', 'definition': 'Synthetic retail fixture'}})
    for key, code, binding, encoding in [
        ('scatter', 'r02', {'categoryField': 'store', 'measures': {'x': 'sales', 'y': 'units'}, 'attributes': {'rating': {'field': 'rating', 'aggregation': 'unique'}}}, {'symbolSize': 18, 'colorBy': 'rating', 'tooltip': ['x', 'y', 'rating']}),
        ('bars', 'c03', {'categoryField': 'store', 'seriesField': 'product', 'measures': {'value': 'sales'}}, {'orientation': 'horizontal', 'stacked': True})
    ]:
        ops.append({'op': 'put_component', 'id': key, 'value': {'kind': 'legacy', 'family': 'chart', 'title': key, 'datasetId': 'retail', 'linkGroup': 'store', 'binding': {'datasetId': 'retail', **binding}, 'config': {'code': code, 'data': {}, 'presentation': {}, 'encoding': encoding}}})
    ops.append({'op': 'put_dataset', 'id': 'retail-details', 'meta': {'sourceId': 'fixture', 'fields': fields}, 'rows': rows})
    ops.append({'op': 'put_component', 'id': 'details', 'value': {'kind': 'table', 'title': 'Retail rows', 'datasetId': 'retail-details', 'linkGroup': 'store'}})
    ops.append({'op': 'set_filters', 'value': [{'id': 'store', 'label': 'Store', 'field': 'store', 'op': 'in', 'values': [], 'componentIds': ['scatter', 'bars', 'details']}]})
    return apply_operations(new_document('retail', 'Synthetic retail'), ops)


def test_dynamic_encoding_browser(tmp_path):
    from playwright.sync_api import sync_playwright
    service = Service(tmp_path / 'state')
    service.store.create('retail', 'Retail', retail_document())
    server = RuntimeHTTPServer(service, 0, 'encoding-test')
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1600, 'height': 1400})
            errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/?board=retail#encoding-test')
            page.locator('[data-component-id=scatter] canvas').wait_for()
            page.locator('[data-component-id=bars] canvas').wait_for()
            expression = "id=>{const h=document.querySelector('[data-component-id='+id+'] .card').shadowRoot;return window.getDashboardAppForElement(h.querySelector('canvas')).state.chartInstances['original-'+id].getOption()}"
            option = page.evaluate(expression, 'scatter')
            assert all(s['symbolSize'] == 18 for s in option['series'])
            assert len(page.evaluate(expression, 'bars')['series']) == 3
            page.get_by_role('button', name='Store：全部', exact=True).click()
            for check in page.locator('.filter-choice input').all(): check.uncheck()
            page.locator('.filter-choice').filter(has_text='North').locator('input').check()
            page.get_by_role('button', name='应用', exact=True).click()
            page.wait_for_function("document.querySelector('.filter-summary').textContent==='已生效条件：1'")
            option = page.evaluate(expression, 'bars')
            assert len(option['series']) == 2
            assert sum(s['data'][0]['value'] for s in option['series']) == 150
            assert page.locator('[data-component-id=details] tbody tr').count() == 2
            page.get_by_role('button', name='清除所有筛选', exact=True).click()
            page.wait_for_function("document.querySelector('.filter-summary').textContent==='已生效条件：0'")
            xy = page.evaluate("""()=>{const h=document.querySelector('[data-component-id=scatter] .card').shadowRoot;const chart=window.getDashboardAppForElement(h.querySelector('canvas')).state.chartInstances['original-scatter'];const p=chart.convertToPixel({seriesIndex:0},[150,30]);const r=chart.getDom().getBoundingClientRect();return [r.x+p[0],r.y+p[1]];}""")
            page.mouse.click(*xy)
            page.locator('.linkage-chip').wait_for()
            assert page.locator('[data-component-id=details] tbody tr').count() == 2
            page.keyboard.press('Escape')
            page.wait_for_function("!document.querySelector('.linkage-chip')")
            assert page.locator('[data-component-id=details] tbody tr').count() == 3
            assert not errors, errors
            page.screenshot(path=str(tmp_path / 'retail.png'), full_page=True)
            browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join()
