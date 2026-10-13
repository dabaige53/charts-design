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
                        updated = await session.call_tool('dashboard_patch', {'dashboardId': 'embedded',
                            'expectedRevision': 1, 'operations': [{'op': 'set_title', 'value': 'Saved inside MCP App'}]})
                        assert not updated.isError
                        await page.evaluate('result=>window.deliverToolResult(result)',
                            updated.model_dump(by_alias=True, exclude_none=True))
                        await expect(title).to_have_value('Saved inside MCP App')
                        saved = await session.call_tool('dashboard_get', {'dashboardId': 'embedded'})
                        assert saved.structuredContent is not None
                        assert saved.structuredContent['document']['manifest']['title'] == 'Saved inside MCP App'
                        await app.locator('.toolbar').get_by_role('button', name='全屏查看', exact=True).click()
                        await expect(page.locator('body')).to_have_attribute('data-display-mode', 'fullscreen')
                        await app.get_by_role('button', name='返回对话', exact=True).click()
                        await expect(page.locator('body')).to_have_attribute('data-display-mode', 'inline')
                        # A late original result must not overwrite the saved revision.
                        await page.evaluate('result=>window.deliverToolResult(result)',
                            result.model_dump(by_alias=True, exclude_none=True))
                        await expect(title).to_have_value('Saved inside MCP App')
                        # Reopen with a fresh bridge and the canonical saved artifact.
                        await page.add_init_script('window.initialResult=' + json.dumps(
                            saved.model_dump(by_alias=True, exclude_none=True)))
                        await page.reload()
                        await expect(page.frame_locator('#app').get_by_label('Dashboard title')).to_have_value(
                            'Saved inside MCP App')
                        assert not errors, errors
                    finally:
                        await browser.close()
    asyncio.run(check())
