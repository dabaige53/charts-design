"""Shared remote MCP reads and resumable dataset transfers."""
from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import time
from urllib.parse import urlparse

from .local_data import LocalData
from .model import DashboardError, json_bytes
from .transfer_payload import BULK_ENCODING, BULK_ROWS, TRANSFER_ROWS, encode_bulk

TRANSFER_TOOLS = {
    'dataset_transfer_chunk': {'uploadId', 'ref', 'part', 'rows'},
    'dataset_transfer_finish': {'uploadId', 'ref'},
    'dataset_transfer_status': {'uploadId', 'ref', 'parts'},
}


def save_private(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(value, out, ensure_ascii=False, allow_nan=False)
    os.replace(temporary, path)


def connection_settings():
    endpoint = os.environ.get('CHARTS_MCP_URL', '')
    token = os.environ.get('CHARTS_SERVER_TOKENS', '').split(',')[0].strip()
    parsed = urlparse(endpoint)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('CHARTS_MCP_URL must be an HTTPS endpoint without embedded credentials')
    if not token:
        raise ValueError('CHARTS_SERVER_TOKENS must contain a server token')
    return endpoint, token


@asynccontextmanager
async def connect(endpoint, token):
    try:
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as error:
        raise RuntimeError(
            'Remote client dependencies are missing; run bun run setup in the repository, '
            'or install the package mcp extra in the selected Python environment'
        ) from error
    async with httpx.AsyncClient(
        headers={'Authorization': 'Bearer ' + token}, timeout=120, follow_redirects=False,
    ) as http:
        async with streamable_http_client(endpoint, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


async def require_tools(session, required):
    available, cursor = {}, None
    while True:
        page = await session.list_tools(cursor=cursor)
        available.update({tool.name: tool.inputSchema for tool in page.tools})
        cursor = page.nextCursor
        if not cursor:
            break
    if required.keys() - available.keys():
        from pydantic import AnyUrl
        from mcp.types import TextResourceContents
        resource = (await session.read_resource(AnyUrl('charts://contract'))).contents[0]
        if isinstance(resource, TextResourceContents):
            available.update(json.loads(resource.text).get('clientTools', {}))
    for name, parameters in required.items():
        schema = available.get(name)
        if schema is None or not parameters <= set(schema.get('properties', {})):
            raise RuntimeError(f'CAPABILITY_MISSING: {name}; update the target service before uploading')
    return available


def supports_bulk(available):
    return all(
        BULK_ENCODING in available[name].get('properties', {}).get('encoding', {}).get('enum', [])
        for name in TRANSFER_TOOLS
    ) and 'payload' in available['dataset_transfer_chunk']['properties']


async def call_tool(session, project, name, arguments):
    async def request(tool, payload):
        response = await session.call_tool(tool, {'projectRoot': project, **payload})
        value = response.structuredContent
        if value is None and response.content:
            value = json.loads(response.content[0].text)
        if response.isError or not isinstance(value, dict) or value.get('ok') is False:
            error = value.get('error', {}) if isinstance(value, dict) else {}
            # Error messages may contain source values. Keep diagnostics metadata-only.
            code = error.get('code', 'MCP_ERROR') if isinstance(error, dict) else 'MCP_ERROR'
            raise RuntimeError(f'{tool}: {code}')
        return value

    result = await request(name, arguments)
    transport = result.get('transport')
    if transport:
        if transport.get('encoding') != 'base64-json-v1':
            raise ValueError('Unknown MCP response encoding')
        chunks = []
        for index in range(transport['chunks']):
            page = await request('runtime_result_chunk', {'requestId': transport['requestId'], 'index': index})
            if page.get('requestId') != transport['requestId'] or page.get('index') != index:
                raise ValueError('MCP response chunk does not match the request')
            chunks.append(page['data'])
        raw = base64.b64decode(''.join(chunks), validate=True)
        if len(raw) != transport['bytes']:
            raise ValueError('MCP response byte count does not match')
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get('ok') is False:
            raise RuntimeError(f'{name}: invalid or failed MCP response')
    return result


def batches(root, ref, size=TRANSFER_ROWS):
    data_path = Path(root).resolve() / 'data' / 'data.sqlite3'
    if not data_path.is_file():
        raise ValueError('Local data/data.sqlite3 is missing')
    version = ref.get('version')
    if not isinstance(version, str) or not re.fullmatch('[0-9a-f]{64}', version):
        raise ValueError('Invalid local data version')
    with sqlite3.connect(data_path.as_uri() + '?mode=ro', uri=True) as db:
        record = db.execute('SELECT metadata FROM versions WHERE version=?', (version,)).fetchone()
        if record is None or LocalData._metadata(record[0]) != ref:
            raise ValueError('Local data reference differs from supplied metadata')
        keys, fields = ref['fieldOrder'], ref['fields']
        columns = ','.join('c' + str(i) for i in range(len(keys)))
        cursor = db.execute(f'SELECT {columns}, _missing FROM d_{version} ORDER BY rowid')
        while values := cursor.fetchmany(size):
            yield [LocalData._decode(keys, row[:-1], fields, row[-1]) for row in values]


def check_source(root, ref, *, bulk=False):
    count = 0
    for rows in batches(root, ref, BULK_ROWS if bulk else TRANSFER_ROWS):
        try:
            raw = json_bytes(rows)
        except DashboardError as error:
            if bulk and error.code == 'PAYLOAD_TOO_LARGE':
                raise ValueError('Bulk chunk exceeds 16 MiB decoded; use --legacy for a new upload') from error
            raise
        if bulk:
            encode_bulk(raw)
        elif len(raw) > 2 * 1024 * 1024:
            raise ValueError('A 250-row upload chunk exceeds 2 MiB; reduce source field size')
        count += len(rows)
    if count != ref['rowCount']:
        raise ValueError('Local row count differs from the data reference')


def progress(event):
    print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)


def run_command(coroutine, state_path=None):
    try:
        asyncio.run(coroutine)
    except Exception as error:
        # MCP stream failures are often wrapped in task groups. Report useful leaves
        # without exposing HTTP headers, URLs or raw tool response bodies.
        def messages(exc):
            children = getattr(exc, 'exceptions', None)
            if children:
                return [message for child in children for message in messages(child)]
            if isinstance(exc, (ValueError, RuntimeError)):
                return [str(exc)]
            return [type(exc).__name__]
        progress({'stage': 'command', 'errors': messages(error), 'stateFile': state_path,
                  'recovery': 'Correct the error and rerun with the same state file; check-only performs preflight'})
        raise SystemExit(1) from None


class TransferClient:
    def __init__(self, call, root, endpoint, project, state_path, *, concurrency=4, emit=progress,
                 bulk_available=False, legacy=False):
        if type(concurrency) is not int or not 1 <= concurrency <= 4:
            raise ValueError('Upload concurrency must be between 1 and 4')
        self.call, self.root, self.path = call, Path(root).resolve(), Path(state_path)
        self.concurrency, self.emit = concurrency, emit
        self.bulk_available, self.legacy = bulk_available, legacy
        identity = hashlib.sha256((endpoint + '\0' + project + '\0' + str(self.root)).encode()).hexdigest()
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            if self.state['identity'] != identity:
                raise ValueError('State file belongs to a different source or destination')
        else:
            self.state = {'identity': identity, 'uploads': {}, 'created': []}
        self.state.setdefault('staged', [])
        self.state.setdefault('bulk', [])

    def save(self):
        save_private(self.path, self.state)

    def uses_bulk(self, version):
        if version in self.state['bulk']:
            if not self.bulk_available:
                raise RuntimeError('CAPABILITY_MISSING: gzip-json-v1; resume on a bulk-compatible service')
            return True
        return version not in self.state['uploads'] and self.bulk_available and not self.legacy

    def check_source(self, ref):
        check_source(self.root, ref, bulk=self.uses_bulk(ref['version']))

    async def transfer(self, ref, *, resume_staged=False):
        version = ref['version']
        if resume_staged and version not in self.state['uploads']:
            raise ValueError('The staged version must already exist in the state file')
        fresh = version not in self.state['uploads']
        bulk = self.uses_bulk(version)
        if fresh and bulk:
            self.state['bulk'].append(version)
        upload = self.state['uploads'].setdefault(version, secrets.token_hex(32))
        self.save()
        args = {'uploadId': upload, 'ref': ref}
        if bulk:
            args['encoding'] = BULK_ENCODING
        start = time.monotonic()
        phase = 'inspect'
        timings = {}

        def report(**values):
            self.emit({'version': version, 'stage': phase, **values})

        try:
            result = await self.call('dataset_transfer_status', args)
            state = self.status(result)
            if (state == 'failed' and result.get('code') == 'DATA_INCOMPLETE'
                    and version in self.state['staged']):
                self.state['staged'].remove(version)
                self.save()
            if state not in ('complete', 'running', 'cleanup_required'):
                if version not in self.state['staged'] and not resume_staged:
                    phase = 'upload'
                    uploaded, skipped = 0, 0
                    block = []
                    # Inspect remote receipts in bounded windows, including an acknowledged
                    # chunk whose response was lost before a local state save.
                    for part, rows in enumerate(batches(self.root, ref, BULK_ROWS if bulk else TRANSFER_ROWS)):
                        block.append((part, rows))
                        if len(block) == (4 if bulk else 128):
                            sent, reused = await self.upload_window(args, block, inspect=not fresh)
                            uploaded += sent
                            skipped += reused
                            report(uploadedParts=uploaded, reusedParts=skipped)
                            block = []
                    if block:
                        sent, reused = await self.upload_window(args, block, inspect=not fresh)
                        uploaded += sent
                        skipped += reused
                    report(uploadedParts=uploaded, reusedParts=skipped)
                self.state['staged'] = list(dict.fromkeys([*self.state['staged'], version]))
                self.save()
                timings['uploadSeconds'] = round(time.monotonic() - start, 3)
                result = await self.call('dataset_transfer_finish', args)
            phase = 'finalize'
            phase_start = time.monotonic()
            last_report = 0
            while self.status(result) != 'complete':
                state = self.status(result)
                if state == 'failed':
                    if result.get('code') == 'DATA_INCOMPLETE' and version in self.state['staged']:
                        self.state['staged'].remove(version)
                        self.save()
                    raise RuntimeError(f'TRANSFER_FAILED: {result.get("code", "unknown")}')
                if time.monotonic() - last_report >= 20:
                    report(state=state, phase=result.get('phase'),
                           completed=result.get('completed'), total=result.get('total'))
                    last_report = time.monotonic()
                if state in ('unknown', 'cleanup_required'):
                    result = await self.call('dataset_transfer_finish', args)
                else:
                    result = await self.call('dataset_transfer_status', args)
                if self.status(result) != 'complete':
                    await asyncio.sleep(2)
            if result.get('ref') != ref:
                raise ValueError('Completed transfer reference differs from the source')
            timings['finalizeSeconds'] = round(time.monotonic() - phase_start, 3)
            report(state='complete', rows=ref['rowCount'], **timings)
            return ref
        except Exception as error:
            report(state='failed', errorType=type(error).__name__, stateFile=str(self.path),
                   recovery='Keep the state file; correct the reported error and rerun the same command')
            raise

    @staticmethod
    def status(result):
        state = result.get('state')
        if state not in ('unknown', 'running', 'cleanup_required', 'complete', 'failed'):
            raise RuntimeError('TRANSFER_PROTOCOL_ERROR: missing or unsupported state; update the target service')
        return state

    async def upload_window(self, args, block, *, inspect=True):
        started = time.monotonic()
        bulk = args.get('encoding') == BULK_ENCODING
        received = {}
        if inspect:
            result = await self.call('dataset_transfer_status', {**args, 'parts': [part for part, _ in block]})
            state = self.status(result)
            if state in ('complete', 'cleanup_required'):
                return 0, len(block)
            received = result.get('receivedParts')
            if not isinstance(received, dict):
                raise RuntimeError('TRANSFER_PROTOCOL_ERROR: missing receivedParts; update the target service')
        checked = time.monotonic()
        pending = []
        encoded_bytes = sent_bytes = 0
        for part, rows in block:
            raw = json_bytes(rows)
            encoded_bytes += len(raw)
            digest = hashlib.sha256(raw).hexdigest()
            remote = received.get(str(part))
            if remote is not None and remote != digest:
                raise ValueError(f'DATA_CONFLICT: staged part {part} differs from the source')
            if remote is None:
                if bulk:
                    payload = encode_bulk(raw)
                    sent_bytes += len(payload)
                    pending.append((part, {'payload': payload}))
                else:
                    sent_bytes += len(raw)
                    pending.append((part, {'rows': rows}))
        encoded = time.monotonic()

        async def send(part, data):
            result = await self.call('dataset_transfer_chunk', {**args, 'part': part, **data})
            if result.get('part') != part or type(result.get('complete')) is not bool:
                raise RuntimeError('TRANSFER_PROTOCOL_ERROR: invalid chunk receipt')

        # Await every in-flight request before propagating failure. Never finalize a partial window.
        for offset in range(0, len(pending), self.concurrency):
            results = await asyncio.gather(
                *(send(part, data) for part, data in pending[offset:offset + self.concurrency]),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    raise result
        self.emit({'stage': 'upload-window', 'sentParts': len(pending), 'reusedParts': len(block) - len(pending),
                   'encodedBytes': encoded_bytes, 'sentPayloadBytes': sent_bytes,
                   'receiptSeconds': round(checked - started, 3),
                   'encodeSeconds': round(encoded - checked, 3),
                   'requestSeconds': round(time.monotonic() - encoded, 3)})
        return len(pending), len(block) - len(pending)
