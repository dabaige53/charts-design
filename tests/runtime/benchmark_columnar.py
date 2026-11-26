#!/usr/bin/env python3
"""Synthetic data-export benchmark; no production data or shared source writes.

Run with the project's Python:
  .venv/bin/python tests/runtime/benchmark_columnar.py --output /tmp/columnar.json
Application Parquet caches are cleared before each miss; OS caches are not cleared.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time


def command(arguments, **kwargs):
    return subprocess.run(arguments, check=True, text=True, capture_output=True, **kwargs).stdout.strip()


def summarize(paths):
    return {'fileCount': len(paths), 'bytes': sum(path.stat().st_size for path in paths)}


def worker_sizes(repo, bun, work, base_ref):
    def measure(path):
        data = path.read_bytes()
        return {'minifiedBytes': len(data), 'gzipBytes': len(gzip.compress(data, mtime=0)), 'sha256': hashlib.sha256(data).hexdigest()}

    current = repo / 'dashboard_runtime/web/dist/static-worker.js'
    new = measure(current)
    if not base_ref:
        return {'current': new, 'method': 'Existing packaged worker; use --worker-base-ref for an explicit historical comparison.'}
    old_web = work / 'old-source'
    names = command(['git', 'ls-tree', '-r', '--name-only', base_ref, '--',
                     'dashboard_runtime/web', 'runtime-ui/src'], cwd=repo).splitlines()
    for name in names:
        if name.endswith(('.mjs', '.ts', '.tsx')):
            destination = old_web / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(subprocess.run(['git', 'show', f'{base_ref}:{name}'], cwd=repo, check=True, capture_output=True).stdout)
    driver = work / 'build-old-worker.mjs'
    driver.write_text(
        'import { build } from ' + json.dumps(str(repo / 'runtime-ui/node_modules/esbuild/lib/main.js')) + ';\n'
        'await build({entryPoints:[process.argv[2]],outfile:process.argv[3],bundle:true,format:"esm",target:"es2022",minify:true,'
        'nodePaths:[' + json.dumps(str(repo / 'runtime-ui/node_modules')) + ']});\n', encoding='utf-8',
    )
    previous = work / 'old-worker.js'
    command([str(bun), str(driver), str(old_web / 'dashboard_runtime/web/static-worker.mjs'), str(previous)], cwd=repo)
    old = measure(previous)
    return {'base': old, 'current': new,
            'deltaMinifiedBytes': new['minifiedBytes'] - old['minifiedBytes'],
            'deltaGzipBytes': new['gzipBytes'] - old['gzipBytes'],
            'baseRef': base_ref,
            'method': 'Historical source rebuilt with the current installed dependencies and esbuild options; current worker is the packaged UI build.'}


# @wu-test type=integration | scope=列式导出性能测量 | protects=只依赖回执行数而掩盖解码丢行或数值及空值语义变化
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--bun', type=Path, default=shutil.which('bun'))
    parser.add_argument('--native', type=Path, help='Override the configured/discovered native exporter')
    parser.add_argument('--rustc', type=Path, default=shutil.which('rustc'), help='Optional Rust version reporting')
    parser.add_argument('--temp-root', type=Path, default=Path(tempfile.gettempdir()))
    parser.add_argument('--worker-base-ref', help='Optional Git revision for rebuilding the previous worker')
    parser.add_argument('--rows', type=int, default=1_000_000)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--parquet-only', action='store_true')
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--label', default='current-native-encoding')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.rows < 1 or args.runs < 1:
        parser.error('rows and runs must be positive')
    if not args.bun:
        parser.error('Bun is required; use --bun or put bun on PATH')
    repo = args.repo.resolve()
    sys.path.insert(0, str(repo))
    from dashboard_runtime.local_data import LocalData
    from dashboard_runtime.deployment import _write_shards
    from dashboard_runtime.columnar import native_binary, write_parquet
    found = args.native or native_binary()
    if not found:
        parser.error('Native exporter is required; install it or pass --native')
    binary = Path(found).resolve()
    fields = {
        'id': {'type': 'number'}, 'month': {'type': 'date'}, 'region': {'type': 'string'},
        'revenue': {'type': 'number'}, 'passengers': {'type': 'number'}, 'active': {'type': 'boolean'},
    }
    expected = {'rows': 0, 'revenue': 0, 'passengers': 0, 'revenueNull': 0, 'revenueMissing': 0,
                'passengersNull': 0, 'passengersMissing': 0, 'activeNull': 0, 'activeMissing': 0}
    regions = ['华东', '华北', '华南', '西南', '东北', '西北', '华中']

    def source_rows():
        for i in range(args.rows):
            row = {'id': i, 'month': f'2026-{i % 12 + 1:02d}-01', 'region': regions[i % len(regions)],
                   'revenue': ((i * 37) % 1_000_003) / 4, 'passengers': i % 300 + 1, 'active': i % 3 != 0}
            for key, missing_mod, null_mod in [('revenue', 113, 89), ('passengers', 101, 97), ('active', 173, 167)]:
                if i % missing_mod == 0:
                    del row[key]
                    expected[key + 'Missing'] += 1
                elif i % null_mod == 0:
                    row[key] = None
                    expected[key + 'Null'] += 1
            expected['rows'] += 1
            for key in ('revenue', 'passengers'):
                expected[key] += row.get(key) or 0
            yield row

    with tempfile.TemporaryDirectory(prefix='charts-columnar-benchmark-', dir=args.temp_root) as temporary:
        work = Path(temporary)
        data = LocalData(work / 'source')
        started = time.perf_counter()
        ref = data.import_rows(source_rows(), fields)
        if args.baseline:
            baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
            assert ref['version'] == baseline['dataset']['version'], 'Comparison dataset changed'
        import_seconds = time.perf_counter() - started
        print(json.dumps({'stage': 'import-complete', 'rows': args.rows, 'seconds': import_seconds}), flush=True)
        samples = {'parquet_cache_miss': [], 'parquet_cache_hit': []} if args.parquet_only else {'gzip_json': [], 'parquet_cache_miss': [], 'parquet_cache_hit': []}
        sample_sizes = {}
        cache = work / 'cache'
        verification_paths = {}
        for run in range(args.runs):
            for kind in samples:
                site = work / f'{kind}-{run}'
                (site / 'data').mkdir(parents=True)
                if kind == 'parquet_cache_miss' and cache.exists():
                    shutil.rmtree(cache)
                started = time.perf_counter()
                if kind == 'gzip_json':
                    files, count = _write_shards(site, 'bench', data.iter_rows(ref))
                else:
                    files, count, info = write_parquet(site, data, ref, cache, str(binary))
                    assert info['cacheHit'] == (kind == 'parquet_cache_hit'), info
                elapsed = time.perf_counter() - started
                assert count == args.rows
                paths = [site / name for name in files]
                size = summarize(paths)
                if kind in sample_sizes:
                    assert sample_sizes[kind] == size
                sample_sizes[kind] = size
                samples[kind].append(elapsed)
                if run == 0:
                    verification_paths[kind] = paths
                print(json.dumps({'stage': kind, 'run': run + 1, 'seconds': elapsed, **size}), flush=True)

        # The real browser decoder reads one complete shard at a time. No receipt-only validation.
        paths_file = work / 'parquet-files.json'
        paths_file.write_text(json.dumps([str(path) for path in verification_paths['parquet_cache_miss']]), encoding='utf-8')
        decoder = work / 'verify-parquet.ts'
        decoder.write_text('import { decodeParquet } from ' + json.dumps(str(repo / 'runtime-ui/src/static-data.ts')) + ';\n' + '''
const files = await Bun.file(process.argv[2]).json();
const summary = {rows:0,revenue:0,passengers:0,revenueNull:0,revenueMissing:0,passengersNull:0,passengersMissing:0,activeNull:0,activeMissing:0};
let nextId = 0;
for (const path of files) {
  const rows = await decodeParquet(await Bun.file(path).arrayBuffer());
  for (const row of rows) {
    if (row.id !== nextId++) throw Error('row order or count changed');
    summary.rows++;
    for (const key of ['revenue','passengers','active']) {
      if (!Object.hasOwn(row,key)) summary[key+'Missing']++;
      else if (row[key] === null) summary[key+'Null']++;
    }
    for (const key of ['revenue','passengers']) if (typeof row[key] === 'number') summary[key] += row[key];
  }
}
console.log(JSON.stringify(summary));
''', encoding='utf-8')
        started = time.perf_counter()
        actual = json.loads(command([str(args.bun), str(decoder), str(paths_file)], cwd=repo))
        decoder_seconds = time.perf_counter() - started
        assert actual == expected, {'actual': actual, 'expected': expected}
        legacy = None
        if 'gzip_json' in verification_paths:
            legacy = {'rows': 0, 'revenue': 0, 'passengers': 0}
            for path in verification_paths['gzip_json']:
                for row in json.loads(gzip.decompress(path.read_bytes())):
                    legacy['rows'] += 1
                    for key in ('revenue', 'passengers'):
                        legacy[key] += row.get(key) or 0
            assert legacy == {key: expected[key] for key in legacy}

        cpu_lines = Path('/proc/cpuinfo').read_text().splitlines() if Path('/proc/cpuinfo').is_file() else []
        memory_lines = Path('/proc/meminfo').read_text().splitlines() if Path('/proc/meminfo').is_file() else []
        cpu = next((line.split(':', 1)[1].strip() for line in cpu_lines if line.startswith('model name')), platform.processor() or 'unknown')
        memory = next((line.split(':', 1)[1].strip() for line in memory_lines if line.startswith('MemTotal:')), 'unreported')
        measurements = {kind: {'seconds': values, 'medianSeconds': statistics.median(values), **sample_sizes[kind]}
                        for kind, values in samples.items()}
        report = {
            'schema': 1,
            'label': args.label,
            'comparisonBaseline': str(args.baseline) if args.baseline else None,
            'recordedAtUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'baseCommit': command(['git', 'rev-parse', 'HEAD'], cwd=repo),
            'environment': {'platform': platform.platform(), 'cpu': cpu, 'logicalCpuCount': os.cpu_count(), 'hostMemory': memory,
                            'python': sys.version, 'bun': command([str(args.bun), '--version']),
                            'rust': command([str(args.rustc), '--version'], cwd=repo / 'runtime-core') if args.rustc else None},
            'dataset': {'rows': args.rows, 'fields': fields, 'version': ref['version'], 'sqliteBytes': data.path.stat().st_size,
                        'construction': 'id=i, month=i%12, 7 regions, revenue=((i*37)%1000003)/4, passengers=i%300+1, active=i%3!=0; deterministic sparse missing/nulls; no random seed needed',
                        'importSecondsExcluded': import_seconds},
            'measurements': measurements,
            'validation': {'decoder': 'runtime-ui/src/static-data.ts decodeParquet via Bun, one shard at a time',
                           'parquet': actual, 'gzipJson': legacy, 'expected': expected,
                           'decoderWallSecondsNotAnExportMeasurement': decoder_seconds, 'passed': True},
            'artifacts': {'releaseBinaryBytes': binary.stat().st_size, 'releaseBinarySha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                          'worker': worker_sizes(repo, args.bun, work, args.worker_base_ref)},
            'scope': ['Only dataset file generation/copying is timed; import, UI copying, ZIP creation, full export_site orchestration, and verification are excluded.',
                      'Gzip-JSON is the existing _write_shards + iter_rows path with gzip default compression. Parquet miss uses write_parquet + native release process + verified file copies.',
                      'Parquet hit retains immutable encoded cache, checks receipts and performs SHA256-verified copies. It does not skip copying data into the independent site.',
                      'Each miss removes the application cache before timing; OS filesystem caches are not cleared. These are not physical-disk cold-start numbers.',
                      'One synthetic, narrow-table workload on this host; no browser, network, production concurrency, or production latency claims.'],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'stage': 'complete', 'output': str(args.output), 'measurements': measurements, 'artifacts': report['artifacts']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
