import threading
from dashboard_runtime.service import Service
from dashboard_runtime.http_server import RuntimeHTTPServer
from test_encoding_browser import retail_document


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
