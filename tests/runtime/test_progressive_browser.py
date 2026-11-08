import threading
from dashboard_runtime.service import Service
from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.model import apply_operations
from test_encoding_browser import retail_document


# @wu-test type=integration | scope=渐进加载筛选 | protects=筛选后可见组件未更新 | debt=D6,D7
def test_project_progressive_browser(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    service=Service(tmp_path/'runtime',project_root=tmp_path/'project')
    service.store.create('retail','Retail',retail_document())
    calls=[]
    original=service.call
    def traced(tool,args):
        calls.append((tool,dict(args)))
        return original(tool,args)
    service.call=traced
    server=RuntimeHTTPServer(service,0,'progressive-test')
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1600,'height':1400})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/?board=retail#progressive-test')
            page.locator('[data-component-id=scatter] canvas').first.wait_for()
            page.locator('[data-component-id=bars] canvas').first.wait_for()
            assert all(len(args['componentIds'])==1 for tool,args in calls if tool=='dashboard_view')
            page.get_by_role('button',name='Store：全部',exact=True).click()
            page.locator('.filter-choice').filter(has_text='North').wait_for()
            for check in page.locator('.filter-choice input').all():check.uncheck()
            page.locator('.filter-choice').filter(has_text='North').locator('input').check()
            page.get_by_role('button',name='应用',exact=True).click()
            expression="""()=>{const h=document.querySelector('[data-component-id=bars] .card').shadowRoot;return window.getDashboardAppForElement(h.querySelector('canvas')).state.chartInstances['original-bars'].getOption().series.length===2}"""
            page.wait_for_function(expression)
            page.get_by_role('button',name='运行诊断',exact=True).click()
            expect(page.get_by_text('检查通过',exact=True)).to_be_visible()
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()


# @wu-test type=integration | scope=渐进加载输出准备与打印 | protects=未滚动到的图表缺数据或打印画布超出卡片
def test_output_readiness_loads_offscreen_charts_before_printing(tmp_path):
    from playwright.sync_api import sync_playwright
    document = apply_operations(retail_document(), [{
        'op': 'set_layout', 'breakpoint': 'desktop', 'value': [
            {'id': 'scatter', 'x': 0, 'y': 0, 'w': 12, 'h': 10},
            {'id': 'bars', 'x': 0, 'y': 10, 'w': 12, 'h': 10},
            {'id': 'details', 'x': 0, 'y': 20, 'w': 12, 'h': 6},
        ],
    }])
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.store.create('retail', 'Retail', document)
    server = RuntimeHTTPServer(service, 0, 'output-test')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1600, 'height': 300})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/?board=retail#output-test')
            page.locator('[data-component-id=scatter] canvas').first.wait_for()
            bars = page.locator('[data-component-id=bars]')
            assert bars.bounding_box()['y'] > page.viewport_size['height'] + 300
            assert bars.locator('canvas').count() == 0
            page.evaluate('window.__chartsReady()')
            assert bars.locator('canvas').count() > 0
            assert bars.locator('.card').get_attribute('aria-busy') == 'false'
            assert page.evaluate('window.scrollY') == 0
            page.emulate_media(media='print')
            bounds = bars.evaluate("""item=>{
                const root=item.querySelector('.card').shadowRoot;
                const card=root.querySelector('.section-card').getBoundingClientRect();
                const canvas=root.querySelector('canvas').getBoundingClientRect();
                return {card:card.width,canvas:canvas.width,height:canvas.height};
            }""")
            assert 0 < bounds['canvas'] <= bounds['card'] + 1, bounds
            assert bounds['height'] > 0, bounds
            output = tmp_path / 'offscreen-charts.pdf'
            page.pdf(path=str(output), print_background=True)
            assert output.read_bytes().startswith(b'%PDF-')
            assert errors == []
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
