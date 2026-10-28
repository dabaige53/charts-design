"""The published MCP command uses the configured project interpreter and data."""
import asyncio
import json
import os
from pathlib import Path

import pytest

pytest.importorskip('mcp')
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_project_mcp_command_and_reconnect(tmp_path):
    root = Path(__file__).resolve().parents[2]
    config = json.loads(root.joinpath('mcp.json').read_text())['mcpServers']['charts-design']
    args = [value.replace('${PLUGIN_ROOT}', str(root)) for value in config['args']]
    args[args.index('--root') + 1] = str(tmp_path/'runtime')
    args[1:1] = ['--project-root', str(tmp_path/'project')]

    async def check():
        params = StdioServerParameters(command=config['command'], args=args, env=dict(os.environ))
        for first in (True, False):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    names = {tool.name for tool in (await session.list_tools()).tools}
                    assert {'dashboard_create', 'dashboard_patch', 'dashboard_preview', 'runtime_keepalive'} <= names
                    if first:
                        created = await session.call_tool('dashboard_create', {'dashboardId': 'configured'})
                        assert not created.isError
                        edited = await session.call_tool('dashboard_patch', {'dashboardId': 'configured',
                            'expectedRevision': 1, 'operations': [{'op': 'set_title', 'value': 'Saved through configured MCP'}]})
                        assert not edited.isError
                    result = await session.call_tool('dashboard_get', {'dashboardId': 'configured'})
                    assert not result.isError and result.structuredContent is not None
                    assert result.structuredContent['document']['revision'] == 2
                    assert result.structuredContent['document']['manifest']['title'] == 'Saved through configured MCP'
    asyncio.run(check())


def test_same_host_session_survives_worker_idle_shutdown(tmp_path):
    root = Path(__file__).resolve().parents[2]
    worker_log = tmp_path / 'worker.log'

    async def check():
        params = StdioServerParameters(command='node', args=[str(root / 'bin/dashboard-runtime.js'),
            '--project-root', str(tmp_path/'project'), '--runtime-root', str(tmp_path/'runtime'), 'mcp', '--idle-timeout', '0.2'], env=dict(os.environ))
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                created = await session.call_tool('dashboard_create', {'dashboardId': 'idle-reopen'})
                assert not created.isError
                for revision in (1, 2):
                    await asyncio.sleep(1)
                    assert worker_log.read_text().count('MCP closed after idle timeout') >= revision
                    result = await session.call_tool('dashboard_get', {'dashboardId': 'idle-reopen'})
                    assert not result.isError and result.structuredContent is not None
                    assert result.structuredContent['document']['revision'] == revision
                    if revision == 1:
                        edited = await session.call_tool('dashboard_patch', {'dashboardId': 'idle-reopen',
                            'expectedRevision': 1, 'operations': [{'op': 'set_title', 'value': 'After idle'}]})
                        assert not edited.isError
    with worker_log.open('w') as errlog:
        asyncio.run(check())
