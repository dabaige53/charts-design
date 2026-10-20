"""Local web editor. Bearer token + Origin/Host checks, no permissive CORS."""
from __future__ import annotations
import hmac
import json
import secrets
import sys
import threading
from .lifecycle import IdleLifetime, DEFAULT_IDLE_TIMEOUT
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote
from typing import cast
from .assets import export_document, render_html
from .model import MAX_BYTES, DashboardError, json_bytes

class RuntimeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, service, port=8765, token=None, idle_timeout: float=DEFAULT_IDLE_TIMEOUT):
        self.lifetime = IdleLifetime(idle_timeout)
        self.service, self.token = service, token or secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1', port), Handler)

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
        if authenticated and not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + self.runtime.token):
            raise DashboardError('UNAUTHORIZED', 'Open the token-bearing URL printed by the local server', 401)

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
            path = urlparse(self.path).path
            self.check(authenticated=path.startswith('/api/'))
            if path == '/':
                self.send(render_html('web', idle_timeout=self.runtime.lifetime.timeout), content_type='text/html')
            elif path == '/health':
                self.send({'ok': True})
            elif path.startswith('/api/export/'):
                store = self.runtime.service.store
                doc = store.hydrate(store.get(unquote(path.removeprefix('/api/export/')), hydrate=False))
                self.send(export_document(doc), content_type='text/html')
            else:
                raise DashboardError('NOT_FOUND', 'Unknown endpoint', 404)
        except Exception as exc:
            self.fail(exc)

    def do_POST(self):
        try:
            self.check()
            path = urlparse(self.path).path
            if not path.startswith('/api/tools/'):
                raise DashboardError('NOT_FOUND', 'Unknown endpoint', 404)
            if self.headers.get_content_type() != 'application/json':
                raise DashboardError('CONTENT_TYPE', 'Use application/json', 415)
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > MAX_BYTES:
                raise DashboardError('PAYLOAD_TOO_LARGE', 'Body must contain 1 byte to 16 MiB', 413)
            args = json.loads(self.rfile.read(length))
            result = self.runtime.service.call(path.removeprefix('/api/tools/'), args)
            self.send(result)
        except Exception as exc:
            self.fail(exc)

    def do_OPTIONS(self):
        self.send({'error': 'Cross-origin access is disabled'}, 405)
