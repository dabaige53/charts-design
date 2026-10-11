"""Explicit fixture, never inserted into a real dashboard implicitly."""
from .model import apply_operations, new_document

def document(board_id='demo'):
    doc = new_document(board_id, 'Revenue and Capacity / DEMO')
    rows = [
        {'month': '2026-07', 'region': 'East', 'revenue': 80, 'passengers': 72, 'seats': 100},
        {'month': '2026-07', 'region': 'South', 'revenue': 60, 'passengers': 45, 'seats': 50},
        {'month': '2026-08', 'region': 'East', 'revenue': 102, 'passengers': 85, 'seats': 100},
        {'month': '2026-08', 'region': 'South', 'revenue': 72, 'passengers': 48, 'seats': 50},
        {'month': '2026-09', 'region': 'East', 'revenue': 96, 'passengers': 80, 'seats': 100},
        {'month': '2026-09', 'region': 'South', 'revenue': 74, 'passengers': 46, 'seats': 50}
    ]
    ops = [
        {'op': 'put_source', 'id': 'fixture', 'value': {'kind': 'fixture', 'name': 'Synthetic acceptance-test data; not a real query'}},
        {'op': 'put_dataset', 'id': 'sales', 'meta': {'sourceId': 'fixture', 'fields': {k: {'type': 'string' if k in ('month', 'region') else 'number'} for k in rows[0]}}, 'rows': rows},
        {'op': 'put_metric', 'id': 'revenue', 'value': {'datasetId': 'sales', 'field': 'revenue', 'aggregation': 'sum', 'label': 'Revenue', 'unit': '10k CNY', 'definition': 'Sum of synthetic revenue for the selected months and regions.', 'status': 'unverified'}},
        {'op': 'put_metric', 'id': 'load-factor', 'value': {'datasetId': 'sales', 'aggregation': 'ratio', 'numerator': 'passengers', 'denominator': 'seats', 'label': 'Load factor', 'unit': '', 'format': 'percent', 'scale': 'fraction', 'definition': 'Sum(passengers) / sum(seats), recomputed after filters. Synthetic example only.', 'status': 'unverified'}},
        {'op': 'put_component', 'id': 'total', 'value': {'kind': 'kpi', 'title': 'Revenue', 'datasetId': 'sales', 'measures': ['revenue']}},
        {'op': 'put_component', 'id': 'load', 'value': {'kind': 'kpi', 'title': 'Load factor', 'datasetId': 'sales', 'measures': ['load-factor']}},
        {'op': 'put_component', 'id': 'trend', 'value': {'kind': 'chart', 'title': 'Revenue by month', 'datasetId': 'sales', 'x': 'month', 'measures': ['revenue'], 'chartType': 'line'}},
        {'op': 'put_component', 'id': 'regions', 'value': {'kind': 'chart', 'title': 'Regional mix', 'datasetId': 'sales', 'x': 'region', 'measures': ['revenue'], 'chartType': 'bar'}},
        {'op': 'put_component', 'id': 'details', 'value': {'kind': 'table', 'title': 'Reviewed snapshot rows', 'datasetId': 'sales'}},
        {'op': 'set_filters', 'value': [{'id': 'region', 'label': 'Region', 'field': 'region', 'op': 'in', 'values': [], 'componentIds': ['total','load','trend','regions','details']}]},
        {'op': 'set_status', 'value': 'fixture'}
    ]
    doc = apply_operations(doc, ops)
    for bp, cols in [('desktop',12),('tablet',8)]:
        half = cols//2
        doc = apply_operations(doc, [{'op':'set_layout','breakpoint':bp,'value':[
            {'id':'total','x':0,'y':0,'w':half,'h':4}, {'id':'load','x':half,'y':0,'w':half,'h':4},
            {'id':'trend','x':0,'y':4,'w':half,'h':7}, {'id':'regions','x':half,'y':4,'w':half,'h':7},
            {'id':'details','x':0,'y':11,'w':cols,'h':7}]}])
    return doc

def report_document(board_id='report-demo'):
    """A Markdown-first document, using only explicitly synthetic data."""
    from pathlib import Path
    markdown = (Path(__file__).parent / 'examples' / 'academic-report.md').read_text(encoding='utf-8')
    return apply_operations(document(board_id), [
        {'op': 'set_title', 'value': '季度收入变化与区域结构的描述性分析'},
        {'op': 'set_report_markdown', 'value': markdown},
        {'op': 'set_view_mode', 'value': 'report'}
    ])
