"""Optional offline acceptance benchmark: python tests/runtime/benchmark_local.py --output /tmp/local-benchmark/report.json."""
from __future__ import annotations

import argparse
import csv
import importlib
import heapq
import json
from pathlib import Path
import resource
import sqlite3
import sys
import time

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

new_document = importlib.import_module('dashboard_runtime.model').new_document
Service = importlib.import_module('dashboard_runtime.service').Service

FIELDS = {key: {'type': kind} for key, kind in [('rowId', 'number'), ('department', 'string'), ('month', 'date'), ('agent', 'string'), ('amount', 'number'), ('numerator', 'number'), ('denominator', 'number')]}
COMPONENT_IDS = ['total', 'rate', 'category', 'details']


def source_row(index):
    return {'rowId': index, 'department': f'Department-{index % 4}',
            'month': f'2026-{(index // 4) % 12 + 1:02}-01', 'agent': f'Agent-{index % 97:02}',
            'amount': index % 101 + 1, 'numerator': index % 19 + 1, 'denominator': index % 23 + 20}


def expected_totals(rows):
    totals: dict[str, int] = {'count': 0, 'amount': 0, 'numerator': 0, 'denominator': 0}
    for row in rows:
        totals['count'] += 1
        for key in ('amount', 'numerator', 'denominator'):
            totals[key] += row[key]
    ratio = totals['numerator'] / totals['denominator'] if totals['denominator'] else None
    return {**totals, 'ratio': ratio}


def build_source(root, count):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    source = root / 'source.sqlite3'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE facts (rowId INTEGER, department TEXT, month TEXT, agent TEXT, amount INTEGER, numerator INTEGER, denominator INTEGER)')
        db.executemany('INSERT INTO facts VALUES (?,?,?,?,?,?,?)', (tuple(source_row(i).values()) for i in range(count)))
    config = root / 'sources.json'
    config.write_text(json.dumps({'benchmark': {'engine': 'sqlite', 'path': str(source.resolve())}}))
    return source, config


def filters(selected=False):
    return [{'id': 'department', 'field': 'department', 'label': 'Department', 'op': 'in',
             'values': ['Department-1'] if selected else [], 'componentIds': COMPONENT_IDS},
            {'id': 'month', 'field': 'month', 'label': 'Month', 'op': 'in',
             'values': ['2026-01-01', '2026-02-01'] if selected else [], 'componentIds': COMPONENT_IDS}]


def operations(count):
    category_totals = [sum(source_row(i)['amount'] for i in range(department, count, 4)) for department in range(4)]
    metrics = {'amount': {'field': 'amount', 'aggregation': 'sum', 'label': 'Amount'},
               'count': {'aggregation': 'count', 'label': 'Records'},
               'rate': {'aggregation': 'ratio', 'numerator': 'numerator', 'denominator': 'denominator', 'label': 'Rate', 'format': 'percent', 'scale': 'fraction'}}
    result = [{'op': 'put_metric', 'id': key, 'value': {**value, 'datasetId': 'facts', 'definition': 'Independent integer acceptance fixture', 'unit': '', 'decimals': 2}} for key, value in metrics.items()]
    components = {
        'total': {'kind': 'legacy', 'family': 'kpi', 'title': 'Amount', 'config': {'type': 'mc02', 'label': 'Amount', 'value': '0', 'subVal': '0'},
                  'binding': {'datasetId': 'facts', 'measures': {'value': 'amount', 'subVal': 'count'}}},
        'rate': {'kind': 'kpi', 'title': 'Rate', 'datasetId': 'facts', 'measures': ['rate']},
        'category': {'kind': 'legacy', 'family': 'chart', 'title': 'Amount by department',
                     'config': {'code': 'c01', 'unit': '', 'data': {'categories': [f'Department-{i}' for i in range(4)], 'values': category_totals}, 'presentation': {'axisLabels': {'x': 'Department', 'y': 'Amount'}, 'seriesLabels': ['Amount'], 'tooltipValueLabels': ['Amount'], 'units': ['units'], 'tableHeaders': ['Department', 'Amount']}},
                     'binding': {'datasetId': 'facts', 'categoryField': 'department', 'categoryTarget': 'categories', 'measures': {'values': 'amount'}}},
        'details': {'kind': 'table', 'title': 'Details', 'datasetId': 'facts'},
    }
    result.extend({'op': 'put_component', 'id': key, 'value': value} for key, value in components.items())
    result.append({'op': 'set_filters', 'value': filters()})
    return result


def attach(root, count):
    source, config = build_source(root, count)
    service = Service(Path(root) / 'store', config)
    service.call('dashboard_create', {'dashboardId': 'acceptance', 'document': new_document('acceptance', 'Local acceptance')})
    started = time.perf_counter()
    response = service.call('dataset_attach', {'dashboardId': 'acceptance', 'expectedRevision': 1, 'datasetId': 'facts', 'connection': 'benchmark', 'table': 'facts', 'fields': FIELDS})
    duration = (time.perf_counter()-started)*1000
    configured = service.call('dashboard_patch', {'dashboardId': 'acceptance', 'expectedRevision': 2, 'operations': operations(count)})
    return service, source, response, configured, duration


def assert_compact(response, count, page_size=10):
    document = response['document']
    assert document['snapshot']['datasets'] == {}
    assert document['snapshot']['datasetRefs']['facts']['rowCount'] == count
    if 'details' in document.get('computed', {}).get('components', {}):
        assert len(document['computed']['components']['details']['rows']) <= page_size
    assert len(json.dumps(response).encode()) < 100_000


def run_benchmark(root, count):
    root = Path(root)
    service, source, imported, configured, import_ms = attach(root, count)
    assert_compact(imported, count)
    assert_compact(configured, count)
    timings = {'import': import_ms}
    response_sizes = {'attach': len(json.dumps(imported).encode())}
    def measured(name, tool, **arguments):
        started = time.perf_counter()
        result = service.call(tool, {'dashboardId': 'acceptance', **arguments})
        timings[name] = (time.perf_counter()-started)*1000
        response_sizes[name] = len(json.dumps(result).encode())
        return result
    opened = measured('open', 'dashboard_get', dataMode='local')
    assert_compact(opened, count)
    preview = measured('preview', 'dashboard_preview')
    assert_compact(preview, count)
    selected = measured('filter', 'dashboard_view', filters=filters(True))
    assert_compact(selected, count)
    metrics = service.store.get('acceptance', hydrate=False)['manifest']['metrics']
    ref = opened['document']['snapshot']['datasetRefs']['facts']
    started = time.perf_counter()
    actual = service.store.data.aggregate(ref, metrics, filters(True))[0]
    timings['aggregate'] = (time.perf_counter()-started)*1000
    expected = expected_totals(source_row(i) for i in range(count) if i % 4 == 1 and (i//4) % 12 < 2)
    assert actual == {'amount': expected['amount'], 'count': expected['count'], 'rate': expected['ratio']}
    assert selected['document']['computed']['tables']['details']['totalRows'] == expected['count']
    assert opened['document']['computed']['filterOptions']['department'] == [f'Department-{i}' for i in range(min(4, count))]
    page = measured('page', 'dashboard_view', tableStates={'details': {'page': 2, 'pageSize': 25}})
    assert_compact(page, count, 25)
    if count > 25:
        assert page['document']['computed']['components']['details']['rows'][0]['rowId'] == 25
    sorted_result = measured('sort', 'dashboard_view', tableStates={'details': {'page': 1, 'pageSize': 25, 'sortCol': 'amount', 'sortDir': 'desc'}})
    assert_compact(sorted_result, count, 25)
    sorted_rows = sorted_result['document']['computed']['components']['details']['rows']
    assert [r['amount'] for r in sorted_rows] == heapq.nlargest(25, (source_row(i)['amount'] for i in range(count)))
    searched = measured('search', 'dashboard_view', tableStates={'details': {'keyword': 'Agent-17', 'pageSize': 25}})
    assert searched['document']['computed']['tables']['details']['totalRows'] == sum(i % 97 == 17 for i in range(count))
    exported = measured('export', 'dataset_export', datasetId='facts')['export']
    assert exported['rowCount'] == count
    exported_rows = exported_sum = 0
    with Path(exported['path']).open(encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            exported_rows += 1
            exported_sum += int(row['amount'])
    assert exported_rows == count
    overall = expected_totals(source_row(i) for i in range(count))
    assert exported_sum == overall['amount']
    components = opened['document']['computed']['components']
    assert components['total']['value'] == f"{overall['amount']:,}"
    assert components['rate']['value'] == f"{overall['ratio']:.2%}"
    assert components['category']['data']['values'] == [sum(source_row(i)['amount'] for i in range(department, count, 4)) for department in range(4)]
    with sqlite3.connect(service.store.data.path) as db:
        versions_before = db.execute('SELECT COUNT(*) FROM versions').fetchone()[0]
    edited = measured('edit', 'dashboard_patch', expectedRevision=3, operations=[{'op': 'set_title', 'value': 'Edited local acceptance'}])
    restored = measured('restore', 'dashboard_restore', expectedRevision=4, revision=3)
    assert edited['document']['snapshot']['datasetRefs'] == restored['document']['snapshot']['datasetRefs']
    with sqlite3.connect(service.store.data.path) as db:
        assert db.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == versions_before
    with service.store.connect() as db:
        histories = [len(row[0].encode()) for row in db.execute('SELECT document FROM revisions')]
    assert max(histories) < 32_000
    with sqlite3.connect(source) as db:
        source_rows = db.execute('SELECT COUNT(*) FROM facts').fetchone()[0]
    assert source_rows == count
    return {'rows': count, 'sourceRows': source_rows, 'exportRows': exported_rows, 'timingsMs': timings,
            'datasetLogicalBytes': ref['bytes'], 'memoryScope': 'Peak RSS of Python acceptance process on macOS; excludes browser and Codex host',
            'peakRSSBytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'diskBytes': {'source': source.stat().st_size, 'data': service.store.data.path.stat().st_size,
                          'config': service.store.path.stat().st_size,
                          'configWAL': Path(str(service.store.path) + '-wal').stat().st_size if Path(str(service.store.path) + '-wal').exists() else 0,
                          'csv': exported['bytes']},
            'responseBytes': response_sizes, 'historyDocumentBytes': histories,
            'independentExpectedFiltered': expected, 'actualFiltered': actual,
            'independentExpectedOverall': overall, 'exportAmountSum': exported_sum,
            'dataVersions': versions_before, 'exportPath': exported['path'], 'status': 'passed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows', type=int, default=1_000_000)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.rows < 100:
        parser.error('--rows must be at least 100')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # An independent run directory prevents touching existing sources or dashboard databases.
    import tempfile
    root = Path(tempfile.mkdtemp(prefix='.local-benchmark-', dir=args.output.parent)).resolve()
    report = run_benchmark(root, args.rows)
    report['workspace'] = str(root)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'rows': args.rows, 'report': str(args.output.resolve()), 'timingsMs': report['timingsMs']}))


if __name__ == '__main__':
    main()
