import asyncio
import os
import sys
from pathlib import Path
import pytest

pytest.importorskip('mcp',reason='Install the optional official MCP SDK for protocol integration tests')
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent, TextResourceContents
from pydantic import AnyUrl

def test_real_stdio_protocol(tmp_path):
    async def check():
        params=StdioServerParameters(command=sys.executable,args=['-m','dashboard_runtime','--root',str(tmp_path/'mcp'),'mcp'],env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[2])+os.pathsep+os.environ.get('PYTHONPATH','')})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                tools=await session.list_tools()
                assert 'dashboard_preview' in [t.name for t in tools.tools]
                from dashboard_runtime.mcp_server import UI_TOOLS, URI, MIME
                by_name = {tool.name: tool for tool in tools.tools}
                for name in UI_TOOLS:
                    assert by_name[name].meta == {'ui': {'resourceUri': URI}, 'ui/resourceUri': URI}
                assert by_name['runtime_keepalive'].meta == {'ui': {'visibility': ['app']}}
                assert by_name['generation_examples'].meta is None
                ui = await session.read_resource(AnyUrl(URI))
                assert isinstance(ui.contents[0], TextResourceContents)
                assert ui.contents[0].mimeType == MIME
                assert ui.contents[0].meta == {'ui': {'prefersBorder': True}}
                assert '"mode": "mcp"' in ui.contents[0].text
                result=await session.call_tool('dashboard_create',{'dashboardId':'mcp-test','title':'MCP'})
                assert not result.isError
                result=await session.call_tool('dashboard_patch',{'dashboardId':'mcp-test','expectedRevision':1,'operations':[{'op':'set_title','value':'Edited over MCP'}]})
                assert not result.isError
                assert result.structuredContent is not None
                assert result.structuredContent['document']['revision']==2
                import json
                assert isinstance(result.content[0], TextContent)
                summary = json.loads(result.content[0].text)
                assert summary['dashboardId'] == 'mcp-test'
                assert summary['artifactLocation'] == 'structuredContent.document'
                assert 'document' not in summary
                assert summary['datasetRows'] == {}
                bad=await session.call_tool('dashboard_patch',{'dashboardId':'mcp-test','expectedRevision':1,'operations':[{'op':'set_title','value':'Stale'}]})
                assert bad.isError
                report=await session.call_tool('dashboard_patch',{'dashboardId':'mcp-test','expectedRevision':2,'operations':[
                    {'op':'put_component','id':'note','value':{'kind':'text','title':'Analysis','text':'Authored finding'}},
                    {'op':'set_view_mode','value':'report'},
                    {'op':'set_report','value':{'subtitle':'Personal report','blocks':[{'id':'opening','componentId':'note'}]}}
                ]})
                assert not report.isError
                assert report.structuredContent is not None
                assert report.structuredContent['document']['manifest']['viewMode']=='report'
                assert report.structuredContent['document']['manifest']['report']['blocks']==[{'id':'opening','componentId':'note'}]
                source='# Written over MCP\n\n**A finding** with a list:\n\n- Verify the source.\n'
                markdown=await session.call_tool('dashboard_patch',{'dashboardId':'mcp-test','expectedRevision':3,'operations':[
                    {'op':'set_report_markdown','value':source}
                ]})
                assert not markdown.isError
                assert markdown.structuredContent is not None
                assert markdown.structuredContent['document']['manifest']['report']['markdown']==source
                invalid=await session.call_tool('dashboard_patch',{'dashboardId':'mcp-test','expectedRevision':4,'operations':[
                    {'op':'set_report_markdown','value':'```chart\n{"componentId":"missing"}\n```'}
                ]})
                assert invalid.isError
                unchanged=await session.call_tool('dashboard_get',{'dashboardId':'mcp-test'})
                assert unchanged.structuredContent is not None
                assert unchanged.structuredContent['document']['revision']==4
                assert unchanged.structuredContent['document']['manifest']['report']['markdown']==source
                # Pipe reads must support report requests beyond asyncio's default 64 KiB limit.
                large_source = '# Large report\n\n' + ('Descriptive findings.\n' * 5000)
                large = await session.call_tool('dashboard_patch', {'dashboardId':'mcp-test',
                    'expectedRevision':4,'operations':[{'op':'set_report_markdown','value':large_source}]})
                assert not large.isError
                assert large.structuredContent is not None
                assert large.structuredContent['document']['manifest']['report']['markdown'] == large_source
                assert isinstance(large.content[0], TextContent)
                assert len(large.content[0].text) < 1000
                # A representative 960-row transport fixture exceeds the reported response size.
                rows = [{'detail': str(i) + 'x' * 1000} for i in range(960)]
                payload = await session.call_tool('dashboard_patch', {'dashboardId': 'mcp-test',
                    'dataMode': 'snapshot',
                    'expectedRevision': 5, 'operations': [
                        {'op': 'put_source', 'id': 'transport-fixture', 'value': {'kind': 'fixture'}},
                        {'op': 'put_dataset', 'id': 'details', 'meta': {
                            'sourceId': 'transport-fixture', 'fields': {'detail': {'type': 'string'}}}, 'rows': rows},
                    ]})
                assert not payload.isError
                assert payload.structuredContent is not None
                assert payload.structuredContent['document']['snapshot']['datasets']['details'] == rows
                assert isinstance(payload.content[0], TextContent)
                assert json.loads(payload.content[0].text)['documentBytes'] > 900000
                assert len(payload.content[0].text) < 1000
                resources=await session.list_resources()
                assert any(str(r.uri).startswith('ui://') for r in resources.resources)
                contract=await session.read_resource(AnyUrl('charts://contract'))
                assert isinstance(contract.contents[0], TextResourceContents)
                assert 'set_layout' in contract.contents[0].text
                assert 'set_report_markdown' in contract.contents[0].text and 'set_report' in contract.contents[0].text and 'set_view_mode' in contract.contents[0].text
    asyncio.run(check())
