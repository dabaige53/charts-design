"""Explicit component data for workspace import and binding checks."""
import json
from pathlib import Path

from dashboard_runtime.model import apply_operations, new_document


def document(board_id='original-review'):
    quickstart = Path(__file__).resolve().parents[2] / 'skills/executive-charts/references/quickstart'
    chart = json.loads((quickstart / 'regional-sales.chart.json').read_text())
    chart['id'] = 'chart-c01'
    chart.pop('binding')
    table = json.loads((quickstart / 'sales.table.json').read_text())
    cards = [
        {'id': 'kpi-trend', 'type': 'mc03', 'label': 'Synthetic trend', 'value': '224',
         'sparkData': [128, 96], 'sparkMonths': ['2026-08', '2026-09'], 'subVal': '200'},
        {'id': 'kpi-target', 'type': 'mc04', 'label': 'Synthetic target', 'value': '86.5%',
         'percent': 86.5, 'statusBadge': 'Fixture'},
    ]
    operations = [
        {'op': 'put_source', 'id': 'original-fixture', 'value': {'kind': 'fixture', 'name': 'Explicit synthetic configurations'}},
        {'op': 'set_status', 'value': 'fixture'},
        {'op': 'put_component', 'id': 'c01', 'value': {
            'kind': 'legacy', 'family': 'chart', 'title': chart['title'],
            'config': chart, 'sourceId': 'original-fixture'}},
        {'op': 'put_component', 'id': 'original-table', 'value': {
            'kind': 'legacy', 'family': 'table', 'title': table['title'],
            'config': table, 'sourceId': 'original-fixture'}},
    ]
    operations.extend({'op': 'put_component', 'id': card['id'], 'value': {
        'kind': 'legacy', 'family': 'kpi', 'title': card['label'],
        'config': card, 'sourceId': 'original-fixture'}} for card in cards)
    return apply_operations(new_document(board_id, 'Workspace import fixture'), operations)
