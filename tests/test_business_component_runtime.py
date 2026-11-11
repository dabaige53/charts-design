"""Validate business component data without a UI renderer."""
import importlib
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).parents[1] / "skills" / "executive-charts" / "scripts"
sys.path.insert(0, str(SCRIPTS))
validate_resolved = importlib.import_module("dashboard_workspace").validate_resolved


def bound_config():
    return {
        'meta': {'title': 'Sales'},
        'filters': [{'id': 'region', 'key': 'region', 'label': '区域', 'type': 'multi-select',
                     'options': [{'value': 'east'}, {'value': 'south'}], 'fields': ['region'],
                     'componentIds': ['revenue', 'sales']}],
        'kpis': [{'id': 'revenue', 'type': 'mc01', 'label': '收入', 'value': '224 万元', 'unit': '万元',
                  'binding': {'field': 'sales', 'aggregate': 'sum', 'precision': 0}}],
        'charts': [{'id': 'sales', 'code': 'c01', 'title': '区域收入', 'unit': '万元',
                    'data': {'categories': ['east', 'south'], 'values': [128, 96]},
                    'presentation': {'axisLabels': {'x': '区域', 'y': '收入'}, 'seriesLabels': ['收入'],
                                     'tooltipValueLabels': ['收入'], 'units': ['万元'],
                                     'tableHeaders': ['区域', '收入']},
                    'binding': {'groupBy': 'region', 'category': 'categories',
                                'series': {'values': {'field': 'sales', 'aggregate': 'sum'}}}}],
        'table': {'columns': [{'key': 'region', 'title': '区域'},
                              {'key': 'sales', 'title': '收入', 'unit': '万元', 'align': 'right'}],
                  'rows': [{'region': 'east', 'sales': 128}, {'region': 'south', 'sales': 96}]},
    }


# @wu-test type=boundary | scope=筛选绑定校验 | protects=无法解析的字段组件或聚合进入配置
@pytest.mark.parametrize('mutation,code', [
    (lambda config: config['filters'][0].update(fields=['missing']), 'FILTER_FIELD_UNKNOWN'),
    (lambda config: config['filters'][0].update(componentIds=['missing']), 'FILTER_CONSUMER_UNKNOWN'),
    (lambda config: config['kpis'][0].pop('binding'), 'FILTER_BINDING_MISSING'),
    (lambda config: config['kpis'][0]['binding'].update(field='missing'), 'BINDING_FIELD_UNKNOWN'),
    (lambda config: config['charts'][0]['binding']['series']['values'].update(aggregate='guess'), 'BINDING_AGGREGATE_INVALID'),
])
def test_strict_filter_validation_rejects_unresolvable_bindings(mutation, code):
    config = bound_config()
    mutation(config)
    errors, _ = validate_resolved(config, strict=True)
    assert code in {error['code'] for error in errors}


# @wu-test type=behavior | scope=筛选绑定校验 | protects=完整有效绑定被拒绝
def test_complete_binding_is_accepted():
    assert validate_resolved(bound_config(), strict=True)[0] == []


# @wu-test type=boundary | scope=KPI比较值校验 | protects=含糊或无效比较值进入声明
@pytest.mark.parametrize('value', ['12.4%', '1%', '1.2.3%', float('nan'), True, {}])
def test_strict_kpi_rejects_ambiguous_comparisons(value):
    config = bound_config()
    config['kpis'][0]['yoy'] = value
    errors, _ = validate_resolved(config, strict=True)
    assert any(error['code'] == 'KPI_COMPARISON_INVALID' and error['path'] == 'kpis[0].yoy' for error in errors)


# @wu-test type=boundary | scope=KPI比较值校验 | protects=有效数字带符号值和空值被拒绝
@pytest.mark.parametrize('value', [12.4, -1, 0, '+12.4%', '-1%', '0%', None, '—', '持平'])
def test_strict_kpi_accepts_numeric_signed_and_empty_comparisons(value):
    config = bound_config()
    config['kpis'][0]['yoy'] = value
    assert validate_resolved(config, strict=True)[0] == []


# @wu-test type=boundary | scope=KPI配置校验 | protects=缺少必要数据的专用KPI被接受
@pytest.mark.parametrize('card_type', ['mc03', 'mc06', 'mc09'])
def test_specialized_kpis_require_their_data(card_type):
    config = bound_config()
    config['filters'] = []
    config['kpis'][0].pop('binding')
    config['kpis'][0]['type'] = card_type
    errors, _ = validate_resolved(config, strict=True)
    assert any(error['code'] == 'KPI_PRESENTATION_INVALID' for error in errors)
