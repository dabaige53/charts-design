"""Synthetic Charts Design acceptance project with a report and linked dashboard pages."""

import copy
from argparse import ArgumentParser
from collections import Counter
from itertools import product
import json
from pathlib import Path
from typing import Any

from dashboard_runtime.demo import report_document
from dashboard_runtime.model import apply_operations

BOARD = 'quarterly-route-review'
ENDPOINT = 'https://charts-design.49-51-184-179.sslip.io/mcp'
MONTHS = ['2026-07', '2026-08', '2026-09']
REGIONS = ['华东', '华南']
CHANNELS = ['直营', '代理']
ROUTES = ['干线', '区域航线']
CABINS = ['经济舱', '商务舱']
TITLE = '第三季度航线经营复盘'
FILTER_FIELDS = [('month', '运营月份'), ('region', '运营区域'), ('route', '航线类型'),
                 ('channel', '销售渠道'), ('cabin', '舱位')]


def figure(key, caption):
    return '```chart\n' + json.dumps({'componentId': key, 'caption': caption}, ensure_ascii=False) + '\n```'


def kpi(title, card_type, measures, config, **binding) -> dict[str, Any]:
    return {'kind': 'legacy', 'family': 'kpi', 'title': title, 'sourceId': 'fixture',
            'config': {'type': card_type, 'label': title, **config},
            'binding': {'datasetId': 'sales', 'measures': measures, **binding}}


def load_card(card_type, fraction):
    return kpi('整体客座率', card_type, {'value': 'load-factor', 'percent': 'load-factor'},
               {'value': f'{fraction:.2%}', 'percent': 100 * fraction},
               scale={'percent': 100})


def document():
    rows = []
    for month, region, channel, route, cabin in product(MONTHS, REGIONS, CHANNELS, ROUTES, CABINS):
        m, r, c, t, s = MONTHS.index(month), REGIONS.index(region), CHANNELS.index(channel), ROUTES.index(route), CABINS.index(cabin)
        seats = (1050 if s == 0 else 170) + 23 * m - 52 * t - 19 * r
        passengers = seats * (76 + 3 * m + 3 * r - 4 * t - 2 * c + s) // 100
        fare = (1390 if s == 0 else 3080) - 210 * t - 55 * c + 55 * r
        rows.append(dict(month=month, region=region, channel=channel, route=route, cabin=cabin,
                         passengers=passengers, seats=seats, revenue=round(passengers * fare / 10000, 2)))
    def rollup(key):
        totals = Counter()
        for row in rows:
            totals[row[key]] += row['revenue']
        return totals
    months, regions, channels = (rollup(field) for field in ('month', 'region', 'channel'))
    total = sum(months.values())
    passenger = sum(row['passengers'] for row in rows)
    seats = sum(row['seats'] for row in rows)
    last_change = (months[MONTHS[-1]] / months[MONTHS[0]] - 1) * 100
    fields = {k: {'type': 'string', 'label': label} for k, label in FILTER_FIELDS}
    fields.update({k: {'type': 'number', 'label': label} for k, label in [
        ('revenue', '营业收入（万元）'), ('passengers', '旅客量（人次）'), ('seats', '可用座位数（个）')]})
    doc = report_document(BOARD)
    binding = [ ('trend', '月度营业收入', 'month', '运营月份', 'months', 'rpk', months),
                ('regions', '区域收入结构', 'region', '运营区域', 'categories', 'values', regions),
                ('channels', '销售渠道收入', 'channel', '销售渠道', 'categories', 'values', channels) ]
    chart_ops = []
    for key, title, field, label, field_key, value_key, values in binding:
        template = doc['manifest']['components']['trend' if key == 'trend' else 'regions']
        component = copy.deepcopy(template)
        component['title'] = title
        component['binding']['categoryField'] = field
        component['config']['data'] = {field_key: list(values), value_key: [round(value, 2) for value in values.values()]}
        component['config']['presentation']['axisLabels']['x'] = label
        component['config']['presentation']['tableHeaders'][0] = label
        chart_ops.append({'op': 'put_component', 'id': key, 'value': component})
    md = f"""# {TITLE}

*2026 年 7—9 月*

**摘要**　本季度累计收入 **{total:,.1f} 万元**，运输 **{passenger:,} 人次**，整体客座率 **{passenger / seats:.1%}**。9 月收入较 7 月增长 {last_change:.1f}%，华东贡献季度收入的 {regions['华东'] / total:.1%}。

**关键词**　航线经营、营业收入、客座率

## 数据与分析方法

数据来自 {len(rows)} 条合成航线经营记录，按月份、区域、航线类型、渠道和舱位汇总。收入以万元计，客座率为总旅客人次除以总可用座位数。正文数值基于完整季度。

## 月度收入变化

7、8、9 月收入分别为 **{months[MONTHS[0]]:,.1f}**、**{months[MONTHS[1]]:,.1f}** 和 **{months[MONTHS[2]]:,.1f} 万元**。见[图](#fig-trend)。

{figure('trend', '月度营业收入')}

## 区域与渠道结构

华东与华南的季度收入分别为 **{regions['华东']:,.1f} 万元**和 **{regions['华南']:,.1f} 万元**。见[图](#fig-regions)。

{figure('regions', '区域收入对比')}

直营与代理收入分别为 **{channels['直营']:,.1f} 万元**和 **{channels['代理']:,.1f} 万元**。见[图](#fig-channels)。

{figure('channels', '渠道收入对比')}

## 结论

季度末月收入较首月增长 {last_change:.1f}%。从收入构成看，直营贡献全季收入的 {channels['直营'] / total:.1%}，两个运营区域的收入相差 {abs(regions['华东'] - regions['华南']):,.1f} 万元。

## 月度收入附表

| 运营月份 | 营业收入（万元） |
| --- | ---: |
| 2026 年 7 月 | {months[MONTHS[0]]:,.2f} |
| 2026 年 8 月 | {months[MONTHS[1]]:,.2f} |
| 2026 年 9 月 | {months[MONTHS[2]]:,.2f} |
"""
    operations = [
        {'op': 'put_dataset', 'id': 'sales', 'meta': {'sourceId': 'fixture', 'fields': fields}, 'rows': rows},
        *chart_ops,
        {'op': 'set_title', 'value': TITLE},
        {'op': 'set_report_markdown', 'value': md},
        {'op': 'set_view_mode', 'value': 'report'},
        {'op': 'put_component', 'id': 'total', 'value': kpi('营业收入', 'mc01', {'value': 'revenue'},
                                                            {'value': f'{total:,.2f} 万元'})},
        {'op': 'put_component', 'id': 'load', 'value': load_card('mc05', passenger / seats)},
        {'op': 'put_component', 'id': 'details', 'value': {**doc['manifest']['components']['details'], 'title': '航线经营明细'}},
        {'op': 'set_filters', 'value': []},
    ]
    saved = apply_operations(doc, operations)
    saved['manifest']['metrics']['revenue'].update(label='营业收入', unit='万元')
    saved['manifest']['metrics']['load-factor'].update(label='整体客座率')
    return saved, rows, round(total, 2)


OVERVIEW = 'route-overview'
ROUTE_PAGE = 'route-capacity'
MARKET_PAGE = 'route-markets'
DETAIL_PAGE = 'route-details'


def dashboard_pages(report, rows):
    source = report['manifest']
    metric_ops = [
        {'op': 'put_metric', 'id': field, 'value': {
            'datasetId': 'sales', 'field': field, 'aggregation': 'sum', 'label': title,
            'unit': unit, 'definition': f'筛选范围内各条记录的{title}之和。',
        }}
        for field, title, unit in [('passengers', '旅客运输量', '人次'), ('seats', '可用座位数', '个')]
    ]

    def chart(title, code, field, dimension, target, metrics):
        categories = list(dict.fromkeys(row[field] for row in rows))
        data = {target: categories}
        labels, units = [], []
        for value_key, (metric, label, unit) in metrics.items():
            data[value_key] = [sum(row[metric] for row in rows if row[field] == name) for name in categories]
            labels.append(label)
            units.append(unit)
        horizontal = code == 'c02'
        return {'kind': 'legacy', 'family': 'chart', 'title': title, 'sourceId': 'fixture',
                'config': {'code': code, 'unit': units[0], 'data': data,
                           'presentation': {'axisLabels': {'x': labels[0] if horizontal else dimension,
                                                           'y': dimension if horizontal else labels[0]},
                                            'seriesLabels': labels, 'tooltipValueLabels': labels, 'units': units,
                                            'tableHeaders': [dimension, *labels, *({'c03': ['差额', '达成率'], 't01': ['环比']}.get(code, []))]}},
                'binding': {'datasetId': 'sales', 'categoryField': field, 'categoryTarget': target,
                            'measures': {key: measure[0] for key, measure in metrics.items()}}}

    revenue = {'values': ('revenue', '营业收入', '万元')}
    monthly_passengers = [sum(row['passengers'] for row in rows if row['month'] == month) for month in MONTHS]
    passenger_count = sum(monthly_passengers)
    seat_count = sum(row['seats'] for row in rows)
    passenger_snapshot = {'value': f'{passenger_count:,} 人次', 'sparkMonths': MONTHS,
                          'sparkData': monthly_passengers}
    seats = kpi('座位与旅客量', 'mc06', {'leftVal': 'seats', 'rightVal': 'passengers'},
                {'leftTitle': '可用座位数', 'leftVal': f'{seat_count:,} 个',
                 'rightTitle': '旅客运输量', 'rightVal': passenger_snapshot['value']})
    components = {
        **source['components'],
        'passengers': kpi('旅客运输量', 'mc03', {'value': 'passengers'}, passenger_snapshot, timeField='month'),
        'seats': seats,
        'route-revenue': chart('航线收入排名', 'c02', 'route', '航线类型', 'categories', revenue),
        'cabin-revenue': chart('各舱位收入', 'c01', 'cabin', '舱位', 'categories', revenue),
        'passenger-trend': chart('月度旅客量', 't01', 'month', '运营月份', 'months',
                                 {'rpk': ('passengers', '旅客运输量', '人次')}),
        'route-capacity': chart('航线运量与座位', 'c03', 'route', '航线类型', 'clusters',
                                {'budget': ('seats', '可用座位数', '个'), 'actual': ('passengers', '旅客运输量', '人次')}),
        'channel-rank': chart('渠道收入排名', 'c02', 'channel', '销售渠道', 'categories', revenue),
    }
    components['route-revenue']['binding']['orderBy'] = {'target': 'values', 'direction': 'desc'}
    components['channel-rank']['binding']['orderBy'] = {'target': 'values', 'direction': 'desc'}
    card_overrides = {
        OVERVIEW: {'total': kpi('营业收入', 'mc16', {'value': 'revenue'}, {
            'value': source['components']['total']['config']['value'],
        })},
        ROUTE_PAGE: {
            'passengers': kpi('旅客运输量', 'mc12', {'value': 'passengers'}, passenger_snapshot, timeField='month'),
            'load': load_card('mc11', passenger_count / seat_count),
        },
    }
    specs = {
        OVERVIEW: ('航线经营｜总览', ['total', 'load', 'passengers'], ['trend', 'regions', 'channels']),
        ROUTE_PAGE: ('航线经营｜运量与运力', ['passengers', 'seats', 'load'], ['route-capacity', 'passenger-trend', 'route-revenue']),
        MARKET_PAGE: ('航线经营｜区域与渠道', ['total'], ['regions', 'channel-rank', 'cabin-revenue']),
        DETAIL_PAGE: ('航线经营｜可筛选明细', ['total', 'passengers', 'load'], ['details']),
    }
    result = {}
    for board, (title, kpis, figures) in specs.items():
        selected = kpis + figures
        page_components = {**components, **card_overrides.get(board, {})}
        page = copy.deepcopy(report)
        page['id'] = board
        manifest = page['manifest']
        manifest.pop('report')
        manifest['components'] = {}
        manifest['filters'] = []
        manifest['layout'] = {bp: [] for bp in ('desktop', 'tablet', 'mobile')}
        filters = [
            {'id': field, 'label': label, 'field': field, 'op': 'in', 'values': [],
             'alwaysVisible': index < 4, 'componentIds': selected}
            for index, (field, label) in enumerate(FILTER_FIELDS)
        ]
        ops = [
            *metric_ops,
            {'op': 'set_title', 'value': title},
            {'op': 'set_meta', 'value': {'iconKey': 'plane'}},
            {'op': 'set_view_mode', 'value': 'dashboard'},
            *({'op': 'put_component', 'id': key, 'value': copy.deepcopy(page_components[key])} for key in selected),
            {'op': 'set_filters', 'value': filters},
        ]
        for bp, columns in [('desktop', 12), ('tablet', 8), ('mobile', 4)]:
            tiles = []
            card_width = columns // len(kpis) if bp == 'desktop' else columns
            top = 0
            for index, key in enumerate(kpis):
                left = index * card_width if bp == 'desktop' else 0
                top = 0 if bp == 'desktop' else index * 4
                tiles.append({'id': key, 'x': left, 'y': top, 'w': card_width, 'h': 4})
            y = top + 4
            for index, key in enumerate(figures):
                half = bp == "desktop" and index < len(figures) - len(figures) % 2
                width = columns // 2 if half else columns
                left = (index % 2) * width if half else 0
                height = 13 if key == 'details' else 9
                tiles.append({'id': key, 'x': left, 'y': y, 'w': width, 'h': height})
                if not half or index % 2:
                    y += height
            ops.append({'op': 'set_layout', 'breakpoint': bp, 'value': tiles})
        result[board] = apply_operations(page, ops)
    return result


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    target = parser.parse_args().output
    target.mkdir(parents=True, exist_ok=True)
    report, records, _ = document()
    pages = {report['id']: report, **dashboard_pages(report, records)}
    for board, page in pages.items():
        (target / f'{board}.json').write_text(json.dumps(page, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
