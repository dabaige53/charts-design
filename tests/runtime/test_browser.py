"""Runs with real Chromium and the built ECharts/GridStack bundle, not UI stubs."""

import threading
import pytest
from dashboard_runtime.assets import DIST
from dashboard_runtime.demo import document
from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.service import Service

pytestmark = pytest.mark.skipif(
    not (DIST / "app.js").exists(),
    reason="Build runtime-ui before browser acceptance testing",
)


def test_display_preserves_chart_switch_and_service_updates(tmp_path):
    from playwright.sync_api import sync_playwright

    service = Service(tmp_path / "browser")
    service.store.create("demo", "Demo", document())
    server = RuntimeHTTPServer(service, 0, "browser-test-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(
                f"http://127.0.0.1:{server.server_address[1]}/?board=demo#browser-test-token"
            )
            page.wait_for_selector('[data-component-id="trend"] canvas')
            assert (
                page.locator("[data-component-id=total] .text-2xl").first.inner_text()
                == "484 10k CNY"
            )
            assert page.get_by_role("button", name="切换图表类型", exact=True).count() == 0
            assert page.get_by_role("button", name="编辑", exact=True).is_visible()
            assert page.get_by_role("button", name="添加组件", exact=True).count() == 0
            title = page.get_by_label("Dashboard title")
            assert title.is_disabled()
            assert page.locator('.is-draggable').count() == 0
            service.store.mutate("demo", 1, [{"op": "set_title", "value": "Updated through MCP"}])
            page.reload()
            page.wait_for_function("document.querySelector('.dashboard-title').value==='Updated through MCP'")
            page.get_by_role("button", name="编辑", exact=True).click()
            assert title.is_enabled()
            assert page.get_by_role("button", name="添加组件", exact=True).count() == 0
            title.fill("可编辑经营看板")
            title.press("Tab")
            page.wait_for_function("document.querySelector('.dashboard-title').value==='可编辑经营看板'")
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v3')")
            page.get_by_label("页面描述", exact=True).fill("最新经营描述")
            page.get_by_label("页面描述", exact=True).press("Enter")
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v4')")
            trend = page.locator('[data-component-id="trend"]')
            trend.get_by_label("图表标题", exact=True).fill("收入走势")
            trend.get_by_label("图表标题", exact=True).press("Enter")
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v5')")
            trend.get_by_label("图表描述", exact=True).fill("按月比较收入")
            trend.get_by_label("图表描述", exact=True).press("Enter")
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v6')")
            assert page.get_by_role("button", name="编辑组件", exact=True).count() == 0
            assert page.evaluate("document.querySelector('.grid-stack').gridstack.opts.disableResize")
            before = service.store.get("demo")["revision"]
            page.evaluate("()=>{const g=document.querySelector('.grid-stack').gridstack;g.update(document.querySelector('[data-component-id=trend]'),{x:6});}")
            page.wait_for_function(f"document.querySelector('#notice').textContent.includes('v{before+1}')")
            assert next(x for x in service.store.get('demo')['manifest']['layout']['desktop'] if x['id']=='trend')['w'] == 6
            trend.get_by_role("button", name="图表批注", exact=True).click()
            page.get_by_label("新增批注", exact=True).fill("八月收入增长，需核对原因。")
            page.get_by_role("button", name="添加批注", exact=True).click()
            page.get_by_label("批注内容", exact=True).wait_for()
            page.get_by_label("批注内容", exact=True).fill("八月收入增长，已核对。")
            page.get_by_role("button", name="保存批注", exact=True).click()
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v9')")
            page.get_by_role("button", name="关闭", exact=True).click()
            page.reload()
            page.locator('[data-component-id="trend"] canvas').wait_for()
            assert page.get_by_label("Dashboard title").input_value() == "可编辑经营看板"
            assert trend.get_by_role("button", name="图表批注", exact=True).count() == 0
            trend.get_by_role("button", name="指标定义与语义", exact=True).click()
            assert page.get_by_text("八月收入增长，已核对。", exact=True).is_visible()
            assert page.get_by_role("heading", name="查看语义", exact=True).is_visible()
            assert page.get_by_text("SUM(revenue)", exact=True).first.is_visible()
            assert page.get_by_role("heading", name="SQL 与来源", exact=True).is_visible()
            page.get_by_text("未记录 SQL", exact=True).wait_for()
            page.get_by_role("button", name="关闭", exact=True).click()
            page.get_by_role("button", name="编辑", exact=True).click()
            trend.get_by_role("button", name="图表批注", exact=True).click()
            assert page.get_by_label("批注内容", exact=True).input_value() == "八月收入增长，已核对。"
            page.get_by_role("button", name="删除批注", exact=True).click()
            page.get_by_text("暂无批注", exact=True).wait_for()
            page.get_by_role("button", name="关闭", exact=True).click()
            page.screenshot(path="runtime-screenshot.png", full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(400)
            assert page.locator(".card").count() == 5
            assert page.evaluate(
                "document.documentElement.scrollWidth<=window.innerWidth"
            )
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_metadata_and_component_descriptions_survive_render(tmp_path):
    from playwright.sync_api import sync_playwright

    doc = document()
    doc["manifest"]["originalWorkspace"] = {
        "meta": {"org": "Imported organization", "subtitle": "Imported description"}
    }
    doc["manifest"]["components"]["total"]["subtitle"] = (
        "KPI description <b>plain text</b>"
    )
    doc["manifest"]["components"]["details"]["subtitle"] = "Table description"
    doc["manifest"]["components"]["trend"]["subtitle"] = "Chart description"
    service = Service(tmp_path / "metadata")
    service.store.create("demo", "Demo", doc)
    server = RuntimeHTTPServer(service, 0, "metadata-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(
                f"http://127.0.0.1:{server.server_address[1]}/?board=demo#metadata-token"
            )
            page.wait_for_selector('[data-component-id="trend"] canvas')
            assert (
                page.locator(".dashboard-description").inner_text()
                == "Imported description"
            )
            assert (
                page.locator(".dashboard-context").inner_text()
                == "Imported organization"
            )
            assert (
                page.locator(
                    "[data-component-id=total] .component-subtitle"
                ).inner_text()
                == "KPI description <b>plain text</b>"
            )
            assert (
                page.locator("[data-component-id=total] .component-subtitle b").count()
                == 0
            )
            assert (
                page.locator(
                    "[data-component-id=details] .component-subtitle"
                ).inner_text()
                == "Table description"
            )
            assert (
                "Chart description"
                in page.locator("[data-component-id=trend] p").first.inner_text()
            )
            service.store.mutate(
                "demo",
                1,
                [
                    {
                        "op": "set_meta",
                        "value": {
                            "subtitle": "Explicit description",
                            "org": "New organization",
                        },
                    }
                ],
            )
            page.reload()
            page.wait_for_function(
                "document.querySelector('.dashboard-description').textContent==='Explicit description'"
            )
            assert page.locator(".dashboard-context").inner_text() == "New organization"
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
