"""Self-contained UI bundle; snapshots cannot introduce executable markup."""
from __future__ import annotations
import json
import hashlib
from functools import lru_cache
from pathlib import Path
from .model import DashboardError, validate

DIST = Path(__file__).parent / 'web' / 'dist'

def _asset_signature():
    signature = []
    for name in ('app.js', 'app.css'):
        path = DIST / name
        try:
            stat = path.stat()
            signature.append((stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino))
        except FileNotFoundError:
            signature.append(None)
    return str(DIST.resolve()), tuple(signature)


@lru_cache(maxsize=2)
def _read_assets(directory, signature):
    """Reuse immutable build contents; stat changes invalidate running MCP previews."""
    digest = hashlib.sha256()
    contents = []
    for name, stamp in zip(('app.js', 'app.css'), signature):
        raw = (Path(directory) / name).read_bytes() if stamp is not None else b''
        digest.update(raw)
        contents.append(raw.decode('utf-8'))
    return digest.hexdigest()[:12], contents[0].replace('</script', '<\\/script'), contents[1].replace('</style', '<\\/style')


def ui_build_id():
    return _read_assets(*_asset_signature())[0]

def render_html(mode='web', document=None, legacy=None, idle_timeout: float=60):
    js, css = DIST / 'app.js', DIST / 'app.css'
    if not js.exists() or not css.exists():
        raise DashboardError('ASSETS_NOT_BUILT', 'Build the UI first: npm --prefix runtime-ui install && npm --prefix runtime-ui run build', 503)
    if document is not None:
        validate(document)
    from .statistical import statistical_artifacts
    build_id, javascript, styles = _read_assets(*_asset_signature())
    boot = {'uiBuildId': build_id, 'statisticalArtifacts': statistical_artifacts(document) if document else {}, 'mode': mode, 'document': document, 'legacy': legacy or {}, 'idleTimeout': idle_timeout}
    payload = json.dumps(boot, ensure_ascii=True, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Charts Design</title><style>' + styles + '</style></head><body>'
            '<script>window.__DASHBOARD_BOOT__=' + payload + ';</script><script>' + javascript + '</script></body></html>')

def export_document(document):
    return render_html('offline', document)

def export_component(document, component_id):
    """Use the same UI and limit the artifact to this component and its sources."""
    import copy
    from .model import COLS, require
    validate(document)
    require(component_id in document['manifest']['components'], 'Component not found')
    result = copy.deepcopy(document)
    m, s = result['manifest'], result['snapshot']
    component = m['components'][component_id]
    m['components'] = {component_id: component}
    m['title'] = component['title'] or m['title']
    # A standalone component has no enclosing report or other narrative blocks.
    m['viewMode'] = 'dashboard'
    m.pop('report', None)
    metric_ids = set(component.get('measures', []))
    m['metrics'] = {k: v for k, v in m['metrics'].items() if k in metric_ids}
    dataset_ids = {component.get('datasetId')} | {v['datasetId'] for v in m['metrics'].values()}
    m['datasets'] = {k: v for k, v in m['datasets'].items() if k in dataset_ids}
    s['datasets'] = {k: v for k, v in s['datasets'].items() if k in dataset_ids}
    if 'datasetRefs' in s:
        s['datasetRefs'] = {k: v for k, v in s['datasetRefs'].items() if k in dataset_ids}
    if 'componentDataRefs' in s:
        s['componentDataRefs'] = {k: v for k, v in s['componentDataRefs'].items() if k == component_id}
    if 'computed' in result:
        for collection in ('components', 'tables', 'grouped'):
            result['computed'][collection] = {k: v for k, v in result['computed'].get(collection, {}).items() if k == component_id}
    source_ids = {component.get('sourceId')} | {v['sourceId'] for v in m['datasets'].values()}
    m['sources'] = {k: v for k, v in m['sources'].items() if k in source_ids}
    m['filters'] = [{**f, 'componentIds': [component_id]} for f in m['filters'] if component_id in f['componentIds']]
    m.pop('originalWorkspace', None)
    for bp, cols in COLS.items():
        old = next(p for p in m['layout'][bp] if p['id'] == component_id)
        m['layout'][bp] = [{**old, 'x': 0, 'y': 0, 'w': cols}]
    return render_html('offline', result)
