"""Data-only chart authoring guidance shared by MCP and runtime documentation.

JSON Schema here describes declaration shapes, not the complete document validator.
Cross-reference, semantic, layout and legacy nested-data checks remain authoritative
in model.validate and the installed original component validators. This module must
not import service or contract: both transports and contract discovery use it.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

from .model import AGGREGATES, ID, MAX_COMPONENTS, MAX_ROWS, TYPES, require

REPO = Path(__file__).resolve().parent.parent
LEGACY_ROOT = Path('skills/executive-charts')
LEGACY_SCHEMA_SOURCE = str(LEGACY_ROOT / 'scripts/core/component_schemas.py')
LEGACY_CATALOG_SOURCE = str(LEGACY_ROOT / 'references/chart_catalog.json')


def _object(properties, required=()):
    # Runtime declarations permit extra presentation metadata; do not invent a
    # stricter additionalProperties=False contract than the actual validator.
    return {'type': 'object', 'properties': properties, 'required': list(required)}


def _identifier():
    return {'type': 'string', 'pattern': ID.pattern}


def _common():
    string = {'type': 'string'}
    field_name = {'type': 'string', 'minLength': 1, 'maxLength': 199}
    field_info = _object({'type': {'enum': ['string', 'number', 'date', 'boolean']},
                          'label': string}, ['type'])
    source = _object({'kind': {'enum': ['file', 'query', 'fixture', 'declared']},
                      'name': string, 'query': _object({
                          'sql': {'type': 'string', 'minLength': 1},
                          'executedAt': string, 'engine': string, 'id': string,
                      }, ['sql', 'executedAt', 'engine', 'id'])}, ['kind'])
    source['allOf'] = [{'if': {'properties': {'kind': {'const': 'query'}}},
                        'then': {'required': ['query']}}]
    metric = _object({
        'datasetId': _identifier(), 'field': field_name,
        'aggregation': {'enum': list(AGGREGATES)},
        'label': {'type': 'string', 'minLength': 1},
        'unit': string, 'definition': {'type': 'string', 'minLength': 1},
        'format': {'enum': ['number', 'percent', 'currency'], 'default': 'number'},
        'scale': string, 'semantic': string,
        'numerator': field_name, 'denominator': field_name,
        'status': {'enum': ['unverified', 'reviewed'], 'default': 'unverified'},
    }, ['datasetId', 'aggregation', 'label', 'unit', 'definition'])
    metric['allOf'] = [
        {'if': {'properties': {'aggregation': {'const': 'ratio'}}},
         'then': {'required': ['numerator', 'denominator']}},
        {'if': {'properties': {'aggregation': {'enum': ['sum', 'avg', 'min', 'max']}}},
         'then': {'required': ['field']}},
        {'if': {'required': ['format'], 'properties': {'format': {'const': 'percent'}}},
         'then': {'required': ['scale'], 'properties': {'scale': {'const': 'fraction'}}}},
    ]
    component = _object({
        'kind': {'enum': ['chart', 'kpi', 'table', 'text', 'legacy']},
        'title': {'type': 'string', 'maxLength': 240},
        'datasetId': _identifier(), 'x': field_name, 'series': field_name,
        'measures': {'type': 'array', 'items': _identifier(), 'minItems': 1, 'uniqueItems': True},
        'chartType': {'enum': list(TYPES)},
        'presentation': {'type': 'object'}, 'text': string,
        'family': {'enum': ['chart', 'kpi', 'table']},
        'config': {'type': 'object'}, 'binding': {'type': 'object'},
        'sourceId': _identifier(),
    }, ['kind', 'title'])
    return {
        'identifierSchema': _identifier(), 'sourceSchema': source,
        'datasetMetaSchema': _object({
            'sourceId': _identifier(),
            'fields': {'type': 'object', 'minProperties': 1,
                       'propertyNames': field_name, 'additionalProperties': field_info},
        }, ['sourceId', 'fields']),
        'rowsSchema': {'type': 'array', 'items': {'type': 'object'}},
        'metricSchema': metric, 'componentSchema': component,
        'limits': {'maxRowsAcrossDatasets': MAX_ROWS, 'maxComponents': MAX_COMPONENTS,
                   'maxOperationsPerPatch': 200, 'maxDocumentBytes': 16 * 1024 * 1024},
        'rules': [
            'Rows use declared field names and types; null and missing cell values are allowed. JSON numbers must be finite.',
            'Dataset metadata is in manifest.datasets; rows are in snapshot.datasets. put_dataset supplies both meta and rows.',
            'Every dataset references an existing source. Every native measure references a metric in that same dataset.',
            'sum, avg, min and max require a numeric field; count counts rows and needs no field.',
            'ratio requires numeric numerator and denominator fields and computes sum(numerator)/sum(denominator), never avg(ratios).',
            'Percent metrics require format=percent and scale=fraction; 0.98 displays as 98%.',
            'Declared provenance is supplied evidence, not proof of query execution or certification.',
        ],
    }


def _native_example(chart_type):
    numeric_x = chart_type == 'scatter'
    x = 'quantity' if numeric_x else 'category'
    rows = [{x: 1 if numeric_x else 'A', 'region': 'East', 'value': 12},
            {x: 2 if numeric_x else 'B', 'region': 'West', 'value': 8}]
    if chart_type in ('bar', 'line', 'area', 'heatmap'):
        rows = [{x: 'A', 'region': 'East', 'value': 12},
                {x: 'B', 'region': 'East', 'value': 8},
                {x: 'A', 'region': 'West', 'value': 10},
                {x: 'B', 'region': 'West', 'value': 9}]
    metric = {'datasetId': 'example-data', 'field': 'value', 'aggregation': 'sum',
              'label': 'Example value', 'unit': 'units',
              'definition': 'Sum of explicit synthetic example values; replace with reviewed business data.',
              'status': 'unverified'}
    if chart_type == 'waterfall':
        metric['semantic'] = 'delta'
        metric['definition'] = 'Additive synthetic changes in encounter order, starting from zero.'
        rows[1]['value'] = -3
    component = {'kind': 'chart', 'title': f'Example {chart_type}',
                 'datasetId': 'example-data', 'x': x,
                 'measures': ['example-value'], 'chartType': chart_type}
    if chart_type in ('bar', 'line', 'area', 'heatmap'):
        component['series'] = 'region'
    return {
        'status': 'fixture',
        'usage': 'Apply these operations to a new empty dashboard, replacing the synthetic data and identifiers for real work. Read its current revision first.',
        'componentId': f'example-{chart_type}',
        'operations': [
            {'op': 'put_source', 'id': 'example-source', 'value': {
                'kind': 'fixture', 'name': 'Explicit synthetic declaration example'}},
            {'op': 'put_dataset', 'id': 'example-data', 'meta': {
                'sourceId': 'example-source', 'fields': {
                    x: {'type': 'number' if numeric_x else 'string'},
                    'region': {'type': 'string'}, 'value': {'type': 'number'}}}, 'rows': rows},
            {'op': 'put_metric', 'id': 'example-value', 'value': metric},
            {'op': 'put_component', 'id': f'example-{chart_type}', 'value': component},
            {'op': 'set_status', 'value': 'fixture'},
        ],
    }


def _native_charts(common):
    result = {}
    for chart_type in TYPES:
        schema = copy.deepcopy(common['componentSchema'])
        schema['properties']['kind'] = {'const': 'chart'}
        schema['properties']['chartType'] = {'const': chart_type}
        schema['required'] = ['kind', 'title', 'datasetId', 'x', 'measures', 'chartType']
        one_measure = chart_type in ('pie', 'funnel', 'waterfall', 'heatmap', 'scatter')
        if one_measure:
            schema['properties']['measures']['maxItems'] = 1
        series_policy = 'required' if chart_type == 'heatmap' else (
            'forbidden' if chart_type in ('pie', 'funnel', 'waterfall') else 'optional')
        if series_policy == 'required':
            schema['required'].append('series')
        if series_policy == 'forbidden':
            schema['not'] = {'required': ['series']}
        constraints = {
            'measureCount': {'minimum': 1, **({'maximum': 1} if one_measure else {})},
            'sameUnitAndFormat': True, 'series': series_policy,
            'xFieldType': 'number' if chart_type == 'scatter' else 'declared field',
        }
        if chart_type in ('pie', 'funnel'):
            constraints.update({'metricAggregations': ['sum', 'count'],
                                'renderedValues': 'nonnegative; the renderer rejects negative values'})
        if chart_type == 'waterfall':
            constraints.update({'metricAggregations': ['sum'], 'metricSemantic': 'delta'})
        result[chart_type] = {
            'componentSchema': schema, 'constraints': constraints,
            'notes': [
                'series is a dataset field name for grouping, not an ECharts series array.',
                'x and series must reference declared dataset fields. Categories follow snapshot encounter order.',
                'Shape validation does not prove cross-reference or metric compatibility; use dashboard_validate or an atomic dashboard_patch.',
            ],
            'example': _native_example(chart_type),
        }
        if chart_type == 'heatmap':
            result[chart_type]['notes'].append('Use x and series as the two category dimensions; both axes are rendered as categories.')
    return result


def _registry():
    path = REPO / LEGACY_SCHEMA_SOURCE
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location('_charts_declaration_schemas', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_example(family, config):
    key = 'example-original-' + family
    return {'status': 'fixture', 'componentId': key, 'operations': [
        {'op': 'put_source', 'id': 'example-source', 'value': {
            'kind': 'fixture', 'name': 'Explicit synthetic original-component example'}},
        {'op': 'put_component', 'id': key, 'value': {
            'kind': 'legacy', 'family': family,
            'title': config.get('title', config.get('label', 'Example table')),
            'sourceId': 'example-source', 'config': config}},
        {'op': 'set_status', 'value': 'fixture'},
    ]}


def _legacy(common):
    module = _registry()
    catalog_path = REPO / LEGACY_CATALOG_SOURCE
    catalog = json.loads(catalog_path.read_text(encoding='utf-8')) if catalog_path.is_file() else []
    codes = list(module.CHART_CODES) if module else []
    kpis = sorted(module.KPI_TYPES) if module else []
    entries = {entry['id']: entry for entry in catalog}
    chart_codes = {}
    for code in codes:
        chart_codes[code] = {
            'family': 'chart', 'configSelector': {'code': code},
            'catalogEntry': entries.get(code),
            'schemaId': module.CHART_SCHEMA_REGISTRY[code],
            'schemaSource': LEGACY_SCHEMA_SOURCE,
            'completeJsonSchema': False,
            'registeredArrayFields': [
                {'field': name, 'items': item_type, 'minItems': 1}
                for name, item_type in module.CHART_ARRAY_FIELDS.get(code, ())],
            'equalLengthGroups': [list(group) for group in module.CHART_EQUAL_LENGTH_GROUPS.get(code, ())],
            'presentationRequirements': copy.deepcopy(module.CHART_PRESENTATION_CONTRACTS[code]),
            'tableHeaderCount': module.CHART_TABLE_HEADER_COUNTS[code],
            'validation': 'validate_chart_data(data, path, code=code, strict=True, presentation=presentation)',
        }
    chart_config = {
        'code': 'c01', 'title': 'Synthetic regional values', 'unit': 'units',
        'data': {'categories': ['East', 'West'], 'values': [12, 8]},
        'presentation': {'axisLabels': {'x': 'Region', 'y': 'Value'},
                         'seriesLabels': ['Value'], 'tooltipValueLabels': ['Value'],
                         'units': ['units'], 'tableHeaders': ['Region', 'Value']},
    }
    kpi_configs = {}
    for code in kpis:
        config = {'type': code, 'label': 'Synthetic example value', 'value': '12',
                  'unit': 'units', 'yoy': '+2%', 'mom': '+1%', 'isPositive': True,
                  'statusBadge': 'Example', 'subLabel': 'Previous', 'subVal': '10',
                  'percent': 60, 'trendLabel': 'Synthetic trend', 'rankBadge': '2 / 5',
                  'thresholdLabel': 'Example threshold', 'segLeftWidth': '60%', 'segRightWidth': '40%'}
        if code == 'mc03':
            config.update({'sparkMonths': ['Jan', 'Feb', 'Mar'], 'sparkData': [8, 10, 12]})
        if code == 'mc06':
            config.pop('value')
            config.update({'leftLabel': 'Actual', 'leftVal': '12', 'rightLabel': 'Target', 'rightVal': '20'})
        kpi_configs[code] = {
            'configSelector': {'type': code}, 'required': ['label'] + (
                ['leftVal', 'rightVal'] if code == 'mc06' else ['value']),
            'completeJsonSchema': False, 'exampleConfig': config,
        }
        if code == 'mc03':
            kpi_configs[code]['requiredOneOf'] = [['sparkData'], ['sparkline']]
        if code == 'mc06':
            kpi_configs[code]['required'] = ['label']
            kpi_configs[code]['requiredOneOf'] = [['value'], ['leftVal', 'rightVal']]
    families = {}
    for family in ('chart', 'kpi', 'table'):
        schema = copy.deepcopy(common['componentSchema'])
        schema['properties']['kind'] = {'const': 'legacy'}
        schema['properties']['family'] = {'const': family}
        schema['required'] = ['kind', 'title', 'family', 'config']
        if family == 'chart':
            config_schema = _object({'code': {'enum': codes} if codes else {'type': 'string'}, 'data': {'type': 'object', 'minProperties': 1},
                                     'presentation': {'type': 'object'}}, ['code', 'data', 'presentation'])
            example_config = chart_config
        elif family == 'kpi':
            config_schema = _object({'type': {'enum': kpis, 'default': 'mc01'} if kpis else {'type': 'string', 'default': 'mc01'},
                                     'label': {'type': 'string'}, 'value': {},
                                     'leftVal': {}, 'rightVal': {},
                                     'sparkData': {'type': 'array'}, 'sparkline': {'type': 'array'}}, ['label'])
            config_schema['anyOf'] = [
                {'required': ['value']},
                {'required': ['type', 'leftVal', 'rightVal'], 'properties': {'type': {'const': 'mc06'}}},
            ]
            config_schema['allOf'] = [
                {'if': {'required': ['type'], 'properties': {'type': {'const': 'mc03'}}},
                 'then': {'anyOf': [{'required': ['sparkData']}, {'required': ['sparkline']}]}}
            ]
            example_config = kpi_configs['mc01']['exampleConfig'] if kpis else {'type': 'mc01', 'label': 'Synthetic value', 'value': '12'}
        else:
            config_schema = _object({
                'columns': {'type': 'array', 'items': _object({'key': {'type': 'string'}, 'label': {'type': 'string'}}, ['key'])},
                'rows': {'type': 'array', 'items': {'type': 'object'}},
            }, ['columns', 'rows'])
            example_config = {'title': 'Synthetic regional detail', 'columns': [
                {'key': 'region', 'label': 'Region'}, {'key': 'value', 'label': 'Value', 'type': 'number'}],
                'rows': [{'region': 'East', 'value': 12}, {'region': 'West', 'value': 8}]}
        schema['properties']['config'] = config_schema
        families[family] = {'componentSchema': schema, 'example': _legacy_example(family, example_config)}
    return {
        'available': module is not None,
        'schemaSource': LEGACY_SCHEMA_SOURCE, 'catalogSource': LEGACY_CATALOG_SOURCE,
        'validator': 'dashboard_runtime.legacy.validate_original',
        'catalogEntries': catalog,
        'counts': {'catalogEntries': len(catalog), 'registeredChartCodes': len(codes), 'registeredKpiTypes': len(kpis)},
        'chartCodes': chart_codes, 'kpiTypes': kpi_configs, 'families': families,
        'limits': [
            'Catalog entries are discovery metadata, not a list of chart renderers: the bundled catalog has 45 entries including KPI and table entries. The bundled validator registry has 40 chart codes and 9 KPI types.',
            'Per-code requirements are extracted from the installed Python registry. They are partial guidance, not complete JSON Schemas. Nested object rules, matrix dimensions, scalar fields and specialized checks remain in the authoritative validator.',
            'registeredArrayFields does not enumerate every required data field: for example t06 requires month and quarter objects, m01 requires target, and m04 requires rate and target.',
            'presentationRequirements uses axis keys and required lengths for seriesLabels, tooltipValueLabels, units and optional labels; numeric/domain pairs name additional required fields. A series count of lines means len(data.lines); tableHeaderCount can be months+1 or stages+1.',
            'Use only registered chartCodes for family=chart, kpiTypes for family=kpi, and explicit columns/rows for family=table. Do not interpret all catalog IDs as config.code.',
            'Legacy family defaults to chart in the validator; declarations should always supply family explicitly.',
            'Legacy configs preserve original data paths and presentation. No catalog preview data is substituted for supplied business data.',
            'Without the installed original repository, legacy schema discovery is unavailable; native declarations remain usable.',
        ],
        'bindings': {
            'schemaSource': 'dashboard_runtime/bindings.py',
            'requiredForFilters': True,
            'description': 'Original components use explicit config snapshots. Cross-component filters require a reviewed binding to a dataset and metrics; not every legacy shape has a supported binding transform.',
            'exampleForC01': {'datasetId': 'example-data', 'categoryField': 'category',
                              'categoryTarget': 'categories', 'measures': {'values': 'example-value'}},
        },
    }


def declaration_contract(*, chart_type=None, legacy_code=None, summary=False):
    """Return a fresh reference, compact index, or one native/legacy declaration.

    The resource uses the complete no-argument form. Interactive tools should use
    summary=True until a type/code is chosen, so discovery stays bounded.
    """
    require(not (chart_type is not None and legacy_code is not None),
            'Choose chartType or code, not both')
    require(not (summary and (chart_type is not None or legacy_code is not None)),
            'A declaration summary cannot also select a chartType or code')
    require(chart_type is None or (isinstance(chart_type, str) and chart_type in TYPES),
            'Unknown native chart type')
    require(legacy_code is None or isinstance(legacy_code, str), 'Legacy code must be a string')
    common = _common()
    result = {
        'schemaVersion': 1,
        'documentSchemaVersion': 2,
        'authority': {
            'nativeValidator': 'dashboard_runtime/model.py:validate and compatibility',
            'nativeRenderer': 'dashboard_runtime/web/engine.mjs:optionFor',
            'legacyValidator': 'dashboard_runtime/legacy.py:validate_original',
            'scope': 'Authoring guidance and shape schemas, not a replacement for full document validation.',
        },
        'workflow': [
            {'tool': 'dashboard_create', 'purpose': 'Create an empty dashboard, or use an existing dashboard ID.'},
            {'tool': 'dashboard_get', 'purpose': 'Read canonical state and current revision before mutation.'},
            {'tool': 'dashboard_patch', 'purpose': 'Supply dashboardId, the latest expectedRevision and an operations array. Put source, dataset, metric and component in one atomic batch.'},
            {'tool': 'dashboard_validate', 'purpose': 'Validate the saved dashboard or a complete proposed document.'},
            {'tool': 'dashboard_preview', 'purpose': 'Render and inspect the result. A successful declaration check does not substitute for visual review.'},
        ],
        'common': common, 'nativeCharts': _native_charts(common), 'legacy': _legacy(common),
        'reportEmbedding': {
            'operation': 'set_report_markdown',
            'example': '## Observation\n\n```chart\n{"componentId":"example-bar","caption":"Synthetic comparison","source":"Explicit fixture data"}\n```\n',
            'rules': ['Chart fences reference existing non-text component IDs; they do not create charts.',
                      'Creating a component does not append it to report Markdown. Set view mode to report separately when desired.'],
        },
    }
    if summary:
        legacy = result['legacy']
        result = {
            'schemaVersion': result['schemaVersion'],
            'documentSchemaVersion': result['documentSchemaVersion'],
            'summary': True, 'resource': 'charts://declarations',
            'usage': 'Choose chartType for a native declaration or code for an original chart/KPI. The full resource also documents the table family.',
            'nativeCharts': list(result['nativeCharts']),
            'legacy': {
                'available': legacy['available'], 'counts': legacy['counts'],
                'chartCodes': list(legacy['chartCodes']), 'kpiTypes': list(legacy['kpiTypes']),
                'families': list(legacy['families']), 'schemaSource': legacy['schemaSource'],
                'catalogSource': legacy['catalogSource'], 'completeJsonSchema': False,
                'limits': legacy['limits'][:2],
            },
        }
    elif chart_type is not None:
        result['selection'] = {'chartType': chart_type}
        result['nativeCharts'] = {chart_type: result['nativeCharts'][chart_type]}
        del result['legacy']
    elif legacy_code is not None:
        legacy = result['legacy']
        require(legacy['available'], 'Original schema registry is not installed', 'LEGACY_UNAVAILABLE')
        require(legacy_code in legacy['chartCodes'] or legacy_code in legacy['kpiTypes'],
                'Unknown original chart/KPI code; table catalog entries use family=table with explicit columns and rows')
        family = 'chart' if legacy_code in legacy['chartCodes'] else 'kpi'
        result['selection'] = {'code': legacy_code, 'family': family}
        del result['nativeCharts']
        legacy['chartCodes'] = {legacy_code: legacy['chartCodes'][legacy_code]} if family == 'chart' else {}
        legacy['kpiTypes'] = {legacy_code: legacy['kpiTypes'][legacy_code]} if family == 'kpi' else {}
        legacy['catalogEntries'] = [entry for entry in legacy['catalogEntries'] if entry['id'] == legacy_code]
        legacy['families'] = {family: legacy['families'][family]}
        selected_schema = legacy['families'][family]['componentSchema']['properties']['config']
        selected_schema['properties']['code' if family == 'chart' else 'type'] = {'const': legacy_code}
        if family == 'kpi':
            selected_schema['required'].append('type')
            legacy['families'][family]['example'] = _legacy_example('kpi', legacy['kpiTypes'][legacy_code]['exampleConfig'])
        elif legacy_code != 'c01':
            # c01 demonstrates only its own shape. Never advertise it as a
            # runnable config for a different code with different data paths.
            legacy['families'][family].pop('example')
            legacy['families'][family]['exampleNote'] = 'The complete resource includes a c01 example. This selected code uses its own registry requirements; supply reviewed business data and presentation, then validate.'
    # Normalize registry tuples and detach all nested values for JSON callers.
    return json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False))
