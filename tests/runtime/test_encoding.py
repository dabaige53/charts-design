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
