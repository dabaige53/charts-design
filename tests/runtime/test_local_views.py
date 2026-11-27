"""Service-level local acceptance; all data lives in pytest temporary directories."""
import copy
import base64
import csv
from contextlib import closing
from functools import partial
import importlib.util
import json
import os
from pathlib import Path
import sqlite3

import pytest

from dashboard_runtime.model import DashboardError, apply_operations, json_bytes, new_document, utcnow
from dashboard_runtime.project_routing import ProjectServices
from dashboard_runtime.service import Service

spec = importlib.util.spec_from_file_location('local_acceptance_benchmark', Path(__file__).with_name('benchmark_local.py'))
assert spec is not None and spec.loader is not None
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


@pytest.fixture
def local(tmp_path):
    return benchmark.attach(tmp_path, 240)


# @wu-test type=integration | scope=PostgreSQL 与 DuckDB 实时 SQL | protects=刷新读取旧值、数值日期绑定失败、筛选漏应用或查询写入源库
@pytest.mark.parametrize('engine', ['duckdb', 'postgresql'])
def test_external_sql_live_refresh(tmp_path, monkeypatch, engine):
    if engine == 'postgresql':
        import psycopg
        dsn = os.getenv('CHARTS_TEST_POSTGRESQL_DSN')
        if not dsn:
            pytest.skip('Set CHARTS_TEST_POSTGRESQL_DSN to a disposable PostgreSQL database')
        monkeypatch.setenv('TEST_SALES_DSN', dsn)
        connect = partial(psycopg.connect, dsn, autocommit=True)
        source = {'engine': engine, 'dsnEnv': 'TEST_SALES_DSN'}
        parameter = '%(minimum)s'
    else:
        import duckdb
        path = str(tmp_path / 'sales.duckdb')
        connect = partial(duckdb.connect, path)
        source = {'engine': engine, 'path': path}
        parameter = '$minimum'

    with closing(connect()) as db:
        db.execute('CREATE TABLE charts_connector_test_sales (region VARCHAR, amount DECIMAL(10, 2), month DATE, active BOOLEAN)')
    try:
        with closing(connect()) as db:
            db.execute("""INSERT INTO charts_connector_test_sales VALUES
                        ('east', 12.25, DATE '2026-11-01', TRUE), ('west', 8, DATE '2026-11-01', FALSE)""")
        config = tmp_path / 'sources.json'
        config.write_text(json.dumps({'sales': source}))
        services = ProjectServices(Service(tmp_path / 'runtime', config))
        service, _ = services.resolve({'projectRoot': str(tmp_path / 'project')})
        board = {'dashboardId': 'sales-test'}
        service.call('dashboard_create', board)
        sql = f'SELECT region, amount, month, active FROM charts_connector_test_sales WHERE amount >= {parameter};'
        saved = service.call('query_execute', {**board, 'expectedRevision': 1,
            'datasetId': 'sales', 'mode': 'live', 'connection': 'sales', 'sql': sql, 'parameters': {'minimum': 8}})
        assert saved['execution']['engine'] == engine
        fields = saved['document']['manifest']['datasets']['sales']['fields']
        assert fields['month']['type'] == 'date'
        assert fields['amount']['type'] == 'number'
        assert fields['active']['type'] == 'boolean'
        assert 'sales' not in saved['document']['snapshot']['datasets']
        assert 'sales' not in saved['document']['snapshot'].get('datasetRefs', {})

        table_id = 'sales-table'
        selection = {'id': 'region', 'op': 'in', 'label': 'Region', 'field': 'region',
                     'componentIds': [table_id], 'values': []}
        service.call('dashboard_patch', {**board, 'expectedRevision': 2, 'operations': [
            {'op': 'put_component', 'id': table_id,
             'value': {'kind': 'table', 'title': 'Sales', 'datasetId': 'sales'}},
            {'op': 'set_filters', 'value': [selection]},
        ]})
        assert service.call('dashboard_checkpoint', {**board, 'expectedRevision': 3})['ok']
        filtered = [{**selection, 'id': 'runtime-linkage', 'values': ['east']}]
        reading = {**board, 'expectedRevision': 3, 'responseMode': 'patch', 'componentIds': [table_id]}
        first = service.call('dashboard_view', {**reading, 'filters': filtered})
        assert first['computed']['components'][table_id]['rows'] == [
            {'region': 'east', 'amount': 12.25, 'month': '2026-11-01', 'active': True}]
        assert service.call('query_inspect', {**board, 'expectedRevision': 3,
                            'componentId': table_id})['source']['query']['sql'] == sql

        for rejected in ['UPDATE charts_connector_test_sales SET amount = 100 RETURNING amount', 'SELECT 1; SELECT 2']:
            with pytest.raises(DashboardError) as error:
                service.queries.execute('sales', rejected)
            assert error.value.code == 'QUERY_REJECTED'
        if engine == 'duckdb':
            csv_path = tmp_path / 'external.csv'
            csv_path.write_text('region,amount\neast,100\n')
            with pytest.raises(DashboardError) as error:
                service.queries.execute('sales', 'SELECT * FROM read_csv(?)', [str(csv_path)])
            assert error.value.code == 'QUERY_REJECTED'

        with closing(connect()) as db:
            db.execute("UPDATE charts_connector_test_sales SET amount = 15.5 WHERE region = 'east'")
        refresh = service.call('dashboard_refresh', {**board, 'filters': filtered})['document']
        assert refresh['revision'] == reading['expectedRevision']
        final = service.call('dashboard_view', {**reading, 'filters': refresh['manifest']['filters']})
        assert final['computed']['components'][table_id]['rows'] == [
            {'region': 'east', 'amount': 15.5, 'month': '2026-11-01', 'active': True}]
        options = service.call('dashboard_filter_options', {**board, 'expectedRevision': 3, 'filterId': 'region'})
        assert options['values'] == ['east', 'west']
    finally:
        if engine == 'postgresql':
            with closing(connect()) as db:
                db.execute('DROP TABLE charts_connector_test_sales')


# @wu-test type=integration | scope=实时 SQL 看板 | protects=刷新只读旧数据、混合筛选漏项或查询行与分块保存到磁盘
def test_live_sql_refresh_filters_and_persistence(tmp_path):
    source, config = benchmark.build_source(tmp_path, 4)
    service = Service(tmp_path / 'runtime', config, project_root=tmp_path / 'project')
    board = {'dashboardId': 'acceptance'}
    service.call('dashboard_create', board)
    sql = 'SELECT * FROM facts WHERE rowId >= :first'
    service.call('query_execute', {**board, 'expectedRevision': 1, 'mode': 'live',
                                  'datasetId': 'facts', 'connection': 'benchmark', 'sql': sql,
                                  'parameters': {'first': 0}, 'fields': benchmark.FIELDS})
    operations = benchmark.operations(4)
    selection = operations[-1]['value'][0]
    selection['componentIds'] = [*selection['componentIds'], 'static-details']
    operations.extend([
        {'op': 'put_source', 'id': 'manual', 'value': {'kind': 'file'}},
        {'op': 'put_dataset', 'id': 'manual', 'meta': {'sourceId': 'manual', 'fields': benchmark.FIELDS},
         'rows': [{**benchmark.source_row(0), 'department': 'Static department'}]},
        {'op': 'put_component', 'id': 'static-details',
         'value': {'kind': 'table', 'title': 'Static details', 'datasetId': 'manual'}},
    ])
    service.call('dashboard_patch', {**board, 'expectedRevision': 2, 'operations': operations})
    assert service.call('dashboard_checkpoint', {**board, 'expectedRevision': 3})['ok']

    filters = benchmark.filters()
    filters.append({'id': 'runtime-linkage', 'label': 'Department', 'field': 'department',
                    'op': 'in', 'values': ['Department-1'], 'componentIds': ['total', 'details']})
    reading = {**board, 'expectedRevision': 3}
    view = {**reading, 'responseMode': 'patch', 'componentIds': ['total', 'details']}
    first = service.call('dashboard_view', {**view, 'filters': filters})
    amount = benchmark.source_row(1)['amount']
    assert first['computed']['components']['total']['value'] == f'{amount:,}'
    assert service.call('query_inspect', {**reading, 'componentId': 'category'})['source']['query']['sql'] == sql
    before = service.store.get('acceptance', hydrate=False)
    assert set(before['snapshot']['datasetRefs']) == {'manual'}
    live_source = before['manifest']['datasets']['facts']['sourceId']
    with pytest.raises(DashboardError) as forbidden:
        service.call('dashboard_patch', {**reading, 'operations': [
            {'op': 'put_source', 'id': live_source, 'value': {'kind': 'declared'}},
        ]})
    assert forbidden.value.code == 'INVALID_OPERATION'

    long_value = 'fresh-' * 9_000
    with closing(sqlite3.connect(source)) as db, db:
        db.execute('UPDATE facts SET amount=?, agent=? WHERE rowId=1', (amount + 1000, long_value))
        db.execute('UPDATE facts SET department=? WHERE rowId=2', ('New department',))

    refreshed = service.call('dashboard_refresh', {**board, 'filters': filters})['document']
    result = service.call('dashboard_view', {**view, 'filters': refreshed['manifest']['filters']})
    assert result['computed']['components']['total']['value'] == f'{amount + 1000:,}'
    assert result['computed']['tables']['details']['totalRows'] == 1
    options = service.call('dashboard_filter_options', {**reading, 'filterId': 'department',
                           'search': 'department', 'offset': 2, 'limit': 3})
    assert options['values'] == ['Department-3', 'New department', 'Static department']
    detail = service.call('component_data', {**reading, 'componentId': 'details', 'filters': filters})
    assert [(row['amount'], row['agent']) for row in detail['rows']] == [(amount + 1000, long_value)]
    packed = service.transport.pack(detail, 'component_data')['transport']
    request_id = packed['requestId']
    assert service.transport.chunk({'requestId': request_id, 'index': 0})['data']
    assert json.loads(service.transport.result_text(request_id))['rows'] == detail['rows']
    with closing(sqlite3.connect(service.transport.cache_path)) as db:
        assert db.execute('SELECT count(*) FROM results').fetchone()[0] == 0
    with closing(sqlite3.connect(service.store.data.path)) as db:
        assert db.execute('SELECT count(*) FROM versions').fetchone()[0] == 1

    csv_result = service.call('dataset_export', {**reading, 'componentId': 'details',
                             'columns': ['amount'], 'filters': filters})['export']
    assert base64.b64decode(csv_result['content']).decode('utf-8-sig').splitlines() == ['amount', str(amount + 1000)]
    assert 'path' not in csv_result
    assert service.store.get('acceptance', hydrate=False) == before


# @wu-test type=integration | scope=本地服务 | protects=导入到导出丢数据
def test_local_service_end_to_end_small_fixture(tmp_path):
    report = benchmark.run_benchmark(tmp_path, 240)
    assert report['status'] == 'passed'
    assert report['sourceRows'] == report['exportRows'] == 240
    assert report['dataVersions'] == 1
    assert max(report['historyDocumentBytes']) < 32_000


# @wu-test type=integration | scope=筛选视图导出 | protects=图表表格导出筛选范围不同 | debt=impl-detail
def test_local_filtered_components_and_reader_state_not_saved(local, tmp_path):
    service, _, imported, configured, _ = local
    benchmark.assert_compact(imported, 240)
    benchmark.assert_compact(configured, 240)
    original = service.store.get('acceptance', hydrate=False)
    active = benchmark.filters(True)
    result = service.call('dashboard_view', {'dashboardId': 'acceptance', 'filters': active})['document']
    selected = [benchmark.source_row(i) for i in range(240) if i % 4 == 1 and (i//4) % 12 < 2]
    expected = benchmark.expected_totals(selected)
    computed = result['computed']
    assert computed['components']['total']['value'] == f"{expected['amount']:,}"
    assert computed['components']['total']['subVal'] == str(expected['count'])
    assert computed['components']['category']['data'] == {'categories': ['Department-1'], 'values': [expected['amount']]}
    assert computed['components']['rate']['value'] == f"{expected['ratio']:.2%}"
    assert computed['tables']['details']['totalRows'] == expected['count']
    assert len(computed['components']['details']['rows']) == 10
    assert len(computed['filterOptions']['department']) == 4
    assert len(computed['filterOptions']['month']) == 12
    repeated = service.call('dashboard_view', {'dashboardId': 'acceptance', 'filters': active})['document']
    assert repeated['computed']['cacheHits'] >= 3
    assert service.store.get('acceptance', hydrate=False) == original
    exported = service.call('dataset_export', {'dashboardId': 'acceptance', 'componentId': 'details', 'filters': active,
                                              'columns': ['rowId', 'amount'], 'sort': [{'field': 'rowId', 'direction': 'desc'}]})['export']
    with Path(exported['path']).open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert exported['rowCount'] == len(selected)
    assert [int(row['rowId']) for row in rows] == sorted([row['rowId'] for row in selected], reverse=True)
    assert sum(int(row['amount']) for row in rows) == expected['amount']


# @wu-test type=integration | scope=表格CLI导出 | protects=添加说明后丢列或导出不完整
def test_native_table_preserves_presentation_columns_with_explanation(local, tmp_path, capsys):
    from dashboard_runtime.__main__ import main
    service, _, _, _, _ = local
    doc = service.store.get('acceptance', hydrate=False)
    component = doc['manifest']['components']['details']
    component['presentation'] = {'columns': [{'key': 'agent', 'title': 'Agent'}, {'key': 'amount', 'title': 'Amount'}]}
    component['config'] = {'explanation': 'Business definition'}
    viewed = service.call('dashboard_patch', {'dashboardId': 'acceptance', 'expectedRevision': doc['revision'],
        'operations': [{'op': 'put_component', 'id': 'details', 'value': component}]})['document']
    table = viewed['computed']['components']['details']
    assert table['columns'] == component['presentation']['columns']
    assert list(table['rows'][0]) == ['agent', 'amount']
    output = tmp_path / 'full.csv'
    assert main(['--root', str(service.store.root), 'export', 'acceptance', '--format', 'csv', '--dataset', 'facts', '--output', str(output)]) == 0
    assert json.loads(capsys.readouterr().out)['rowCount'] == 240
    with output.open(encoding='utf-8-sig', newline='') as handle:
        assert len(list(csv.DictReader(handle))) == 240
    snapshot = tmp_path / 'small.json'
    assert main(['--root', str(service.store.root), 'export', 'acceptance', '--format', 'json', '--output', str(snapshot)]) == 0
    assert len(json.loads(snapshot.read_text())['snapshot']['datasets']['facts']) == 240


# @wu-test type=integration | scope=筛选选项分页 | protects=高基数选项漏项或无法选末项
def test_option_pages_cover_the_complete_high_cardinality_domain(local):
    service, _, _, _, _ = local
    canonical = service.store.get('acceptance', hydrate=False)
    declared = [*canonical['manifest']['filters'], {'id': 'row-selector', 'field': 'rowId', 'label': 'Row ID',
                'op': 'in', 'values': [], 'componentIds': benchmark.COMPONENT_IDS}]
    response = service.call('dashboard_patch', {'dashboardId': 'acceptance', 'expectedRevision': canonical['revision'],
        'operations': [{'op': 'set_filters', 'value': declared}]})['document']
    first = response['computed']['filterPages']['row-selector']
    assert first['totalValues'] == 240 and first['hasMore'] and len(first['values']) == 100
    options = []
    for offset in (0, 100, 200):
        page = service.call('dashboard_filter_options', {'dashboardId': 'acceptance', 'filterId': 'row-selector', 'offset': offset})
        options.extend(page['values'])
    assert options == list(range(240))
    last = service.call('dashboard_filter_options', {'dashboardId': 'acceptance', 'filterId': 'row-selector', 'search': '239'})
    assert last['values'] == [239]
    declared[-1]['values'] = [239]
    viewed = service.call('dashboard_view', {'dashboardId': 'acceptance', 'filters': declared})['document']
    assert viewed['computed']['tables']['details']['totalRows'] == 1


# @wu-test type=integration | scope=数据版本共享 | protects=数据别名恢复后引用错误 | debt=impl-detail
def test_version_shared_by_two_dataset_aliases_and_restore(local):
    service, _, _, configured, _ = local
    before = service.store.get('acceptance', hydrate=False)
    original_ref = before['snapshot']['datasetRefs']['facts']
    response = service.call('dataset_attach', {'dashboardId': 'acceptance', 'expectedRevision': 3, 'datasetId': 'same-facts',
                                              'connection': 'benchmark', 'table': 'facts', 'fields': benchmark.FIELDS})
    benchmark.assert_compact(response, 240)
    inspect = service.call('dashboard_data_inspect', {'dashboardId': 'acceptance'})
    assert inspect['datasets']['same-facts'] == original_ref
    assert any(set(ids) == {'facts', 'same-facts'} for ids in inspect['sharedVersions'])
    with sqlite3.connect(service.store.data.path) as db:
        assert db.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 1
    restored = service.call('dashboard_restore', {'dashboardId': 'acceptance', 'expectedRevision': 4, 'revision': 3})
    assert restored['document']['snapshot']['datasetRefs'] == {'facts': original_ref}


# @wu-test type=integration | scope=旧数据迁移 | protects=迁移回滚丢原数据 | debt=impl-detail
def test_legacy_inline_snapshot_migration_backup_and_rollback(tmp_path):
    service = Service(tmp_path / 'store')
    rows = [benchmark.source_row(i) for i in range(24)]
    document = apply_operations(new_document('old', 'Original inline snapshot'), [
        {'op': 'put_source', 'id': 'old-source', 'value': {'kind': 'file', 'name': 'Legacy inline acceptance data'}},
        {'op': 'put_dataset', 'id': 'facts', 'meta': {'sourceId': 'old-source', 'fields': benchmark.FIELDS}, 'rows': rows},
        {'op': 'put_component', 'id': 'details', 'value': {'kind': 'table', 'title': 'Original detail', 'datasetId': 'facts'}},
    ])
    document['revision'] = 1
    raw = json_bytes(document).decode()
    with service.store.connect() as db:
        db.execute('INSERT INTO boards VALUES (?,?,?)', ('old', 1, raw))
        db.execute('INSERT INTO revisions VALUES (?,?,?,?,?)', ('old', 1, utcnow(), 'legacy-import', raw))
    migration = service.call('dashboard_migrate', {'dashboardId': 'old', 'expectedRevision': 1})
    assert migration['document']['revision'] == 1
    assert migration['document']['snapshot']['datasets'] == {}
    assert migration['document']['snapshot']['datasetRefs']['facts']['rowCount'] == 24
    assert migration['document']['computed']['tables']['details']['totalRows'] == 24
    backup_id = migration['migration']['backupId']
    backup = json.loads((service.store.root / 'backups' / (backup_id + '.json')).read_text())
    assert json.loads(backup['board']['document']) == document
    edited = service.call('dashboard_patch', {'dashboardId': 'old', 'expectedRevision': 1, 'operations': [{'op': 'set_title', 'value': 'After migration'}]})
    assert edited['document']['revision'] == 2
    restored = service.call('dashboard_migration_rollback', {'dashboardId': 'old', 'expectedRevision': 2, 'backupId': backup_id})['document']
    expected = copy.deepcopy(document)
    expected['revision'] = 3
    assert service.store.get('old', hydrate=False) == expected
    assert restored['snapshot']['datasets'] == {}
    assert restored['snapshot']['datasetRefs']['facts']['rowCount'] == 24
    assert restored['computed']['tables']['details']['totalRows'] == 24
    with service.store.connect() as db:
        history = db.execute('SELECT revision, action FROM revisions WHERE board_id=? ORDER BY revision', ('old',)).fetchall()
    assert [tuple(r) for r in history] == [(1, 'legacy-import'), (2, 'set_title'), (3, 'migration-rollback')]
