"""KPI card selection guide: purpose, fields and working examples per type.

Agents previously saw one generic example for all card types and copied the
first four. Each entry here states what question the card answers, which
config fields shape it, which fields a binding can recompute, and a legal
synthetic example. Validation remains in the shared schema and legacy
validator; this module is discovery data.
"""
from __future__ import annotations

import copy

COMMON = {
    'label': 'Card label (the component title replaces it in the runtime header)',
    'value': 'Displayed headline text, including unit, e.g. "484 万元"',
    'yoy': 'Optional signed comparison: number or text such as "+4.8%" (red = increase, green = decrease)',
    'subLabel': 'Footer label', 'subVal': 'Footer value text',
}

GUIDE = {
    'mc01': {'name': '基础数值卡', 'question': 'How big is one headline metric now?',
             'fields': {**COMMON, 'statusBadge': 'Short neutral status text'},
             'bind': ['value', 'yoy', 'subVal'],
             'example': {'label': '营业收入', 'value': '484 万元', 'yoy': '+24.1%', 'statusBadge': '月度核算', 'subLabel': '基期收入', 'subVal': '390 万元'}},
    'mc02': {'name': '同环比波动卡', 'question': 'Is the metric rising or falling against last year and last period?',
             'fields': {**COMMON, 'mom': 'Signed period-over-period comparison'},
             'bind': ['value', 'yoy', 'mom', 'subVal'],
             'example': {'label': '客座率', 'value': '83.6%', 'yoy': '+2.1%', 'mom': '-0.4%', 'subLabel': '可用座位', 'subVal': '450 万座'}},
    'mc03': {'name': '微走势迷你面积卡', 'question': 'What is the value and its recent continuous trend?',
             'fields': {**COMMON, 'sparkMonths': 'Period labels', 'sparkData': 'Finite values, same length', 'trendLabel': 'Neutral trend note'},
             'bind': ['value', 'yoy', 'subVal', 'timeField → sparkMonths/sparkData'],
             'example': {'label': '旅客运输量', 'value': '376 万人次', 'sparkMonths': ['2026-07', '2026-08', '2026-09'], 'sparkData': [117, 133, 126], 'subLabel': '可用座位', 'subVal': '450 万座'}},
    'mc04': {'name': '目标进度条形卡', 'question': 'How far along is a target, as a percentage?',
             'fields': {**COMMON, 'value': 'Numeric percent display, e.g. "92.2%"', 'percent': 'Optional 0-100 bar width'},
             'bind': ['value', 'percent', 'subVal'],
             'example': {'label': '预算达成率', 'value': '92.2%', 'percent': 92.2, 'subLabel': '预算收入', 'subVal': '525 万元'}},
    'mc05': {'name': '迷你半环仪表卡', 'question': 'Where does a 0-100 score sit on its scale?',
             'fields': {**COMMON, 'value': 'Numeric display', 'percent': '0-100 gauge position', 'gaugeSub': 'Badge beside the value'},
             'bind': ['value', 'percent', 'subVal'],
             'example': {'label': '航班正常率', 'value': '88.6%', 'percent': 88.6, 'gaugeSub': '基准 85%', 'subLabel': '行业基准', 'subVal': '85.0%'}},
    'mc06': {'name': '双指标并列卡', 'question': 'How do two peer metrics compare side by side?',
             'fields': {'label': COMMON['label'], 'leftTitle': 'Left metric name', 'leftVal': 'Left value text', 'leftYoy': 'Optional signed change',
                        'rightTitle': 'Right metric name', 'rightVal': 'Right value text', 'rightYoy': 'Optional signed change', 'subLabel': COMMON['subLabel'], 'subVal': COMMON['subVal']},
             'bind': ['leftVal', 'rightVal', 'subVal'],
             'example': {'label': '供给与需求', 'leftTitle': '可用座公里', 'leftVal': '52.4 亿', 'leftYoy': '+6.2%', 'rightTitle': '客公里', 'rightVal': '43.8 亿', 'rightYoy': '+8.1%', 'subLabel': '匹配率', 'subVal': '83.6%'}},
    'mc07': {'name': '排位梯队徽章卡', 'question': 'What rank or tier does the business hold?',
             'fields': {**COMMON, 'value': 'Rank headline text', 'rankSub': 'Line under the rank', 'rankBadge': 'Badge text such as "#2 / 12"'},
             'bind': [],
             'example': {'label': '区域收入排名', 'value': '华东第 2', 'rankSub': '共 12 个区域', 'rankBadge': '#2', 'subLabel': '收入占比', 'subVal': '18.4%'}},
    'mc08': {'name': '阈值预警卡', 'question': 'Which metric crossed a warning threshold?',
             'fields': {**COMMON, 'alertLabel': 'Threshold text shown in the attention badge'},
             'bind': [],
             'example': {'label': '成本超支率', 'value': '6.3%', 'alertLabel': '超过 5% 红线', 'subLabel': '超支金额', 'subVal': '42 万元'}},
    'mc09': {'name': '结构分段卡', 'question': 'How is a total split between two parts?',
             'fields': {**COMMON, 'segLeftWidth': 'Left share 0-100', 'segRightWidth': 'Right share; the two sum to 100', 'subLabel': 'Left segment label and value', 'subVal': 'Right segment label and value'},
             'bind': [],
             'example': {'label': '收入结构', 'value': '484 万元', 'segLeftWidth': '72%', 'segRightWidth': '28%', 'subLabel': '国内 348 万元', 'subVal': '国际 136 万元'}},
    'mc10': {'name': '中位数极差分布卡', 'question': 'What is typical, and how spread out is a skewed distribution?',
             'fields': {'label': COMMON['label'], 'value': 'Displayed median text', 'valueLabel': 'Label before the value (default 中位数)',
                        'stats': 'Finite numbers {min, p25, median, p75, max}, ascending', 'meanText': 'Optional mean text', 'sampleText': 'Optional sample size text'},
             'bind': [],
             'example': {'label': '客单票价', 'value': '¥680', 'meanText': '均值 ¥742.5', 'sampleText': '5,420 万张', 'stats': {'min': 320, 'p25': 540, 'median': 680, 'p75': 920, 'max': 1850}}},
    'mc11': {'name': '环形进度卡', 'question': 'How complete is a goal, at a glance?',
             'fields': {**COMMON, 'percent': 'Completion 0-100 (above 100 fills the ring and shows the real percent)', 'trendLabel': 'Optional neutral note'},
             'bind': ['value', 'percent', 'subVal'],
             'example': {'label': '年度收入目标', 'value': '1,840 万元', 'percent': 92, 'trendLabel': '按月累计', 'subLabel': '年度目标', 'subVal': '2,000 万元'}},
    'mc12': {'name': '迷你柱趋势卡', 'question': 'How does the latest period compare with the previous few?',
             'fields': {**COMMON, 'sparkMonths': 'Period labels', 'sparkData': 'Finite values, same length; the last bar is emphasized', 'trendLabel': 'Optional neutral note'},
             'bind': ['value', 'yoy', 'subVal', 'timeField → sparkMonths/sparkData'],
             'example': {'label': '月度新增客户', 'value': '1,268 户', 'yoy': '+12.4%', 'sparkMonths': ['04', '05', '06', '07', '08', '09'], 'sparkData': [940, 1012, 1105, 990, 1180, 1268], 'subLabel': '近六个月均值', 'subVal': '1,083 户'}},
    'mc13': {'name': '子弹目标卡', 'question': 'Is actual above target, and in which qualitative range?',
             'fields': {**COMMON, 'actual': 'Finite actual value', 'target': 'Finite target value (marker)', 'ranges': 'Up to three ascending range limits in the same unit',
                        'rangeBasis': 'value (absolute limits, default) or target (limits are fractions of target, e.g. [0.8, 1.0]; use when filters recompute target)',
                        'max': 'Optional scale maximum', 'unit': 'Unit used when target text is derived'},
             'bind': ['value', 'actual', 'target', 'subVal'],
             'example': {'label': '季度营收对目标', 'value': '484 万元', 'actual': 484, 'target': 525, 'ranges': [400, 500], 'unit': '万元', 'subLabel': '季度目标', 'subVal': '525 万元'}},
    'mc14': {'name': '双期对比卡', 'question': 'How does this period compare with the prior period?',
             'fields': {**COMMON, 'currentLabel': 'Current period label', 'currentValue': 'Finite current value', 'priorLabel': 'Prior period label',
                        'priorValue': 'Finite prior value', 'currentText': 'Optional display text', 'priorText': 'Optional display text', 'deltaLabel': 'Badge label (default 较上期)', 'unit': 'Unit for derived text'},
             'bind': ['value', 'currentValue', 'priorValue', 'yoy', 'subVal'],
             'example': {'label': '季度收入对比', 'value': '484 万元', 'yoy': '+24.1%', 'currentLabel': '2026Q3', 'currentValue': 484, 'priorLabel': '2025Q3', 'priorValue': 390, 'unit': '万元'}},
    'mc15': {'name': '指标清单卡', 'question': 'What are 2-4 related sub-metrics of one theme?',
             'fields': {'label': COMMON['label'], 'value': 'Optional headline text', 'valueLabel': 'Optional note beside it',
                        'items': '1-4 objects {label, value, delta?}; delta is a signed comparison'},
             'bind': [],
             'example': {'label': '渠道收入', 'value': '484 万元', 'valueLabel': '合计', 'items': [{'label': '直销', 'value': '226 万元', 'delta': '+8.2%'}, {'label': '分销', 'value': '172 万元', 'delta': '-3.1%'}, {'label': '电商', 'value': '86 万元', 'delta': '+21.5%'}]}},
    'mc16': {'name': '大字主指标卡', 'question': 'What is the single number that matters most, and the takeaway?',
             'fields': {**COMMON, 'note': 'Authored one-line takeaway (at most 120 characters)'},
             'bind': ['value', 'yoy', 'subVal'],
             'example': {'label': '北极星 · 月活跃客户', 'value': '12.6 万', 'yoy': '+9.8%', 'note': '新客留存改善带动活跃规模连续三个月增长。', 'subLabel': '目标', 'subVal': '13 万'}},
}

PATTERNS = [
    'Mix shapes by question instead of repeating mc01: trend → mc03/mc12, goal → mc04/mc11/mc13, change → mc02/mc14, composition → mc09/mc15, distribution → mc10, alert → mc08, headline → mc16.',
    'Within one KPI row prefer 2-4 different shapes; keep cards that are compared directly in the same shape.',
    'Use at most one mc16 hero card per page; pair it with the focus or scorecard layout template.',
    'Bind value/geometry targets listed in "bind" when filters must recompute the card; snapshot-only shapes ignore filters.',
]


def kpi_example(code: str) -> dict:
    return {'type': code, **copy.deepcopy(GUIDE[code]['example'])}


def kpi_guide(codes=None) -> list[dict]:
    return [{'code': code, 'name': GUIDE[code]['name'], 'question': GUIDE[code]['question'],
             'bindable': bool(GUIDE[code]['bind'])} for code in (codes or GUIDE)]
