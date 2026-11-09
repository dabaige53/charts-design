"""Smoke-test the self-hosted server as deployed: a built image or a running URL.

    python3 tests/deploy/container_smoke.py --image charts-design:ci
    python3 tests/deploy/container_smoke.py --url http://127.0.0.1:8000 --token <token>

Exercises the deployment surface end to end with the standard library only:
health, bearer enforcement, MCP over Streamable HTTP (initialize, tools/list,
authoring a dashboard through an edit batch, preview), the preview page and
its cached bundle, the scoped viewer API and a signed export download. With
--image it also checks the container runs as a non-root user.
"""
from __future__ import annotations

import argparse
import base64
import json
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

PROJECT, BOARD = 'smoke', 'ops'


def http(method, url, body=None, headers=None, timeout=60):
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


class Mcp:
    """Minimal JSON-RPC client for Streamable HTTP (JSON or SSE replies)."""

    def __init__(self, base, token):
        self.url, self.token, self.session, self.protocol, self.counter = base + '/mcp', token, None, None, 0

    def post(self, message):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
                   'Authorization': 'Bearer ' + self.token}
        if self.session:
            headers['Mcp-Session-Id'] = self.session
        if self.protocol:
            headers['MCP-Protocol-Version'] = self.protocol
        status, headers, raw = http('POST', self.url, message, headers)
        self.session = headers.get('mcp-session-id') or self.session
        return status, headers, raw

    def request(self, method, params=None):
        self.counter += 1
        message = {'jsonrpc': '2.0', 'id': self.counter, 'method': method, 'params': params or {}}
        status, headers, raw = self.post(message)
        check(status == 200, f'{method} returned HTTP {status}: {raw[:300]!r}')
        text = raw.decode()
        if 'text/event-stream' in (headers.get('content-type') or ''):
            replies = [json.loads(line[5:]) for line in text.splitlines() if line.startswith('data:') and line[5:].strip()]
            reply = next(item for item in replies if item.get('id') == message['id'])
        else:
            reply = json.loads(text)
        check('error' not in reply, f'{method} failed: {reply.get("error")}')
        return reply['result']

    def notify(self, method):
        status, _, raw = self.post({'jsonrpc': '2.0', 'method': method})
        check(status in (200, 202), f'{method} returned HTTP {status}: {raw[:200]!r}')

    def tool(self, name, arguments):
        result = self.request('tools/call', {'name': name, 'arguments': {'projectRoot': PROJECT, **arguments}})
        value = result.get('structuredContent') or json.loads(result['content'][0]['text'])
        check(not result.get('isError'), f'{name} failed: {value}')
        envelope = value.get('transport') if isinstance(value, dict) else None
        if envelope:  # Large results arrive as base64 pages; reassemble them.
            pages = [self.tool('runtime_result_chunk', {'requestId': envelope['requestId'], 'index': index})['data']
                     for index in range(envelope['chunks'])]
            raw = base64.b64decode(''.join(pages))
            check(len(raw) == envelope['bytes'], f'{name}: chunked result size mismatch')
            value = json.loads(raw)
        return value


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def wait_healthy(base, seconds=90):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            status, _, raw = http('GET', base + '/health', timeout=5)
            if status == 200 and json.loads(raw).get('ok'):
                return
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise AssertionError(f'{base}/health did not become healthy within {seconds}s')


# @wu-test type=integration | scope=部署镜像 | protects=部署后鉴权失效或编辑批次失败或只读链接可写或部署包缺源码
def run_checks(base, token):
    wait_healthy(base)
    status, _, _ = http('POST', base + '/mcp', {}, {'Content-Type': 'application/json'})
    check(status == 401, f'/mcp without a token returned {status}, expected 401')
    print('ok  health and bearer enforcement')

    client = Mcp(base, token)
    info = client.request('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                         'clientInfo': {'name': 'container-smoke', 'version': '1'}})
    client.protocol = info.get('protocolVersion')
    client.notify('notifications/initialized')
    names = {tool['name'] for tool in client.request('tools/list')['tools']}
    check({'dashboard_share', 'dashboard_preview', 'layout_templates', 'chart_recommend'} <= names, 'expected server tools are missing')
    check('dashboard_export_open' not in names, 'desktop-only tool is exposed remotely')
    print(f'ok  MCP initialize ({client.protocol}) and {len(names)} tools')

    outside = client.request('tools/call', {'name': 'dashboard_list', 'arguments': {'projectRoot': '/etc'}})
    check(outside.get('isError'), 'a path outside the workspace was accepted')
    operations = client.tool('generation_examples', {'caseId': 'operations-scorecard'})['operations']
    revision = client.tool('dashboard_create', {'dashboardId': BOARD, 'title': 'Smoke'})['document']['revision']
    batch = client.tool('dashboard_edit_begin', {'dashboardId': BOARD, 'expectedRevision': revision})
    revision = client.tool('dashboard_patch', {'dashboardId': BOARD, 'expectedRevision': revision, 'operations': operations})['document']['revision']
    finished = client.tool('dashboard_edit_finish', {'dashboardId': BOARD, 'expectedRevision': revision, 'batchId': batch['batch_id']})
    check(finished.get('ok'), f'edit batch failed Doctor checks: {finished.get("doctor")}')
    preview = client.tool('dashboard_preview', {'dashboardId': BOARD})
    check(len(preview['document']['manifest']['components']) == 10, 'authored dashboard is incomplete')
    print(f'ok  authored {BOARD!r} through an edit batch (revision {revision})')

    link = preview['previewUrl']
    page_url, share = link.split('#token=')
    path = urlparse(page_url).path
    status, headers, page = http('GET', base + path)
    check(status == 200 and b'/assets/app.' in page, f'preview page returned {status}')
    check("script-src 'self' 'sha256-" in (headers.get('content-security-policy') or ''), 'preview page has no CSP')
    asset = page.decode().split('src="')[-1].split('"')[0]
    status, headers, _ = http('GET', base + asset, headers={'Accept-Encoding': 'gzip'})
    check(status == 200 and headers.get('content-encoding') == 'gzip' and 'immutable' in (headers.get('cache-control') or ''),
          'bundle is not served compressed and immutable')
    print('ok  preview page, CSP and cached bundle')

    api = f'{base}/api/v1/p/{PROJECT}/tools/'
    viewer = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + share}
    status, _, raw = http('POST', api + 'dashboard_view', {'dashboardId': BOARD}, viewer)
    check(status == 200 and len(json.loads(raw)['document']['computed']['components']) >= 9, f'viewer read returned {status}')
    status, _, _ = http('POST', api + 'dashboard_patch', {'dashboardId': BOARD, 'expectedRevision': revision, 'operations': [{'op': 'set_title', 'value': 'x'}]}, viewer)
    check(status == 403, f'read-only link could write (HTTP {status})')
    export = client.tool('dashboard_export', {'dashboardId': BOARD, 'format': 'json'})['export']
    status, _, raw = http('GET', export['downloadUrl'].replace(urlparse(export['downloadUrl']).netloc, urlparse(base).netloc))
    check(status == 200 and json.loads(raw)['id'] == BOARD, f'signed download returned {status}')
    print('ok  scoped viewer API and signed download')
    site = client.tool('dashboard_export_site', {'dashboardId': BOARD})['export']
    status, _, raw = http('GET', site['siteDownloadUrl'])
    check(status == 200 and raw.startswith(b'PK'), 'standalone site export is missing runtime build inputs')
    print('ok  standalone site export')


# @wu-test type=boundary | scope=Docker镜像内容 | protects=构建上下文中的令牌配置或业务目录被带入运行镜像
def check_image_files(container):
    forbidden = ('deploy/charts.env', '.env', 'dashboard_runtime/.env', 'runtime-ui/local.env', '.git', '.codex', '.aws', 'boards')
    probe = subprocess.run(
        ['docker', 'exec', container, 'python', '-c',
         'import json,pathlib,sys; print(json.dumps([p for p in sys.argv[1:] if (pathlib.Path("/app")/p).exists()]))',
         *forbidden], check=True, capture_output=True, text=True,
    )
    check(json.loads(probe.stdout) == [], 'runtime image contains private build inputs: ' + probe.stdout.strip())
    print('ok  image excludes environment files and local workspaces')


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description='Smoke-test the self-hosted server as deployed: a built image or a running URL.')
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--image', help='Docker image to run and test')
    target.add_argument('--url', help='Base URL of a running server')
    parser.add_argument('--token', help='Server token (required with --url)')
    args = parser.parse_args()
    if args.url:
        check(bool(args.token), '--token is required with --url')
        run_checks(args.url.rstrip('/'), args.token)
        return 0
    token, port = secrets.token_urlsafe(32), free_port()
    base = f'http://127.0.0.1:{port}'
    container = subprocess.run(['docker', 'run', '-d', '-p', f'127.0.0.1:{port}:8000', '-e', 'CHARTS_SERVER_TOKENS=' + token,
                                '-e', 'CHARTS_PUBLIC_URL=' + base, args.image], check=True, capture_output=True, text=True).stdout.strip()
    try:
        check_image_files(container)
        user = subprocess.run(['docker', 'exec', container, 'id', '-u'], check=True, capture_output=True, text=True).stdout.strip()
        check(user != '0', 'container runs as root')
        run_checks(base, token)
        print(f'ok  container runs as uid {user}')
        return 0
    except Exception:
        print(subprocess.run(['docker', 'logs', container], capture_output=True, text=True).stderr[-4000:], file=sys.stderr)
        raise
    finally:
        subprocess.run(['docker', 'rm', '-f', container], capture_output=True)


if __name__ == '__main__':
    sys.exit(main())
