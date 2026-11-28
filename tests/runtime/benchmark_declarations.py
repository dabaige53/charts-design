"""Reproduce declaration discovery timings against an immutable Git baseline.

Explicit diagnostic only: no network, business data, or machine-dependent CI gate.
Each variant runs in a fresh process with its own source package and the same
Python interpreter. Warm samples exclude process startup and archive extraction.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import io
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]
SOURCES = (
    'dashboard_runtime/declarations.py', 'dashboard_runtime/chart_examples.py',
    'dashboard_runtime/recommend.py', 'dashboard_runtime/encoding.py',
    'dashboard_runtime/bindings.py', 'dashboard_runtime/kpi_cards.py',
    'dashboard_runtime/model.py', 'dashboard_runtime/statistical.py',
    'dashboard_runtime/structure_diagram.py',
    'skills/executive-charts/scripts/core/component_schemas.py',
    'skills/executive-charts/scripts/core/chart_catalog.py',
    'skills/executive-charts/references/chart_catalog.json',
)
SELECTED = ['c02', 't01', 'mc03', 'mc14']


def worker(root, samples, iterations, warmup):
    sys.path.insert(0, str(root))
    from dashboard_runtime.declarations import declaration_contract
    from dashboard_runtime.recommend import recommend_charts

    calls = {
        'declarations_index': lambda: declaration_contract(summary=True),
        'declarations_c02': lambda: declaration_contract(legacy_code='c02'),
        'recommend_comparison': lambda: recommend_charts({'intent': 'comparison', 'categories': 8, 'measures': 1}),
    }
    results = {}
    for name, call in calls.items():
        started = time.perf_counter()
        value = call()
        first_ms = (time.perf_counter() - started) * 1000
        for _ in range(warmup):
            call()
        measured = []
        for _ in range(samples):
            started = time.perf_counter()
            for _ in range(iterations):
                call()
            measured.append((time.perf_counter() - started) * 1000 / iterations)
        results[name] = {
            'firstCallMs': first_ms, 'warmMsPerCall': measured,
            'medianMsPerCall': statistics.median(measured),
            'jsonBytes': len(json.dumps(value, ensure_ascii=False).encode()),
        }
    assert declaration_contract(summary=True)['legacy']['counts']['registeredChartCodes'] == 40
    assert declaration_contract(legacy_code='c02')['selection']['code'] == 'c02'
    compact_bytes = lambda value: len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())
    delivery = {'codes': SELECTED,
                'individualJsonBytes': sum(compact_bytes(declaration_contract(legacy_code=code)) for code in SELECTED)}
    if 'legacy_codes' in inspect.signature(declaration_contract).parameters:
        batch = declaration_contract(legacy_codes=SELECTED)
        assert [selection['code'] for selection in batch['selections']] == SELECTED
        delivery['batchJsonBytes'] = compact_bytes(batch)
    return {'results': results, 'delivery': delivery,
            'sourceSha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                             for name in SOURCES if (root / name).is_file()}}


def baseline_package(commit, destination):
    archive = subprocess.check_output([
        'git', 'archive', '--format=tar', commit, '--', 'dashboard_runtime',
        'skills/executive-charts/scripts/core', 'skills/executive-charts/references/chart_catalog.json',
    ], cwd=REPO)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar:
            if not member.isfile():
                continue
            target = (destination / member.name).resolve()
            if not target.is_relative_to(destination):
                raise ValueError('Git archive path escapes benchmark source root')
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = tar.extractfile(member)
            assert stream is not None
            with stream:
                target.write_bytes(stream.read())


def compare(args):
    commit = subprocess.check_output([
        'git', 'rev-parse', '--verify', '--end-of-options', args.baseline_ref + '^{commit}',
    ], cwd=REPO, text=True).strip()

    def run(root):
        output = subprocess.check_output([
            sys.executable, str(Path(__file__).resolve()), '--worker', '--source-root', str(root),
            '--samples', str(args.samples), '--iterations', str(args.iterations), '--warmup', str(args.warmup),
        ], cwd=REPO, text=True)
        return json.loads(output)

    with tempfile.TemporaryDirectory(prefix='charts-declarations-benchmark-') as directory:
        root = Path(directory).resolve()
        baseline_package(commit, root)
        before = run(root)
        after = run(REPO)
    return {
        'baselineCommit': commit,
        'workingTreeHead': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'python': platform.python_version(), 'platform': platform.platform(),
        'samples': args.samples, 'iterationsPerSample': args.iterations,
        'warmupCallsPerCase': args.warmup,
        'scope': 'Separate source packages and subprocesses; warm per-call elapsed time includes detached return construction. Excludes subprocess startup, HTTP, model generation, browser and network. OS file cache is not cleared. First-call times are diagnostic only; earlier cases may have imported shared dependencies.',
        'before': before, 'after': after,
        'speedups': {name: before['results'][name]['medianMsPerCall'] / result['medianMsPerCall']
                     for name, result in after['results'].items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref')
    parser.add_argument('--samples', type=int, default=7)
    parser.add_argument('--iterations', type=int, default=100)
    parser.add_argument('--warmup', type=int, default=1)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--source-root', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.samples, args.iterations, args.warmup) < 1:
        parser.error('samples, iterations and warmup must be positive')
    if args.worker:
        if args.source_root is None:
            parser.error('worker requires source-root')
        print(json.dumps(worker(args.source_root, args.samples, args.iterations, args.warmup), ensure_ascii=False))
        return
    if not args.baseline_ref or args.output is None:
        parser.error('baseline-ref and output are required')
    report = compare(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
