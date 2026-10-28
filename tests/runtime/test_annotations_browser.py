import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


def test_new_annotation_targets_outer_component(tmp_path):
    root = Path(__file__).resolve().parents[2]
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.evaluate('''async () => {
              const {createAnnotations} = await import('/dashboard_runtime/web/annotations.mjs');
              const root = document.createElement('main'); document.body.append(root);
              const host = document.createElement('div'); host.dataset.componentId = 'chart';
              host.style.cssText = 'width:300px;height:200px'; root.append(host);
              const inner = document.createElement('button'); inner.dataset.componentId = 'inner';
              inner.textContent = '图表内容'; host.attachShadow({mode:'open'}).append(inner);
              window.doc = {id:'board', manifest:{components:{chart:{title:'图表'}}, annotations:[]}};
              window.annotations = createAnnotations({root, getDocument:()=>window.doc,
                save:async transform=>{window.doc.manifest.annotations=transform(window.doc.manifest.annotations)},
                readOnly:false, onError:e=>{throw e}, onMode:()=>{},
                iconButton:()=>document.createElement('button')});
              window.annotations.toggle();
            }''')
            page.locator('main').locator('button').click()
            panel = page.locator('.annotation-panel')
            assert '原位置已失效' not in panel.inner_text()
            assert page.locator('.annotation-outline').is_visible()
            panel.locator('textarea').fill('测试批注')
            panel.get_by_role('button', name='保存批注').click()
            assert panel.get_by_text('测试批注').is_visible()
            assert page.evaluate('window.doc.manifest.annotations[0].componentId') == 'chart'
            assert '原位置已失效' not in panel.inner_text()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_report_annotations_persist_and_report_missing_text(tmp_path):
    from dashboard_runtime.demo import report_document
    from dashboard_runtime.http_server import RuntimeHTTPServer
    from dashboard_runtime.service import Service
    from playwright.sync_api import expect

    service = Service(tmp_path / 'state')
    service.store.create('report-demo', 'Report', report_document('report-demo'))
    server = RuntimeHTTPServer(service, 0, 'annotation-test')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1500, 'height': 1050})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_address[1]}/?board=report-demo#annotation-test')
            page.locator('.markdown-chart canvas').first.wait_for()
            page.get_by_role('button', name='批注', exact=True).click()
            panel = page.locator('.annotation-panel')
            expect(panel).to_contain_text('暂无批注')
            chart = page.locator('.markdown-chart').first
            component_id = chart.get_attribute('data-component-id')
            chart.locator('canvas').first.click(position={'x': 100, 'y': 60})
            expect(panel).to_contain_text('新增批注')
            expect(panel).not_to_contain_text('原位置已失效')
            expect(page.locator('.annotation-outline')).to_be_visible()
            panel.locator('textarea').fill('检查图表')
            panel.get_by_role('button', name='保存批注').click()
            expect(panel).to_contain_text('1. 检查图表')
            assert service.store.get('report-demo')['manifest']['annotations'][0]['componentId'] == component_id
            paragraph = page.locator('.markdown-preview p').first
            paragraph_text = paragraph.text_content()
            assert paragraph_text is not None
            text_quote = paragraph_text.strip()[:1000]
            paragraph.click()
            expect(panel).not_to_contain_text('原位置已失效')
            panel.locator('textarea').fill('检查段落')
            panel.get_by_role('button', name='保存批注').click()
            expect(panel).to_contain_text('2. 检查段落')
            page.reload()
            page.locator('.markdown-chart canvas').first.wait_for()
            page.get_by_role('button', name='批注', exact=True).click()
            expect(panel).to_contain_text('批注（2）')
            expect(panel).not_to_contain_text('原位置已失效')
            panel.get_by_role('button', name='1. 检查图表', exact=True).click()
            expect(panel.locator('textarea')).to_have_value('检查图表')
            expect(page.locator('.annotation-outline')).to_be_visible()
            page.screenshot(path='/private/tmp/annotations-chart-verified.png')
            panel.get_by_role('button', name='返回列表').click()
            # Remove the anchored paragraph from the saved report, preserving annotations.
            doc = service.store.get('report-demo')
            markdown = doc['manifest']['report']['markdown']
            assert text_quote in markdown
            service.store.mutate('report-demo', doc['revision'], [{'op':'set_report_markdown', 'value':markdown.replace(text_quote, '替换后的段落')}])
            page.reload()
            page.locator('.markdown-chart canvas').first.wait_for()
            page.get_by_role('button', name='批注', exact=True).click()
            panel.get_by_role('button', name='2. 检查段落').click()
            expect(panel).to_contain_text('原位置已失效，批注已保留')
            expect(panel.locator('textarea')).to_have_value('检查段落')
            page.screenshot(path='/private/tmp/annotations-missing-verified.png')
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
