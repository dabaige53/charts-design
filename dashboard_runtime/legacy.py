"""Read-only adapter for the existing executive-charts catalog and workspace v1."""
from __future__ import annotations
import html
import importlib.util
import json
import sys
from pathlib import Path
from .model import DashboardError, apply_operations, identifier, new_document, require

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / 'skills' / 'executive-charts'

def catalog():
    path = SKILL / 'references' / 'chart_catalog.json'
    if not path.exists():
        return []
    return json.loads(path.read_text())

def render(config):
    """Reuse registered JS builders and the original shell, without example data fallback."""
    path = SKILL / 'scripts' / 'generate_chart.py'
    require(path.exists(), 'Legacy renderer requires the original charts-design repository', 'LEGACY_UNAVAILABLE')
    sys.path.insert(0, str(path.parent)) if str(path.parent) not in sys.path else None
    spec = importlib.util.spec_from_file_location('_charts_legacy', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    code = config.get('code')
    require(code in module.ALL_CHART_BUILDERS, 'Unknown legacy chart code')
    errors = module.validate_chart_data(config.get('data'), 'chart.data', code=code, strict=True, presentation=config.get('presentation'))
    require(not errors, 'Legacy contract failed: ' + json.dumps(errors, ensure_ascii=False))
    safe_json = json.dumps(config, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e')
    values = {
        '__CODE__': html.escape(code.upper()), '__TITLE__': html.escape(config.get('title', code)),
        '__SUBTITLE__': html.escape(config.get('subtitle', 'Legacy chart; metric definitions are in the inspector.')),
        '__CARD_WIDTH__': '100%', '__CHART_HEIGHT__': '320', '__GRANULARITY_TABS__': ('<div id="granularityTabs"><button type="button" onclick="setGranularity(\'month\', this)">\u6708\u5ea6</button><button type="button" onclick="setGranularity(\'quarter\', this)">\u5b63\u5ea6</button></div>' if config.get('hasGranularity', 'hasGranularity: true' in module.ALL_CHART_BUILDERS[code]) else ''),
        '__CHART_CONFIG_JS__': '{ ...(' + module.ALL_CHART_BUILDERS[code] + '), ...' + safe_json + ' }',
        '__EXPLANATION_DIALOG_CSS__': module.EXPLANATION_DIALOG_CSS,
        '__EXPLANATION_DIALOG_SHELL__': module.EXPLANATION_DIALOG_SHELL,
        '__EXPLANATION_DIALOG_RENDERER_JS__': module.EXPLANATION_DIALOG_RENDERER_JS,
        '__EXPLANATION_TRIGGER_ICON__': module.EXPLANATION_TRIGGER_ICON,
        '__EXPLANATION_JSON__': json.dumps(config.get('explanation') or module.CHART_EXPLANATIONS.get(config.get('explainKey', code), {}), ensure_ascii=True).replace('<', '\\u003c')
    }
    result = module.STANDALONE_CHART_TEMPLATE
    for key, value in values.items():
        result = result.replace(key, value)
    result = result.replace('echarts@5.5.0/', 'echarts@6.1.0/')
    policy = "default-src 'none'; script-src 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'unsafe-inline' https://cdn.jsdelivr.net; img-src data: blob:; connect-src 'none'; base-uri 'none'; form-action 'none'"
    return result.replace('<head>', '<head><meta http-equiv="Content-Security-Policy" content="' + html.escape(policy, quote=True) + '">', 1)

def import_workspace(path, board_id):
    root = Path(path).expanduser().resolve(strict=True)
    def read(relative):
        target = (root / relative).resolve(strict=True)
        require(target.is_relative_to(root), 'Workspace reference escapes its root', 'PATH_OUTSIDE_WORKSPACE')
        return json.loads(target.read_text())
    old = read('dashboard.json')
    require(old.get('schemaVersion') == 1, 'Expected workspace schemaVersion 1')
    doc = new_document(board_id, old.get('meta', {}).get('title') or 'Imported dashboard')
    ops = [{'op': 'put_source', 'id': 'workspace-import', 'value': {'kind': 'file', 'name': root.name, 'verification': 'supplied'}}]
    notes = []
    refs = old.get('components', {})
    for i, relative in enumerate(refs.get('charts', [])):
        chart = read(relative)
        key = identifier(chart.get('id', f'chart-{i}'))
        ops.append({'op': 'put_component', 'id': key, 'value': {
            'kind': 'legacy', 'family': 'chart', 'title': chart.get('title', key),
            'config': chart, 'sourceId': 'workspace-import'}})
    for i, relative in enumerate(refs.get('kpis', [])):
        card = read(relative)
        key = identifier(card.get('id', f'kpi-{i}'))
        ops.append({'op': 'put_component', 'id': key, 'value': {
            'kind': 'legacy', 'family': 'kpi', 'title': card.get('label', key),
            'config': card, 'sourceId': 'workspace-import'}})
    table_ref = refs.get('table')
    if table_ref:
        table = read(table_ref)
        if table.get('columns'):
            ops.append({'op': 'put_component', 'id': identifier(table.get('id', 'import-table')), 'value': {
                'kind': 'legacy', 'family': 'table', 'title': table.get('title', 'Details'),
                'config': table, 'sourceId': 'workspace-import'}})
    result = apply_operations(doc, ops)
    result['manifest']['originalWorkspace'] = {'meta': old.get('meta', {}), 'manifest': old,
        'filters': read(refs['filters']) if refs.get('filters') else []}
    notes.append('Original chart, KPI and table configurations are preserved; bind verified data paths before enabling cross-component filters.')
    ordered = list(result['manifest']['components'])
    for bp, cols in [('desktop', 12), ('tablet', 8), ('mobile', 4)]:
        x = y = row_height = 0
        positions = []
        ordered = sorted(ordered, key=lambda k: {'kpi': 0, 'chart': 1, 'table': 2}[result['manifest']['components'][k]['family']])
        for key in ordered:
            c = result['manifest']['components'][key]
            width = (cols // 4 if bp == 'desktop' else cols // 2) if c['family'] == 'kpi' else (cols if c['family'] == 'table' or c['config'].get('colSpan') == 2 else cols // 2)
            if bp == 'mobile': width = cols
            height = 4 if c['family'] == 'kpi' else 8
            if x + width > cols: y += row_height; x = row_height = 0
            positions.append({'id': key, 'x': x, 'y': y, 'w': width, 'h': height})
            x += width; row_height = max(row_height, height)
        result['manifest']['layout'][bp] = positions
    from .model import validate
    return validate(result), notes

def validate_original(component):
    """Validate explicit original contracts before any web/CLI/MCP state is saved."""
    config = component.get('config')
    require(isinstance(config, dict), 'Original component requires a config object')
    family = component.get('family', 'chart')
    require(family in ('chart', 'kpi', 'table'), 'Unknown original component family')
    scripts = SKILL / 'scripts'
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from core.component_schemas import validate_chart_data, KPI_TYPES
    if family == 'chart':
        require(isinstance(config.get('data'), dict) and isinstance(config.get('presentation'), dict), 'Original charts need explicit data and presentation')
        errors = validate_chart_data(config['data'], 'config.data', code=config.get('code'), strict=True, presentation=config['presentation'])
        require(not errors, 'Original chart contract: ' + json.dumps(errors, ensure_ascii=False))
    elif family == 'kpi':
        require(config.get('type', 'mc01') in KPI_TYPES, 'Unknown original KPI type')
        require(isinstance(config.get('label'), str), 'Original KPI requires a label')
        require('value' in config or (config.get('type') == 'mc06' and 'leftVal' in config and 'rightVal' in config), 'Original KPI requires explicit values')
        if config.get('type') == 'mc03':
            require(isinstance(config.get('sparkData', config.get('sparkline')), list), 'Sparkline needs explicit sparkData, never preview defaults')
    else:
        require(isinstance(config.get('columns'), list) and isinstance(config.get('rows'), list), 'Original table requires columns and rows')
        keys = [col.get('key') for col in config['columns'] if isinstance(col, dict)]
        require(len(keys) == len(config['columns']) and len(set(keys)) == len(keys) and all(isinstance(key, str) for key in keys), 'Table columns require unique keys')
