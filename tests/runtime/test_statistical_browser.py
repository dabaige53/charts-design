"""Real report rendering and responsive static statistical images."""
import os
from pathlib import Path
import runpy
import threading
import pytest
pytest.importorskip('seaborn')
from playwright.sync_api import sync_playwright
from dashboard_runtime.service import Service
from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.assets import export_document


def test_statistical_report_browser(tmp_path):
    doc=runpy.run_path(str(Path(__file__).with_name('test_statistical.py')))['statistical_document']()
    service=Service(tmp_path/'state');service.store.create('statistics','Statistics',doc)
    server=RuntimeHTTPServer(service,0,'statistical-test')
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,**({'executable_path':os.environ['CHARTS_CHROMIUM_EXECUTABLE']} if os.environ.get('CHARTS_CHROMIUM_EXECUTABLE') else {}))
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_address[1]}/?board=statistics#statistical-test')
            page.locator('.statistical-image').wait_for()
            page.wait_for_function("document.querySelector('.statistical-image').naturalWidth>0")
            assert page.locator('.paper-caption').count()==1
            assert 'missing observations omitted=1' in page.locator('.statistical-caption').inner_text()
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.reload();page.locator('.statistical-image').wait_for()
            page.set_content(export_document(service.store.get('statistics')))
            page.locator('.statistical-image').wait_for()
            assert page.locator('.statistical-error').count()==0
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()
