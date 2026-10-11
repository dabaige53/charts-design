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
                report=await session.call_tool('dashboard_patch',{'dashboardId':'mcp-test','expectedRevision':2,'operations':[
                    {'op':'put_component','id':'note','value':{'kind':'text','title':'Analysis','text':'Authored finding'}},
                    {'op':'set_view_mode','value':'report'},
                    {'op':'set_report','value':{'subtitle':'Personal report','blocks':[{'id':'opening','componentId':'note'}]}}
                ]})
                assert not report.isError
                assert report.structuredContent['document']['manifest']['viewMode']=='report'
                assert report.structuredContent['document']['manifest']['report']['blocks']==[{'id':'opening','componentId':'note'}]
                source='# Written over MCP\n\n**A finding** with a list:\n\n- Verify the source.\n'
                markdown=await session.call_tool('dashboard_patch',{'dashboardId':'mcp-test','expectedRevision':3,'operations':[
                    {'op':'set_report_markdown','value':source}
                ]})
                assert not markdown.isError
                assert markdown.structuredContent['document']['manifest']['report']['markdown']==source
                invalid=await session.call_tool('dashboard_patch',{'dashboardId':'mcp-test','expectedRevision':4,'operations':[
                    {'op':'set_report_markdown','value':'```chart\n{"componentId":"missing"}\n```'}
                ]})
                assert invalid.isError
                unchanged=await session.call_tool('dashboard_get',{'dashboardId':'mcp-test'})
                assert unchanged.structuredContent['document']['revision']==4
                assert unchanged.structuredContent['document']['manifest']['report']['markdown']==source
                resources=await session.list_resources()
                assert any(str(r.uri).startswith('ui://') for r in resources.resources)
                contract=await session.read_resource('charts://contract')
                assert 'set_layout' in contract.contents[0].text
                assert 'set_report_markdown' in contract.contents[0].text and 'set_report' in contract.contents[0].text and 'set_view_mode' in contract.contents[0].text
    asyncio.run(check())
