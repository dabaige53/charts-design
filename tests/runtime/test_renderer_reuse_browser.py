"""Canonical offline renderer retains live charts and bounds large table DOM."""
import importlib
import re
import sys
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / 'skills/executive-charts/scripts'))
generate_html = importlib.import_module('core.dashboard_template').generate_dashboard_html
ECHARTS = ROOT / 'runtime-ui/node_modules/echarts/dist/echarts.min.js'


@pytest.fixture
def renderer_page():
    if not ECHARTS.exists():
        pytest.skip('Install runtime-ui dependencies first')
    html = generate_html('', 'Renderer reuse')
    source = next(script for script in re.findall(r'<script\b[^>]*>(.*?)</script>', html, re.S) if 'class DashboardApp' in script)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        page.set_content('''<style>
        #app-charts-grid .card-chart-pane {height:270px;width:600px}
        #app-kpis div[id^=kpi-] {height:44px;width:300px}
        table {border-collapse:collapse;width:100%} td,th {padding:8px 14px;white-space:nowrap;font:12px monospace}
        </style><div id="app-kpis"></div><div id="app-charts-grid"></div><div id="app-table-section"></div>''')
        page.add_script_tag(path=str(ECHARTS))
        page.add_script_tag(content=source)
        page.evaluate('''() => {
          window.config = () => ({meta:{title:'Test'}, filters:[],
            kpis:[{id:'spark',type:'mc03',label:'收入',value:12,sparkMonths:['一月','二月'],sparkData:[4,12]}],
            charts:[{id:'trend',code:'c01',title:'收入',data:[2,4], optionBuilder(data){return {
              animation:false,legend:{data:['保留','移除']},dataZoom:[{id:'zoom',type:'inside'}],
              xAxis:{type:'category',data:['一月','二月']},yAxis:{type:'value'},
              series:data.map((value,i)=>({name:i?'移除':'保留',type:'bar',data:[value,value+1]}))
            }}}], table:{columns:[{key:'name',title:'名称',align:'left'},{key:'value',title:'值',align:'right'}],
              rows:Array.from({length:600},(_,i)=>({name:`记录${i}`,value:i}))}});
          window.runtime = createDashboardRuntime(config()); runtime.mount();
        }''')
        yield page
        browser.close()


def test_update_retains_canvas_chrome_and_interaction_state(renderer_page):
    page = renderer_page
    page.evaluate('''() => {
      window.app = runtime.app;
      window.chart = app.state.chartInstances.trend;
      window.spark = app.state.chartInstances['kpi-spark-spark'];
      window.canvas = document.querySelector('#trend canvas');
      window.sparkCanvas = document.querySelector('#kpi-spark-spark canvas');
      window.chrome = document.createElement('header'); chrome.className='component-header'; chrome.textContent='Custom title';
      document.querySelector('#app-charts-grid .section-card').prepend(chrome);
      const kpi=document.querySelector('#spark');
      window.kpiChrome=document.createElement('header');kpiChrome.className='component-header';kpiChrome.textContent='Custom metric';
      kpi.firstElementChild.replaceWith(kpiChrome);
      const sections=[...kpi.children].slice(1),value=sections.shift(),footer=sections.pop(),aux=document.createElement('div');
      value.classList.add('kpi-headline');footer.classList.add('kpi-footer');aux.className='kpi-aux';aux.append(...sections);
      kpi.replaceChildren(kpiChrome,value,aux,footer);kpi.classList.add('kpi-aligned');
      chart.dispatchAction({type:'legendUnSelect',name:'保留'});
      chart.dispatchAction({type:'dataZoom',dataZoomId:'zoom',start:20,end:75});
      const next=config(); next.charts[0].data=[9]; next.kpis[0].value=99; next.kpis[0].sparkData=[9,99];
      runtime.update(next);
    }''')
    assert page.evaluate('runtime.app===app && app.state.chartInstances.trend===chart && document.querySelector("#trend canvas")===canvas')
    assert page.evaluate('app.state.chartInstances["kpi-spark-spark"]===spark && document.querySelector("#kpi-spark-spark canvas")===sparkCanvas')
    assert page.evaluate('chrome.isConnected && chart.getOption().series.length===1 && chart.getOption().legend[0].selected["保留"]===false')
    assert page.evaluate('chart.getOption().dataZoom[0].start===20 && chart.getOption().dataZoom[0].end===75')
    assert '99' in page.locator('#spark').inner_text()
    assert page.evaluate('kpiChrome.isConnected && document.querySelector("#spark").children.length===4 && document.querySelector("#spark > .kpi-headline").textContent.includes("99") && document.querySelector("#spark > .kpi-aux #kpi-spark-spark")!==null')
    page.evaluate("const next=config();next.charts[0].code='c02';runtime.update(next)")
    assert page.evaluate('chart.isDisposed() && app.state.chartInstances.trend!==chart')
    page.evaluate('runtime.destroy()')
    assert page.evaluate('spark.isDisposed() && runtime.app===null')


def test_large_page_window_sort_and_csv_keep_all_rows(renderer_page):
    page = renderer_page
    page.evaluate('runtime.app.state.table.pageSize=600;runtime.app.renderTableEngine()')
    assert page.locator('#main14ColTbody tr').count() < 60
    assert page.locator('#main14ColTbody').evaluate('body=>body.closest("table").getAttribute("aria-rowcount")') == '601'
    widths = page.locator('thead th').evaluate_all('headers=>headers.map(header=>header.getBoundingClientRect().width)')
    page.locator('#main14ColTbody').evaluate('body=>body.closest("table").parentElement.scrollTop=100000')
    page.wait_for_function('document.querySelector("#main14ColTbody").textContent.includes("记录599")')
    assert page.locator('thead th').evaluate_all('headers=>headers.map(header=>header.getBoundingClientRect().width)') == widths
    assert page.locator('#main14ColTbody tr[aria-rowindex="601"]').count() == 1
    page.evaluate('runtime.app.sortTable("value")')
    assert page.locator('#main14ColTbody tr').count() < 60
    page.evaluate('''() => {
      window.csvBlob=null; URL.createObjectURL=blob=>{window.csvBlob=blob;return 'blob:test'};
      HTMLAnchorElement.prototype.click=function(){};runtime.app.exportTableToCSV();
    }''')
    assert page.evaluate('(async()=> (await csvBlob.text()).split("\\r\\n").length)()') == 601
    page.evaluate('runtime.destroy()')
    assert page.evaluate('runtime.app===null')


def test_chart_data_view_retains_all_rows_and_exports_every_row(renderer_page):
    page = renderer_page
    page.evaluate('''() => {
      const next=config();next.charts[0].data=Array.from({length:45},(_,i)=>i);
      next.charts[0].optionBuilder=data=>({animation:false,xAxis:{type:'category',data:data.map(i=>`类别${i}`)},yAxis:{type:'value'},series:[{type:'bar',name:'金额',data}]});
      runtime.update(next);
    }''')
    page.locator('.view-toggle-btn').click()
    pane = page.locator('#table-pane-trend')
    assert pane.locator('tbody tr').count() == 45
    assert pane.locator('tbody tr').first.inner_text().startswith('类别0')
    assert pane.locator('tbody tr').last.inner_text().startswith('类别44')
    page.evaluate('''() => {
      window.csvBlob=null;URL.createObjectURL=blob=>{window.csvBlob=blob;return 'blob:test'};
      HTMLAnchorElement.prototype.click=function(){};
    }''')
    page.locator('.export-chart-btn').click()
    assert page.evaluate('(async()=> (await csvBlob.text()).split("\\r\\n").length)()') == 46
    page.evaluate('''() => {
      const next={...runtime.app.config,charts:runtime.app.config.charts.map(chart=>({...chart,data:Array.from({length:46},(_,i)=>i)}))};runtime.update(next);
    }''')
    assert pane.locator('tbody tr').count() == 46
    assert pane.locator('tbody tr').first.inner_text().startswith('类别0')
    page.evaluate('''() => {
      const next={...runtime.app.config,charts:runtime.app.config.charts.map(chart=>({...chart,data:[0,1,2]}))};runtime.update(next);
    }''')
    assert pane.locator('tbody tr').count() == 3
    assert pane.locator('[data-chart-table-page]').count() == 0


def test_offline_update_refreshes_declarations_without_replacing_table_body(renderer_page):
    page = renderer_page
    page.evaluate('''() => {
      for(const id of ['app-header','app-filters']){const host=document.createElement('div');host.id=id;document.body.prepend(host);}
      window.tableBody=document.querySelector('#main14ColTbody');
      const next=config();next.meta.title='新标题';next.table.title='新明细';
      next.filters=[{id:'region',key:'region',label:'区域',type:'select',fields:['name'],options:[{value:'ALL',label:'全部',default:true},{value:'记录1',label:'一店'}]}];
      runtime.update(next);
    }''')
    assert page.locator('#app-header').inner_text().startswith('新标题')
    assert page.locator('[data-dashboard-table-title]').inner_text() == '新明细'
    assert page.locator('#filterWrap_region').count() == 1
    page.evaluate('''() => {
      runtime.app.selectFilterOption('region','记录1','一店');
      window.filterControl=document.querySelector('#filterWrap_region');
      const next={...runtime.app.config,table:{...runtime.app.config.table,rows:[...runtime.app.config.table.rows],columns:[...runtime.app.config.table.columns,{key:'extra',title:'新列',align:'left'}]}};
      runtime.update(next);
    }''')
    assert page.evaluate('runtime.app.state.filterValues.region==="记录1" && document.querySelector("#filterWrap_region")===filterControl && document.querySelector("#main14ColTbody")===tableBody')
    assert '新列' in page.locator('#main14ColThead').inner_text()
    page.evaluate('''() => {
      const next={...runtime.app.config,filters:[{id:'store',key:'store',label:'门店',type:'select',fields:['name'],options:[{value:'ALL',label:'所有店',default:true}]}],tableState:{page:2,pageSize:20,columns:['value','name','extra'],visible:['name','value'],sortCol:'value',sortDir:'desc'}};
      runtime.update(next);
    }''')
    assert page.locator('#filterWrap_region').count() == 0
    assert page.locator('#filterWrap_store').count() == 1
    assert page.evaluate('runtime.app.state.table.page===2 && runtime.app.state.table.pageSize===20 && runtime.app.state.table.sortDir==="desc" && runtime.app.state.table.orderedColumns[0].key==="value" && runtime.app.state.table.visibleCols.size===2')
    page.evaluate('''() => {
      const {tableState,...next}=runtime.app.config;
      runtime.update({...next,table:{...next.table,title:'再次更新'}});
    }''')
    assert page.evaluate('runtime.app.state.table.page===2 && runtime.app.state.table.pageSize===20 && document.querySelector("#main14ColTbody")===tableBody')
    assert page.locator('[data-dashboard-table-title]').inner_text() == '再次更新'


def test_chart_data_window_scroll_resize_updates_and_cleanup(renderer_page):
    page = renderer_page
    page.add_style_tag(content='''
      .card-table-pane > div {height:270px;overflow:auto}
      .card-table-pane thead {position:sticky;top:0;background:white}
      .hidden {display:none}
    ''')
    page.evaluate('''() => {
      const next=config();next.charts[0].data=Array.from({length:10000},(_,i)=>i);
      next.charts[0].optionBuilder=data=>({animation:false,xAxis:{type:'category',data:data.map(i=>`类别${i}`)},yAxis:{type:'value'},series:[{type:'bar',name:'金额',data}]});
      runtime.update(next);
      window.keptChart=runtime.app.state.chartInstances.trend;
    }''')
    page.locator('.view-toggle-btn').click()
    pane = page.locator('#table-pane-trend')
    rows = pane.locator('tbody tr[aria-rowindex]')
    assert 1 < rows.count() < 60
    initial_count = rows.count()
    assert pane.locator('table').get_attribute('aria-rowcount') == '10001'
    widths = pane.locator('th').evaluate_all('cells=>cells.map(cell=>cell.getBoundingClientRect().width)')
    pane.evaluate('pane=>pane.firstElementChild.scrollTop=150000')
    page.wait_for_function('Number(document.querySelector("#table-pane-trend tr[aria-rowindex]").getAttribute("aria-rowindex"))>100')
    assert rows.count() < 60
    pane.evaluate('pane=>pane.firstElementChild.scrollTop=10000000')
    page.wait_for_function("selector=>!!document.querySelector(selector)", arg='#table-pane-trend tr[aria-rowindex="10001"]')
    assert rows.last.inner_text().startswith('类别9999')
    assert pane.locator('th').evaluate_all('cells=>cells.map(cell=>cell.getBoundingClientRect().width)') == widths
    assert pane.locator('thead').evaluate('head=>Math.abs(head.getBoundingClientRect().top-head.closest("table").parentElement.getBoundingClientRect().top)<2')
    pane.evaluate('pane=>{pane.firstElementChild.style.height="650px";pane.firstElementChild.scrollTop=0}')
    page.wait_for_function('count=>document.querySelectorAll("#table-pane-trend tr[aria-rowindex]").length>count', arg=initial_count)
    assert rows.count() < 80
    assert rows.first.inner_text().startswith('类别0')
    page.evaluate('''() => {
      window.csvBlob=null;URL.createObjectURL=blob=>{window.csvBlob=blob;return 'blob:test'};
      HTMLAnchorElement.prototype.click=function(){};
    }''')
    page.locator('.export-chart-btn').click()
    assert page.evaluate('(async()=> (await csvBlob.text()).split("\\r\\n").length)()') == 10001
    for _ in range(5):
        page.locator('.view-toggle-btn').click()
        assert page.evaluate('runtime.app._chartTableCleanups.size') == 0
        page.locator('.view-toggle-btn').click()
        assert page.evaluate('runtime.app._chartTableCleanups.size') == 1
    page.evaluate('''() => {
      const next={...runtime.app.config,charts:runtime.app.config.charts.map(chart=>({...chart,data:[0,1,2]}))};runtime.update(next);
    }''')
    assert rows.count() == 3
    assert page.evaluate('runtime.app._chartTableCleanups.size===0 && runtime.app.state.chartInstances.trend===keptChart')
    page.evaluate('''() => {
      const next={...runtime.app.config,charts:runtime.app.config.charts.map(chart=>({...chart,data:Array.from({length:500},(_,i)=>i)}))};runtime.update(next);
    }''')
    assert rows.count() < 60
    assert page.evaluate('runtime.app._chartTableCleanups.size') == 1
    page.evaluate('window.oldApp=runtime.app;runtime.update({...runtime.app.config,charts:[]})')
    assert page.evaluate('oldApp._chartTableCleanups.size') == 0
    page.evaluate('runtime.destroy()')


def test_chart_data_window_handles_wrapped_rows(renderer_page):
    page = renderer_page
    page.add_style_tag(content='''
      .hidden {display:none}
      .card-table-pane > div {height:270px;overflow:auto;width:400px}
      .card-table-pane table {width:400px!important;max-width:400px}
      .card-table-pane td {white-space:normal;overflow-wrap:anywhere}
    ''')
    page.evaluate('''() => {
      const next=config();next.charts[0].data=Array.from({length:500},(_,i)=>i);
      next.charts[0].optionBuilder=data=>({animation:false,xAxis:{type:'category',data:data.map(i=>i%3?`类别${i}`:`类别${i} `+'换行文本 '.repeat(20))},yAxis:{type:'value'},series:[{type:'bar',name:'金额',data}]});
      runtime.update(next);
    }''')
    page.locator('.view-toggle-btn').click()
    pane = page.locator('#table-pane-trend')
    for fraction in (0.3, 0.6, 1, 0):
        pane.evaluate('(pane,fraction)=>{const scroll=pane.firstElementChild;scroll.scrollTop=fraction*(scroll.scrollHeight-scroll.clientHeight)}', fraction)
        page.wait_for_function('''() => {
          const pane=document.querySelector('#table-pane-trend'),scroll=pane.firstElementChild;
          const rows=[...pane.querySelectorAll('tr[aria-rowindex]')];
          return rows.length<80 && rows[0].getBoundingClientRect().top<=scroll.getBoundingClientRect().bottom && rows.at(-1).getBoundingClientRect().bottom>=scroll.getBoundingClientRect().bottom-2;
        }''')
    pane.evaluate('pane=>pane.firstElementChild.scrollTop=10000000')
    page.wait_for_function("selector=>!!document.querySelector(selector)", arg='#table-pane-trend tr[aria-rowindex="501"]')
    assert pane.locator('tr[aria-rowindex="501"]').inner_text().startswith('类别499')
    page.evaluate('window.oldApp=runtime.app;runtime.destroy()')
    assert page.evaluate('oldApp._chartTableCleanups.size') == 0


def test_chart_data_window_in_bundled_and_offline_pages(tmp_path):
    import importlib.util
    import threading
    from playwright.sync_api import expect
    from dashboard_runtime.assets import export_document
    from dashboard_runtime.http_server import RuntimeHTTPServer
    from dashboard_runtime.service import Service

    spec = importlib.util.spec_from_file_location('window_fixture', Path(__file__).with_name('fidelity_fixture.py'))
    assert spec is not None and spec.loader is not None
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    doc = fixture.document('window-test')
    doc['manifest']['components']['c01']['config']['data'] = {
        'categories': [f'类别{i}' for i in range(1000)], 'values': list(range(1000))}
    service = Service(tmp_path / 'state')
    saved = service.store.create('window-test', 'Window test', doc)
    offline = export_document(saved)
    server = RuntimeHTTPServer(service, 0, 'window-token')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            base = f'http://127.0.0.1:{server.server_port}'
            page.route('**/virtual-offline.html', lambda route: route.fulfill(content_type='text/html', body=offline))
            for url in [base + '/?board=window-test#window-token', base + '/virtual-offline.html']:
                page.goto(url)
                chart = page.locator('.grid-stack-item[data-component-id=c01]')
                chart.scroll_into_view_if_needed()
                chart.locator('canvas').first.wait_for()
                chart.locator('.view-toggle-btn').click()
                pane = chart.locator('.card-table-pane')
                rows = pane.locator('tbody tr[aria-rowindex]')
                assert 1 < rows.count() < 80
                expect(pane.locator('table')).to_have_attribute('aria-rowcount', '1001')
                pane.evaluate('pane=>pane.firstElementChild.scrollTop=1000000')
                expect(pane.locator('tr[aria-rowindex="1001"]')).to_contain_text('类别999')
                chart.get_by_role('button', name='全屏查看', exact=True).click()
                assert rows.count() < 100
                page.keyboard.press('Escape')
                with page.expect_download() as downloaded:
                    chart.get_by_role('button', name='导出数据', exact=True).click()
                path = downloaded.value.path()
                assert len(Path(path).read_text().splitlines()) == 1001
                page.set_viewport_size({'width': 390, 'height': 844})
                pane.evaluate('pane=>pane.firstElementChild.scrollTop=1000000')
                expect(pane.locator('tr[aria-rowindex="1001"]')).to_contain_text('类别999')
                assert rows.count() < 100
                page.set_viewport_size({'width': 1440, 'height': 1000})
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
