"""Small data initialization and component-independent, revision-pinned previews."""
import copy
import json
import sqlite3
from contextlib import closing

import pytest

from dashboard_runtime.dataset_authoring import dataset_preview, dataset_source_id, parse_dataset_input
from dashboard_runtime.doctor import data_version
from dashboard_runtime.model import DashboardError, MAX_BYTES, MAX_ROWS
from dashboard_runtime.service import Service


# @wu-test type=behavior | scope=CSV数据初始化 | protects=常见数值空单元格导致整表失败或前导零ID被转成数值
def test_csv_inference_preserves_identifiers_and_converts_empty_cells_to_null():
    rows, fields = parse_dataset_input({'csvText': '\ufeffregion,amount,postcode\r\nEast,12,00123\r\nSouth,,00234\r\n'})
    assert rows == [{'region': 'East', 'amount': 12, 'postcode': '00123'},
                    {'region': 'South', 'amount': None, 'postcode': '00234'}]
    assert fields == {'region': {'type': 'string', 'label': 'region'},
                      'amount': {'type': 'number', 'label': 'amount'},
                      'postcode': {'type': 'string', 'label': 'postcode'}}


# @wu-test type=behavior | scope=显式数据字段类型 | protects=数值ID被求和化或布尔值、月份及标签在导入中被重解释
def test_explicit_fields_control_csv_conversion_and_preserve_json_values():
    fields = {'customerId': {'type': 'string', 'label': 'Customer'}, 'amount': {'type': 'number'},
              'active': {'type': 'boolean'}, 'month': {'type': 'date'}}
    csv_rows, parsed = parse_dataset_input({'fields': fields,
        'csvText': 'customerId,amount,active,month\n123,1.5e2,TRUE,2026-01\n001,,0,2026-02\n'})
    assert csv_rows == [{'customerId': '123', 'amount': 150, 'active': True, 'month': '2026-01'},
                        {'customerId': '001', 'amount': None, 'active': False, 'month': '2026-02'}]
    incoming = {'fields': fields, 'rows': [csv_rows[0], {'customerId': '001', 'active': None}]}
    before = copy.deepcopy(incoming)
    rows, _ = parse_dataset_input(incoming)
    assert rows == incoming['rows'] and incoming == before
    assert 'amount' not in rows[1] and rows[1]['active'] is None
    parsed['customerId']['label'] = 'Changed result'
    assert fields['customerId']['label'] == 'Customer'


# @wu-test type=boundary | scope=CSV结构检查 | protects=重复表头或错列数静默覆盖、删除或错位输入值
@pytest.mark.parametrize(('text', 'message'), [
    ('amount,amount\n1,2\n', 'unique'),
    ('region,\nEast,12\n', 'non-empty'),
    ('region, \nEast,12\n', 'non-empty'),
    ('region,amount\nEast\n', 'expected 2 cells, got 1'),
    ('region,amount\nEast,12,extra\n', 'expected 2 cells, got 3'),
    ('region,amount\n"East,12\n', 'Invalid CSV'),
])
def test_csv_invalid_structure_is_rejected_before_values_are_lost(text, message):
    with pytest.raises(DashboardError, match=message) as error:
        parse_dataset_input({'csvText': text})
    assert error.value.code == 'INVALID_ARGUMENT'


# @wu-test type=boundary | scope=显式字段数据校验 | protects=类型强转掩盖错误或非有限数、复合值进入运行数据
@pytest.mark.parametrize('arguments', [
    {'fields': {'amount': {'type': 'number'}}, 'rows': [{'amount': '12'}]},
    {'fields': {'amount': {'type': 'number'}}, 'rows': [{'amount': True}]},
    {'fields': {'amount': {'type': 'number'}}, 'rows': [{'amount': float('nan')}]},
    {'fields': {'amount': {'type': 'number'}}, 'rows': [{'amount': 2**63}]},
    {'fields': {'active': {'type': 'boolean'}}, 'rows': [{'active': 1}]},
    {'fields': {'month': {'type': 'date'}}, 'rows': [{'month': 202601}]},
    {'fields': {'amount': {'type': 'number'}}, 'csvText': 'amount\n1e309\n'},
    {'fields': {'active': {'type': 'boolean'}}, 'csvText': 'active\nyes\n'},
    {'fields': {'known': {'type': 'string'}}, 'csvText': 'unknown\nvalue\n'},
    {'fields': {'known': {'type': 'string'}}, 'rows': [{'unknown': 'value'}]},
    {'fields': {'': {'type': 'string'}}, 'rows': []},
    {'fields': {'value': {'type': 'object'}}, 'rows': []},
    {'rows': [{'value': {'nested': 'value'}}]},
    {'rows': [None]},
    {'rows': [{'amount': 1}, {'amount': 'n/a'}]},
])
def test_invalid_cells_do_not_become_usable_dataset_values(arguments):
    with pytest.raises(DashboardError) as error:
        parse_dataset_input(arguments)
    assert error.value.code == 'INVALID_ARGUMENT'


# @wu-test type=boundary | scope=空数据集初始化 | protects=空数据被默认为未知字符串字段或不完整导入请求被接受
def test_empty_inputs_require_explicit_schema_and_exactly_one_input():
    fields = {'month': {'type': 'date'}, 'amount': {'type': 'number'}}
    assert parse_dataset_input({'rows': [], 'fields': fields}) == ([], fields)
    assert parse_dataset_input({'csvText': 'month,amount\n', 'fields': fields}) == ([], fields)
    for args in ({}, {'rows': []}, {'csvText': 'month,amount\n'},
                 {'rows': [], 'csvText': 'month,amount\n', 'fields': fields}):
        with pytest.raises(DashboardError) as error:
            parse_dataset_input(args)
        assert error.value.code == 'INVALID_ARGUMENT'


# @wu-test type=boundary | scope=小数据导入边界 | protects=新增解析入口绕过既有20000行与16MiB限制
@pytest.mark.parametrize('format, boundary', [('rows', 'count'), ('csv', 'count'), ('rows', 'bytes'), ('csv', 'bytes')])
def test_dataset_input_retains_bounded_payload_limits(format, boundary):
    if format == 'rows':
        arguments = {'rows': [{'value': 1}] * (MAX_ROWS + 1) if boundary == 'count' else [{'value': 'x' * MAX_BYTES}]}
    else:
        arguments = {'csvText': 'value\n' + ('1\n' * (MAX_ROWS + 1) if boundary == 'count' else 'x' * MAX_BYTES)}
    with pytest.raises(DashboardError) as error:
        parse_dataset_input(arguments)
    assert error.value.code == 'PAYLOAD_TOO_LARGE'


# @wu-test type=boundary | scope=数据来源ID派生 | protects=合法长数据集ID导入失败或不同数据集被映射到同一来源
@pytest.mark.parametrize('prefix', ['import', 'local'])
def test_dataset_source_ids_preserve_existing_ids_and_hash_long_names(prefix):
    import hashlib

    assert dataset_source_id(prefix, 'sales') == f'{prefix}-sales'
    boundary = 'd' * (80 - len(prefix) - 1)
    assert dataset_source_id(prefix, boundary) == f'{prefix}-{boundary}'
    longest = 'd' * 80
    result = dataset_source_id(prefix, longest)
    assert result == f'{prefix}-{hashlib.sha256(longest.encode()).hexdigest()}'
    assert len(result) <= 80 and dataset_source_id(prefix, longest) == result
    assert dataset_source_id(prefix, 'd' * 79 + 'x') != result


@pytest.fixture
def project(tmp_path):
    service = Service(tmp_path / 'runtime', project_root=tmp_path / 'project')
    service.call('dashboard_create', {'dashboardId': 'initialization', 'title': 'Initialization'})
    return service


def imported(service, rows):
    doc = service.store.get('initialization', hydrate=False)
    service.call('dataset_import', {'dashboardId': doc['id'], 'datasetId': 'sales',
                 'expectedRevision': doc['revision'], 'rows': rows})
    return service.store.get('initialization', hydrate=False)


# @wu-test type=integration | scope=空数据与最长ID初始化 | protects=解析接受空数据或合法长ID后仍在实际存储或预览时失败
@pytest.mark.parametrize('input_value', [{'rows': []}, {'csvText': 'month,amount\n'}])
def test_empty_typed_data_with_long_id_can_be_imported_and_inspected(project, input_value):
    dataset_id = 'd' * 80
    fields = {'month': {'type': 'date'}, 'amount': {'type': 'number'}}
    result = project.call('dataset_import', {'dashboardId': 'initialization', 'expectedRevision': 1,
        'datasetId': dataset_id, 'fields': fields, **input_value})
    doc = result['document']
    assert doc['revision'] == 2
    assert len(doc['manifest']['datasets'][dataset_id]['sourceId']) <= 80
    preview = project.call('dataset_preview', {'dashboardId': doc['id'],
        'datasetId': dataset_id, 'expectedRevision': doc['revision']})
    assert preview['rows'] == [] and preview['totalRows'] == 0
    assert preview['fields'] == fields and preview['nextOffset'] is None
    assert project.store.revision(doc['id']) == doc['revision']


# @wu-test type=integration | scope=无组件数据预览 | protects=导入后必须先造组件才能看数据或预览将完整数据灌入模型
def test_import_then_preview_without_components_preserves_nulls_and_missing_fields(project, monkeypatch):
    rows = [{'region': f'R{index}', 'amount': index, **({'active': None} if index % 2 else {'active': True})}
            for index in range(203)]
    del rows[3]['active']
    doc = imported(project, rows)
    assert doc['manifest']['components'] == {}
    monkeypatch.setattr(project.store, 'compact', lambda *_: pytest.fail('Preview must not prepare all datasets'))
    monkeypatch.setattr(project.store.data, 'iter_rows', lambda *_: pytest.fail('Preview must not hydrate full data'))
    args = {'dashboardId': doc['id'], 'datasetId': 'sales'}
    first = dataset_preview(project, args)
    assert first['rows'] == rows[:20] and first['totalRows'] == 203
    assert first['offset'] == 0 and first['limit'] == first['nextOffset'] == 20 and first['hasMore']
    assert first['fields'] == doc['manifest']['datasets']['sales']['fields']
    assert first['sourceId'] == doc['manifest']['datasets']['sales']['sourceId']
    assert first['mode'] == 'snapshot' and first['transient'] is False
    assert first['scope'] == 'unfiltered-dataset' and first['filtersApplied'] is False
    assert first['datasetVersion'] == doc['snapshot']['datasetRefs']['sales']['version']
    assert first['dataVersion'] == data_version(doc)
    last = dataset_preview(project, {**args, 'offset': 200, 'limit': 100})
    assert last['rows'] == rows[200:] and last['totalRows'] == 203
    assert not last['hasMore'] and last['nextOffset'] is None
    beyond = dataset_preview(project, {**args, 'offset': 300})
    assert beyond['rows'] == [] and beyond['totalRows'] == 203 and not beyond['hasMore']
    assert project.store.get(doc['id'], hydrate=False) == doc


# @wu-test type=integration | scope=数据预览修订一致性 | protects=草稿更新后预览混读已保存版本或冲突未被拒绝
def test_dataset_preview_pins_saved_revision_and_rejects_conflicting_versions(project):
    saved = imported(project, [{'region': 'saved', 'amount': 10}])
    project.call('dashboard_submit', {'dashboardId': saved['id'], 'expectedRevision': saved['revision']})
    current = imported(project, [{'region': 'draft', 'amount': 30}, {'region': 'draft', 'amount': 40}])
    reading = {'dashboardId': saved['id'], 'datasetId': 'sales',
               'expectedRevision': saved['revision'], 'dataVersion': data_version(saved)}
    before = dataset_preview(project, reading)
    after = dataset_preview(project, {'dashboardId': saved['id'], 'datasetId': 'sales'})
    assert before['rows'] == [{'region': 'saved', 'amount': 10}] and before['revision'] == saved['revision']
    assert after['totalRows'] == 2 and after['revision'] == current['revision']
    for mismatch in ({'expectedRevision': 999}, {'dataVersion': data_version(current)}):
        with pytest.raises(DashboardError) as error:
            dataset_preview(project, {**reading, **mismatch})
        assert error.value.code == 'REVISION_CONFLICT'
    assert project.store.get(saved['id'], hydrate=False) == current


# @wu-test type=integration | scope=数据预览过滤范围 | protects=数据探索隐式继承组件过滤而将部分数据误当全量
def test_dataset_preview_explicitly_ignores_saved_component_filters(project):
    doc = imported(project, [{'region': 'east', 'amount': 1}, {'region': 'west', 'amount': 2}])
    project.call('dashboard_patch', {'dashboardId': doc['id'], 'expectedRevision': doc['revision'], 'operations': [
        {'op': 'put_component', 'id': 'details', 'value': {'kind': 'table', 'title': 'Details', 'datasetId': 'sales'}},
        {'op': 'set_filters', 'value': [{'id': 'region', 'field': 'region', 'op': 'in',
                                      'values': ['east'], 'componentIds': ['details']}]},
    ]})
    result = dataset_preview(project, {'dashboardId': doc['id'], 'datasetId': 'sales'})
    assert result['totalRows'] == 2 and len(result['rows']) == 2 and result['filtersApplied'] is False


# @wu-test type=boundary | scope=数据预览分页参数 | protects=无效边界导致无界读取、SQLite溢出或指向未知数据集
@pytest.mark.parametrize('override', [
    {'offset': -1}, {'offset': True}, {'offset': 2**53}, {'offset': 0.5},
    {'limit': 0}, {'limit': 101}, {'limit': True}, {'datasetId': 'missing'},
])
def test_dataset_preview_rejects_invalid_page_requests(project, override):
    imported(project, [{'amount': 1}])
    with pytest.raises(DashboardError) as error:
        dataset_preview(project, {'dashboardId': 'initialization', 'datasetId': 'sales', **override})
    assert error.value.code == ('NOT_FOUND' if 'datasetId' in override else 'INVALID_ARGUMENT')


# @wu-test type=integration | scope=数据挂接前置版本检查 | protects=目标不存在或修订已过期的请求仍完整复制源数据并留下无引用版本
@pytest.mark.parametrize(('board', 'revision', 'code'), [
    ('initialization', 999, 'REVISION_CONFLICT'), ('missing', 1, 'NOT_FOUND'),
])
def test_attach_rejects_stale_or_missing_target_before_copying_data(tmp_path, board, revision, code):
    database = tmp_path / 'source.sqlite3'
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('CREATE TABLE sales (amount REAL)')
        db.executemany('INSERT INTO sales VALUES (?)', [(10,), (20,)])
    config = tmp_path / 'sources.json'
    config.write_text(json.dumps({'sales': {'engine': 'sqlite', 'path': str(database)}}))
    service = Service(tmp_path / 'runtime', config, project_root=tmp_path / 'project')
    service.call('dashboard_create', {'dashboardId': 'initialization'})
    with pytest.raises(DashboardError) as error:
        service.call('dataset_attach', {'dashboardId': board, 'expectedRevision': revision,
            'datasetId': 'sales', 'connection': 'sales', 'table': 'sales'})
    assert error.value.code == code
    with closing(sqlite3.connect(service.store.data.path)) as db:
        assert db.execute('SELECT count(*) FROM versions').fetchone()[0] == 0
    assert service.store.get('initialization')['manifest']['datasets'] == {}
    assert service.store.revision('initialization') == 1


# @wu-test type=integration | scope=实时SQL原始数据预览 | protects=实时预览读取旧快照、保存临时行或以样本数量误报总数
def test_dataset_preview_live_sql_uses_current_rows_without_persisting_them(tmp_path, monkeypatch):
    database = tmp_path / 'source.sqlite3'
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('CREATE TABLE sales (amount REAL, active INTEGER)')
        db.executemany('INSERT INTO sales VALUES (?, ?)', [(10, 1), (None, 0), (30, None)])
    config = tmp_path / 'sources.json'
    config.write_text(json.dumps({'sales': {'engine': 'sqlite', 'path': str(database)}}))
    service = Service(tmp_path / 'runtime', config, project_root=tmp_path / 'project')
    service.call('dashboard_create', {'dashboardId': 'live'})
    service.call('query_execute', {'dashboardId': 'live', 'datasetId': 'sales', 'expectedRevision': 1,
        'connection': 'sales', 'sql': 'SELECT * FROM sales', 'mode': 'live',
        'fields': {'amount': {'type': 'number'}, 'active': {'type': 'boolean'}}})
    doc = service.store.get('live', hydrate=False)
    monkeypatch.setattr(service.store.data, 'import_rows', lambda *_: pytest.fail('Live preview cannot persist rows'))
    args = {'dashboardId': 'live', 'datasetId': 'sales', 'limit': 1,
            'expectedRevision': doc['revision'], 'dataVersion': data_version(doc)}
    first = dataset_preview(service, args)
    assert first['mode'] == 'live' and first['transient'] is True and 'datasetVersion' not in first
    assert first['rows'] == [{'amount': 10, 'active': True}] and first['totalRows'] == 3
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('INSERT INTO sales VALUES (40, 0)')
    fresh = dataset_preview(service, {**args, 'offset': 3})
    assert fresh['rows'] == [{'amount': 40, 'active': False}] and fresh['totalRows'] == 4
    assert service.store.get('live', hydrate=False) == doc
    assert doc['snapshot'].get('datasetRefs', {}) == {}


# @wu-test type=integration | scope=COS数据预览查询文件 | protects=新预览错误使用本地表或必须全量恢复云端业务行
def test_dataset_preview_reads_cos_query_file_through_shared_data_interface(project, tmp_path, monkeypatch):
    from dashboard_runtime.cloud_data import CloudData

    doc = imported(project, [{'region': 'east', 'amount': 1}, {'region': 'west', 'amount': None}])
    ref = doc['snapshot']['datasetRefs']['sales']
    query_file = tmp_path / 'query.sqlite3'
    with closing(sqlite3.connect(project.store.data.path)) as source, closing(sqlite3.connect(query_file)) as target:
        source.backup(target)

    class Assets:
        def call(self, action, **args):
            assert action == 'object_get' and args['version'] == ref['version']
            return {'id': 'a' * 32, 'descriptor': {'queryFormat': 1, 'metadata': ref}}

        def read_file(self, _object, filename):
            assert filename == 'query.sqlite3'
            return query_file.read_bytes()

    cloud = CloudData(tmp_path / 'cloud', None, 'project', assets=Assets(), cos_enabled=True)
    monkeypatch.setattr(project.store, 'data', cloud)
    monkeypatch.setattr(cloud, 'iter_rows', lambda *_: pytest.fail('Preview must page the attached query file'))
    result = dataset_preview(project, {'dashboardId': doc['id'], 'datasetId': 'sales', 'offset': 1, 'limit': 1})
    assert result['rows'] == [{'region': 'west', 'amount': None}] and result['totalRows'] == 2
    assert result['datasetVersion'] == ref['version'] and not result['hasMore']
