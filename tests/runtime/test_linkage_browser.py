"""Clicking a bound chart category links compatible components and greys out the rest."""

import threading

from playwright.sync_api import sync_playwright

from dashboard_runtime.demo import executive_document
from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.model import apply_operations
from dashboard_runtime.service import Service


def unbound_goal_document():
    doc = executive_document()
    m = doc["manifest"]
    goal = {k: v for k, v in m["components"]["goal"].items() if k not in ("binding", "datasetId")}
    filters = [{**f, "componentIds": [c for c in f["componentIds"] if c != "goal"]} for f in m["filters"]]
    return apply_operations(doc, [
        {"op": "set_filters", "value": filters},
        {"op": "put_component", "id": "goal", "value": goal},
    ])


def test_chart_click_links_compatible_components_and_blurs_the_rest(tmp_path):
    service = Service(tmp_path / "state")
    before = service.store.create("link", "Link", unbound_goal_document())
    server = RuntimeHTTPServer(service, 0, "link-test")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1400})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/?board=link#link-test")
            regions = page.locator("[data-component-id=regions] canvas").first
            regions.wait_for()
            box = regions.bounding_box()
            assert box is not None
            grid_top = page.evaluate("document.querySelector('.grid-stack').getBoundingClientRect().top")
            # At 1440px the chart renders vertical bars; 华东基地 is the left bar, its lower body is safely clickable.
            page.mouse.click(box["x"] + box["width"] * 0.32, box["y"] + box["height"] * 0.65)
            chip = page.locator(".linkage-chip")
            chip.wait_for()
            chip_text = chip.inner_text()
            assert "区域 = 华东基地" in chip_text
            assert "生效" not in chip_text
            off = page.locator(".linkage-off")
            assert off.count() == 1 and off.get_attribute("data-component-id") == "goal"
            tag = page.locator(".linkage-off-note span")
            assert tag.text_content() == "未参与联动" and tag.get_attribute("title") == "未绑定数据"
            # The linkage chip floats; it must not push the filter bar or the grid down.
            assert page.evaluate("getComputedStyle(document.querySelector('.linkage-chip')).position") == "fixed"
            assert page.evaluate("document.querySelector('.grid-stack').getBoundingClientRect().top") == grid_top
            regions_in_table = page.evaluate(
                "[...document.querySelector('[data-component-id=details] .grid-stack-item-content')"
                ".shadowRoot.querySelectorAll('tbody tr')].map(r=>r.children[1].textContent.trim())"
            )
            assert regions_in_table and set(regions_in_table) == {"华东基地"}
            clear = page.get_by_role("button", name="清除所有筛选", exact=True)
            assert clear.is_visible() and clear.is_enabled()
            assert page.locator(".filter-summary").inner_text() == "已生效条件：1"
            clear.click()
            page.wait_for_function("!document.querySelector('.linkage-chip')")
            assert page.locator(".linkage-off").count() == 0
            assert clear.is_visible() and clear.is_disabled()
            regions_in_table = page.evaluate(
                "[...document.querySelector('[data-component-id=details] .grid-stack-item-content')"
                ".shadowRoot.querySelectorAll('tbody tr')].map(r=>r.children[1].textContent.trim())"
            )
            assert len(set(regions_in_table)) > 1
            # Escape remains available for cancelling the next chart selection.
            regions = page.locator("[data-component-id=regions] canvas").first
            box = regions.bounding_box()
            assert box is not None
            page.mouse.click(box["x"] + box["width"] * 0.32, box["y"] + box["height"] * 0.65)
            chip.wait_for()
            page.keyboard.press("Escape")
            page.wait_for_function("!document.querySelector('.linkage-chip')")
            assert page.locator(".linkage-off").count() == 0
            # Linking is a reading aid only; nothing is written to the dashboard.
            assert service.store.get("link")["revision"] == before["revision"]
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
