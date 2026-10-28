"""Read-only component diagnostics keyed by design, data and installed build."""
import hashlib
import json
import time
import uuid
from .model import validate, DashboardError
from .assets import ui_build_id


def data_version(doc):
    return hashlib.sha256(json.dumps(doc['snapshot'], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def diagnose(service, board, mode='full'):
    doc = service.store.get(board, hydrate=False)
    request_id = uuid.uuid4().hex
    report = {'dashboardId': board, 'requestId': request_id, 'revision': doc['revision'], 'dataVersion': data_version(doc), 'uiBuildId': ui_build_id(), 'mode': mode, 'checks': []}
    def check(item, callback, component=None):
        start=time.perf_counter()
        try:
            callback()
            report['checks'].append({'check': item, 'componentId': component, 'status': 'passed'})
        except (DashboardError, ValueError, KeyError, OSError, sqlite3.Error) as error:
            report['checks'].append({'check': item, 'componentId': component, 'status': 'failed', 'code': getattr(error, 'code', type(error).__name__), 'message': str(error), 'action': '检查该组件绑定和项目数据文件'})
        service.transport.log(request_id, 'dashboard_doctor', item, size=0, dashboard_id=board, duration_ms=(time.perf_counter()-start)*1000, revision=doc['revision'])
    import sqlite3
    check('definition', lambda: validate(doc))
    for key, ref in doc['snapshot'].get('datasetRefs', {}).items():
        check('dataset:'+key, lambda ref=ref: service.store.data.describe(ref['version']))
    ids=list(doc['manifest']['components'])
    if mode=='quick':
        ids=[item['id'] for item in doc['manifest']['layout']['desktop'] if item.get('y',0)<8]
    for key in ids:
        def calculate(key=key):
            service.views.prepare(doc, component_ids=[key], include_filter_options=False)
            if doc['manifest']['components'][key]['kind']=='statistical':
                from .statistical import statistical_artifacts
                selected=json.loads(json.dumps(doc))
                selected['manifest']['components']={key: selected['manifest']['components'][key]}
                statistical_artifacts(service.store.statistical_document(selected))
        check('component', calculate, key)
    report['warnings']=[{'code':'ANNOTATION_ANCHOR_UNAVAILABLE','annotationId': note['id']} for note in doc['manifest'].get('annotations',[]) if note.get('componentId') and note['componentId'] not in doc['manifest']['components']]
    report['passed']=all(item['status']=='passed' for item in report['checks'])
    return report
