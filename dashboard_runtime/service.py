"""Transport-independent command service. Mutation arguments are always explicit."""
from __future__ import annotations
import copy
import time
from .model import DashboardError, apply_operations, identifier, inferred_fields, require, validate
from .query import QueryRunner
from .store import Store
from .declarations import declaration_contract
from .local_view import LocalView

class Service:
    def __init__(self, root, sources_file=None):
        self.store, self.queries = Store(root), QueryRunner(sources_file)
        self.views = LocalView(self.store.data)

    def call(self, tool, args):
        started = time.perf_counter()
        result = self._call(tool, args)
        if "document" in result:
            from .statistical import statistical_artifacts
            doc = result['document']
            if tool in ('dashboard_preview', 'dashboard_view', 'dashboard_refresh', 'dashboard_migration_rollback') or args.get('dataMode') == 'local' or doc['snapshot'].get('localMode') or doc['snapshot'].get('datasetRefs'):
                doc = self.store.compact(doc)
                doc = self.views.prepare(doc, None if tool == 'dashboard_refresh' else args.get('filters'), args.get('tableStates'), args.get('granularities'))
                result['document'] = doc
            result["statisticalArtifacts"] = statistical_artifacts(self.store.statistical_document(doc))
            if doc.get('computed'):
                doc['computed']['totalDurationMs'] = (time.perf_counter()-started)*1000
        return result

    def _call(self, tool, args):
        require(isinstance(args, dict), 'Tool arguments must be an object')
        if tool == 'runtime_keepalive':
            return {'ok': True}
        board = args.get('dashboardId')
        if tool == 'runtime_info':
            from .assets import ui_build_id
            from . import __version__
            return {'version': __version__, 'uiBuildId': ui_build_id(),
                    'dashboardRevision': self.store.get(board, hydrate=False)['revision'] if board else None}
        if tool == 'dashboard_refresh':
            doc = self.store.get(board, hydrate=False)
            incoming = args.get('filters')
            if incoming is not None:
                require(isinstance(incoming, list), 'Filter overrides must be an array')
                values = {}
                for item in incoming:
                    require(isinstance(item, dict) and isinstance(item.get('id'), str) and isinstance(item.get('values'), list), 'Invalid filter override')
                    values[item.get('id')] = item['values']
                for declared in doc['manifest']['filters']:
                    if declared['id'] in values:
                        declared['values'] = copy.deepcopy(values[declared['id']])
                doc['manifest']['filters'].extend(copy.deepcopy(item) for item in incoming if item.get('id') == 'runtime-linkage')
                doc = validate(doc)
            return {'document': doc}
        if tool == 'statistical_render':
            from .statistical import render_statistical
            doc = self.store.statistical_document(self.store.get(board, hydrate=False))
            return render_statistical(doc, args.get('componentId'), args.get('format', 'svg'))
        if tool == 'generation_examples':
            from .generation import generation_examples
            return generation_examples(args.get('caseId'))
        if tool == 'chart_declarations':
            return declaration_contract(chart_type=args.get('chartType'), legacy_code=args.get('code'), summary=not (args.get('chartType') or args.get('code')))
        if tool == 'dashboard_list':
            return {'dashboards': self.store.list()}
        if tool == 'dashboard_export_open':
            from .exports import open_export
            return open_export(self.store.root, board, args.get('exportId'), args.get('format'), args.get('action'))
        if tool == 'dashboard_export':
            from .exports import export_dashboard
            doc = self.store.compact(self.store.get(board, hydrate=False))
            view = self.views.prepare(doc, args.get('filters'), args.get('tableStates'), args.get('granularities'))
            return export_dashboard(self.store.root, view, args.get('format'), self.store.data)
        if tool == 'dashboard_view':
            return {'document': self.store.get(board, hydrate=False)}
        if tool == 'dashboard_filter_options':
            doc = self.store.compact(self.store.get(board, hydrate=False))
            return self.views.filter_options(doc, args.get('filterId'), args.get('search', ''), args.get('offset', 0), args.get('limit', 100))
        if tool == 'dashboard_data_inspect':
            doc = self.store.compact(self.store.get(board, hydrate=False))
            refs = doc['snapshot'].get('datasetRefs', {})
            shared = {}
            for key, ref in refs.items():
                shared.setdefault(ref['version'], []).append(key)
            return {'datasets': refs, 'componentData': doc['snapshot'].get('componentDataRefs', {}),
                    'sharedVersions': [ids for ids in shared.values() if len(ids) > 1],
                    'configBytes': len(__import__('json').dumps(doc).encode()),
                    'dataFileBytes': self.store.data.path.stat().st_size}
        if tool == 'dashboard_migrate':
            migration = self.store.migrate(board, args.get('expectedRevision'))
            return {'document': self.store.get(board, hydrate=False), 'migration': migration}
        if tool == 'dashboard_migration_rollback':
            return {'document': self.store.rollback_migration(board, args.get('expectedRevision'), args.get('backupId'))}
        if tool == 'dataset_attach':
            imported_at = time.perf_counter()
            require(args.get('connection') in self.queries.sources, 'Configure the local source alias before attaching data', 'SOURCE_NOT_ALLOWED')
            ds = identifier(args.get('datasetId'))
            ref = self.store.data.import_sqlite(self.queries.sources[args['connection']], args.get('table'), args.get('fields'))
            source = 'local-' + ds
            ops = [{'op': 'put_source', 'id': source, 'value': {'kind': 'file', 'name': args['connection'] + ':' + args['table'], 'verification': 'runtime-executed'}},
                   {'op': 'put_dataset_ref', 'id': ds, 'meta': {'fields': ref['fields'], 'sourceId': source}, 'ref': ref},
                   {'op': 'set_data_mode', 'value': 'local'}]
            return {'document': self.store.mutate(board, args.get('expectedRevision'), ops), 'import': {'rowCount': ref['rowCount'], 'logicalBytes': ref['bytes'], 'durationMs': (time.perf_counter()-imported_at)*1000}}
        if tool == 'component_data':
            doc = self.store.compact(self.store.get(board, hydrate=False))
            require(args.get('expectedRevision', doc['revision']) == doc['revision'], 'Data changed; reopen the component explanation')
            key = args.get('componentId')
            component = doc['manifest']['components'].get(key)
            require(component is not None, 'Component not found')
            ds = component.get('datasetId') or component.get('binding', {}).get('datasetId')
            ref = doc['snapshot'].get('datasetRefs', {}).get(ds) if ds else doc['snapshot'].get('componentDataRefs', {}).get(key)
            require(ref is not None, 'Component has no row dataset')
            filters = args.get('filters', doc['manifest']['filters'])
            checked = apply_operations(doc, [{'op': 'set_filters', 'value': filters}])
            active = [f for f in checked['manifest']['filters'] if key in f['componentIds'] and f['values']]
            offset, limit = args.get('offset', 0), args.get('limit', 1000)
            require(type(offset) is int and offset >= 0 and type(limit) is int and 1 <= limit <= 1000, 'Invalid data range')
            return self.store.data.rows(ref, active, offset=offset, limit=limit)
        if tool == 'dataset_export':
            import uuid
            doc = self.store.compact(self.store.get(board, hydrate=False))
            key = args.get('componentId')
            component = doc['manifest']['components'].get(key) if key else None
            ds = component.get('datasetId') if component else args.get('datasetId')
            ref = doc['snapshot'].get('datasetRefs', {}).get(ds) if ds else doc['snapshot'].get('componentDataRefs', {}).get(key)
            require(ref is not None, 'Choose an existing dataset or table component')
            filters = args.get('filters', doc['manifest']['filters'])
            checked = apply_operations(doc, [{'op': 'set_filters', 'value': filters}])
            active = [f for f in checked['manifest']['filters'] if f['values'] and (key in f['componentIds'] if key else any(doc['manifest']['components'][cid].get('datasetId') == ds for cid in f['componentIds']))]
            export_dir = self.store.root / 'exports'
            export_dir.mkdir(mode=0o700, exist_ok=True)
            path = export_dir / (str(board) + '-' + uuid.uuid4().hex + '.csv')
            return {'export': self.store.data.export_csv(ref, path, active, args.get('columns'), args.get('sort'), search=args.get('search', ''))}
        if tool == 'dashboard_create':
            if args.get('document'):
                require(not any(c.get('kind') == 'chart' for c in args['document'].get('manifest', {}).get('components', {}).values()), 'New charts must use the original 40 codes (kind=legacy, family=chart)', 'UNSUPPORTED_CHART_FAMILY')
            doc = args.get('document')
            if doc is not None:
                doc = copy.deepcopy(doc)
                for source in doc.get('manifest', {}).get('sources', {}).values():
                    source['verification'] = 'supplied'
            return {'document': self.store.create(args['dashboardId'], args.get('title', 'Dashboard'), doc)}
        if tool in ('dashboard_get', 'dashboard_preview'):
            return {'document': self.store.get(board, hydrate=not (tool == 'dashboard_preview' or args.get('dataMode') == 'local'))}
        if tool == 'dashboard_validate':
            return {'valid': bool(validate(args.get('document') or self.store.get(board, hydrate=False)))}
        if tool == 'dashboard_patch':
            ops = copy.deepcopy(args.get('operations'))
            current = self.store.get(board, hydrate=False)
            require(isinstance(ops, list), 'operations must be an array')
            for op in ops:
                if isinstance(op, dict) and op.get('op') == 'set_chart':
                    require(False, 'Use set_original_chart with an original code', 'UNSUPPORTED_CHART_FAMILY')
                if isinstance(op, dict) and op.get('op') == 'put_component' and isinstance(op.get('value'), dict) and op['value'].get('kind') == 'chart':
                    old = current['manifest']['components'].get(op.get('id'), {})
                    require(old.get('kind') == 'chart' and old.get('chartType') == op['value'].get('chartType'), 'New charts must use the original 40 codes', 'UNSUPPORTED_CHART_FAMILY')
                if isinstance(op, dict) and op.get('op') == 'put_source' and isinstance(op.get('value'), dict):
                    op['value']['verification'] = 'supplied'
            return {'document': self.store.mutate(board, args.get('expectedRevision'), ops)}
        if tool == 'dashboard_history':
            return {'history': self.store.history(board)}
        if tool == 'dashboard_restore':
            return {'document': self.store.mutate(board, args.get('expectedRevision'), restore_revision=args.get('revision'))}
        if tool == 'chart_catalog':
            reference = declaration_contract(summary=True)
            charts = [{'code': code} for code in reference['legacy']['chartCodes']]
            from .legacy import catalog
            from .statistical import statistical_declarations
            return {'statistical': statistical_declarations(), 'charts': charts, 'legacy': catalog(), 'originalKpis': ['mc%02d'%i for i in range(1,10)], 'policy': 'Original components are preserved without automatic conversion; use explicit config and family.'}
        if tool in ('query_inspect', 'semantic_inspect'):
            doc = self.store.get(board, hydrate=False)
            c = doc['manifest']['components'].get(args.get('componentId'))
            require(c is not None, 'Component not found')
            meta = doc['manifest']['datasets'].get(c.get('datasetId'), {})
            source = doc['manifest']['sources'].get(meta.get('sourceId') or c.get('sourceId'))
            if tool == 'query_inspect':
                return {'source': source, 'snapshotUpdatedAt': doc['snapshot']['updatedAt'],
                        'filters': [f for f in doc['manifest']['filters'] if args['componentId'] in f['componentIds']],
                        'localVersion': doc['snapshot'].get('datasetRefs', {}).get(c.get('datasetId')),
                        'note': 'Interactive filters query the immutable local data version; upstream source SQL is not re-executed.'}
            return {'metrics': {key: doc['manifest']['metrics'][key] for key in c.get('measures', [])}, 'dataset': meta, 'originalPresentation': c.get('config',{}).get('presentation'), 'originalExplanation': c.get('config',{}).get('explanation'), 'statisticalAnalysis': c.get('analysis'), 'certified': False}
        if tool == 'legacy_render':
            from .assets import export_component
            doc = self.store.get(board)
            if doc['snapshot'].get('datasetRefs'):
                doc = self.views.prepare(self.store.compact(doc))
            key = args.get('componentId')
            c = doc['manifest']['components'].get(key)
            require(c is not None and c['kind'] == 'legacy', 'Original component not found')
            return {'html': export_component(doc, key), 'scope': 'component', 'componentId': key}
        if tool == 'dataset_import':
            import csv
            import io
            import re
            ds = identifier(args.get('datasetId'))
            rows = args.get('rows')
            if args.get('csvText') is not None:
                rows = list(csv.DictReader(io.StringIO(args['csvText'])))
                for row in rows:
                    for key, value in row.items():
                        if isinstance(value, str) and re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?', value):
                            row[key] = float(value) if '.' in value else int(value)
            fields = inferred_fields(rows)
            source_id = 'import-' + ds
            ops = [{'op': 'put_source', 'id': source_id, 'value': {'kind': 'file', 'name': args.get('name', ds), 'verification': 'supplied'}},
                   {'op': 'put_dataset', 'id': ds, 'meta': {'fields': fields, 'sourceId': source_id}, 'rows': rows}]
            doc = self.store.get(board)
            for index, (key, info) in enumerate(fields.items()):
                import uuid
                mid = 'metric-' + uuid.uuid5(uuid.NAMESPACE_URL, ds + ':' + key).hex[:20]
                if info['type'] == 'number' and mid not in doc['manifest']['metrics']:
                    ops.append({'op': 'put_metric', 'id': mid, 'value': {'datasetId': ds, 'field': key, 'aggregation': 'sum', 'label': key, 'unit': '', 'definition': f'业务定义待确认：字段「{key}」的业务对象、记录粒度、纳入与排除条件尚未说明。当前配置仅对该字段求和。', 'status': 'unverified'}})
            return {'document': self.store.mutate(board, args.get('expectedRevision'), ops)}
        if tool == 'query_execute':
            doc = self.store.get(board)
            require(doc['revision'] == args.get('expectedRevision'), 'Reload before running a query', 'REVISION_CONFLICT')
            ds = identifier(args.get('datasetId'))
            rows, fields, source = self.queries.execute(args.get('connection'), args.get('sql'), args.get('parameters'))
            if not rows and ds in doc['manifest']['datasets']:
                previous = doc['manifest']['datasets'][ds]['fields']
                fields = {key: previous.get(key, info) for key, info in fields.items()}
            source_id = 'query-' + source['query']['id']
            operations = [{'op': 'put_source', 'id': source_id, 'value': source},
                          {'op': 'put_dataset', 'id': ds, 'meta': {'fields': fields, 'sourceId': source_id}, 'rows': rows}]
            import uuid
            for key, info in fields.items():
                mid = 'metric-' + uuid.uuid5(uuid.NAMESPACE_URL, ds + ':' + key).hex[:20]
                if info['type'] == 'number' and mid not in doc['manifest']['metrics']:
                    operations.append({'op': 'put_metric', 'id': mid, 'value': {'datasetId': ds, 'field': key, 'aggregation': 'sum', 'label': key, 'unit': '', 'definition': f'业务定义待确认：字段「{key}」的业务对象、记录粒度、纳入与排除条件尚未说明。当前配置仅对该字段求和。', 'status': 'unverified'}})
            return {'document': self.store.mutate(board, args['expectedRevision'], operations), 'execution': source['query']}
        raise DashboardError('UNKNOWN_TOOL', f'Unsupported tool: {tool}', 404)

def schema(properties=None, required=()):
    return {'type': 'object', 'properties': properties or {}, 'required': list(required), 'additionalProperties': False}
STR = {'type': 'string'}
INT = {'type': 'integer', 'minimum': 1}
BOARD = {'dashboardId': STR, 'dataMode': {'enum': ['snapshot', 'local']}}
TARGET = {**BOARD, 'componentId': STR}
TOOLS = {
    'runtime_keepalive': ('Keep the local runtime alive only while its preview is visible; do not poll from background agents', schema()),
    'dashboard_list': ('List saved dashboards', schema()),
    'dashboard_create': ('Create a dashboard with an optional reviewed artifact', schema({**BOARD, 'title': STR, 'document': {'type': 'object'}}, ('dashboardId',))),
    'dashboard_get': ('Read current canonical state before editing', schema(BOARD, ('dashboardId',))),
    'dashboard_preview': ('Open an interactive MCP App; non-UI hosts receive the canonical artifact', schema(BOARD, ('dashboardId',))),
    'dashboard_validate': ('Validate a stored dashboard or supplied artifact', schema({**BOARD, 'document': {'type': 'object'}})),
    'dashboard_patch': ('Apply atomic typed operations with optimistic concurrency', schema({**BOARD, 'expectedRevision': INT, 'operations': {'type': 'array', 'minItems': 1, 'maxItems': 200, 'items': {'type': 'object'}}}, ('dashboardId', 'expectedRevision', 'operations'))),
    'dashboard_history': ('List the last 100 revisions', schema(BOARD, ('dashboardId',))),
    'dashboard_restore': ('Restore a revision as a new revision; never overwrite history', schema({**BOARD, 'expectedRevision': INT, 'revision': INT}, ('dashboardId', 'expectedRevision', 'revision'))),
    'chart_catalog': ('List the 40 installed original chart codes and component catalog', schema(TARGET)),
    'component_data': ('Read a bounded page of component snapshot rows using the current filters', schema({**TARGET, 'expectedRevision': INT, 'filters': {'type': 'array', 'items': {'type': 'object'}}, 'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 1000}}, ('dashboardId', 'componentId'))),
    'query_inspect': ('Inspect actual or supplied SQL provenance, without execution', schema(TARGET, ('dashboardId', 'componentId'))),
    'semantic_inspect': ('Inspect stored metric definitions, units and aggregation', schema(TARGET, ('dashboardId', 'componentId'))),
    'query_execute': ('Execute a bounded read-only SQLite query on a configured alias and atomically save its snapshot', schema({**BOARD, 'expectedRevision': INT, 'datasetId': STR, 'connection': STR, 'sql': STR, 'parameters': {'type': ['object', 'array']}}, ('dashboardId', 'expectedRevision', 'datasetId', 'connection', 'sql')))
}
READ_ONLY = {'component_data', 'dashboard_list', 'dashboard_get', 'dashboard_preview', 'dashboard_validate', 'dashboard_history', 'chart_catalog', 'query_inspect', 'semantic_inspect'}
READ_ONLY.add('runtime_keepalive')
TOOLS.update({
    'dataset_import': ('Import explicit JSON rows or CSV; inferred measures remain unverified', schema({**BOARD, 'expectedRevision': INT, 'datasetId': STR, 'rows': {'type':'array', 'items':{'type':'object'}}, 'csvText':STR, 'name':STR}, ('dashboardId','expectedRevision','datasetId'))),
    'legacy_render': ('Export one original component with the shared bundled UI and only its required data sources', schema(TARGET, ('dashboardId','componentId')))
})
READ_ONLY.add('legacy_render')

TOOLS.update({
    'generation_examples': ('Discover Dashboard and analytical-report generation cases; select caseId for reusable atomic declarations and the academic Markdown master. All case data is synthetic.', schema({'caseId': {'type':'string','enum':['executive-dashboard','academic-report']}})),
    'chart_declarations': ('Discover available declaration types; select an original chart/KPI code for bounded schemas and working examples. Full reference: charts://declarations.', schema({'code':STR}))
})
READ_ONLY.update({'generation_examples','chart_declarations'})

TOOLS["statistical_render"] = ("Render a declared Seaborn component as bounded SVG or PNG with raw-observation provenance", schema({**TARGET, "format": {"enum": ["svg", "png"]}}, ("dashboardId", "componentId")))
READ_ONLY.add("statistical_render")

VIEW = {**BOARD, 'filters': {'type': 'array', 'items': {'type': 'object'}}, 'tableStates': {'type': 'object'}, 'granularities': {'type': 'object'}}
TOOLS['runtime_info'] = ('Read installed UI build identity and current dashboard revision without loading view rows', schema(BOARD))
TOOLS['dashboard_refresh'] = ('Refresh the latest dashboard while preserving reader filter values and table state; never saves reader overrides', schema(VIEW, ('dashboardId',)))
READ_ONLY.update({'runtime_info', 'dashboard_refresh'})
TOOLS.update({
    'dashboard_view': ('Compute a local preview from immutable versions; returns only aggregate results and table pages, without saving reader filters', schema(VIEW, ('dashboardId',))),
    'dashboard_data_inspect': ('Inspect dataset versions, row counts, sizes and shared versions without reading full rows', schema(BOARD, ('dashboardId',))),
    'dashboard_filter_options': ('Search and page the full selection universe without reducing filter scope', schema({**BOARD, 'filterId': STR, 'search': STR, 'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 1000}}, ('dashboardId', 'filterId'))),
    'dataset_attach': ('Stream an operator-configured local SQLite table into an immutable data version; never send full data through MCP', schema({**BOARD, 'expectedRevision': INT, 'datasetId': STR, 'connection': STR, 'table': STR, 'fields': {'type': 'object'}}, ('dashboardId', 'expectedRevision', 'datasetId', 'connection', 'table'))),
    'dataset_export': ('Export every matching row to a local CSV file, streaming; returns the local path and counts, not the file content', schema({**TARGET, 'datasetId': STR, 'filters': {'type': 'array', 'items': {'type': 'object'}}, 'columns': {'type': 'array', 'items': STR}, 'sort': {'type': 'array', 'items': {'type': 'object'}}, 'search': STR}, ('dashboardId',))),
    'dashboard_migrate': ('Back up a legacy dashboard and compact all revisions to immutable local data references; preserves business revision numbers', schema({**BOARD, 'expectedRevision': INT}, ('dashboardId', 'expectedRevision'))),
    'dashboard_migration_rollback': ('Restore backed-up pre-migration content as a new revision, preserving subsequent history', schema({**BOARD, 'expectedRevision': INT, 'backupId': STR}, ('dashboardId', 'expectedRevision', 'backupId'))),
})
READ_ONLY.update({'dashboard_view', 'dashboard_data_inspect', 'dashboard_filter_options'})
TOOLS['dashboard_export'] = ('Export the current view as a local PDF or self-contained HTML, or JSON configuration with immutable local data references; never exports full detail rows', schema({**VIEW, 'format': {'enum': ['pdf', 'html', 'json']}}, ('dashboardId', 'format')))
READ_ONLY.add('dashboard_export')
TOOLS['dashboard_export_open'] = ('Open a previously generated managed export or reveal it in Finder, only after a user file-action click', schema({**BOARD, 'exportId': STR, 'format': {'enum': ['pdf', 'html', 'json']}, 'action': {'enum': ['open', 'reveal']}}, ('dashboardId', 'exportId', 'format', 'action')))
