"""One browser data description for online pages, history and publications."""
from __future__ import annotations

import copy

from .model import DashboardError, live_datasets, require


def web_document(store, document, url_for, editable=False, *, dataset_asset=None, show_sql=False):
    doc = copy.deepcopy(document)
    if not editable:
        sources = doc['manifest'].pop('sources', {})
        if show_sql:
            doc['manifest']['sources'] = {
                key: {'query': {'sql': source['query']['sql']}}
                for key, source in sources.items() if source.get('kind') == 'query'
            }
        for key in ('queries', 'annotations'):
            doc['manifest'].pop(key, None)
        for artifact in doc.get('statisticalArtifacts', {}).values():
            artifact.pop('provenance', None)
    doc['progressive'] = True
    if live_datasets(doc):
        return doc
    doc['staticFiles'], doc['staticOptions'], doc['staticPartitionIndexes'] = {}, {}, {}
    pages = doc.get('computed', {}).get('filterPages', {})
    doc['staticFilterOptions'] = {
        key: page['values'] for key, page in pages.items() if not page.get('hasMore') and not page.get('offset')
    }
    doc['storageFormat'] = 'cos-v1'
    doc['versionKey'] = f"{doc['id']}:{doc['revision']}"
    doc['staticComponentDatasets'], doc['staticDatasetFields'] = {}, {}
    used = {component.get('datasetId') or component.get('binding', {}).get('datasetId')
            for component in doc['manifest']['components'].values()}
    refs = {key: ref for key, ref in doc['snapshot'].get('datasetRefs', {}).items() if key in used}
    for component_id, ref in doc['snapshot'].get('componentDataRefs', {}).items():
        component = doc['manifest']['components'].get(component_id)
        if component:
            key = 'component-' + component_id
            refs[key] = ref
            doc['staticComponentDatasets'][component_id] = key
            doc['staticDatasetFields'][key] = ref['fields']
    for key, ref in refs.items():
        obj = (dataset_asset(ref) if dataset_asset else
               store.assets.call('object_get', version=ref['version']))
        require(obj is not None, 'Dataset files unavailable', 'ASSET_UNAVAILABLE')
        descriptor = obj['descriptor']
        doc['staticFiles'][key] = [url_for(obj['id'], name) for name in descriptor['shards']]
        doc['staticOptions'][key] = {
            field: (url_for(obj['id'], entry) if isinstance(entry, str) else
                    {'field': entry['field'], 'files': [url_for(obj['id'], name) for name in entry['files']]})
            for field, entry in descriptor['options'].items()
        }
        if descriptor.get('partitionIndex'):
            index = descriptor['partitionIndex']
            doc['staticPartitionIndexes'][key] = {'field': index['field'],
                'entries': [{'value': entry['value'], 'files': [url_for(obj['id'], name) for name in entry['files']]}
                            for entry in index['entries']]}
    doc['snapshot']['datasets'] = {}
    return doc


def authorized_file(store, document, object_id, name):
    used = {component.get('datasetId') or component.get('binding', {}).get('datasetId')
            for component in document['manifest']['components'].values()}
    refs = [*(ref for key, ref in document['snapshot'].get('datasetRefs', {}).items() if key in used),
            *document['snapshot'].get('componentDataRefs', {}).values()]
    obj = store.assets.call('object_get', id=object_id)
    if obj is None:
        raise DashboardError('FORBIDDEN', 'File is outside the selected version')
    require(obj['kind'] == 'dataset'
            and any(ref['version'] == obj['version'] for ref in refs),
            'File is outside the selected version', 'FORBIDDEN')
    allowed = [*obj['descriptor']['shards'],
               *(name for entry in obj['descriptor']['options'].values()
                 for name in ([entry] if isinstance(entry, str) else entry['files']))]
    require(name in allowed, 'File is not a browser data resource', 'FORBIDDEN')
    return store.assets.read_file(obj, name)
