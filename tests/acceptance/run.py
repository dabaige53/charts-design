"""Independent data initialization, functional acceptance, and performance scenarios."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib import import_module
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests/fixtures'), str(ROOT / 'tests/runtime')]

from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.service import Service

large = import_module('benchmark_local')
small = import_module('charts_acceptance')
REQUIRED_MCP_TOOLS = {'dashboard_get', 'dashboard_list', 'dashboard_submit'}


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def measured(action):
    start = time.perf_counter()
    result = action()
    return result, round((time.perf_counter() - start) * 1000, 3)


def summarize(samples):
    ordered = sorted(samples)
    return {'medianMs': round(statistics.median(ordered), 3),
            'p95Ms': round(ordered[math.ceil(0.95 * len(ordered)) - 1], 3), 'samplesMs': samples}


def result(payload):
    if payload.get('error') or payload.get('ok') is False:
        raise RuntimeError(str(payload.get('error') or 'Dashboard action failed'))
    return payload


def seed(root, rows):
    manifest = root / 'fixture.json'
    if manifest.is_file():
        existing = read(manifest)
        if existing['rows'] != rows:
            raise ValueError('Existing fixture row count differs. Use a new --output directory.')
        return existing
    if (root / 'project').exists():
        raise ValueError('An existing project needs its original fixture.json or a new --output directory.')
    root.mkdir(parents=True, exist_ok=True)
    if rows == 48:
        report, records, _ = small.document()
        pages = {report['id']: report, **small.dashboard_pages(report, records)}
        service = Service(root / 'runtime', project_root=root / 'project')
        for board, page in pages.items():
            service.call('dashboard_create', {'dashboardId': board, 'document': page})
        board, dataset = small.DETAIL_PAGE, 'sales'
        filter_fields = ('month', 'region')
        selection = {'channel': '直营'}
        filtered = sum(row['channel'] == '直营' for row in records)
        fixture = {'rows': rows, 'boards': list(pages), 'filters': filter_fields, 'selection': selection,
                   'filteredRows': filtered, 'board': board, 'dataset': dataset}
    else:
        _, aliases = large.build_source(root / 'source', rows)
        service = Service(root / 'runtime', aliases, project_root=root / 'project')
        board, dataset = 'acceptance', 'facts'
        service.call('dashboard_create', {'dashboardId': board, 'document': large.new_document(board, 'Large data acceptance')})
        service.call('dataset_attach', {'dashboardId': board, 'expectedRevision': 1, 'datasetId': dataset,
                                        'connection': 'benchmark', 'table': 'facts', 'fields': large.FIELDS})
        result(service.call('dashboard_submit', {'dashboardId': board, 'expectedRevision': 2,
                                                 'operations': large.operations(rows)}))
        fixture = {'rows': rows, 'boards': [board], 'filters': ['month', 'department'],
                   'selection': {'department': 'Department-1', 'month': '2026-01-01'},
                   'filteredRows': ((rows - 2) // 48) + 1, 'board': board, 'dataset': dataset}
    save(manifest, fixture)
    return fixture


@contextmanager
def workspace(service, board):
    server = RuntimeHTTPServer(service, port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.1}, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}', trust_env=False, timeout=90) as client:
            author = {'Authorization': 'Bearer ' + server.token}
            viewer = {'Authorization': 'Bearer ' + server.preview_token(board)}
            assert client.get(f'/view/{board}').status_code == 200

            def tool(name, args=None, *, edit=False):
                payload = client.post('/api/tools/' + name, json={'dashboardId': board, **(args or {})},
                                      headers=author if edit else viewer)
                payload.raise_for_status()
                return result(payload.json())

            yield client, tool, author, viewer
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def options_request(doc, field):
    return {'filterId': field, 'expectedRevision': doc['revision'], 'dataVersion': doc['dataVersion'],
            'search': '', 'limit': 100, 'offset': 0}


def mk_note():
    return {'id': 'note-' + str(uuid4()), 'text': '验收批注：核对筛选后的明细行数。', 'componentId': 'details',
            'createdAt': datetime.now(timezone.utc).isoformat(),
            'anchor': {'scope': 'component', 'kind': 'area', 'quote': '',
                       'rect': {'x': 0.1, 'y': 0.1, 'width': 0.2, 'height': 0.1}}}


async def mcp_discovery(incoming, outgoing, project):
    from mcp import ClientSession
    from mcp.types import TextContent

    async with ClientSession(incoming, outgoing) as session:
        await session.initialize()
        discovery = await session.list_tools()
        assert REQUIRED_MCP_TOOLS <= {item.name for item in discovery.tools}
        response = await session.call_tool('dashboard_list', {'projectRoot': project})
        assert not response.isError
        if response.structuredContent is not None:
            return response.structuredContent
        if response.content and isinstance(response.content[0], TextContent):
            return json.loads(response.content[0].text)
        raise RuntimeError('MCP dashboard_list returned no JSON or text result')


# @wu-test type=integration | scope=MCP 连接与工具发现 | protects=样例完成初始化却不能通过本机或远程 MCP 读取
async def check_mcp(root, fixture):
    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable, cwd=str(ROOT), env={**os.environ},
        args=['-m', 'dashboard_runtime', '--project-root', str(root / 'project'), '--runtime-root', str(root / 'mcp'), 'mcp'])
    async with stdio_client(params) as (incoming, outgoing):
        data = await mcp_discovery(incoming, outgoing, str(root / 'project'))
        assert set(fixture['boards']) <= {item['id'] for item in data['dashboards']}
    return {'localMcp': True}


# @wu-test type=integration | scope=已部署作者的 MCP HTTP 接口 | protects=远程连接或工具发现成功却无法读取指定测试项目
def check_remote_mcp(url, token, project):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise ValueError('CHARTS_TEST_MCP_URL must be an HTTPS MCP endpoint')
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json, text/event-stream'}

    def rpc_result(message: dict[str, Any]) -> dict[str, Any]:
        payload = result(message).get('result')
        if not isinstance(payload, dict):
            raise RuntimeError('MCP response has no result object')
        return payload

    with httpx.Client(headers=headers, timeout=30) as client:
        def exchange(method, number=None, params=None) -> dict[str, Any]:
            body = {'jsonrpc': '2.0', 'method': method}
            if number is not None:
                body['id'] = number
            if params is not None:
                body['params'] = params
            with client.stream('POST', url, json=body) as response:
                response.raise_for_status()
                if session_id := response.headers.get('MCP-Session-Id'):
                    client.headers['MCP-Session-Id'] = session_id
                if number is None:
                    return {}
                if 'application/json' in response.headers.get('Content-Type', ''):
                    response.read()
                    message = response.json()
                    assert message['id'] == number
                    return rpc_result(message)
                lines = []
                for line in response.iter_lines():
                    if line.startswith('data:'):
                        lines.append(line.removeprefix('data:').lstrip())
                    elif not line and lines:
                        message = json.loads('\n'.join(lines))
                        lines.clear()
                        if message.get('id') == number:
                            return rpc_result(message)
                raise RuntimeError('MCP stream ended without a matching response')
        try:
            hello = exchange('initialize', 1, {'protocolVersion': '2025-03-26', 'capabilities': {},
                                                      'clientInfo': {'name': 'charts-design-acceptance', 'version': '1'}})
            client.headers['MCP-Protocol-Version'] = hello['protocolVersion']
            exchange('notifications/initialized')
            assert REQUIRED_MCP_TOOLS <= {item['name'] for item in exchange('tools/list', 2)['tools']}
            response = exchange('tools/call', 3, {'name': 'dashboard_list', 'arguments': {'projectRoot': project}})
            assert not response.get('isError')
            payload = response.get('structuredContent') or json.loads(response['content'][0]['text'])
            assert isinstance(payload['dashboards'], list)
            return {'project': project, 'boards': len(payload['dashboards'])}
        finally:
            if 'MCP-Session-Id' in client.headers:
                client.delete(url)


# @wu-test type=integration | scope=作者预览、保存和批注 | protects=草稿提前出现在预览、只读链接写入内容或批注改变草稿
def check_versions(fixture, client, tool, author, viewer):
    board = fixture['board']
    existing = tool('dashboard_version_status', edit=True)
    saved = existing['savedRevision']
    title = tool('dashboard_get')['document']['manifest']['title']
    draft = tool('dashboard_patch', {'expectedRevision': existing['draftRevision'],
        'operations': [{'op': 'set_title', 'value': title + ' · 验收'}]}, edit=True)['document']['revision']
    assert tool('dashboard_get')['document']['revision'] == saved
    assert client.post('/api/tools/dashboard_patch', json={'dashboardId': board}, headers=viewer).status_code == 403
    endpoint = '/api/annotations/' + board
    note = mk_note()
    request = {'revision': saved, 'append': note}
    first = client.post(endpoint, json=request, headers=viewer)
    assert first.is_success, first.text
    assert first.json()['targetRevision'] == saved
    retry = client.post(endpoint, json=request, headers=viewer)
    retry.raise_for_status()
    readback = client.get(endpoint, params={'revision': saved}, headers=author)
    readback.raise_for_status()
    assert sum(item['id'] == note['id'] for item in readback.json()['annotations']) == 1
    assert tool('dashboard_version_status', edit=True)['draftRevision'] == draft
    tool('dashboard_submit', {'expectedRevision': draft}, edit=True)
    assert tool('dashboard_get')['document']['revision'] == draft
    assert tool('dashboard_version_status', edit=True)['publishedRevision'] == existing['publishedRevision']
    tool('dashboard_version_publish', {'expectedRevision': draft, 'revision': draft}, edit=True)
    assert tool('dashboard_version_status', edit=True)['publishedRevision'] == draft
    return {'draftIsolation': True, 'projectAnnotationId': note['id'], 'savedRevision': draft, 'publishedRevision': draft}


def worker(fixture, doc, expected, filters, samples, *, base=None, headers=None, directory=None, source=None):
    base = base or 'https://fixture.invalid/fixture/'
    payload = {'document': doc, 'worker': str(source), 'base': base, 'headers': headers or {},
               'directory': str(directory.resolve()) if directory else None, 'fields': fixture['filters'],
               'samples': samples, 'expected': expected, 'table': 'details', 'rows': fixture['rows'],
               'filteredRows': fixture['filteredRows'], 'filters': filters}
    process = subprocess.run(['node', str(ROOT / 'tests/acceptance/share-worker.mjs')], input=json.dumps(payload),
                             env={**os.environ, 'NODE_USE_ENV_PROXY': '1'},
                             text=True, capture_output=True, check=False, timeout=240)
    if process.returncode:
        raise RuntimeError(f'Share Worker exited with {process.returncode}: ' + process.stderr.strip()[-1800:])
    measured_worker = json.loads(process.stdout)
    measured_worker['options'] = {field: {'query': summarize([r['queryMs'] for r in timings]),
        'bootAndQuery': summarize([r['bootAndQueryMs'] for r in timings]),
        'dataRequests': max(r['dataRequests'] for r in timings)} for field, timings in measured_worker['options'].items()}
    return measured_worker


def measure_local(fixture, tool, doc, filters, samples):
    board, revision = fixture['board'], doc['revision']
    timings, expected = {}, {}
    for field in fixture['filters']:
        values, milliseconds = [], []
        for _ in range(samples):
            response, elapsed = measured(lambda: tool('dashboard_filter_options', options_request(doc, field)))
            values.append(response['values'])
            milliseconds.append(elapsed)
        assert all(candidate == values[0] for candidate in values)
        expected[field] = values[0]
        timings[field] = {'firstMs': milliseconds[0], **summarize(milliseconds)}
    args = {'dashboardId': board, 'componentId': 'details', 'expectedRevision': revision, 'limit': 10}
    full, full_ms = measured(lambda: tool('component_data', args))
    filtered, apply_ms = measured(lambda: tool('component_data', {**args, 'filters': filters}))
    page = tool('component_data', {**args, 'filters': filters, 'offset': 10})
    assert full['totalRows'] == fixture['rows'] and filtered['totalRows'] == fixture['filteredRows']
    assert len(page['rows']) == min(max(fixture['filteredRows'] - 10, 0), 10)
    return {'options': timings, 'firstRowsMs': full_ms, 'applyFilterMs': apply_ms,
            'fullRows': full['totalRows'], 'filteredRows': filtered['totalRows']}, expected


# @wu-test type=integration | scope=Cloudflare 固定分享与批注 | protects=重复创建链接、访问绕过、共享批注丢失或作者反馈可写
def online(root, fixture, tool, doc, expected, filters, samples, keep_share, workspace_client, author):
    origin = os.environ['CHARTS_SHARE_SERVICE_URL'].rstrip('/')
    parsed = urlsplit(origin)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('CHARTS_SHARE_SERVICE_URL must be the HTTPS origin of the share service')
    board = fixture['board']
    version = tool('dashboard_version_status', edit=True)
    pending = root / 'online-request.json'
    if pending.is_file():
        request = read(pending)
        if request['revision'] != doc['revision']:
            raise ValueError('Online request already belongs to a saved revision. Use a new --output directory.')
    else:
        request = {'revision': doc['revision'], 'requestId': str(uuid4()), 'annotationMode': 'annotate', 'expiration': '7d'}
        save(pending, request)
    share, publish_ms = measured(lambda: tool('dashboard_share_publish', request, edit=True))
    assert tool('dashboard_share_publish', request, edit=True) == share
    assert tool('dashboard_version_status', edit=True)['publishedRevision'] == version['publishedRevision']
    url = urlsplit(share['url'])
    assert f'{url.scheme}://{url.netloc}' == origin
    path = url.path
    ua = 'Charts-Design-Acceptance/1'
    with httpx.Client(base_url=origin, headers={'User-Agent': ua}, timeout=60) as client:
        health = client.get('/health')
        health.raise_for_status()
        assert health.json()['storage'] == 'd1'
        assert client.get(path + 'document.json').status_code == 401
        login = client.post(path, data={'accessKey': share['accessKey']}, headers={'Origin': origin})
        assert login.status_code == 303
        received, load_ms = measured(lambda: client.get(path + 'document.json'))
        received.raise_for_status()
        published = received.json()
        assert published['publication']['revision'] == doc['revision']
        assert all(published['staticFilterOptions'][field] == values for field, values in expected.items())
        downloaded, worker_ms = measured(lambda: client.get(path + 'static-worker.js'))
        downloaded.raise_for_status()
        script = root / 'published-worker.js'
        script.write_bytes(downloaded.content)
        cookie = 'charts-share-' + share['shareId']
        note = mk_note()
        note['id'] = 'note-' + request['requestId']
        note['createdAt'] = '2026-01-01T00:00:00Z'
        payload = {'dashboardId': board, 'revision': doc['revision'], 'append': note, 'authorName': '验收脚本'}
        endpoint = path + 'api/annotations'
        first = client.post(endpoint, json=payload, headers={'Origin': origin})
        first.raise_for_status()
        assert client.post(endpoint, json=payload, headers={'Origin': origin}).json() == first.json()
        client.cookies.clear()
        assert client.post(path, data={'accessKey': share['accessKey']}, headers={'Origin': origin}).status_code == 303
        readback = client.get(endpoint, params={'dashboardId': board, 'revision': doc['revision']})
        readback.raise_for_status()
        assert sum(item['id'] == note['id'] for item in readback.json()['annotations']) == 1
        assert first.json()['annotation']['context']['designRevision'] == doc['revision']
        read_headers = {'Cookie': cookie + '=' + client.cookies[cookie], 'User-Agent': ua}
        measured_worker = worker(fixture, published, expected, filters, samples, base=share['url'],
                                 headers=read_headers, source=script)
        feedback = workspace_client.get('/api/publications/' + share['shareId'] + '/feedback',
                                        params={'dashboardId': board}, headers=author)
        feedback.raise_for_status()
        received_feedback = feedback.json()
        assert received_feedback['revision'] == doc['revision'] and received_feedback['canAnnotate'] is False
        assert received_feedback['annotations'] == readback.json()['annotations']
        token = parse_qs(urlsplit(received_feedback['url']).fragment)['feedback'][0]
        assert client.post(path, data={'feedbackToken': token}, headers={'Origin': origin}).status_code == 303
        assert client.post(endpoint, json=payload, headers={'Origin': origin}).status_code == 403
    if not keep_share:
        assert tool('dashboard_share_delete', {'shareId': share['shareId']}, edit=True)['revoked']
        pending.unlink()
    return {**measured_worker, 'shareUrl': share['url'], 'retained': keep_share, 'publishMs': publish_ms,
            'documentMs': load_ms, 'workerDownloadMs': worker_ms, 'annotationId': note['id'], 'health': health.json()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('seed', 'verify', 'perf'))
    parser.add_argument('--rows', type=int, default=48)
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--output', type=Path, help='Directory for the synthetic project and JSON reports')
    parser.add_argument('--online', action='store_true')
    parser.add_argument('--keep-share', action='store_true', help='Keep the successfully verified synthetic link for 7 days')
    args = parser.parse_args()
    if args.rows < 48 or not 1 <= args.samples <= 30:
        parser.error('Use at least 48 rows and 1–30 samples')
    if args.keep_share and not args.online:
        parser.error('--keep-share requires --online')
    if args.online and not all(os.environ.get(k) for k in ('CHARTS_SHARE_SERVICE_URL', 'CHARTS_SHARE_SERVICE_TOKEN')):
        parser.error('--online requires CHARTS_SHARE_SERVICE_URL and CHARTS_SHARE_SERVICE_TOKEN')
    if os.environ.get('CHARTS_TEST_MCP_URL') and not all(os.environ.get(k) for k in ('CHARTS_TEST_MCP_TOKEN', 'CHARTS_TEST_MCP_PROJECT')):
        parser.error('Remote MCP acceptance requires CHARTS_TEST_MCP_TOKEN and CHARTS_TEST_MCP_PROJECT')
    os.environ['CHARTS_STORAGE_BACKEND'] = 'local'
    root = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='charts-acceptance-'))
    fixture, seed_ms = measured(lambda: seed(root, args.rows))
    if args.mode == 'seed':
        print(json.dumps({'output': str(root), **fixture}, ensure_ascii=False))
        return
    checks: dict[str, object] = {}
    if args.mode == 'verify':
        checks.update(asyncio.run(check_mcp(root, fixture)))
        if url := os.environ.get('CHARTS_TEST_MCP_URL'):
            checks['remoteMcp'] = check_remote_mcp(url, os.environ['CHARTS_TEST_MCP_TOKEN'], os.environ['CHARTS_TEST_MCP_PROJECT'])
        subprocess.run(['bun', 'test', 'tests/deploy/pages-d1.test.mjs'], cwd=ROOT, check=True)
    service = Service(root / 'runtime', project_root=root / 'project')
    with workspace(service, fixture['board']) as (client, tool, author, viewer):
        if args.mode == 'verify':
            saved_check = root / 'functional-version-check.json'
            if not saved_check.is_file():
                save(saved_check, check_versions(fixture, client, tool, author, viewer))
            checks.update(read(saved_check))
        doc, structure = measured(lambda: tool('dashboard_get')['document'])
        assert doc['snapshot']['datasetRefs'][fixture['dataset']]['rowCount'] == fixture['rows']
        filters = [{**entry, 'values': [fixture['selection'][entry['id']]]}
                   if entry['id'] in fixture['selection'] else entry for entry in doc['manifest']['filters']]
        local, expected = measure_local(fixture, tool, doc, filters, args.samples)
        export, encode = measured(lambda: tool('dashboard_export_site', {'dataFormat': 'parquet'}, edit=True)['export'])
        directory = Path(export['directory'])
        saved = read(directory / 'document.json')
        offline = worker(fixture, saved, expected, filters, args.samples, directory=directory,
                         source=directory / 'static-worker.js')
        reports = {'fixture': fixture, 'checks': checks, 'seedMs': seed_ms, 'localStructureMs': structure,
                   'parquetExportMs': encode, 'zipBytes': export['bytes'], 'localAuthor': local, 'localShareWorker': offline}
        save(root / 'report.json', reports)
        print('Local author and packaged Worker passed. Report:', root / 'report.json', flush=True)
        if args.online:
            reports['cloudflare'] = online(root, fixture, tool, doc, expected, filters, args.samples, args.keep_share,
                                           client, author)
            save(root / 'report.json', reports)
            print('Cloudflare D1 and shared annotations passed.', flush=True)


if __name__ == '__main__':
    main()
