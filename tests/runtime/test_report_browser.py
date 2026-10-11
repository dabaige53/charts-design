"""One focused browser flow for Markdown writing, inline charts and persistence."""
import os
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright
from dashboard_runtime.demo import report_document
from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.service import Service


def test_markdown_authoring_and_preview(tmp_path):
    service = Service(tmp_path / 'state')
    service.store.create('report-demo', 'Report', report_document('report-demo'))
    server = RuntimeHTTPServer(service, 0, 'markdown-test')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, **({'executable_path': os.environ['CHARTS_CHROMIUM_EXECUTABLE']} if os.environ.get('CHARTS_CHROMIUM_EXECUTABLE') else {}))
            page = browser.new_page(viewport={'width': 1500, 'height': 1050})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_address[1]}/?board=report-demo#markdown-test')
            page.locator('.markdown-chart canvas').first.wait_for()
            assert page.locator('.paper-caption').count() == 2
            assert page.locator('.paper-figure-ref').first.inner_text() == '图 1'
            assert page.get_by_label('Markdown 源文档', exact=True).count() == 0
            page.locator('.paper-figure-ref').first.click()
            page.reload()
            page.locator('.markdown-chart canvas').first.wait_for()
            assert page.locator('.markdown-preview .component-actions:visible').count() == 0
            assert page.locator('.markdown-preview .component-header:visible').count() == 0
            page.get_by_role('button', name='编辑', exact=True).click()
            source = page.get_by_label('Markdown 源文档', exact=True)
            original = source.input_value()
            edited = original + '\n\n## 补充观察\n\n- 保留原始 Markdown\n\n```js\nalert("ordinary code")\n```\n'
            source.fill(edited)
            page.get_by_role('button', name='保存 Markdown', exact=True).click()
            page.wait_for_function("document.querySelector('.markdown-save-state').textContent.includes('已保存')")
            assert service.store.get('report-demo')['manifest']['report']['markdown'] == edited
            page.reload()
            page.get_by_role('button', name='编辑', exact=True).click()
            assert source.input_value() == edited
            assert page.locator('.markdown-preview pre code.language-js').inner_text().strip() == 'alert("ordinary code")'
            source.fill(edited + '\n```chart\n{"componentId":"missing"}\n```\n')
            page.locator('.markdown-error').wait_for()
            assert page.get_by_role('button', name='保存 Markdown', exact=True).is_disabled()
            assert 'missing' in source.input_value()
            page.get_by_role('button', name='放弃修改', exact=True).click()
            assert source.input_value() == edited
            page.screenshot(path='report-preview.png', full_page=True)
            page.get_by_role('button', name='阅读', exact=True).click()
            page.get_by_role('button', name='仪表盘', exact=True).click()
            page.locator('.grid-stack-item').first.wait_for()
            page.get_by_role('button', name='分析报告', exact=True).click()
            page.locator('.markdown-chart canvas').first.wait_for()
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
