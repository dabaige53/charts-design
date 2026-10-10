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
        '__CARD_WIDTH__': '100%', '__CHART_HEIGHT__': '320', '__GRANULARITY_TABS__': '',
        '__CHART_CONFIG_JS__': '{ ...(' + module.ALL_CHART_BUILDERS[code] + '), ...' + safe_json + ' }',
        '__EXPLANATION_DIALOG_CSS__': module.EXPLANATION_DIALOG_CSS,
        '__EXPLANATION_DIALOG_SHELL__': module.EXPLANATION_DIALOG_SHELL,
        '__EXPLANATION_DIALOG_RENDERER_JS__': module.EXPLANATION_DIALOG_RENDERER_JS,
        '__EXPLANATION_TRIGGER_ICON__': module.EXPLANATION_TRIGGER_ICON,
        '__EXPLANATION_JSON__': json.dumps({'title': 'Legacy chart', 'overview': 'Chart-shape guidance is not a certified business definition.'})
    }
    result = module.STANDALONE_CHART_TEMPLATE
    for key, value in values.items():
        result = result.replace(key, value)
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
        if chart.get('code') in ('c01', 'c02') and chart.get('data', {}).get('categories') is not None:
            data = chart['data']
            require(len(data['categories']) == len(data['values']), 'Legacy chart arrays differ in length')
            ds, mid = f'ds-{key}', f'm-{key}'
            ops.extend([
                {'op': 'put_dataset', 'id': ds, 'meta': {'fields': {'category': {'type': 'string'}, 'value': {'type': 'number'}}, 'sourceId': 'workspace-import'}, 'rows': [{'category': c, 'value': v} for c, v in zip(data['categories'], data['values'])]},
                {'op': 'put_metric', 'id': mid, 'value': {'datasetId': ds, 'field': 'value', 'aggregation': 'sum', 'label': chart.get('title', key), 'unit': chart.get('unit', ''), 'definition': 'Imported reviewed values; verify original aggregation before regrouping.', 'status': 'unverified'}},
                {'op': 'put_component', 'id': key, 'value': {'kind': 'chart', 'chartType': 'bar', 'title': chart.get('title', key), 'datasetId': ds, 'x': 'category', 'measures': [mid]}}
            ])
        else:
            ops.append({'op': 'put_component', 'id': key, 'value': {'kind': 'legacy', 'title': chart.get('title', key), 'config': chart, 'sourceId': 'workspace-import'}})
            notes.append(f'{key}: preserved as isolated legacy chart; no implicit cross-filter or type conversion')
    for i, relative in enumerate(refs.get('kpis', [])):
        card = read(relative)
        key = identifier(card.get('id', f'kpi-{i}'))
        ops.append({'op': 'put_component', 'id': key, 'value': {'kind': 'text', 'title': card.get('label', key), 'text': f'{card.get("value", "")} {card.get("unit", "")}\nImported KPI snapshot; bind a governed metric to enable filtering.'}})
    if refs.get('filters'):
        notes.append('Legacy filters are not silently enabled. Rebind them to explicit dataset fields and supported consumers.')
    table_ref = refs.get('table')
    if table_ref:
        table = read(table_ref)
        if table.get('rows'):
            from .model import inferred_fields
            ops.extend([{'op': 'put_dataset', 'id': 'import-table', 'meta': {'fields': inferred_fields(table['rows']), 'sourceId': 'workspace-import'}, 'rows': table['rows']},
                        {'op': 'put_component', 'id': 'import-table', 'value': {'kind': 'table', 'title': table.get('title', 'Details'), 'datasetId': 'import-table'}}])
    return apply_operations(doc, ops), notes
