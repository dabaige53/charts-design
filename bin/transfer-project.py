#!/usr/bin/env python3
"""Transfer explicitly selected current dashboard datasets to a cloud MCP server."""
import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from dashboard_runtime.local_data import LocalData
from dashboard_runtime.model import validate


def read_project(manifest):
    root = Path(manifest['projectRoot']).resolve()
    uri = (root / 'dashboards' / 'dashboards.sqlite3').as_uri() + '?mode=ro'
    docs, refs = {}, {}
    with sqlite3.connect(uri, uri=True) as db:
        for page in manifest['pages']:
            board = page['dashboardId']
            row = db.execute('SELECT revision,document FROM boards WHERE id=?', (board,)).fetchone()
            if row is None or row[0] != page['draftRevision']:
                raise ValueError(f'{board}: draft revision changed; rebuild the manifest')
            doc = json.loads(row[1])
            if any(c.get('kind') == 'chart' for c in doc['manifest']['components'].values()):
                raise ValueError(f'{board}: native chart components cannot be imported by dashboard_create')
            notes = db.execute('SELECT payload FROM annotations WHERE board_id=?', (board,)).fetchone()
            doc['manifest']['annotations'] = json.loads(notes[0]) if notes else []
            if len(doc['manifest']['components']) != page['componentCount']:
                raise ValueError(f'{board}: component count changed')
            chosen = {item['id']: item for item in page['datasets']}
            if len(chosen) != len(page['datasets']):
                raise ValueError(f'{board}: duplicate dataset in manifest')
            snapshot = doc['snapshot']
            if snapshot.get('datasets') or snapshot.get('componentDataRefs'):
                raise ValueError(f'{board}: inline or component datasets require an explicit migration plan')
            for key, item in chosen.items():
                ref = snapshot['datasetRefs'][key]
                if any(ref.get(k) != item[k] for k in ('version', 'rowCount', 'bytes')):
                    raise ValueError(f'{board}/{key}: manifest data reference changed')
                prior = refs.setdefault(ref['version'], ref)
                if prior != ref:
                    raise ValueError('Conflicting immutable reference metadata')
            used = {c.get('datasetId') for c in doc['manifest']['components'].values() if c.get('datasetId')}
            used.update(c['binding']['datasetId'] for c in doc['manifest']['components'].values() if c.get('binding'))
            if not used <= set(chosen):
                raise ValueError(f'{board}: manifest omits a component dataset')
            doc['manifest']['datasets'] = {k: v for k, v in doc['manifest']['datasets'].items() if k in chosen}
            doc['manifest']['metrics'] = {k: v for k, v in doc['manifest']['metrics'].items() if v['datasetId'] in chosen}
            snapshot['datasetRefs'] = {k: v for k, v in snapshot['datasetRefs'].items() if k in chosen}
            for source in doc['manifest']['sources'].values():
                source['verification'] = 'supplied'
            validate(doc)
            docs[board] = doc
    return root, docs, refs


def batches(root, ref):
    uri = (root / 'data' / 'data.sqlite3').as_uri() + '?mode=ro'
    version = ref['version']
    fields = ref['fields']
    keys = ref['fieldOrder']
    if not all(isinstance(k, str) for k in keys) or set(keys) != set(fields):
        raise ValueError('Invalid field order')
    # Version is validated by model.validate before it is used in SQL.
    with sqlite3.connect(uri, uri=True) as db:
        columns = ','.join('c' + str(i) for i in range(len(keys)))
        cursor = db.execute(f'SELECT {columns}, _missing FROM d_{version} ORDER BY rowid')
        count = 0
        while True:
            values = cursor.fetchmany(250)
            if not values:
                break
            count += len(values)
            yield [LocalData._decode(keys, row[:-1], fields, row[-1]) for row in values]
        if count != ref['rowCount']:
            raise ValueError('Local data row count differs from manifest')


def normalized(doc):
    doc = json.loads(json.dumps(doc))
    for key in ('dataVersion', 'computed', 'progressive', 'loading'):
        doc.pop(key, None)
    doc['revision'] = 1
    return doc


async def call_tool(session, project, name, arguments):
    async def request(tool, payload):
        result = await session.call_tool(tool, {'projectRoot': project, **payload})
        if result.isError or not isinstance(result.structuredContent, dict):
            raise RuntimeError(f'{tool}: {result.structuredContent or result.content}')
        value = result.structuredContent
        if value.get('ok') is False:
            raise RuntimeError(f'{tool}: {value.get("error")}')
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


async def run(args):
    manifest = json.loads(Path(args.manifest).read_text())
    root, docs, refs = read_project(manifest)
    endpoint = os.environ['CHARTS_MCP_URL']
    token = os.environ['CHARTS_SERVER_TOKENS'].split(',')[0].strip()
    if not token:
        raise ValueError('CHARTS_SERVER_TOKENS must contain a server token')
    if urlparse(endpoint).scheme != 'https':
        raise ValueError('CHARTS_MCP_URL must use HTTPS')
    state_path = Path(args.state)
    identity = hashlib.sha256((endpoint + '\0' + args.project + '\0' + str(root)).encode()).hexdigest()
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state['identity'] != identity:
            raise ValueError('State file belongs to a different source or destination')
    else:
        state = {'identity': identity, 'uploads': {}, 'created': []}
    staged = state.setdefault('staged', [])
    if args.resume_staged and (args.resume_staged not in refs or args.resume_staged not in state['uploads']):
        raise ValueError('The requested staged version must exist in both manifest and state file')
    def save():
        temporary = state_path.with_name(state_path.name + '.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump(state, out)
        os.replace(temporary, state_path)
    async with httpx.AsyncClient(headers={'Authorization': 'Bearer ' + token}, timeout=120) as http:
        async with streamable_http_client(endpoint, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                async def call(name, arguments):
                    return await call_tool(session, args.project, name, arguments)
                existing = {item['id'] for item in (await call('dashboard_list', {}))['dashboards']}
                for board in existing & docs.keys():
                    actual = (await call('dashboard_get', {'dashboardId': board}))['document']
                    if normalized(actual) != normalized(docs[board]):
                        raise ValueError(f'{board}: destination exists and differs; refusing to overwrite')
                for version, ref in refs.items():
                    upload = state['uploads'].setdefault(version, secrets.token_hex(32))
                    save()
                    print(f'Transferring {version[:12]}: {ref["rowCount"]} rows', flush=True)
                    if version not in staged and version != args.resume_staged:
                        for part, rows in enumerate(batches(root, ref)):
                            result = await call('dataset_transfer_chunk', {'uploadId': upload, 'ref': ref, 'part': part, 'rows': rows})
                            if result['complete']:
                                break
                            if (part + 1) % 50 == 0:
                                print(f'  {min((part + 1) * 250, ref["rowCount"])} rows staged', flush=True)
                        staged.append(version)
                        save()
                    else:
                        print('  Resuming staged data without resending rows', flush=True)
                        if version not in staged:
                            staged.append(version)
                            save()
                    result = await call('dataset_transfer_finish', {'uploadId': upload, 'ref': ref})
                    last_progress = 0.0
                    while result['state'] != 'complete':
                        if result['state'] == 'failed':
                            raise RuntimeError(f'Transfer failed: {result.get("code")}')
                        if result['state'] in ('unknown', 'cleanup_required'):
                            result = await call('dataset_transfer_finish', {'uploadId': upload, 'ref': ref})
                        else:
                            if result.get('phase') and time.monotonic() - last_progress >= 20:
                                print(f'  {result["phase"]}: {result["completed"]}/{result["total"]} chunks', flush=True)
                                last_progress = time.monotonic()
                            await asyncio.sleep(2)
                            result = await call('dataset_transfer_status', {'uploadId': upload, 'ref': ref})
                for board, doc in docs.items():
                    if board not in existing:
                        await call('dashboard_create', {'dashboardId': board, 'document': doc})
                    if board not in state['created']:
                        state['created'].append(board)
                        save()
                    print(f'Imported {board}; run dashboard_checkpoint before publishing', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--state', required=True, help='Private resumable state file')
    parser.add_argument('--resume-staged', help='One existing data version already fully staged by an older client')
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except (OSError, KeyError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == '__main__':
    main()
