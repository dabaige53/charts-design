from dashboard_runtime.local_data import LocalData
from dashboard_runtime.local_view import LocalView
from dashboard_runtime.encoding import resolve_encoding


def test_local_dynamic_aggregate(tmp_path):
    data = LocalData(tmp_path)
    fields = {k: {'type': 'number' if k in ('market', 'ho', 'minutes') else 'string'} for k in ('od', 'market', 'ho', 'minutes', 'grade')}
    ref = data.import_rows(iter([{'od': 'A', 'market': 100, 'ho': 10, 'minutes': 90, 'grade': 'good'}, {'od': 'A', 'market': 900, 'ho': 180, 'minutes': 60, 'grade': 'mixed'}]), fields)
    m = {'metrics': {'share': {'aggregation': 'ratio', 'numerator': 'ho', 'denominator': 'market'}}}
    c = {'config': {'code': 'r02'}, 'binding': {'categoryField': 'od', 'measures': {'share': 'share'}, 'attributes': {'minutes': {'field': 'minutes', 'aggregation': 'min'}, 'grade': {'field': 'grade', 'aggregation': 'unique'}}}}
    view = LocalView(data)
    assert resolve_encoding(view, ref, m, c, []) == [{'category': 'A', 'series': None, 'values': {'share': .19, 'minutes': 60, 'grade': None}}]
    assert resolve_encoding(view, ref, m, c, [{'field': 'od', 'op': 'in', 'values': ['absent']}]) == []


def test_retail_series_and_filter_parity(tmp_path):
    data = LocalData(tmp_path)
    fields = {k: {'type': 'number' if k == 'sales' else 'string'} for k in ('region', 'product', 'sales')}
    ref = data.import_rows(iter([{'region': 'North', 'product': 'Tea', 'sales': 0}, {'region': 'South', 'product': 'Tea', 'sales': 20}, {'region': 'South', 'product': 'Coffee', 'sales': 30}]), fields)
    m = {'metrics': {'sales': {'field': 'sales', 'aggregation': 'sum'}}}
    c = {'config': {'code': 'c03'}, 'binding': {'categoryField': 'region', 'seriesField': 'product', 'measures': {'value': 'sales'}}}
    rows = resolve_encoding(LocalView(data), ref, m, c, [{'field': 'region', 'op': 'in', 'values': ['South']}])
    assert sum(r['values']['value'] for r in rows) == 50
    assert {r['series'] for r in rows} == {'Tea', 'Coffee'}


def test_dynamic_declaration_validation():
    import pytest
    from dashboard_runtime.model import new_document, apply_operations, DashboardError
    from dashboard_runtime.declarations import declaration_contract
    doc = new_document('retail', 'Retail fixture')
    operations = [
        {'op': 'put_source', 'id': 'fixture', 'value': {'kind': 'fixture'}},
        {'op': 'put_dataset', 'id': 'sales', 'meta': {'sourceId': 'fixture', 'fields': {'region': {'type': 'string'}, 'product': {'type': 'string'}, 'sales': {'type': 'number'}}}, 'rows': [{'region': 'North', 'product': 'Tea', 'sales': 10}]},
        {'op': 'put_metric', 'id': 'revenue', 'value': {'datasetId': 'sales', 'field': 'sales', 'aggregation': 'sum', 'label': 'Sales', 'unit': 'USD', 'definition': 'Synthetic fixture sales'}},
        {'op': 'put_component', 'id': 'plot', 'value': {'kind': 'legacy', 'family': 'chart', 'title': 'Retail sales', 'datasetId': 'sales', 'config': {'code': 'c03', 'data': {}, 'presentation': {}, 'encoding': {'orientation': 'horizontal', 'stacked': True}}, 'binding': {'datasetId': 'sales', 'categoryField': 'region', 'seriesField': 'product', 'measures': {'value': 'revenue'}}}},
    ]
    result = apply_operations(doc, operations)
    assert result['manifest']['components']['plot']['binding']['seriesField'] == 'product'
    assert 'dynamicEncoding' in declaration_contract(summary=True)
    operations[-1]['value']['binding']['seriesField'] = 'unknown'
    with pytest.raises(DashboardError):
        apply_operations(doc, operations)
