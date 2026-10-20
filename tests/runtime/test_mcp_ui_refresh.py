"""A running MCP connection must advertise rebuilt UI assets to the host."""
import asyncio
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip('mcp')
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


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
        f'assets.DIST=Path({str(assets)!r}); '
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
                javascript.write_text('second build with zoom')
                result = await session.call_tool('dashboard_list', {})
                assert not result.isError
                after = await session.list_tools()
                after_meta = next(tool for tool in after.tools if tool.name == 'dashboard_preview').meta
                assert after_meta is not None
                current = after_meta['ui']['resourceUri']
                assert current != previous
                assert 'notifications/tools/list_changed' in notifications
                assert 'notifications/resources/list_changed' in notifications
                resources = await session.list_resources()
                assert any(str(resource.uri) == current for resource in resources.resources)

    asyncio.run(check())
