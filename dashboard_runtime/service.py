"""Transport-independent command service. Mutation arguments are always explicit."""
from __future__ import annotations
import copy
from .model import TYPES, DashboardError, compatibility, identifier, inferred_fields, require, validate
from .query import QueryRunner
from .store import Store

class Service:
    def __init__(self, root, sources_file=None):
        self.store, self.queries = Store(root), QueryRunner(sources_file)

    def call(self, tool, args):
        require(isinstance(args, dict), 'Tool arguments must be an object')
        board = args.get('dashboardId')
        if tool == 'generation_examples':
            from .generation import generation_examples
            return generation_examples(args.get('caseId'))
        if tool == 'chart_declarations':
            from .declarations import declaration_contract
            return declaration_contract(chart_type=args.get('chartType'), legacy_code=args.get('code'), summary=not (args.get('chartType') or args.get('code')))
        if tool == 'dashboard_list':
            return {'dashboards': self.store.list()}
        if tool == 'dashboard_create':
            doc = args.get('document')
            if doc is not None:
                doc = copy.deepcopy(doc)
                for source in doc.get('manifest', {}).get('sources', {}).values():
                    source['verification'] = 'supplied'
            return {'document': self.store.create(args['dashboardId'], args.get('title', 'Dashboard'), doc)}
        if tool in ('dashboard_get', 'dashboard_preview'):
            return {'document': self.store.get(board)}
        if tool == 'dashboard_validate':
            return {'valid': bool(validate(args.get('document') or self.store.get(board)))}
        if tool == 'dashboard_patch':
            ops = copy.deepcopy(args.get('operations'))
            require(isinstance(ops, list), 'operations must be an array')
            for op in ops:
                if isinstance(op, dict) and op.get('op') == 'put_source' and isinstance(op.get('value'), dict):
                    op['value']['verification'] = 'supplied'
            return {'document': self.store.mutate(board, args.get('expectedRevision'), ops)}
        if tool == 'dashboard_history':
            return {'history': self.store.history(board)}
        if tool == 'dashboard_restore':
            return {'document': self.store.mutate(board, args.get('expectedRevision'), restore_revision=args.get('revision'))}
        if tool == 'chart_catalog':
            charts = [{'type': t} for t in TYPES]
            if board and args.get('componentId'):
                doc = self.store.get(board)
                component = doc['manifest']['components'].get(args['componentId'])
                require(component is not None and component['kind'] in ('chart','legacy'), 'Chart not found')
                charts = [] if component['kind']=='legacy' else [{'type': t, 'compatible': compatibility(doc, component, t) is None,
                           'reason': compatibility(doc, component, t)} for t in TYPES]
            from .legacy import catalog
            return {'charts': charts, 'legacy': catalog(), 'originalKpis': ['mc%02d'%i for i in range(1,10)], 'policy': 'Original components are preserved without automatic conversion; use explicit config and family.'}
        if tool in ('query_inspect', 'semantic_inspect'):
            doc = self.store.get(board)
            c = doc['manifest']['components'].get(args.get('componentId'))
            require(c is not None, 'Component not found')
            meta = doc['manifest']['datasets'].get(c.get('datasetId'), {})
            source = doc['manifest']['sources'].get(meta.get('sourceId') or c.get('sourceId'))
            if tool == 'query_inspect':
                return {'source': source, 'snapshotUpdatedAt': doc['snapshot']['updatedAt'],
                        'filters': [f for f in doc['manifest']['filters'] if args['componentId'] in f['componentIds']],
                        'note': 'Interactive filters apply to the reviewed snapshot, not to a new SQL execution.'}
            return {'metrics': {key: doc['manifest']['metrics'][key] for key in c.get('measures', [])}, 'dataset': meta, 'originalPresentation': c.get('config',{}).get('presentation'), 'originalExplanation': c.get('config',{}).get('explanation'), 'certified': False}
        if tool == 'legacy_render':
            from .assets import export_component
            doc = self.store.get(board)
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
                    ops.append({'op': 'put_metric', 'id': mid, 'value': {'datasetId': ds, 'field': key, 'aggregation': 'sum', 'label': key, 'unit': '', 'definition': f'Unreviewed sum of {key}. Confirm the business meaning before use.', 'status': 'unverified'}})
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
                    operations.append({'op': 'put_metric', 'id': mid, 'value': {'datasetId': ds, 'field': key, 'aggregation': 'sum', 'label': key, 'unit': '', 'definition': f'Unreviewed sum of {key}; confirm grain and meaning.', 'status': 'unverified'}})
            return {'document': self.store.mutate(board, args['expectedRevision'], operations), 'execution': source['query']}
        raise DashboardError('UNKNOWN_TOOL', f'Unsupported tool: {tool}', 404)

def schema(properties=None, required=()):
    return {'type': 'object', 'properties': properties or {}, 'required': list(required), 'additionalProperties': False}
STR = {'type': 'string'}
INT = {'type': 'integer', 'minimum': 1}
BOARD = {'dashboardId': STR}
TARGET = {**BOARD, 'componentId': STR}
TOOLS = {
    'dashboard_list': ('List saved dashboards', schema()),
    'dashboard_create': ('Create a dashboard with an optional reviewed artifact', schema({**BOARD, 'title': STR, 'document': {'type': 'object'}}, ('dashboardId',))),
    'dashboard_get': ('Read current canonical state before editing', schema(BOARD, ('dashboardId',))),
    'dashboard_preview': ('Open an editable MCP App; non-UI hosts receive the canonical artifact', schema(BOARD, ('dashboardId',))),
    'dashboard_validate': ('Validate a stored dashboard or supplied artifact', schema({**BOARD, 'document': {'type': 'object'}})),
    'dashboard_patch': ('Apply atomic typed operations with optimistic concurrency', schema({**BOARD, 'expectedRevision': INT, 'operations': {'type': 'array', 'minItems': 1, 'maxItems': 200, 'items': {'type': 'object'}}}, ('dashboardId', 'expectedRevision', 'operations'))),
    'dashboard_history': ('List the last 100 revisions', schema(BOARD, ('dashboardId',))),
    'dashboard_restore': ('Restore a revision as a new revision; never overwrite history', schema({**BOARD, 'expectedRevision': INT, 'revision': INT}, ('dashboardId', 'expectedRevision', 'revision'))),
    'chart_catalog': ('List compatible native types and installed original chart codes', schema(TARGET)),
    'query_inspect': ('Inspect actual or supplied SQL provenance, without execution', schema(TARGET, ('dashboardId', 'componentId'))),
    'semantic_inspect': ('Inspect stored metric definitions, units and aggregation', schema(TARGET, ('dashboardId', 'componentId'))),
    'query_execute': ('Execute a bounded read-only SQLite query on a configured alias and atomically save its snapshot', schema({**BOARD, 'expectedRevision': INT, 'datasetId': STR, 'connection': STR, 'sql': STR, 'parameters': {'type': ['object', 'array']}}, ('dashboardId', 'expectedRevision', 'datasetId', 'connection', 'sql')))
}
READ_ONLY = {'dashboard_list', 'dashboard_get', 'dashboard_preview', 'dashboard_validate', 'dashboard_history', 'chart_catalog', 'query_inspect', 'semantic_inspect'}
TOOLS.update({
    'dataset_import': ('Import explicit JSON rows or CSV; inferred measures remain unverified', schema({**BOARD, 'expectedRevision': INT, 'datasetId': STR, 'rows': {'type':'array', 'items':{'type':'object'}}, 'csvText':STR, 'name':STR}, ('dashboardId','expectedRevision','datasetId'))),
    'legacy_render': ('Export one original component with the shared bundled UI and only its required data sources', schema(TARGET, ('dashboardId','componentId')))
})
READ_ONLY.add('legacy_render')

TOOLS.update({
    'generation_examples': ('Discover Dashboard and analytical-report generation cases; select caseId for reusable atomic declarations and the academic Markdown master. All case data is synthetic.', schema({'caseId': {'type':'string','enum':['executive-dashboard','academic-report']}})),
    'chart_declarations': ('Discover available declaration types; select chartType or original code for bounded schemas and working examples. Full reference: charts://declarations.', schema({'chartType': {'type':'string','enum':list(TYPES)}, 'code':STR}))
})
READ_ONLY.update({'generation_examples','chart_declarations'})
