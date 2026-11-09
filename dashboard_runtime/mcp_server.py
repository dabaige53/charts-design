"""MCP stdio adapter using the official Python SDK v1 compatibility line."""
from __future__ import annotations
import asyncio
import json
import re
import sys
from .lifecycle import IdleLifetime, DEFAULT_IDLE_TIMEOUT
from . import __version__
from .assets import render_html, ui_build_id
from .model import DashboardError, MAX_BYTES
from .service import READ_ONLY, TOOLS
from .project_routing import ProjectResolver, ProjectServices, project_result, project_schema

LEGACY_URI = f'ui://charts-design/dashboard-v{__version__}.html'
def current_ui_uri():
    """Frontend rebuilds also change resource identity in a running worker."""
    return f'ui://charts-design/dashboard-v{__version__}-{ui_build_id()}.html'

URI = current_ui_uri()
MIME = 'text/html;profile=mcp-app'
UI_TOOLS = {'dashboard_preview'}

def current_preview_tool():
    """A new tool identity also bypasses hosts caching old tool descriptors."""
    return f'dashboard_preview_{ui_build_id()}'

def is_preview_alias(name):
    return re.fullmatch(r'dashboard_preview_[0-9a-f]{12}', name) is not None

def is_ui_uri(uri):
    # Historical conversations retain resource identities across worker restarts.
    return re.fullmatch(r'ui://charts-design/dashboard-v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9a-f]{12})?\.html', str(uri)) is not None

def result_text(result):
    """Transport.pack already bounds the payload; text-only hosts need all fields."""
    return json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':'))

UNPACKED = ('runtime_result_chunk', 'runtime_diagnostics', 'runtime_report_error', 'runtime_keepalive')


class McpProfile:
    """Transport-specific policy. The local stdio profile changes nothing.

    A self-hosted server substitutes project sandboxing, hides tools that act on
    the server desktop and decorates results with browser links.
    """
    hidden_tools = frozenset()
    extra_tools: dict = {}

    def projects(self, service) -> ProjectResolver:
        return ProjectServices(service)

    def describe(self, name, description):
        return description

    def schema(self, name, schema):
        return project_schema(schema)

    def call(self, name, request, selected) -> dict | None:
        """Handle a profile-owned tool, or return None to use the shared service."""
        return None

    def decorate(self, name, request, result, selected):
        return project_result(result, selected)


def create_server(service, lifetime=None, profile=None):
    lifetime = lifetime or IdleLifetime()
    profile = profile or McpProfile()
    projects = profile.projects(service)
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
        tools = {**TOOLS, current_preview_tool(): (
            'Open the latest dashboard UI; prefer this build-specific preview over historical preview cards',
            TOOLS['dashboard_preview'][1]), **profile.extra_tools}
        for name, (description, schema) in tools.items():
            if name in profile.hidden_tools:
                continue
            description = profile.describe('dashboard_preview' if is_preview_alias(name) else name, description)
            schema = profile.schema(name, schema)
            preview = name in UI_TOOLS or is_preview_alias(name)
            metadata = {'ui': {'resourceUri': advertised_uri}, 'ui/resourceUri': advertised_uri} if preview else {}
            if name == 'runtime_keepalive':
                metadata = {'ui': {'visibility': ['app']}}
            tool = types.Tool(name=name, description=description, inputSchema=schema,
                annotations=types.ToolAnnotations(readOnlyHint=preview or name in READ_ONLY, destructiveHint=False, openWorldHint=False))
            if metadata:
                tool.meta = metadata
            result.append(tool)
        return result

    @server.call_tool()
    @lifetime.track
    async def call_tool(name, arguments):
        nonlocal advertised_uri
        selected = service
        try:
            if is_preview_alias(name):
                name = 'dashboard_preview'
            if name in profile.hidden_tools or (name not in TOOLS and name not in profile.extra_tools):
                raise DashboardError('UNKNOWN_TOOL', f'Unsupported tool: {name}', 404)
            selected, request = await asyncio.to_thread(projects.resolve, dict(arguments or {}))
            if name == 'dashboard_create' and not selected.project_root:
                raise DashboardError('PROJECT_REQUIRED', 'Pass projectRoot or start with --project-root for new dashboards; legacy --root supports existing dashboards only')
            if name in TOOLS and 'dataMode' in TOOLS[name][1].get('properties', {}):
                request.setdefault('dataMode', 'local')
            def execute():
                handled = profile.call(name, request, selected)
                return profile.decorate(name, request, handled if handled is not None else selected.call(name, request), selected)
            result = await asyncio.to_thread(execute)
            text = None
            if name not in UNPACKED:
                packed, text = selected.transport.encode(result, name)
                if packed is not result:
                    result, text = profile.decorate('runtime_result_chunk', request, packed, selected), None
            uri = current_ui_uri()
            if advertised_uri != uri:
                advertised_uri = uri
                known_uris.add(uri)
                await server.request_context.session.send_tool_list_changed()
                await server.request_context.session.send_resource_list_changed()
            # The measured compact JSON doubles as the text fallback; serialize once.
            return types.CallToolResult(content=[types.TextContent(type='text', text=text if text is not None else result_text(result))], structuredContent=result)
        except DashboardError as exc:
            selected.transport.log('', name, 'server', exc.code)
            return types.CallToolResult(isError=True, content=[types.TextContent(type='text', text=json.dumps(exc.as_dict()))], structuredContent=exc.as_dict())
        except (KeyError, TypeError, ValueError) as exc:
            selected.transport.log('', name, 'server', type(exc).__name__)
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
                types.Resource(uri=AnyUrl('charts://layouts'), name='Dashboard layout templates', mimeType='application/json'),
                types.Resource(uri=AnyUrl('charts://examples'), name='Dashboard and report reference cases', mimeType='application/json'),
                types.Resource(uri=AnyUrl('charts://examples/executive-dashboard'), name='Dashboard generation case', mimeType='application/json'),
                types.Resource(uri=AnyUrl('charts://examples/operations-scorecard'), name='Contrasting scorecard dashboard case', mimeType='application/json'),
                types.Resource(uri=AnyUrl('charts://examples/academic-report'), name='Approved academic report master', mimeType='application/json')]

    @server.read_resource()
    @lifetime.track
    async def read_resource(uri):
        if str(uri) in known_uris or is_ui_uri(uri):
            return [ReadResourceContents(content=render_html('mcp', idle_timeout=lifetime.timeout),
                                         mime_type=MIME, meta={'ui': {'prefersBorder': True}})]
        if str(uri) == 'charts://catalog':
            return [ReadResourceContents(content=json.dumps(service.call('chart_catalog', {}), ensure_ascii=False), mime_type='application/json')]
        if str(uri) == 'charts://contract':
            from .contract import CONTRACT
            contract = {**CONTRACT, 'tools': {name: {**tool, 'inputSchema': project_schema(tool['inputSchema'])}
                for name, tool in CONTRACT['tools'].items()}, 'projectRouting': {
                    'selector': 'projectRoot', 'scope': 'request', 'path': 'absolute asset directory',
                    'omitted': 'startup project default or legacy store; never the last selected project',
                    'preview': 'bind once from result.projectRoot; include it in all subsequent calls, including chunks'}}
            return [ReadResourceContents(content=json.dumps(contract, ensure_ascii=False), mime_type='application/json')]
        if str(uri) == 'charts://layouts':
            from .layouts import templates_catalog
            return [ReadResourceContents(content=json.dumps(templates_catalog(), ensure_ascii=False), mime_type='application/json')]
        if str(uri) == 'charts://declarations':
            from .declarations import declaration_contract
            return [ReadResourceContents(content=json.dumps(declaration_contract(), ensure_ascii=False), mime_type='application/json')]
        if str(uri) == 'charts://examples' or str(uri) in ('charts://examples/executive-dashboard', 'charts://examples/operations-scorecard', 'charts://examples/academic-report'):
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
