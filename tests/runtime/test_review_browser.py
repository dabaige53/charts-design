"""Real DOM tests of the review modules, with explicit fixture-only transport.

This is not a replacement for the repository's full app/MCP/browser suite.
"""
import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.browser


def open_fixture(page, query='', saved=None):
    """Mount real ES modules in an offline DOM; transport remains a test double.

    No URL navigation, download, external dependencies, or browser policy changes.
    The small loader only replaces ES import/export syntax with lexical modules.
    """
    import json
    import re
    web = ROOT / 'dashboard_runtime' / 'web'
    paths = ['review-state.mjs', 'annotation-points.mjs', 'annotations.mjs']
    variables = {'review-state.mjs': 'stateModule', 'annotation-points.mjs': 'pointModule', 'annotations.mjs': 'annotationModule'}
    bundle = ''
    for name in paths:
        source = (web / name).read_text()
        exported = re.findall(r'export\s+(?:function|const)\s+(\w+)', source)
        for dependency, variable in variables.items():
            source = re.sub(r"import\s*\{([^}]+)\}\s*from\s*'\./" + re.escape(dependency) + r"';", lambda m: 'const {' + m[1] + '}=' + variable + ';', source)
        source = re.sub(r'\bexport\s+(?=function|const)', '', source)
        bundle += 'const ' + variables[name] + '=(()=>{\n' + source + '\nreturn {' + ','.join(exported) + '};})();\n'
    html = (ROOT / 'tests/runtime/fixtures/review-harness.html').read_text()
    script = re.search(r'<script type="module">(.*?)</script>', html, re.S)[1]
    script = re.sub(r"import\s*\{([^}]+)\}\s*from\s*'[^']+/annotations.mjs';", r'const {\1}=annotationModule;', script)
    script = re.sub(r"import\s*\{([^}]+)\}\s*from\s*'[^']+/annotation-points.mjs';", r'const {\1}=pointModule;', script)
    script = script.replace('location.search', json.dumps(query)).replace('localStorage', 'testStorage')
    storage = "const stored=new Map();const testStorage={getItem:k=>stored.get(k)||null,setItem:(k,v)=>stored.set(k,v),clear:()=>stored.clear()};\n"
    if saved is not None:
        storage += 'testStorage.setItem("review-fixture",' + json.dumps(json.dumps(saved)) + ');\n'
    html = re.sub(r'<script type="module">.*?</script>', '', html, flags=re.S)
    html = re.sub(r'<link[^>]+>', '', html)
    html += '<style>' + (web / 'reviews.css').read_text() + '</style>'
    page.evaluate('window.fixture?.manager.destroy()')
    page.set_content(html)
    page.add_script_tag(content='(()=>{\n' + bundle + storage + script + '\n})();')
    page.wait_for_function('window.ready===true')


@pytest.fixture
def page():
    with sync_playwright() as p:
        executable = os.getenv('CHARTS_TEST_CHROMIUM')
        browser = p.chromium.launch(**({'executable_path': executable} if executable else {}), args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = context.new_page()
        page.set_default_timeout(4000)
        open_fixture(page)
        page.on('dialog', lambda dialog: dialog.accept())
        yield page
        browser.close()


def click_text(page, text):
    page.get_by_role('button', name=text, exact=True).click()


def add_note(page, text='Check the denominator'):
    if page.locator('.annotation-layer').is_hidden():
        click_text(page, 'Review')
    page.locator('#revenue-title').click()
    page.get_by_role('textbox', name='\u65b0\u589e\u4f4d\u7f6e\u6279\u6ce8').fill(text)
    click_text(page, '\u4fdd\u5b58\u6279\u6ce8')
    page.wait_for_function('fixture.doc.manifest.annotations.length===1')
    page.locator('.annotation-body-text').wait_for()


# @wu-test type=behavior | scope=test_review_browser | protects=create reply edit resolve reopen and recreate view
def test_create_reply_edit_resolve_reopen_and_recreate_view(page):
    add_note(page)
    page.get_by_role('textbox', name='\u56de\u590d', exact=True).fill('Compared with the same source')
    click_text(page, '\u56de\u590d')
    page.wait_for_function('fixture.doc.manifest.annotations[0].replies.length===1')
    click_text(page, '\u6807\u8bb0\u5df2\u89e3\u51b3')
    page.wait_for_function("fixture.doc.manifest.annotations[0].status==='resolved'")
    click_text(page, '\u91cd\u65b0\u6253\u5f00')
    page.wait_for_function("fixture.doc.manifest.annotations[0].status==='open'")
    page.locator('.annotation-more summary').click()
    click_text(page, '\u8bf7\u6c42 Agent \u5904\u7406')
    page.wait_for_function("fixture.doc.manifest.annotations[0].agentRequest?.status==='requested'")
    assert page.evaluate('fixture.attached.length') == 0
    open_fixture(page, saved=page.evaluate('fixture.doc'))
    assert page.evaluate('fixture.doc.manifest.annotations[0].replies[0].text') == 'Compared with the same source'
    assert page.evaluate('fixture.errors') == []


# @wu-test type=behavior | scope=test_review_browser | protects=save failure keeps draft and can retry
def test_save_failure_keeps_draft_and_can_retry(page):
    click_text(page, 'Review');page.locator('#revenue-title').click()
    area=page.get_by_role('textbox', name='\u65b0\u589e\u4f4d\u7f6e\u6279\u6ce8')
    area.fill('Do not lose this draft');page.evaluate('fixture.setFail(true)')
    click_text(page, '\u4fdd\u5b58\u6279\u6ce8')
    page.get_by_role('alert').filter(has_text='Simulated save failure').wait_for()
    assert area.input_value() == 'Do not lose this draft'
    assert page.evaluate('fixture.saves') == 0
    page.evaluate('fixture.setFail(false)');click_text(page, '\u4fdd\u5b58\u6279\u6ce8')
    page.wait_for_function('fixture.saves===1')


# @wu-test type=behavior | scope=test_review_browser | protects=readonly has no mutations
def test_readonly_has_no_mutations(page):
    add_note(page,'Read only');open_fixture(page, '?readonly', saved=page.evaluate('fixture.doc'))
    click_text(page,'Review');page.locator('.annotation-list-entry').first.click()
    assert page.locator('.annotation-body-text').inner_text() == 'Read only'
    assert page.locator('.annotation-panel textarea').count() == 0
    for label in ['\u4fdd\u5b58\u6279\u6ce8','\u56de\u590d','\u6807\u8bb0\u5df2\u89e3\u51b3','\u5220\u9664\u6279\u6ce8']:
        assert page.get_by_role('button',name=label,exact=True).count()==0
    assert page.evaluate('fixture.saves') == 0


# @wu-test type=behavior | scope=test_review_browser | protects=host attach keeps existing contract
def test_host_attach_keeps_existing_contract(page):
    open_fixture(page, '?host')
    click_text(page,'Review');page.locator('#revenue-title').click()
    page.get_by_role('textbox',name='\u65b0\u589e\u4f4d\u7f6e\u6279\u6ce8').fill('Attach, do not auto send')
    click_text(page,'\u9644\u5230\u5bf9\u8bdd');page.wait_for_function('fixture.attached.length===1')
    assert page.evaluate('fixture.saves')==0
    assert page.evaluate('fixture.doc.manifest.annotations.length')==0
    assert page.locator('.annotation-panel').is_hidden()


# @wu-test type=behavior | scope=test_review_browser | protects=reset removes listeners and restores one instance
def test_reset_removes_listeners_and_restores_one_instance(page):
    add_note(page)
    page.evaluate('fixture.manager.reset();fixture.manager.refresh()')
    assert page.locator('.annotation-layer').count()==1
    assert page.locator('.annotation-layer').is_hidden()
    page.keyboard.press('c');assert page.locator('.annotation-layer').is_visible()
    page.keyboard.press('Escape');assert page.locator('.annotation-layer').is_hidden()
    page.evaluate('fixture.manager.destroy()');assert page.locator('.annotation-layer').count()==0


# @wu-test type=behavior | scope=test_review_browser | protects=plain text is not executed
def test_plain_text_is_not_executed(page):
    add_note(page,'<img src=x onerror="window.compromised=true">')
    assert page.locator('.annotation-panel img').count()==0
    assert page.evaluate('window.compromised===undefined')


# @wu-test type=behavior | scope=test_review_browser | protects=reply edit and delete
def test_reply_edit_and_delete(page):
    add_note(page)
    page.get_by_role('textbox',name='\u56de\u590d',exact=True).fill('Original reply');click_text(page,'\u56de\u590d')
    page.wait_for_function('fixture.doc.manifest.annotations[0].replies.length===1')
    click_text(page,'\u4fee\u6539')
    page.get_by_role('textbox',name='\u4fee\u6539\u56de\u590d').fill('Corrected reply')
    page.locator('.annotation-message').get_by_role('button',name='\u4fdd\u5b58\u6279\u6ce8').click()
    page.wait_for_function("fixture.doc.manifest.annotations[0].replies[0].text==='Corrected reply'")
    click_text(page,'\u5220\u9664');page.wait_for_function('fixture.doc.manifest.annotations[0].replies.length===0')
    page.locator('.annotation-more summary').click()
    click_text(page,'\u5220\u9664\u6279\u6ce8');page.wait_for_function('fixture.doc.manifest.annotations.length===0')


# @wu-test type=behavior | scope=test_review_browser | protects=panel stays in viewport and never overflows document
@pytest.mark.parametrize('width',[390,768,1100,1600])
def test_panel_stays_in_viewport_and_never_overflows_document(page,width):
    page.set_viewport_size({'width':width,'height':900});add_note(page)
    box=page.locator('.annotation-panel').bounding_box()
    assert box['x']>=0 and box['x']+box['width']<=width+1
    assert box['y']>=0 and box['y']+box['height']<=901
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    if width>=1000:
        right=page.locator('.fixture-cards').bounding_box()
        assert right['x']+right['width']<=box['x']
    evidence=os.getenv('CHARTS_TEST_EVIDENCE')
    if evidence:
        Path(evidence).mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(Path(evidence)/f'review-{width}.png'))


# @wu-test type=behavior | scope=批注阅读与编辑 | protects=打开批注直接进入修改或取消时覆盖已保存正文
def test_read_before_edit_and_cancel_preserves_saved_content(page):
    add_note(page, 'Saved context')
    assert page.locator('.annotation-body-text').inner_text() == 'Saved context'
    assert page.get_by_role('button', name='保存批注', exact=True).count() == 0
    assert page.get_by_role('button', name='回复', exact=True).is_disabled()
    click_text(page, '修改批注')
    area = page.get_by_role('textbox', name='位置批注内容')
    assert page.get_by_role('button', name='保存批注', exact=True).is_disabled()
    area.fill('Unsaved replacement')
    click_text(page, '取消')
    assert page.locator('.annotation-body-text').inner_text() == 'Saved context'
    assert page.evaluate('fixture.saves') == 1


# @wu-test type=behavior | scope=批注回复草稿 | protects=页面重建后丢失未发送回复或错误打开正文编辑器
def test_reply_draft_recovers_into_thread(page):
    add_note(page)
    page.get_by_role('textbox', name='回复', exact=True).fill('Keep this reply')
    page.evaluate('fixture.manager.reset();fixture.manager.refresh()')
    click_text(page, 'Review')
    click_text(page, '恢复未保存草稿')
    assert page.get_by_role('textbox', name='回复', exact=True).input_value() == 'Keep this reply'
    assert page.locator('.annotation-body-text').is_visible()
    assert page.evaluate('fixture.saves') == 1


# @wu-test type=behavior | scope=手机批注编辑面板 | protects=长正文滚动后保存和取消按钮离开可见区域
def test_mobile_editor_keeps_actions_visible_while_scrolling(page):
    page.set_viewport_size({'width': 390, 'height': 844})
    click_text(page, 'Review')
    page.locator('#revenue-title').click()
    page.get_by_role('textbox', name='新增位置批注').fill('Long draft\n' * 120)
    page.locator('.annotation-panel-body').evaluate('(body)=>body.scrollTop=body.scrollHeight')
    for label in ['取消', '保存批注']:
        button = page.get_by_role('button', name=label, exact=True)
        assert button.is_visible()
        box = button.bounding_box()
        assert box['y'] >= 0 and box['y'] + box['height'] <= 844
    assert page.locator('.annotation-hint').is_hidden()


# @wu-test type=behavior | scope=test_review_browser | protects=nearby annotations cluster and deleted targets remain listed
def test_nearby_annotations_cluster_and_deleted_targets_remain_listed(page):
    add_note(page)
    page.evaluate("fixture.add([{...structuredClone(fixture.doc.manifest.annotations[0]),id:'note-second',text:'Second note'}])")
    page.get_by_role('button',name='\u8fd4\u56de\u5217\u8868').click()
    page.locator('.annotation-pin[data-cluster=true]').wait_for()
    assert page.locator('.annotation-pin').count()==1
    page.evaluate("document.querySelector('[data-component-id=revenue]').remove()")
    page.wait_for_function("document.querySelectorAll('.annotation-pin').length===0")
    page.get_by_role('button',name='\u5168\u90e8',exact=True).click()
    assert page.locator('.annotation-list-entry').count()==2
    assert page.locator('.annotation-location-warning').count()==2


# @wu-test type=behavior | scope=test_review_browser | protects=data point anchor relocates after sort
@pytest.mark.parametrize('shadow',[False,True])
def test_data_point_anchor_relocates_after_sort(page,shadow):
    if shadow:
        open_fixture(page,'?shadow')
    click_text(page,'Review')
    box=page.locator('[data-component-id=trend] .chart').bounding_box()
    page.mouse.click(box['x']+80,box['y']+60)
    page.get_by_role('textbox',name='\u65b0\u589e\u4f4d\u7f6e\u6279\u6ce8').fill('February point')
    click_text(page,'\u4fdd\u5b58\u6279\u6ce8');page.wait_for_function('fixture.doc.manifest.annotations.length===1')
    assert page.evaluate('fixture.doc.manifest.annotations[0].anchor.point.key.value')=='Feb'
    old=page.locator('.annotation-pin').bounding_box()['x']
    page.evaluate("fixture.option.xAxis[0].data=['Feb','Jan'];fixture.option.series[0].data=[20,10];fixture.manager.refresh()")
    page.wait_for_function('(old)=>document.querySelector(".annotation-pin").getBoundingClientRect().x<old-40', arg=old)


# @wu-test type=behavior | scope=test_review_browser | protects=changed filter hides point instead of moving to wrong data
def test_changed_filter_hides_point_instead_of_moving_to_wrong_data(page):
    click_text(page,'Review')
    box=page.locator('[data-component-id=trend] .chart').bounding_box()
    page.mouse.click(box['x']+80,box['y']+60)
    page.get_by_role('textbox',name='\u65b0\u589e\u4f4d\u7f6e\u6279\u6ce8').fill('Point context')
    click_text(page,'\u4fdd\u5b58\u6279\u6ce8');page.wait_for_function('fixture.doc.manifest.annotations.length===1')
    page.evaluate("fixture.doc.manifest.filters=[{id:'region',field:'region',op:'in',values:['West'],componentIds:['trend']}];fixture.manager.refresh()")
    page.wait_for_function('document.querySelectorAll(".annotation-pin").length===0')
    click_text(page,'\u8fd4\u56de\u5217\u8868')
    assert page.locator('.annotation-location-warning').count()==1


# @wu-test type=behavior | scope=test_review_browser | protects=recover draft after view lifecycle reset
def test_recover_draft_after_view_lifecycle_reset(page):
    click_text(page,'Review');page.locator('#revenue-title').click()
    page.get_by_role('textbox',name='\u65b0\u589e\u4f4d\u7f6e\u6279\u6ce8').fill('Recover me')
    page.evaluate('fixture.manager.reset();fixture.manager.refresh()')
    click_text(page,'Review');click_text(page,'\u6062\u590d\u672a\u4fdd\u5b58\u8349\u7a3f')
    assert page.get_by_role('textbox',name='\u65b0\u589e\u4f4d\u7f6e\u6279\u6ce8').input_value()=='Recover me'
    assert page.evaluate('fixture.saves')==0


# @wu-test type=behavior | scope=test_review_browser | protects=shortcut does not interrupt typing and print hides review ui
def test_shortcut_does_not_interrupt_typing_and_print_hides_review_ui(page):
    add_note(page)
    area=page.get_by_role('textbox',name='\u56de\u590d',exact=True)
    area.focus();page.keyboard.type('c');assert page.locator('.annotation-layer').is_visible()
    page.emulate_media(media='print');assert page.locator('.annotation-layer').is_hidden()
    assert page.evaluate('getComputedStyle(document.querySelector(".workspace")).paddingRight')=='0px'


# @wu-test type=behavior | scope=test_review_browser | protects=concurrent root edit keeps local draft
def test_concurrent_root_edit_keeps_local_draft(page):
    add_note(page)
    click_text(page, '修改批注')
    area=page.get_by_role('textbox',name='\u4f4d\u7f6e\u6279\u6ce8\u5185\u5bb9')
    area.fill('My local change')
    page.evaluate("fixture.doc.manifest.annotations[0].text='Remote edit'")
    click_text(page,'\u4fdd\u5b58\u6279\u6ce8')
    page.get_by_role('alert').filter(has_text='This comment changed').wait_for()
    assert area.input_value()=='My local change'
    assert page.evaluate('fixture.doc.manifest.annotations[0].text')=='Remote edit'


# @wu-test type=behavior | scope=test_review_browser | protects=kpi layout geometry in browser fixture
@pytest.mark.parametrize('count',[1,4,8,12,20])
@pytest.mark.parametrize('width',[390,768,1600])
def test_kpi_layout_geometry_in_browser_fixture(page,count,width):
    """Real layout algorithm + KPI CSS; simplified markup, not GridStack QA."""
    from dashboard_runtime.layouts import compute_layout
    components={f'k{i}':{'kind':'kpi','title':f'Synthetic KPI {i+1}','presentation':{'type':'mc01'}} for i in range(count)}
    doc={'components':components}
    bp='mobile' if width<650 else 'tablet' if width<1050 else 'desktop'
    columns={'desktop':12,'tablet':8,'mobile':4}[bp]
    placements=compute_layout(doc,'executive')[bp]
    page.set_viewport_size({'width':width,'height':1000})
    page.evaluate('''({placements,columns,css})=>{
      const root=document.querySelector('.fixture-cards');root.replaceChildren();
      root.style.gridTemplateColumns=`repeat(${columns},minmax(0,1fr))`;root.style.gridAutoRows='48px';root.style.gap='0 12px';
      document.querySelector('h1').textContent=`${placements.length} KPIs / geometry fixture`;
      const base=`:host{display:block;min-width:0;height:100%;font:14px/1.5 system-ui;color:#17212b}*{box-sizing:border-box}#app-kpis{height:100%}.component-kpi{height:100%;background:white;padding:16px;border:1px solid #dbe2e8;border-radius:10px;container-type:inline-size;display:grid}.component-title{font-size:12px;margin:0;color:#52606d}.text-2xl{font-size:24px;white-space:nowrap}.component-header{min-width:0}.kpi-aux{display:flex;align-items:center}.kpi-footer{font-size:12px;color:#52606d}.spark{height:16px;width:100%;border-bottom:2px solid #56738a;transform:skewY(-2deg)}`;
      for(const [i,p] of placements.entries()){
        const host=document.createElement('section');host.dataset.fixtureKpi=p.id;host.style.cssText=`min-width:0;grid-column:${p.x+1}/span ${p.w};grid-row:${p.y+1}/span ${p.h};padding:8px 0`;
        const shadow=host.attachShadow({mode:'open'}),style=document.createElement('style');style.textContent=base+css;
        const outer=document.createElement('div');outer.id='app-kpis';outer.innerHTML='<div class="section-card component-kpi kpi-aligned"><header class="component-header"><h2 class="component-title"></h2></header><div class="kpi-headline"><strong class="text-2xl"></strong></div><div class="kpi-aux"><span class="spark"></span></div><div class="kpi-footer">YoY +12.4% &middot; MoM +3.2%</div></div>';
        outer.querySelector('h2').textContent=['Operating revenue','Passengers','Average fare','Load factor'][i%4];outer.querySelector('strong').textContent=['128.6 million','240,000','628','86.8%'][i%4];
        shadow.append(style,outer);root.append(host);
      }
    }''',{'placements':placements,'columns':columns,'css':(ROOT/'dashboard_runtime/web/kpi-layout.css').read_text()})
    assert page.locator('[data-fixture-kpi]').count()==count
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    measurements=page.evaluate('''()=>[...document.querySelectorAll('[data-fixture-kpi]')].map(host=>{
      const card=host.shadowRoot.querySelector('.component-kpi'),headline=host.shadowRoot.querySelector('.kpi-headline'),value=host.shadowRoot.querySelector('.text-2xl');
      return {width:card.getBoundingClientRect().width,cardBottom:card.getBoundingClientRect().bottom,headlineBottom:headline.getBoundingClientRect().bottom,font:parseFloat(getComputedStyle(value).fontSize),scroll:headline.scrollWidth,client:headline.clientWidth};
    })''')
    for m in measurements:
        assert m['width']>=220 and m['font']>=24
        assert m['headlineBottom']<=m['cardBottom']+1
        assert m['scroll']<=m['client']+1
    evidence=os.getenv('CHARTS_TEST_EVIDENCE')
    if evidence and count in [4,20]:
        page.screenshot(path=str(Path(evidence)/f'kpi-fixture-{count}-{width}.png'),full_page=True)
