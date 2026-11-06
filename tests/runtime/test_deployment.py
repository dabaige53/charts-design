import json
from dashboard_runtime.service import Service
from dashboard_runtime.demo import executive_document
from pathlib import Path


# @wu-test type=integration | scope=静态部署包 | protects=部署缺数据构建文件或泄露查询参数
def test_site_is_independent_and_keeps_all_used_rows(tmp_path):
    s=Service(tmp_path/'runtime',project_root=tmp_path/'project')
    s.call('dashboard_create',{'dashboardId':'demo','document':executive_document('demo')})
    result=s.call('dashboard_export_site',{'dashboardId':'demo'})['export']
    base=Path(result['directory']);site=Path(result['publishDirectory'])
    doc=json.loads((site/'document.json').read_text())['document']
    assert 'datasetRefs' not in doc['snapshot']
    assert 'computed' not in doc
    assert not doc['manifest']['annotations']
    for key,files in doc['staticFiles'].items():
        assert sum(len(json.loads((site/path).read_text())) for path in files)==result['datasetRows'][key]
    assert (base/'source/runtime-ui/generated/original-engine.mjs').exists()
    assert (base/'package-lock.json').exists()
    assert (base/'source/runtime-ui/report-markdown.mjs').exists()
    assert Path(result['path']).exists()
    assert all('sql' not in source and 'parameters' not in source for source in doc['manifest']['sources'].values())
