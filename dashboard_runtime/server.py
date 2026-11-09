"""Self-hosted server: Streamable HTTP MCP, browser previews and signed downloads.

One long-running process serves three audiences from the same project storage
and the same transport-independent ``Service``:

* MCP clients (Claude Code, Claude Desktop, Codex, IDEs) on ``/mcp`` with a
  bearer token, or ``/mcp/<token>`` for clients that cannot send headers.
* Browser readers on ``/view/<project>/<dashboard>`` (read-only) and
  ``/edit/<project>/<dashboard>`` (layout/title editing). Pages load the shared
  UI bundle and read data through a scoped API using an expiring signed token
  carried in the URL fragment, which browsers never send to servers or proxies.
* Downloads of exports through signed, expiring ``/files/<token>`` links.

Remote callers name a project; they never choose arbitrary server paths. Each
project is a directory in one workspace with the same layout as local projects.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import gzip
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sqlite3
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

from . import __version__
from .model import ID, DashboardError, MAX_BYTES, require
from .service import STR, TOOLS, Service, schema as tool_schema
from .mcp_server import McpProfile

PROJECT_NAME = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$')
MIN_TOKEN_LENGTH = 16
DEFAULT_SHARE_HOURS = 168
FILE_LINK_SECONDS = 24 * 3600

# Tools a read-only share link may call. Every call is pinned to the shared
# dashboard; listing returns only that dashboard.
VIEW_TOOLS = frozenset({
    'dashboard_get', 'dashboard_view', 'dashboard_refresh', 'dashboard_filter_options',
    'component_data', 'query_inspect', 'semantic_inspect', 'statistical_render',
    'dashboard_annotations', 'dashboard_list', 'runtime_info', 'runtime_keepalive',
    'runtime_report_error', 'dashboard_export', 'dataset_export', 'legacy_render',
})
# An edit link additionally saves layout, titles, descriptions and checkpoints.
EDIT_TOOLS = VIEW_TOOLS | frozenset({
    'dashboard_patch', 'dashboard_edit_begin', 'dashboard_edit_finish', 'dashboard_checkpoint',
    'dashboard_validate', 'dashboard_doctor', 'dashboard_history', 'dashboard_history_diff',
    'dashboard_restore', 'dashboard_version_label', 'runtime_diagnostics', 'dashboard_export_site',
})
# Acts on the server's desktop session; meaningless and unsafe remotely.
HIDDEN_TOOLS = frozenset({'dashboard_export_open'})
SANITIZED_INFO = ('version', 'uiBuildId', 'backendBuildId', 'dashboardRevision')


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def _iso(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec='seconds')


@dataclass
class ServerSettings:
    workspace: Path
    runtime: Path
    host: str = '127.0.0.1'
    port: int = 8000
    public_url: str = ''
    tokens: tuple = ()
    secret: bytes = b''
    share_hours: float = DEFAULT_SHARE_HOURS
    default_project: str = 'default'
    sources: str | None = None
    stateless: bool = False
    allowed_hosts: tuple = ()
    forwarded_allow_ips: str = '127.0.0.1'
    insecure_no_auth: bool = False
    base_path: str = field(init=False, default='')
    explicit_public_url: bool = field(init=False, default=False)

    def __post_init__(self):
        self.workspace = Path(self.workspace).expanduser().resolve()
        self.runtime = Path(self.runtime).expanduser().resolve()
        self.explicit_public_url = bool(self.public_url)
        if not self.public_url:
            shown = '127.0.0.1' if self.host in ('0.0.0.0', '::', '') else self.host
            self.public_url = f'http://{shown}:{self.port}'
        parsed = urlparse(self.public_url)
        require(parsed.scheme in ('http', 'https') and bool(parsed.netloc), 'public URL must be an absolute http(s) URL', 'INVALID_CONFIG')
        self.public_url = self.public_url.rstrip('/')
        # A reverse proxy may publish the server under a prefix; it must strip
        # the prefix before forwarding. Generated links include it.
        self.base_path = parsed.path.rstrip('/')
        require(PROJECT_NAME.fullmatch(self.default_project) is not None, 'Invalid default project name', 'INVALID_CONFIG')
        require(0 < self.share_hours <= 24 * 366, 'Share lifetime must be between 1 hour and 1 year', 'INVALID_CONFIG')
        for token in self.tokens:
            require(len(token) >= MIN_TOKEN_LENGTH, f'Bearer tokens need at least {MIN_TOKEN_LENGTH} characters', 'INVALID_CONFIG')
        if self.insecure_no_auth:
            require(self.host in ('127.0.0.1', 'localhost', '::1'), '--insecure-no-auth is only allowed on a loopback address', 'INVALID_CONFIG')
        if not self.secret:
            self.secret = load_secret(self.runtime / 'server-secret')
        require(len(self.secret) >= 32, 'The signing secret needs at least 32 bytes', 'INVALID_CONFIG')

    def security(self):
        """DNS-rebinding protection derived from the published and bound addresses.

        Bearer authentication already prevents a rebinding page from using the
        endpoint, so Host/Origin checks are enforced when the canonical address
        is known (explicit public URL or allowed hosts) or authentication is off.
        """
        from mcp.server.transport_security import TransportSecuritySettings
        if not (self.explicit_public_url or self.allowed_hosts or self.insecure_no_auth):
            return TransportSecuritySettings(enable_dns_rebinding_protection=False)
        public = urlparse(self.public_url)
        hosts = {public.netloc, f'127.0.0.1:{self.port}', f'localhost:{self.port}', *self.allowed_hosts}
        if self.host not in ('0.0.0.0', '::', ''):
            hosts.add(f'{self.host}:{self.port}')
        origins = {f'{public.scheme}://{public.netloc}', f'http://127.0.0.1:{self.port}', f'http://localhost:{self.port}'}
        origins.update(f'https://{host}' for host in self.allowed_hosts)
        return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=sorted(hosts), allowed_origins=sorted(origins))


def load_secret(path: Path) -> bytes:
    """Publish a complete key once, including during concurrent startup."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            return path.read_bytes()
        except FileNotFoundError:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.server-secret-') as handle:
                handle.write(secrets.token_bytes(32))
                handle.flush()
                os.fsync(handle.fileno())
                try:
                    os.link(handle.name, path)
                except FileExistsError:
                    pass  # Another process published its complete key first.
            return path.read_bytes()
    except OSError as exc:
        raise DashboardError('INVALID_CONFIG', f'Cannot initialize signing secret: {exc}') from exc


class Signer:
    """Compact HMAC-SHA256 tokens: base64url(payload).base64url(mac)."""

    def __init__(self, secret: bytes):
        self.secret = secret

    def _mac(self, body: str) -> str:
        return _b64(hmac.new(self.secret, b'charts-design.v1.' + body.encode('ascii'), hashlib.sha256).digest())

    def sign(self, payload: dict) -> str:
        body = _b64(json.dumps(payload, separators=(',', ':'), sort_keys=True, ensure_ascii=True).encode())
        return body + '.' + self._mac(body)

    def verify(self, token, kind: str) -> dict | None:
        if not isinstance(token, str) or token.count('.') != 1 or len(token) > 4096:
            return None
        body, mac = token.split('.')
        if not hmac.compare_digest(mac, self._mac(body)):
            return None
        try:
            payload = json.loads(_unb64(body))
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get('k') != kind:
            return None
        if not isinstance(payload.get('exp'), int) or payload['exp'] < time.time():
            return None
        return payload


class ShareState:
    """Per-dashboard link generations; revoking bumps the generation."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), timeout=10, isolation_level=None, check_same_thread=False)
        self._db.execute('CREATE TABLE IF NOT EXISTS share_generations (project TEXT, dashboard TEXT, generation INTEGER, PRIMARY KEY(project, dashboard))')

    def generation(self, project, dashboard) -> int:
        with self._lock:
            row = self._db.execute('SELECT generation FROM share_generations WHERE project=? AND dashboard=?', (project, dashboard)).fetchone()
        return row[0] if row else 0

    def revoke(self, project, dashboard) -> int:
        with self._lock:
            self._db.execute('INSERT INTO share_generations VALUES(?,?,1) ON CONFLICT(project, dashboard) DO UPDATE SET generation=generation+1', (project, dashboard))
            return self._db.execute('SELECT generation FROM share_generations WHERE project=? AND dashboard=?', (project, dashboard)).fetchone()[0]


class WorkspaceProjects:
    """Resolve project names inside one workspace; never accept outside paths."""

    def __init__(self, settings: ServerSettings, queries=None):
        self.settings = settings
        self.queries = queries
        self._services: dict[str, Service] = {}
        self._lock = threading.Lock()
        settings.workspace.mkdir(parents=True, exist_ok=True)

    def name(self, value) -> str:
        if value is None:
            return self.settings.default_project
        require(isinstance(value, str) and bool(value), 'projectRoot must be a project name such as "sales"', 'INVALID_PROJECT')
        path = Path(value).expanduser()
        if path.is_absolute():
            # Absolute paths remain accepted for compatibility with local skills,
            # but only for direct children of the workspace.
            resolved = path.resolve()
            require(resolved.parent == self.settings.workspace, 'projectRoot must name a project in this server workspace', 'PROJECT_OUTSIDE_WORKSPACE')
            value = resolved.name
        require(PROJECT_NAME.fullmatch(value) is not None, 'projectRoot must be a project name: letters, digits, "-" or "_" (at most 64 characters)', 'INVALID_PROJECT')
        return value

    def exists(self, name: str) -> bool:
        return PROJECT_NAME.fullmatch(name or '') is not None and (self.settings.workspace / name / 'charts-project.json').is_file()

    def names(self) -> list[str]:
        return sorted(path.name for path in self.settings.workspace.iterdir()
                      if path.is_dir() and PROJECT_NAME.fullmatch(path.name) and (path / 'charts-project.json').is_file())

    def service(self, name: str) -> Service:
        with self._lock:
            service = self._services.get(name)
            if service is None:
                service = Service(self.settings.runtime / 'projects' / name, project_root=self.settings.workspace / name)
                if self.queries is not None:
                    # Source aliases remain operator configured, not supplied by callers.
                    service.queries = self.queries
                service.project_name = name
                self._services[name] = service
        return service

    def resolve(self, arguments: dict) -> tuple[Service, dict]:
        request = dict(arguments)
        return self.service(self.name(request.pop('projectRoot', None))), request


class Links:
    def __init__(self, settings: ServerSettings, signer: Signer, state: ShareState):
        self.settings, self.signer, self.state = settings, signer, state

    def share(self, project: str, dashboard: str, access: str = 'view', hours: float | None = None) -> dict:
        require(access in ('view', 'edit'), 'access must be view or edit')
        hours = self.settings.share_hours if hours is None else hours
        require(isinstance(hours, (int, float)) and not isinstance(hours, bool) and 0 < hours <= 24 * 366, 'expiresInHours must be between 1 and 8784')
        expires = int(time.time() + hours * 3600)
        token = self.signer.sign({'k': 'share', 'p': project, 'd': dashboard, 'a': access, 'exp': expires,
                                  'g': self.state.generation(project, dashboard), 'n': secrets.token_hex(4)})
        url = f'{self.settings.public_url}/{access}/{quote(project)}/{quote(dashboard)}#token={token}'
        return {'url': url, 'access': access, 'expiresAt': _iso(expires)}

    def file(self, project: str, path: str) -> str | None:
        root = (self.settings.workspace / project).resolve()
        target = Path(path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            return None
        expires = int(time.time() + FILE_LINK_SECONDS)
        token = self.signer.sign({'k': 'file', 'p': project, 'f': target.relative_to(root).as_posix(), 'exp': expires})
        return f'{self.settings.public_url}/files/{token}'


class ServerProfile(McpProfile):
    """MCP policy for remote clients: sandboxed projects and browser links."""

    hidden_tools = HIDDEN_TOOLS

    def __init__(self, projects: WorkspaceProjects, links: Links):
        self.workspace, self.links = projects, links
        self.extra_tools = {
            'dashboard_share': ('Create an expiring browser link for one dashboard or report on this server. '
                                'access=view is read-only; access=edit also saves layout and titles. Give the URL to the user; it contains the access token.',
                                tool_schema({'dashboardId': STR, 'access': {'enum': ['view', 'edit']},
                                             'expiresInHours': {'type': 'number', 'minimum': 1, 'maximum': 8784}}, ('dashboardId',))),
            'dashboard_share_revoke': ('Invalidate every browser link previously issued for one dashboard on this server',
                                       tool_schema({'dashboardId': STR}, ('dashboardId',))),
        }

    def projects(self, service):
        return self.workspace

    def describe(self, name, description):
        if name == 'dashboard_preview':
            return (description + '. On this self-hosted server the result also contains previewUrl, an expiring read-only '
                    'browser link for hosts that cannot display MCP Apps; give it to the user after the edit batch finishes.')
        if name in ('dashboard_export', 'dataset_export', 'dashboard_export_site'):
            return description + '. On this server the export also contains downloadUrl, an expiring signed link.'
        return description

    def schema(self, name, schema):
        return {**schema, 'properties': {**schema.get('properties', {}), 'projectRoot': {
            'type': 'string', 'description': 'Project name on this server, for example "sales". Pass it on every call; '
            'a new name creates the project. Omit only to use the server default project.'}}}

    def call(self, name, request, selected):
        if name == 'dashboard_share':
            board = request.get('dashboardId')
            selected.store.revision(board)  # NOT_FOUND for unknown dashboards
            link = self.links.share(selected.project_name, board, request.get('access', 'view'), request.get('expiresInHours'))
            return {'dashboardId': board, **link}
        if name == 'dashboard_share_revoke':
            board = request.get('dashboardId')
            selected.store.revision(board)
            return {'dashboardId': board, 'revoked': True, 'generation': self.links.state.revoke(selected.project_name, board)}
        return None

    def decorate(self, name, request, result, selected):
        project = selected.project_name
        result = {**result, 'projectRoot': project}
        if name == 'dashboard_preview' and isinstance(result.get('document'), dict):
            link = self.links.share(project, result['document']['id'], 'view')
            result['previewUrl'], result['previewExpiresAt'] = link['url'], link['expiresAt']
        export = result.get('export')
        if isinstance(export, dict) and isinstance(export.get('path'), str):
            export = dict(export)
            export['downloadUrl'] = self.links.file(project, export['path'])
            if isinstance(export.get('siteArchive'), str):
                export['siteDownloadUrl'] = self.links.file(project, export['siteArchive'])
            result['export'] = export
        return result


@dataclass
class Principal:
    admin: bool
    access: str
    dashboard: str | None = None


class RemoteServer:
    """Owns settings, project services and the MCP session manager."""

    def __init__(self, settings: ServerSettings):
        if not settings.tokens and not settings.insecure_no_auth:
            raise DashboardError('INVALID_CONFIG', 'Configure at least one bearer token (--token, --token-file or CHARTS_SERVER_TOKENS)')
        from .query import QueryRunner
        from .mcp_server import create_server
        from .lifecycle import IdleLifetime
        self.settings = settings
        settings.runtime.mkdir(parents=True, exist_ok=True)
        self.queries = QueryRunner(settings.sources)
        self.projects = WorkspaceProjects(settings, self.queries)
        self.signer = Signer(settings.secret)
        self.state = ShareState(settings.runtime / 'server-state.sqlite3')
        self.links = Links(settings, self.signer, self.state)
        self.profile = ServerProfile(self.projects, self.links)
        # A long-running service has no idle shutdown.
        self.mcp = create_server(self.projects.service(settings.default_project), IdleLifetime(10 ** 9), self.profile)
        self._gzip: dict[tuple, bytes] = {}

    # Authentication -----------------------------------------------------
    def admin(self, token) -> bool:
        if not isinstance(token, str) or not token:
            return False
        matched = False
        for candidate in self.settings.tokens:
            matched |= hmac.compare_digest(token.encode(), candidate.encode())
        return matched

    def principal(self, token, project) -> Principal | None:
        if self.settings.insecure_no_auth and not token:
            return Principal(admin=True, access='edit')
        if self.admin(token):
            return Principal(admin=True, access='edit')
        payload = self.signer.verify(token, 'share')
        if payload is None or payload.get('p') != project:
            return None
        if payload.get('g') != self.state.generation(project, payload.get('d')):
            return None
        return Principal(admin=False, access=payload.get('a', 'view'), dashboard=payload.get('d'))

    # Viewer API ---------------------------------------------------------
    def call_viewer(self, project: str, name: str, args, principal: Principal):
        require(isinstance(args, dict), 'Tool arguments must be an object', 'INVALID_REQUEST')
        allowed = EDIT_TOOLS if principal.access == 'edit' else VIEW_TOOLS
        if name not in allowed:
            raise DashboardError('FORBIDDEN', 'This link does not allow that operation', 403)
        args = {key: value for key, value in args.items() if key != 'projectRoot'}
        service = self.projects.service(project)
        if principal.dashboard:
            if name == 'dashboard_list':
                return {'dashboards': [item for item in service.call('dashboard_list', {})['dashboards'] if item['id'] == principal.dashboard], 'projectRoot': project}
            properties = TOOLS.get(name, ('', {}))[1].get('properties', {})
            if 'dashboardId' in properties or 'dashboardId' in args:
                requested = args.get('dashboardId', principal.dashboard)
                if requested != principal.dashboard:
                    raise DashboardError('FORBIDDEN', 'This link is limited to another dashboard', 403)
                args['dashboardId'] = principal.dashboard
        result = self.profile.decorate(name, args, service.call(name, args), service)
        if name == 'runtime_info' and not principal.admin:
            result = {key: result[key] for key in SANITIZED_INFO if key in result} | {'projectRoot': project}
        export = result.get('export')
        if not principal.admin and isinstance(export, dict):
            # Readers receive download links, not server filesystem paths.
            result['export'] = {key: value for key, value in export.items()
                                if key not in ('path', 'directory', 'siteArchive', 'publishDirectory')}
        return result

    def file_path(self, token) -> Path | None:
        payload = self.signer.verify(token, 'file')
        if payload is None or not self.projects.exists(payload.get('p', '')):
            return None
        root = (self.settings.workspace / payload['p']).resolve()
        target = (root / str(payload.get('f', ''))).resolve()
        allowed = [(root / 'dashboards' / 'exports').resolve(), (root / 'deployments').resolve()]
        if not any(target.is_relative_to(base) for base in allowed) or not target.is_file():
            return None
        return target

    def gzip_asset(self, key, raw: bytes) -> bytes:
        cached = self._gzip.get(key)
        if cached is None:
            cached = gzip.compress(raw, 6)
            if len(self._gzip) > 8:
                self._gzip.clear()
            self._gzip[key] = cached
        return cached


SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'X-Frame-Options': 'DENY',
    'Cross-Origin-Opener-Policy': 'same-origin',
}


def _csp(*scripts: str) -> str:
    hashes = ' '.join("'sha256-" + base64.b64encode(hashlib.sha256(script.encode()).digest()).decode() + "'" for script in scripts)
    return ("default-src 'self'; script-src 'self' " + hashes + "; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; "
            "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


INDEX_SCRIPT = r"""
const $=s=>document.querySelector(s),api=(p,b)=>fetch(BASE+p,{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+(sessionStorage.getItem('charts-admin-token')||'')},body:JSON.stringify(b||{})}).then(async r=>{const v=await r.json();if(!r.ok)throw Error(v.error?.message||r.statusText);return v;});
const BASE=document.body.dataset.base;
async function load(){const list=$('#projects');list.replaceChildren();$('#status').textContent='正在读取…';
  try{const v=await api('/api/v1/catalog');$('#status').textContent=v.projects.length?'':'暂无项目。通过 MCP 创建看板或报告后在此预览。';
    for(const p of v.projects){const sec=document.createElement('section'),h=document.createElement('h2');h.textContent=p.name;sec.append(h);
      if(!p.dashboards.length){const e=document.createElement('p');e.className='muted';e.textContent='暂无看板';sec.append(e);}
      for(const d of p.dashboards){const row=document.createElement('div');row.className='row';const t=document.createElement('span');t.textContent=d.title+'  ·  '+d.id+'  ·  v'+d.revision;row.append(t);
        for(const [access,label] of [['view','预览'],['edit','编辑']]){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=async()=>{try{const s=await api('/api/v1/share',{project:p.name,dashboardId:d.id,access,expiresInHours:12});window.open(s.url,'_blank','noopener');}catch(e){$('#status').textContent=e.message;}};row.append(b);}
        sec.append(row);}
      list.append(sec);}
  }catch(e){$('#status').textContent=e.message;}}
$('#login').onsubmit=e=>{e.preventDefault();sessionStorage.setItem('charts-admin-token',$('#token').value.trim());$('#token').value='';load();};
if(sessionStorage.getItem('charts-admin-token'))load();
"""


def index_page(base: str) -> str:
    style = ('body{font:14px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif;color:#17212B;background:#F5F7F9;margin:0}'
             'main{max-width:880px;margin:0 auto;padding:40px 16px}h1{font-size:22px;margin:0 0 4px}h2{font-size:15px;margin:24px 0 8px;color:#123B5D}'
             '.muted{color:#7B8794}form{display:flex;gap:8px;margin:20px 0}input{flex:1;padding:8px 10px;border:1px solid #C9D1D8;border-radius:6px}'
             'button{padding:6px 12px;border:1px solid #123B5D;background:#123B5D;color:#fff;border-radius:6px;cursor:pointer}'
             '.row button{background:#fff;color:#123B5D;margin-left:8px}.row{display:flex;align-items:center;justify-content:space-between;'
             'background:#fff;border:1px solid #E6EAED;border-radius:8px;padding:10px 12px;margin:6px 0}code{background:#E6EAED;padding:1px 5px;border-radius:4px}')
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="referrer" content="no-referrer"><title>Charts Design Server</title><style>' + style + '</style></head>'
            f'<body data-base="{html.escape(base)}"><main><h1>Charts Design Server</h1>'
            f'<p class="muted">v{html.escape(__version__)} · MCP 端点 <code>{html.escape(base)}/mcp</code> · 看板与分析报告的网页预览</p>'
            '<form id="login"><input id="token" type="password" autocomplete="off" placeholder="输入服务器访问令牌以浏览全部项目" aria-label="访问令牌">'
            '<button type="submit">进入</button></form><p id="status" class="muted" role="status">预览链接也可由 MCP 工具 dashboard_preview / dashboard_share 生成。</p>'
            '<div id="projects"></div></main><script>' + INDEX_SCRIPT + '</script></body></html>')


def create_app(server: RemoteServer):
    """Starlette ASGI application. Starlette and uvicorn ship with the MCP SDK."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response
    from starlette.routing import Route
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    settings = server.settings
    base = settings.base_path
    import inspect
    options = {}
    if 'max_request_body_size' in inspect.signature(StreamableHTTPSessionManager).parameters:
        # dataset_import and patches accept up to 16 MiB, like the local transports.
        options['max_request_body_size'] = MAX_BYTES + 1024 * 1024
    manager = StreamableHTTPSessionManager(app=server.mcp, stateless=settings.stateless, security_settings=settings.security(), **options)

    async def read_body(request: Request, limit: int) -> bytes:
        """Refuse oversized bodies before buffering them, with or without Content-Length."""
        declared = request.headers.get('content-length')
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            raise DashboardError('PAYLOAD_TOO_LARGE', f'Body must contain at most {limit} bytes', 413)
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                raise DashboardError('PAYLOAD_TOO_LARGE', f'Body must contain at most {limit} bytes', 413)
            chunks.append(chunk)
        return b''.join(chunks)

    def bearer(request: Request) -> str:
        value = request.headers.get('authorization', '')
        return value[7:].strip() if value[:7].lower() == 'bearer ' else ''

    def failure(error: Exception) -> Response:
        if isinstance(error, DashboardError):
            return JSONResponse(error.as_dict(), status_code=error.status if error.status >= 400 else 400, headers=SECURITY_HEADERS)
        if isinstance(error, (KeyError, TypeError, ValueError)):
            return JSONResponse({'ok': False, 'error': {'code': 'INVALID_REQUEST', 'message': str(error)}}, status_code=400, headers=SECURITY_HEADERS)
        print('server error', type(error).__name__, file=sys.stderr)
        return JSONResponse({'ok': False, 'error': {'code': 'INTERNAL_ERROR', 'message': 'Request failed; inspect server logs'}}, status_code=500, headers=SECURITY_HEADERS)

    def compressed(request: Request, raw: bytes, media_type: str, headers: dict | None = None, cache_key=None) -> Response:
        headers = {**SECURITY_HEADERS, 'Vary': 'Accept-Encoding', **(headers or {})}
        if len(raw) > 1024 and 'gzip' in request.headers.get('accept-encoding', ''):
            raw = server.gzip_asset(cache_key, raw) if cache_key else gzip.compress(raw, 5)
            headers['Content-Encoding'] = 'gzip'
        return Response(raw, media_type=media_type, headers=headers)

    class McpEndpoint:
        """Bearer-authenticated Streamable HTTP MCP; the token may also be a path segment."""

        async def __call__(self, scope, receive, send):
            request = Request(scope, receive)
            token = scope.get('path_params', {}).get('secret') or bearer(request)
            if not (settings.insecure_no_auth or server.admin(token)):
                response = JSONResponse({'error': 'unauthorized', 'message': 'Send Authorization: Bearer <server token>'},
                                        status_code=401, headers={'WWW-Authenticate': 'Bearer realm="charts-design"'})
                await response(scope, receive, send)
                return
            await manager.handle_request(scope, receive, send)

    async def health(request: Request):
        return JSONResponse({'ok': True, 'version': __version__}, headers={'Cache-Control': 'no-store'})

    async def index(request: Request):
        return HTMLResponse(index_page(base), headers={**SECURITY_HEADERS, 'Cache-Control': 'no-store', 'Content-Security-Policy': _csp(INDEX_SCRIPT)})

    async def asset(request: Request):
        from .assets import bundle_assets
        name = request.path_params['name']
        build_id, javascript, styles = bundle_assets()
        match = re.fullmatch(r'app\.([0-9a-f]{12})\.(js|css)', name)
        if match is None or match[1] != build_id:
            return JSONResponse({'ok': False, 'error': {'code': 'NOT_FOUND', 'message': 'Unknown or outdated asset; reload the page'}}, status_code=404)
        kind = match[2]
        raw = javascript if kind == 'js' else styles
        etag = f'"{build_id}-{kind}"'
        if request.headers.get('if-none-match') == etag:
            return Response(status_code=304, headers={'ETag': etag})
        media = 'text/javascript; charset=utf-8' if kind == 'js' else 'text/css; charset=utf-8'
        return compressed(request, raw, media, {'Cache-Control': 'public, max-age=31536000, immutable', 'ETag': etag}, cache_key=(build_id, kind))

    async def page(request: Request):
        from .assets import render_shell
        project, board = request.path_params['project'], request.path_params['dashboard']
        access = 'edit' if request.url.path.startswith('/edit/') else 'view'
        if PROJECT_NAME.fullmatch(project) is None or ID.fullmatch(board) is None:
            return HTMLResponse('<!doctype html><title>Not found</title><p>Unknown page</p>', status_code=404, headers=SECURITY_HEADERS)
        boot = {'mode': 'web', 'idleTimeout': 3600, 'remote': {'apiBase': f'{base}/api/v1/p/{project}', 'board': board, 'access': access, 'project': project}}
        markup, script = render_shell(boot, f'{base}/assets')
        return HTMLResponse(markup, headers={**SECURITY_HEADERS, 'Cache-Control': 'no-store', 'Content-Security-Policy': _csp(script)})

    async def tool(request: Request):
        try:
            project, name = request.path_params['project'], request.path_params['name']
            # Authenticate before revealing whether a project exists.
            principal = server.principal(bearer(request), project)
            if principal is None:
                raise DashboardError('UNAUTHORIZED', '链接已失效或缺少访问令牌，请重新打开分享链接', 401)
            if not server.projects.exists(project):
                raise DashboardError('NOT_FOUND', 'Project not found', 404)
            if request.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
                raise DashboardError('CONTENT_TYPE', 'Use application/json', 415)
            body = await read_body(request, MAX_BYTES)
            if not body:
                raise DashboardError('INVALID_REQUEST', 'Body must contain a JSON object', 400)
            result = await asyncio.to_thread(server.call_viewer, project, name, json.loads(body), principal)
            raw = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
            return compressed(request, raw, 'application/json', {'Cache-Control': 'no-store'})
        except Exception as error:  # noqa: BLE001 - mapped to bounded JSON errors
            return failure(error)

    async def admin_catalog(request: Request):
        try:
            if not (settings.insecure_no_auth or server.admin(bearer(request))):
                raise DashboardError('UNAUTHORIZED', '访问令牌无效', 401)
            def catalog():
                return {'projects': [{'name': name, 'dashboards': server.projects.service(name).call('dashboard_list', {})['dashboards']}
                                     for name in server.projects.names()]}
            return JSONResponse(await asyncio.to_thread(catalog), headers={**SECURITY_HEADERS, 'Cache-Control': 'no-store'})
        except Exception as error:  # noqa: BLE001
            return failure(error)

    async def admin_share(request: Request):
        try:
            if not (settings.insecure_no_auth or server.admin(bearer(request))):
                raise DashboardError('UNAUTHORIZED', '访问令牌无效', 401)
            args = json.loads(await read_body(request, 64 * 1024) or b'{}')
            require(isinstance(args, dict), 'Arguments must be an object', 'INVALID_REQUEST')
            project = server.projects.name(args.get('project'))
            if not server.projects.exists(project):
                raise DashboardError('NOT_FOUND', 'Project not found', 404)
            def share():
                service = server.projects.service(project)
                return server.profile.call('dashboard_share', {k: v for k, v in args.items() if k != 'project'}, service)
            return JSONResponse(await asyncio.to_thread(share), headers={**SECURITY_HEADERS, 'Cache-Control': 'no-store'})
        except Exception as error:  # noqa: BLE001
            return failure(error)

    async def download(request: Request):
        target = await asyncio.to_thread(server.file_path, request.path_params['token'])
        if target is None:
            return JSONResponse({'ok': False, 'error': {'code': 'LINK_EXPIRED', 'message': 'Download link is invalid or expired'}}, status_code=404, headers=SECURITY_HEADERS)
        return FileResponse(target, filename=target.name, headers={**SECURITY_HEADERS, 'Cache-Control': 'private, no-store'})

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            yield

    routes = [
        Route('/health', health, methods=['GET', 'HEAD']),
        Route('/', index, methods=['GET']),
        Route('/assets/{name}', asset, methods=['GET']),
        Route('/view/{project}/{dashboard}', page, methods=['GET']),
        Route('/edit/{project}/{dashboard}', page, methods=['GET']),
        Route('/api/v1/p/{project}/tools/{name}', tool, methods=['POST']),
        Route('/api/v1/catalog', admin_catalog, methods=['POST']),
        Route('/api/v1/share', admin_share, methods=['POST']),
        Route('/files/{token}', download, methods=['GET']),
        Route('/mcp', McpEndpoint(), methods=['GET', 'POST', 'DELETE']),
        Route('/mcp/{secret}', McpEndpoint(), methods=['GET', 'POST', 'DELETE']),
    ]
    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.server = server
    return RequestLog(app)


class RequestLog:
    """Access log with route templates only: paths can carry tokens."""

    TEMPLATES = (
        (re.compile(r'^/mcp/[^/]+$'), '/mcp/<token>'),
        (re.compile(r'^/files/[^/]+$'), '/files/<token>'),
        (re.compile(r'^/api/v1/p/[^/]+/tools/([a-z_0-9]+)$'), '/api/v1/p/<project>/tools/{0}'),
        (re.compile(r'^/(view|edit)/[^/]+/[^/]+$'), '/{0}/<project>/<dashboard>'),
    )

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        started, status = time.perf_counter(), {'code': 0}

        async def capture(message):
            if message['type'] == 'http.response.start':
                status['code'] = message['status']
            await send(message)
        try:
            await self.app(scope, receive, capture)
        finally:
            path = scope.get('path', '')
            for pattern, template in self.TEMPLATES:
                match = pattern.match(path)
                if match:
                    path = template.format(*match.groups())
                    break
            else:
                if path.startswith('/assets/'):
                    path = '/assets/<bundle>'
            print(f"{scope.get('method', '')} {path} {status['code']} {(time.perf_counter() - started) * 1000:.0f}ms", file=sys.stderr, flush=True)


def settings_from_args(args) -> ServerSettings:
    def env(name, default=None):
        value = os.environ.get(name)
        return value if value not in (None, '') else default
    tokens = list(args.token or [])
    tokens += [item.strip() for item in (env('CHARTS_SERVER_TOKENS', '') or '').split(',') if item.strip()]
    token_file = args.token_file or env('CHARTS_SERVER_TOKEN_FILE')
    if token_file:
        tokens += [line.strip() for line in Path(token_file).expanduser().read_text().splitlines() if line.strip() and not line.startswith('#')]
    workspace = args.workspace or env('CHARTS_WORKSPACE')
    if not workspace:
        raise DashboardError('INVALID_CONFIG', 'Choose the server workspace with --workspace or CHARTS_WORKSPACE')
    runtime = args.runtime_root or env('CHARTS_RUNTIME_ROOT') or str(Path(workspace).expanduser() / '.runtime')
    secret = env('CHARTS_SERVER_SECRET')
    return ServerSettings(
        workspace=Path(workspace), runtime=Path(runtime),
        host=args.host or env('CHARTS_HOST', '127.0.0.1'), port=int(args.port or env('CHARTS_PORT', 8000)),
        public_url=args.public_url or env('CHARTS_PUBLIC_URL', ''), tokens=tuple(dict.fromkeys(tokens)),
        secret=secret.encode() if secret else b'',
        share_hours=float(args.share_ttl_hours or env('CHARTS_SHARE_TTL_HOURS', DEFAULT_SHARE_HOURS)),
        default_project=args.default_project or env('CHARTS_DEFAULT_PROJECT', 'default'),
        sources=args.sources or env('CHARTS_SOURCES'), stateless=bool(args.stateless or env('CHARTS_STATELESS')),
        allowed_hosts=tuple(args.allowed_host or [item.strip() for item in (env('CHARTS_ALLOWED_HOSTS', '') or '').split(',') if item.strip()]),
        forwarded_allow_ips=args.forwarded_allow_ips or env('CHARTS_FORWARDED_ALLOW_IPS', '127.0.0.1'),
        insecure_no_auth=bool(getattr(args, 'insecure_no_auth', False)))


class _ClosedStreamFilter:
    """Drop the SDK's benign traceback when a client closes its SSE stream first."""

    def filter(self, record):
        exc = record.exc_info[1] if record.exc_info else None
        return not (type(exc).__name__ == 'ClosedResourceError' and 'standalone SSE writer' in record.getMessage())


def serve(settings: ServerSettings):
    import logging
    logging.getLogger('mcp.server.streamable_http').addFilter(_ClosedStreamFilter())
    try:
        import uvicorn
    except ImportError as exc:
        raise DashboardError('MCP_NOT_INSTALLED', 'Install the server dependencies: python3 -m pip install "mcp>=1.28,<2"') from exc
    from .assets import bundle_assets
    bundle_assets()  # Fail early with the exact build command.
    server = RemoteServer(settings)
    app = create_app(server)
    print(json.dumps({'mcp': settings.public_url + '/mcp', 'web': settings.public_url + '/', 'workspace': str(settings.workspace),
                      'auth': 'disabled (loopback trial)' if settings.insecure_no_auth else 'bearer', 'version': __version__}, ensure_ascii=False), flush=True)
    if settings.public_url.startswith('http://') and settings.host not in ('127.0.0.1', 'localhost', '::1'):
        print('Warning: publish this server through HTTPS (reverse proxy) before sharing links; tokens travel in requests.', file=sys.stderr)
    uvicorn.run(app, host=settings.host, port=settings.port, access_log=False, log_level='warning',
                proxy_headers=True, forwarded_allow_ips=settings.forwarded_allow_ips, server_header=False)
