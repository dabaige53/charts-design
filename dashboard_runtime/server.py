"""Self-hosted server: Streamable HTTP MCP, browser previews and signed downloads.

One long-running process serves four audiences from the same project storage
and the same transport-independent ``Service``:

* MCP clients (Claude Code, Claude Desktop, Codex, IDEs) on ``/mcp`` with a
  bearer token, or ``/mcp/<token>`` for clients that cannot send headers.
* Browser readers on ``/view/<project>/<dashboard>`` (read-only) and
  ``/edit/<project>/<dashboard>`` (layout/title editing). Pages load the shared
  UI bundle and read data through a scoped API using an expiring signed token
  carried in the URL fragment, which browsers never send to servers or proxies.
* Downloads of exports through signed, expiring ``/files/<token>`` links.
* Separate Tencent COS publications on ``/s/<shareId>/``, gated by an
  eight-digit visitor key. Expired copies are removed by cloud SCF, not this process.

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
import mimetypes
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
from urllib.parse import parse_qs, quote, urlparse

from . import __version__
from .model import ID, DashboardError, MAX_BYTES, require
from .service import TOOLS, Service
from .tool_contract import BOARD, described, schema as tool_schema
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
    'dashboard_annotations', 'dashboard_list', 'dashboard_preview', 'runtime_info', 'runtime_keepalive',
    'runtime_report_error', 'dashboard_export', 'dashboard_export_read', 'dataset_export', 'legacy_render',
})
# An edit link additionally saves layout, titles, descriptions and checkpoints.
EDIT_TOOLS = VIEW_TOOLS | frozenset({
    'dashboard_patch', 'dashboard_edit_begin', 'dashboard_edit_finish', 'dashboard_checkpoint',
    'dashboard_validate', 'dashboard_doctor', 'dashboard_history', 'dashboard_history_diff',
    'dashboard_restore', 'dashboard_version_label', 'runtime_diagnostics', 'dashboard_export_site',
    'dashboard_version_status', 'dashboard_version_get', 'dashboard_version_publish',
    'dashboard_share_status', 'dashboard_share_publish', 'dashboard_share_delete', 'dashboard_share_replace',
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
        from .cloud_database import cloud_enabled
        if cloud_enabled():
            require(bool(self.secret), 'Cloud storage requires a stable CHARTS_SERVER_SECRET', 'INVALID_CONFIG')
            self.stateless = True
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
        from .cloud_database import CloudDatabase, cloud_enabled
        self.database = CloudDatabase() if cloud_enabled() else None
        if self.database is not None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), timeout=10, isolation_level=None, check_same_thread=False)
        self._db.execute('CREATE TABLE IF NOT EXISTS share_generations (project TEXT, dashboard TEXT, generation INTEGER, PRIMARY KEY(project, dashboard))')

    def generation(self, project, dashboard) -> int:
        if self.database is not None:
            return self.database.call('generation', project, board=dashboard)
        with self._lock:
            row = self._db.execute('SELECT generation FROM share_generations WHERE project=? AND dashboard=?', (project, dashboard)).fetchone()
        return row[0] if row else 0

    def revoke(self, project, dashboard) -> int:
        if self.database is not None:
            return self.database.call('revoke', project, board=dashboard)
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
        from .cloud_database import CloudDatabase, cloud_enabled
        if cloud_enabled():
            return name in CloudDatabase().call('projects')
        return PROJECT_NAME.fullmatch(name or '') is not None and (self.settings.workspace / name / 'charts-project.json').is_file()

    def names(self) -> list[str]:
        from .cloud_database import CloudDatabase, cloud_enabled
        if cloud_enabled():
            return CloudDatabase().call('projects')
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
            'dashboard_share': ('Create an expiring browser link to the saved dashboard/report checkpoint; does not deploy a site or finish draft edits. '
                                'Returns url/access/expiresAt; the URL contains an access token. Share only when requested. '
                                'view permits reading; edit also permits the supported viewer edits. Repeated calls issue new links. '
                                'For eight-digit visitor keys, never/7d/30d and physical expiry deletion use dashboard_share_publish instead; this signed-link tool does not delete stored data.',
                                tool_schema({'dashboardId': BOARD['dashboardId'],
                                    'access': described({'enum': ['view', 'edit'], 'default': 'view'},
                                        'Permission granted by this link; use edit only when the user requested editing access.'),
                                    'expiresInHours': described({'type': 'number', 'minimum': 1, 'maximum': 8784},
                                        'Link lifetime in hours; omit to use the operator-configured server default.')}, ('dashboardId',))),
            'dashboard_share_revoke': ('Revoke every previously issued browser share link for this dashboard/report; all those readers lose access. '
                                      'Does not delete the dashboard or revoke unrelated export download links. '
                                      'Returns revoked=true and generation. Call only for the requested dashboard; use dashboard_share for a new link. '
                                      'To remove a Tencent COS publication use dashboard_share_delete with its shareId instead.',
                                      tool_schema({'dashboardId': BOARD['dashboardId']}, ('dashboardId',))),
        }

    def projects(self, service):
        return self.workspace

    def describe(self, name, description):
        if name in ('dashboard_export', 'dataset_export'):
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
        self.cloud_shares = None
        if os.environ.get('CHARTS_COS_BUCKET'):
            from .cloud_shares import CloudShares
            self.cloud_shares = CloudShares.from_environment()
        self._cloud_attempts = {}
        self._cloud_attempts_lock = threading.Lock()

    def cloud_key_attempt(self, share_id, peer):
        """Bound online guessing of the deliberately short visitor access key."""
        now = time.time()
        with self._cloud_attempts_lock:
            self._cloud_attempts = {key: value for key, value in self._cloud_attempts.items() if value[1] > now}
            for key, limit in (((share_id, peer), 5), ((share_id, '*'), 100)):
                attempts, until = self._cloud_attempts.get(key, (0, now + 900))
                require(attempts < limit, '尝试次数过多，请 15 分钟后重试', 'SHARE_RATE_LIMITED')
            for key in ((share_id, peer), (share_id, '*')):
                attempts, until = self._cloud_attempts.get(key, (0, now + 900))
                self._cloud_attempts[key] = (attempts + 1, until)

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
        if not any(target.is_relative_to(base) for base in allowed):
            return None
        from .cloud_database import cloud_enabled
        if cloud_enabled() and not target.is_file():
            from .cloud_files import CloudFiles
            if not CloudFiles().restore(payload['p'], target.relative_to(root).as_posix(), target):
                return None
        if not target.is_file():
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


def create_app(server: RemoteServer):
    """Starlette ASGI application. Starlette and uvicorn ship with the MCP SDK."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import FileResponse, JSONResponse, Response
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
        payload: dict[str, object] = {'ok': True, 'version': __version__}
        if os.environ.get('CHARTS_RELEASE_VERSION'):
            payload['release'] = {
                'version': os.environ['CHARTS_RELEASE_VERSION'],
                'commit': os.environ.get('CHARTS_RELEASE_COMMIT', ''),
            }
        return JSONResponse(payload, headers={'Cache-Control': 'no-store'})

    async def viewer(request: Request):
        from .assets import render_html
        try:
            project = request.path_params.get('project', settings.default_project)
            require(PROJECT_NAME.fullmatch(project) is not None, 'Invalid project name')
            dashboard = request.path_params.get('dashboard')
            if dashboard:
                require(re.fullmatch(ID, dashboard) is not None, 'Invalid dashboard ID')
            boot = {'mode': 'web', 'projectRoot': project, 'dashboardId': dashboard,
                    'apiBase': base + '/api/v1/p/' + quote(project) + '/tools/',
                    'readOnly': request.url.path.startswith(base + '/view/'), 'idleTimeout': None}
            return compressed(request, render_html(boot_state=boot).encode(), 'text/html', {'Cache-Control': 'no-store'})
        except DashboardError as error:
            return failure(error)

    async def asset(request: Request):
        from .assets import bundle_assets
        name = request.path_params['name']
        if name not in ('app.js', 'app.css'):
            return JSONResponse({'error': 'not found'}, status_code=404)
        try:
            return compressed(request, bundle_assets()[name], 'text/javascript' if name.endswith('.js') else 'text/css',
                              {'Cache-Control': 'no-cache'})
        except DashboardError as error:
            return failure(error)

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

    async def cloud_publication(request: Request):
        """Every file stays behind key/session and expiry checks; no public COS URLs."""
        from .cloud_shares import checked_id
        from starlette.responses import RedirectResponse

        def access_form(path, message='', status=200):
            nonce = secrets.token_urlsafe(18)
            error = ('<p id="key-error" class="error" role="alert">' + html.escape(message) + '</p>') if message else ''
            described_by = 'key-hint key-error' if message else 'key-hint'
            invalid = ' aria-invalid="true"' if status == 401 else ''
            page = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>访问分享 · Charts Design</title><style nonce="' + nonce + '">' + """
                :root{color-scheme:light;--canvas:#f5f5f4;--surface:#fff;--ink:#1c1917;
                    --muted:#57534e;--border:#d6d3d1;--primary:#123b5d;--focus:#2c6485;--error:#b42318}
                *{box-sizing:border-box}
                body{margin:0;background:var(--canvas);color:var(--ink);
                    font:400 14px/1.6 'Inter Variable',Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
                ::selection{background:var(--primary);color:#fff}
                main{min-height:100vh;min-height:100svh;display:grid;place-items:center;padding:32px 20px}
                .access{width:100%;max-width:420px;padding:36px;background:var(--surface);
                    border:1px solid var(--border);border-radius:8px}
                h1{font-size:20px;line-height:1.4;font-weight:600;margin:0 0 8px;text-wrap:balance}
                .intro{margin:0 0 28px;color:var(--muted)}
                label{display:block;font-size:13px;font-weight:600;margin-bottom:8px}
                input{width:100%;height:48px;padding:10px 14px;border:1px solid var(--border);
                    border-radius:0;background:var(--surface);color:var(--ink);font:inherit;font-size:16px;
                    font-variant-numeric:tabular-nums;letter-spacing:.2em;caret-color:var(--primary)}
                input:hover{border-color:var(--muted)}
                input[aria-invalid=true]{border-color:var(--error)}
                input:focus-visible,button:focus-visible,a:focus-visible{outline:2px solid var(--focus);outline-offset:3px}
                .hint{margin:8px 0 24px;color:var(--muted);font-size:12px}
                .error{margin:0 0 20px;padding:12px;background:var(--canvas);color:var(--error);overflow-wrap:anywhere}
                button{width:100%;min-height:44px;padding:10px 16px;border:0;border-radius:0;
                    background:var(--primary);color:#fff;font:inherit;font-weight:600;cursor:pointer}
                button:hover{background:var(--focus)}button:active{background:#051c2c}
                .footer{margin:24px 0 0;color:var(--muted);font-size:12px;text-align:center}
                .retry{display:block;margin:16px 0 0;text-align:center;color:var(--primary);text-underline-offset:3px}
                @media(max-width:480px){main{padding:20px 16px}.access{padding:28px 24px}}
                """ + '</style></head><body><main><section class="access" aria-labelledby="access-title">'
                    '<h1 id="access-title">访问分享</h1>'
                    '<p class="intro">输入分享者提供的密钥，即可查看页面。</p>' + error +
                    '<form method="post" action="' + html.escape(path, quote=True) + '">'
                    '<label for="access-key">8 位数字访问密钥</label>'
                    '<input id="access-key" name="accessKey" type="password" inputmode="numeric" '
                    'pattern="[0-9]{8}" minlength="8" maxlength="8" required autocomplete="off" '
                    'aria-describedby="' + described_by + '"' + invalid + '>'
                    '<p class="hint" id="key-hint" aria-live="polite">可直接粘贴密钥，包含开头的 0。</p>'
                    '<button type="submit">打开分享</button></form>' +
                    ('<a class="retry" href="' + html.escape(path, quote=True) + '">重新打开分享</a>' if status == 403 else '') +
                    '<p class="footer">Charts Design · 私密分享</p></section></main>'
                    '<script nonce="' + nonce + '">' + """
                const key = new URLSearchParams(location.hash.slice(1)).get('key');
                if (key !== null) {
                    history.replaceState(null, '', location.pathname + location.search);
                    if (/^[0-9]{8}$/.test(key)) {
                        document.getElementById('access-key').value = key;
                        document.getElementById('key-hint').textContent = '密钥已从分享链接填入，点击下方按钮即可查看。';
                    }
                }
                """ + '</script></body></html>')
            headers = {**SECURITY_HEADERS, 'Cache-Control': 'no-store',
                       # no-referrer makes a browser's native form POST send Origin: null.
                       # Keep the same-origin form identifiable without leaking cross-site referrers.
                       'Referrer-Policy': 'same-origin',
                       'Content-Security-Policy': "default-src 'none'; style-src 'nonce-" + nonce +
                           "'; script-src 'nonce-" + nonce +
                           "'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"}
            if status == 429:
                headers['Retry-After'] = '900'
            return Response(page, status_code=status, media_type='text/html', headers=headers)

        try:
            shares = server.cloud_shares
            if shares is None:
                raise DashboardError('CLOUD_SHARE_NOT_CONFIGURED', '云端分享未配置')
            share_id = checked_id(request.path_params['share_id'])
            control = await asyncio.to_thread(shares.control, share_id)
            path = base + '/s/' + share_id + '/'
            cookie = 'charts-share-' + share_id
            if request.method == 'POST':
                origin = request.headers.get('origin')
                public = urlparse(settings.public_url)
                require(origin is None or origin == public.scheme + '://' + public.netloc,
                        'Invalid form origin', 'FORBIDDEN')
                peer = request.client.host if request.client else 'unknown'
                server.cloud_key_attempt(share_id, peer)
                body = await read_body(request, 1024)
                values = parse_qs(body.decode('utf-8'), max_num_fields=4)
                await asyncio.to_thread(shares.authenticate, share_id, values.get('accessKey', [''])[0])
                expiry = min(int(time.time()) + 12 * 3600, control['expiresAt'] or int(time.time()) + 12 * 3600)
                token = server.signer.sign({'k': 'cloud-share', 'shareId': share_id, 'exp': expiry})
                response = RedirectResponse(path, status_code=303,
                                            headers={**SECURITY_HEADERS, 'Cache-Control': 'no-store'})
                response.set_cookie(cookie, token, max_age=max(0, expiry - int(time.time())),
                                    path=path, secure=True, httponly=True, samesite='strict')
                return response
            session = server.signer.verify(request.cookies.get(cookie), 'cloud-share')
            authorized = session is not None and session.get('shareId') == share_id
            name = request.path_params.get('name') or 'index.html'
            if not authorized:
                require(name == 'index.html', '请先输入访问密钥', 'INVALID_ACCESS_KEY')
                return access_form(path)
            raw = await asyncio.to_thread(shares.content, share_id, name, control=control)
            kind = 'application/gzip' if name.endswith('.gz') else mimetypes.guess_type(name)[0] or 'application/octet-stream'
            return compressed(request, raw, kind, {
                'Cache-Control': 'private, no-store, max-age=0',
                # Custom HTML retains its existing opaque iframe sandbox and
                # child CSP, including explicitly supported HTTPS resources.
                'Content-Security-Policy': "frame-ancestors 'none'; base-uri 'self'; object-src 'none'",
            })
        except DashboardError as error:
            status = {'INVALID_ACCESS_KEY': 401, 'SHARE_RATE_LIMITED': 429,
                      'SHARE_EXPIRED': 410, 'SHARE_UNAVAILABLE': 410, 'NOT_FOUND': 404,
                      'FORBIDDEN': 403}.get(error.code, 400)
            if request.method == 'POST' and error.code in ('INVALID_ACCESS_KEY', 'SHARE_RATE_LIMITED', 'FORBIDDEN'):
                message = '无法验证本次访问来源。请重新打开分享后输入密钥。' if error.code == 'FORBIDDEN' else str(error)
                return access_form(base + '/s/' + request.path_params['share_id'] + '/', message, status)
            return JSONResponse(error.as_dict(), status_code=status,
                                headers={**SECURITY_HEADERS, 'Cache-Control': 'no-store'})
        except Exception as error:
            return failure(error)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            yield

    routes = [
        Route('/health', health, methods=['GET', 'HEAD']),
        Route('/', viewer, methods=['GET']),
        Route('/assets/{name}', asset, methods=['GET']),
        Route('/view/{project}/{dashboard}', viewer, methods=['GET']),
        Route('/edit/{project}/{dashboard}', viewer, methods=['GET']),
        Route('/api/v1/p/{project}/tools/{name}', tool, methods=['POST']),
        Route('/api/v1/catalog', admin_catalog, methods=['POST']),
        Route('/api/v1/share', admin_share, methods=['POST']),
        Route('/files/{token}', download, methods=['GET']),
        Route('/s/{share_id}/', cloud_publication, methods=['GET', 'POST']),
        Route('/s/{share_id}/{name:path}', cloud_publication, methods=['GET']),
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
        (re.compile(r'^/s/[^/]+/.*$'), '/s/<share>/<file>'),
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
    server = RemoteServer(settings)
    app = create_app(server)
    print(json.dumps({'mcp': settings.public_url + '/mcp', 'uiStatus': 'unavailable', 'workspace': str(settings.workspace),
                      'auth': 'disabled (loopback trial)' if settings.insecure_no_auth else 'bearer', 'version': __version__}, ensure_ascii=False), flush=True)
    if settings.public_url.startswith('http://') and settings.host not in ('127.0.0.1', 'localhost', '::1'):
        print('Warning: publish this server through HTTPS (reverse proxy) before sharing links; tokens travel in requests.', file=sys.stderr)
    uvicorn.run(app, host=settings.host, port=settings.port, access_log=False, log_level='warning',
                proxy_headers=True, forwarded_allow_ips=settings.forwarded_allow_ips, server_header=False)
