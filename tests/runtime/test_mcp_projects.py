"""One stdio connection isolates project assets, response chunks and legacy defaults."""
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
from mcp.types import TextResourceContents
from pydantic import AnyUrl

from dashboard_runtime.service import Service
from dashboard_runtime.demo import executive_document


def parameters(tmp_path, default=None):
    root = Path(__file__).resolve().parents[2]
    args = ['-m', 'dashboard_runtime', '--runtime-root', str(tmp_path / 'runtime')]
    if default:
        args += ['--project-root', str(default)]
    return StdioServerParameters(command=sys.executable, args=[*args, 'mcp'],
        env={**os.environ, 'PYTHONPATH': str(root) + os.pathsep + os.environ.get('PYTHONPATH', '')})


async def call(session, name, project=None, **args):
    if project is not None:
        args['projectRoot'] = str(project)
    result = await session.call_tool(name, args)
    assert not result.isError, result
    value = result.structuredContent
    assert value is not None
    return value


# @wu-test type=integration | scope=MCP多项目 | protects=同ID看板批注分块串数据或刷新临时筛选被保存
def test_one_connection_handles_two_projects_and_restart(tmp_path):
    first, second = tmp_path / 'first', tmp_path / 'second'

    async def check():
        async with stdio_client(parameters(tmp_path)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                assert all('projectRoot' in tool.inputSchema['properties'] for tool in tools)
                contract = (await session.read_resource(AnyUrl('charts://contract'))).contents[0]
                assert isinstance(contract, TextResourceContents)
                assert 'projectRoot' in json.loads(contract.text)['tools']['dashboard_preview']['inputSchema']['properties']
                documents = [executive_document('same'), executive_document('same')]
                for doc, title in zip(documents, ('First', 'Second')):
                    doc['manifest']['title'] = title
                documents[1]['snapshot']['datasets']['sales'][0]['revenue'] += 1000
                await asyncio.gather(*[call(session, 'dashboard_create', project,
                    dashboardId='same', document=doc) for project, doc in zip((first, second), documents)])
                a, b = await asyncio.gather(*[call(session, 'dashboard_get', project, dashboardId='same')
                    for project in (first, second)])
                assert a['projectRoot'] == str(first)
                assert b['projectRoot'] == str(second)
                assert 'projectRoot' not in a['document'] and 'projectRoot' not in b['document']
                assert a['document']['manifest']['title'] == 'First'
                assert b['document']['manifest']['title'] == 'Second'
                views = await asyncio.gather(*[call(session, 'dashboard_view', project,
                    dashboardId='same', componentIds=['total'], responseMode='patch') for project in (first, second)])
                assert views[0]['computed']['components']['total'] != views[1]['computed']['components']['total']
                selected_filter = a['document']['manifest']['filters'][0]['id']
                refreshed = await call(session, 'dashboard_refresh', first, dashboardId='same',
                    filters=[{'id': selected_filter, 'values': ['East']}])
                assert next(f for f in refreshed['document']['manifest']['filters'] if f['id'] == selected_filter)['values'] == ['East']
                saved = await call(session, 'dashboard_get', first, dashboardId='same')
                assert next(f for f in saved['document']['manifest']['filters'] if f['id'] == selected_filter)['values'] == []
                exports = await asyncio.gather(*[call(session, 'dataset_export', project,
                    dashboardId='same', datasetId='sales') for project in (first, second)])
                assert exports[0]['export']['rowCount'] == exports[1]['export']['rowCount'] == 6
                assert Path(exports[0]['export']['path']).read_text() != Path(exports[1]['export']['path']).read_text()
                assert (await call(session, 'dashboard_list'))['dashboards'] == []
                missing = await session.call_tool('dashboard_create', {'dashboardId': 'missing'})
                assert missing.isError
                assert missing.structuredContent is not None
                assert missing.structuredContent['error']['code'] == 'PROJECT_REQUIRED'
                relative = await session.call_tool('dashboard_list', {'projectRoot': 'relative'})
                assert relative.isError
                assert relative.structuredContent is not None
                assert relative.structuredContent['error']['code'] == 'INVALID_PROJECT'

                batch = await call(session, 'dashboard_edit_begin', first, dashboardId='same', expectedRevision=1)
                note = {'id': 'note', 'componentId': None, 'text': 'First only', 'createdAt': '2026-11-02'}
                await call(session, 'dashboard_patch', first, dashboardId='same', expectedRevision=1,
                    operations=[{'op': 'set_title', 'value': 'Updated first'}, {'op': 'set_annotations', 'value': [note]}])
                done = await call(session, 'dashboard_edit_finish', first, dashboardId='same',
                    expectedRevision=2, batchId=batch['batch_id'])
                assert done['ok']
                assert done['nextAction'] == 'dashboard_preview'
                assert done['displayPolicy'] == 'saved-dashboard-ui'
                assert (await call(session, 'dashboard_annotations', first, dashboardId='same'))['count'] == 1
                assert (await call(session, 'dashboard_annotations', second, dashboardId='same'))['count'] == 0
                assert len((await call(session, 'dashboard_history', first, dashboardId='same'))['history']) == 2
                assert len((await call(session, 'dashboard_history', second, dashboardId='same'))['history']) == 1

                # The project is available before the first chunk is decoded.
                text = '# First project\n\n' + 'Project-owned report content.\n' * 3000
                packed = await call(session, 'dashboard_patch', first, dashboardId='same', expectedRevision=2,
                    operations=[{'op': 'set_report_markdown', 'value': text}])
                assert packed['projectRoot'] == str(first)
                transfer = packed['transport']
                wrong = await session.call_tool('runtime_result_chunk', {'projectRoot': str(second),
                    'requestId': transfer['requestId'], 'index': 0})
                assert wrong.isError
                assert wrong.structuredContent is not None
                assert wrong.structuredContent['error']['code'] == 'RESULT_EXPIRED'
                pieces = [await call(session, 'runtime_result_chunk', first,
                    requestId=transfer['requestId'], index=index) for index in range(transfer['chunks'])]
                decoded = json.loads(base64.b64decode(''.join(piece['data'] for piece in pieces)))
                assert decoded['document']['manifest']['report']['markdown'] == text
                assert decoded['projectRoot'] == str(first)
                info_a, info_b = await asyncio.gather(*[call(session, 'runtime_info', project) for project in (first, second)])
                assert info_a['runtimeRoot'] != info_b['runtimeRoot']
                loaded = await call(session, 'dashboard_get', second, dashboardId='same')
                assert loaded['document']['manifest']['title'] == 'Second'

        async with stdio_client(parameters(tmp_path)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                assert (await call(session, 'dashboard_get', second, dashboardId='same'))['document']['manifest']['title'] == 'Second'
                assert (await call(session, 'dashboard_annotations', first, dashboardId='same'))['count'] == 1
                chunk = await call(session, 'runtime_result_chunk', first, requestId=transfer['requestId'], index=0)
                assert chunk['data'] == pieces[0]['data']
        for project in (first, second):
            draft = json.loads((project / 'dashboards' / 'same' / 'draft.json').read_text())
            assert 'projectRoot' not in draft
            assert (project / 'data' / 'data.sqlite3').exists()

    asyncio.run(check())


# @wu-test type=integration | scope=MCP默认项目 | protects=默认项目或旧存储切换后读错
def test_startup_project_and_legacy_store_remain_defaults(tmp_path):
    default, other = tmp_path / 'default', tmp_path / 'other'
    Service(tmp_path / 'runtime', project_root=default).call('dashboard_create', {'dashboardId': 'same', 'title': 'Existing'})

    async def check():
        async with stdio_client(parameters(tmp_path, default)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await call(session, 'dashboard_create', other, dashboardId='same', title='Other')
                implicit = await call(session, 'dashboard_get', dashboardId='same')
                explicit = await call(session, 'dashboard_get', default, dashboardId='same')
                assert implicit['document'] == explicit['document']
                info = await call(session, 'runtime_info')
                assert info['projectRoot'] == str(default)
                assert info['runtimeRoot'] == str(tmp_path / 'runtime')

        legacy = Service(tmp_path / 'runtime')
        legacy.call('dashboard_create', {'dashboardId': 'legacy', 'title': 'Legacy'})
        async with stdio_client(parameters(tmp_path)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await call(session, 'dashboard_list', other)
                result = await call(session, 'dashboard_get', dashboardId='legacy')
                assert result['projectRoot'] is None
                assert result['document']['manifest']['title'] == 'Legacy'

    asyncio.run(check())
