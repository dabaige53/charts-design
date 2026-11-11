"""Compact MCP write receipts; the shared Service keeps its document results."""

DOCUMENT_WRITES = frozenset({
    'dashboard_create', 'dashboard_patch', 'dashboard_restore',
    'dataset_import', 'dataset_attach', 'query_execute',
    'dashboard_migrate', 'dashboard_migration_rollback',
})

WRITE_RESPONSE_HELP = (
    ' MCP defaults to a summary without document: dashboardId, revision, affectedComponentIds, '
    'counts and operation metadata. Use top-level revision for the next expectedRevision. '
    'Request responseMode=full or dashboard_get when the document is needed. '
    'Write success does not replace edit-finish validation.'
)


def write_response_schema(name, schema):
    if name not in DOCUMENT_WRITES:
        return schema
    return {**schema, 'properties': {**schema.get('properties', {}), 'responseMode': {
        'type': 'string', 'enum': ['summary', 'full'], 'default': 'summary',
        'description': 'summary returns a compact write receipt; full retains the complete document for editors. MCP only.',
    }}}


def write_receipt(name, args, result):
    """Preserve operation metadata, including warnings and migration recovery IDs."""
    if name not in DOCUMENT_WRITES or 'document' not in result or result.get('ok') is False:
        return result
    doc = result['document']
    manifest = doc['manifest']
    components = manifest['components']
    if name == 'dashboard_patch':
        affected = set()
        for operation in args.get('operations', []):
            if operation['op'] in ('put_component', 'remove_component', 'set_original_chart'):
                affected.add(operation['id'])
            elif operation['op'] in ('put_metric', 'put_dataset', 'put_dataset_ref',
                                     'set_filters', 'set_layout', 'apply_layout_template'):
                # These shared definitions can affect multiple components.
                affected.update(components)
    elif name in ('dataset_import', 'dataset_attach', 'query_execute'):
        affected = {key for key, component in components.items()
                    if component.get('datasetId') == args['datasetId']
                    or component.get('binding', {}).get('datasetId') == args['datasetId']}
    else:
        affected = set(components)
    return {
        **{key: value for key, value in result.items() if key not in ('document', 'statisticalArtifacts')},
        'ok': True,
        'dashboardId': doc['id'],
        'revision': doc['revision'],
        'affectedComponentIds': sorted(affected),
        'counts': {key: len(manifest.get(key, {})) for key in ('components', 'datasets', 'metrics')},
        'readTool': 'dashboard_get',
    }
