"""Service-level local acceptance; all data lives in pytest temporary directories."""
import copy
import csv
import importlib.util
import json
from pathlib import Path
import sqlite3
import re
import subprocess

import pytest

from dashboard_runtime.model import apply_operations, json_bytes, new_document, utcnow
from dashboard_runtime.service import Service

spec = importlib.util.spec_from_file_location('local_acceptance_benchmark', Path(__file__).with_name('benchmark_local.py'))
assert spec is not None and spec.loader is not None
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_pdf_exports_every_sorted_row_across_batches(tmp_path):
    service, _, _, _, _ = benchmark.attach(tmp_path, 1005)
    doc = service.store.get('acceptance', hydrate=False)
    component = copy.deepcopy(doc['manifest']['components']['details'])
    component['presentation'] = {'columns': [{'key': 'rowId', 'title': 'rowId'}, {'key': 'agent', 'title': 'agent'}]}
    service.call('dashboard_patch', {'dashboardId': 'acceptance', 'expectedRevision': doc['revision'],
        'operations': [{'op': 'put_component', 'id': 'details', 'value': component}]})
    result = service.call('dashboard_export', {'dashboardId': 'acceptance', 'format': 'pdf',
        'tableStates': {'details': {'page': 2, 'pageSize': 10, 'sortCol': 'rowId', 'sortDir': 'desc'}}})['export']
    assert result['tableRows'] == {'details': 1005}
    text = subprocess.check_output(['pdftotext', '-layout', result['path'], '-'], text=True)
    ids = [int(x) for x in re.findall(r'^\s*(\d+)\s+Agent-\d+', text, re.MULTILINE)]
    assert ids == list(range(1004, -1, -1))
    assert '搜索明细' not in text and '当前页快照' not in text


@pytest.fixture
def local(tmp_path):
    return benchmark.attach(tmp_path, 240)


def test_local_service_end_to_end_small_fixture(tmp_path):
    report = benchmark.run_benchmark(tmp_path, 240)
    assert report['status'] == 'passed'
    assert report['sourceRows'] == report['exportRows'] == 240
    assert report['dataVersions'] == 1
    assert max(report['historyDocumentBytes']) < 32_000


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
