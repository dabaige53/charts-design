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
                complete = (await session.read_resource(AnyUrl(transfer['resourceUri']))).contents[0]
                assert isinstance(complete, TextResourceContents)
                assert json.loads(complete.text) == saved

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


# @wu-test type=integration | scope=MCP数据初始化连续性 | protects=导入后缺少字段和真实指标ID，或必须先造临时组件才能检查数据
def test_data_receipts_continue_to_inspection_and_authoring(tmp_path):
    import sqlite3

    upstream = tmp_path / 'upstream.sqlite3'
    with sqlite3.connect(upstream) as db:
        db.execute('CREATE TABLE sales (customerId TEXT, amount REAL)')
        db.executemany('INSERT INTO sales VALUES (?, ?)', [('001', 10), ('002', 20)])
    sources = tmp_path / 'sources.json'
    sources.write_text(json.dumps({'sales-db': {'engine': 'sqlite', 'path': str(upstream)}}))

    async def check():
        root = Path(__file__).resolve().parents[2]
        project = str(tmp_path / 'project')
        params = StdioServerParameters(command=sys.executable,
            args=['-m', 'dashboard_runtime', '--root', str(tmp_path / 'runtime'),
                  '--sources', str(sources), 'mcp'],
            env={**os.environ, 'PYTHONPATH': str(root) + os.pathsep + os.environ.get('PYTHONPATH', '')})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                assert tools['dataset_preview'].annotations.readOnlyHint is True
                assert tools['dataset_preview'].inputSchema['properties']['limit']['maximum'] == 100
                assert 'fields' in tools['dataset_import'].inputSchema['properties']

                async def call(tool, arguments):
                    result = await session.call_tool(tool, arguments)
                    assert not result.isError, result
                    assert result.structuredContent is not None
                    return result.structuredContent

                context = {'projectRoot': project, 'dashboardId': 'analysis'}
                created = await call('dashboard_create', {**context, 'title': 'Sales analysis'})
                fields = {'customerId': {'type': 'string'}, 'amount': {'type': 'number'}}
                imported = await call('dataset_import', {**context, 'expectedRevision': created['revision'],
                    'datasetId': 'sales', 'fields': fields,
                    'csvText': 'customerId,amount\n001,10\n002,20\n003,\n'})
                dataset = imported['dataset']
                assert dataset['fields'] == fields and dataset['sourceId']
                assert dataset['mode'] == 'snapshot' and dataset['rowCount'] == 3
                assert imported['counts']['components'] == 0
                assert 'document' not in imported
                metric_id, metric = next(iter(dataset['metrics'].items()))
                assert len(dataset['metrics']) == 1
                assert metric['field'] == 'amount' and metric['status'] == 'unverified'
                assert metric['aggregation'] == 'sum' and metric['unit'] == ''

                # A separate project request must not change the continuation target.
                await call('dashboard_create', {'projectRoot': str(tmp_path / 'other-project'),
                    'dashboardId': 'analysis', 'title': 'Other project'})
                next_call = imported['nextCalls'][0]
                assert next_call['tool'] == 'dataset_preview'
                assert next_call['arguments']['projectRoot'] == project
                sample = await call(next_call['tool'], next_call['arguments'])
                assert sample['revision'] == imported['revision']
                assert sample['totalRows'] == 3 and sample['filtersApplied'] is False
                assert sample['rows'] == [{'customerId': '001', 'amount': 10},
                    {'customerId': '002', 'amount': 20}, {'customerId': '003', 'amount': None}]
                assert sample['dataVersion'] == next_call['arguments']['dataVersion']

                # Bind the returned ID directly; do not reproduce UUID generation.
                saved = await call('dashboard_submit', {**context, 'expectedRevision': imported['revision'],
                    'operations': [
                        {'op': 'put_metric', 'id': metric_id, 'value': {**metric, 'label': 'Sales amount',
                            'unit': 'CNY', 'definition': 'Sum of supplied sales amounts; missing values excluded.'}},
                        {'op': 'put_component', 'id': 'total', 'value': {'kind': 'kpi', 'title': 'Sales amount',
                            'datasetId': 'sales', 'measures': [metric_id]}},
                        {'op': 'put_component', 'id': 'detail', 'value': {'kind': 'table', 'title': 'Sales rows',
                            'datasetId': 'sales'}},
                        {'op': 'set_report_markdown', 'value': '# Sales analysis\n\n```chart\n{"componentId":"total"}\n```\n\n```chart\n{"componentId":"detail"}\n```'},
                        {'op': 'set_view_mode', 'value': 'report'},
                    ]})
                assert saved['ok'] and saved['nextAction'] == 'dashboard_preview'
                view = await call('dashboard_view', {**context, 'expectedRevision': saved['revision'],
                    'componentIds': ['total'], 'includeEvidence': True})
                assert view['computed']['components']['total']['value'] == '30 CNY'
                assert view['evidence']['total']['metrics'][metric_id]['status'] == 'unverified'
                preview = await call(saved['nextAction'], context)
                assert preview['document']['revision'] == saved['revision']
                assert preview['document']['manifest']['viewMode'] == 'report'
                assert '"componentId":"detail"' in preview['document']['manifest']['report']['markdown']

                attached = await call('dataset_attach', {**context, 'expectedRevision': saved['revision'],
                    'datasetId': 'a' * 80, 'connection': 'sales-db', 'table': 'sales'})
                assert attached['dataset']['id'] == 'a' * 80
                assert len(attached['dataset']['sourceId']) <= 80
                assert attached['dataset']['fields']['amount']['type'] == 'number'
                assert attached['dataset']['metrics'] == {}
                next_call = attached['nextCalls'][0]
                assert (await call(next_call['tool'], next_call['arguments']))['totalRows'] == 2

                queried = await call('query_execute', {**context, 'expectedRevision': attached['revision'],
                    'datasetId': 'live-sales', 'connection': 'sales-db', 'sql': 'SELECT * FROM sales',
                    'mode': 'live', 'fields': fields})
                assert queried['dataset']['mode'] == 'live'
                assert queried['dataset']['fields'] == fields and queried['dataset']['sourceId']
                assert 'version' not in queried['dataset'] and 'rowCount' not in queried['dataset']
                assert len(queried['dataset']['metrics']) == 1
                with sqlite3.connect(upstream) as db:
                    db.execute('INSERT INTO sales VALUES (?, ?)', ('004', 40))
                next_call = queried['nextCalls'][0]
                sample = await call(next_call['tool'], next_call['arguments'])
                assert sample['transient'] is True and sample['mode'] == 'live'
                assert sample['totalRows'] == 3 and sample['rows'][-1]['amount'] == 40
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
