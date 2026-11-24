"""Wire limits and encoding for resumable dataset uploads."""
import base64
import gzip
import json
import zlib

from .model import MAX_BYTES, DashboardError, json_bytes, require

TRANSFER_ROWS = 250
BULK_ROWS = 5_000
BULK_COMPRESSED = 8 * 1024 * 1024
BULK_DECODED = MAX_BYTES
BULK_ENCODED = 4 * ((BULK_COMPRESSED + 2) // 3)
BULK_ENCODING = 'gzip-json-v1'


def encode_bulk(raw):
    if len(raw) > BULK_DECODED:
        raise ValueError('Bulk chunk exceeds 16 MiB decoded; use --legacy for a new upload')
    compressed = gzip.compress(raw, compresslevel=3, mtime=0)
    if len(compressed) > BULK_COMPRESSED:
        raise ValueError('Bulk chunk exceeds 8 MiB compressed; use --legacy for a new upload')
    return base64.b64encode(compressed).decode('ascii')


def bulk_binary(payload):
    require(isinstance(payload, str) and len(payload) <= BULK_ENCODED,
            'Bulk chunk exceeds encoded size limit')
    try:
        compressed = base64.b64decode(payload, validate=True)
    except ValueError as error:
        raise DashboardError('INVALID_DOCUMENT', 'Invalid bulk chunk Base64') from error
    require(len(compressed) <= BULK_COMPRESSED, 'Bulk chunk exceeds 8 MiB compressed')
    return compressed


def bulk_raw(compressed):
    require(len(compressed) <= BULK_COMPRESSED, 'Bulk chunk exceeds 8 MiB compressed')
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        raw = decoder.decompress(compressed, BULK_DECODED + 1)
    except zlib.error as error:
        raise DashboardError('INVALID_DOCUMENT', 'Invalid bulk chunk gzip') from error
    require(len(raw) <= BULK_DECODED, 'Bulk chunk exceeds 16 MiB decoded')
    require(decoder.eof and not decoder.unused_data, 'Invalid bulk chunk gzip')
    return raw


def bulk_rows(raw, expected):
    try:
        rows = json.loads(raw)
        canonical = json_bytes(rows)
    except (ValueError, RecursionError) as error:
        raise DashboardError('INVALID_DOCUMENT', 'Invalid bulk chunk JSON') from error
    require(isinstance(rows, list) and len(rows) == expected
            and all(isinstance(row, dict) for row in rows), 'Invalid chunk rows')
    require(canonical == raw, 'Bulk chunk must use canonical JSON')
    return rows
