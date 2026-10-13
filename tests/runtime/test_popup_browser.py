"""Column settings survive outside clicks; filters align with their trigger."""

import threading

import pytest
from playwright.sync_api import sync_playwright

from dashboard_runtime.demo import executive_document
from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.service import Service


@pytest.mark.parametrize("width", [1440, 390])
def test_column_settings_reopen_and_filter_alignment(tmp_path, width):
    service = Service(tmp_path / "state")
    service.store.create("popups", "Popups", executive_document())
    server = RuntimeHTTPServer(service, 0, "popup-test")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/?board=popups#popup-test")
            for label, popup_label in [("区域：全部", "区域"), ("月份范围：全部月份", "月份范围")]:
                trigger = page.get_by_role("button", name=label, exact=True)
                trigger.click()
                popup = page.get_by_role("dialog", name=popup_label, exact=True)
                anchor, box = trigger.bounding_box(), popup.bounding_box()
                assert anchor is not None and box is not None
                expected = max(8, min(width - box["width"] - 8, anchor["x"]))
                assert box["x"] == pytest.approx(expected, abs=1)
                assert box["x"] + box["width"] <= width - 7
                page.keyboard.press("Escape")
            table = page.locator("[data-component-id=details]")
            for _ in range(2):
                table.get_by_label("搜索明细", exact=True).click()
                table.get_by_role("button", name="列配置", exact=True).click()
                popup = table.get_by_role("dialog", name="列设置", exact=True)
                box = popup.bounding_box()
                assert box is not None and box["height"] > 150
                assert 7 <= box["x"] and box["x"] + box["width"] <= width - 7
                checks = popup.locator('input[type="checkbox"]')
                assert checks.count() == 8
                assert all(check.is_visible() for check in checks.all())
                assert checks.first.evaluate("e=>e.getBoundingClientRect().width") == 14
                assert popup.get_by_text("基期金额", exact=True).is_visible()
                checks.last.uncheck()
                assert table.locator("th").count() == 7
                popup.get_by_role("button", name="恢复默认", exact=True).click()
                assert table.locator("th").count() == 8
                page.keyboard.press("Escape")
            assert service.store.get("popups")["revision"] == 1
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
