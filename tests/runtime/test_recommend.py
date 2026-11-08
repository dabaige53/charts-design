"""chart_recommend ranks registered codes by question, shape and page variety."""
import pytest

from dashboard_runtime.demo import executive_document
from dashboard_runtime.model import DashboardError
from dashboard_runtime.recommend import INTENTS, RULES, recommend_charts


def codes(result):
    return [item['code'] for item in result['charts']]


def test_rules_cover_only_registered_codes_and_every_intent():
    from dashboard_runtime.declarations import _registry
    registry = _registry()
    assert set(RULES) <= set(registry.CHART_CODES)
    assert all(recommend_charts({'intent': intent})['charts'] for intent in INTENTS)


def test_shape_and_existing_page_steer_the_ranking():
    many = codes(recommend_charts({'intent': 'comparison', 'categories': 25, 'measures': 1}))
    assert many[0] in ('c02', 'c05') and many.index('c01') > many.index('c02')
    doc = executive_document('page')
    page = recommend_charts({'intent': 'comparison', 'categories': 4, 'measures': 1}, doc)
    first = {item['code']: item for item in page['charts']}
    assert page['usedOnPage'] == {'t06': 1, 'c01': 1}
    assert any('已使用' in note for note in first['c01']['notes'])
    assert codes(page)[0] != 'c01'


def test_time_requirements_and_kpi_suggestions():
    undated = recommend_charts({'intent': 'trend', 'measures': 1, 'hasTime': False})
    dated = recommend_charts({'intent': 'trend', 'measures': 1, 'hasTime': True})
    assert next(item for item in dated['charts'] if item['code'] == 't01')['score'] > next(
        (item['score'] for item in undated['charts'] if item['code'] == 't01'), -99)
    assert dated['kpiShapes'] == ['mc03', 'mc12']
    assert all(item['filterBinding'] in ('supported', 'snapshotOnly') for item in dated['charts'])


@pytest.mark.parametrize('args', [{}, {'intent': 'pie'}, {'intent': 'trend', 'categories': 0}, {'intent': 'trend', 'hasTime': 'yes'}])
def test_invalid_requests_fail(args):
    with pytest.raises(DashboardError):
        recommend_charts(args)
