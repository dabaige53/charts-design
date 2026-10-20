"""Performance changes preserve chart state, layout, styling and disposal."""
import threading

import pytest
from playwright.sync_api import sync_playwright

from dashboard_runtime.demo import report_document
from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.service import Service


@pytest.mark.parametrize('shared_styles', [True, False])
def test_prose_and_changed_references_reuse_compatible_charts(tmp_path, shared_styles):
    service = Service(tmp_path)
    doc = report_document('report')
    source = doc['manifest']['report']['markdown']
    service.store.create('report', 'Report', doc)
    server = RuntimeHTTPServer(service, 0, 'performance-test')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            if not shared_styles:
                page.add_init_script('CSSStyleSheet.prototype.replaceSync=undefined')
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/?board=report#token=performance-test')
            page.locator('.markdown-chart canvas').first.wait_for()
            assert page.locator('.markdown-preview .component-header:visible').count() == 0
            page.get_by_role('button', name='编辑', exact=True).click()
            area = page.get_by_label('Markdown 源文档', exact=True)
            area.wait_for()
            page.evaluate('''()=>{
              window.beforeHosts=[...document.querySelectorAll('.markdown-chart')];
              window.beforeCanvases=beforeHosts.map(host=>host.shadowRoot.querySelector('canvas'));
            }''')
            if shared_styles:
                assert page.evaluate('beforeHosts[0].shadowRoot.adoptedStyleSheets[0] === beforeHosts[1].shadowRoot.adoptedStyleSheets[0]')
            edited = source + '\n\n仅修改文字，保留图表。'
            area.fill(edited)
            page.get_by_text('仅修改文字，保留图表。', exact=True).wait_for()
            assert page.evaluate('beforeHosts.every((host,i)=>host.isConnected&&host.shadowRoot.querySelector("canvas")===beforeCanvases[i])')
            assert page.locator('.markdown-preview .component-header:visible').count() == 0
            page.get_by_role('button', name='保存 Markdown', exact=True).click()
            page.wait_for_function('document.querySelector(".markdown-save-state").textContent.includes("已保存")')
            assert service.store.get('report')['manifest']['report']['markdown'] == edited
            duplicate = edited + '\n\n```chart\n{"componentId":"trend","caption":"新增引用"}\n```'
            area.fill(duplicate)
            page.get_by_text('图 3　新增引用', exact=True).wait_for()
            assert page.locator('.markdown-chart').count() == 3
            assert page.evaluate('beforeHosts.every(host=>host.isConnected)')
            page.evaluate('window.duplicateHosts=[...document.querySelectorAll(".markdown-chart")]')
            area.fill(duplicate.replace('新增引用', '修改图注'))
            page.get_by_text('图 3　修改图注', exact=True).wait_for()
            assert page.evaluate('duplicateHosts.every(host=>host.isConnected)')
            area.fill('# 仅保留文字')
            page.get_by_role('heading', name='仅保留文字', exact=True).wait_for()
            assert page.locator('.markdown-chart').count() == 0
            assert page.evaluate('duplicateHosts.every(host=>!host.isConnected)')
            area.fill(edited)
            page.locator('.markdown-chart canvas').first.wait_for()
            assert page.locator('.markdown-chart').count() == 2
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
