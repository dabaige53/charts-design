import csv
import sqlite3

import pytest

from dashboard_runtime.local_data import LocalData


FIELDS = {'name': {'type': 'string'}, 'amount': {'type': 'number'}, 'base': {'type': 'number'}, 'date': {'type': 'date'}, 'enabled': {'type': 'boolean'}}


def dataset(data):
    return data.import_rows(iter([
        {'name': 'ÄLPHA', 'amount': 4, 'base': 2, 'date': '2026-01-01', 'enabled': True},
        {'name': 'Beta', 'amount': 8, 'base': 2, 'date': '2026-02-01', 'enabled': False},
        {'name': None, 'amount': None, 'base': 0, 'date': '2026-04-01', 'enabled': None},
    ]), FIELDS)


def test_aggregate_null_and_ratio_recomputed(tmp_path):
    data = LocalData(tmp_path)
    ref = dataset(data)
    metrics = {'ratio': {'aggregation': 'ratio', 'numerator': 'amount', 'denominator': 'base'},
               'sum': {'aggregation': 'sum', 'field': 'amount'}, 'count': {'aggregation': 'count'},
               'avg': {'aggregation': 'avg', 'field': 'amount'}}
    assert data.aggregate(ref, metrics) == [{'ratio': 3, 'sum': 12, 'count': 3, 'avg': 6}]
    assert data.aggregate(ref, metrics, [{'field': 'name', 'op': 'in', 'values': [None]}]) == [{'ratio': None, 'sum': None, 'count': 1, 'avg': None}]
    assert data.aggregate(ref, metrics, [{'field': 'name', 'op': 'in', 'values': ['absent']}]) == [{'ratio': None, 'sum': None, 'count': 0, 'avg': None}]
    grouped = data.aggregate(ref, {'sum': metrics['sum']}, group_by=['date'], time_grain='quarter')
    assert grouped == [{'date': '2026 Q1', 'sum': 12}, {'date': '2026 Q2', 'sum': None}]


def test_filter_sort_pagination_and_complete_export(tmp_path):
    data = LocalData(tmp_path)
    ref = dataset(data)
    result = data.rows(ref, sort=[{'field': 'amount', 'direction': 'desc'}], offset=1, limit=1, columns=['name', 'amount'])
    assert result['totalRows'] == 3
    assert result['rows'] == [{'name': 'ÄLPHA', 'amount': 4}]
    assert data.rows(ref, [{'field': 'name', 'op': 'contains', 'values': ['äl']}])['rows'][0]['enabled'] is True
    assert data.rows(ref, [{'field': 'amount', 'op': 'range', 'values': [4, 8]}])['totalRows'] == 2
    assert data.distinct(ref, 'enabled') == [True, False, None]
    exported = data.export_csv(ref, tmp_path / 'all.csv', columns=['name', 'amount'], sort=[{'field': 'amount', 'direction': 'desc'}])
    with open(exported['path'], encoding='utf-8-sig', newline='') as handle:
        assert list(csv.reader(handle)) == [['name', 'amount'], ['Beta', '8'], ['ÄLPHA', '4'], ['', '']]
    assert exported['rowCount'] == 3
    with pytest.raises(ValueError, match='limit'):
        data.rows(ref, limit=100001)


def test_versions_streaming_and_metadata_verification(tmp_path):
    data = LocalData(tmp_path)
    ref = dataset(data)
    assert dataset(data) == ref
    assert data.describe(ref['version']) == ref
    assert len(list(data.iter_rows({'version': ref['version'], 'fields': {}}))) == 3
    stream = ({'x': i} for i in range(20000))
    version = data.import_rows(stream, {'x': {'type': 'number'}})
    assert version['rowCount'] == 20000
    assert data.aggregate(version, {'n': {'aggregation': 'count'}}) == [{'n': 20000}]
    with sqlite3.connect(data.path) as db:
        assert db.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 2
    with pytest.raises(ValueError):
        data.describe('../data.sqlite3')


def test_injection_and_readonly_import(tmp_path):
    source = tmp_path / 'source.sqlite3'
    table = 'odd"; DROP TABLE source;--'
    column = 'x"; DROP TABLE versions;--'
    def quote(value):
        return '"' + value.replace('"', '""') + '"'
    with sqlite3.connect(source) as db:
        db.execute(f'CREATE TABLE {quote(table)} ({quote(column)} REAL)')
        db.execute(f'INSERT INTO {quote(table)} VALUES (7)')
    data = LocalData(tmp_path / 'data')
    ref = data.import_sqlite(source, table)
    assert data.rows(ref)['rows'] == [{column: 7}]
    with pytest.raises(ValueError, match='Unknown field'):
        data.rows(ref, columns=['c0 FROM versions;--'])
    with pytest.raises(ValueError, match='Unknown SQLite table'):
        data.import_sqlite(source, table + '; DROP TABLE source')
    assert data.describe(ref['version'])['rowCount'] == 1


def test_result_bounds_raise_and_invalid_import_rolls_back(tmp_path, monkeypatch):
    import dashboard_runtime.local_data as module
    data = LocalData(tmp_path)
    ref = data.import_rows(({'x': i} for i in range(4)), {'x': {'type': 'number'}})
    monkeypatch.setattr(module, 'MAX_RESULT_ROWS', 2)
    with pytest.raises(ValueError, match='Result exceeds'):
        data.distinct(ref, 'x')
    with pytest.raises(ValueError, match='Result exceeds'):
        data.aggregate(ref, {}, group_by=['x'])
    with pytest.raises(ValueError, match='Invalid scalar'):
        data.import_rows([{'x': []}], {'x': {'type': 'number'}})
    assert data.import_rows([{'x': 2}], {'x': {'type': 'number'}})['rowCount'] == 1


def test_missing_values_roundtrip_and_lazy_index_reuse(tmp_path):
    data = LocalData(tmp_path)
    fields = {'x': {'type': 'number'}, 'name': {'type': 'string'}}
    rows = [{'x': 1}, {'x': None, 'name': 'A'}, {'name': None}]
    ref = data.import_rows(iter(rows), fields)
    assert ref['hasMissingFields'] is True
    assert list(data.iter_rows(ref)) == rows
    assert data.rows(ref)['rows'] == rows
    explicit = data.import_rows([{'x': 1, 'name': None}, {'x': None, 'name': 'A'}, {'x': None, 'name': None}], fields)
    assert explicit['version'] != ref['version']
    filters = [{'field': 'x', 'op': 'range', 'values': [0, 9]}]
    sort = [{'field': 'name', 'direction': 'asc'}]
    data.rows(ref, filters, sort=sort)
    with sqlite3.connect(data.path) as db:
        first = db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'i_%'").fetchall()
    data.rows(ref, filters, sort=sort)
    with sqlite3.connect(data.path) as db:
        second = db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'i_%'").fetchall()
    assert first == second
    assert len(first) == 2


def test_sqlite_declared_boolean_conversion(tmp_path):
    source = tmp_path / 'booleans.sqlite3'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE source (enabled INTEGER)')
        db.executemany('INSERT INTO source VALUES (?)', [(0,), (1,), (None,)])
    data = LocalData(tmp_path / 'data')
    ref = data.import_sqlite(source, 'source', {'enabled': {'type': 'boolean'}})
    assert data.rows(ref)['rows'] == [{'enabled': False}, {'enabled': True}, {'enabled': None}]
    assert data.rows(ref, [{'field': 'enabled', 'op': 'contains', 'values': ['TRUE']}])['totalRows'] == 1


def test_search_matches_visible_fields_null_unicode_and_full_export(tmp_path):
    data = LocalData(tmp_path)
    fields = {'label': {'type': 'string'}, 'amount': {'type': 'number'},
              'rawLabel': {'type': 'string'}, '_private': {'type': 'string'}}
    ref = data.import_rows([
        {'label': 'ÄLPHA', 'amount': 1234, 'rawLabel': 'secret', '_private': 'hidden'},
        {'label': None, 'amount': 15, 'rawLabel': 'secret', '_private': 'hidden'},
        {'label': 'Beta', 'amount': 1234, 'rawLabel': 'secret', '_private': 'hidden'},
    ], fields)
    assert data.rows(ref, search='äl')['totalRows'] == 1
    assert data.rows(ref, search='NULL')['rows'][0]['label'] is None
    assert data.rows(ref, search='secret')['totalRows'] == 0
    assert data.rows(ref, search='hidden')['totalRows'] == 0
    page = data.rows(ref, search='1234', columns=['label'], limit=1, offset=1)
    assert page['totalRows'] == 2
    assert page['rows'] == [{'label': 'Beta'}]
    result = data.export_csv(ref, tmp_path / 'search.csv', columns=['label'], search='1234')
    assert result['rowCount'] == 2
    with open(result['path'], encoding='utf-8-sig', newline='') as handle:
        assert list(csv.reader(handle)) == [['label'], ['ÄLPHA'], ['Beta']]
    assert data.rows(ref, search="%' OR 1=1 --")['totalRows'] == 0


def test_table_sort_numeric_display_and_raw_override(tmp_path):
    data = LocalData(tmp_path)
    fields = {'label': {'type': 'string'}, 'rate': {'type': 'string'},
              'rawRate': {'type': 'number'}, 'date': {'type': 'date'}}
    ref = data.import_rows([
        {'label': '¥1,234', 'rate': '99%', 'rawRate': 1, 'date': '2026-01-01'},
        {'label': '12.4%', 'rate': '1%', 'rawRate': 20, 'date': '2026-10-01'},
        {'label': '-2.5%', 'rate': '10%', 'rawRate': 3, 'date': '2026-02-01'},
    ], fields)
    assert [r['label'] for r in data.rows(ref, sort=[{'field': 'label', 'direction': 'asc'}])['rows']] == ['-2.5%', '12.4%', '¥1,234']
    assert [r['rawRate'] for r in data.rows(ref, sort=[{'field': 'rate', 'direction': 'desc'}])['rows']] == [20, 3, 1]
    assert [r['date'] for r in data.rows(ref, sort=[{'field': 'date', 'direction': 'asc'}])['rows']] == ['2026-01-01', '2026-02-01', '2026-10-01']
    result = data.export_csv(ref, tmp_path / 'sorted.csv', columns=['rawRate'], sort=[{'field': 'rate', 'direction': 'desc'}])
    with open(result['path'], encoding='utf-8-sig', newline='') as handle:
        assert list(csv.reader(handle)) == [['rawRate'], ['20'], ['3'], ['1']]


def test_explicit_null_filter_and_search_exclude_missing_fields(tmp_path):
    data = LocalData(tmp_path)
    # A second visible field must remain searchable even when name is missing.
    ref = data.import_rows([{'name': None}, {}, {'name': 'null string'}, {'other': 'null other'}],
                           {'name': {'type': 'string'}, 'other': {'type': 'string'}})
    null_filter = [{'field': 'name', 'op': 'in', 'values': [None]}]
    assert data.rows(ref, null_filter)['rows'] == [{'name': None}]
    assert data.aggregate(ref, {'count': {'aggregation': 'count'}}, null_filter) == [{'count': 1}]
    assert data.rows(ref, search='null')['rows'] == [{'name': None}, {'name': 'null string'}, {'other': 'null other'}]
    assert data.rows(ref, [{'field': 'name', 'op': 'in', 'values': [None, 'null string']}])['totalRows'] == 2
    exported = data.export_csv(ref, tmp_path / 'null.csv', filters=null_filter)
    assert exported['rowCount'] == 1
    searched = data.export_csv(ref, tmp_path / 'search-null.csv', search='null')
    assert searched['rowCount'] == 3


def test_original_field_order_survives_versions_reopen_and_default_csv(tmp_path):
    fields = {'zulu': {'type': 'number'}, 'alpha': {'type': 'string'}, 'middle': {'type': 'boolean'}}
    rows = [{'zulu': 7, 'alpha': 'visible', 'middle': True}]
    data = LocalData(tmp_path)
    ref = data.import_rows(iter(rows), fields)
    assert list(ref['fields']) == ['zulu', 'alpha', 'middle']
    assert ref['fieldOrder'] == ['zulu', 'alpha', 'middle']
    reopened = LocalData(tmp_path)
    assert list(reopened.describe(ref['version'])['fields']) == list(fields)
    assert list(reopened.import_rows(iter(rows), fields)['fields']) == list(fields)
    assert list(reopened.rows(ref)['rows'][0]) == list(fields)
    assert list(next(reopened.iter_rows(ref))) == list(fields)
    assert reopened.rows(ref, [{'field': 'zulu', 'op': 'range', 'values': [5, 10]}])['rows'] == rows
    assert reopened.aggregate(ref, {'sum': {'aggregation': 'sum', 'field': 'zulu'}}) == [{'sum': 7}]
    exported = reopened.export_csv(ref, tmp_path / 'original-order.csv')
    with open(exported['path'], encoding='utf-8-sig', newline='') as handle:
        assert list(csv.reader(handle)) == [['zulu', 'alpha', 'middle'], ['7', 'visible', 'true']]
    same_values = [{'zulu': 1, 'alpha': 1}]
    first = data.import_rows(same_values, {'zulu': {'type': 'number'}, 'alpha': {'type': 'number'}})
    second = data.import_rows(same_values, {'alpha': {'type': 'number'}, 'zulu': {'type': 'number'}})
    assert first['version'] != second['version']


def test_older_metadata_without_field_order_still_maps_original_columns(tmp_path):
    data = LocalData(tmp_path)
    fields = {'alpha': {'type': 'number'}, 'zulu': {'type': 'string'}}
    ref = data.import_rows([{'alpha': 11, 'zulu': 'old'}], fields)
    # Simulate the previous metadata format; physical columns were alphabetic.
    with sqlite3.connect(data.path) as db:
        old = dict(ref)
        old.pop('fieldOrder')
        import json
        db.execute('UPDATE versions SET metadata=? WHERE version=?', (json.dumps(old, sort_keys=True), ref['version']))
    reopened = LocalData(tmp_path)
    assert reopened.describe(ref['version']) == old
    assert reopened.rows(old)['rows'] == [{'alpha': 11, 'zulu': 'old'}]
    assert list(reopened.iter_rows(old)) == [{'alpha': 11, 'zulu': 'old'}]
    assert reopened.import_rows([{'alpha': 11, 'zulu': 'old'}], fields) == old
