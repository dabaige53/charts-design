"""Explicit file exports; Chromium runs only for the duration of a PDF export."""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

from .assets import export_document
from .model import DashboardError, require


def export_dashboard(root: Path, document: dict, format: str, data=None) -> dict:
    require(format in ('pdf', 'html', 'json'), 'Choose PDF, HTML or JSON')
    directory = root / 'exports' / uuid.uuid4().hex
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    name = document['id'] + '.' + format
    path = directory / name
    details = {}
    if format == 'json':
        path.write_text(json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
        mime = 'application/json'
    else:
        html = export_document(document)
        mime = 'text/html' if format == 'html' else 'application/pdf'
        if format == 'html':
            path.write_text(html, encoding='utf-8')
        else:
            try:
                from .pdf_export import render_pdf
                details = render_pdf(path, document, html, data)
            except Exception as exc:
                path.unlink(missing_ok=True)
                raise DashboardError('PDF_EXPORT_FAILED', '本机 PDF 导出失败：' + str(exc)) from exc
    return {'export': {**details, 'id': directory.name, 'filename': name, 'path': str(path.resolve()), 'mimeType': mime,
                       'bytes': path.stat().st_size, 'encoding': 'base64',
                       'content': base64.b64encode(path.read_bytes()).decode('ascii'),
                       'scope': 'all-filtered-rows' if format == 'pdf' else ('current-view' if format == 'html' else 'configuration-and-local-references')}}


def open_export(root: Path, board: str, export_id: str, format: str, action: str) -> dict:
    """Open only managed exports, on the user's explicit button click."""
    from .model import identifier
    board = identifier(board)
    require(isinstance(export_id, str) and re.fullmatch(r'[0-9a-f]{32}', export_id) is not None, 'Invalid export ID')
    require(format in ('pdf', 'html', 'json'), 'Invalid export format')
    require(action in ('open', 'reveal'), 'Invalid file action')
    base = (root / 'exports').resolve()
    path = (base / export_id / (board + '.' + format)).resolve()
    require(path.is_relative_to(base) and path.is_file(), 'Export file not found')
    require(sys.platform == 'darwin', '当前平台暂不支持打开文件，请按显示的路径访问文件')
    try:
        subprocess.run(['open', *(['-R'] if action == 'reveal' else []), str(path)], check=True, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise DashboardError('EXPORT_OPEN_FAILED', '打开失败，文件仍保存在：' + str(path)) from exc
    return {'ok': True, 'action': action, 'path': str(path)}
