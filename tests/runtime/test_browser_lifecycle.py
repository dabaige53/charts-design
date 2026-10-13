"""Actual page visibility controls the lifetime of the local preview."""
import threading

from playwright.sync_api import sync_playwright

from dashboard_runtime.demo import document
from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.service import Service


def test_visible_preview_keeps_running_and_closed_preview_exits(tmp_path):
    service = Service(tmp_path)
    service.store.create('demo', 'Demo', document())
    server = RuntimeHTTPServer(service, 0, 'visibility-test', idle_timeout=0.6)
    thread = threading.Thread(target=lambda: server.serve_forever(0.02), daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            with server.lifetime.activity():
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                page.goto(f'http://127.0.0.1:{server.server_port}/?board=demo#token=visibility-test')
                page.locator('[data-component-id="trend"] canvas').wait_for()
            page.wait_for_timeout(1000)
            assert thread.is_alive()
            page.close()
            thread.join(3)
            assert not thread.is_alive()
            assert service.store.get('demo')['revision'] == 1
            browser.close()
    finally:
        if thread.is_alive():
            server.shutdown()
        server.server_close()
        thread.join()
