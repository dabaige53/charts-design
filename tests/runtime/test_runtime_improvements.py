import copy
import json
from dashboard_runtime.service import Service
from dashboard_runtime.semantic_diff import semantic_diff
from dashboard_runtime.wire import compact_records


def test_backend_identity_invalidates_doctor(tmp_path):
    service=Service(tmp_path/'runtime',project_root=tmp_path/'project')
    service.call('dashboard_create',{'dashboardId':'board'})
    info=service.call('runtime_info',{})
    assert len(info['backendBuildId'])==16
    assert info['moduleRoot'].endswith('dashboard_runtime')
    import os
    assert info['processId']==os.getpid()
    assert info['parentProcessId']==os.getppid()
    assert info['projectRoot']==str((tmp_path/'project').resolve())
    old=service.call('dashboard_doctor',{'dashboardId':'board'})
    old['backendBuildId']='previous'
    new=service.call('dashboard_preview',{'dashboardId':'board'})['doctor']
    assert new['backendBuildId']==info['backendBuildId']
    assert new['requestId']!=old['requestId']


def test_removed_binding_and_definition_are_reported_without_rows():
    before={'manifest':{'components':{'kpi':{'binding':{'comparisons':{'mom':{'baseline':'prior'}}},'config':{'explanation':'Definition'}}},'metrics':{}}}
    after=copy.deepcopy(before)
    after['manifest']['components']['kpi']={'config':{}}
    result=semantic_diff(before,after)
    assert result['count']==2
    assert all(change['change']=='removed' for change in result['changes'])
    assert 'Definition' not in json.dumps(result)


def test_wire_is_lossless_and_smaller():
    rows=[{'category':str(i),'series':'HO','values':{'value':-i,'name':'西安'}} for i in range(100)]
    result={'computed':{'components':{'c':{'data':{'records':copy.deepcopy(rows)}}}}}
    original=len(json.dumps(result))
    compact_records(result)
    packed=result['computed']['components']['c']['data']['packedRecords']
    restored=[{'category':r[0],'series':r[1],'values':dict(zip(packed['keys'],r[2:]))} for r in packed['rows']]
    assert restored==rows
    assert len(json.dumps(result)) < original * .7


def test_diagnostics_duration_and_build(tmp_path):
    service=Service(tmp_path/'runtime',project_root=tmp_path/'project')
    service.call('runtime_report_error',{'requestId':'sample','code':'CLIENT_FRAME_READY','durationMs':12.5})
    event=service.call('runtime_diagnostics',{'requestId':'sample'})['events'][0]
    assert event['duration_ms']==12.5
    assert event['backend_build_id']


def test_mcp_ignores_shadow_module_and_keeps_relative_project(tmp_path):
    import asyncio
    from pathlib import Path
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    root=Path(__file__).resolve().parents[2]
    shadow=tmp_path/'dashboard_runtime'
    shadow.mkdir()
    (shadow/'__init__.py').write_text('raise RuntimeError("wrong module")')
    async def check():
        params=StdioServerParameters(command='node',args=[str(root/'bin/dashboard-runtime.js'),'--project-root','project','--runtime-root','runtime','mcp'],cwd=str(tmp_path))
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                result=await session.call_tool('runtime_info',{})
                assert not result.isError
                value=result.structuredContent or json.loads(result.content[0].text)
                assert value['moduleRoot']==str(root/'dashboard_runtime')
    asyncio.run(check())
    assert (tmp_path/'project/charts-project.json').exists()
