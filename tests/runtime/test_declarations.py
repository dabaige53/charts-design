"""Declaration discovery must reflect accepted runtime data, not renderer guesses."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from dashboard_runtime import declarations
from dashboard_runtime.contract import CONTRACT
from dashboard_runtime.declarations import declaration_contract
from dashboard_runtime.model import DashboardError, TYPES, apply_operations, new_document, validate

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def reference():
    return declaration_contract()


@pytest.mark.parametrize('chart_type', TYPES)
def test_every_native_example_is_complete_and_valid(reference, chart_type):
    chart = reference['nativeCharts'][chart_type]
    example = chart['example']
    document = apply_operations(new_document('example', 'Declaration example'), example['operations'])
    component = document['manifest']['components'][example['componentId']]
    assert component['chartType'] == chart_type
    assert set(chart['componentSchema']['required']) <= set(component)
    assert validate(document) is document
    assert document['snapshot']['status'] == 'fixture'
    assert document['manifest']['sources']['example-source']['kind'] == 'fixture'


@pytest.mark.skipif(not shutil.which('node'), reason='Node is needed to check the native renderer')
def test_native_examples_produce_real_render_options(reference):
    documents = []
    for name, chart in reference['nativeCharts'].items():
        example = chart['example']
        documents.append({'componentId': example['componentId'],
                          'document': apply_operations(new_document('example', name), example['operations'])})
    engine = (ROOT / 'dashboard_runtime/web/engine.mjs').as_uri()
    script = f'''import {{optionFor}} from {json.dumps(engine)};
import {{readFileSync}} from 'node:fs';
for (const sample of JSON.parse(readFileSync(0, 'utf8'))) {{
  const option = optionFor(sample.document, sample.componentId);
  if (!option.series?.length || option.series.some(s => !s.data?.length)) throw Error(sample.componentId);
}}
console.log('8 rendered declarations');'''
    result = subprocess.run(['node', '--input-type=module', '-e', script],
                            input=json.dumps(documents), text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert '8 rendered declarations' in result.stdout


@pytest.mark.parametrize('chart_type,change', [
    ('heatmap', 'remove-series'), ('scatter', 'nonnumeric-x'),
    ('waterfall', 'remove-delta'), ('pie', 'nonadditive'), ('funnel', 'nonadditive'),
])
def test_documented_native_constraints_are_enforced(reference, chart_type, change):
    example = reference['nativeCharts'][chart_type]['example']
    document = apply_operations(new_document('example', 'Constraints'), example['operations'])
    component = document['manifest']['components'][example['componentId']]
    metric = document['manifest']['metrics']['example-value']
    if change == 'remove-series':
        del component['series']
    elif change == 'nonnumeric-x':
        component['x'] = 'region'
    elif change == 'remove-delta':
        del metric['semantic']
    else:
        metric['aggregation'] = 'avg'
    with pytest.raises(DashboardError):
        validate(document)


@pytest.mark.parametrize('family', ['chart', 'kpi', 'table'])
def test_legacy_family_examples_validate(reference, family):
    if not reference['legacy']['available']:
        pytest.skip('Original repository is required for legacy validation')
    example = reference['legacy']['families'][family]['example']
    document = apply_operations(new_document('example', family), example['operations'])
    assert document['manifest']['components'][example['componentId']]['family'] == family


@pytest.mark.parametrize('code', [f'mc{i:02d}' for i in range(1, 10)])
def test_each_legacy_kpi_selected_example_validates(code):
    if not declaration_contract(summary=True)['legacy']['available']:
        pytest.skip('Original repository is required for legacy validation')
    reference = declaration_contract(legacy_code=code)
    assert reference['selection'] == {'code': code, 'family': 'kpi'}
    assert list(reference['legacy']['kpiTypes']) == [code]
    example = reference['legacy']['families']['kpi']['example']
    document = apply_operations(new_document('example', code), example['operations'])
    assert document['manifest']['components'][example['componentId']]['config']['type'] == code


def test_legacy_registry_and_catalog_are_distinguished(reference):
    legacy = reference['legacy']
    if not legacy['available']:
        pytest.skip('Original repository is required for registry assertions')
    registry = declarations._registry()
    catalog = json.loads((ROOT / declarations.LEGACY_CATALOG_SOURCE).read_text())
    assert legacy['catalogEntries'] == catalog
    assert legacy['counts'] == {
        'catalogEntries': 45, 'registeredChartCodes': 40, 'registeredKpiTypes': 9}
    assert set(legacy['chartCodes']) == set(registry.CHART_CODES)
    assert set(legacy['kpiTypes']) == set(registry.KPI_TYPES)
    assert 'r05' in legacy['chartCodes']
    assert legacy['chartCodes']['r05']['catalogEntry'] is None
    assert 'tb01' not in legacy['chartCodes']
    assert 'mc01' not in legacy['chartCodes']
    for code, entry in legacy['chartCodes'].items():
        assert entry['completeJsonSchema'] is False
        assert entry['schemaSource'] == declarations.LEGACY_SCHEMA_SOURCE
        assert entry['presentationRequirements'] == json.loads(json.dumps(registry.CHART_PRESENTATION_CONTRACTS[code]))
        assert entry['tableHeaderCount'] == registry.CHART_TABLE_HEADER_COUNTS[code]
        assert entry['registeredArrayFields'] == [
            {'field': name, 'items': kind, 'minItems': 1}
            for name, kind in registry.CHART_ARRAY_FIELDS.get(code, ())]


def test_compact_index_and_native_selection(reference):
    index = declaration_contract(summary=True)
    assert len(json.dumps(index)) < 4000
    assert index['summary'] is True
    assert index['nativeCharts'] == list(TYPES)
    assert index['resource'] == CONTRACT['declarationsResource']
    selected = declaration_contract(chart_type='heatmap')
    assert list(selected['nativeCharts']) == ['heatmap']
    assert selected['nativeCharts']['heatmap'] == reference['nativeCharts']['heatmap']
    assert 'legacy' not in selected
    assert len(json.dumps(selected)) < 15000


def test_legacy_selection_never_substitutes_a_different_code_example():
    if not declaration_contract(summary=True)['legacy']['available']:
        pytest.skip('Original repository is required for legacy selection')
    selected = declaration_contract(legacy_code='t06')
    assert list(selected['legacy']['chartCodes']) == ['t06']
    family = selected['legacy']['families']['chart']
    assert 'example' not in family
    assert family['componentSchema']['properties']['config']['properties']['code'] == {'const': 't06'}
    assert 'exampleNote' in family


@pytest.mark.parametrize('arguments', [
    {'chart_type': 'unknown'}, {'chart_type': {}}, {'legacy_code': []}, {'legacy_code': 'unknown'},
    {'chart_type': 'bar', 'legacy_code': 'c01'}, {'chart_type': 'bar', 'summary': True},
])
def test_invalid_selections_fail_explicitly(arguments):
    with pytest.raises(DashboardError):
        declaration_contract(**arguments)


def test_discovery_is_detached_json_data(reference):
    encoded = json.dumps(reference, allow_nan=False)
    assert json.loads(encoded) == reference
    changed = declaration_contract(chart_type='bar')
    changed['nativeCharts']['bar']['example']['operations'].clear()
    assert declaration_contract(chart_type='bar')['nativeCharts']['bar']['example']['operations']


def test_missing_legacy_sources_preserves_native_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr(declarations, 'REPO', tmp_path)
    reference = declaration_contract()
    assert reference['legacy']['available'] is False
    assert reference['legacy']['counts'] == {
        'catalogEntries': 0, 'registeredChartCodes': 0, 'registeredKpiTypes': 0}
    assert set(reference['nativeCharts']) == set(TYPES)
    with pytest.raises(DashboardError) as failure:
        declaration_contract(legacy_code='c01')
    assert failure.value.code == 'LEGACY_UNAVAILABLE'


def test_contract_exposes_conditional_native_and_legacy_fields():
    fields = CONTRACT['operations']['put_component']['value']
    assert {'series', 'family', 'config', 'sourceId', 'binding'} <= set(fields)
    assert {'code', 'type', 'data', 'presentation', 'columns', 'rows'} <= set(fields['config'])
    assert 'conditional' in ' '.join(CONTRACT['rules'])


def test_declarations_do_not_import_transport_modules():
    result = subprocess.run([sys.executable, '-c', '''import sys
from dashboard_runtime.declarations import declaration_contract
assert declaration_contract(summary=True)['summary']
assert 'dashboard_runtime.service' not in sys.modules
assert 'dashboard_runtime.contract' not in sys.modules
from dashboard_runtime.contract import CONTRACT
from dashboard_runtime.service import Service
assert CONTRACT['declarationsResource'] == 'charts://declarations'
'''], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_advertised_shape_schemas_accept_their_examples(reference):
    jsonschema = pytest.importorskip('jsonschema')
    for chart in reference['nativeCharts'].values():
        schema = chart['componentSchema']
        jsonschema.Draft202012Validator.check_schema(schema)
        component = next(op['value'] for op in chart['example']['operations'] if op['op'] == 'put_component')
        jsonschema.validate(component, schema)
        for operation in chart['example']['operations']:
            common_schema = {'put_source': 'sourceSchema', 'put_metric': 'metricSchema',
                             'put_dataset': 'datasetMetaSchema'}.get(operation['op'])
            if common_schema:
                value = operation.get('meta', operation.get('value'))
                jsonschema.validate(value, reference['common'][common_schema])
    for family in reference['legacy']['families'].values():
        schema = family['componentSchema']
        jsonschema.Draft202012Validator.check_schema(schema)
        component = next(op['value'] for op in family['example']['operations'] if op['op'] == 'put_component')
        jsonschema.validate(component, schema)
    for name in ('sourceSchema', 'metricSchema', 'datasetMetaSchema', 'componentSchema'):
        jsonschema.Draft202012Validator.check_schema(reference['common'][name])
