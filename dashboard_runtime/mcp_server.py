"""MCP stdio adapter using the official Python SDK v1 compatibility line."""
from __future__ import annotations
import asyncio
import json
import sys
from .lifecycle import IdleLifetime, DEFAULT_IDLE_TIMEOUT
from . import __version__
from .assets import render_html, ui_build_id
from .model import DashboardError, MAX_BYTES
from .service import READ_ONLY, TOOLS

LEGACY_URI = f'ui://charts-design/dashboard-v{__version__}.html'
def current_ui_uri():
    """Frontend rebuilds also change resource identity in a running worker."""
    return f'ui://charts-design/dashboard-v{__version__}-{ui_build_id()}.html'

URI = current_ui_uri()
MIME = 'text/html;profile=mcp-app'
UI_TOOLS = {'dashboard_create', 'dashboard_preview', 'dashboard_patch',
            'dashboard_restore', 'dataset_import', 'query_execute', 'dataset_attach',
            'dashboard_view', 'dashboard_migrate', 'dashboard_migration_rollback'}
UI_TOOLS.add('dashboard_refresh')

def result_text(result):
    """Keep the canonical artifact once, in structuredContent, rather than twice."""
    if 'export' in result and 'content' in result['export']:
        return json.dumps({'export': {k: v for k, v in result['export'].items() if k != 'content'}}, ensure_ascii=False)
    if isinstance(result.get('computed'), dict) and isinstance(result.get('componentIds'), list):
        return json.dumps({'dashboardId': result['id'], 'revision': result['revision'],
                           'componentIds': result['componentIds'], 'artifactLocation': 'structuredContent'},
                          ensure_ascii=False, allow_nan=False)
    document = result.get('document')
    if not isinstance(document, dict):
        return json.dumps(result, ensure_ascii=False, allow_nan=False)
    summary = {key: value for key, value in result.items() if key not in ('document', 'statisticalArtifacts')}
    summary.update({
        'dashboardId': document['id'], 'revision': document['revision'],
        'annotationCount': len(document['manifest'].get('annotations', [])),
        'title': document['manifest']['title'], 'artifactLocation': 'structuredContent.document',
        'documentBytes': len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode('utf-8')),
        'datasetRows': {**{key: len(rows) for key, rows in document['snapshot']['datasets'].items()},
                        **{key: ref['rowCount'] for key, ref in document['snapshot'].get('datasetRefs', {}).items()}},
    })
    return json.dumps(summary, ensure_ascii=False, allow_nan=False)

def create_server(service, lifetime=None):
    lifetime = lifetime or IdleLifetime()
    try:
        import mcp.types as types
        from mcp.server.lowlevel import Server
        from mcp.server.lowlevel.helper_types import ReadResourceContents
        from pydantic import AnyUrl
    except ImportError as exc:
        raise DashboardError('MCP_NOT_INSTALLED', 'Install the MCP adapter: python3 -m pip install "mcp>=1.28,<2"') from exc
    server = Server('charts-design', version=__version__)
    advertised_uri = None
    known_uris = {URI, LEGACY_URI}

    @server.list_tools()
    @lifetime.track
    async def list_tools():
        nonlocal advertised_uri
        advertised_uri = current_ui_uri()
        known_uris.add(advertised_uri)
        result = []
        for name, (description, schema) in TOOLS.items():
            metadata = {'ui': {'resourceUri': advertised_uri}, 'ui/resourceUri': advertised_uri} if name in UI_TOOLS else {}
            if name == 'runtime_keepalive':
                metadata = {'ui': {'visibility': ['app']}}
            tool = types.Tool(name=name, description=description, inputSchema=schema,
                annotations=types.ToolAnnotations(readOnlyHint=name in READ_ONLY, destructiveHint=False, openWorldHint=False))
            if metadata:
                tool.meta = metadata
            result.append(tool)
        return result

    @server.call_tool()
    @lifetime.track
    async def call_tool(name, arguments):
        nonlocal advertised_uri
        try:
            request = dict(arguments or {})
            if name in TOOLS and 'dataMode' in TOOLS[name][1].get('properties', {}):
                request.setdefault('dataMode', 'local')
            result = await asyncio.to_thread(service.call, name, request)
            uri = current_ui_uri()
            if advertised_uri != uri:
                advertised_uri = uri
                known_uris.add(uri)
                await server.request_context.session.send_tool_list_changed()
                await server.request_context.session.send_resource_list_changed()
            return types.CallToolResult(content=[types.TextContent(type='text', text=result_text(result))], structuredContent=result)
        except DashboardError as exc:
            return types.CallToolResult(isError=True, content=[types.TextContent(type='text', text=json.dumps(exc.as_dict()))], structuredContent=exc.as_dict())
        except (KeyError, TypeError, ValueError) as exc:
            return types.CallToolResult(isError=True, content=[types.TextContent(type='text', text=str(exc))])

    @server.list_resources()
    @lifetime.track
    async def list_resources():
        uri = current_ui_uri()
        known_uris.add(uri)
        return [types.Resource(uri=AnyUrl(uri), name='Dashboard editor', mimeType=MIME),
                types.Resource(uri=AnyUrl('charts://catalog'), name='Chart catalog', mimeType='application/json'),
                types.Resource(uri=AnyUrl('charts://contract'), name='Runtime tools and typed operations', mimeType='application/json'),
                types.Resource(uri=AnyUrl('charts://declarations'), name='Chart declaration requirements', mimeType='application/json'),
                types.Resource(uri=AnyUrl('charts://examples'), name='Dashboard and report reference cases', mimeType='application/json'),
                types.Resource(uri=AnyUrl('charts://examples/executive-dashboard'), name='Dashboard generation case', mimeType='application/json'),
                types.Resource(uri=AnyUrl('charts://examples/academic-report'), name='Approved academic report master', mimeType='application/json')]

    @server.read_resource()
    @lifetime.track
    async def read_resource(uri):
        if str(uri) in known_uris or str(uri) == current_ui_uri():
            return [ReadResourceContents(content=render_html('mcp', idle_timeout=lifetime.timeout),
                                         mime_type=MIME, meta={'ui': {'prefersBorder': True}})]
        if str(uri) == 'charts://catalog':
            return [ReadResourceContents(content=json.dumps(service.call('chart_catalog', {}), ensure_ascii=False), mime_type='application/json')]
        if str(uri) == 'charts://contract':
            from .contract import CONTRACT
            return [ReadResourceContents(content=json.dumps(CONTRACT, ensure_ascii=False), mime_type='application/json')]
        if str(uri) == 'charts://declarations':
            from .declarations import declaration_contract
            return [ReadResourceContents(content=json.dumps(declaration_contract(), ensure_ascii=False), mime_type='application/json')]
        if str(uri) == 'charts://examples' or str(uri) in ('charts://examples/executive-dashboard', 'charts://examples/academic-report'):
            args = {} if str(uri) == 'charts://examples' else {'caseId':str(uri).rsplit('/',1)[1]}
            return [ReadResourceContents(content=json.dumps(service.call('generation_examples', args), ensure_ascii=False), mime_type='application/json')]
        raise ValueError('Unknown resource')
    return server

async def run(service, idle_timeout=DEFAULT_IDLE_TIMEOUT):
    lifetime = IdleLifetime(idle_timeout)
    server = create_server(service, lifetime)
    from mcp.server.stdio import stdio_server
    from anyio import AsyncFile
    # The SDK's default stdin uses a blocking file-reader thread. Use a pipe
    # reader so idle shutdown can finish even while the host keeps stdin open.
    reader = asyncio.StreamReader(limit=MAX_BYTES * 2)
    pipe, _ = await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
    class AsyncStdin(AsyncFile[str]):
        async def readline(self):
            line = await reader.readline()
            return line.decode('utf-8', errors='replace')
    async with stdio_server(stdin=AsyncStdin(sys.stdin)) as (read_stream, write_stream):
        # SDK import and transport setup are startup work, not idle time.
        with lifetime.activity():
            pass
        async def watch_idle():
            while not lifetime.expired():
                await asyncio.sleep(min(1, idle_timeout / 4))
            print('MCP closed after idle timeout', file=sys.stderr)
        tasks = [asyncio.create_task(server.run(read_stream, write_stream, server.create_initialization_options())),
                 asyncio.create_task(watch_idle())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            pipe.close()
            reader.feed_eof()
            await write_stream.aclose()
