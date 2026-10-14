"""Explicit fixture, never inserted into a real dashboard implicitly."""
from typing import Any
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
    doc = document(board_id)
    ops = []
    for key, code, category, target, measure_target in [('trend', 't01', 'month', 'months', 'rpk'), ('regions', 'c01', 'region', 'categories', 'values')]:
        categories = ['2026-07', '2026-08', '2026-09'] if key == 'trend' else ['East', 'South']
        values = [140, 174, 170] if key == 'trend' else [278, 206]
        config = {'code': code, 'unit': '万元', 'data': {target: categories, measure_target: values}, 'presentation': {'axisLabels': {'x': '月份' if key == 'trend' else '区域', 'y': '收入'}, 'seriesLabels': ['收入'], 'tooltipValueLabels': ['收入'], 'units': ['万元'], 'tableHeaders': ['月份', '收入', '变化率'] if key == 'trend' else ['区域', '收入']}}
        ops.append({'op': 'put_component', 'id': key, 'value': {'kind': 'legacy', 'family': 'chart', 'title': doc['manifest']['components'][key]['title'], 'config': config, 'sourceId': 'fixture', 'binding': {'datasetId': 'sales', 'categoryField': category, 'categoryTarget': target, 'measures': {measure_target: 'revenue'}}}})
    doc = apply_operations(doc, ops)
    return apply_operations(doc, [
        {'op': 'set_title', 'value': '季度收入变化与区域结构的描述性分析'},
        {'op': 'set_report_markdown', 'value': markdown},
        {'op': 'set_view_mode', 'value': 'report'}
    ])

def executive_document(board_id='executive-demo'):
    """Authored executive master; all values derive from declared synthetic rows."""
    from .declarations import _advanced_configs
    doc = document(board_id)
    rows = doc['snapshot']['datasets']['sales']
    for row in rows:
        row['month'] += '-01'
        row['budget'] = 100 if row['region'] == 'East' else 75
        row['yieldDelta'] = row['revenue'] - (75 if row['region'] == 'East' else 55)
        row['yieldBase'] = 75 if row['region'] == 'East' else 55
        row['region'] = '华东基地' if row['region'] == 'East' else '华南基地'
    fields = {key: {'type': 'date' if key == 'month' else 'string' if key == 'region' else 'number'} for key in rows[0]}
    labels = {'month': '月份', 'region': '区域', 'revenue': '营业收入', 'passengers': '旅客量', 'seats': '座位数', 'budget': '预算', 'yieldDelta': '收益增量', 'yieldBase': '基期金额'}
    for key, metadata in fields.items():
        metadata['label'] = labels[key]
    ops = [{'op': 'put_metric', 'id': 'revenue', 'value': {**doc['manifest']['metrics']['revenue'], 'label': '营业收入', 'unit': '万元'}}, {'op': 'set_title', 'value': '民航航空集团月度运营与收益复盘全景看板'},
           {'op': 'set_meta', 'value': {'iconKey': 'plane', 'subtitle': '收入规模、运力利用与目标推进', 'org': '航空运营管理中心', 'system': '经营决策与运行控制系统 (AOC / RMS)', 'statusText': '月度经营复盘'}},
           {'op': 'put_dataset', 'id': 'sales', 'meta': {'sourceId': 'fixture', 'fields': fields}, 'rows': rows}]
    for key, numerator, denominator, label in [('attainment', 'revenue', 'budget', '预算达成率'), ('yield-growth', 'yieldDelta', 'yieldBase', '收益变动率')]:
        ops.append({'op': 'put_metric', 'id': key, 'value': {'datasetId': 'sales', 'aggregation': 'ratio', 'numerator': numerator, 'denominator': denominator, 'label': label, 'unit': '', 'format': 'percent', 'scale': 'fraction', 'definition': f'合成数据 sum({numerator}) / sum({denominator})；筛选后重算。'}})
    ids = ['total', 'load', 'passengers', 'goal']
    cards = [('total', 'mc01', 'revenue', '主营收入', '万元'), ('load', 'mc02', 'load-factor', '客座率', ''), ('passengers', 'mc03', 'passengers', '旅客运输量', '万人次'), ('goal', 'mc04', 'attainment', '预算目标推进', '')]
    ops.append({'op': 'put_metric', 'id': 'passengers', 'value': {'datasetId': 'sales', 'field': 'passengers', 'aggregation': 'sum', 'label': '旅客运输量', 'unit': '万人次', 'definition': '合成旅客量求和，筛选后重算。'}})
    for key, field_name, label, unit in [('budget', 'budget', '预算收入', '万元'), ('seats', 'seats', '可用座位数', '万座'), ('baseline-revenue', 'yieldBase', '基期收入', '万元')]:
        ops.append({'op': 'put_metric', 'id': key, 'value': {'datasetId': 'sales', 'field': field_name, 'aggregation': 'sum', 'label': label, 'unit': unit, 'definition': f'按所选范围汇总 {field_name}。'}})
    totals = {field: sum(row[field] for row in rows) for field in ('revenue', 'passengers', 'seats', 'budget')}
    headline = {'revenue': str(totals['revenue']), 'passengers': str(totals['passengers']), 'load-factor': f"{totals['passengers'] / totals['seats']:.2%}", 'attainment': f"{totals['revenue'] / totals['budget']:.2%}"}
    for key, card_type, metric, label, unit in cards:
        config: dict[str, Any] = {'type': card_type, 'label': label, 'value': headline[metric], 'unit': unit, 'statusBadge': '月度核算'}
        footer_metric = 'baseline-revenue' if key == 'total' else 'budget' if key == 'goal' else 'seats'
        config['subLabel'] = '基期收入' if key == 'total' else '预算收入' if key == 'goal' else '可用座位'
        binding: dict[str, Any] = {'datasetId': 'sales', 'measures': {'value': metric, 'subVal': footer_metric}}
        if key == 'total':
            binding['measures']['yoy'] = 'yield-growth'
        if card_type == 'mc03':
            config.update({'sparkMonths': ['2026-07', '2026-08', '2026-09'], 'sparkData': [117, 133, 126]})
            binding['timeField'] = 'month'
        if card_type == 'mc04':
            config.update({'percent': 100 * totals['revenue'] / totals['budget'], 'subLabel': '预算收入', 'subVal': '', 'trendLabel': '按所选范围重算'})
            binding['measures']['percent'] = metric
            binding['scale'] = {'percent': 100}
        ops.append({'op': 'put_component', 'id': key, 'value': {'kind': 'legacy', 'family': 'kpi', 'title': label, 'sourceId': 'fixture', 'datasetId': 'sales', 'config': config, 'binding': binding}})
    for key, title, subtitle in [('regions', '区域收入贡献', '比较各区域收入贡献与业务规模'), ('details', '经营数据明细', '与指标卡和图表使用同一筛选范围')]:
        ops.append({'op': 'put_component', 'id': key, 'value': {**doc['manifest']['components'][key], 'title': title, 'subtitle': subtitle}})
    config = _advanced_configs()['t06']
    config['unit'] = '万元'
    config['presentation'] = {'axisLabels': {'x': '周期', 'leftY': '收入', 'rightY': '收益变动率'}, 'seriesLabels': ['收入', '收益变动率'], 'tooltipValueLabels': ['收入', '收益变动率'], 'units': ['万元', '%'], 'tableHeaders': ['周期', '收入', '收益变动率']}
    ops.append({'op': 'put_component', 'id': 'trend', 'value': {'kind': 'legacy', 'family': 'chart', 'title': '收入与收益变动 · 月度 / 季度', 'subtitle': '按月度与季度追踪收入规模及收益变动', 'sourceId': 'fixture', 'datasetId': 'sales', 'config': config, 'binding': {'datasetId': 'sales', 'categoryField': 'month', 'categoryTarget': 'categories', 'timeGrain': 'month', 'measures': {'revenue': 'revenue', 'yieldGrowth': 'yield-growth'}, 'scale': {'yieldGrowth': 100}}}})
    region_config = {'code': 'c01', 'title': '区域收入贡献', 'unit': '万元', 'data': {'categories': ['华东基地', '华南基地'], 'values': [278, 206]}, 'presentation': {'axisLabels': {'x': '基地', 'y': '收入'}, 'seriesLabels': ['营业收入'], 'tooltipValueLabels': ['营业收入'], 'units': ['万元'], 'tableHeaders': ['基地', '营业收入']}}
    ops.append({'op': 'put_component', 'id': 'regions', 'value': {'kind': 'legacy', 'family': 'chart', 'title': '各基地营业收入贡献对比', 'subtitle': '比较各基地收入贡献与业务规模', 'sourceId': 'fixture', 'config': region_config, 'binding': {'datasetId': 'sales', 'categoryField': 'region', 'categoryTarget': 'categories', 'measures': {'values': 'revenue'}}}})
    consumers = ids + ['trend', 'regions', 'details']
    ops.append({'op': 'set_filters', 'value': [{'id': 'region', 'label': '区域', 'field': 'region', 'op': 'in', 'values': [], 'componentIds': consumers}, {'id': 'period', 'label': '月份范围', 'field': 'month', 'op': 'range', 'values': [], 'componentIds': consumers}, {'id': 'search', 'label': '搜索区域', 'field': 'region', 'op': 'contains', 'values': [], 'componentIds': consumers}]})
    for bp, cols, card_cols in [('desktop', 12, 3), ('tablet', 8, 4), ('mobile', 4, 4)]:
        card_rows = len(ids) // (cols // card_cols)
        positions = [{'id': key, 'x': (index % (cols // card_cols)) * card_cols, 'y': (index // (cols // card_cols)) * 4, 'w': card_cols, 'h': 4} for index, key in enumerate(ids)]
        y = card_rows * 4
        if bp == 'desktop':
            positions += [{'id': 'trend', 'x': 0, 'y': y, 'w': 6, 'h': 9}, {'id': 'regions', 'x': 6, 'y': y, 'w': 6, 'h': 9}, {'id': 'details', 'x': 0, 'y': y + 9, 'w': cols, 'h': 7}]
        else:
            positions += [{'id': 'trend', 'x': 0, 'y': y, 'w': cols, 'h': 9}, {'id': 'regions', 'x': 0, 'y': y + 9, 'w': cols, 'h': 7}, {'id': 'details', 'x': 0, 'y': y + 16, 'w': cols, 'h': 7}]
        ops.append({'op': 'set_layout', 'breakpoint': bp, 'value': positions})
    return apply_operations(doc, ops)
