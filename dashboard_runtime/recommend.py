"""Question- and shape-aware chart suggestions over the 40 registered codes.

Generated dashboards tended to reuse c01/t06 for every question. This module
ranks codes by the analytical intent, the number of categories and measures,
and whether a date field exists, and reports reviewed filter bindings.
Comparable questions retain comparable encodings across a page. It is
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
    't03': (('trend',), 3, 40, (1, 1), False, '有序阶段或时间上的离散阶跃变化'),
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
    'fn04': (('trend', 'comparison'), 3, 40, (4, 4), True, '四个不同量级序列归一到 100 后比较增速'),
    'm01': (('target',), 1, 8, (1, 2), False, '实际、合格线与目标线（子弹图）'),
    'm02': (('forecast', 'trend'), 4, 24, (1, 3), True, '预测中枢与置信区间（扇形）'),
    'm03': (('target', 'comparison'), 2, 60, (1, 1), False, '各类别超阈值红线的监控与告警'),
    'm04': (('target',), 1, 1, (1, 1), False, '单一综合达成进度（半环仪表）'),
}
INTENTS = ('comparison', 'ranking', 'trend', 'composition', 'distribution', 'relationship', 'flow', 'change', 'attribution', 'target', 'forecast')
KPI_BY_INTENT = {
    'trend': ['mc03', 'mc12'], 'target': ['mc04', 'mc11', 'mc13'], 'change': ['mc02', 'mc14'],
    'composition': ['mc09', 'mc15'], 'distribution': ['mc10'], 'comparison': ['mc06', 'mc14'],
    'ranking': ['mc07'], 'forecast': ['mc03'], 'attribution': ['mc15'], 'relationship': ['mc06'], 'flow': ['mc04'],
}

REQUIREMENTS = {
    'c03': '明确两项可比指标，或用 encoding 声明类别、系列维度和一个指标。',
    'c04': '已定义基准及正负差异；增长率与百分点分别标明。',
    'c06': '同一实体的两期配对值，口径和单位一致。',
    'c07': '真实目标或基期与当前实际值，两个系列口径一致。',
    'c08': '同一分类下两个可比群体；左右轴单位和范围一致。',
    't02': '明确实际与预测的分界、预测方法和数据来源。',
    't03': '有序阶段或日期，且值确实按阶跃变化。',
    't04': '四个可加总、互斥、同单位的构成项。',
    't05': '同一组实体在两期的配对数值，不能只提供名次。',
    't06': '同一时间粒度的规模和比率；分别声明左右轴、单位与比较基准。',
    'k01': '非负且互斥的部分；明确同一总体和分母。',
    'k02': '三个互斥构成项和一致的分母；每组份额完整。',
    'k03': '非负可加总值；层级与叶节点归属明确。',
    'k04': '非负贡献值，按贡献排序，累计百分比由同一总体重算。',
    'k05': '非负互斥份额及已知总量；精确比较接近份额时优先条形。',
    'k06': '真实父子层级；各层合计一致，不能重复计数。',
    'd01': '已声明分箱边界及频数；不等宽区间需要核对密度表示。',
    'd02': '每组原始观测或可追溯的五数概括，不能由均值推造分布。',
    'd03': '原始观测和明确的密度估计方法，或已计算的密度。',
    'd04': '两维时段及各单元格真实数值；区分零与未观测。',
    'r01': '同一实体的成对指标和有依据的象限阈值。',
    'r02': '同一实体的成对 x/y；气泡面积还需非负规模指标。',
    'r03': '已计算的相关系数及其方法、样本量；encoding 热力图不自动计算相关性。',
    'r04': '真实节点和边，明确方向与连接含义。',
    'r05': '同尺度且方向一致的多个指标；归一方法和基准可解释。',
    'f01': '同一批对象的有序阶段，明确各阶段分母和去重规则。',
    'f02': '真实来源、去向及非负流量；同一节点入流出流需核对。',
    'f03': '批次、相对时间和留存分母；尚未到达的周期不得填零。',
    'fn01': '期初、各增减因素与期末能够核对闭合。',
    'fn02': '同期同单位收入和成本；盈亏差额由两者相减。',
    'fn03': '真实情景模型的正负冲击结果，注明变量变化幅度。',
    'fn04': '共同且非零的基期；各序列使用相同归一规则。',
    'm01': '真实目标与实际值；多个不同指标须先转成可比达成率。',
    'm02': '预测上下界与中枢来自明确模型或情景，不把情景范围称为置信区间。',
    'm03': '业务已确认的阈值和超限方向。',
    'm04': '真实分子、目标和量程；超额完成保留真实数字。',
}

DESIGN_GUIDANCE = [
    '先确定读者要作的判断，再选择能直接表达比较、趋势或分布的图形；复杂度需要信息收益。',
    '同一组可直接比较的指标保持相同图形、尺度和语义颜色；页面已使用某图不构成换图理由。',
    '保留一个主要阅读焦点，按总览、原因、明细组织；颜色强调异常或选中对象，避免每图换色。',
    '标题说明分析问题或有数据支持的结论；单位、时间范围、分母和数据来源可见。',
    '柱形/面积的长度比较使用合理基线；双轴明确两侧单位，不用调轴制造相关性。',
    '类别过多先排序、分面或提供滚动/明细；Top N 需交代其余项，不能悄悄丢弃数据。',
]


def recommend_charts(args: dict, doc: dict | None = None) -> dict:
    intent = args.get('intent')
    require(intent in INTENTS, f'intent must be one of: {", ".join(INTENTS)}', 'INVALID_INTENT')
    categories = args.get('categories')
    measures = args.get('measures')
    has_time = args.get('hasTime')
    requires_binding = args.get('requiresFilterBinding', False)
    require(categories is None or (type(categories) is int and categories >= 1), 'categories must be a positive integer')
    require(measures is None or (type(measures) is int and measures >= 1), 'measures must be a positive integer')
    require(has_time is None or type(has_time) is bool, 'hasTime must be boolean')
    require(type(requires_binding) is bool, 'requiresFilterBinding must be boolean')
    if args.get('datasetId') is not None:
        require(doc is not None and args['datasetId'] in doc['manifest']['datasets'],
                'datasetId must identify a dataset in the supplied dashboard', 'DATASET_NOT_FOUND')
    used: dict[str, int] = {}
    if doc is not None:
        meta = doc['manifest']['datasets'].get(args.get('datasetId')) if args.get('datasetId') else None
        if meta and has_time is None and any(field.get('type') == 'date' for field in meta['fields'].values()):
            has_time = True
        for component in doc['manifest']['components'].values():
            if component.get('kind') == 'legacy' and component.get('family', 'chart') == 'chart':
                code = component.get('config', {}).get('code')
                used[code] = used.get(code, 0) + 1
    from .bindings import KPI_SNAPSHOT_ONLY, SERIES_TARGETS
    from .encoding import DYNAMIC_CODES
    from .legacy import catalog
    names = {entry['id']: entry.get('nameZh') for entry in catalog()}
    ranked, excluded = [], []
    for code, (intents, low, high, (fewest, most), needs_time, why) in RULES.items():
        if intent not in intents:
            continue
        # A correlation snapshot is not equivalent to a grouped-value heatmap.
        # Discovery must not promise that encoding recomputes a correlation.
        bindable = code in SERIES_TARGETS or (code in DYNAMIC_CODES and code != 'r03')
        if requires_binding and not bindable:
            excluded.append({'code': code, 'reason': '该分析形态没有已实现的筛选重算路径；不能用快照冒充联动。'})
            continue
        if needs_time and has_time is False:
            excluded.append({'code': code, 'reason': '该形态需要真实时间维度。'})
            continue
        score, notes = 3 if intents[0] == intent else 2, []
        mismatches = []
        if categories is not None and not low <= categories <= high:
            score -= 2
            mismatches.append({'field': 'categories', 'kind': 'readability', 'actual': categories,
                               'range': [low, high]})
            notes.append(f'当前 {categories} 个类别超出建议阅读范围 {low}~{high}；需调整布局或明细呈现。')
        binding_mode = 'preset' if code in SERIES_TARGETS else 'encoding' if bindable else 'snapshot'
        if code == 'r02' and measures == 2:
            fewest, most, binding_mode = 2, 2, 'encoding'
            notes.append('两个指标使用固定点大小的 encoding 散点；不虚构气泡规模。')
        if code == 'c03' and measures == 1:
            fewest, most, binding_mode = 1, 1, 'encoding'
            notes.append('单指标分组图需另有 seriesField；未确认系列维度前不要提交。')
        if measures is not None and not fewest <= measures <= most:
            score -= 2
            mismatches.append({'field': 'measures', 'kind': 'structure', 'actual': measures,
                               'range': [fewest, most]})
            notes.append(f'当前 {measures} 项指标与所需数值结构 {fewest}~{most} 项不匹配；先核对该预设声明。')
        if bindable:
            score += 1
        if used.get(code):
            notes.append(f'本页已使用 {used[code]} 次；相同分析问题优先保持一致形态。')
        requirements = [REQUIREMENTS.get(code, '明确类别、指标口径和单位；比较对象使用一致范围。')]
        if needs_time:
            requirements.append('时间顺序、粒度和缺失期处理已确认。')
        if binding_mode == 'encoding':
            requirements.append('必须提供 config.encoding 和其专用 binding；普通预设数据路径不会自动启用此能力。')
        cautions = []
        if any(item['kind'] == 'structure' for item in mismatches):
            cautions.append('已知指标结构不匹配；不能直接填入当前数据，也不能编造缺少的系列。')
        if any(item['kind'] == 'readability' for item in mismatches):
            cautions.append('类别数量超出阅读建议；该范围不是验证器硬限制，应明确处理拥挤或空疏。')
        if not bindable:
            cautions.append('此推荐为静态快照；筛选不重新计算其统计值。')
        if categories is None or measures is None or (needs_time and has_time is None):
            cautions.append('输入形态尚不完整；当前排序是候选建议，不代表已验证适配。')
        fit = ('shape_mismatch' if mismatches else 'needs_confirmation'
               if categories is None or measures is None or (needs_time and has_time is None) or binding_mode == 'encoding'
               else 'candidate')
        ranked.append({'code': code, 'name': names.get(code) or ('多维雷达对标图' if code == 'r05' else code),
                       'why': why, 'score': score, 'fit': fit, 'shapeMismatches': mismatches,
                       'filterBinding': 'supported' if bindable else 'snapshotOnly',
                       'bindingMode': binding_mode, 'requirements': requirements, 'cautions': cautions, 'notes': notes,
                       'declarationCall': {'tool': 'chart_declarations', 'arguments': {'code': code}}})
    ranked.sort(key=lambda item: (any(issue['kind'] == 'structure' for issue in item['shapeMismatches']),
                                  -item['score'], item['code']))
    candidates = ranked[:6]
    kpis = KPI_BY_INTENT.get(intent, [])
    if requires_binding:
        kpis = [code for code in kpis if code not in KPI_SNAPSHOT_ONLY]
    questions = []
    if categories is None:
        questions.append('图中实际需要展示多少个类别或时间点？')
    if measures is None:
        questions.append('要比较几个指标；它们的单位、聚合方式和基准是什么？')
    if has_time is None and intent in ('trend', 'forecast'):
        questions.append('是否存在真实日期字段，采用什么时间粒度？')
    has_viable_shape = any(not any(item['kind'] == 'structure' for item in chart['shapeMismatches']) for chart in candidates)
    return {'intent': intent, 'inputs': {'categories': categories, 'measures': measures, 'hasTime': has_time,
                                        'requiresFilterBinding': requires_binding},
            'charts': candidates, 'kpiShapes': kpis, 'usedOnPage': used, 'excluded': excluded,
            'questions': questions, 'designGuidance': list(DESIGN_GUIDANCE),
            'status': 'candidates' if has_viable_shape else 'needs_input',
            'next': ('chart_declarations {"codes": ["<chosen-chart>", "<chosen-kpi>"]} returns shared schemas and synthetic working examples in one call.'
                     if has_viable_shape else '确认数据形态或筛选要求；不要用不支持该分析的预设替代。可另行评估原生 ECharts、HTML 或统计图快照。')}
