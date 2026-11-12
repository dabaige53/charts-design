#!/usr/bin/env python3
"""Upload a data version or download a complete remote dashboard configuration."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard_runtime.local_data import LocalData
from dashboard_runtime.remote_client import (
    TRANSFER_TOOLS, TransferClient, call_tool, check_source, connect,
    connection_settings, progress, require_tools, run_command, save_private,
)


def source_ref(args):
    if args.ref:
        return json.loads(Path(args.ref).read_text())
    if not args.fields:
        raise ValueError('--fields is required with --rows')
    fields = json.loads(Path(args.fields).read_text())
    path = Path(args.rows)
    if path.suffix == '.jsonl':
        with path.open() as source:
            return LocalData(Path(args.root) / 'data').import_rows(
                (json.loads(line) for line in source if line.strip()), fields)
    rows = json.loads(path.read_text())
    if not isinstance(rows, list):
        raise ValueError('--rows must contain a JSON array or a .jsonl file')
    return LocalData(Path(args.root) / 'data').import_rows(rows, fields)


async def run(args):
    endpoint, token = connection_settings()
    if args.command == 'read':
        async with connect(endpoint, token) as session:
            await require_tools(session, {'dashboard_get': {'dashboardId'},
                                          'runtime_result_chunk': {'requestId', 'index'}})
            result = await call_tool(session, args.project, 'dashboard_get', {'dashboardId': args.dashboard})
        save_private(args.output, result)
        doc = result['document']
        print(json.dumps({'output': str(Path(args.output).resolve()), 'revision': doc['revision'],
                          'componentIds': list(doc['manifest']['components'])}))
        return
    start = time.monotonic()
    ref = source_ref(args)
    check_source(args.root, ref)
    progress({'stage': 'source', 'rows': ref['rowCount'], 'bytes': ref['bytes'],
              'seconds': round(time.monotonic() - start, 3)})
    async with connect(endpoint, token) as session:
        async def call(name, arguments):
            return await call_tool(session, args.project, name, arguments)
        await require_tools(session, TRANSFER_TOOLS)
        client = TransferClient(call, args.root, endpoint, args.project, args.state,
                                concurrency=args.concurrency)
        if args.check_only:
            print(json.dumps({'checked': True, 'rows': ref['rowCount'], 'bytes': ref['bytes']}))
            return
        await client.transfer(ref)
        save_private(args.output, ref)
        print(json.dumps({'state': 'complete', 'output': str(Path(args.output).resolve()),
                          'version': ref['version'], 'rowCount': ref['rowCount']}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    upload = commands.add_parser('upload', help='Transfer data only; preserve all dashboard definitions')
    upload.add_argument('--project', required=True)
    upload.add_argument('--root', required=True, help='Local project containing data/data.sqlite3')
    source = upload.add_mutually_exclusive_group(required=True)
    source.add_argument('--ref', help='JSON file containing an existing immutable local data reference')
    source.add_argument('--rows', help='Typed JSON array or .jsonl source, imported into --root')
    upload.add_argument('--fields', help='JSON field definitions, required with --rows')
    upload.add_argument('--state', required=True, help='Private resumable state file')
    upload.add_argument('--output', required=True, help='Verified ref JSON, written only after completion')
    upload.add_argument('--concurrency', type=int, choices=range(1, 5), default=4)
    upload.add_argument('--check-only', action='store_true', help='Check source and service; upload no rows')
    read = commands.add_parser('read', help='Save complete configuration, decoding all MCP response chunks')
    read.add_argument('--project', required=True)
    read.add_argument('--dashboard', required=True)
    read.add_argument('--output', required=True)
    args = parser.parse_args()
    run_command(run(args), getattr(args, 'state', None))


if __name__ == '__main__':
    main()
