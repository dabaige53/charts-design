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
        {'op': 'put_metric', 'id': 'revenue', 'value': {'datasetId': 'sales', 'field': 'revenue', 'aggregation': 'sum', 'label': 'Revenue', 'unit': '10k CNY', 'definition': '所选月份和区域内，收入记录的金额合计，用于比较各期与各区域的收入规模。', 'status': 'unverified'}},
        {'op': 'put_metric', 'id': 'load-factor', 'value': {'datasetId': 'sales', 'aggregation': 'ratio', 'numerator': 'passengers', 'denominator': 'seats', 'label': 'Load factor', 'unit': '', 'format': 'percent', 'scale': 'fraction', 'definition': '所选月份和区域内，旅客量占可用座位数的比例，反映座位使用情况。先分别汇总旅客量与座位数，再计算比例。', 'status': 'unverified'}},
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
            {'id':'details','x':0,'y':11,'w':cols,'h':11}]}])
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
    ratio_definitions = {'attainment': '所选月份和区域内，营业收入占同期预算收入的比例，反映当前收入相对于预算目标的完成程度。', 'yield-growth': '所选月份和区域内，收入相对基期金额的增减幅度。正值表示收入增加，负值表示收入减少。'}
    for key, numerator, denominator, label in [('attainment', 'revenue', 'budget', '预算达成率'), ('yield-growth', 'yieldDelta', 'yieldBase', '收益变动率')]:
        ops.append({'op': 'put_metric', 'id': key, 'value': {'datasetId': 'sales', 'aggregation': 'ratio', 'numerator': numerator, 'denominator': denominator, 'label': label, 'unit': '', 'format': 'percent', 'scale': 'fraction', 'definition': ratio_definitions[key]}})
    ids = ['total', 'load', 'passengers', 'goal']
    cards = [('total', 'mc01', 'revenue', '主营收入', '万元'), ('load', 'mc02', 'load-factor', '客座率', ''), ('passengers', 'mc03', 'passengers', '旅客运输量', '万人次'), ('goal', 'mc04', 'attainment', '预算目标推进', '')]
    ops.append({'op': 'put_metric', 'id': 'passengers', 'value': {'datasetId': 'sales', 'field': 'passengers', 'aggregation': 'sum', 'label': '旅客运输量', 'unit': '万人次', 'definition': '所选月份和区域内，数据表记录的旅客运输量合计，用于比较运输业务规模。'}})
    for key, field_name, label, unit in [('budget', 'budget', '预算收入', '万元'), ('seats', 'seats', '可用座位数', '万座'), ('baseline-revenue', 'yieldBase', '基期收入', '万元')]:
        ops.append({'op': 'put_metric', 'id': key, 'value': {'datasetId': 'sales', 'field': field_name, 'aggregation': 'sum', 'label': label, 'unit': unit, 'definition': {'budget': '所选月份和区域对应的预算收入合计，作为同一范围营业收入的目标比较值。', 'seats': '所选月份和区域内记录的可用座位数合计，作为座位使用比例的计算基础。', 'baseline-revenue': '与所选月份和区域对应的基期收入合计，作为收入增减幅度的比较基础。'}[key]}})
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
            config.update({'percent': 100 * totals['revenue'] / totals['budget'], 'subLabel': '预算收入', 'subVal': ''})
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
            positions += [{'id': 'trend', 'x': 0, 'y': y, 'w': 6, 'h': 9}, {'id': 'regions', 'x': 6, 'y': y, 'w': 6, 'h': 9}, {'id': 'details', 'x': 0, 'y': y + 9, 'w': cols, 'h': 11}]
        else:
            positions += [{'id': 'trend', 'x': 0, 'y': y, 'w': cols, 'h': 9}, {'id': 'regions', 'x': 0, 'y': y + 9, 'w': cols, 'h': 7}, {'id': 'details', 'x': 0, 'y': y + 16, 'w': cols, 'h': 11}]
        ops.append({'op': 'set_layout', 'breakpoint': bp, 'value': positions})
    return apply_operations(doc, ops)


def operations_document(board_id='operations-demo'):
    """Contrasting master: dense KPI wall, different card shapes and chart codes.

    Same declared synthetic rows and metrics as the executive master, so the two
    cases differ only in composition. Every bound value recomputes under filters.
    """
    doc = executive_document(board_id)
    ops: list[dict] = [{'op': 'set_filters', 'value': []}]
    ops += [{'op': 'remove_component', 'id': key} for key in ('total', 'load', 'passengers', 'goal', 'trend', 'regions')]
    ops += [{'op': 'set_title', 'value': '航空运营指标墙 · 收入、运力与目标'},
            {'op': 'set_meta', 'value': {'iconKey': 'plane', 'subtitle': '一屏查看收入目标、同比基期与运力利用', 'org': '航空运营管理中心', 'statusText': '运营监控'}}]
    def kpi(key, title, config, measures, **binding):
        ops.append({'op': 'put_component', 'id': key, 'value': {'kind': 'legacy', 'family': 'kpi', 'title': title, 'sourceId': 'fixture',
                    'config': {'label': title, **config}, 'binding': {'datasetId': 'sales', 'measures': measures, **binding}}})
    kpi('north-star', '营业收入', {'type': 'mc16', 'value': '484 万元', 'yoy': '+24.1%', 'subLabel': '预算收入', 'subVal': '525 万元'},
        {'value': 'revenue', 'yoy': 'yield-growth', 'subVal': 'budget'})
    kpi('budget-ring', '预算完成度', {'type': 'mc11', 'value': '484 万元', 'percent': 92.19, 'subLabel': '预算收入', 'subVal': '525 万元'},
        {'value': 'revenue', 'percent': 'attainment', 'subVal': 'budget'}, scale={'percent': 100})
    kpi('budget-bullet', '收入对预算', {'type': 'mc13', 'value': '484 万元', 'actual': 484, 'target': 525, 'ranges': [0.8, 1.0], 'rangeBasis': 'target', 'unit': '万元', 'subLabel': '预算收入', 'subVal': '525 万元'},
        {'value': 'revenue', 'actual': 'revenue', 'target': 'budget', 'subVal': 'budget'})
    kpi('period-compare', '收入对基期', {'type': 'mc14', 'value': '484 万元', 'yoy': '+24.1%', 'currentLabel': '本期', 'currentValue': 484, 'priorLabel': '基期', 'priorValue': 390, 'unit': '万元'},
        {'value': 'revenue', 'currentValue': 'revenue', 'priorValue': 'baseline-revenue', 'yoy': 'yield-growth'})
    kpi('passenger-bars', '旅客运输量', {'type': 'mc12', 'value': '376 万人次', 'sparkMonths': ['2026-07-01', '2026-08-01', '2026-09-01'], 'sparkData': [117, 133, 126], 'subLabel': '可用座位', 'subVal': '450 万座'},
        {'value': 'passengers', 'subVal': 'seats'}, timeField='month')
    kpi('load-gauge', '客座率', {'type': 'mc05', 'value': '83.56%', 'percent': 83.56, 'subLabel': '可用座位', 'subVal': '450 万座'},
        {'value': 'load-factor', 'percent': 'load-factor', 'subVal': 'seats'}, scale={'percent': 100})
    def chart(key, title, subtitle, config, binding):
        ops.append({'op': 'put_component', 'id': key, 'value': {'kind': 'legacy', 'family': 'chart', 'title': title, 'subtitle': subtitle,
                    'sourceId': 'fixture', 'config': config, 'binding': {'datasetId': 'sales', **binding}}})
    chart('region-rank', '各基地收入排序', '按营业收入降序比较基地规模',
          {'code': 'c02', 'unit': '万元', 'data': {'categories': ['华东基地', '华南基地'], 'values': [278, 206]},
           'presentation': {'axisLabels': {'x': '收入', 'y': '基地'}, 'seriesLabels': ['营业收入'], 'tooltipValueLabels': ['营业收入'], 'units': ['万元'], 'tableHeaders': ['基地', '营业收入']}},
          {'categoryField': 'region', 'categoryTarget': 'categories', 'measures': {'values': 'revenue'}, 'orderBy': {'target': 'values', 'direction': 'desc'}})
    chart('budget-actual', '预算与实际收入', '同一基地的预算收入与实际收入并列',
          {'code': 'c03', 'unit': '万元', 'data': {'clusters': ['华东基地', '华南基地'], 'budget': [300, 225], 'actual': [278, 206]},
           'presentation': {'axisLabels': {'x': '基地', 'y': '收入'}, 'seriesLabels': ['预算收入', '实际收入'], 'tooltipValueLabels': ['预算收入', '实际收入'], 'units': ['万元', '万元'], 'tableHeaders': ['基地', '预算收入', '实际收入', '差额', '达成率']}},
          {'categoryField': 'region', 'categoryTarget': 'clusters', 'measures': {'budget': 'budget', 'actual': 'revenue'}})
    chart('passenger-trend', '月度旅客运输量', '按月追踪旅客规模，可切换季度',
          {'code': 't01', 'unit': '万人次', 'data': {'months': ['2026-07', '2026-08', '2026-09'], 'rpk': [117, 133, 126]},
           'presentation': {'axisLabels': {'x': '月份', 'y': '旅客'}, 'seriesLabels': ['旅客运输量'], 'tooltipValueLabels': ['旅客运输量'], 'units': ['万人次'], 'tableHeaders': ['月份', '旅客运输量', '环比']}},
          {'categoryField': 'month', 'categoryTarget': 'months', 'measures': {'rpk': 'passengers'}, 'timeGrain': True})
    consumers = ['north-star', 'budget-ring', 'budget-bullet', 'period-compare', 'passenger-bars', 'load-gauge', 'region-rank', 'budget-actual', 'passenger-trend', 'details']
    ops.append({'op': 'set_filters', 'value': [
        {'id': 'region', 'label': '区域', 'field': 'region', 'op': 'in', 'values': [], 'componentIds': consumers},
        {'id': 'period', 'label': '月份范围', 'field': 'month', 'op': 'range', 'values': [], 'componentIds': consumers}]})
    ops.append({'op': 'apply_layout_template', 'template': 'scorecard', 'order': consumers})
    return apply_operations(doc, ops)
