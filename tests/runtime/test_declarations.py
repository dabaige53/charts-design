"""Declaration discovery must reflect accepted runtime data, not renderer guesses."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from dashboard_runtime import declarations
from dashboard_runtime.contract import CONTRACT
from dashboard_runtime.declarations import declaration_contract
from dashboard_runtime.model import DashboardError, apply_operations, new_document, validate

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def reference():
    return declaration_contract()


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
    assert registry is not None
    catalog = json.loads((ROOT / declarations.LEGACY_CATALOG_SOURCE).read_text())
    assert [{key: value for key, value in entry.items() if key != 'filterBinding'} for entry in legacy['catalogEntries']] == catalog
    assert all('filterBinding' in entry for entry in legacy['catalogEntries'])
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


def test_index_only_advertises_original_charts(reference):
    index = declaration_contract(summary=True)
    assert index['summary'] is True
    assert 'nativeCharts' not in index and 'nativeCharts' not in reference
    assert len(index['legacy']['chartCodes']) == 40
    assert 'chartType' not in reference['common']['componentSchema']['properties']
    with pytest.raises(DashboardError):
        declaration_contract(chart_type='bar')


def test_legacy_selection_never_substitutes_a_different_code_example():
    if not declaration_contract(summary=True)['legacy']['available']:
        pytest.skip('Original repository is required for legacy selection')
    selected = declaration_contract(legacy_code='t06')
    assert list(selected['legacy']['chartCodes']) == ['t06']
    family = selected['legacy']['families']['chart']
    example = family['example']
    document = apply_operations(new_document('example', 't06'), example['operations'])
    assert document['manifest']['components'][example['componentId']]['config']['code'] == 't06'
    assert family['componentSchema']['properties']['config']['properties']['code'] == {'const': 't06'}
    assert selected['legacy']['chartCodes']['t06']['filterBinding']['supported'] is True


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
    changed = declaration_contract(legacy_code='c01')
    changed['legacy']['families']['chart']['example']['operations'].clear()
    assert declaration_contract(legacy_code='c01')['legacy']['families']['chart']['example']['operations']


def test_missing_original_sources_has_no_alternative_chart_system(tmp_path, monkeypatch):
    monkeypatch.setattr(declarations, 'REPO', tmp_path)
    reference = declaration_contract()
    assert reference['legacy']['available'] is False
    assert reference['legacy']['counts'] == {
        'catalogEntries': 0, 'registeredChartCodes': 0, 'registeredKpiTypes': 0}
    assert 'nativeCharts' not in reference
    with pytest.raises(DashboardError) as failure:
        declaration_contract(legacy_code='c01')
    assert failure.value.code == 'LEGACY_UNAVAILABLE'


def test_contract_exposes_conditional_native_and_legacy_fields():
    fields = CONTRACT['operations']['put_component']['value']
    assert {'family', 'config', 'sourceId', 'binding'} <= set(fields)
    assert {'code', 'type', 'data', 'presentation', 'columns', 'rows'} <= set(fields['config'])
    assert 'chartType' not in fields and 'set_chart' not in CONTRACT['operations']
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
    for family in reference['legacy']['families'].values():
        schema = family['componentSchema']
        jsonschema.Draft202012Validator.check_schema(schema)
        component = next(op['value'] for op in family['example']['operations'] if op['op'] == 'put_component')
        jsonschema.validate(component, schema)
    for name in ('sourceSchema', 'metricSchema', 'datasetMetaSchema', 'componentSchema'):
        jsonschema.Draft202012Validator.check_schema(reference['common'][name])


@pytest.mark.parametrize('code', ['t06', 'm01'])
def test_advanced_examples_are_legal_own_code_configs(code):
    selected = declaration_contract(legacy_code=code)
    example = selected['legacy']['families']['chart']['example']
    doc = apply_operations(new_document('example', code), example['operations'])
    assert doc['manifest']['components'][example['componentId']]['config']['code'] == code
    assert validate(doc) is doc
    capability = selected['legacy']['chartCodes'][code]['filterBinding']
    assert capability['snapshotOnly'] is (code == 'm01')


def test_public_metadata_and_table_heading_contract(reference):
    assert set(reference['common']['metaSchema']['properties']) == {'subtitle', 'org', 'system', 'statusText', 'iconKey'}
    assert 'subtitle' in reference['common']['componentSchema']['properties']
    assert 'contains' in reference['common']['filterSchema']['properties']['op']['enum']
    columns = reference['legacy']['families']['table']['componentSchema']['properties']['config']['properties']['columns']
    assert {'title', 'label', 'key'} <= set(columns['items']['properties'])
