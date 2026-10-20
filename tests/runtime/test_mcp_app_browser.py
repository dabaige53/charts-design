"""Real stdio server → official AppBridge → embedded UI → persisted MCP edit.

This acceptance host does not claim to be the Codex desktop host.
"""
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

from dashboard_runtime.demo import executive_document as document
from dashboard_runtime.mcp_server import URI


def test_embedded_app_edits_persists_and_reopens(tmp_path):
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
                result = await session.call_tool('dashboard_create', {'dashboardId': 'embedded',
                    'document': document()})
                assert not result.isError
                resource = await session.read_resource(AnyUrl(URI))
                content = resource.contents[0]
                assert isinstance(content, TextResourceContents)
                calls = []

                async def call_tool(_source, arguments):
                    calls.append(arguments['name'])
                    if arguments['name'] == 'dashboard_export_open':
                        assert arguments['arguments']['action'] in ('open', 'reveal')
                        return {'structuredContent': {'ok': True}, 'content': []}
                    response = await session.call_tool(arguments['name'], arguments.get('arguments', {}))
                    return response.model_dump(by_alias=True, exclude_none=True)

                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(headless=True)
                    try:
                        page = await browser.new_page(viewport={'width': 1440, 'height': 1100})
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        await page.expose_binding('mcpCallTool', call_tool)
                        await page.add_init_script('window.initialResult=' + json.dumps(
                            result.model_dump(by_alias=True, exclude_none=True)))
                        await page.route('http://127.0.0.1:54321/**', lambda route: route.fulfill(
                            content_type='text/html' if route.request.url.endswith('/app') else
                            'text/javascript' if route.request.url.endswith('/host.js') else 'text/html',
                            body=content.text if route.request.url.endswith('/app') else
                            bundle.read_text() if route.request.url.endswith('/host.js') else
                            '<!doctype html><script type="module" src="/host.js"></script>'))
                        await page.goto('http://127.0.0.1:54321/')
                        app = page.frame_locator('#app')
                        await app.locator('[data-component-id="trend"] canvas').wait_for()
                        await expect(app.get_by_role('button', name='编辑', exact=True)).to_be_visible()
                        title = app.get_by_label('Dashboard title')
                        await expect(title).to_be_disabled()
                        # Exercise real exports through stdio, not only button presence.
                        await app.get_by_role('button', name='导出', exact=True).click()
                        for format in ('JSON', 'HTML', 'PDF'):
                            async with page.expect_download() as transfer:
                                await app.get_by_role('button', name='导出 ' + format, exact=True).click()
                            file = await transfer.value
                            target = tmp_path / file.suggested_filename
                            await file.save_as(target)
                            assert target.suffix == '.' + format.lower()
                            assert target.stat().st_size > 100
                            if format == 'JSON':
                                exported = json.loads(target.read_text())
                                assert exported['id'] == 'embedded'
                                assert exported['snapshot']['datasetRefs']
                                assert not any(exported['snapshot']['datasets'].values())
                            if format == 'HTML':
                                exported_page = await browser.new_page()
                                await exported_page.goto(target.as_uri())
                                await expect(exported_page.get_by_label('Dashboard title')).to_have_value(document()['manifest']['title'])
                                await exported_page.locator('[data-component-id="trend"] canvas').wait_for()
                                await exported_page.close()
                            if format == 'PDF':
                                assert target.read_bytes().startswith(b'%PDF-')
                        evidence = root / 'dist/local-data-acceptance/export'
                        evidence.mkdir(parents=True, exist_ok=True)
                        # Host refusal must preserve a usable local-file result.
                        await page.evaluate('window.rejectDownloads=true')
                        await app.get_by_role('button', name='导出 JSON', exact=True).click()
                        await expect(app.locator('.export-feedback')).to_have_text('JSON 已保存到本机')
                        await expect(app.locator('.export-path')).to_contain_text('.json')
                        await app.get_by_role('button', name='打开文件', exact=True).click()
                        await expect(app.locator('.export-feedback')).to_have_text('已请求打开文件')
                        await app.get_by_role('button', name='在文件夹中显示', exact=True).click()
                        await expect(app.locator('.export-feedback')).to_have_text('已在文件夹中显示')
                        assert calls.count('dashboard_export_open') == 2
                        await page.screenshot(path=str(evidence / 'export-dialog.png'))
                        await app.get_by_role('button', name='关闭', exact=True).click()
                        updated = await session.call_tool('dashboard_patch', {'dashboardId': 'embedded',
                            'expectedRevision': 1, 'operations': [{'op': 'set_title', 'value': 'Saved inside MCP App'}]})
                        assert not updated.isError
                        await page.evaluate('result=>window.deliverToolResult(result)',
                            updated.model_dump(by_alias=True, exclude_none=True))
                        await expect(title).to_have_value('Saved inside MCP App')
                        # Reader refresh observes canonical updates even without host tool-result delivery.
                        refreshed = await session.call_tool('dashboard_patch', {'dashboardId': 'embedded',
                            'expectedRevision': 2, 'operations': [{'op': 'set_title', 'value': 'Refreshed MCP App'}]})
                        assert not refreshed.isError
                        await app.get_by_role('button', name='刷新报表', exact=True).click()
                        await expect(title).to_have_value('Refreshed MCP App')
                        await expect(app.get_by_role('button', name='刷新报表', exact=True)).to_be_enabled()
                        assert 'runtime_info' in calls and 'dashboard_refresh' in calls
                        # A subsequent update is picked up by the visible read-mode poll.
                        automatic = await session.call_tool('dashboard_patch', {'dashboardId': 'embedded',
                            'expectedRevision': 3, 'operations': [{'op': 'set_title', 'value': 'Auto refreshed MCP App'}]})
                        assert not automatic.isError
                        await expect(title).to_have_value('Auto refreshed MCP App', timeout=10000)
                        saved = await session.call_tool('dashboard_get', {'dashboardId': 'embedded'})
                        assert saved.structuredContent is not None
                        assert saved.structuredContent['document']['manifest']['title'] == 'Auto refreshed MCP App'
                        await app.locator('.toolbar').get_by_role('button', name='全屏查看', exact=True).click()
                        await expect(page.locator('body')).to_have_attribute('data-display-mode', 'fullscreen')
                        await app.get_by_role('button', name='返回对话', exact=True).click()
                        await expect(page.locator('body')).to_have_attribute('data-display-mode', 'inline')
                        # A late original result must not overwrite the saved revision.
                        await page.evaluate('result=>window.deliverToolResult(result)',
                            result.model_dump(by_alias=True, exclude_none=True))
                        await expect(title).to_have_value('Auto refreshed MCP App')
                        # Decode errors must be visible in reading mode, with input length.
                        await page.evaluate('result=>window.deliverToolResult(result)',
                            {'content': [{'type': 'text', 'text': '{} {}'}]})
                        await expect(app.locator('#notice')).to_be_visible()
                        await expect(app.locator('#notice')).to_contain_text('文本 5 字符')
                        # Reopen with a fresh bridge and the canonical saved artifact.
                        await page.add_init_script('window.initialResult=' + json.dumps(
                            saved.model_dump(by_alias=True, exclude_none=True)))
                        await page.reload()
                        await expect(page.frame_locator('#app').get_by_label('Dashboard title')).to_have_value(
                            'Auto refreshed MCP App')
                        # A computed offline component is a page snapshot, never a full export.
                        from dashboard_runtime.assets import export_document
                        saved_document = saved.structuredContent['document']
                        offline_html = export_document(saved_document)
                        offline = await browser.new_page()
                        await offline.route('http://127.0.0.1:54322/**', lambda route: route.fulfill(
                            content_type='text/html', body=offline_html))
                        await offline.goto('http://127.0.0.1:54322/')
                        await expect(offline.get_by_text('当前页快照；完整明细请在本机看板中导出', exact=True)).to_be_visible()
                        await expect(offline.get_by_placeholder('搜索明细')).to_be_disabled()
                        await offline.close()
                        assert not errors, errors
                    finally:
                        await browser.close()
    asyncio.run(check())
