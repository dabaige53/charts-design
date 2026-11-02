"""Two MCP Apps share one connection but never share their project context."""
import asyncio
import json
import os
import subprocess
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextResourceContents
from playwright.async_api import async_playwright, expect
from pydantic import AnyUrl

from dashboard_runtime.demo import executive_document
from dashboard_runtime.mcp_server import URI


def test_two_project_previews_share_one_connection(tmp_path):
    root = Path(__file__).resolve().parents[2]
    bundle = tmp_path / 'host.js'
    subprocess.run([str(root / 'runtime-ui/node_modules/esbuild/bin/esbuild'),
        str(root / 'tests/runtime/mcp-app-host.mjs'), '--bundle', '--format=esm',
        f'--outfile={bundle}'], check=True, capture_output=True)

    async def check():
        params = StdioServerParameters(command='node', args=[str(root / 'bin/dashboard-runtime.js'),
            '--runtime-root', str(tmp_path / 'runtime'), 'mcp'], env=dict(os.environ))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                projects = [str(tmp_path / 'first'), str(tmp_path / 'second')]
                initial = []
                for project, title in zip(projects, ('First project', 'Second project')):
                    doc = executive_document('same')
                    doc['manifest']['title'] = title
                    created = await session.call_tool('dashboard_create', {
                        'projectRoot': project, 'dashboardId': 'same', 'document': doc})
                    assert not created.isError
                    result = await session.call_tool('dashboard_preview', {'projectRoot': project, 'dashboardId': 'same'})
                    assert not result.isError
                    initial.append(result.model_dump(by_alias=True, exclude_none=True))
                resource = (await session.read_resource(AnyUrl(URI))).contents[0]
                assert isinstance(resource, TextResourceContents)
                calls = {project: [] for project in projects}
                errors = []

                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(headless=True)
                    try:
                        pages, apps = [], []
                        for project, result in zip(projects, initial):
                            page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
                            page.on('pageerror', lambda error: errors.append(str(error)))

                            async def call_tool(_source, arguments, owner=project):
                                calls[owner].append(arguments)
                                response = await session.call_tool(arguments['name'], arguments.get('arguments', {}))
                                return response.model_dump(by_alias=True, exclude_none=True)

                            await page.expose_binding('mcpCallTool', call_tool)
                            await page.add_init_script('window.initialResult=' + json.dumps(result))
                            await page.route('http://127.0.0.1:54321/**', lambda route: route.fulfill(
                                content_type='text/javascript' if route.request.url.endswith('/host.js') else 'text/html',
                                body=resource.text if route.request.url.endswith('/app') else
                                bundle.read_text() if route.request.url.endswith('/host.js') else
                                '<!doctype html><script type="module" src="/host.js"></script>'))
                            await page.goto('http://127.0.0.1:54321/')
                            app = page.frame_locator('#app')
                            await app.locator('[data-component-id="trend"] canvas').wait_for()
                            pages.append(page)
                            apps.append(app)

                        await apps[0].get_by_role('button', name='编辑', exact=True).click()
                        await apps[0].get_by_label('Dashboard title').fill('Updated first project')
                        await apps[0].get_by_label('Dashboard title').press('Tab')
                        await expect(apps[0].locator('#notice')).to_contain_text('v2')
                        await apps[1].get_by_role('button', name='刷新报表', exact=True).click()
                        await expect(apps[1].get_by_label('Dashboard title')).to_have_value('Second project')

                        await pages[0].evaluate('result=>window.deliverToolResult(result)', initial[1])
                        await expect(apps[0].locator('#notice')).to_contain_text('其他项目')
                        await expect(apps[0].get_by_label('Dashboard title')).to_have_value('Updated first project')
                        for project in projects:
                            assert calls[project]
                            assert all(item['arguments'].get('projectRoot') == project for item in calls[project])
                            assert 'dashboard_view' in [item['name'] for item in calls[project]]
                        for project, title in zip(projects, ('Updated first project', 'Second project')):
                            current = await session.call_tool('dashboard_get', {'projectRoot': project, 'dashboardId': 'same'})
                            assert current.structuredContent is not None
                            assert current.structuredContent['document']['manifest']['title'] == title
                        assert not errors
                    finally:
                        await browser.close()

    asyncio.run(check())
