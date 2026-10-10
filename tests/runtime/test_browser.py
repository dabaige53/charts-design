"""Runs with real Chromium and the built ECharts/GridStack bundle, not UI stubs."""
import threading
import time
from pathlib import Path
import pytest
from dashboard_runtime.assets import DIST
from dashboard_runtime.demo import document
from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.service import Service
pytestmark=pytest.mark.skipif(not (DIST/'app.js').exists(),reason='Build runtime-ui before browser acceptance testing')

def test_editor_preview_switch_layout_and_inspect(tmp_path):
    from playwright.sync_api import sync_playwright
    service=Service(tmp_path/'browser');service.store.create('demo','Demo',document())
    server=RuntimeHTTPServer(service,0,'browser-test-token');thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1100});errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_address[1]}/?board=demo#browser-test-token')
            page.wait_for_selector('[data-component-id="trend"] canvas')
            assert page.locator('[data-component-id=total] .text-2xl').first.inner_text()=='484 10k CNY'
            page.get_by_role('button',name='切换图表',exact=True).first.click()
            page.get_by_role('menuitemradio',name='柱状图',exact=True).click()
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v2')")
            assert service.store.get('demo')['manifest']['components']['trend']['chartType']=='bar'
            page.get_by_role('button',name='编辑',exact=True).click()
            title=page.get_by_label('Dashboard title');title.fill('Edited dashboard');title.press('Tab')
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v3')")
            before=service.store.get('demo')['manifest']['layout']['desktop']
            page.evaluate("""()=>{const g=document.querySelector('.grid-stack').gridstack;g.update(document.querySelector('[data-component-id=trend]'),{w:12});}""")
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v4')")
            assert service.store.get('demo')['manifest']['layout']['desktop']!=before
            page.get_by_role('button',name='撤销',exact=True).click()
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v5')")
            assert service.store.get('demo')['manifest']['layout']['desktop']==before
            page.locator('[data-component-id="load"]').get_by_role('button',name='SQL / 语义',exact=True).click()
            page.wait_for_selector('dialog.inspector[open]')
            assert 'denominator' in page.locator('dialog.inspector[open]').inner_text()
            page.get_by_role('button',name='查询来源',exact=True).click()
            page.wait_for_function("document.querySelector('dialog.inspector').textContent.includes('fixture')")
            page.get_by_role('button',name='关闭',exact=True).click()
            page.screenshot(path='runtime-screenshot.png',full_page=True)
            page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(400)
            assert page.locator('.card').count()==5
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close();thread.join()
