"""Actual browser filtering of original chart, KPI and table from one dataset."""

from pathlib import Path
import importlib.util
import threading
import pytest
from dashboard_runtime.demo import document
from dashboard_runtime.model import apply_operations
from dashboard_runtime.assets import DIST
from dashboard_runtime.service import Service
from dashboard_runtime.http_server import RuntimeHTTPServer

spec = importlib.util.spec_from_file_location(
    "fixture", Path(__file__).with_name("fidelity_fixture.py")
)
assert spec is not None and spec.loader is not None
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


@pytest.mark.skipif(
    not (DIST / "app.js").exists(), reason="Build shared frontend first"
)
def test_original_filter_binding_and_persisted_table(tmp_path):
    from playwright.sync_api import sync_playwright

    doc = document()
    chart = fixture.document()["manifest"]["components"]["c01"]
    ds = doc["manifest"]["metrics"]["revenue"]["datasetId"]
    meta = doc["manifest"]["datasets"][ds]
    chart["binding"] = {
        "datasetId": ds,
        "categoryField": "region",
        "categoryTarget": "categories",
        "measures": {"values": "revenue"},
    }
    ops = [
        {"op": "put_component", "id": "bound-chart", "value": chart},
        {
            "op": "put_component",
            "id": "bound-kpi",
            "value": {
                "kind": "legacy",
                "family": "kpi",
                "title": "Bound revenue",
                "config": {
                    "label": "Bound revenue",
                    "type": "mc02",
                    "value": "old",
                    "yoy": "stale",
                },
                "binding": {"datasetId": ds, "measures": {"value": "revenue", "yoy": "load-factor"}},
            },
        },
        {
            "op": "put_component",
            "id": "bound-table",
            "value": {
                "kind": "legacy",
                "family": "table",
                "title": "Bound rows",
                "config": {
                    "columns": [{"key": key, "title": key} for key in meta["fields"]],
                    "rows": [],
                },
                "binding": {"datasetId": ds, "measures": {}},
            },
        },
    ]
    fs = doc["manifest"]["filters"]
    fs[0]["componentIds"] += ["bound-chart", "bound-kpi", "bound-table"]
    ops.append({"op": "set_filters", "value": fs})
    doc = apply_operations(doc, ops)
    service = Service(tmp_path / "state")
    service.store.create("demo", "Demo", doc)
    server = RuntimeHTTPServer(service, 0, "binding-test")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(
                f"http://127.0.0.1:{server.server_address[1]}/?board=demo#binding-test"
            )
            chart = page.locator("[data-component-id=bound-chart]")
            chart.locator("canvas").wait_for()
            values = [r["region"] for r in doc["snapshot"]["datasets"][ds]]
            chosen = values[0]
            page.get_by_role("button", name="Region：全部", exact=True).click()
            checks = page.locator(".filter-choice input")
            assert checks.count() == len(set(values))
            for i in range(checks.count()):
                checks.nth(i).uncheck()
            page.locator(".filter-choice").filter(has_text=chosen).locator(
                "input"
            ).check()
            page.get_by_role("button", name="应用", exact=True).click()
            page.wait_for_function(
                "document.querySelector('.filter-summary').textContent==='已生效条件：1'"
            )
            expected = sum(
                r["revenue"]
                for r in doc["snapshot"]["datasets"][ds]
                if r["region"] == chosen
            )
            content = page.locator(
                "[data-component-id=bound-kpi] .text-2xl"
            ).inner_text()
            assert str(expected) in content, (expected, content)
            comparison = page.locator('[data-component-id=bound-kpi] .text-positive').filter(has_text='同比')
            assert comparison.inner_text().startswith('同比 +')
            assert comparison.evaluate('(node)=>getComputedStyle(node).color') == 'rgb(164, 69, 60)'
            chart.locator(".view-toggle-btn").click()
            assert chosen in chart.locator(".card-table-pane").inner_text()
            table = page.locator("[data-component-id=bound-table]")
            assert table.locator("tbody tr").count() == sum(
                r["region"] == chosen for r in doc["snapshot"]["datasets"][ds]
            )
            table.locator("#colDrawerBtn").click()
            table.locator("#colCheckboxesContainer input").last.uncheck()
            page.keyboard.press("Escape")
            page.wait_for_timeout(600)
            assert 'tableState' not in service.store.get('demo')['manifest']['components']['bound-table']['config']
            assert service.store.get('demo')['revision'] == 1
            page.reload()
            page.locator('[data-component-id=bound-chart] canvas').wait_for()
            assert table.locator('th').count() == len(meta['fields'])
            page.get_by_role('button', name='编辑', exact=True).click()
            table.locator('#colDrawerBtn').click()
            table.locator('#colCheckboxesContainer input').last.uncheck()
            page.keyboard.press('Escape')
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v2')")
            saved = service.store.get('demo')['manifest']['components']['bound-table']['config']['tableState']
            assert len(saved['visible']) == len(meta['fields'])-1
            assert not errors, errors
            page.screenshot(path="runtime-bound-filter.png", full_page=True)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
