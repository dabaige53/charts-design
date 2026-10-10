import copy
import importlib.util
import json
from pathlib import Path
import threading
import pytest
from dashboard_runtime.legacy import import_workspace
from dashboard_runtime.model import validate
from dashboard_runtime.service import Service
from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.assets import DIST,export_document

spec=importlib.util.spec_from_file_location('fidelity_fixture',Path(__file__).with_name('fidelity_fixture.py'))
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

def test_original_workspace_import_is_lossless(tmp_path):
    doc=fixture.document();components=doc['manifest']['components'];refs={'charts':[],'kpis':[],'filters':'filters.json','table':'table.json'}
    for key,c in components.items():
        if c['family']=='table':(tmp_path/'table.json').write_text(json.dumps(c['config']));continue
        path=key+'.json';(tmp_path/path).write_text(json.dumps(c['config']));refs['charts' if c['family']=='chart' else 'kpis'].append(path)
    (tmp_path/'filters.json').write_text('[{"id":"region","fields":["region"],"type":"multi-select","options":[]}]')
    (tmp_path/'dashboard.json').write_text(json.dumps({'schemaVersion':1,'meta':{'title':'Original'},'components':refs}))
    result,_=import_workspace(tmp_path,'imported');validate(result)
    for key,c in components.items():
        imported=result['manifest']['components'].get(c['config'].get('id', key) if c['family']!='table' else c['config'].get('id', 'import-table'))
        assert imported['kind']=='legacy' and imported['family']==c['family']
        assert imported['config']==c['config']
    assert result['manifest']['originalWorkspace']['filters'][0]['type']=='multi-select'
    assert result['manifest']['components']['chart-c01']['config']['code']=='c01'

@pytest.mark.skipif(not (DIST/'app.js').exists(),reason='Build the shared frontend first')
def test_original_toolbar_kpi_table_and_offline_fidelity(tmp_path):
    from playwright.sync_api import sync_playwright
    service=Service(tmp_path/'state');doc=service.store.create('original-review','Review',fixture.document())
    server=RuntimeHTTPServer(service,0,'fidelity-token');thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1600,'height':1200});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_address[1]}/?board=original-review#fidelity-token')
            chart=page.locator('.grid-stack-item[data-component-id=t06]');chart.locator('canvas').wait_for()
            assert chart.locator('.granularity-tab-btn').count()==2
            assert chart.locator('.view-toggle-btn,.export-chart-btn,.copy-chart-btn,.fullscreen-btn,.chart-explain-btn').count()==5
            assert page.locator('[data-component-id=kpi-plf] canvas').count()==1
            assert page.locator('[data-component-id=kpi-rask]').get_by_text('+1.2% MoM',exact=True).count()==1
            chart.get_by_role('button',name='\u5b63\u5ea6',exact=True).click()
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v2')")
            assert service.store.get('original-review')['manifest']['components']['t06']['config']['defaultGranularity']=='quarter'
            chart.locator('.view-toggle-btn').click();assert chart.locator('.card-table-pane').is_visible()
            chart.locator('.view-toggle-btn').click()
            chart.locator('.chart-explain-btn').click();assert chart.locator('dialog[open]').count()==1
            chart.locator('#closeExplainModalBtn').click()
            table=page.locator('.grid-stack-item[data-component-id=original-table]');table.locator('#colDrawerBtn').click()
            assert table.locator('#colDrawerMenu').is_visible()
            checks=table.locator('#colCheckboxesContainer input');before=table.locator('th').count();checks.last.uncheck();assert table.locator('th').count()==before-1
            table.get_by_role('button',name='\u6062\u590d\u9ed8\u8ba4',exact=True).click();assert table.locator('th').count()==before
            table.locator('#colDrawerBtn').click()
            page.screenshot(path='runtime-original-restored.png',full_page=True)
            offline=tmp_path/'offline.html';offline.write_text(export_document(service.store.get('original-review')))
            page.goto(offline.as_uri());page.locator('[data-component-id=t06] canvas').wait_for();assert page.locator('iframe').count()==0
            page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(500)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close();thread.join()
