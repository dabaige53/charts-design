"""Optional Rust data exporter; immutable Parquet caches never own project data."""
from __future__ import annotations

import json
import hashlib
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from .assets import DIST
from .file_lock import exclusive_file_lock
from .model import DashboardError, require

FORMAT = 'parquet-v1'


def native_binary():
    """Use only operator configuration or an installed binary, never request paths."""
    configured = os.environ.get('CHARTS_CORE_BIN')
    if configured:
        path = Path(configured).expanduser()
        require(path.is_absolute() and path.is_file() and os.access(path, os.X_OK),
                'CHARTS_CORE_BIN must name an executable absolute path', 'NATIVE_UNAVAILABLE')
        return str(path)
    machine = platform.machine().lower()
    arch = {'x86_64': 'x64', 'amd64': 'x64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(machine, machine)
    root = Path(__file__).parent / 'native'
    name = 'charts-design-core.exe' if os.name == 'nt' else 'charts-design-core'
    for packaged in (root / f'{sys.platform}-{arch}' / name, root / name):
        if packaged.is_file() and os.access(packaged, os.X_OK):
            return str(packaged)
    return shutil.which('charts-design-core')


def export_format(requested='auto'):
    require(requested in ('auto', 'parquet', 'json'), 'dataFormat must be auto, parquet or json')
    if requested == 'json':
        return 'json', None
    binary = native_binary()
    build = json.loads((DIST / 'build.json').read_text(encoding='utf-8'))
    supported = FORMAT in build.get('staticDataFormats', [])
    if requested == 'parquet':
        require(binary is not None,
                'Parquet export needs charts-design-core; install the native binary or set CHARTS_CORE_BIN.',
                'NATIVE_UNAVAILABLE')
        require(supported, 'The UI bundle needs Parquet support; prepare matching UI resources.', 'UI_UNAVAILABLE')
    return ('parquet', binary) if binary and supported else ('json', None)


def _package_files(receipt):
    yield from receipt['files']
    for files in receipt.get('options', {}).values():
        yield from files


def _receipt(directory, ref, partition_field=None, include_options=False):
    """A cache is complete only after its receipt was atomically published."""
    try:
        receipt = json.loads((directory / 'receipt.json').read_text(encoding='utf-8'))
        if (receipt['format'] != FORMAT or receipt['version'] != ref['version']
                or receipt['rowCount'] != ref['rowCount']
                or receipt['fieldOrder'] != ref.get('fieldOrder', list(ref['fields']))
                or sum(item['rowCount'] for item in receipt['files']) != ref['rowCount']):
            return None
        main_names = [item['path'] for item in receipt['files']]
        if main_names != [f"{ref['version']}-{index}.parquet" for index in range(len(main_names))]:
            return None
        options = receipt.get('options', {})
        if not isinstance(options, dict) or set(options) != (set(ref['fields']) if include_options else set()):
            return None
        for index, field in enumerate(ref.get('fieldOrder', list(ref['fields']))):
            option_files = options.get(field, [])
            if ([item['path'] for item in option_files]
                    != [f"{ref['version']}-options-{index}-{part}.parquet" for part in range(len(option_files))]
                    or sum(item['rowCount'] for item in option_files) > ref['rowCount']):
                return None
        if not isinstance(receipt.get('missingColumn'), str) or receipt['missingColumn'] in ref['fields']:
            return None
        partition = receipt.get('partitionIndex')
        ordinal = receipt.get('ordinalColumn')
        if partition_field:
            if (not isinstance(ordinal, str) or ordinal in ref['fields'] or ordinal == receipt['missingColumn']
                    or not isinstance(partition, dict) or partition.get('field') != partition_field):
                return None
            entries = partition['entries']
            if (any(entry['value'] is not None and not isinstance(entry['value'], str) for entry in entries)
                    or len({entry['value'] for entry in entries}) != len(entries)
                    or sorted(name for entry in entries for name in entry['files']) != sorted(main_names)):
                return None
        elif partition is not None or ordinal is not None:
            return None
        for item in _package_files(receipt):
            if (type(item['rowCount']) is not int or item['rowCount'] < 0
                    or type(item['bytes']) is not int or not 0 < item['bytes'] <= 24 * 1024 * 1024
                    or (directory / item['path']).stat().st_size != item['bytes']
                    or not isinstance(item['sha256'], str) or len(item['sha256']) != 64
                    or any(char not in '0123456789abcdef' for char in item['sha256'])):
                return None
        return receipt
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _native_json(arguments):
    try:
        process = subprocess.run(arguments, capture_output=True, text=True, encoding='utf-8', check=False)
    except (OSError, UnicodeError) as error:
        raise DashboardError('PARQUET_EXPORT_FAILED', 'Native program could not be executed') from error
    if process.returncode:
        raise DashboardError('PARQUET_EXPORT_FAILED', process.stderr.strip() or 'Native program failed')
    try:
        return json.loads(process.stdout)
    except ValueError as error:
        raise DashboardError('PARQUET_EXPORT_FAILED', 'Invalid native receipt') from error


def _encode_cache(data, ref, cache_root, directory, binary, partition_field=None, include_options=False):
    source, metadata = data.sqlite_source(ref)
    require(metadata == ref, 'Immutable dataset metadata changed', 'DATA_CONFLICT')
    with TemporaryDirectory(prefix='parquet-', dir=cache_root) as temporary:
        staged = Path(temporary) / 'data'
        arguments = [binary, 'export-parquet', '--database', str(source), '--version', ref['version'],
                     '--output', str(staged)]
        if partition_field is not None:
            arguments.extend(['--partition-field', partition_field])
        if include_options:
            arguments.append('--include-options')
        result = _native_json(arguments)
        (staged / 'receipt.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        receipt = _receipt(staged, ref, partition_field, include_options)
        if receipt is None:
            raise DashboardError('PARQUET_EXPORT_FAILED', 'Incomplete native export')
        if directory.exists():
            shutil.rmtree(directory)  # Only this locked, disposable cache; never source data.
        staged.rename(directory)
        return receipt


def _copy_verified(source, destination, digest):
    checksum = hashlib.sha256()
    with source.open('rb') as reader, destination.open('wb') as writer:
        while block := reader.read(1024 * 1024):
            writer.write(block)
            checksum.update(block)
    if checksum.hexdigest() != digest:
        destination.unlink()
        return False
    return True


def copy_package(target_dir, data, ref, cache_root, binary, *, partition_field=None, include_options=False) -> dict:
    """Copy a verified immutable representation into a caller-owned directory."""
    version = ref['version']
    require(isinstance(version, str) and len(version) == 64
            and all(char in '0123456789abcdef' for char in version), 'Invalid data version')
    require(partition_field is None or ref['fields'].get(partition_field, {}).get('type') in ('string', 'date'),
            'Partition field must be a declared string or date')
    target_dir = Path(target_dir)
    target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    cache_root = Path(cache_root) / FORMAT
    cache_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Physical layouts share logical data identity, but must never share cache entries.
    layout = json.dumps([partition_field, include_options], ensure_ascii=False).encode('utf-8')
    key = version + ('-' + hashlib.sha256(layout).hexdigest()[:24] if partition_field or include_options else '')
    directory = cache_root / key
    # Repair and copying share the same process lock, so a repair cannot remove
    # a cache while another MCP process is delivering it.
    with exclusive_file_lock(cache_root / (key + '.lock')):
        receipt = _receipt(directory, ref, partition_field, include_options)
        reused = receipt is not None
        for _ in range(2):
            if receipt is None:
                receipt = _encode_cache(data, ref, cache_root, directory, binary, partition_field, include_options)
            for item in _package_files(receipt):
                if not _copy_verified(directory / item['path'], target_dir / item['path'], item['sha256']):
                    receipt, reused = None, False
                    break
            else:
                return {**receipt, 'cacheHit': reused}
        raise DashboardError('PARQUET_EXPORT_FAILED', 'Native export checksum mismatch')


def write_parquet(site, data, ref, cache_root, binary):
    """Generate once per immutable dataset, then copy into a self-contained site."""
    receipt = copy_package(site / 'data', data, ref, cache_root, binary)
    return ['data/' + item['path'] for item in receipt['files']], receipt['rowCount'], {
        'format': FORMAT, 'cacheHit': receipt['cacheHit'], 'bytes': sum(item['bytes'] for item in receipt['files'])}


def inspect_parquet(path, binary):
    """Decode every record batch, used before an explicit cloud migration commits."""
    receipt = _native_json([binary, 'inspect-parquet', '--input', str(path)])
    require(isinstance(receipt, dict) and receipt.get('format') == FORMAT
            and type(receipt.get('rowCount')) is int and receipt['rowCount'] >= 0
            and isinstance(receipt.get('fieldOrder'), list)
            and all(isinstance(field, str) for field in receipt['fieldOrder']),
            'Invalid Parquet inspection receipt', 'PARQUET_EXPORT_FAILED')
    return receipt
