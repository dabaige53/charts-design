import importlib.util
import json
from pathlib import Path
import re
import pytest
from dashboard_runtime.assets import DIST
from dashboard_runtime.service import Service
spec=importlib.util.spec_from_file_location('fixture',Path(__file__).with_name('fidelity_fixture.py'))
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

@pytest.mark.skipif(not (DIST/'app.js').exists(),reason='Build the shared frontend first')
def test_mcp_original_export_uses_shared_ui_and_only_requested_component(tmp_path):
    doc=fixture.document();service=Service(tmp_path/'state');service.store.create('original-review','Review',doc)
    for key in ('c01','kpi-plf','original-table'):
        result=service.call('legacy_render',{'dashboardId':'original-review','componentId':key})
        html=result['html'];boot=json.loads(re.search(r'window.__DASHBOARD_BOOT__=(.*?);</script>',html).group(1))
        assert result['scope']=='component'
        assert set(boot['document']['manifest']['components'])=={key}
        assert '<iframe' not in html and 'cdn.jsdelivr.net/npm/' not in html
        assert 'component-header' in html and 'ui-icon' in html
