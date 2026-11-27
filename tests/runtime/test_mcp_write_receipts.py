"""Write summaries at the real MCP boundary, without changing saved documents."""
import asyncio
import base64
import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip('mcp')
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent, TextResourceContents
from pydantic import AnyUrl


# @wu-test type=integration | scope=MCP写入摘要 | protects=大文档修改重复进入模型上下文或摘要版本无法用于后续写入
def test_write_receipts_preserve_storage_and_revision_flow(tmp_path):
    async def check():
        root = Path(__file__).resolve().parents[2]
        params = StdioServerParameters(command=sys.executable,
            args=['-m', 'dashboard_runtime', '--project-root', str(tmp_path / 'project'),
                  '--runtime-root', str(tmp_path / 'runtime'), 'mcp'],
            env={**os.environ, 'PYTHONPATH': str(root) + os.pathsep + os.environ.get('PYTHONPATH', '')})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                resource = (await session.read_resource(AnyUrl('charts://contract'))).contents[0]
                assert isinstance(resource, TextResourceContents)
                contract = json.loads(resource.text)
                mode = contract['clientTools']['dashboard_patch']['properties']['responseMode']
                assert mode == tools['dataset_import'].inputSchema['properties']['responseMode']
                assert mode['default'] == 'summary'
                assert 'responseMode' not in tools['dashboard_get'].inputSchema['properties']
                assert tools['dashboard_view'].inputSchema['properties']['responseMode']['enum'] == ['full', 'patch']

                async def call(name, **args):
                    target = {} if name == 'runtime_result_chunk' else {'dashboardId': 'receipt'}
                    result = await session.call_tool(name, {**target, **args})
                    assert not result.isError, result
                    value = result.structuredContent
                    assert value is not None
                    assert isinstance(result.content[0], TextContent)
                    assert json.loads(result.content[0].text) == value
                    return value

                created = await call('dashboard_create', title='Receipt')
                assert created['revision'] == 1 and 'document' not in created
                assert created['projectRoot'] == str(tmp_path / 'project')
                begun = await call('dashboard_edit_begin', expectedRevision=created['revision'])
                text = 'PRIVATE_REPORT_BODY ' * 4000
                patched = await call('dashboard_patch', expectedRevision=created['revision'], operations=[
                    {'op': 'put_component', 'id': 'note', 'value': {'kind': 'text', 'title': 'Note', 'text': text}},
                ])
                assert patched['revision'] == 2 and patched['affectedComponentIds'] == ['note']
                assert 'document' not in patched and 'transport' not in patched
                assert 'PRIVATE_REPORT_BODY' not in json.dumps(patched)
                assert len(json.dumps(patched)) < 2000
                assert 'doctor' not in patched  # A write receipt must not claim full validation.
                stored = await call('dashboard_get')
                transfer = stored['transport']
                parts = []
                for index in range(transfer['chunks']):
                    chunk = await call('runtime_result_chunk', requestId=transfer['requestId'], index=index)
                    parts.append(chunk['data'])
                saved = json.loads(base64.b64decode(''.join(parts)))
                assert saved['document']['manifest']['components']['note']['text'] == text

                imported = await call('dataset_import', expectedRevision=patched['revision'],
                                      datasetId='sales', rows=[{'month': 'July', 'revenue': 100}])
                assert imported['revision'] == 3 and imported['counts']['datasets'] == 1
                assert imported['counts']['metrics'] == 1
                assert imported['dataset']['id'] == 'sales' and imported['dataset']['rowCount'] == 1
                assert imported['dataset']['version']
                assert 'document' not in imported
                finished = await call('dashboard_edit_finish', expectedRevision=imported['revision'],
                                      batchId=begun['batch_id'])
                assert finished['ok'] is True and finished['doctor']['passed'] is True

                invalid = await session.call_tool('dashboard_patch', {'dashboardId': 'receipt',
                    'expectedRevision': imported['revision'], 'responseMode': 'invalid',
                    'operations': [{'op': 'set_title', 'value': 'Must not save'}]})
                assert invalid.isError
                removed = await call('dashboard_patch', expectedRevision=imported['revision'],
                                     operations=[{'op': 'remove_component', 'id': 'note'}])
                assert removed['affectedComponentIds'] == ['note']
                full = await call('dashboard_patch', expectedRevision=removed['revision'], responseMode='full',
                                 operations=[{'op': 'set_title', 'value': 'Full result'}])
                assert full['document']['manifest']['title'] == 'Full result'
                assert full['document']['manifest']['components'] == {}
                current = await call('dashboard_get')
                assert current['document']['revision'] == full['document']['revision']
                assert current['document']['manifest']['datasets']['sales']['fields']['revenue']['type'] == 'number'
                stale = await session.call_tool('dashboard_patch', {'dashboardId': 'receipt',
                    'expectedRevision': 1, 'operations': [{'op': 'set_title', 'value': 'Stale'}]})
                assert stale.isError and stale.structuredContent is not None
                assert stale.structuredContent['error']['code'] == 'REVISION_CONFLICT'
    asyncio.run(check())


# @wu-test type=integration | scope=MCP 保存版本读取一致性 | protects=未保存草稿导致预览的图表、明细、筛选项、口径和导出读取不同版本
def test_saved_reader_queries_keep_one_revision_while_the_draft_changes(tmp_path):
    from dashboard_runtime.model import apply_operations, new_document

    async def check():
        root = Path(__file__).resolve().parents[2]
        params = StdioServerParameters(command=sys.executable,
            args=['-m', 'dashboard_runtime', '--project-root', str(tmp_path / 'project'),
                  '--runtime-root', str(tmp_path / 'runtime'), 'mcp'],
            env={**os.environ, 'PYTHONPATH': str(root) + os.pathsep + os.environ.get('PYTHONPATH', '')})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                async def call(name, **args):
                    result = await session.call_tool(name, {'dashboardId': 'pinned', **args})
                    assert not result.isError, result
                    assert result.structuredContent is not None
                    return result.structuredContent

                meta = {'sourceId': 'fixture', 'fields': {'region': {'type': 'string'}, 'revenue': {'type': 'number'}}}
                rows = [{'region': 'saved', 'revenue': 10}, {'region': 'saved', 'revenue': 20}]
                metric = {'datasetId': 'sales', 'field': 'revenue', 'aggregation': 'sum',
                          'label': 'Revenue', 'unit': 'CNY', 'definition': 'Saved revenue definition', 'status': 'unverified'}
                doc = apply_operations(new_document('pinned', 'Pinned'), [
                    {'op': 'put_source', 'id': 'fixture', 'value': {'kind': 'fixture', 'name': 'Saved source'}},
                    {'op': 'put_dataset', 'id': 'sales', 'meta': meta, 'rows': rows},
                    {'op': 'put_metric', 'id': 'revenue', 'value': metric},
                    {'op': 'put_component', 'id': 'total', 'value': {'kind': 'kpi', 'title': 'Revenue', 'datasetId': 'sales', 'measures': ['revenue']}},
                    {'op': 'set_filters', 'value': [{'id': 'region', 'label': 'Region', 'field': 'region', 'op': 'in', 'values': [], 'componentIds': ['total']}]},
                ])
                await call('dashboard_create', document=doc)
                saved = (await call('dashboard_get'))['document']
                await call('dashboard_patch', expectedRevision=1, operations=[
                    {'op': 'put_dataset', 'id': 'sales', 'meta': meta, 'rows': [{'region': 'draft', 'revenue': 900}]},
                    {'op': 'put_metric', 'id': 'revenue', 'value': {**metric, 'unit': 'USD', 'definition': 'Unsaved definition'}},
                ])
                pinned = {'expectedRevision': 1, 'dataVersion': saved['dataVersion']}
                view = await call('dashboard_view', **pinned, responseMode='patch', componentIds=['total'])
                assert view['revision'] == 1 and view['computed']['components']['total']['value'] == '30 CNY'
                details = await call('component_data', **pinned, componentId='total', limit=10)
                assert details['rows'] == rows and details['totalRows'] == 2
                options = await call('dashboard_filter_options', **pinned, filterId='region')
                assert options['values'] == ['saved']
                semantics = await call('semantic_inspect', **pinned, componentId='total')
                assert semantics['metrics']['revenue']['definition'] == metric['definition']
                provenance = await call('query_inspect', **pinned, componentId='total')
                assert provenance['localVersion'] == saved['snapshot']['datasetRefs']['sales']
                exported = await call('dataset_export', **pinned, componentId='total')
                csv = Path(exported['export']['path']).read_text()
                assert 'saved,10' in csv and 'saved,20' in csv and 'draft' not in csv
                snapshot = await call('dashboard_export', **pinned, format='json')
                exported_doc = json.loads(Path(snapshot['export']['path']).read_text())
                assert exported_doc['revision'] == 1
                assert exported_doc['computed']['components']['total']['value'] == '30 CNY'
                assert (await call('dashboard_filter_options', filterId='region'))['values'] == ['draft']

                requests = [
                    ('dashboard_view', {'responseMode': 'patch', 'componentIds': ['total']}),
                    ('component_data', {'componentId': 'total'}),
                    ('dashboard_filter_options', {'filterId': 'region'}),
                    ('semantic_inspect', {'componentId': 'total'}),
                    ('query_inspect', {'componentId': 'total'}),
                    ('dataset_export', {'componentId': 'total'}),
                    ('dashboard_export', {'format': 'json'}),
                ]
                for name, args in requests:
                    for invalid in ({'expectedRevision': 99}, {**pinned, 'dataVersion': 'stale-data'}):
                        result = await session.call_tool(name, {'dashboardId': 'pinned', **args, **invalid})
                        assert result.isError and result.structuredContent is not None
                        assert result.structuredContent['error']['code'] == 'REVISION_CONFLICT'
                await call('dashboard_checkpoint', expectedRevision=2)
                historic = await call('dashboard_version_query', revision=1, operation='details',
                                      request={'componentId': 'total', 'dataVersion': saved['dataVersion']})
                assert historic['rows'] == rows and historic['totalRows'] == 2
                assert (await call('dashboard_get'))['document']['revision'] == 2
    asyncio.run(check())
