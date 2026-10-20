"""Product acceptance: visible scope, shared filters, native KPI consistency and export."""

import csv
import io
from pathlib import Path
import threading

import pytest

from dashboard_runtime.demo import document
from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.model import DashboardError, validate
from dashboard_runtime.service import Service


def test_search_contract_rejects_wrong_values_and_fields():
    for field, values in [("region", [2]), ("region", ["a", "b"]), ("revenue", ["8"])]:
        doc = document()
        doc["manifest"]["filters"] = [
            {
                "id": "search",
                "op": "contains",
                "field": field,
                "values": values,
                "componentIds": ["total"],
            }
        ]
        with pytest.raises(DashboardError):
            validate(doc)


def test_visible_filters_union_search_kpi_and_table_export(tmp_path):
    from playwright.sync_api import sync_playwright

    doc = document()
    doc["manifest"]["datasets"]["other"] = doc["manifest"]["datasets"]["sales"].copy()
    doc["snapshot"]["datasets"]["other"] = [
        dict(doc["snapshot"]["datasets"]["sales"][0], region="North")
    ]
    doc["manifest"]["components"]["details"]["datasetId"] = "other"
    doc["manifest"]["components"]["details"]["presentation"] = {
        "columns": [
            {"key": "region", "label": "地区"},
            {"key": "revenue", "label": "收入"},
        ]
    }
    doc["manifest"]["components"]["total"]["presentation"] = {
        "type": "mc02",
        "yoy": "+12% YoY",
        "mom": "+3% MoM",
        "subVal": "fixed baseline",
    }
    doc["manifest"]["filters"].append(
        {
            "id": "search",
            "op": "contains",
            "field": "region",
            "values": [],
            "label": "搜索区域",
            "componentIds": ["total", "load", "trend", "regions", "details"],
        }
    )
    service = Service(tmp_path / "state")
    service.store.create("demo", "Demo", doc)
    server = RuntimeHTTPServer(service, 0, "product-test")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(
                f"http://127.0.0.1:{server.server_address[1]}/?board=demo#product-test"
            )
            page.locator("[data-component-id=trend] canvas").wait_for()
            assert page.get_by_role("region", name="筛选条件").is_visible()
            page.get_by_role("button", name="Region：全部", exact=True).click()
            assert page.locator(".filter-choice").filter(has_text="North").count() == 1
            for choice in page.locator(".filter-choice input").all():
                choice.uncheck()
            page.locator(".filter-choice").filter(has_text="East").locator(
                "input"
            ).check()
            page.get_by_role("button", name="应用", exact=True).click()
            page.wait_for_function(
                "document.querySelector('.filter-summary').textContent==='已生效条件：1'"
            )
            assert page.get_by_role(
                "button", name="Region：East", exact=True
            ).is_visible()
            assert page.locator(".filter-summary").inner_text() == "已生效条件：1"
            kpi = page.locator("[data-component-id=total]")
            assert "278" in kpi.locator(".text-2xl").inner_text()
            assert kpi.get_by_text("+12% YoY", exact=True).count() == 0
            assert kpi.get_by_text("+3% MoM", exact=True).count() == 0
            assert kpi.get_by_text("fixed baseline", exact=True).count() == 0
            page.get_by_role("button", name="清除全部筛选", exact=True).click()
            page.wait_for_function(
                "document.querySelector('.filter-summary').textContent==='已生效条件：0'"
            )
            page.get_by_label("搜索区域", exact=True).fill("nor")
            page.get_by_role("button", name="应用搜索", exact=True).click()
            page.wait_for_function(
                "document.querySelector('.filter-summary').textContent==='已生效条件：1'"
            )
            table = page.locator("[data-component-id=details]")
            assert table.locator("tbody").get_by_text("North", exact=True).count() == 1
            assert "地区" in table.locator("thead").inner_text()
            assert table.get_by_label("搜索明细", exact=True).is_visible()
            with page.expect_response("**/api/tools/dataset_export") as download:
                table.get_by_role("button", name="导出表格 CSV", exact=True).click()
            exported = download.value.json()["export"]
            content = Path(exported["path"]).read_text(encoding="utf-8-sig")
            records = list(csv.DictReader(io.StringIO(content)))
            assert records == [{"region": "North", "revenue": "80"}]
            page.screenshot(path=".runtime-cache/executive-product.png", full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_function("document.documentElement.scrollWidth<=window.innerWidth")
            assert page.evaluate(
                "document.documentElement.scrollWidth<=window.innerWidth"
            )
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_complete_executive_case_has_visible_month_quarter_controls(tmp_path):
    from playwright.sync_api import sync_playwright
    from dashboard_runtime.demo import executive_document

    doc = executive_document("executive")
    service = Service(tmp_path / "complete")
    service.store.create("executive", "Executive", doc)
    server = RuntimeHTTPServer(service, 0, "complete-test")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(
                f"http://127.0.0.1:{server.server_address[1]}/?board=executive#complete-test"
            )
            page.locator("[data-component-id=trend] canvas").wait_for()
            chart = page.locator("[data-component-id=trend]")
            assert chart.get_by_role("button", name="季度", exact=True).is_visible()
            assert page.locator(".filter-trigger").count() == 2
            assert page.get_by_label("搜索区域", exact=True).is_visible()
            page.get_by_role("button", name="月份范围：全部月份", exact=True).click()
            assert page.get_by_role("button", name="应用范围", exact=True).is_visible()
            page.keyboard.press("Escape")
            assert '合成' not in page.locator('body').inner_text()
            assert not any(item.is_visible() for item in page.locator('[data-component-id=load]').get_by_text('—', exact=True).all())
            geometry = page.evaluate("""() => {
                const card = id => document.querySelector(`[data-component-id=${id}] .card`);
                const kpi = card('total').getBoundingClientRect(), plot = card('trend').getBoundingClientRect();
                const buttons = [...card('trend').shadowRoot.querySelectorAll('.component-actions .icon-button')].filter(b => !b.hidden).map(b => b.getBoundingClientRect());
                return {gap: plot.top-kpi.bottom, widths: buttons.map(b=>b.width), gaps: buttons.slice(1).map((b,i)=>b.left-buttons[i].right)};
            }""")
            assert geometry['gap'] == pytest.approx(24, abs=1)
            assert geometry['widths'] == [24] * 5
            assert all(abs(gap-6) < 1 for gap in geometry['gaps'])
            page.locator('.canvas').click(position={'x': 2, 'y': 2})
            page.screenshot(path=".runtime-cache/executive-complete.png", full_page=True)
            chart.get_by_role("button", name="季度", exact=True).click()
            assert service.store.get("executive")['revision'] == 1
            assert page.get_by_role('button', name='图表批注', exact=True).count() == 0
            assert page.locator('.is-draggable').count() == 0
            alignment = page.evaluate("""()=>{const ids=['total','load','passengers','goal'];const values=ids.map(id=>document.querySelector(`[data-component-id=${id}] .card`).shadowRoot.querySelector('.text-2xl').getBoundingClientRect().top);return Math.max(...values)-Math.min(...values);}""")
            assert alignment < 1
            assert page.locator('.component-code').count() == 0
            assert page.locator('.component-details').count() == 0
            assert chart.get_by_role('button', name='切换图表类型', exact=True).count() == 0
            chart.get_by_role('button', name='指标定义与语义', exact=True).click()
            assert page.get_by_role('heading', name='核心指标业务口径与数学公式', exact=True).is_visible()
            assert page.get_by_text(doc['manifest']['metrics']['revenue']['definition'], exact=True).is_visible()
            assert page.get_by_role('heading', name='查看语义', exact=True).is_visible()
            assert page.get_by_text('SUM(revenue)', exact=True).first.is_visible()
            assert page.get_by_text('SUM(yieldDelta) / SUM(yieldBase)', exact=True).first.is_visible()
            assert page.get_by_role('dialog').get_by_text('季度', exact=True).is_visible()
            assert page.get_by_text('区域：全部；月份范围：全部；搜索区域：全部', exact=True).is_visible()
            page.get_by_role('button', name='关闭', exact=True).click()
            assert service.store.get('executive')['revision'] == 1
            chart.get_by_role('button', name='全屏查看', exact=True).click()
            assert chart.locator('.original-fullscreen[open]').count() == 1
            chart.get_by_role('button', name='退出全屏', exact=True).click()
            assert chart.locator('.original-fullscreen[open]').count() == 0
            with page.expect_download() as exported:
                chart.get_by_role('button', name='导出数据', exact=True).click()
            assert exported.value.suggested_filename.endswith('.csv')
            page.get_by_role('button', name='编辑', exact=True).click()
            chart.get_by_role('button', name='切换图表类型', exact=True).click()
            assert page.get_by_role('menuitemradio', name='暂无兼容类型，保留当前数据结构', exact=True).is_disabled()
            page.keyboard.press('Escape')
            assert service.store.get('executive')['revision'] == 1
            regions = page.locator('[data-component-id=regions]')
            regions.get_by_role('button', name='切换图表类型', exact=True).click()
            page.get_by_role('menuitemradio', name='排序横向条形图', exact=True).click()
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v2')")
            assert service.store.get('executive')['manifest']['components']['regions']['config']['code'] == 'c02'
            page.set_viewport_size({'width': 390, 'height': 844})
            regions.get_by_role('button', name='切换图表类型', exact=True).wait_for()
            # GridStack animates cards into the narrow layout; assert once it settles, not mid-transition.
            page.wait_for_function('document.documentElement.scrollWidth <= innerWidth', timeout=3000)
            for label in ['切换图表类型', '导出数据', '复制图片', '全屏查看', '指标定义与语义']:
                assert regions.get_by_role('button', name=label, exact=True).is_visible()
            regions.get_by_role('button', name='切换图表类型', exact=True).click()
            page.get_by_role('menuitemradio', name='标准垂直柱状图', exact=True).click()
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v3')")
            assert service.store.get('executive')['manifest']['components']['regions']['config']['code'] == 'c01'
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
