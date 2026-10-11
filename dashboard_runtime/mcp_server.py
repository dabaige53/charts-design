"""MCP stdio adapter using the official Python SDK v1 compatibility line."""
from __future__ import annotations
import asyncio
import json
from . import __version__
from .assets import render_html
from .model import DashboardError
from .service import READ_ONLY, TOOLS

URI = f'ui://charts-design/dashboard-v{__version__}.html'
MIME = 'text/html;profile=mcp-app'

def create_server(service):
    try:
        import mcp.types as types
        from mcp.server.lowlevel import Server
        from mcp.server.lowlevel.helper_types import ReadResourceContents
    except ImportError as exc:
        raise DashboardError('MCP_NOT_INSTALLED', 'Install the MCP adapter: python3 -m pip install "mcp>=1.28,<2"') from exc
    server = Server('charts-design', version=__version__)

    @server.list_tools()
    async def list_tools():
        result = []
        for name, (description, schema) in TOOLS.items():
            metadata = {'ui': {'resourceUri': URI}} if name == 'dashboard_preview' else {}
            result.append(types.Tool(name=name, description=description, inputSchema=schema,
                annotations=types.ToolAnnotations(readOnlyHint=name in READ_ONLY, destructiveHint=False, openWorldHint=False),
                **({'_meta': metadata} if metadata else {})))
        return result

    @server.call_tool()
    async def call_tool(name, arguments):
        try:
            result = await asyncio.to_thread(service.call, name, arguments or {})
            return types.CallToolResult(content=[types.TextContent(type='text', text=json.dumps(result, ensure_ascii=False, allow_nan=False))], structuredContent=result)
        except DashboardError as exc:
            return types.CallToolResult(isError=True, content=[types.TextContent(type='text', text=json.dumps(exc.as_dict()))], structuredContent=exc.as_dict())
        except (KeyError, TypeError, ValueError) as exc:
            return types.CallToolResult(isError=True, content=[types.TextContent(type='text', text=str(exc))])

    @server.list_resources()
    async def list_resources():
        return [types.Resource(uri=URI, name='Dashboard editor', mimeType=MIME),
                types.Resource(uri='charts://catalog', name='Chart catalog', mimeType='application/json'),
                types.Resource(uri='charts://contract', name='Runtime tools and typed operations', mimeType='application/json')]

    @server.read_resource()
    async def read_resource(uri):
        if str(uri) == URI:
            return [ReadResourceContents(content=render_html('mcp'), mime_type=MIME)]
        if str(uri) == 'charts://catalog':
            return json.dumps(service.call('chart_catalog', {}), ensure_ascii=False)
        if str(uri) == 'charts://contract':
            from .contract import CONTRACT
            return json.dumps(CONTRACT)
        raise ValueError('Unknown resource')
    return server

async def run(service):
    server = create_server(service)
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
