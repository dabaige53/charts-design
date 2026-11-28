"""chart_recommend ranks by evidence and shape while preserving comparability."""
import pytest

from dashboard_runtime.demo import executive_document
from dashboard_runtime.model import DashboardError
from dashboard_runtime.recommend import INTENTS, RULES, recommend_charts


def codes(result):
    return [item['code'] for item in result['charts']]


# @wu-test type=behavior | scope=图表推荐规则 | protects=推荐未注册图表或某意图无结果 | debt=D6
def test_rules_cover_only_registered_codes_and_every_intent():
    from dashboard_runtime.declarations import _registry
    registry = _registry()
    assert set(RULES) <= set(registry.CHART_CODES)
    assert all(recommend_charts({'intent': intent})['charts'] for intent in INTENTS)


# @wu-test type=behavior | scope=图表推荐排序 | protects=排序忽略数据形状或为换图而破坏可比性
def test_shape_and_existing_page_steer_the_ranking():
    many = codes(recommend_charts({'intent': 'comparison', 'categories': 25, 'measures': 1}))
    assert many[0] in ('c02', 'c05') and many.index('c01') > many.index('c02')
    doc = executive_document('page')
    page = recommend_charts({'intent': 'comparison', 'categories': 4, 'measures': 1}, doc)
    first = {item['code']: item for item in page['charts']}
    assert page['usedOnPage'] == {'t06': 1, 'c01': 1}
    assert any('已使用' in note for note in first['c01']['notes'])
    assert codes(page)[0] == codes(recommend_charts({'intent': 'comparison', 'categories': 4, 'measures': 1}))[0]


# @wu-test type=behavior | scope=图表推荐时间维度 | protects=无时间字段仍优先趋势图或KPI建议错误
def test_time_requirements_and_kpi_suggestions():
    undated = recommend_charts({'intent': 'trend', 'measures': 1, 'hasTime': False})
    dated = recommend_charts({'intent': 'trend', 'measures': 1, 'hasTime': True})
    assert next(item for item in dated['charts'] if item['code'] == 't01')['score'] > next(
        (item['score'] for item in undated['charts'] if item['code'] == 't01'), -99)
    assert dated['kpiShapes'] == ['mc03', 'mc12']
    assert all(item['filterBinding'] in ('supported', 'snapshotOnly') for item in dated['charts'])


# @wu-test type=boundary | scope=图表推荐参数 | protects=非法意图或参数类型被接受
@pytest.mark.parametrize('args', [{}, {'intent': 'pie'}, {'intent': 'trend', 'categories': 0}, {'intent': 'trend', 'hasTime': 'yes'}])
def test_invalid_requests_fail(args):
    with pytest.raises(DashboardError):
        recommend_charts(args)


# @wu-test type=boundary | scope=推荐证据与交互要求 | protects=未知数据被当作单指标或推荐无法筛选的快照
def test_unknown_shape_and_required_filters_remain_explicit():
    unknown = recommend_charts({'intent': 'comparison'})
    assert unknown['inputs']['measures'] is None
    assert unknown['questions'] and unknown['designGuidance']
    assert all(item['requirements'] and item['cautions'] for item in unknown['charts'])
    for intent in INTENTS:
        result = recommend_charts({'intent': intent, 'requiresFilterBinding': True})
        assert all(item['filterBinding'] == 'supported' for item in result['charts'])
        from dashboard_runtime.bindings import KPI_SNAPSHOT_ONLY
        assert not set(result['kpiShapes']) & KPI_SNAPSHOT_ONLY
    correlation = recommend_charts({'intent': 'relationship', 'requiresFilterBinding': True})
    assert 'r03' not in codes(correlation)  # grouped heatmap is not recomputed correlation
    assert 'r03' in [item['code'] for item in correlation['excluded']]
    with pytest.raises(DashboardError):
        recommend_charts({'intent': 'trend', 'requiresFilterBinding': 'yes'})


# @wu-test type=behavior | scope=推荐动态编码 | protects=把编码散点气泡或构成图标为不支持筛选并虚构数据维度
def test_encoding_candidates_describe_the_required_mapping():
    scatter = recommend_charts({'intent': 'relationship', 'measures': 2, 'requiresFilterBinding': True})
    candidate = next(item for item in scatter['charts'] if item['code'] == 'r02')
    assert candidate['bindingMode'] == 'encoding'
    assert any('固定点大小' in note for note in candidate['notes'])
    composition = recommend_charts({'intent': 'composition', 'measures': 1, 'requiresFilterBinding': True})
    assert next(item for item in composition['charts'] if item['code'] == 'k01')['bindingMode'] == 'encoding'
    with pytest.raises(DashboardError) as missing:
        recommend_charts({'intent': 'trend', 'datasetId': 'missing'}, executive_document('page'))
    assert missing.value.code == 'DATASET_NOT_FOUND'


# @wu-test type=boundary | scope=推荐已知不匹配 | protects=指标结构已不适配仍把候选声称为可直接制作
def test_shape_mismatch_is_distinct_from_unknown_input():
    mismatch = recommend_charts({'intent': 'target', 'measures': 9, 'categories': 4})
    assert mismatch['status'] == 'needs_input'
    assert all(item['fit'] == 'shape_mismatch' for item in mismatch['charts'])
    assert all(any(issue['field'] == 'measures' for issue in item['shapeMismatches']) for item in mismatch['charts'])
    assert all(any('不能直接' in caution for caution in item['cautions']) for item in mismatch['charts'])
    unknown = recommend_charts({'intent': 'target'})
    assert all(item['fit'] == 'needs_confirmation' for item in unknown['charts'])
    assert all(not item['shapeMismatches'] for item in unknown['charts'])
    # A compatible but crowded shape must not disappear behind six structurally
    # incompatible recommendations and leave a misleading candidates status.
    crowded = recommend_charts({'intent': 'comparison', 'categories': 30, 'measures': 3, 'hasTime': False})
    assert crowded['status'] == 'candidates'
    assert crowded['charts'][0]['code'] == 'r05'
    assert not any(item['kind'] == 'structure' for item in crowded['charts'][0]['shapeMismatches'])


# @wu-test type=boundary | scope=推荐时间维度推断 | protects=字符串月份季度被当成不存在时间而排除合法趋势图
def test_string_period_fields_remain_unknown_until_confirmed():
    doc = executive_document('page')
    dataset_id = next(iter(doc['manifest']['datasets']))
    for field in doc['manifest']['datasets'][dataset_id]['fields'].values():
        if field['type'] == 'date':
            field['type'] = 'string'
    args = {'intent': 'trend', 'datasetId': dataset_id, 'requiresFilterBinding': True, 'measures': 1}
    unknown = recommend_charts(args, doc)
    assert unknown['inputs']['hasTime'] is None
    assert 't01' in codes(unknown)
    explicit = recommend_charts({**args, 'hasTime': False}, doc)
    assert 't01' not in codes(explicit)
    assert any(item['code'] == 't01' for item in explicit['excluded'])
