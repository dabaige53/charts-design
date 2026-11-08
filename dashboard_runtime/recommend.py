"""Question- and shape-aware chart suggestions over the 40 registered codes.

Generated dashboards tended to reuse c01/t06 for every question. This module
ranks codes by the analytical intent, the number of categories and measures,
and whether a date field exists, prefers codes with reviewed filter bindings,
and down-ranks codes the dashboard already uses so pages vary. It is
discovery data; the caller still declares data and presentation explicitly.
"""
from __future__ import annotations

from .model import require

# code: (intents, min categories, max categories, measures (min, max), needs time, why)
RULES = {
    'c01': (('comparison',), 2, 12, (1, 1), False, '少量类别的规模对比，柱顶直接标值'),
    'c02': (('comparison', 'ranking'), 3, 30, (1, 1), False, '降序排名或类别名较长时用横向条形'),
    'c03': (('comparison', 'target'), 2, 10, (2, 2), False, '同一类别下预算与实际等两项并列'),
    'c04': (('change',), 2, 15, (1, 1), False, '正负偏离/增长率围绕零基线对比'),
    'c05': (('comparison', 'ranking'), 6, 40, (1, 1), False, '类别较多时以棒棒糖减轻视觉重量'),
    'c06': (('change', 'comparison'), 2, 12, (2, 2), False, '两期取值的跨度与跃升（哑铃）'),
    'c07': (('target',), 2, 10, (2, 2), False, '目标底槽与实际完成重叠对比'),
    'c08': (('comparison',), 3, 15, (2, 2), False, '两个对立群体在同一类目的对称对比'),
    't01': (('trend',), 3, 60, (1, 1), True, '单一指标的连续时间走势'),
    't02': (('trend', 'forecast'), 3, 40, (2, 2), True, '历史实际与预测/指引对照'),
    't03': (('trend',), 3, 40, (1, 1), True, '政策、价格等离散阶跃变化'),
    't04': (('trend', 'composition'), 3, 40, (4, 4), True, '总量与结构随时间演变（堆叠面积）'),
    't05': (('change', 'ranking'), 2, 12, (2, 2), False, '两个时间截面之间的排位与斜率变化'),
    't06': (('trend', 'comparison'), 3, 36, (2, 2), True, '规模与增速/比率同屏（双轴）'),
    'k01': (('composition',), 2, 6, (1, 1), False, '少量构成与中心总额（环形）'),
    'k02': (('composition',), 2, 10, (3, 3), False, '多个类别各自的 100% 结构'),
    'k03': (('composition',), 5, 50, (1, 1), False, '多层级、多部件的面积拆解（矩形树图）'),
    'k04': (('composition', 'ranking'), 4, 20, (1, 1), False, '找出贡献 80% 的少数关键因素（帕累托）'),
    'k05': (('composition',), 2, 4, (1, 1), False, '2~4 项的大类切分（饼图）'),
    'k06': (('composition',), 2, 8, (1, 2), False, '主分类与二级细分两层嵌套'),
    'd01': (('distribution',), 4, 30, (1, 1), False, '连续数值的区间频数（直方图）'),
    'd02': (('distribution', 'comparison'), 2, 8, (1, 1), False, '各组中位数、四分位与离群值（箱线图）'),
    'd03': (('distribution',), 10, 200, (1, 1), False, '时长/金额的概率密度波峰'),
    'd04': (('distribution', 'trend'), 7, 200, (1, 1), True, '星期×小时等二维时段热力'),
    'r01': (('relationship', 'ranking'), 3, 30, (2, 2), False, '增速×利润率等四象限定位'),
    'r02': (('relationship',), 3, 40, (3, 3), False, 'x/y/规模三维气泡关系'),
    'r03': (('relationship',), 3, 12, (3, 12), False, '多个指标两两相关系数矩阵'),
    'r04': (('relationship', 'flow'), 3, 40, (1, 1), False, '组织/资金拓扑网络关系'),
    'r05': (('relationship', 'comparison'), 3, 10, (3, 8), False, '多维能力雷达对标'),
    'f01': (('flow', 'change'), 3, 8, (1, 1), False, '逐级转化与流失（漏斗）'),
    'f02': (('flow', 'composition'), 3, 30, (1, 1), False, '总额到各去向的流向分配（桑基）'),
    'f03': (('flow', 'trend'), 3, 24, (1, 1), True, '新客批次随时间的留存衰减（Cohort）'),
    'fn01': (('change', 'attribution'), 3, 15, (1, 1), False, '期初到期末的增减因素桥接（瀑布）'),
    'fn02': (('trend', 'comparison'), 3, 40, (2, 2), True, '收入与成本的剪刀差与盈亏平衡点'),
    'fn03': (('attribution', 'ranking'), 3, 15, (2, 2), False, '各变量对结果影响的敏感度（龙卷风）'),
    'fn04': (('trend', 'comparison'), 3, 40, (2, 6), True, '不同量级序列归一到 100 后比较增速'),
    'm01': (('target',), 1, 8, (1, 2), False, '实际、合格线与目标线（子弹图）'),
    'm02': (('forecast', 'trend'), 4, 24, (1, 3), True, '预测中枢与置信区间（扇形）'),
    'm03': (('target', 'trend'), 4, 60, (1, 1), True, '超阈值红线的监控与告警'),
    'm04': (('target',), 1, 1, (1, 1), False, '单一综合达成进度（半环仪表）'),
}
INTENTS = ('comparison', 'ranking', 'trend', 'composition', 'distribution', 'relationship', 'flow', 'change', 'attribution', 'target', 'forecast')
KPI_BY_INTENT = {
    'trend': ['mc03', 'mc12'], 'target': ['mc04', 'mc11', 'mc13'], 'change': ['mc02', 'mc14'],
    'composition': ['mc09', 'mc15'], 'distribution': ['mc10'], 'comparison': ['mc06', 'mc14'],
    'ranking': ['mc07'], 'forecast': ['mc03'], 'attribution': ['mc15'], 'relationship': ['mc06'], 'flow': ['mc04'],
}


def recommend_charts(args: dict, doc: dict | None = None) -> dict:
    intent = args.get('intent')
    require(intent in INTENTS, f'intent must be one of: {", ".join(INTENTS)}', 'INVALID_INTENT')
    categories = args.get('categories')
    measures = args.get('measures', 1)
    has_time = args.get('hasTime')
    require(categories is None or (type(categories) is int and categories >= 1), 'categories must be a positive integer')
    require(type(measures) is int and measures >= 1, 'measures must be a positive integer')
    require(has_time is None or type(has_time) is bool, 'hasTime must be boolean')
    used: dict[str, int] = {}
    if doc is not None:
        meta = doc['manifest']['datasets'].get(args.get('datasetId')) if args.get('datasetId') else None
        if meta and has_time is None:
            has_time = any(field.get('type') == 'date' for field in meta['fields'].values())
        for component in doc['manifest']['components'].values():
            if component.get('kind') == 'legacy' and component.get('family', 'chart') == 'chart':
                code = component.get('config', {}).get('code')
                used[code] = used.get(code, 0) + 1
    from .bindings import SERIES_TARGETS
    from .legacy import catalog
    names = {entry['id']: entry.get('nameZh') for entry in catalog()}
    ranked = []
    for code, (intents, low, high, (fewest, most), needs_time, why) in RULES.items():
        if intent not in intents:
            continue
        score, notes = 3 if intents[0] == intent else 2, []
        if categories is not None and not low <= categories <= high:
            score -= 2
            notes.append(f'建议类别数 {low}~{high}')
        if not fewest <= measures <= most:
            score -= 2
            notes.append(f'建议指标数 {fewest}~{most}')
        if needs_time and has_time is False:
            score -= 3
            notes.append('需要日期字段')
        bindable = code in SERIES_TARGETS
        if bindable:
            score += 1
        if used.get(code):
            score -= used[code]
            notes.append(f'本页已使用 {used[code]} 次，优先换用其他形态')
        ranked.append({'code': code, 'name': names.get(code), 'why': why, 'score': score,
                       'filterBinding': 'supported' if bindable else 'snapshotOnly', 'notes': notes})
    ranked.sort(key=lambda item: (-item['score'], item['code']))
    return {'intent': intent, 'inputs': {'categories': categories, 'measures': measures, 'hasTime': has_time},
            'charts': ranked[:6], 'kpiShapes': KPI_BY_INTENT.get(intent, []), 'usedOnPage': used,
            'next': 'chart_declarations {"code": "<chosen>"} returns the declaration contract and a working example.'}
