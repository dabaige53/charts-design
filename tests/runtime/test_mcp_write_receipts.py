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
                mode = tools['dashboard_patch'].inputSchema['properties']['responseMode']
                assert mode == contract['tools']['dashboard_patch']['inputSchema']['properties']['responseMode']
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
