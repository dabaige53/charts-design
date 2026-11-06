"""A running MCP connection must advertise rebuilt UI assets to the host."""
import asyncio
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip('mcp')
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextResourceContents
from pydantic import AnyUrl


# @wu-test type=integration | scope=MCP UI更新 | protects=构建后宿主用旧资源或旧工具不可调用 | debt=D1
def test_running_worker_announces_new_ui_resource(tmp_path):
    assets = tmp_path / 'assets'
    assets.mkdir()
    javascript = assets / 'app.js'
    javascript.write_text('first build')
    (assets / 'app.css').write_text('body{}')
    source = (
        'import asyncio; from pathlib import Path; import dashboard_runtime.assets as assets; '
        'import dashboard_runtime.mcp_server as server; '
        'from dashboard_runtime.service import Service; '
        'from dashboard_runtime.store import Store; '
        f'assets.DIST=Path({str(assets)!r}); '
        f'Store(Path({str(tmp_path / "store")!r})).create("preview", "Preview"); '
        f'asyncio.run(server.run(Service(Path({str(tmp_path / "store")!r}))))'
    )

    async def check():
        notifications = []

        async def receive(message):
            notifications.append(getattr(getattr(message, 'root', None), 'method', None))

        root = str(Path(__file__).resolve().parents[2])
        params = StdioServerParameters(
            command=sys.executable, args=['-c', source],
            env={**os.environ, 'PYTHONPATH': root + os.pathsep + os.environ.get('PYTHONPATH', '')},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, message_handler=receive) as session:
                await session.initialize()
                before = await session.list_tools()
                before_meta = next(tool for tool in before.tools if tool.name == 'dashboard_preview').meta
                assert before_meta is not None
                previous = before_meta['ui']['resourceUri']
                previous_alias = next(tool for tool in before.tools if tool.name.startswith('dashboard_preview_'))
                assert previous_alias.meta == before_meta
                assert previous_alias.annotations is not None
                assert previous_alias.annotations.readOnlyHint is True
                preview = await session.call_tool(previous_alias.name, {'dashboardId': 'preview'})
                assert not preview.isError
                assert preview.structuredContent is not None
                assert preview.structuredContent['document']['id'] == 'preview'
                javascript.write_text('second build with zoom')
                result = await session.call_tool('dashboard_list', {})
                assert not result.isError
                after = await session.list_tools()
                after_meta = next(tool for tool in after.tools if tool.name == 'dashboard_preview').meta
                assert after_meta is not None
                current = after_meta['ui']['resourceUri']
                assert current != previous
                current_alias = next(tool for tool in after.tools if tool.name.startswith('dashboard_preview_'))
                assert current_alias.name != previous_alias.name
                assert current_alias.meta == after_meta
                assert previous_alias.name not in [tool.name for tool in after.tools]
                # Existing conversations can still call their earlier tool identity.
                preview = await session.call_tool(previous_alias.name, {'dashboardId': 'preview'})
                assert not preview.isError
                assert preview.structuredContent is not None
                assert preview.structuredContent['document']['id'] == 'preview'
                assert 'notifications/tools/list_changed' in notifications
                assert 'notifications/resources/list_changed' in notifications
                resources = await session.list_resources()
                assert any(str(resource.uri) == current for resource in resources.resources)
                # The previous build was never advertised by this worker (e.g. after restart).
                historical = 'ui://charts-design/dashboard-v0.6.0-ba89657db749.html'
                resource = await session.read_resource(AnyUrl(historical))
                assert isinstance(resource.contents[0], TextResourceContents)
                assert 'second build with zoom' in resource.contents[0].text
                resource = await session.read_resource(AnyUrl(previous))
                assert isinstance(resource.contents[0], TextResourceContents)
                assert 'second build with zoom' in resource.contents[0].text
                resource = await session.read_resource(AnyUrl(current))
                assert isinstance(resource.contents[0], TextResourceContents)
                assert 'second build with zoom' in resource.contents[0].text

    asyncio.run(check())
