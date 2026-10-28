"""Incremental view and immutable query cache acceptance."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import time
from unittest.mock import patch

import pytest

from dashboard_runtime.local_data import LocalData, QueryCache
from dashboard_runtime.local_view import LocalView
from dashboard_runtime.model import DashboardError

spec = importlib.util.spec_from_file_location('incremental_benchmark', Path(__file__).with_name('benchmark_local.py'))
assert spec is not None and spec.loader is not None
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


@pytest.fixture
def service(tmp_path):
    return benchmark.attach(tmp_path, 240)[0]


def view(service, **args):
    return service.call('dashboard_view', {'dashboardId': 'acceptance', **args})


def test_patch_matches_full_and_skips_unselected(service):
    state = {'details': {'page': 2, 'pageSize': 25, 'sortCol': 'amount', 'sortDir': 'desc', 'keyword': 'Agent-1'}}
    full = view(service, filters=benchmark.filters(True), tableStates=state)['document']
    with patch.object(service.views, 'aggregate', side_effect=AssertionError('Unselected chart evaluated')), patch.object(service.views, 'filter_options', side_effect=AssertionError('Options evaluated')):
        partial = view(service, responseMode='patch', expectedRevision=3, componentIds=['details'], filters=benchmark.filters(True), tableStates=state)
    assert 'document' not in partial
    assert partial['id'] == full['id'] and partial['revision'] == full['revision']
    assert partial['componentIds'] == ['details']
    assert partial['computed']['components'] == {'details': full['computed']['components']['details']}
    for key in ('page', 'pageSize', 'totalRows', 'keyword', 'sortCol', 'sortDir'):
        assert partial['computed']['tables']['details'][key] == full['computed']['tables']['details'][key]
    assert partial['computed']['filterOptions'] == partial['computed']['filterPages'] == partial['statisticalArtifacts'] == {}
    all_patch = view(service, responseMode='patch', filters=benchmark.filters(True), tableStates=state, includeFilterOptions=True)
    assert all_patch['computed']['components'] == full['computed']['components']
    assert all_patch['computed']['filterOptions'] == full['computed']['filterOptions']


def test_empty_patch_and_revision_conflict(service):
    with patch.object(service.store.data, 'rows', side_effect=AssertionError('Rows evaluated')):
        result = view(service, responseMode='patch', componentIds=[])
    assert result['componentIds'] == [] and result['computed']['components'] == {}
    for mode in ('full', 'patch'):
        with pytest.raises(DashboardError) as error:
            view(service, responseMode=mode, expectedRevision=2)
        assert error.value.code == 'REVISION_CONFLICT' and error.value.status == 409
    with pytest.raises(DashboardError):
        view(service, responseMode='patch', componentIds=['missing'])


def test_refresh_discards_deleted_component_reader_state(service):
    filters = benchmark.filters()
    filters.append({'id': 'runtime-linkage', 'field': 'department', 'op': 'in', 'values': ['Department-1'], 'componentIds': ['category', 'details']})
    service.call('dashboard_patch', {'dashboardId': 'acceptance', 'expectedRevision': 3,
                                    'operations': [{'op': 'remove_component', 'id': 'category'}]})
    result = service.call('dashboard_refresh', {'dashboardId': 'acceptance', 'filters': filters,
                          'tableStates': {'category': {}, 'details': {'page': 2, 'pageSize': 10}},
                          'granularities': {'category': 'quarter'}})['document']
    assert result['revision'] == 4
    assert result['computed']['tables']['details']['page'] == 2
    assert result['manifest']['filters'][-1]['componentIds'] == ['details']
    assert service.store.get('acceptance', hydrate=False)['manifest']['filters'][0]['values'] == []


def test_component_data_sort_search_and_sequential_pages(service):
    args = {'dashboardId': 'acceptance', 'componentId': 'details', 'expectedRevision': 3, 'search': 'Agent-1', 'sort': [{'field': 'amount', 'direction': 'desc'}]}
    records = []
    for offset in (0, 7, 14):
        result = service.call('component_data', {**args, 'offset': offset, 'limit': 7})
        records.extend(result['rows'])
    expected = sorted([benchmark.source_row(i) for i in range(240) if 'agent-1' in benchmark.source_row(i)['agent'].lower()], key=lambda r: (-r['amount'], r['rowId']))
    assert result['totalRows'] == len(expected)
    assert records == expected[:21]
    plain = {k: v for k, v in args.items() if k not in ('sort', 'search')}
    first = service.call('component_data', {**plain, 'offset': 100, 'limit': 25})
    second = service.call('component_data', {**plain, 'offset': 125, 'limit': 25})
    assert [r['rowId'] for r in first['rows'] + second['rows']] == list(range(100, 150))


def test_semantic_aggregate_reuses_aliases_and_versions_invalidate(tmp_path):
    data = LocalData(tmp_path)
    fields = {'n': {'type': 'number'}, 'group': {'type': 'string'}}
    old = data.import_rows([{'n': 2, 'group': 'a'}, {'n': 3, 'group': 'b'}], fields)
    local = LocalView(data)
    first = {'one': {'aggregation': 'sum', 'field': 'n', 'label': 'First'}}
    second = {'two': {'aggregation': 'sum', 'field': 'n', 'label': 'Changed', 'definition': 'Display'}}
    filters = [{'id': 'a', 'label': 'First', 'field': 'group', 'op': 'in', 'values': ['a', 'b'], 'componentIds': ['one']}]
    assert local.aggregate(old, first, filters)[0] == [{'one': 5}]
    filters[0].update(id='b', label='Other', componentIds=['two'], values=['b', 'a'])
    with patch.object(data, 'aggregate', side_effect=AssertionError('Equivalent calculation ran')):
        assert local.aggregate(old, second, filters) == ([{'two': 5}], True)
    new = data.import_rows([{'n': 10, 'group': 'a'}], fields)
    assert local.aggregate(new, second, filters) == ([{'two': 10}], False)
    assert data.rows(old, filters)['totalRows'] == 2
    assert data.rows(new, filters)['totalRows'] == 1
    assert data.option_page([old], 'n')['values'] == [2, 3]
    assert data.option_page([new], 'n')['values'] == [10]


def test_singleflight_shares_key_without_serializing_unrelated_queries():
    cache = QueryCache(max_entries=2)
    calls = []
    gate = threading.Barrier(2)
    def compute(key):
        calls.append(key)
        gate.wait(timeout=3)
        time.sleep(.03)
        return {'key': key}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(cache.get, key, lambda key=key: compute(key)) for key in ('one', 'one', 'two', 'two')]
        assert [job.result(timeout=5)[0] for job in jobs] == [{'key': 'one'}, {'key': 'one'}, {'key': 'two'}, {'key': 'two'}]
    assert sorted(calls) == ['one', 'two']
    value, _ = cache.get('one', lambda: None)
    value['key'] = 'modified'
    assert cache.get('one', lambda: None)[0] == {'key': 'one'}
    cache.get('three', lambda: 3)
    assert len(cache.values) == 2


def test_counts_and_options_reuse_cached_sql(service):
    ref = service.store.get('acceptance', hydrate=False)['snapshot']['datasetRefs']['facts']
    data = service.store.data
    filters = benchmark.filters(True)
    data.rows(ref, filters)
    data.option_page([ref], 'agent')
    with patch.object(data.cache, 'get', wraps=data.cache.get) as cached:
        data.rows(ref, filters, offset=10)
        data.option_page([ref], 'agent')
    assert cached.call_count == 2
    assert all(key.startswith(('["count"', '["options"')) for key in data.cache.values)


@pytest.mark.parametrize('direction', ['asc', 'desc'])
def test_sorted_cursor_preserves_nulls_and_duplicate_ties(tmp_path, direction):
    data = LocalData(tmp_path)
    rows = [{'n': n, 'id': i} for i, n in enumerate([None, 2, 1, 2, None, 1, 3, None])]
    ref = data.import_rows(rows, {'n': {'type': 'number'}, 'id': {'type': 'number'}})
    sort = [{'field': 'n', 'direction': direction}]
    expected = data.rows(ref, sort=sort, limit=100)['rows']
    result = []
    for offset in range(0, len(rows), 2):
        result.extend(data.rows(ref, sort=sort, offset=offset, limit=2)['rows'])
    assert result == expected


def test_concurrent_component_reads_and_filters(service):
    def read(index):
        if index % 2:
            return view(service, responseMode='patch', componentIds=['category'], filters=benchmark.filters(True))['computed']['components']['category']['data']['values']
        return service.call('component_data', {'dashboardId': 'acceptance', 'componentId': 'details', 'offset': 20, 'limit': 10})['rows'][0]['rowId']
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(read, range(24)))
    assert all(value == results[1] if i % 2 else value == 20 for i, value in enumerate(results))


def test_singleflight_failure_can_retry():
    cache = QueryCache()
    with pytest.raises(ValueError):
        cache.get('key', lambda: (_ for _ in ()).throw(ValueError('query failed')))
    assert cache.get('key', lambda: 3) == (3, False)


def test_patch_mcp_text_preserves_small_response_for_text_only_hosts(service):
    import json
    from dashboard_runtime.mcp_server import result_text
    result = view(service, responseMode='patch', componentIds=['details'])
    summary = json.loads(result_text(result))
    assert summary == result
    assert len(result_text(result)) < 48000
    assert result['computed']['components']['details']['rows']


def test_semantic_alias_does_not_collide_with_group_field(tmp_path):
    data = LocalData(tmp_path)
    fields = {'__metric_0': {'type': 'string'}, 'n': {'type': 'number'}}
    ref = data.import_rows([{'__metric_0': 'a', 'n': 2}, {'__metric_0': 'a', 'n': 3}], fields)
    local = LocalView(data)
    first, hit = local.aggregate(ref, {'sum': {'aggregation': 'sum', 'field': 'n'}}, [], ['__metric_0'])
    assert not hit and first == [{'__metric_0': 'a', 'sum': 5}]
    second, hit = local.aggregate(ref, {'renamed': {'aggregation': 'sum', 'field': 'n'}}, [], ['__metric_0'])
    assert hit and second == [{'__metric_0': 'a', 'renamed': 5}]
