"""Transport-independent command service. Mutation arguments are always explicit."""
from __future__ import annotations
import copy
import os
from pathlib import Path
import time
from typing import Any
from .model import DashboardError, apply_operations, identifier, inferred_fields, json_bytes, require, validate
from .query import QueryRunner
from .store import Store
from .declarations import declaration_contract
from .local_view import LocalView
from .build import BACKEND_BUILD_ID, MODULE_ROOT
from .tool_contract import READ_ONLY as READ_ONLY, TOOLS as TOOLS

class Service:
    project_name: str

    def __init__(self, root, sources_file=None, project_root=None):
        from .project import ProjectStore
        from .cloud_database import cloud_enabled
        if cloud_enabled():
            from .cloud_project import CloudProjectStore
            require(project_root is not None, 'Cloud storage requires a named project', 'PROJECT_REQUIRED')
            self.store: Any = CloudProjectStore(project_root, root)
        else:
            self.store = ProjectStore(project_root, root) if project_root else Store(root)
        self.queries = QueryRunner(sources_file)
        self.project_root = project_root
        self.doctor_reports = {}
        self.views = LocalView(self.store.data)
        from .transport import ResultTransport
        self.transport = ResultTransport(getattr(self.store, "runtime_root", self.store.root))

    def call(self, tool, args):
        import uuid
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        try:
            result = self._execute(tool, args)
            if tool in ('dashboard_view', 'dashboard_filter_options'):
                result['requestId'] = request_id
                if args.get('compactRecords'):
                    from .wire import compact_records
                    compact_records(result)
                self.transport.log(request_id, tool, 'query_complete', dashboard_id=args.get('dashboardId'), duration_ms=(time.perf_counter()-started)*1000, revision=result.get('revision'), cache_hits=result.get('computed', {}).get('cacheHits'))
            return result
        except (DashboardError, ValueError, KeyError, OSError) as error:
            if isinstance(error, DashboardError):
                setattr(error, 'request_id', request_id)
            self.transport.log(request_id, tool, 'failed', getattr(error, 'code', type(error).__name__), dashboard_id=args.get('dashboardId'), duration_ms=(time.perf_counter()-started)*1000)
            raise

    def _execute(self, tool, args):
        started = time.perf_counter()
        result = self._call(tool, args)
        from .cloud_database import cloud_enabled
        if cloud_enabled() and isinstance(result.get('export'), dict):
            from .cloud_files import CloudFiles
            files = CloudFiles()
            assert self.project_root is not None
            project = Path(self.project_root).resolve()
            for key in ('path', 'siteArchive'):
                if isinstance(result['export'].get(key), str):
                    target = Path(result['export'][key]).resolve()
                    require(target.is_relative_to(project), 'Export must remain in its project', 'INVALID_PATH')
                    files.save(project.name, target.relative_to(project).as_posix(), target)
        if "document" in result and self.project_root and tool != "dashboard_view":
            from .doctor import data_version
            doc = result['document']
            doc['dataVersion'] = data_version(doc)
            doc['loading'] = self.store.config['loading']
            doc['progressive'] = True
            doc['computed'] = {'components': {}, 'tables': {}, 'grouped': {}, 'filterOptions': {}, 'filterPages': {}}
            if tool in ('dashboard_preview', 'dashboard_refresh', 'dashboard_get'):
                preload=set(doc['loading'].get('preloadFilterIds', []))
                for f in doc['manifest']['filters']:
                    if f['id'] in preload and f['op']=='in':
                        import hashlib
                        import json
                        refs=doc['snapshot'].get('datasetRefs', {})
                        definition=[f['field'], sorted({refs[doc['manifest']['components'][cid]['datasetId']]['version'] for cid in f['componentIds'] if doc['manifest']['components'][cid].get('datasetId') in refs})]
                        cache_key=hashlib.sha256(json_bytes(definition)).hexdigest()
                        cache_dir=self.transport.path.parent/'filter-options'
                        cache_dir.mkdir(exist_ok=True)
                        cache_file=cache_dir/(cache_key+'.json')
                        try:
                            page=json.loads(cache_file.read_text())
                        except (FileNotFoundError, json.JSONDecodeError):
                            page=self.views.filter_options(doc,f['id'],limit=100)
                            import uuid
                            temporary=cache_dir/(cache_key+'.'+uuid.uuid4().hex+'.tmp')
                            temporary.write_text(json.dumps(page,ensure_ascii=False))
                            temporary.replace(cache_file)
                        doc['computed']['filterPages'][f['id']]=page
                        doc['computed']['filterOptions'][f['id']]=page['values']
            return result
        if "document" in result:
            from .statistical import statistical_artifacts
            doc = result['document']
            if tool in ('dashboard_preview', 'dashboard_view', 'dashboard_refresh', 'dashboard_migration_rollback') or args.get('dataMode') == 'local' or doc['snapshot'].get('localMode') or doc['snapshot'].get('datasetRefs'):
                doc = self.store.compact(doc)
                tables, grains = args.get('tableStates'), args.get('granularities')
                if tool == 'dashboard_refresh':
                    components = doc['manifest']['components']
                    tables = {key: value for key, value in (tables or {}).items() if key in components}
                    grains = {key: value for key, value in (grains or {}).items() if key in components}
                doc = self.views.prepare(doc, None if tool == 'dashboard_refresh' else args.get('filters'), tables, grains)
                result['document'] = doc
            result["statisticalArtifacts"] = statistical_artifacts(self.store.statistical_document(doc))
            if doc.get('computed'):
                doc['computed']['totalDurationMs'] = (time.perf_counter()-started)*1000
        if 'computed' in result:
            result['computed']['totalDurationMs'] = (time.perf_counter()-started)*1000
        return result

    def _call(self, tool, args):
        require(isinstance(args, dict), 'Tool arguments must be an object')
        if tool == 'runtime_keepalive':
            return {'ok': True}
        if tool == 'runtime_result_chunk':
            return self.transport.chunk(args)
        if tool == 'runtime_diagnostics':
            return self.transport.diagnostics(args)
        if tool == 'runtime_report_error':
            request_id = args.get('requestId', '')
            code = args.get('code', 'CLIENT_DECODE_FAILED')
            require(isinstance(request_id, str) and len(request_id) <= 64, 'Invalid request ID')
            require(code in ('CLIENT_DECODE_FAILED', 'CHUNK_MISMATCH', 'RESULT_EXPIRED','CLIENT_RENDER_FAILED','CLIENT_DATA_APPLIED','CLIENT_DECODE_COMPLETE','CLIENT_FRAME_READY'), 'Invalid diagnostic code')
            duration = args.get('durationMs')
            require(duration is None or (type(duration) in (int, float) and 0 <= duration <= 3600000), 'Invalid duration')
            self.transport.log(request_id, 'preview', 'client', code, dashboard_id=args.get('dashboardId'), revision=args.get('revision'), duration_ms=duration)
            return {'ok': True}
        board = args.get('dashboardId')
        if tool in ('dashboard_share_publish', 'dashboard_share_delete', 'dashboard_share_status', 'dashboard_share_replace'):
            from .cloud_shares import CloudShares
            shares = CloudShares.from_environment()
            from qcloud_cos.cos_exception import CosClientError, CosServiceError
            try:
                if tool == 'dashboard_share_publish':
                    return shares.publish(self, board, args['expectedRevision'],
                                          args.get('expiration', '7d'), args.get('accessKey'), args.get('pages'))
                if tool == 'dashboard_share_replace':
                    return shares.replace(self, board, args['shareId'], args['expectedRevision'],
                                          args.get('expiration', '7d'))
                if tool == 'dashboard_share_status':
                    return shares.status(self, board, args.get('shareId'))
                return shares.revoke(self, board, args.get('shareId'))
            except (CosClientError, CosServiceError) as error:
                raise DashboardError('CLOUD_STORAGE_FAILED',
                    'Tencent COS request failed. Check cloud service permissions and dashboard_share_status before retrying a publish.',
                    503) from error
        if tool in ('dashboard_version_status', 'dashboard_version_get', 'dashboard_version_publish'):
            require(self.project_root is not None, 'Project required', 'PROJECT_REQUIRED')
            from .versions import Versions
            versions = Versions(self.store)
            if tool == 'dashboard_version_status':
                return versions.status(board)
            if tool == 'dashboard_version_get':
                return {'version': versions.read(board, args['revision'])}
            return versions.publish(board, args['expectedRevision'], args['revision'])
        if tool == 'dashboard_version_label':
            require(self.project_root is not None, 'Project required', 'PROJECT_REQUIRED')
            return self.store.label_checkpoint(board,args['expectedRevision'],args['revision'],args.get('name',''),args.get('published',False))
        if tool == 'dashboard_doctor':
            from .doctor import diagnose
            report = diagnose(self, board, args.get('mode', 'full'))
            self.doctor_reports[board] = report
            from .project import write_json
            write_json(self.transport.path.parent / 'doctor' / (board+'.json'), report)
            return report
        if tool in ('dashboard_edit_begin', 'dashboard_edit_finish', 'dashboard_checkpoint', 'dashboard_history_diff'):
            require(self.project_root is not None, 'Migrate this dashboard to a project first', 'PROJECT_REQUIRED')
            if tool == 'dashboard_edit_begin':
                return self.store.begin(board, args['expectedRevision'])
            if tool == 'dashboard_history_diff':
                return self.store.diff(board, args['fromRevision'], args['toRevision'])
            report = self._call('dashboard_doctor', {'dashboardId': board, 'mode': 'full'})
            if not report['passed']:
                return {'ok': False, 'error': {'code': 'DOCTOR_FAILED',
                        'message': 'Draft checks failed; no checkpoint was created. Read dashboard_get, fix the reported issues, then retry with the latest revision.'},
                        'doctor': report, 'nextAction': 'dashboard_get'}
            from .semantic_diff import semantic_diff
            changes = semantic_diff(self.store.readable(board), self.store.get(board, hydrate=False))
            checkpoint = self.store.checkpoint(board, args['expectedRevision'], args.get('name', ''), args.get('published', False), args.get('batchId'))
            return {'ok': True, 'checkpoint': checkpoint, 'doctor': report, 'semanticChanges': changes, 'nextAction': 'dashboard_preview', 'displayPolicy': 'saved-dashboard-ui'}
        if tool == 'runtime_info':
            from .assets import ui_build_id
            from . import __version__
            return {'version': __version__, 'uiBuildId': ui_build_id(), 'backendBuildId': BACKEND_BUILD_ID, 'moduleRoot': MODULE_ROOT,
                    'processId': os.getpid(), 'parentProcessId': os.getppid(),
                    'projectRoot': str(Path(self.project_root).resolve()) if self.project_root else None,
                    'runtimeRoot': str(Path(getattr(self.store, 'runtime_root', self.store.root)).resolve()),
                    'dashboardRevision': (self.store.display_revision(board) if self.project_root else self.store.revision(board)) if board else None}
        if tool == 'dashboard_refresh':
            doc = self.store.readable(board) if self.project_root else self.store.get(board, hydrate=False)
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
                for item in incoming:
                    if item.get('id') == 'runtime-linkage':
                        item = copy.deepcopy(item)
                        item['componentIds'] = [key for key in item.get('componentIds', []) if key in doc['manifest']['components']]
                        if item['componentIds']:
                            doc['manifest']['filters'].append(item)
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
        if tool == 'layout_templates':
            from .layouts import templates_catalog
            return templates_catalog()
        if tool == 'chart_recommend':
            from .recommend import recommend_charts
            doc = self.store.get(board, hydrate=False) if board else None
            return recommend_charts({key: value for key, value in args.items() if key not in ('dashboardId', 'dataMode')}, doc)
        if tool == 'dashboard_list':
            return {'dashboards': self.store.list()}
        if tool == 'dashboard_export_open':
            from .exports import open_export
            return open_export(self.store.root, board, args.get('exportId'), args.get('format'), args.get('action'))
        if tool == 'dashboard_export_read':
            from .exports import read_export
            return read_export(self.store.root, board, args.get('exportId'), args.get('format'), args.get('offset', 0), args.get('limit', 262144))
        if tool == 'dashboard_export_site':
            from .deployment import export_site
            return export_site(self.store, board)
        if tool == 'dashboard_export':
            from .exports import export_dashboard
            doc = self.store.compact(self.store.get(board, hydrate=False))
            view = self.views.prepare(doc, args.get('filters'), args.get('tableStates'), args.get('granularities'))
            if args.get('format') == 'html':
                from .statistical import statistical_artifacts
                view['statisticalArtifacts'] = statistical_artifacts(self.store.statistical_document(view))
            return export_dashboard(self.store.root, view, args.get('format'), self.store.data)
        if tool == 'dashboard_view':
            doc = self.store.get(board, hydrate=False)
            if self.project_root and args.get('expectedRevision') != doc['revision'] and args.get('expectedRevision') == self.store.display_revision(board):
                doc = self.store.readable(board)
            from .doctor import data_version
            require(args.get('dataVersion', data_version(doc)) == data_version(doc), 'Data version changed; reload', 'REVISION_CONFLICT')
            if args.get('expectedRevision', doc['revision']) != doc['revision']:
                raise DashboardError('REVISION_CONFLICT', 'Data changed; reload the dashboard', 409)
            require(args.get('responseMode', 'full') in ('full', 'patch'), 'Invalid response mode')
            if args.get('responseMode') == 'patch':
                ids = args.get('componentIds', list(doc['manifest']['components']))
                require(isinstance(ids, list) and all(isinstance(k, str) for k in ids), 'componentIds must be an array of strings')
                require(type(args.get('includeFilterOptions', False)) is bool, 'includeFilterOptions must be boolean')
                ids = list(dict.fromkeys(ids))
                if self.project_root:
                    states = args.setdefault('tableStates', {})
                    for key in ids:
                        states.setdefault(key, {'pageSize': self.store.config['loading']['pageSize']})
                doc = self.views.prepare(self.store.compact(doc), args.get('filters'), args.get('tableStates'), args.get('granularities'), ids, args.get('includeFilterOptions', False))
                statistical = [key for key in ids if doc['manifest']['components'][key].get('kind') == 'statistical']
                artifacts = {}
                if statistical:
                    from .statistical import statistical_artifacts
                    selected_doc = copy.deepcopy(doc)
                    selected_doc['manifest']['components'] = {key: doc['manifest']['components'][key] for key in statistical}
                    artifacts = statistical_artifacts(self.store.statistical_document(selected_doc))
                result = {'id': doc['id'], 'revision': doc['revision'], 'componentIds': ids, 'computed': doc['computed'], 'statisticalArtifacts': artifacts}
                result['computed']['responseBytes'] = len(json_bytes(result))
                return result
            return {'document': doc}
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
            search = args.get('search', '')
            require(isinstance(search, str) and len(search) <= 1000, 'Table search must contain at most 1000 characters')
            return self.store.data.rows(ref, active, sort=args.get('sort'), search=search, offset=offset, limit=limit)
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
            export_id = uuid.uuid4().hex
            directory = export_dir / export_id
            directory.mkdir(mode=0o700)
            path = directory / (str(board) + '.csv')
            presentation = {**component.get('presentation', {}), **component.get('config', {})} if component else {}
            columns = args.get('columns')
            if presentation.get('groupBy') and columns is None:
                columns = [col['key'] for col in presentation['columns']]
            result = self.store.data.export_csv(ref, path, active, columns, args.get('sort'), search=args.get('search', ''), group_by=presentation.get('groupBy'), sum_fields=presentation.get('sumFields'), calculated=presentation.get('calculatedColumns'))
            return {'export': {**result, 'id': export_id, 'filename': path.name, 'format': 'csv', 'mimeType': 'text/csv'}}
        if tool == 'dashboard_create':
            if args.get('document'):
                require(not any(c.get('kind') == 'chart' for c in args['document'].get('manifest', {}).get('components', {}).values()), 'Use kind=legacy, family=chart with a preset code or config.renderer=echarts/html', 'UNSUPPORTED_CHART_FAMILY')
            doc = args.get('document')
            if doc is not None:
                doc = copy.deepcopy(doc)
                for source in doc.get('manifest', {}).get('sources', {}).values():
                    source['verification'] = 'supplied'
            return {'document': self.store.create(args['dashboardId'], args.get('title', 'Dashboard'), doc)}
        if tool == 'dashboard_annotations':
            doc = self.store.get(board, hydrate=False)
            manifest = doc['manifest']
            notes = copy.deepcopy(manifest.get('annotations', []))
            targets = {}
            for note in notes:
                component_id = note.get('componentId')
                anchor = note.get('anchor', {})
                target = {'scope': anchor.get('scope', 'component' if component_id else 'page')}
                if component_id:
                    component = manifest['components'].get(component_id)
                    target.update({'componentExists': component is not None,
                                   'sourcePath': 'manifest.components.' + component_id})
                    if component is not None:
                        target.update({'title': component.get('title', ''), 'kind': component['kind']})
                else:
                    target['sourcePath'] = 'manifest.report.markdown' if manifest.get('viewMode') == 'report' else 'manifest'
                targets[note['id']] = target
            return {'dashboardId': doc['id'], 'title': manifest['title'], 'revision': doc['revision'],
                    'annotations': notes, 'targets': targets, 'count': len(notes),
                    'independentSave': self.project_root is not None}
        if tool == 'dashboard_preview':
            from .assets import require_preview
            require_preview()
            return {'document': self.store.readable(board) if self.project_root else self.store.get(board, hydrate=False)}
        if tool == 'dashboard_get':
            return {'document': self.store.get(board, hydrate=args.get('dataMode') != 'local')}
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
                    require(old.get('kind') == 'chart' and old.get('chartType') == op['value'].get('chartType'), 'Use kind=legacy, family=chart with a preset code or config.renderer=echarts/html for custom charts', 'UNSUPPORTED_CHART_FAMILY')
                if isinstance(op, dict) and op.get('op') == 'put_source' and isinstance(op.get('value'), dict):
                    op['value']['verification'] = 'supplied'
            note_options = {}
            if 'expectedAnnotations' in args:
                require(self.project_root is not None, 'Independent annotation saves require a project', 'PROJECT_REQUIRED')
                require(isinstance(args['expectedAnnotations'], list), 'expectedAnnotations must be an array')
                note_options['expected_annotations'] = args['expectedAnnotations']
            updated = self.store.mutate(board, args.get('expectedRevision'), ops, **note_options)
            from .semantic_diff import semantic_diff
            return {'document': updated, 'semanticChanges': semantic_diff(current, updated)}
        if tool == 'dashboard_history':
            return {'history': self.store.history(board, args.get('offset', 0), args.get('limit', 50)) if self.project_root else self.store.history(board)}
        if tool == 'dashboard_restore':
            return {'document': self.store.mutate(board, args.get('expectedRevision'), restore_revision=args.get('revision'), **({'use_current_data': args.get('useCurrentData', False)} if self.project_root else {}))}
        if tool == 'chart_catalog':
            reference = declaration_contract(summary=True)
            charts = [{'code': code} for code in reference['legacy']['chartCodes']]
            from .legacy import catalog
            from .statistical import statistical_declarations
            from .kpi_cards import PATTERNS, kpi_guide
            kpis = sorted(reference['legacy']['kpiTypes'])
            return {'statistical': statistical_declarations(), 'charts': charts, 'legacy': catalog(), 'originalKpis': kpis,
                    'kpiGuide': kpi_guide(kpis), 'kpiPatterns': PATTERNS,
                    'policy': 'Original components are preserved without automatic conversion; use explicit config and family.'}
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
            require(('rows' in args) != ('csvText' in args),
                    'Supply exactly one of rows or csvText', 'INVALID_ARGUMENT')
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
            updated = self.store.mutate(board, args.get('expectedRevision'), ops)
            from .semantic_diff import semantic_diff
            return {'document': updated, 'semanticChanges': semantic_diff(doc, updated)}
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
