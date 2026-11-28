"""Bounded dataset input and inspection, separate from business metric authoring."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import math
import re

from .doctor import data_version
from .model import DashboardError, MAX_BYTES, MAX_ROWS, identifier, inferred_fields, json_bytes, require


INFER_NUMBER = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?')
EXPLICIT_NUMBER = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?')
MAX_PREVIEW_OFFSET = 2**53 - 1


def dataset_source_id(prefix, dataset_id):
    """Keep existing source IDs while supporting the full dataset-ID length."""
    identifier(dataset_id, 'dataset id')
    value = f'{prefix}-{dataset_id}'
    if len(value) > 80:
        value = f'{prefix}-{hashlib.sha256(dataset_id.encode()).hexdigest()}'
    return identifier(value, 'source id')


def _fields(value):
    require(isinstance(value, dict) and bool(value), 'fields must be a non-empty field metadata object', 'INVALID_ARGUMENT')
    for key, info in value.items():
        require(isinstance(key, str) and 0 < len(key) < 200, 'Field names must contain 1-199 characters', 'INVALID_ARGUMENT')
        require(isinstance(info, dict) and info.get('type') in ('string', 'number', 'date', 'boolean'),
                f'{key}: declare type as string, number, date or boolean', 'INVALID_ARGUMENT')
        require('label' not in info or isinstance(info['label'], str), f'{key}: label must be a string', 'INVALID_ARGUMENT')
    return copy.deepcopy(value)


def _csv_value(value, kind, row_number, field):
    if value == '':
        return None
    if kind in ('string', 'date'):
        # Dates keep the runtime's existing string contract (including month
        # grains). Explicit types never invent a calendar format or business rule.
        return value
    if kind == 'boolean':
        normalized = value.strip().lower()
        require(normalized in ('true', 'false', '1', '0'),
                f'CSV row {row_number}, field {field}: expected true, false, 1 or 0', 'INVALID_ARGUMENT')
        return normalized in ('true', '1')
    if kind == 'number':
        normalized = value.strip()
        require(EXPLICIT_NUMBER.fullmatch(normalized) is not None,
                f'CSV row {row_number}, field {field}: expected a number', 'INVALID_ARGUMENT')
        value = normalized
    # Preserve inference for existing valid CSV, including leading-zero IDs.
    if kind == 'number' or INFER_NUMBER.fullmatch(value):
        try:
            return float(value) if any(char in value for char in '.eE') else int(value)
        except ValueError as error:
            raise DashboardError('INVALID_ARGUMENT', f'CSV row {row_number}, field {field}: number is out of range; use a string field for identifiers') from error
    return value


def _csv_rows(text, fields):
    require(isinstance(text, str), 'csvText must contain CSV text, not a file reference', 'INVALID_ARGUMENT')
    require(len(text.encode('utf-8')) <= MAX_BYTES, 'CSV exceeds 16 MiB', 'PAYLOAD_TOO_LARGE')
    reader = csv.reader(io.StringIO(text.removeprefix('\ufeff'), newline=''), strict=True)
    try:
        header = next(reader, None)
        require(header and all(name.strip() for name in header), 'CSV needs non-empty column headers', 'INVALID_ARGUMENT')
        require(len(header) == len(set(header)), 'CSV column headers must be unique; duplicate columns would lose data', 'INVALID_ARGUMENT')
        require(all(len(name) < 200 for name in header), 'CSV column headers must contain 1-199 characters', 'INVALID_ARGUMENT')
        if fields is not None:
            require(set(header) <= set(fields), 'CSV contains undeclared columns; include every header in fields', 'INVALID_ARGUMENT')
        rows = []
        for values in reader:
            if not values:  # Match DictReader's handling of empty physical lines.
                continue
            require(len(values) == len(header),
                    f'CSV row ending at line {reader.line_num}: expected {len(header)} cells, got {len(values)}', 'INVALID_ARGUMENT')
            require(len(rows) < MAX_ROWS, f'Dataset exceeds {MAX_ROWS} rows', 'PAYLOAD_TOO_LARGE')
            rows.append({key: _csv_value(value, fields[key]['type'] if fields else None, reader.line_num, key)
                         for key, value in zip(header, values)})
        return rows
    except csv.Error as error:
        raise DashboardError('INVALID_ARGUMENT', f'Invalid CSV at line {reader.line_num}: {error}') from error


def parse_dataset_input(args):
    """Return typed rows and fields without creating metrics or mutating inputs."""
    require(('rows' in args) != ('csvText' in args), 'Supply exactly one of rows or csvText', 'INVALID_ARGUMENT')
    fields = _fields(args['fields']) if 'fields' in args else None
    rows = _csv_rows(args['csvText'], fields) if 'csvText' in args else args['rows']
    require(isinstance(rows, list), 'rows must be an array of field objects', 'INVALID_ARGUMENT')
    require(len(rows) <= MAX_ROWS, f'Dataset exceeds {MAX_ROWS} rows', 'PAYLOAD_TOO_LARGE')
    require(bool(rows) or fields is not None, 'Empty rows need explicit fields to define the dataset schema', 'INVALID_ARGUMENT')
    require(all(isinstance(row, dict) for row in rows), 'Each row must be a field object', 'INVALID_ARGUMENT')
    if fields is None:
        fields = _fields(inferred_fields(rows))
    for index, row in enumerate(rows, start=1):
        require(set(row) <= set(fields), f'Row {index}: contains undeclared fields', 'INVALID_ARGUMENT')
        for key, value in row.items():
            kind = fields[key]['type']
            valid = (value is None
                     or kind in ('string', 'date') and isinstance(value, str)
                     or kind == 'boolean' and type(value) is bool
                     or kind == 'number' and (type(value) is float and math.isfinite(value)
                                              or type(value) is int and -(2**63) <= value < 2**63))
            require(valid, f'Row {index}, field {key}: value does not match {kind}; use explicit fields for mixed or ambiguous input', 'INVALID_ARGUMENT')
    json_bytes({'fields': fields, 'rows': rows})
    return [dict(row) for row in rows], fields


def dataset_preview(service, args):
    """Read an ordered page of one complete dataset without component filters."""
    board = identifier(args.get('dashboardId'), 'dashboard id')
    dataset_id = identifier(args.get('datasetId'), 'dataset id')
    offset, limit = args.get('offset', 0), args.get('limit', 20)
    require(type(offset) is int and 0 <= offset <= MAX_PREVIEW_OFFSET,
            f'offset must be an integer from 0 to {MAX_PREVIEW_OFFSET}', 'INVALID_ARGUMENT')
    require(type(limit) is int and 1 <= limit <= 100, 'limit must be an integer from 1 to 100', 'INVALID_ARGUMENT')
    doc = service._reading_document(board, args)
    meta = doc['manifest']['datasets'].get(dataset_id)
    require(meta is not None, f'Dataset not found: {dataset_id}', 'NOT_FOUND')
    is_live = meta.get('mode') == 'live'
    ref = doc['snapshot'].get('datasetRefs', {}).get(dataset_id)
    if is_live:
        with service.views.live_request(doc) as live:
            result = live.data.rows(live.reference(dataset_id), offset=offset, limit=limit)
    elif ref is not None:
        result = service.store.data.rows(ref, offset=offset, limit=limit)
    else:
        # Older embedded snapshots need no hydration, persistence or component.
        rows = doc['snapshot'].get('datasets', {}).get(dataset_id)
        require(isinstance(rows, list), 'Dataset rows are unavailable', 'DATA_INCOMPLETE')
        result = {'rows': copy.deepcopy(rows[offset:offset + limit]), 'totalRows': len(rows)}
    has_more = offset + len(result['rows']) < result['totalRows']
    return {
        **result, 'dashboardId': board, 'datasetId': dataset_id,
        'revision': doc['revision'], 'dataVersion': data_version(doc),
        'fields': copy.deepcopy(meta['fields']), 'sourceId': meta['sourceId'],
        'mode': 'live' if is_live else 'snapshot', 'transient': is_live,
        'scope': 'unfiltered-dataset', 'filtersApplied': False,
        'offset': offset, 'limit': limit, 'hasMore': has_more,
        'nextOffset': offset + len(result['rows']) if has_more else None,
        **({'datasetVersion': ref['version']} if ref is not None and not is_live else {}),
    }
