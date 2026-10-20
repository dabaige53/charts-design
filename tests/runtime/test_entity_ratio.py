from dashboard_runtime.local_data import LocalData


def test_entity_ratio_deduplicates_after_filters_and_nets_refunds(tmp_path):
    data = LocalData(tmp_path)
    fields = {'agent': {'type': 'string'}, 'region': {'type': 'string'},
              'ho': {'type': 'number'}, 'market': {'type': 'number'}}
    rows = [dict(agent='A', region='日韩', ho=3, market=10),
            dict(agent='A', region='欧洲', ho=-3, market=10),
            dict(agent='B', region='日韩', ho=0, market=5),
            dict(agent='C', region='欧洲', ho=2, market=3)]
    ref = data.import_rows(rows, fields)
    metric = {'coverage': dict(aggregation='entity_ratio', entityField='agent', numerator='ho', denominator='market')}
    assert data.aggregate(ref, metric) == [{'coverage': 1/3}]
    assert data.aggregate(ref, metric, [{'field': 'region', 'op': 'in', 'values': ['日韩']}]) == [{'coverage': .5}]
    assert data.aggregate(ref, metric, [{'field': 'region', 'op': 'in', 'values': ['absent']}]) == [{'coverage': None}]
    grouped = data.aggregate(ref, metric, group_by=['region'])
    assert {r['region']: r['coverage'] for r in grouped} == {'日韩': .5, '欧洲': .5}
