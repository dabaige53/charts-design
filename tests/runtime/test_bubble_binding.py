import copy

import pytest

from dashboard_runtime.declarations import declaration_contract
from dashboard_runtime.model import DashboardError
from dashboard_runtime.service import Service


def bubble():
    return {'kind': 'legacy', 'family': 'chart', 'title': 'Agent bubbles',
            'config': {'code': 'r02', 'unit': '', 'data': {'clusters': [[1, 2, 3, 'fixture']]},
                       'presentation': {'axisLabels': {'x': 'Rate', 'y': 'Amount'}, 'seriesLabels': ['Agents'],
                                        'tooltipValueLabels': ['Rate', 'Amount', 'Count', 'Unused'],
                                        'units': ['%', 'units', 'items', 'ratio'], 'tableHeaders': ['Agent', 'Rate', 'Amount', 'Count', 'Unused']}},
            'binding': {'datasetId': 'facts', 'categoryField': 'agent', 'categoryTarget': 'clusters',
                        'measures': {'x': 'rate', 'y': 'amount', 'size': 'count'}, 'scale': {'x': 100}}}


def test_bubble_recomputes_scoped_metrics_in_local_view(tmp_path):
    service = Service(tmp_path)
    service.call('dashboard_create', {'dashboardId': 'bubble', 'title': 'Bubble'})
    rows = [{'agent': 'A', 'month': 'one', 'amount': 100, 'n': 9, 'd': 10},
            {'agent': 'A', 'month': 'two', 'amount': 20, 'n': 1, 'd': 10},
            {'agent': 'B', 'month': 'two', 'amount': 35, 'n': 7, 'd': 10}]
    service.call('dataset_import', {'dashboardId': 'bubble', 'datasetId': 'facts', 'expectedRevision': 1, 'rows': rows})
    metrics = {'rate': {'aggregation': 'ratio', 'numerator': 'n', 'denominator': 'd'},
               'amount': {'aggregation': 'sum', 'field': 'amount'}, 'count': {'aggregation': 'count'}}
    ops = [{'op': 'put_metric', 'id': key, 'value': {**value, 'datasetId': 'facts', 'label': key, 'unit': '', 'definition': 'Synthetic agent metric', 'decimals': 2}} for key, value in metrics.items()]
    ops += [{'op': 'put_component', 'id': 'bubble', 'value': bubble()},
            {'op': 'put_component', 'id': 'details', 'value': {'kind': 'table', 'title': 'Details', 'datasetId': 'facts'}},
            {'op': 'set_filters', 'value': [{'id': 'month', 'field': 'month', 'op': 'in', 'values': [], 'componentIds': ['bubble', 'details']}]}]
    service.call('dashboard_patch', {'dashboardId': 'bubble', 'expectedRevision': 2, 'operations': ops})
    args = {'dashboardId': 'bubble'}
    view = service.call('dashboard_view', args)['document']
    assert sorted(view['computed']['components']['bubble']['data']['clusters']) == [[50, 120, 2, 'A'], [70, 35, 1, 'B']]
    filters = [{'id': 'month', 'field': 'month', 'op': 'in', 'values': ['two'], 'componentIds': ['bubble', 'details']},
               {'id': 'runtime-linkage', 'field': 'agent', 'op': 'in', 'values': ['A'], 'componentIds': ['details']}]
    view = service.call('dashboard_view', {**args, 'filters': filters})['document']
    assert sorted(view['computed']['components']['bubble']['data']['clusters']) == [[10, 20, 1, 'A'], [70, 35, 1, 'B']]
    assert [row['agent'] for row in view['computed']['components']['details']['rows']] == ['A']
    assert declaration_contract(legacy_code='r02')['legacy']['chartCodes']['r02']['filterBinding']['supported']
    invalid = copy.deepcopy(bubble())
    invalid['binding']['measures'].pop('size')
    with pytest.raises(DashboardError):
        service.call('dashboard_patch', {**args, 'expectedRevision': 3, 'operations': [{'op': 'put_component', 'id': 'bad', 'value': invalid}]})
