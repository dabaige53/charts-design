"""Local React preview and data API with bearer, Origin and Host checks."""
from __future__ import annotations
import hmac
import json
import secrets
import sys
import threading
import base64
import hashlib
import copy
from .lifecycle import IdleLifetime, DEFAULT_IDLE_TIMEOUT
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote, quote, parse_qs
from typing import cast
from .assets import export_document, render_html
from .model import MAX_BYTES, DashboardError, identifier, json_bytes, require

# Browser previews can inspect and filter a saved page, but cannot mutate its
# design, checkpoint or publication. Annotations use their own HTTP endpoint.
PREVIEW_TOOLS = frozenset({
    'dashboard_get', 'dashboard_preview', 'dashboard_list', 'dashboard_refresh',
    'dashboard_view', 'dashboard_filter_options', 'component_data', 'query_inspect',
    'semantic_inspect', 'runtime_info', 'runtime_keepalive', 'runtime_report_error',
    'dashboard_export', 'dashboard_export_read', 'dataset_export',
})
READING_TOOLS = frozenset({'dashboard_view', 'dashboard_filter_options', 'component_data',
                           'query_inspect', 'semantic_inspect', 'dashboard_export', 'dataset_export'})


def annotation_response(service, board, *, revision=None, can_annotate=False, can_manage=False, payload=None):
    """One author-workspace annotation contract for local and remote HTTP.

    The displayed revision resolves the anchor; the independently stored list
    and its CAS revision continue to come from the project's annotation store.
    No MCP transport or content version mutation participates in this path.
    """
    identifier(board)
    require(service.project_root is not None, 'Independent annotations require a project', 'PROJECT_REQUIRED')
    if revision is None:
        document = service.store.get(board, hydrate=False) if can_manage else service.store.readable(board)
    else:
        require(type(revision) is int and revision > 0, 'revision must be a positive integer', 'INVALID_ARGUMENT')
        draft = service.store.get(board, hydrate=False) if can_manage else None
        if draft is not None and draft['revision'] == revision:
            document = draft
        else:
            from .versions import Versions
            document = Versions(service.store).read(board, revision)
    if payload is not None:
        if not can_annotate:
            raise DashboardError('FORBIDDEN', 'This page does not allow annotations', 403)
        require(isinstance(payload, dict), 'Body must be an object', 'INVALID_REQUEST')
        if 'append' in payload:
            require(not {'expectedAnnotations', 'annotations'} & payload.keys(), 'Send append or a replacement list', 'INVALID_ARGUMENT')
            require(isinstance(payload['append'], dict), 'append must be an object', 'INVALID_ARGUMENT')
            name = payload.get('authorName', '')
            require(isinstance(name, str) and len(name) <= 80, 'authorName must contain at most 80 characters', 'INVALID_ARGUMENT')
            note = copy.deepcopy(payload['append'])
            # Possessing a workspace link does not verify an account identity.
            # HTTP clients cannot promote an arbitrary author object to one.
            note['author'] = {'name': name.strip() or ('作者' if can_manage else '访客'), 'verified': False}
            result = service.store.append_annotation(board, note, context_document=document)
        else:
            if not can_manage:
                raise DashboardError('FORBIDDEN', 'This preview can add annotations but cannot manage them', 403)
            require(isinstance(payload.get('expectedAnnotations'), list), 'expectedAnnotations must be an array', 'INVALID_ARGUMENT')
            expected = payload.get('expectedRevision', service.store.revision(board))
            require(type(expected) is int and expected > 0, 'expectedRevision must be a positive integer', 'INVALID_ARGUMENT')
            result = service.store.update_annotations(board, expected, payload['expectedAnnotations'],
                                                       copy.deepcopy(payload.get('annotations')))
        return {**result, 'targetRevision': document['revision']}
    result = service.call('dashboard_annotations', {'dashboardId': board, 'includeTargets': False})
    targets = {}
    for note in result['annotations']:
        component_id = note.get('componentId')
        target = {'scope': note.get('anchor', {}).get('scope', 'component' if component_id else 'page')}
        if component_id:
            component = document['manifest']['components'].get(component_id)
            target.update({'sourcePath': 'manifest.components.' + component_id, 'componentExists': component is not None})
            if component:
                target.update({'title': component.get('title', ''), 'kind': component['kind']})
        else:
            target['sourcePath'] = ('manifest.report.markdown' if document['manifest'].get('viewMode') in
                                    ('report', 'filtered-report') else 'manifest')
        targets[note['id']] = target
    return {**result, 'targetRevision': document['revision'], 'targets': targets, 'targetsResolved': True,
            'canRead': True, 'canAnnotate': bool(can_annotate), 'canManageAnnotations': bool(can_manage),
            'author': {'name': '作者' if can_manage else '访客', 'verified': False}}

class RuntimeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, service, port=8765, token=None, idle_timeout: float=DEFAULT_IDLE_TIMEOUT, lifetime=None):
        self.lifetime = lifetime or IdleLifetime(idle_timeout)
        self.service, self.token = service, token or secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1', port), Handler)

    def preview_token(self, board):
        encoded = base64.urlsafe_b64encode(identifier(board).encode()).rstrip(b'=').decode()
        signature = hmac.new(self.token.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        return 'view.' + encoded + '.' + signature

    def principal(self, token):
        if isinstance(token, str) and hmac.compare_digest(token.encode(), self.token.encode()):
            return 'edit', None
        try:
            prefix, encoded, signature = token.split('.')
            board = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).decode()
            if prefix == 'view' and hmac.compare_digest(token, self.preview_token(board)):
                return 'view', board
        except (ValueError, TypeError, UnicodeError, DashboardError):
            pass
        return None

    def browser_links(self, board):
        self.service.store.revision(board)
        base = f'http://127.0.0.1:{self.server_port}'
        return {'editUrl': base + '/edit/' + quote(board) + '#token=' + self.token,
                'viewUrl': base + '/view/' + quote(board) + '#token=' + self.preview_token(board)}

    def serve_forever(self, poll_interval=0.5):
        stopped = threading.Event()
        def watch_idle():
            while not stopped.wait(min(1, self.lifetime.timeout / 4)):
                if self.lifetime.expired():
                    print('Local preview closed after idle timeout', file=sys.stderr)
                    self.shutdown()
                    return
        watcher = threading.Thread(target=watch_idle, daemon=True)
        watcher.start()
        try:
            super().serve_forever(poll_interval)
        finally:
            stopped.set()
            watcher.join()

class Handler(BaseHTTPRequestHandler):
    @property
    def runtime(self) -> RuntimeHTTPServer:
        return cast(RuntimeHTTPServer, self.server)
    server_version = 'ChartsRuntime/0.1'
    def handle_one_request(self):
        with self.runtime.lifetime.activity():
            super().handle_one_request()
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format, *args):
        # Never log credentials, payloads, or query parameters.
        print(f'[{self.command}] {urlparse(self.path).path}', file=sys.stderr)

    def send(self, body, status=200, content_type='application/json'):
        raw = body.encode() if isinstance(body, str) else json_bytes(body)
        self.send_response(status)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.end_headers()
        self.wfile.write(raw)

    def check(self, authenticated=True):
        port = self.runtime.server_port
        allowed = {f'127.0.0.1:{port}', f'localhost:{port}'}
        host = self.headers.get('Host', '')
        if host not in allowed:
            raise DashboardError('INVALID_HOST', 'Unexpected Host header', 403)
        origin = self.headers.get('Origin')
        if origin and origin not in {f'http://{value}' for value in allowed}:
            raise DashboardError('INVALID_ORIGIN', 'Cross-origin access is disabled', 403)
        principal = self.runtime.principal(self.headers.get('Authorization', '').removeprefix('Bearer '))
        if authenticated and principal is None:
            raise DashboardError('UNAUTHORIZED', 'Open the token-bearing URL printed by the local server', 401)
        return principal

    def scoped_board(self, board, principal):
        identifier(board)
        if principal[1] is not None and principal[1] != board:
            raise DashboardError('FORBIDDEN', 'This preview is limited to another dashboard', 403)
        return board

    def read_body(self):
        if self.headers.get_content_type() != 'application/json':
            raise DashboardError('CONTENT_TYPE', 'Use application/json', 415)
        length = int(self.headers.get('Content-Length', '0'))
        if length <= 0 or length > MAX_BYTES:
            raise DashboardError('PAYLOAD_TOO_LARGE', 'Body must contain 1 byte to 16 MiB', 413)
        args = json.loads(self.rfile.read(length))
        require(isinstance(args, dict), 'Body must be an object', 'INVALID_REQUEST')
        return args

    def fail(self, error):
        if isinstance(error, DashboardError):
            self.send(error.as_dict(), error.status)
        elif isinstance(error, (KeyError, TypeError, ValueError)):
            self.send({'ok': False, 'error': {'code': 'INVALID_REQUEST', 'message': str(error)}}, 400)
        else:
            print(type(error).__name__, file=sys.stderr)
            self.send({'ok': False, 'error': {'code': 'INTERNAL_ERROR', 'message': 'Request failed; inspect server logs'}}, 500)

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            principal = self.check(authenticated=path.startswith('/api/'))
            if path == '/' or path.startswith(('/edit/', '/view/')):
                board = unquote(path.split('/', 2)[2]) if path != '/' else None
                if board is not None:
                    self.runtime.service.store.revision(identifier(board))
                read_only = path.startswith('/view/')
                project = str(self.runtime.service.project_root) if self.runtime.service.project_root else None
                self.send(render_html('web', idle_timeout=self.runtime.lifetime.timeout,
                                      boot_state={'projectRoot': project, 'dashboardId': board, 'readOnly': read_only,
                                                  'annotationAccess': {'endpoint': '/api/annotations/{dashboardId}',
                                                    'canRead': bool(project), 'canAnnotate': bool(project),
                                                    'canManageAnnotations': bool(project) and not read_only,
                                                    'scope': project or 'legacy'},
                                                  'browserLinksEndpoint': '/api/browser-links/{dashboardId}',
                                                  'publicationApiBase': '/api/publications/'}), content_type='text/html')
            elif path == '/health':
                self.send({'ok': True})
            elif path.startswith('/api/browser-links/'):
                board = self.scoped_board(unquote(path.removeprefix('/api/browser-links/')), principal)
                links = self.runtime.browser_links(board)
                self.send(links if principal[0] == 'edit' else {'viewUrl': links['viewUrl']})
            elif path.startswith('/api/annotations/'):
                board = self.scoped_board(unquote(path.removeprefix('/api/annotations/')), principal)
                revision = parse_qs(parsed.query).get('revision', [None])[0]
                self.send(annotation_response(self.runtime.service, board,
                          revision=int(revision) if revision is not None else None,
                          can_annotate=True, can_manage=principal[0] == 'edit'))
            elif path.startswith('/api/publications/') and path.endswith('/feedback'):
                if principal[0] != 'edit':
                    raise DashboardError('FORBIDDEN', 'Author access is required to read share feedback', 403)
                from .local_shares import LocalShares
                params = parse_qs(parsed.query)
                board = self.scoped_board(params.get('dashboardId', [None])[0], principal)
                share_id = unquote(path.removeprefix('/api/publications/').removesuffix('/feedback'))
                self.send(LocalShares(self.runtime.service).feedback(board, share_id))
            elif path.startswith('/api/export/'):
                store = self.runtime.service.store
                board = self.scoped_board(unquote(path.removeprefix('/api/export/')), principal)
                doc = store.hydrate(store.readable(board) if principal[0] == 'view' and self.runtime.service.project_root
                                    else store.get(board, hydrate=False))
                self.send(export_document(doc), content_type='text/html')
            else:
                raise DashboardError('NOT_FOUND', 'Unknown endpoint', 404)
        except Exception as exc:
            self.fail(exc)

    def do_POST(self):
        try:
            principal = self.check()
            path = urlparse(self.path).path
            args = self.read_body()
            if path.startswith('/api/annotations/'):
                board = self.scoped_board(unquote(path.removeprefix('/api/annotations/')), principal)
                self.send(annotation_response(self.runtime.service, board, revision=args.get('revision'),
                          can_annotate=True, can_manage=principal[0] == 'edit', payload=args))
                return
            if not path.startswith('/api/tools/'):
                raise DashboardError('NOT_FOUND', 'Unknown endpoint', 404)
            name = path.removeprefix('/api/tools/')
            if principal[0] != 'edit':
                if name not in PREVIEW_TOOLS:
                    raise DashboardError('FORBIDDEN', 'This preview cannot change content or versions', 403)
                if 'dashboardId' in args:
                    self.scoped_board(args['dashboardId'], principal)
                elif name not in ('dashboard_list', 'runtime_info', 'runtime_keepalive', 'runtime_report_error'):
                    args['dashboardId'] = principal[1]
                if name == 'dashboard_get':
                    name = 'dashboard_preview'
                if name in READING_TOOLS and self.runtime.service.project_root:
                    args.setdefault('expectedRevision', self.runtime.service.store.readable(principal[1])['revision'])
            result = self.runtime.service.call(name, args)
            if principal[0] != 'edit' and name == 'dashboard_list':
                result['dashboards'] = [item for item in result['dashboards'] if item['id'] == principal[1]]
            if path == '/api/tools/dashboard_preview':
                result['projectRoot'] = str(self.runtime.service.project_root) if self.runtime.service.project_root else None
            self.send(result)
        except Exception as exc:
            self.fail(exc)

    def do_OPTIONS(self):
        self.send({'error': 'Cross-origin access is disabled'}, 405)
