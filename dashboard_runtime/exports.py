"""Managed JSON/HTML/CSV exports shared by MCP and browser clients."""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

from .model import DashboardError, identifier, require

FORMATS = ('html', 'json', 'csv', 'zip')


def export_path(root, board, export_id, format):
    board = identifier(board)
    require(isinstance(export_id, str) and re.fullmatch(r'[0-9a-f]{32}', export_id) is not None, 'Invalid export ID')
    require(format in FORMATS, 'Invalid export format')
    base = (Path(root) / 'exports').resolve()
    path = (base / export_id / (board + '.' + format)).resolve()
    require(path.is_relative_to(base) and path.is_file(), 'Export file not found')
    return path


def export_dashboard(root: Path, document: dict, format: str, data=None) -> dict:
    require(format in ('html', 'json'), 'Choose HTML or JSON')
    directory = root / 'exports' / uuid.uuid4().hex
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    name = document['id'] + '.' + format
    path = directory / name
    if format == 'html':
        from .assets import export_document
        path.write_text(export_document(document), encoding='utf-8')
    else:
        path.write_text(json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
    return {'export': {'id': directory.name, 'filename': name, 'path': str(path.resolve()),
                       'mimeType': 'text/html' if format == 'html' else 'application/json',
                       'bytes': path.stat().st_size, 'format': format,
                       'scope': 'current-view-snapshot' if format == 'html' else 'configuration-and-local-references'}}


def read_export(root, board, export_id, format, offset=0, limit=262144):
    path = export_path(root, board, export_id, format)
    total = path.stat().st_size
    require(type(offset) is int and 0 <= offset <= total, 'Invalid export offset')
    require(type(limit) is int and 1 <= limit <= 262144, 'Invalid export chunk size')
    with path.open('rb') as stream:
        stream.seek(offset)
        raw = stream.read(limit)
    return {'id': export_id, 'filename': path.name, 'offset': offset, 'bytes': total,
            'content': base64.b64encode(raw).decode('ascii'), 'encoding': 'base64',
            'nextOffset': offset + len(raw), 'hasMore': offset + len(raw) < total}


def open_export(root: Path, board: str, export_id: str, format: str, action: str) -> dict:
    """Open only managed exports, on the user's explicit button click."""
    path = export_path(root, board, export_id, format)
    require(action in ('open', 'reveal'), 'Invalid file action')
    require(sys.platform == 'darwin', '当前平台暂不支持打开文件，请按显示的路径访问文件')
    try:
        subprocess.run(['open', *(['-R'] if action == 'reveal' else []), str(path)], check=True, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise DashboardError('EXPORT_OPEN_FAILED', '打开失败，文件仍保存在：' + str(path)) from exc
    return {'ok': True, 'action': action, 'path': str(path)}
