import base64
import json
import pytest
from dashboard_runtime.transport import ResultTransport
from dashboard_runtime.model import DashboardError

def test_large_unicode_response_and_metadata_logs(tmp_path):
    transport = ResultTransport(tmp_path)
    original = {'document': {'title': '真实数据', 'rows': ['机场😀"\\\n'] * 70000}}
    manifest = transport.pack(original, 'dashboard_preview')['transport']
    parts = [transport.chunk({'requestId': manifest['requestId'], 'index': i}) for i in range(manifest['chunks'])]
    assert max(len(json.dumps(p)) for p in parts) < 25000
    restored = base64.b64decode(''.join(p['data'] for p in parts))
    assert len(restored) == manifest['bytes']
    assert json.loads(restored) == original
    logs = transport.diagnostics({'requestId': manifest['requestId']})
    assert {r['stage'] for r in logs['events']} == {'serialized', 'chunked', 'read_start', 'read_complete'}
    assert '机场' not in json.dumps(logs, ensure_ascii=False)
    with pytest.raises(DashboardError, match='expired'):
        transport.chunk({'requestId': 'missing', 'index': 0})


def test_response_survives_worker_restart_and_other_previews(tmp_path):
    producer = ResultTransport(tmp_path)
    original = {'rows': ['跨进程真实数据'] * 20000}
    manifest = producer.pack(original, 'dashboard_preview')['transport']
    for _ in range(9):
        producer.pack({'other': 'x' * 50000}, 'dashboard_view')
    consumer = ResultTransport(tmp_path)
    parts = [consumer.chunk({'requestId': manifest['requestId'], 'index': i})['data'] for i in range(manifest['chunks'])]
    assert json.loads(base64.b64decode(''.join(parts))) == original


def test_expired_response_is_logged(tmp_path):
    import sqlite3
    transport = ResultTransport(tmp_path)
    manifest = transport.pack({'data': 'x' * 50000}, 'dashboard_preview')['transport']
    with sqlite3.connect(transport.cache_path) as db:
        db.execute('UPDATE results SET expires=0')
    with pytest.raises(DashboardError, match='expired'):
        ResultTransport(tmp_path).chunk({'requestId': manifest['requestId'], 'index': 0})
    assert transport.diagnostics({'requestId': manifest['requestId']})['events'][0]['code'] == 'RESULT_EXPIRED'
