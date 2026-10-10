import asyncio
import os
import sys
from pathlib import Path
import pytest

mcp=pytest.importorskip('mcp',reason='Install the optional official MCP SDK for protocol integration tests')
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

def test_real_stdio_protocol(tmp_path):
    async def check():
        params=StdioServerParameters(command=sys.executable,args=['-m','dashboard_runtime','--root',str(tmp_path/'mcp'),'mcp'],env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[2])})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                tools=await session.list_tools()
                assert 'dashboard_preview' in [t.name for t in tools.tools]
                result=await session.call_tool('dashboard_create',{'dashboardId':'mcp-test','title':'MCP'})
                assert not result.isError
                result=await session.call_tool('dashboard_patch',{'dashboardId':'mcp-test','expectedRevision':1,'operations':[{'op':'set_title','value':'Edited over MCP'}]})
                assert not result.isError
                assert result.structuredContent['document']['revision']==2
                bad=await session.call_tool('dashboard_patch',{'dashboardId':'mcp-test','expectedRevision':1,'operations':[{'op':'set_title','value':'Stale'}]})
                assert bad.isError
                resources=await session.list_resources()
                assert any(str(r.uri).startswith('ui://') for r in resources.resources)
                contract=await session.read_resource('charts://contract')
                assert 'set_layout' in contract.contents[0].text
    asyncio.run(check())
