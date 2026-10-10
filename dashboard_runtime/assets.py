"""Self-contained UI bundle; snapshots cannot introduce executable markup."""
from __future__ import annotations
import html
import json
from pathlib import Path
from .model import DashboardError, validate

DIST = Path(__file__).parent / 'web' / 'dist'

def render_html(mode='web', document=None, legacy=None):
    js, css = DIST / 'app.js', DIST / 'app.css'
    if not js.exists() or not css.exists():
        raise DashboardError('ASSETS_NOT_BUILT', 'Build the UI first: npm --prefix runtime-ui install && npm --prefix runtime-ui run build', 503)
    if document is not None:
        validate(document)
    boot = {'mode': mode, 'document': document, 'legacy': legacy or {}}
    payload = json.dumps(boot, ensure_ascii=True, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    javascript = js.read_text().replace('</script', '<\\/script')
    styles = css.read_text().replace('</style', '<\\/style')
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Charts Design</title><style>' + styles + '</style></head><body>'
            '<script>window.__DASHBOARD_BOOT__=' + payload + ';</script><script>' + javascript + '</script></body></html>')

def export_document(document):
    # Original components are bundled from canonical source, not external CDN frames.
    return render_html('offline', document)
