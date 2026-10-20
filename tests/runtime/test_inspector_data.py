"""The expanded inspector reads every filtered row without changing the board."""
import pytest
from dashboard_runtime.demo import document
from dashboard_runtime.model import DashboardError
from dashboard_runtime.service import Service


def test_inspector_reads_all_filtered_pages_and_keeps_revision(tmp_path):
    service = Service(tmp_path)
    doc = document('inspector')
    doc['snapshot']['datasets']['sales'] = [
        {'month': '2026-08', 'region': 'North' if i % 2 == 0 else 'East',
         'revenue': i, 'passengers': 1, 'seats': 2}
        for i in range(2010)
    ]
    saved = service.store.create('inspector', 'Inspector', doc)
    filters = [{'id': 'region', 'field': 'region', 'label': '区域', 'op': 'in',
                'values': ['North'], 'componentIds': ['trend']}]
    request = {'dashboardId': 'inspector', 'componentId': 'trend',
               'expectedRevision': saved['revision'], 'filters': filters}
    first = service.call('component_data', request)
    last = service.call('component_data', {**request, 'offset': 1000})
    assert first['totalRows'] == last['totalRows'] == 1005
    assert len(first['rows']) == 1000 and len(last['rows']) == 5
    assert [r['revenue'] for r in first['rows'] + last['rows']] == list(range(0, 2010, 2))
    assert service.store.get('inspector')['revision'] == saved['revision']
    with pytest.raises(DashboardError):
        service.call('component_data', {**request, 'expectedRevision': 999})
    with pytest.raises(DashboardError):
        service.call('component_data', {**request, 'limit': 1001})


def test_single_page_inspector_online_and_offline(tmp_path):
    import threading
    from playwright.sync_api import sync_playwright, expect
    from dashboard_runtime.assets import export_document
    from dashboard_runtime.demo import executive_document
    from dashboard_runtime.http_server import RuntimeHTTPServer

    service = Service(tmp_path / 'state')
    doc = executive_document('inspector')
    doc['snapshot']['datasets']['sales'] = doc['snapshot']['datasets']['sales'][:1] * 1005
    sql = 'SELECT * FROM sales WHERE year = :year'
    doc['manifest']['sources']['fixture']['query'] = {'sql': sql, 'parameters': {'year': 2026}}
    service.store.create('inspector', 'Inspector', doc)
    offline = tmp_path / 'offline.html'
    offline.write_text(export_document(service.store.get('inspector')))
    server = RuntimeHTTPServer(service, 0, 'inspector-test')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            for url in [f'http://127.0.0.1:{server.server_address[1]}/?board=inspector#inspector-test', offline.as_uri()]:
                page.goto(url)
                chart = page.locator('[data-component-id=trend]')
                chart.get_by_role('button', name='指标定义与语义', exact=True).click()
                panel = page.get_by_role('dialog')
                expect(panel.locator('tbody tr')).to_have_count(1005)
                assert panel.locator('nav, details').count() == 0
                assert panel.get_by_role('button', name='下一页', exact=True).count() == 0
                assert panel.locator('.inspector-sql').inner_text() == sql
                assert panel.get_by_text(doc['manifest']['metrics']['revenue']['definition'], exact=True).is_visible()
                assert panel.get_by_text('营业收入合计', exact=True).is_visible()
                assert panel.get_by_text('收益增量合计 ÷ 基期金额合计（按百分比显示）', exact=True).is_visible()
                assert panel.get_by_text('SUM(yieldDelta) / SUM(yieldBase)', exact=True).count() == 1
                assert panel.get_by_text('2026', exact=True).count() == 1
                assert panel.get_by_role('heading', name='坐标系维度与数据序列架构').is_visible()
                text = panel.inner_text()
                assert '示例 · 未连接业务数据 / 未执行' not in text
                assert '合成示例，仅展示版式' not in text
                page.set_viewport_size({'width': 390, 'height': 844})
                assert panel.evaluate('(p)=>p.scrollWidth<=p.clientWidth')
                page.keyboard.press('Escape')
                expect(panel).to_have_count(0)
                page.set_viewport_size({'width': 1440, 'height': 1000})
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_legacy_explanation_keeps_sql_in_source_and_long_scope_in_rows(tmp_path):
    from playwright.sync_api import sync_playwright
    from dashboard_runtime.assets import export_document
    from dashboard_runtime.demo import executive_document

    doc = executive_document('legacy-explanation')
    period = '所选报告航班月，按出发航班所属月份统计，不按出票月统计。'
    component_sql = 'SELECT SUM("transfer") FROM "snapshot_markets" WHERE office = :office'
    source_sql = 'SELECT * FROM snapshot_markets'
    definition = '所选航班月内，责任始发市场的一次中转净销售人次合计。'
    doc['manifest']['components']['total'] = {
        'kind': 'legacy', 'family': 'kpi', 'title': '纯中转市场净销售', 'sourceId': 'fixture',
        'config': {'type': 'mc01', 'label': '纯中转市场净销售', 'value': 141314, 'unit': '人次',
                   'explanation': {'overview': '观察责任始发市场的一次中转销售规模。', 'type': '关键指标',
                                   'period': period, 'comparison': '同一责任始发市场与一次中转范围',
                                   'metrics': [{'name': '纯中转净销售', 'definition': definition,
                                                'formula': 'SUM(transfer)', 'unit': '人次'}],
                                   'sql': component_sql, 'parameters': {'office': '上海'},
                                   'notes': '排除直飞和两次及以上中转。'}}}
    doc['manifest']['sources']['fixture']['query'] = {'sql': source_sql}
    for item in doc['manifest']['filters']:
        item['componentIds'] = [key for key in item['componentIds'] if key != 'total']
    path = tmp_path / 'legacy.html'
    path.write_text(export_document(doc))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 390, 'height': 844})
        page.goto(path.as_uri())
        page.locator('[data-component-id=total]').get_by_role('button', name='指标定义与语义').click()
        panel = page.get_by_role('dialog')
        assert panel.get_by_text(definition, exact=True).is_visible()
        assert panel.get_by_text('纯中转净销售合计', exact=True).is_visible()
        assert panel.get_by_text('SUM(transfer)', exact=True).count() == 0
        assert panel.locator('.inspector-specs dd').filter(has_text=period).count() == 1
        assert panel.get_by_role('heading', name='补充说明').count() == 0
        assert panel.locator('.inspector-sql').all_text_contents() == [component_sql, source_sql]
        assert panel.get_by_text('排除直飞和两次及以上中转。', exact=True).is_visible()
        assert panel.get_by_text('上海', exact=True).count() == 1
        assert panel.evaluate('(p)=>p.scrollWidth<=p.clientWidth')
        browser.close()
