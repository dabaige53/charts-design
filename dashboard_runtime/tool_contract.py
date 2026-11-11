"""Agent-facing tool definitions shared by discovery, CLI and MCP adapters."""
from __future__ import annotations

from .declarations import common_declarations
from .statistical import statistical_schema


def schema(properties=None, required=(), **keywords):
    return {'type': 'object', 'properties': properties or {}, 'required': list(required),
            'additionalProperties': False, **keywords}


def described(value, description, **keywords):
    return {**value, 'description': description, **keywords}


STR = {'type': 'string'}
INT = {'type': 'integer', 'minimum': 1}
ID = {'type': 'string', 'pattern': '^[a-zA-Z][a-zA-Z0-9_-]{0,79}$'}
BOARD = {
    'dashboardId': described(ID, 'Stable dashboard/report ID from dashboard_list, or a new ID for dashboard_create. Scoped to projectRoot.'),
    'dataMode': described({'enum': ['snapshot', 'local']}, 'MCP defaults to local: immutable data references and bounded computed results. snapshot is for explicit legacy snapshot reads, not full-data export.'),
}
EXPECTED = described(INT, 'Latest document.revision from dashboard_get or the previous successful write in this batch. On REVISION_CONFLICT read dashboard_get and reconcile changes before retrying.')
TARGET = {**BOARD, 'componentId': described(ID, 'Existing component key from document.manifest.components, not its display title.')}
PUBLISHED = described({'type': 'boolean', 'default': False}, 'Protect this checkpoint from automatic history pruning. This is a retention marker; it does not deploy a website or create a share link.')
NAME = described(STR, 'Optional checkpoint label. A non-empty name protects the checkpoint from automatic pruning.')
common = common_declarations()
FILTER = common['filterSchema']
FILTER['description'] = 'Complete filter declaration. values=[] clears its condition; include explicit componentIds. Read existing definitions from dashboard_get.'
FILTER['properties'].update({
    'id': described(ID, 'Stable filter ID from manifest.filters, or a new ID when authoring.'),
    'label': described(STR, 'Reader-facing filter label.'),
    'field': described(STR, 'Declared dataset field shared by all target components.'),
    'op': described({'enum': ['in', 'range', 'contains']}, 'in selects values; range uses inclusive lower/upper bounds; contains searches a string field.'),
    'selectionMode': described({'enum': ['single', 'multiple'], 'default': 'multiple'}, 'single permits at most one value and requires op=in.'),
    'values': described({'type': 'array', 'items': {'type': ['string', 'number', 'boolean', 'null']}}, 'Typed values matching the field; [] clears, range needs two bounds, contains accepts at most one string.'),
    'componentIds': described({'type': 'array', 'items': ID, 'minItems': 1}, 'Explicit bound component IDs affected by this filter.'),
})
FILTERS = described({'type': 'array', 'maxItems': 30, 'items': FILTER}, 'Complete temporary filter list, replacing saved conditions for this request only; omit to use saved filters. Use values=[] to clear a condition.')
SORT = described({'type': 'array', 'items': schema({
    'field': described(STR, 'Existing dataset field key, not its display label.'),
    'direction': described({'enum': ['asc', 'desc']}, 'Ascending or descending order.'),
}, ('field', 'direction'))}, 'Ordered sort keys applied to the full matching dataset before paging/export; omit for stored order.')
SEARCH = described({'type': 'string', 'maxLength': 1000}, 'Case-insensitive substring search across this table; omit or use an empty string to disable.')
TABLE_STATE = schema({
    'page': described(INT, 'One-based page number; out-of-range pages are clamped to the final page.'),
    'pageSize': described({'enum': [10, 20, 25, 50, 100, 9999]}, 'Rows per page. Omit to use the saved/default size; 9999 is the supported large-page option.'),
    'sortCol': described(STR, 'Dataset field to sort, not its display label; omit to keep saved sorting.'),
    'sortDir': described({'enum': ['asc', 'desc']}, 'Sort direction; defaults to asc when a sort column is supplied.'),
    'keyword': SEARCH,
}, additionalProperties=True)
VIEW = {
    **BOARD, 'filters': FILTERS,
    'tableStates': described({'type': 'object', 'additionalProperties': TABLE_STATE}, 'Temporary table state keyed by component ID. Omit entries to use their saved/default state; never saves a design revision.'),
    'granularities': described({'type': 'object', 'additionalProperties': {'enum': ['month', 'quarter']}}, 'Temporary grain keyed by bound chart component ID; omit to use the saved/default grain.'),
}
ANNOTATIONS = described({'type': 'array', 'maxItems': 100, 'items': {
    'type': 'object', 'required': ['id', 'text', 'createdAt'], 'properties': {
        'id': described(ID, 'Stable annotation ID; preserve existing IDs when updating.'),
        'componentId': described({'type': ['string', 'null']}, 'Target component ID; omit or use null for page-level comments.'),
        'text': described({'type': 'string', 'minLength': 1, 'maxLength': 4000}, 'Authored comment text.'),
        'createdAt': described({'type': 'string', 'minLength': 1, 'maxLength': 100}, 'Original creation timestamp; preserve it when editing.'),
        'anchor': described({'type': 'object'}, 'Optional relative geometry/text anchor from dashboard_annotations; preserve its complete shape. See charts://contract operations.set_annotations.'),
    },
}}, 'Complete annotation list; replacing it removes omitted comments. Preserve comments unless the user requested changes.')


def operation(name, properties, required, description):
    # The runtime permits extra metadata. Describe supported shapes without
    # rejecting existing stored extensions or historical component declarations.
    return schema({'op': described({'const': name}, description), **properties},
                  ('op', *required), additionalProperties=True, description=description)


OPERATION_SCHEMAS = {
    name: operation(name, {'id': described(ID, f'Stable {label} ID; an existing ID replaces that definition.'),
                           'value': described(shape, description)}, ('id', 'value'), description)
    for name, label, shape, description in (
        ('put_source', 'source', common['sourceSchema'], 'Create or replace provenance; supplied verification is not proof of execution.'),
        ('put_metric', 'metric', common['metricSchema'], 'Create or replace a metric with explicit business definition, unit and aggregation.'),
        ('put_component', 'component', {'anyOf': [common['componentSchema'], statistical_schema(),
            {'type': 'object', 'required': ['kind', 'title', 'chartType'],
             'properties': {'kind': {'const': 'chart'}, 'title': STR, 'chartType': STR},
             'description': 'Historical chart update only: must preserve the existing kind and chartType. New kind=chart components are rejected.'}]},
         'Create or replace the complete component. Preserve existing fields; use chart_declarations(code) for preset details. New charts use kind=legacy, family=chart. KPI prose is forbidden.'),
    )
}
OPERATION_SCHEMAS.update({
    'put_dataset': operation('put_dataset', {
        'id': described(ID, 'Dataset ID; an existing ID replaces its metadata and rows.'),
        'meta': described(common['datasetMetaSchema'], 'Dataset field types and existing sourceId.'),
        'rows': described(common['rowsSchema'], 'Complete small dataset rows; replaces previous contents. Use dataset_attach for large configured SQLite tables.'),
    }, ('id', 'meta', 'rows'), 'Create or replace dataset metadata and explicit rows.'),
    'put_dataset_ref': operation('put_dataset_ref', {
        'id': described(ID, 'Dataset ID to create or replace.'),
        'meta': described(common['datasetMetaSchema'], 'Dataset metadata matching the immutable version.'),
        'ref': described({'type': 'object'}, 'Existing immutable reference returned by dataset_attach or dashboard_get; never invent a version or path.'),
    }, ('id', 'meta', 'ref'), 'Reuse an existing immutable dataset version.'),
    'remove_component': operation('remove_component', {'id': described(ID, 'Existing component ID to remove.')}, ('id',),
        'Remove the component and its layout/filter membership. Remove report chart references first in the same patch.'),
    'set_original_chart': operation('set_original_chart', {
        'id': TARGET['componentId'], 'code': described({'enum': ['c01', 'c02']}, 'Reviewed compatible preset code.'),
    }, ('id', 'code'), 'Switch between c01 and c02 while preserving data and swapping axis labels.'),
    'set_layout': operation('set_layout', {
        'breakpoint': described({'enum': ['desktop', 'tablet', 'mobile'], 'default': 'desktop'}, 'Grid has 12/8/4 columns respectively.'),
        'value': described({'type': 'array', 'items': schema({
            'id': described(ID, 'Existing component ID; include every component exactly once.'),
            **{key: described({'type': 'integer', 'minimum': 0 if key in ('x', 'y') else 1}, label)
               for key, label in (('x', 'Zero-based column.'), ('y', 'Zero-based row.'), ('w', 'Width in grid columns.'), ('h', 'Height in grid rows.'))},
        }, ('id', 'x', 'y', 'w', 'h'), additionalProperties=True)}, 'Complete placements at this breakpoint. Replaces the saved layout template.'),
    }, ('value',), 'Replace one breakpoint layout; keep valid layouts at all three breakpoints.'),
    'apply_layout_template': operation('apply_layout_template', {
        'template': described({'enum': ['executive', 'focus', 'bento', 'sidebar', 'grid3', 'narrative', 'scorecard']}, 'Template ID from layout_templates.'),
        'order': described({'type': 'array', 'items': ID}, 'Optional reading order; remaining components follow manifest order.'),
    }, ('template',), 'Apply a composition at all breakpoints after other operations; saves a template that reflows with membership.'),
})
for op_name, value_schema, meaning in (
    ('set_title', STR, 'Replace the page title.'),
    ('set_theme', {'enum': ['light', 'dark']}, 'Set legacy stored theme metadata; the current UI always renders light.'),
    ('set_filters', FILTERS, 'Replace saved filter declarations, unlike temporary dashboard_view filters.'),
    ('set_annotations', ANNOTATIONS, 'Replace the complete annotation list. Project annotations survive design restoration.'),
    ('set_meta', common['metaSchema'], 'Replace all page metadata; omitted keys are removed and {} clears it.'),
    ('set_view_mode', {'enum': ['dashboard', 'report']}, 'Choose grid or Markdown presentation; preserves existing canonical report source.'),
    ('set_report_markdown', {'type': 'string', 'maxLength': 200000}, 'Replace complete report Markdown; preserve text outside requested edits. chart fences reference existing non-text component IDs.'),
    ('set_report', {'type': 'object'}, 'Legacy whole-report replacement. Prefer set_report_markdown for new authoring; see charts://contract.'),
    ('set_status', {'enum': ['ready', 'partial', 'blocked', 'fixture']}, 'Set saved data status; fixture labels explicitly synthetic data.'),
    ('set_data_mode', {'enum': ['local', 'snapshot']}, 'Set stored data mode; local uses immutable data versions.'),
):
    OPERATION_SCHEMAS[op_name] = operation(op_name, {'value': described(value_schema, meaning)}, ('value',), meaning)

OPERATIONS = described({'type': 'array', 'minItems': 1, 'maxItems': 200,
                        'items': {'oneOf': list(OPERATION_SCHEMAS.values())}},
    'Atomic ordered operations. Read charts://contract for the complete operation guide and chart_declarations for component details. All references must resolve at the end; remove report fences before removing their components.')

READ_ONLY = {
    'runtime_keepalive', 'dashboard_list', 'dashboard_annotations', 'dashboard_get',
    'dashboard_preview', 'dashboard_validate', 'dashboard_history', 'chart_catalog',
    'component_data', 'query_inspect', 'semantic_inspect', 'legacy_render',
    'generation_examples', 'chart_declarations', 'layout_templates', 'chart_recommend',
    'statistical_render', 'runtime_info', 'dashboard_refresh', 'dashboard_view',
    'dashboard_data_inspect', 'dashboard_filter_options', 'runtime_result_chunk',
    'runtime_diagnostics', 'dashboard_export_read', 'dashboard_doctor', 'dashboard_history_diff',
    'dashboard_share_status',
    'dashboard_version_status', 'dashboard_version_get',
}
APP_ONLY = {'runtime_keepalive', 'runtime_report_error', 'dashboard_export_open'}
DESTRUCTIVE = {
    'dashboard_patch', 'dashboard_restore', 'dataset_import', 'dataset_attach',
    'query_execute', 'dashboard_migrate', 'dashboard_migration_rollback',
    'dashboard_checkpoint', 'dashboard_edit_finish', 'dashboard_version_label',
    'dashboard_share_revoke',
    'dashboard_share_delete',
    'dashboard_share_replace',
    'dashboard_version_publish',
}


def tool_annotations(name):
    return {'readOnlyHint': name in READ_ONLY, 'destructiveHint': name in DESTRUCTIVE,
            'idempotentHint': name in READ_ONLY and name != 'runtime_keepalive', 'openWorldHint': False}


WRITE_FLOW = ' In project mode this saves a draft: finish the edit batch before previewing. On REVISION_CONFLICT read dashboard_get, reconcile, and use its latest revision.'
TOOLS = {
    'dashboard_share_status': ('List this dashboard’s Tencent publication jobs, or inspect one shareId, without returning visitor keys. '
        'Returns shares with revision/expiry/state/cleanupState. Use after an uncertain publish response before retrying. '
        'pending means cloud deletion is due or retrying, not complete; successfully cleaned jobs disappear. '
        'An empty result means no matching job remains and is not a host-rendering acceptance check.', schema({
        **BOARD, 'shareId': described({'type': 'string', 'pattern': '^[0-9a-f]{32}$'},
            'Optional shareId from dashboard_share_publish; omit to list this dashboard’s publications.'),
    }, ('dashboardId',))),
    'dashboard_share_publish': ('Publish a separate read-only static copy to configured private Tencent COS storage behind the HTTPS cloud gateway. '
        'Project mode requires the current formal publication at expectedRevision: save with dashboard_checkpoint, then dashboard_version_publish. Also requires cloud credentials and a deployed SCF cleanup timer. '
        'Returns shareId/url/accessUrl/accessKey/expiresAt (UTC Unix seconds, null for never). accessUrl carries the eight-digit key in a #key fragment for automatic form filling; give this link only to intended readers, or send url and accessKey separately. '
        'expiration defaults to 7d; never means no automatic expiry. At expiry the gateway rejects access immediately and cloud SCF deletes the copy, historical object versions and key records. '
        'Does not delete the source project or other shares. Does not deploy cloud infrastructure. On an uncertain response call dashboard_share_status before publishing another copy.', schema({
        **BOARD, 'expectedRevision': described(INT, 'Current publishedRevision from dashboard_version_status; drafts may be newer without changing this share.'),
        'expiration': described({'enum': ['never', '7d', '30d'], 'default': '7d'},
            'Lifetime from publication: never, seven days, or thirty days. Choose the period requested by the user.'),
        'accessKey': described({'type': 'string', 'pattern': '^[0-9]{8}$'},
            'Optional exactly eight ASCII digits, including leading zeros. Omit to generate a random key. Only a salted hash is stored remotely.'),
    }, ('dashboardId', 'expectedRevision'))),
    'dashboard_share_replace': ('Replace one selected share with the current formally published version. Creates a new URL and random eight-digit key, then revokes the old link and its sessions; other shares stay unchanged. Upload failure leaves the old share usable. Returns new share credentials and previousRevoked. If previousRevoked=false, retain the returned new credentials and retry dashboard_share_delete for previousShareId; do not republish. Cloud SCF physically removes the old copy.', schema({
        **BOARD, 'shareId': described({'type': 'string', 'pattern': '^[0-9a-f]{32}$'}, 'Active share to replace; obtain from dashboard_share_status.'),
        'expectedRevision': described(INT, 'Current publishedRevision from dashboard_version_status.'),
        'expiration': described({'enum': ['never', '7d', '30d'], 'default': '7d'}, 'New share lifetime measured from replacement.'),
    }, ('dashboardId', 'shareId', 'expectedRevision'))),
    'dashboard_share_delete': ('Revoke one Tencent cloud publication immediately and queue physical deletion by cloud SCF, including never-expiring shares. '
        'Returns revoked=true, cleanupState=pending and cleanupExecutor=tencent-scf; pending is not proof of completed deletion. '
        'Deletes only this publication copy and its access records; preserves the source project and other shares. '
        'Use shareId from dashboard_share_publish, not a signed browser-link token.', schema({
        **BOARD, 'shareId': described({'type': 'string', 'pattern': '^[0-9a-f]{32}$'},
            'Exact shareId returned by dashboard_share_publish for this project and dashboard.'),
    }, ('dashboardId', 'shareId'))),
    'runtime_keepalive': ('App only: renew the runtime lifetime while the preview is visible; stop when hidden. Returns ok; agents must not poll it.', schema()),
    'dashboard_list': ('List saved dashboards/reports in this project; returns IDs, titles and draft revisions. No cross-project discovery. Choose an ID, then dashboard_get before editing.', schema()),
    'dashboard_create': ('Create an empty dashboard/report container, or import a complete reviewed schema-v2 document. Requires an explicit project or startup project default; inserts no demo data. Returns document and revision. For reports use set_view_mode and set_report_markdown in an edit batch.', schema({
        **BOARD, 'title': described(STR, 'Title for an empty dashboard; defaults to Dashboard. A supplied document carries its own title.'),
        'document': described({'type': 'object'}, 'Optional complete schema-v2 artifact, not a patch. Omit to create an empty dashboard; get shape guidance from charts://contract and chart_declarations.'),
    }, ('dashboardId',))),
    'dashboard_annotations': ('Read saved comments, original selection anchors and target identities without chart rows; returns revision, annotations and targets. Missing targets have componentExists=false. Before acting read dashboard_get; preserve comments unless asked to change them. Verify ambiguous visual anchors in the rendered page.', schema({'dashboardId': BOARD['dashboardId']} , ('dashboardId',))),
    'dashboard_get': ('Read the current editable draft and revision, including annotations and immutable data references. This may be newer than the checkpoint shown by dashboard_preview. Read before writing; use document.revision as expectedRevision. Returns document; use dashboard_view for computed data.', schema(BOARD, ('dashboardId',))),
    'dashboard_preview': ('Open the saved dashboard/report in the MCP App; project mode shows the latest completed checkpoint, not unfinished draft edits. Call once after a successful dashboard_edit_finish, using the same project and dashboard. Returns document and a UI resource when built; UI_UNAVAILABLE requires building/packaging UI resources.', schema(BOARD, ('dashboardId',))),
    'dashboard_validate': ('Validate schema and references of either a complete supplied document or a stored draft; does not run full component calculations or create a checkpoint. Supply document or dashboardId. Returns valid=true; failures return errors. Use dashboard_doctor for data/calculation checks.', schema({
        **BOARD, 'document': described({'type': 'object'}, 'Complete proposed schema-v2 document to validate without saving; omit to validate dashboardId.'),
    }, anyOf=[{'required': ['dashboardId']}, {'required': ['document']}])),
    'dashboard_patch': ('Apply 1-200 atomic operations to the latest draft. Begin with dashboard_get and dashboard_edit_begin; preserve unmodified definitions and stable IDs. Returns updated document and semanticChanges; replacement operations remove omitted content. Read charts://contract for operations.' + WRITE_FLOW, schema({
        **BOARD, 'expectedRevision': EXPECTED, 'operations': OPERATIONS,
        'expectedAnnotations': described(ANNOTATIONS, 'Project-only independent comment save: provide the exact annotation list read earlier and use only set_annotations operations. Conflicts fail; successful independent saves do not increment the design revision.'),
    }, ('dashboardId', 'expectedRevision', 'operations'))),
    'dashboard_history': ('Read retained design checkpoints, newest first; project mode pages with offset/limit (default 50, maximum 100 per page). Legacy storage returns its retained history without paging. Draft edits are not checkpoints. Returns history; choose revisions for diff or restore.', schema({
        **BOARD, 'offset': described({'type': 'integer', 'minimum': 0, 'default': 0}, 'Zero-based checkpoint offset, project mode only.'),
        'limit': described({'type': 'integer', 'minimum': 1, 'maximum': 100, 'default': 50}, 'Maximum checkpoints per page, project mode only. A full page may require another call.'),
    }, ('dashboardId',))),
    'dashboard_restore': ('Restore a retained checkpoint as a new draft revision; preserves history, project annotations and the current formal publication. By default restores its data references too. Returns the draft; inspect and save with dashboard_checkpoint before dashboard_preview. Does not restore deleted/pruned checkpoints.' , schema({
        **BOARD, 'expectedRevision': EXPECTED,
        'revision': described(INT, 'Retained checkpoint revision from dashboard_history, not the current draft revision.'),
        'useCurrentData': described({'type': 'boolean', 'default': False}, 'Project mode only: retain current data snapshot instead of historical data; restored definitions must remain compatible.'),
    }, ('dashboardId', 'expectedRevision', 'revision'))),
    'chart_catalog': ('Discover installed chart/KPI/table codes and binding capabilities without creating content. Returns charts, originalKpis and kpiGuide. Choose by the business question, then chart_declarations(code). Optional target fields are compatibility-only and do not narrow the catalog.', schema(TARGET)),
    'component_data': ('Read paged underlying rows for one dataset-bound component under temporary/saved filters. Returns rows and totalRows, not chart aggregates. Applies search/sort before paging. Use dashboard_view for aggregate results or dataset_export for all matching rows.', schema({
        **TARGET, 'expectedRevision': EXPECTED, 'filters': FILTERS, 'sort': SORT, 'search': SEARCH,
        'offset': described({'type': 'integer', 'minimum': 0, 'default': 0}, 'Zero-based matching-row offset.'),
        'limit': described({'type': 'integer', 'minimum': 1, 'maximum': 1000, 'default': 1000}, 'Maximum rows in this response; advance offset to read more.'),
    }, ('dashboardId', 'componentId'))),
    'query_inspect': ('Inspect component source/query provenance and local data reference without executing upstream SQL. Returns source, filters and snapshot time; supplied provenance is not certified execution. Use semantic_inspect for metric definitions.', schema(TARGET, ('dashboardId', 'componentId'))),
    'semantic_inspect': ('Read the actual component metric definitions, units, aggregation and dataset metadata. Returns metrics and provenance-related presentation; certified=false is not approval. Do not replace unknown business definitions with guessed semantics.', schema(TARGET, ('dashboardId', 'componentId'))),
    'query_execute': ('Execute bounded read-only SQLite SQL through an operator-configured connection alias, then replace the destination dataset snapshot and provenance. The query is read-only but saving changes the dashboard. Returns document and execution metadata; inferred numeric metrics remain unverified.' + WRITE_FLOW, schema({
        **BOARD, 'expectedRevision': EXPECTED,
        'datasetId': described(ID, 'Destination dataset ID; an existing ID replaces its saved data and affects all bound components.'),
        'connection': described(STR, 'Operator-configured source alias, not a path or URL. Obtain it from project configuration; do not guess aliases.'),
        'sql': described(STR, 'Single bounded read-only SQLite query against the configured source; never DDL or writes.'),
        'parameters': described({'type': ['object', 'array']}, 'Named or positional SQL parameters matching the query; omit when none.'),
    }, ('dashboardId', 'expectedRevision', 'datasetId', 'connection', 'sql'))),
    'dataset_import': ('Import a small explicit JSON row array or CSV text; provide exactly one input. Replaces the destination dataset. Returns document and semanticChanges; inferred numeric fields create unverified sum metrics, which need business review.' + WRITE_FLOW, schema({
        **BOARD, 'expectedRevision': EXPECTED,
        'datasetId': described(ID, 'Destination dataset ID; an existing ID replaces its metadata and complete row set.'),
        'rows': described({'type': 'array', 'minItems': 1, 'items': {'type': 'object'}}, 'Non-empty explicit row objects with field keys and typed JSON values; do not also provide csvText.'),
        'csvText': described(STR, 'CSV contents including a header and data rows, not a file path. Numeric-looking cells are inferred as numbers; use JSON strings to preserve numeric identifiers. Do not also provide rows.'),
        'name': described(STR, 'Source display name; defaults to datasetId.'),
    }, ('dashboardId', 'expectedRevision', 'datasetId'), oneOf=[
        {'required': ['rows'], 'not': {'required': ['csvText']}},
        {'required': ['csvText'], 'not': {'required': ['rows']}},
    ])),
    'legacy_render': ('Return standalone HTML for one existing kind=legacy component using the shared renderer; read-only, does not open the App or create a full-dashboard export. Returns html, scope and componentId. Use dashboard_preview for the saved page.', schema(TARGET, ('dashboardId', 'componentId'))),
    'generation_examples': ('Read explicitly synthetic dashboard/report examples and reusable atomic operations without creating data. Omit caseId for the index; choose a case for detail. Adapt composition and metric definitions to the user request; examples are optional aids.', schema({
        'caseId': described({'enum': ['executive-dashboard', 'operations-scorecard', 'academic-report']}, 'Example ID from the index; omission returns discovery information.'),
    })),
    'chart_declarations': ('Discover authoring schemas and working examples. Omit code for a compact index; provide a preset chart or KPI code from chart_catalog for its definition. Full common schemas: charts://declarations. Does not write data; validate final declarations before completing the edit.', schema({
        'code': described(STR, 'Installed chart or KPI code from chart_catalog (for example c01 or mc03); omit for the index.'),
    })),
    'layout_templates': ('Read seven optional composition templates and application guidance without editing. Choose by the business question; apply via dashboard_patch op=apply_layout_template, or use explicit set_layout at every breakpoint. Returns template IDs and layout rules.', schema()),
    'chart_recommend': ('Optionally rank installed chart codes for a business question and data shape; returns binding capabilities and KPI guidance, without editing. Existing dashboard context down-ranks used codes. Inspect chart_declarations for the selected code before authoring.', schema({
        'intent': described({'enum': ['comparison', 'ranking', 'trend', 'composition', 'distribution', 'relationship', 'flow', 'change', 'attribution', 'target', 'forecast']}, 'Business comparison or analysis intent, chosen from the user question.'),
        'categories': described(INT, 'Number of categories in the intended chart, if known.'),
        'measures': described(INT, 'Number of numeric measures to compare, if known.'),
        'hasTime': described({'type': 'boolean'}, 'Whether a real time dimension exists in the supplied data.'),
        'dashboardId': BOARD['dashboardId'],
        'datasetId': described(ID, 'Optional existing dataset in the supplied dashboard context.'),
    }, ('intent',))),
    'statistical_render': ('Render one declared statistical component from raw observations as SVG or PNG; returns bounded artifact and provenance without changing the saved definition. Requires optional statistics dependencies; no interactive filtering. Use chart_declarations/resources for declaration guidance.', schema({
        **TARGET, 'format': described({'enum': ['svg', 'png'], 'default': 'svg'}, 'Output image format; SVG is the default.'),
    }, ('dashboardId', 'componentId'))),
    'runtime_info': ('Read installed backend/UI build identities and project/runtime metadata without chart rows. Optional dashboardId returns the displayed checkpoint revision in project mode, not necessarily the editable draft. Use dashboard_get before edits; build identity does not establish host rendering acceptance.', schema(BOARD)),
    'dashboard_refresh': ('Reload the latest displayed checkpoint while retaining supplied reader filter values, table state and chart grain; never saves them or reruns source SQL. Returns document. Use dashboard_get for the editable draft and dashboard_view for component calculations.', schema({
        **VIEW, 'filters': described({'type': 'array', 'items': {**FILTER, 'required': ['id', 'values']}},
            'Reader value overrides keyed by existing filter id: only id and values are required. Omitted filters retain saved values and current definitions. A runtime-linkage entry must carry its complete declaration.'),
    }, ('dashboardId',))),
    'dashboard_view': ('Compute temporary local chart aggregates and table pages from immutable data versions; does not save filters or rerun source SQL. full returns document; patch returns only selected computed components. On REVISION_CONFLICT reload and reconcile. For reading use the preview/checkpoint revision; for draft inspection use dashboard_get revision.', schema({
        **VIEW, 'expectedRevision': EXPECTED,
        'responseMode': described({'enum': ['full', 'patch'], 'default': 'full'}, 'patch limits computation and response to componentIds; full returns the document and all computed results.'),
        'componentIds': described({'type': 'array', 'items': ID}, 'patch mode only: omit for all, [] for none, or list visible component IDs.'),
        'includeFilterOptions': described({'type': 'boolean', 'default': False}, 'patch mode only: include filter options when they need reloading; otherwise use dashboard_filter_options.'),
        'dataVersion': described(STR, 'Data version from the same document as expectedRevision; mismatch requires reloading.'),
        'filterSequence': described({'type': 'integer', 'minimum': 0}, 'Optional caller-side filter generation; the caller must discard stale results.'),
        'compactRecords': described({'type': 'boolean', 'default': False}, 'Opt into compact field/row wire records; only use when the caller supports decoding them.'),
    }, ('dashboardId',))),
    'dashboard_data_inspect': ('Read immutable dataset references, row counts, shared versions and file/config sizes without full rows. Returns datasets and sharedVersions; use this to check imports before computing views. Does not verify metric business definitions.', schema(BOARD, ('dashboardId',))),
    'dashboard_filter_options': ('Search/page all candidate values of a declared filter; does not narrow candidates by current reader conditions or save a selection. Returns values and paging metadata. Read every page before claiming all values are selected.', schema({
        **BOARD, 'filterId': described(ID, 'Existing manifest.filters ID, not its field name or display label.'),
        'search': described(STR, 'Candidate-label search; omit or empty to read all candidates.'),
        'offset': described({'type': 'integer', 'minimum': 0, 'default': 0}, 'Zero-based candidate offset.'),
        'limit': described({'type': 'integer', 'minimum': 1, 'maximum': 1000, 'default': 100}, 'Maximum candidate values in one response.'),
    }, ('dashboardId', 'filterId'))),
    'dataset_attach': ('Stream a configured local SQLite table into an immutable data version without sending all rows through MCP. Replaces the destination dataset reference. Returns document and import counts; inspect before authoring shared metrics.' + WRITE_FLOW, schema({
        **BOARD, 'expectedRevision': EXPECTED,
        'datasetId': described(ID, 'Destination dataset ID; replacing it affects all components bound to it.'),
        'connection': described(STR, 'Operator-configured read-only SQLite source alias; obtain from project configuration, not an arbitrary path.'),
        'table': described(STR, 'Existing table name in that source, supplied by the operator/project.'),
        'fields': described(common['datasetMetaSchema']['properties']['fields'], 'Optional field metadata keyed by source column; preserve known types and labels. Omit for inference.'),
    }, ('dashboardId', 'expectedRevision', 'datasetId', 'connection', 'table'))),
    'dataset_export': ('Create a managed CSV of all matching dataset/table rows with supplied filters, search, columns and sort; table grouping follows its presentation. Does not change the dashboard. Returns export ID/path/counts, not file contents. Download via dashboard_export_read (format=csv); remote MCP also returns downloadUrl.', schema({
        **TARGET, 'datasetId': described(ID, 'Existing dataset ID when componentId is omitted; componentId takes precedence when supplied.'),
        'filters': FILTERS, 'columns': described({'type': 'array', 'items': STR}, 'Ordered dataset field keys to export; omit for default/all configured columns.'),
        'sort': SORT, 'search': SEARCH,
    }, ('dashboardId',), anyOf=[{'required': ['datasetId']}, {'required': ['componentId']}])),
    'dashboard_migrate': ('Back up a legacy snapshot dashboard and rewrite its retained revisions to immutable local references, preserving revision numbers. Returns document and migration backup ID. Inspect first; use dashboard_migration_rollback with that backup to recover. This differs from project-directory migration.', schema({
        **BOARD, 'expectedRevision': EXPECTED,
    }, ('dashboardId', 'expectedRevision'))),
    'dashboard_migration_rollback': ('Restore a managed pre-migration backup as a new revision; does not erase subsequent history. Returns restored document. Obtain backupId from dashboard_migrate; inspect data references and revision after recovery.', schema({
        **BOARD, 'expectedRevision': EXPECTED,
        'backupId': described(STR, 'Managed backup ID returned by dashboard_migrate, not a filesystem path.'),
    }, ('dashboardId', 'expectedRevision', 'backupId'))),
    'dashboard_export': ('Create a managed JSON configuration export or HTML snapshot of the current computed draft view, including supplied temporary reader state. Does not complete/publish an edit. Returns export ID/path; use dashboard_export_read to download. HTML is a view snapshot; dataset_export provides full matching CSV rows.', schema({
        **VIEW, 'format': described({'enum': ['html', 'json']}, 'json preserves canonical configuration/data references; html captures the computed view and is not a live data connection.'),
    }, ('dashboardId', 'format'))),
    'runtime_result_chunk': ('Read one base64 page when a tool result returns transport.encoding=base64-json-v1. Use the same projectRoot and requestId, read all zero-based pages, concatenate in index order, then decode once as UTF-8 JSON and verify transport.bytes. Returns data; RESULT_EXPIRED requires repeating the original read or inspecting current state before retrying a write.', schema({
        'requestId': described(STR, 'transport.requestId from the original result in this same project.'),
        'index': described({'type': 'integer', 'minimum': 0}, 'Zero-based page index less than transport.chunks.'),
    }, ('requestId', 'index'))),
    'runtime_diagnostics': ('Read metadata-only request/transport logs without business rows, arguments or credentials. Returns events newest first; use requestId from a failed/result call and the same projectRoot. Does not establish successful host rendering.', schema({
        'requestId': described(STR, 'Optional request ID to isolate one operation.'),
        'dashboardId': BOARD['dashboardId'],
        'stage': described(STR, 'Optional exact logged phase such as query_complete or serialized.'),
        'code': described(STR, 'Optional exact error/client event code.'),
        'limit': described({'type': 'integer', 'minimum': 1, 'maximum': 100, 'default': 30}, 'Maximum recent matching events to return.'),
    })),
    'runtime_report_error': ('App only: record a client decode/render failure or completion timing event without response contents. Returns ok; agents should read runtime_diagnostics instead of fabricating client events.', schema({
        'requestId': described({'type': 'string', 'maxLength': 64}, 'Related request ID, if available.'),
        'code': described({'enum': ['CLIENT_DECODE_FAILED', 'CHUNK_MISMATCH', 'RESULT_EXPIRED', 'CLIENT_RENDER_FAILED', 'CLIENT_DATA_APPLIED', 'CLIENT_DECODE_COMPLETE', 'CLIENT_FRAME_READY']}, 'Observed client failure or completion event; never infer a rendered frame from a server response.'),
        'dashboardId': BOARD['dashboardId'],
        'revision': described(INT, 'Document revision observed by the client.'),
        'durationMs': described({'type': 'number', 'minimum': 0, 'maximum': 3600000}, 'Measured client duration in milliseconds, if available.'),
    }, ('code',))),
    'dashboard_export_open': ('App only: open or reveal a previously generated managed export after an explicit user file-action click. Does not generate an export. Returns file-action result; remote MCP hides this tool. Agents should return/download the export instead of launching desktop actions.', schema({
        **BOARD, 'exportId': described(STR, 'Managed export.id from a successful export result.'),
        'format': described({'enum': ['html', 'json', 'csv', 'zip']}, 'Format of that existing export.'),
        'action': described({'enum': ['open', 'reveal']}, 'User-selected desktop action: launch the file or reveal it in Finder.'),
    }, ('dashboardId', 'exportId', 'format', 'action'))),
    'dashboard_export_read': ('Read bytes from a previously generated managed export for download, without opening desktop apps. Returns a bounded base64 chunk with offset/size metadata; read to completion in order. Not the JSON-response runtime_result_chunk protocol.', schema({
        **BOARD, 'exportId': described(STR, 'Managed export.id returned by the export call in the same project/dashboard.'),
        'format': described({'enum': ['html', 'json', 'csv', 'zip']}, 'Existing export format; zip for dashboard_export_site.'),
        'offset': described({'type': 'integer', 'minimum': 0, 'default': 0}, 'Zero-based byte offset in the file, not a chunk index.'),
        'limit': described({'type': 'integer', 'minimum': 1, 'maximum': 262144, 'default': 262144}, 'Maximum bytes in this chunk.'),
    }, ('dashboardId', 'exportId', 'format'))),
    'dashboard_doctor': ('Check current draft definitions, immutable data references and component calculations. full checks every component; quick computes only desktop components whose top row is below 8. Returns passed and detailed issues; does not create a checkpoint. A failed check needs correction before dashboard_edit_finish.', schema({
        **BOARD, 'mode': described({'enum': ['quick', 'full'], 'default': 'full'}, 'Both check definitions/data; quick computes the first desktop rows (y<8), full computes every component.'),
    }, ('dashboardId',))),
    'dashboard_edit_begin': ('Project mode: begin/resume one edit batch at the latest draft revision. Read dashboard_get first. Returns batch_id for dashboard_edit_finish; patch/import operations save draft revisions until finish. Legacy storage returns PROJECT_REQUIRED.', schema({
        **BOARD, 'expectedRevision': EXPECTED,
    }, ('dashboardId', 'expectedRevision'))),
    'dashboard_edit_finish': ('Project mode: run full Doctor checks, then save one checkpoint and close the edit batch. Returns ok, checkpoint, doctor and nextAction=dashboard_preview on success. DOCTOR_FAILED preserves the draft and batch; fix the reported issues and retry with latest revision. Only preview after success; may prune old unprotected checkpoints.', schema({
        **BOARD, 'expectedRevision': EXPECTED,
        'batchId': described(STR, 'Exact batch_id returned by dashboard_edit_begin for this dashboard.'),
        'name': NAME, 'published': PUBLISHED,
    }, ('dashboardId', 'expectedRevision', 'batchId'))),
    'dashboard_checkpoint': ('Project mode: explicitly check and checkpoint the current draft without supplying a batch ID; also closes any active batch. Prefer dashboard_edit_finish for normal Agent editing. Returns ok/checkpoint/doctor or DOCTOR_FAILED; may prune old unprotected checkpoints. published is retention protection, not website publishing.', schema({
        **BOARD, 'expectedRevision': EXPECTED, 'name': NAME, 'published': PUBLISHED,
    }, ('dashboardId', 'expectedRevision'))),
    'dashboard_history_diff': ('Project mode: compare two retained design checkpoints, not unsaved draft revisions. Returns the changes between them without restoring or editing. Choose fromRevision/toRevision from dashboard_history.', schema({
        **BOARD, 'fromRevision': described(INT, 'Earlier comparison checkpoint from dashboard_history.'),
        'toRevision': described(INT, 'Other retained checkpoint from dashboard_history.'),
    }, ('dashboardId', 'fromRevision', 'toRevision'))),
    'dashboard_version_status': ('Read the draft revision, latest saved revision, current published revision and release timeline. Publishing is separate from saving a checkpoint and from updating a remote share. Use before publishing or inspecting version state.', schema(BOARD, ('dashboardId',))),
    'dashboard_version_get': ('Read one saved or previously published version without changing the draft or publication. Returns version, including immutable dataset references; use for historical inspection.', schema({
        **BOARD, 'revision': described(INT, 'Saved revision from dashboard_history or a release revision from dashboard_version_status.'),
    }, ('dashboardId', 'revision'))),
    'dashboard_version_publish': ('Make one saved version the current formal publication and append a release record. Requires the latest draft expectedRevision to reject stale actions. Repeating the current publication does not append a duplicate. Preserves the draft and existing independent shares; explicitly create or update a share afterward.', schema({
        **BOARD, 'expectedRevision': EXPECTED,
        'revision': described(INT, 'Saved revision to publish; may be an older version for a release rollback.'),
    }, ('dashboardId', 'expectedRevision', 'revision'))),
    'dashboard_version_label': ('Project mode: replace the label/retention marker of an existing checkpoint without a new design revision. Returns revision/name/published; requires a non-empty name or published=true. This does not share or deploy the page.', schema({
        **BOARD, 'expectedRevision': EXPECTED,
        'revision': described(INT, 'Existing checkpoint from dashboard_history to label.'),
        'name': NAME, 'published': PUBLISHED,
    }, ('dashboardId', 'expectedRevision', 'revision'))),
    'dashboard_export_site': ('Create a managed ZIP containing an independent static React site and used immutable dataset shards. Project mode exports the latest completed checkpoint; legacy storage exports the current document. Does not deploy, share or complete an edit batch. Returns export metadata; download with dashboard_export_read(format=zip). Static sites have no live backend.', schema(BOARD, ('dashboardId',))),
}
