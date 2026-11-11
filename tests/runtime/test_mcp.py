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

# @wu-test type=integration | scope=MCP stdio | protects=默认写入摘要泄漏全文或显式完整结果及分块读取失败
def test_real_stdio_protocol(tmp_path):
    from dashboard_runtime.store import Store
    Store(tmp_path/'mcp').create('mcp-test', 'MCP')
    async def check():
        params=StdioServerParameters(command=sys.executable,args=['-m','dashboard_runtime','--root',str(tmp_path/'mcp'),'mcp'],env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[2])+os.pathsep+os.environ.get('PYTHONPATH','')})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                tools=await session.list_tools()
                assert 'dashboard_preview' in [t.name for t in tools.tools]
                by_name = {tool.name: tool for tool in tools.tools}
                assert not any(name.startswith('dashboard_preview_') for name in by_name)
                app_only = {'runtime_keepalive', 'runtime_report_error', 'dashboard_export_open'}
                for name in app_only:
                    meta = by_name[name].meta
                    assert meta is not None
                    assert meta['ui']['visibility'] == ['app']
                assert all(tool.meta is None for name,tool in by_name.items() if name not in app_only | {'dashboard_preview'})
                for name in ('dashboard_patch', 'dashboard_restore'):
                    annotations = by_name[name].annotations
                    assert annotations is not None
                    assert annotations.destructiveHint is True
                read_annotations = by_name['dashboard_get'].annotations
                assert read_annotations is not None
                assert read_annotations.readOnlyHint is True
                assert read_annotations.idempotentHint is True
                export_annotations = by_name['dashboard_export'].annotations
                assert export_annotations is not None
                assert export_annotations.readOnlyHint is False
                preview_meta = by_name['dashboard_preview'].meta
                assert preview_meta is not None
                assert preview_meta['ui']['resourceUri'].startswith('ui://charts-design/')
                assert by_name['generation_examples'].meta is None
                preview = await session.call_tool('dashboard_preview', {'dashboardId': 'mcp-test'})
                assert not preview.isError
                assert preview.structuredContent is not None
                assert preview.structuredContent['document']['id'] == 'mcp-test'
                result=await session.call_tool('dashboard_create',{'dashboardId':'mcp-test','title':'MCP'})
                assert result.isError
                assert result.structuredContent is not None
                assert result.structuredContent['error']['code'] == 'PROJECT_REQUIRED'
                invalid_operation = await session.call_tool('dashboard_patch', {
                    'dashboardId': 'mcp-test', 'expectedRevision': 1,
                    'operations': [{'op': 'set_title'}]})
                assert invalid_operation.isError
                result=await session.call_tool('dashboard_patch',{'dashboardId':'mcp-test','expectedRevision':1,'operations':[{'op':'set_title','value':'Edited over MCP'}]})
                assert not result.isError
                assert result.structuredContent is not None
                assert result.structuredContent['revision']==2
                import json
                assert isinstance(result.content[0], TextContent)
                summary = json.loads(result.content[0].text)
                assert summary['dashboardId'] == 'mcp-test'
                assert summary == result.structuredContent
                assert 'document' not in summary
                assert summary['ok'] is True
                bad=await session.call_tool('dashboard_patch',{'dashboardId':'mcp-test','expectedRevision':1,'operations':[{'op':'set_title','value':'Stale'}]})
                assert bad.isError
                report=await session.call_tool('dashboard_patch',{'dashboardId':'mcp-test','responseMode':'full','expectedRevision':2,'operations':[
                    {'op':'put_component','id':'note','value':{'kind':'text','title':'Analysis','text':'Authored finding'}},
                    {'op':'set_view_mode','value':'report'},
                    {'op':'set_report','value':{'subtitle':'Personal report','blocks':[{'id':'opening','componentId':'note'}]}}
                ]})
                assert not report.isError
                assert report.structuredContent is not None
                assert report.structuredContent['document']['manifest']['viewMode']=='report'
                assert report.structuredContent['document']['manifest']['report']['blocks']==[{'id':'opening','componentId':'note'}]
                source='# Written over MCP\n\n**A finding** with a list:\n\n- Verify the source.\n'
                markdown=await session.call_tool('dashboard_patch',{'dashboardId':'mcp-test','responseMode':'full','expectedRevision':3,'operations':[
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
                    'responseMode':'full','expectedRevision':4,'operations':[{'op':'set_report_markdown','value':large_source}]})
                assert not large.isError
                assert large.structuredContent is not None
                async def resolve(result):
                    import base64
                    envelope = result.structuredContent
                    assert envelope is not None
                    if 'transport' not in envelope:
                        return envelope
                    info = envelope['transport']
                    parts = []
                    for index in range(info['chunks']):
                        chunk = await session.call_tool('runtime_result_chunk', {'requestId': info['requestId'], 'index': index})
                        assert isinstance(chunk.content[0], TextContent)
                        assert chunk.structuredContent is not None
                        assert len(chunk.content[0].text) < 25000
                        parts.append(chunk.structuredContent['data'])
                    raw = base64.b64decode(''.join(parts))
                    assert len(raw) == info['bytes']
                    return json.loads(raw)
                assert (await resolve(large))['document']['manifest']['report']['markdown'] == large_source
                assert isinstance(large.content[0], TextContent)
                assert len(large.content[0].text) < 1000
                # A representative 960-row transport fixture exceeds the reported response size.
                rows = [{'detail': str(i) + 'x' * 1000} for i in range(960)]
                payload = await session.call_tool('dashboard_patch', {'dashboardId': 'mcp-test',
                    'dataMode': 'snapshot', 'responseMode': 'full',
                    'expectedRevision': 5, 'operations': [
                        {'op': 'put_source', 'id': 'transport-fixture', 'value': {'kind': 'fixture'}},
                        {'op': 'put_dataset', 'id': 'details', 'meta': {
                            'sourceId': 'transport-fixture', 'fields': {'detail': {'type': 'string'}}}, 'rows': rows},
                    ]})
                assert not payload.isError
                assert payload.structuredContent is not None
                assert (await resolve(payload))['document']['snapshot']['datasets']['details'] == rows
                assert isinstance(payload.content[0], TextContent)
                assert json.loads(payload.content[0].text)['transport']['bytes'] > 900000
                assert len(payload.content[0].text) < 1000
                resources=await session.list_resources()
                assert all(str(resource.uri).startswith(('charts://','ui://charts-design/')) for resource in resources.resources)
                ui=await session.read_resource(preview_meta['ui']['resourceUri'])
                assert isinstance(ui.contents[0], TextResourceContents)
                assert 'window.__chartsBoot=' in ui.contents[0].text
                contract=await session.read_resource(AnyUrl('charts://contract'))
                assert isinstance(contract.contents[0], TextResourceContents)
                guide = json.loads(contract.contents[0].text)
                assert guide['tools'] == {name: tool.model_dump(by_alias=True, exclude_none=True, exclude={'name'})
                    for name, tool in by_name.items()}
                assert 'set_layout' in contract.contents[0].text
                assert 'set_report_markdown' in contract.contents[0].text and 'set_report' in contract.contents[0].text and 'set_view_mode' in contract.contents[0].text
    asyncio.run(check())


# @wu-test type=integration | scope=MCP编辑完成与数据检查 | protects=数据文件不可用时被当作保存成功或失败后草稿批次无法继续
def test_failed_finish_preserves_draft_and_batch_over_stdio(tmp_path):
    from dashboard_runtime.service import Service
    from dashboard_runtime.demo import executive_document

    project = tmp_path / 'project'
    service = Service(tmp_path / 'setup', project_root=project)
    service.call('dashboard_create', {'dashboardId': 'review', 'document': executive_document('review')})

    async def check():
        params = StdioServerParameters(command=sys.executable,
            args=['-m', 'dashboard_runtime', '--project-root', str(project),
                  '--runtime-root', str(tmp_path / 'runtime'), 'mcp'],
            env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[2]) + os.pathsep + os.environ.get('PYTHONPATH', '')})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                batch = await session.call_tool('dashboard_edit_begin', {'dashboardId': 'review', 'expectedRevision': 1})
                assert not batch.isError
                assert batch.structuredContent is not None
                batch_id = batch.structuredContent['batch_id']
                edited = await session.call_tool('dashboard_patch', {'dashboardId': 'review', 'expectedRevision': 1,
                    'operations': [{'op': 'set_title', 'value': 'Reviewed draft'}]})
                assert not edited.isError
                data_path = project / 'data' / 'data.sqlite3'
                unavailable = tmp_path / 'unavailable.sqlite3'
                data_path.rename(unavailable)
                arguments = {'dashboardId': 'review', 'expectedRevision': 2, 'batchId': batch_id}
                for name in ('dashboard_edit_finish', 'dashboard_checkpoint'):
                    failed = await session.call_tool(name, arguments if name == 'dashboard_edit_finish' else
                                                     {'dashboardId': 'review', 'expectedRevision': 2})
                    assert failed.isError
                    value = failed.structuredContent
                    assert value is not None
                    assert value['error']['code'] == 'DOCTOR_FAILED'
                    assert value['doctor']['passed'] is False
                    assert value['nextAction'] == 'dashboard_get'
                draft = await session.call_tool('dashboard_get', {'dashboardId': 'review'})
                assert not draft.isError
                assert draft.structuredContent is not None
                assert draft.structuredContent['document']['manifest']['title'] == 'Reviewed draft'
                assert draft.structuredContent['document']['revision'] == 2
                history = await session.call_tool('dashboard_history', {'dashboardId': 'review'})
                assert not history.isError
                assert history.structuredContent is not None
                assert [item['revision'] for item in history.structuredContent['history']] == [1]
                resumed = await session.call_tool('dashboard_edit_begin', {'dashboardId': 'review', 'expectedRevision': 2})
                assert not resumed.isError
                assert resumed.structuredContent is not None
                assert resumed.structuredContent['batch_id'] == batch_id
                unavailable.replace(data_path)
                finished = await session.call_tool('dashboard_edit_finish', arguments)
                assert not finished.isError, finished
                assert finished.structuredContent is not None
                assert finished.structuredContent['ok'] is True
                assert finished.structuredContent['checkpoint']['revision'] == 2
                assert finished.structuredContent['nextAction'] == 'dashboard_preview'

    asyncio.run(check())


# @wu-test type=integration | scope=MCP批注 | protects=批注目标更新删除后丢批注
def test_read_annotations_and_edit_target_over_stdio(tmp_path):
    from dashboard_runtime.store import Store
    Store(tmp_path/'annotations').create('review', 'Review')
    async def check():
        params = StdioServerParameters(command=sys.executable,
            args=['-m', 'dashboard_runtime', '--root', str(tmp_path / 'annotations'), 'mcp'],
            env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[2]) + os.pathsep + os.environ.get('PYTHONPATH', '')})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {t.name: t for t in (await session.list_tools()).tools}
                assert tools['dashboard_annotations'].annotations is not None
                assert tools['dashboard_annotations'].annotations.readOnlyHint is True
                assert tools['dashboard_annotations'].meta is None

                async def call(name, **args):
                    result = await session.call_tool(name, args)
                    assert not result.isError, result
                    assert result.structuredContent is not None
                    return result.structuredContent

                empty = await call('dashboard_annotations', dashboardId='review')
                assert empty['count'] == 0 and empty['revision'] == 1
                note = {'id': 'review-note', 'componentId': 'finding', 'text': '将观察内容改为已核对收入',
                        'createdAt': '2026-10-28T12:00:00Z',
                        'anchor': {'scope': 'component', 'kind': 'element', 'quote': '待核对',
                                   'rect': {'x': 0, 'y': .2, 'width': 1, 'height': .3}}}
                old_note = {'id': 'page-note', 'componentId': None, 'text': '保留页面结构', 'createdAt': note['createdAt']}
                await call('dashboard_patch', dashboardId='review', expectedRevision=1, operations=[
                    {'op': 'put_component', 'id': 'finding', 'value': {'kind': 'text', 'title': '观察', 'text': '待核对'}},
                    {'op': 'set_annotations', 'value': [note, old_note]}])
                review = await call('dashboard_annotations', dashboardId='review')
                assert review['annotations'] == [note, old_note]
                assert review['count'] == 2 and review['revision'] == 2
                assert review['targets']['review-note'] == {'scope': 'component', 'componentExists': True,
                    'sourcePath': 'manifest.components.finding', 'title': '观察', 'kind': 'text'}
                assert review['targets']['page-note']['scope'] == 'page'
                assert 'document' not in review and 'snapshot' not in review
                current = (await call('dashboard_get', dashboardId='review'))['document']
                component = current['manifest']['components'][note['componentId']]
                modified = await call('dashboard_patch', dashboardId='review', expectedRevision=current['revision'], responseMode='full', operations=[
                    {'op': 'put_component', 'id': note['componentId'], 'value': {**component, 'text': '已核对收入'}}])
                assert modified['document']['manifest']['components']['finding']['text'] == '已核对收入'
                after = await call('dashboard_annotations', dashboardId='review')
                assert after['annotations'] == review['annotations']
                assert after['revision'] == 3
                await call('dashboard_patch', dashboardId='review', expectedRevision=3,
                    operations=[{'op': 'remove_component', 'id': 'finding'}])
                missing = await call('dashboard_annotations', dashboardId='review')
                assert missing['targets']['review-note']['componentExists'] is False
                assert missing['annotations'] == [note, old_note]
    asyncio.run(check())
