"""Asset reuse must not hide a new build from an already-running server."""
import hashlib
import os
from pathlib import Path

import pytest

from dashboard_runtime import assets
from dashboard_runtime.demo import document
from dashboard_runtime.model import DashboardError
from dashboard_runtime.service import Service


def test_asset_reads_are_reused_and_rebuilds_invalidate(tmp_path, monkeypatch):
    monkeypatch.setattr(assets, 'DIST', tmp_path)
    js, css = tmp_path / 'app.js', tmp_path / 'app.css'
    js.write_text('first </script>')
    css.write_text('body{}')
    reads = []
    original = Path.read_bytes

    def read(path):
        reads.append(path.name)
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', read)
    before = assets.ui_build_id()
    for _ in range(3):
        html = assets.render_html()
        assert '<\\/script>' in html
        assert assets.ui_build_id() == before
    assert reads == ['app.js', 'app.css']
    stamp = js.stat()
    js.write_text('other </script>')  # Same size and restored mtime must still invalidate.
    os.utime(js, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert assets.ui_build_id() != before
    assert 'other <\\/script>' in assets.render_html()
    css.write_text('body{color:red}')
    assert assets.ui_build_id() == hashlib.sha256(b'other </script>body{color:red}').hexdigest()[:12]
    assert 'body{color:red}' in assets.render_html()
    js.unlink()
    with pytest.raises(DashboardError, match='Build the UI first'):
        assets.render_html()
    js.write_text('rebuilt')
    assert 'rebuilt' in assets.render_html()


def test_runtime_info_reads_revision_without_loading_document(tmp_path, monkeypatch):
    service = Service(tmp_path)
    service.store.create('demo', 'Demo', document())
    monkeypatch.setattr(service.store, 'get', lambda *a, **k: pytest.fail('Revision check loaded the document'))
    assert service.call('runtime_info', {'dashboardId': 'demo'})['dashboardRevision'] == 1
    service.store.mutate('demo', 1, [{'op': 'set_title', 'value': 'Renamed'}])
    assert service.call('runtime_info', {'dashboardId': 'demo'})['dashboardRevision'] == 2
    assert service.store.list() == [{'id': 'demo', 'revision': 2, 'title': 'Renamed'}]
    with pytest.raises(DashboardError, match='Dashboard not found'):
        service.call('runtime_info', {'dashboardId': 'missing'})
