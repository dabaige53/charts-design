"""The statistical backend is reachable through the existing official MCP server."""
import asyncio
import json
import os
from pathlib import Path
import sys
import pytest
pytest.importorskip('mcp')
pytest.importorskip('seaborn')
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_statistical_stdio_authoring(tmp_path):
    async def check():
        params=StdioServerParameters(command=sys.executable,args=['-m','dashboard_runtime','--root',str(tmp_path),'mcp'],env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[2])+os.pathsep+os.environ.get('PYTHONPATH','')})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                async def call(name,args):
                    result=await session.call_tool(name,args)
                    assert not result.isError,result
                    return result.structuredContent
                assert 'regression' in (await call('chart_declarations',{}))['statistical']['types']
                await call('dashboard_create',{'dashboardId':'statistics'})
                result=await call('dashboard_patch',{'dashboardId':'statistics','expectedRevision':1,'operations':[
                    {'op':'put_source','id':'sample','value':{'kind':'fixture','name':'Explicit synthetic observations'}},
                    {'op':'put_dataset','id':'sample','meta':{'sourceId':'sample','fields':{'x':{'type':'number'},'y':{'type':'number'}}},'rows':[{'x':i,'y':i*2} for i in range(5)]},
                    {'op':'put_component','id':'regression','value':{'kind':'statistical','title':'Synthetic regression','datasetId':'sample','plot':{'type':'regression','x':'x','y':'y'},'analysis':{'definition':'One synthetic observation per row','unit':'units'}}},
                    {'op':'set_view_mode','value':'report'},
                    {'op':'set_report_markdown','value':'# Synthetic report\n\n```chart\n{"componentId":"regression"}\n```'},
                ]})
                assert result['statisticalArtifacts']['regression']['provenance']['rowsUsed']==5
                assert (await call('dashboard_validate',{'dashboardId':'statistics'}))['valid']
                assert 'regression' in (await call('dashboard_preview',{'dashboardId':'statistics'}))['statisticalArtifacts']
                assert (await call('statistical_render',{'dashboardId':'statistics','componentId':'regression','format':'png'}))['mimeType']=='image/png'
    asyncio.run(check())
