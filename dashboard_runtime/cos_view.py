"""One browser data description for online pages, history and publications."""
from __future__ import annotations

import copy

from .model import DashboardError, require


def web_document(store, document, url_for, editable=False):
    doc = copy.deepcopy(document)
    doc['staticFiles'], doc['staticOptions'], doc['staticPartitionIndexes'] = {}, {}, {}
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
        obj = store.assets.call('object_get', version=ref['version'])
        require(obj is not None, 'Dataset files unavailable', 'ASSET_UNAVAILABLE')
        descriptor = obj['descriptor']
        doc['staticFiles'][key] = [url_for(obj['id'], name) for name in descriptor['shards']]
        doc['staticOptions'][key] = {field: url_for(obj['id'], name)
                                    for field, name in descriptor['options'].items()}
        if descriptor.get('partitionIndex'):
            index = descriptor['partitionIndex']
            doc['staticPartitionIndexes'][key] = {'field': index['field'],
                'entries': [{'value': entry['value'], 'files': [url_for(obj['id'], name) for name in entry['files']]}
                            for entry in index['entries']]}
    if not editable:
        for key in ('sources', 'queries', 'annotations'):
            doc['manifest'].pop(key, None)
        for artifact in doc.get('statisticalArtifacts', {}).values():
            artifact.pop('provenance', None)
    doc['snapshot']['datasets'] = {}
    doc['progressive'] = True
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
    allowed = [*obj['descriptor']['shards'], *obj['descriptor']['options'].values()]
    require(name in allowed, 'File is not a browser data resource', 'FORBIDDEN')
    return store.assets.read_file(obj, name)
