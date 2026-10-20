"""Switch saved pages through the real MCP transport and official AppBridge."""
import asyncio
import json
import os
from pathlib import Path
import subprocess

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextResourceContents
from playwright.async_api import async_playwright, expect
from pydantic import AnyUrl

from dashboard_runtime.demo import executive_document
from dashboard_runtime.mcp_server import URI


def test_mcp_page_switch(tmp_path):
    root = Path(__file__).resolve().parents[2]
    bundle = tmp_path / 'host.js'
    subprocess.run([str(root / 'runtime-ui/node_modules/esbuild/bin/esbuild'),
                    str(root / 'tests/runtime/mcp-app-host.mjs'), '--bundle', '--format=esm',
                    f'--outfile={bundle}'], check=True, capture_output=True)

    async def check():
        params = StdioServerParameters(command='node', args=[str(root / 'bin/dashboard-runtime.js'),
            '--root', str(tmp_path / 'state'), 'mcp'], env=dict(os.environ))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                first = executive_document()
                first['manifest']['title'] = '经营总览'
                result = await session.call_tool('dashboard_create', {'dashboardId': 'overview', 'document': first})
                assert not result.isError
                resource = (await session.read_resource(AnyUrl(URI))).contents[0]
                assert isinstance(resource, TextResourceContents)
                calls = []

                async def call_tool(_source, arguments):
                    calls.append(arguments)
                    response = await session.call_tool(arguments['name'], arguments.get('arguments', {}))
                    return response.model_dump(by_alias=True, exclude_none=True)

                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(headless=True)
                    try:
                        page = await browser.new_page(viewport={'width': 1000, 'height': 900})
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        await page.expose_binding('mcpCallTool', call_tool)
                        await page.add_init_script('window.initialResult=' + json.dumps(
                            result.model_dump(by_alias=True, exclude_none=True)))
                        await page.route('http://127.0.0.1:54321/**', lambda route: route.fulfill(
                            content_type='text/javascript' if route.request.url.endswith('/host.js') else 'text/html',
                            body=resource.text if route.request.url.endswith('/app') else
                            bundle.read_text() if route.request.url.endswith('/host.js') else
                            '<!doctype html><script type="module" src="/host.js"></script>'))
                        await page.goto('http://127.0.0.1:54321/')
                        app = page.frame_locator('#app')
                        switch = app.get_by_role('button', name='切换页面', exact=True)
                        await app.locator('[data-component-id="trend"] canvas').wait_for()
                        await expect(switch).to_be_hidden()
                        # A new page created outside the frame becomes discoverable without reopening.
                        report = executive_document()
                        report['manifest'].update(title='销售报告', viewMode='report',
                                                  report={'markdown': '# 销售报告\n\n第二页独有内容'})
                        created = await session.call_tool('dashboard_create', {'dashboardId': 'report', 'document': report})
                        assert not created.isError
                        await expect(switch).to_be_visible(timeout=12000)
                        await expect(switch).to_contain_text('经营总览')
                        await switch.click()
                        await expect(app.get_by_role('menuitemradio', name='经营总览')).to_have_attribute('aria-checked', 'true')
                        await app.get_by_role('menuitemradio', name='销售报告').click()
                        await expect(app.get_by_text('第二页独有内容', exact=True)).to_be_visible()
                        # The report reading layout must also expose the switcher.
                        await expect(switch).to_be_visible()
                        await expect(switch).to_contain_text('销售报告')
                        await app.get_by_role('button', name='编辑', exact=True).click()
                        await expect(app.get_by_label('Dashboard title')).to_be_enabled()
                        draft = '# 销售报告\n\n第二页独有内容\n\n未保存的草稿'
                        await app.get_by_label('Markdown 源文档').fill(draft)
                        await switch.click()
                        await app.get_by_role('menuitemradio', name='经营总览').click()
                        await app.locator('[data-component-id="trend"] canvas').wait_for()
                        await expect(app.get_by_label('Dashboard title')).to_be_disabled()
                        await expect(switch).to_contain_text('经营总览')
                        await expect(app.get_by_text('第二页独有内容', exact=True)).to_have_count(0)
                        # Narrow host: title and arrow remain inside the viewport; keyboard selection works.
                        await page.locator('#app').evaluate("node=>node.style.width='360px'")
                        await switch.click()
                        await app.get_by_role('menuitemradio', name='经营总览').press('ArrowDown')
                        await app.get_by_role('menuitemradio', name='销售报告').press('Enter')
                        await expect(switch).to_contain_text('销售报告')
                        await app.get_by_role('button', name='编辑', exact=True).click()
                        await expect(app.get_by_label('Markdown 源文档')).to_have_value(draft)
                        # Preserve the draft while returning to the reading layout for the screenshot.
                        await switch.click()
                        await app.get_by_role('menuitemradio', name='经营总览').click()
                        await switch.click()
                        await app.get_by_role('menuitemradio', name='销售报告').click()
                        bounds = await switch.bounding_box()
                        assert bounds and bounds['width'] > 20 and bounds['x'] + bounds['width'] < 380
                        actions = await app.locator('.toolbar').bounding_box()
                        assert actions and bounds['x'] + bounds['width'] <= actions['x']
                        evidence = root / 'dist/local-data-acceptance/page-switch'
                        evidence.mkdir(parents=True, exist_ok=True)
                        await switch.click()
                        await expect(app.get_by_role('menuitemradio', name='销售报告')).to_be_visible()
                        await page.screenshot(path=str(evidence / 'page-switch-mobile.png'))
                        assert any(call['name'] == 'dashboard_get' and call['arguments']['dashboardId'] == 'report' for call in calls)
                        assert not errors, errors
                    finally:
                        await browser.close()
    asyncio.run(check())
