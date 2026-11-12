"""One browser data description for online pages, history and publications."""
from __future__ import annotations

import copy
import gzip
import json
from concurrent.futures import ThreadPoolExecutor

from .model import DashboardError, require


MAX_BROWSER_BATCH_BYTES = 16 * 1024 * 1024


def browser_data(store, document, url_for, *, preload_options=False):
    doc = document
    result = {'id': doc['id'], 'revision': doc['revision'],
              'staticFiles': {}, 'staticOptions': {}, 'staticPartitionIndexes': {},
              'staticComponentDatasets': {}, 'staticDatasetFields': {}, 'staticResourceKeys': {}}
    used = {component.get('datasetId') or component.get('binding', {}).get('datasetId')
            for component in doc['manifest']['components'].values()}
    refs = {key: ref for key, ref in doc['snapshot'].get('datasetRefs', {}).items() if key in used}
    for component_id, ref in doc['snapshot'].get('componentDataRefs', {}).items():
        component = doc['manifest']['components'].get(component_id)
        if component:
            key = 'component-' + component_id
            refs[key] = ref
            result['staticComponentDatasets'][component_id] = key
            result['staticDatasetFields'][key] = ref['fields']
    versions = list(dict.fromkeys(ref['version'] for ref in refs.values()))
    with ThreadPoolExecutor(max_workers=4) as pool:
        objects = dict(zip(versions, pool.map(lambda version: store.assets.call('object_get', version=version), versions)))
    for key, ref in refs.items():
        obj = objects[ref['version']]
        require(obj is not None, 'Dataset files unavailable', 'ASSET_UNAVAILABLE')
        descriptor = obj['descriptor']
        result['staticFiles'][key] = [url_for(obj['id'], name) for name in descriptor['shards']]
        result['staticOptions'][key] = {field: url_for(obj['id'], name)
                                       for field, name in descriptor['options'].items()}
        for name in [*descriptor['shards'], *descriptor['options'].values()]:
            result['staticResourceKeys'][url_for(obj['id'], name)] = obj['id'] + '/' + name
        if descriptor.get('partitionIndex'):
            index = descriptor['partitionIndex']
            result['staticPartitionIndexes'][key] = {'field': index['field'],
                'entries': [{'value': entry['value'], 'files': [url_for(obj['id'], name) for name in entry['files']]}
                            for entry in index['entries']]}
    if preload_options:
        result['staticResourceSizes'] = {
            url_for(obj['id'], name): obj['descriptor']['files'][name]['bytes']
            for obj in objects.values()
            for name in [*obj['descriptor']['shards'], *obj['descriptor']['options'].values()]
        }
        # Only fields used by selection controls need candidate values. Shared
        # dataset versions and fields read the same immutable file once.
        selections, files = {}, {}
        for selection in doc['manifest'].get('filters', []):
            if selection['op'] != 'in':
                continue
            for component_id in selection['componentIds']:
                component = doc['manifest']['components'][component_id]
                key = (component.get('datasetId') or component.get('binding', {}).get('datasetId')
                       or result['staticComponentDatasets'].get(component_id))
                if key not in refs:
                    continue
                obj = objects[refs[key]['version']]
                name = obj['descriptor']['options'].get(selection['field'])
                require(name is not None, 'Filter option index is missing', 'ASSET_UNAVAILABLE')
                resource = (obj['id'], name)
                selections.setdefault(key, {})[selection['field']] = resource
                files[resource] = obj
        def read_options(resource):
            return json.loads(gzip.decompress(store.assets.read_file(files[resource], resource[1])))
        with ThreadPoolExecutor(max_workers=4) as pool:
            values = dict(zip(files, pool.map(read_options, files)))
        result['staticOptionValues'] = {
            key: {field: values[resource] for field, resource in fields.items()}
            for key, fields in selections.items()
        }
    return result


def web_document(store, document, url_for, editable=False, data_url=None, *, preload_options=False):
    doc = copy.deepcopy(document)
    doc['storageFormat'] = 'cos-v1'
    doc['versionKey'] = f"{doc['id']}:{doc['revision']}"
    if data_url:
        # Render saved results first; resolve data files only when a query needs them.
        doc['browserDataUrl'] = data_url
        doc['staticComponentDatasets'] = {
            key: 'component-' + key for key in doc['snapshot'].get('componentDataRefs', {})
            if key in doc['manifest']['components']}
    else:
        doc.update(browser_data(store, document, url_for, preload_options=preload_options))
    if not editable:
        for key in ('sources', 'queries', 'annotations'):
            doc['manifest'].pop(key, None)
        for artifact in doc.get('statisticalArtifacts', {}).values():
            artifact.pop('provenance', None)
    doc['snapshot']['datasets'] = {}
    doc['progressive'] = True
    return doc


def browser_version(store, board, revision, editable):
    if not editable:
        doc = store.readable(board)
        require(doc['revision'] == revision, 'Version no longer available', 'REVISION_CONFLICT')
        return doc
    doc = store.get(board, hydrate=False)
    if doc['revision'] == revision:
        return doc
    from .versions import Versions
    return Versions(store).read(board, revision)


def authorized_file(store, document, object_id, name):
    return authorized_files(store, document, [object_id + '/' + name])[object_id + '/' + name]


def authorized_files(store, document, resources, *, max_bytes=None):
    """Resolve each object once and authorize the complete batch before reading."""
    used = {component.get('datasetId') or component.get('binding', {}).get('datasetId')
            for component in document['manifest']['components'].values()}
    refs = [*(ref for key, ref in document['snapshot'].get('datasetRefs', {}).items() if key in used),
            *document['snapshot'].get('componentDataRefs', {}).values()]
    versions = {ref['version'] for ref in refs}
    selected, objects, size = {}, {}, 0
    for resource in dict.fromkeys(resources):
        object_id, name = resource.split('/', 1)
        if object_id not in objects:
            objects[object_id] = store.assets.call('object_get', id=object_id)
        obj = objects[object_id]
        if obj is None:
            raise DashboardError('FORBIDDEN', 'File is outside the selected version')
        require(obj['kind'] == 'dataset' and obj['version'] in versions,
                'File is outside the selected version', 'FORBIDDEN')
        allowed = [*obj['descriptor']['shards'], *obj['descriptor']['options'].values()]
        require(name in allowed, 'File is not a browser data resource', 'FORBIDDEN')
        if max_bytes is not None:
            size += obj['descriptor']['files'][name]['bytes']
            if size > max_bytes:
                raise DashboardError('PAYLOAD_TOO_LARGE', 'Browser file batch is too large', 413)
        selected[resource] = (obj, name)
    with ThreadPoolExecutor(max_workers=4) as pool:
        return dict(zip(selected, pool.map(lambda item: store.assets.read_file(*item), selected.values())))
