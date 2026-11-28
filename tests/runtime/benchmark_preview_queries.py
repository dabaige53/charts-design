"""Compare local preview queries with a Git baseline using identical synthetic data.

Runs only when explicitly invoked; does not impose machine-dependent CI limits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import types

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dashboard_runtime.local_data import LocalData


def compare(rows, samples, baseline_ref):
    commit = subprocess.check_output(
        ['git', 'rev-parse', '--verify', '--end-of-options', baseline_ref + '^{commit}'],
        cwd=REPO, text=True).strip()
    baseline_source = subprocess.check_output(
        ['git', 'show', commit + ':dashboard_runtime/local_data.py'], cwd=REPO)
    baseline = types.ModuleType('dashboard_runtime._preview_baseline')
    baseline.__package__ = 'dashboard_runtime'
    exec(compile(baseline_source, '<baseline local_data.py>', 'exec'), baseline.__dict__)
    fields = {'name': {'type': 'string'}, 'amount': {'type': 'number'},
              'base': {'type': 'number'}, 'rate': {'type': 'number'}}
    expected = {}

    def observations():
        for index in range(rows):
            name, amount, base = f'Group-{index % 1000:04}', index % 101 + 1, index % 23 + 1
            totals = expected.setdefault(name, {'name': name, 'amount': 0, 'base': 0})
            totals['amount'] += amount
            totals['base'] += base
            yield {'name': name, 'amount': amount, 'base': base}

    results = {name: {'beforeMs': [], 'afterMs': []} for name in ('optionSearch', 'groupedPage', 'uniqueOptionMiss')}
    unique_rows = min(rows, 100_000)
    with tempfile.TemporaryDirectory(prefix='charts-preview-benchmark-') as directory:
        seeded = LocalData(directory)
        ref = seeded.import_rows(observations(), fields)
        unique_ref = seeded.import_rows(({'value': f'ID-{index:07}'} for index in range(unique_rows)),
                                        {'value': {'type': 'string'}})
        expected_options = sorted(name for name in expected if 'group-00' in name.lower())
        expected_groups = sorted(expected.values(), key=lambda row: -row['amount'])[:10]
        expected_page = [{**row, 'rate': row['amount'] / row['base']} for row in expected_groups]
        for sample in range(samples):
            # Alternate ordering; each measured request gets an empty application
            # query cache. Both versions read the exact same immutable database.
            variants = [('beforeMs', baseline.LocalData), ('afterMs', LocalData)]
            for label, factory in variants if sample % 2 == 0 else reversed(variants):
                data = factory(directory)
                started = time.perf_counter()
                options = data.option_page([ref], 'name', search='GROUP-00', limit=25, offset=25)
                results['optionSearch'][label].append((time.perf_counter() - started) * 1000)
                assert options == {'values': expected_options[25:50], 'totalValues': len(expected_options),
                                   'offset': 25, 'hasMore': len(expected_options) > 50}
                started = time.perf_counter()
                page = data.grouped_rows(ref, [], list(fields), [{'field': 'amount', 'direction': 'desc'}],
                                         0, 10, '', ['name'], ['amount', 'base', 'rate'],
                                         {'rate': {'numerator': 'amount', 'denominator': 'base'}})
                results['groupedPage'][label].append((time.perf_counter() - started) * 1000)
                assert page['rows'] == expected_page and page['totalRows'] == len(expected)
                started = time.perf_counter()
                missing = data.option_page([unique_ref], 'value', search='absent')
                results['uniqueOptionMiss'][label].append((time.perf_counter() - started) * 1000)
                assert missing == {'values': [], 'totalValues': 0, 'offset': 0, 'hasMore': False}
        database_bytes = Path(directory, 'data.sqlite3').stat().st_size
    for values in results.values():
        values['beforeMedianMs'] = statistics.median(values['beforeMs'])
        values['afterMedianMs'] = statistics.median(values['afterMs'])
        values['speedup'] = values['beforeMedianMs'] / values['afterMedianMs']
    return {
        'baselineCommit': commit, 'rows': rows, 'distinctGroups': len(expected), 'samples': samples,
        'uniqueSearchRows': unique_rows,
        'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
        'platform': platform.platform(), 'databaseBytes': database_bytes,
        'sourceSha256': {
            'before': hashlib.sha256(baseline_source).hexdigest(),
            'after': hashlib.sha256((REPO / 'dashboard_runtime/local_data.py').read_bytes()).hexdigest(),
        },
        'scope': 'One process, alternating before/after, empty application query caches; OS file cache is not cleared. Excludes import, HTTP, browser rendering and network.',
        'correctness': 'Each measured option page and grouped page checked against independently accumulated source observations, including sums, ratios and exact totals.',
        'results': results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--rows', type=int, default=200_000)
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.rows < 1000 or args.samples < 1:
        parser.error('Use at least 1000 rows and one sample.')
    report = compare(args.rows, args.samples, args.baseline_ref)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
