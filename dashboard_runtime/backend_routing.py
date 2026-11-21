"""Persistent project ownership for the optional dual-backend MCP endpoint."""
import asyncio
from contextlib import closing
import os
import re
import sqlite3
from urllib.parse import urlsplit

from .model import DashboardError, require


class BackendRoutes:
    def __init__(self, path, projects, base_url, token):
        self.path, self.projects = path, projects
        self.base_url, self.token = base_url.rstrip('/'), token
        url = urlsplit(self.base_url)
        require(url.scheme == 'https' and url.hostname and not (url.username or url.password or url.query or url.fragment),
                'Configure the HTTPS CloudBase service base URL, not a token URL', 'INVALID_CONFIG')
        with closing(sqlite3.connect(path)) as database:
            database.execute('CREATE TABLE IF NOT EXISTS routes (project TEXT PRIMARY KEY, backend TEXT NOT NULL)')

    def binding(self, project, backend=None):
        with closing(sqlite3.connect(self.path)) as database, database:
            if backend is not None:
                database.execute('INSERT INTO routes VALUES (?, ?) ON CONFLICT(project) DO NOTHING', (project, backend))
            row = database.execute('SELECT backend FROM routes WHERE project = ?', (project,)).fetchone()
            return row[0] if row else None

    async def owners(self, project):
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self.base_url + '/api/v1/catalog', json={},
                                         headers={'Authorization': 'Bearer ' + self.token})
            response.raise_for_status()
            names = {item['name'] for item in response.json()['projects']}
        local = await asyncio.to_thread(self.projects.exists, project)
        return {name for name, present in [('server', local), ('cloudbase', project in names)] if present}

    async def select(self, project, requested, tool):
        require(isinstance(project, str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', project),
                'Pass a project name in projectRoot on every unified call', 'PROJECT_REQUIRED')
        require(requested in (None, 'server', 'cloudbase'), 'Unknown backend', 'INVALID_BACKEND')
        owner = await asyncio.to_thread(self.binding, project)
        if owner is None:
            try:
                owners = await self.owners(project)
            except Exception:
                raise DashboardError('CATALOG_UNAVAILABLE', 'Could not verify both project catalogs; no tool was dispatched', 503) from None
            if len(owners) == 1:
                owner = next(iter(owners))
            else:
                require(requested is not None, 'Choose backend: server or cloudbase', 'BACKEND_REQUIRED')
                require(owners or tool == 'dashboard_create', 'Unknown project; use dashboard_create first', 'PROJECT_NOT_FOUND')
                owner = requested
            require(requested is None or requested == owner, 'Project belongs to the other backend', 'BACKEND_CONFLICT')
            recorded = await asyncio.to_thread(self.binding, project, owner)
            require(recorded == owner, 'A concurrent call bound the project to the other backend', 'BACKEND_CONFLICT')
        require(requested is None or requested == owner, 'Project is already bound to the other backend', 'BACKEND_CONFLICT')
        return owner

    async def forward(self, name, request):
        from .remote_client import connect
        try:
            async with connect(self.base_url + '/mcp', self.token) as session:
                return await session.call_tool(name, request)
        except Exception:
            raise DashboardError('BACKEND_UNAVAILABLE', 'CloudBase request failed; verify state before retrying a write', 503) from None


def configured_routes(server):
    names = ('CHARTS_UNIFIED_TOKEN', 'CHARTS_CLOUDBASE_URL', 'CHARTS_CLOUDBASE_MCP_TOKEN')
    entry_token, base_url, upstream_token = (os.environ.get(name, '') for name in names)
    if not any((entry_token, base_url, upstream_token)):
        return None
    require(len(entry_token) >= 32 and base_url and upstream_token and entry_token != upstream_token
            and not server.admin(entry_token), 'Configure independent unified and backend credentials', 'INVALID_CONFIG')
    return BackendRoutes(server.settings.runtime / 'backend-routes.sqlite3', server.projects, base_url, upstream_token)
