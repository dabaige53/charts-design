"""Real-browser coverage for every shipped original visual, not UI mocks."""

import importlib.util
import json
from pathlib import Path
import threading
import pytest
from dashboard_runtime.model import validate
from dashboard_runtime.assets import DIST
from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.service import Service

spec = importlib.util.spec_from_file_location(
    "all_components_fixture", Path(__file__).with_name("all_components_fixture.py")
)
assert spec is not None and spec.loader is not None
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def test_all_original_contracts_are_explicit():
    doc = fixture.document()
    validate(doc)
    assert len(doc["manifest"]["components"]) == 49
    assert doc["snapshot"]["status"] == "fixture"


@pytest.mark.skipif(
    not (DIST / "app.js").exists(), reason="Build the shared frontend first"
)
def test_every_original_visual_and_icon_header(tmp_path):
    from playwright.sync_api import sync_playwright

    service = Service(tmp_path / "state")
    service.store.create("all-components", "Review", fixture.document())
    server = RuntimeHTTPServer(service, 0, "icons-test")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output = Path("component-review")
    output.mkdir(exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            errors = []
            def record_error(error):
                errors.append(error.stack)
                print(error.stack)
            page.on("pageerror", record_error)
            page.goto(
                f"http://127.0.0.1:{server.server_address[1]}/?board=all-components#icons-test"
            )
            page.wait_for_selector("[data-component-id=c01] canvas")
            page.wait_for_timeout(900)
            report = []
            for key, c in service.store.get("all-components")["manifest"][
                "components"
            ].items():
                card = page.locator(f'.grid-stack-item[data-component-id="{key}"]')
                card.scroll_into_view_if_needed()
                if c["family"] == "chart":
                    card.locator("canvas").first.wait_for()
                assert card.locator(".component-title").inner_text() == c["title"]
                assert card.locator(".component-header").count() == 1
                metrics = card.evaluate(
                    """item=>{const s=item.querySelector('.original-host').shadowRoot,h=s.querySelector('.component-header'),t=s.querySelector('.component-heading').getBoundingClientRect(),a=s.querySelector('.component-actions').getBoundingClientRect();return {titleLeft:t.left,actionsLeft:a.left,titleRight:t.right,titleTop:t.top,actionsTop:a.top,header:h.getBoundingClientRect().width,buttons:[...s.querySelectorAll('.component-actions>button')].filter(b=>!b.hidden).map(b=>({label:b.getAttribute('aria-label'),text:b.textContent.trim(),svg:!!b.querySelector('svg.ui-icon')}))}}"""
                )
                assert metrics["titleRight"] <= metrics["actionsLeft"] + 1, (
                    key,
                    metrics,
                )
                assert abs(metrics["titleTop"] - metrics["actionsTop"]) < 2, (
                    key,
                    metrics,
                )
                assert all(
                    b["label"]
                    and (
                        b["text"]
                        if c["family"] == "table"
                        else b["svg"] and not b["text"]
                    )
                    for b in metrics["buttons"]
                ), (key, metrics)
                if c["family"] == "chart":
                    assert card.locator("canvas").count() >= 1, key
                    card.locator(".view-toggle-btn").click()
                    assert card.locator(".card-table-pane").is_visible(), key
                    card.locator(".view-toggle-btn").click()
                    assert card.locator(".card-chart-pane").is_visible(), key
                    card.get_by_role(
                        "button", name="指标定义与语义", exact=True
                    ).click()
                    assert page.get_by_role(
                        "heading", name="SQL 与来源", exact=True
                    ).is_visible(), key
                    page.get_by_role("button", name="关闭", exact=True).click()
                    with page.expect_download() as downloaded:
                        card.get_by_role(
                            "button", name="导出数据", exact=True
                        ).click()
                    assert Path(downloaded.value.path()).stat().st_size > 3, key
                card.screenshot(path=str(output / (key + ".png")))
                report.append(
                    {
                        "id": key,
                        "family": c["family"],
                        "title": c["title"],
                        "header": metrics,
                        "rendered": True,
                    }
                )
            page.screenshot(path="runtime-icons-gallery.png", full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(500)
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            mobile = page.locator(".grid-stack-item[data-component-id=c01]")
            mobile.scroll_into_view_if_needed()
            for label in ["导出数据", "复制图片", "全屏查看", "指标定义与语义"]:
                assert mobile.get_by_role("button", name=label, exact=True).is_visible()
            assert page.locator(".component-code").count() == 0
            assert not errors, errors
            (output / "coverage.json").write_text(
                json.dumps(
                    {
                        "components": report,
                        "count": len(report),
                        "pageErrors": errors,
                        "mobileOverflow": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
