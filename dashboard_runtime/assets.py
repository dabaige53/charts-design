"""The same compiled React UI is served by this project's MCP and local preview."""
import base64
import json
from pathlib import Path
from .model import DashboardError

DIST = Path(__file__).parent / 'web' / 'dist'
MIME_TYPE = 'text/html;profile=mcp-app'
FAVICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
               '<rect x="2" y="2" width="60" height="60" rx="14" fill="#1016bf"/>'
               '<path d="M15 45 32 34 49 19" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
               '<g fill="#fff"><circle cx="15" cy="45" r="5"/><circle cx="32" cy="34" r="5"/><circle cx="49" cy="19" r="5"/></g></svg>')
FAVICON_LINK = '<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,' + base64.b64encode(FAVICON_SVG.encode()).decode() + '"' + '>'


def ui_build_id():
    try:
        return json.loads((DIST / 'build.json').read_text())['id']
    except FileNotFoundError:
        return 'unavailable'


def ui_resource_uri():
    return 'ui://charts-design/dashboard-' + ui_build_id() + '.html'


def require_preview():
    if ui_build_id() == 'unavailable':
        raise DashboardError('UI_UNAVAILABLE', 'UI 尚未打包；请运行 npm run ui:build 和 npm run ui:package。', 503)


def render_html(mode='web', document=None, legacy=None, idle_timeout: float = 60, boot_state=None):
    require_preview()
    boot = json.dumps({'mode': mode, 'document': document, 'idleTimeout': idle_timeout, 'uiBuildId': ui_build_id(), **(boot_state or {})},
                      ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    css = (DIST / 'app.css').read_text().replace('</style', '<\\/style')
    script = (DIST / 'app.js').read_text().replace('</script', '<\\/script')
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Charts Design</title>' + FAVICON_LINK + '<style>' + css + '</style></head>'
            '<body><div id="root"></div><script>window.__chartsBoot=' + boot
            + ';</script><script>' + script + '</script></body></html>')


def bundle_assets():
    require_preview()
    return {name: (DIST / name).read_bytes() for name in ('app.js', 'app.css', 'static-worker.js')}


def export_document(document):
    import copy
    snapshot = copy.deepcopy(document)
    snapshot['snapshot'] = {'datasets': {}}
    snapshot.pop('loading', None)
    snapshot.pop('progressive', None)
    snapshot['statisticalArtifacts'] = {key: {field: value for field, value in artifact.items() if field != 'provenance'}
                                       for key, artifact in snapshot.get('statisticalArtifacts', {}).items()}
    for key in ('sources', 'queries', 'annotations'):
        snapshot['manifest'].pop(key, None)
    return render_html('snapshot', snapshot)


def export_component(document, component_id):
    import copy
    from .model import require
    require(component_id in document['manifest']['components'], 'Unknown component')
    doc = copy.deepcopy(document)
    doc['manifest']['components'] = {component_id: doc['manifest']['components'][component_id]}
    doc['manifest']['filters'] = []
    doc['manifest']['viewMode'] = 'dashboard'
    doc['manifest']['layout'] = {bp: [{'id': component_id, 'x': 0, 'y': 0, 'w': cols, 'h': 10}] for bp, cols in [('desktop', 12), ('tablet', 8), ('mobile', 4)]}
    return export_document(doc)
