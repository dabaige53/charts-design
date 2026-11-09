from dashboard_runtime.local_data import LocalData
from dashboard_runtime.local_view import LocalView
from dashboard_runtime.encoding import resolve_encoding


# @wu-test type=integration | scope=动态编码 | protects=比例属性聚合或空筛选结果错误
def test_local_dynamic_aggregate(tmp_path):
    data = LocalData(tmp_path)
    fields = {k: {'type': 'number' if k in ('market', 'ho', 'minutes') else 'string'} for k in ('od', 'market', 'ho', 'minutes', 'grade')}
    ref = data.import_rows(iter([{'od': 'A', 'market': 100, 'ho': 10, 'minutes': 90, 'grade': 'good'}, {'od': 'A', 'market': 900, 'ho': 180, 'minutes': 60, 'grade': 'mixed'}]), fields)
    m = {'metrics': {'share': {'aggregation': 'ratio', 'numerator': 'ho', 'denominator': 'market'}}}
    c = {'config': {'code': 'r02'}, 'binding': {'categoryField': 'od', 'measures': {'share': 'share'}, 'attributes': {'minutes': {'field': 'minutes', 'aggregation': 'min'}, 'grade': {'field': 'grade', 'aggregation': 'unique'}}}}
    view = LocalView(data)
    assert resolve_encoding(view, ref, m, c, []) == [{'category': 'A', 'series': None, 'values': {'share': .19, 'minutes': 60, 'grade': None}}]
    assert resolve_encoding(view, ref, m, c, [{'field': 'od', 'op': 'in', 'values': ['absent']}]) == []


# @wu-test type=integration | scope=动态系列 | protects=筛选后系列或销售额错误
def test_retail_series_and_filter_parity(tmp_path):
    data = LocalData(tmp_path)
    fields = {k: {'type': 'number' if k == 'sales' else 'string'} for k in ('region', 'product', 'sales')}
    ref = data.import_rows(iter([{'region': 'North', 'product': 'Tea', 'sales': 0}, {'region': 'South', 'product': 'Tea', 'sales': 20}, {'region': 'South', 'product': 'Coffee', 'sales': 30}]), fields)
    m = {'metrics': {'sales': {'field': 'sales', 'aggregation': 'sum'}}}
    c = {'config': {'code': 'c03'}, 'binding': {'categoryField': 'region', 'seriesField': 'product', 'measures': {'value': 'sales'}}}
    rows = resolve_encoding(LocalView(data), ref, m, c, [{'field': 'region', 'op': 'in', 'values': ['South']}])
    assert sum(r['values']['value'] for r in rows) == 50
    assert {r['series'] for r in rows} == {'Tea', 'Coffee'}


# @wu-test type=boundary | scope=动态绑定声明 | protects=不存在系列字段被保存
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

# @wu-test type=integration | scope=matrix and flow native grouping | protects=MCP丢失矩阵列和流程指标维度
def test_matrix_and_flow_keep_series(tmp_path):
    data = LocalData(tmp_path)
    fields = {'stage': {'type':'string'}, 'metric': {'type':'string'}, 'n': {'type':'number'}}
    ref = data.import_rows(iter([{'stage':'A','metric':'X','n':1},{'stage':'A','metric':'Y','n':2}]), fields)
    m = {'metrics': {'count': {'aggregation':'sum','field':'n'}}}
    for code in ('r03','f02'):
        c = {'config': {'code':code}, 'binding': {'categoryField':'stage','seriesField':'metric','measures':{'value':'count'}}}
        rows = resolve_encoding(LocalView(data),ref,m,c,[])
        assert [(r['series'],r['values']['value']) for r in rows] == [('X',1),('Y',2)]
