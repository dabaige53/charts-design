import importlib.util
import json
from pathlib import Path

from dashboard_runtime.legacy import import_workspace
from dashboard_runtime.model import validate

spec = importlib.util.spec_from_file_location(
    "fidelity_fixture", Path(__file__).with_name("fidelity_fixture.py")
)
assert spec is not None and spec.loader is not None
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


# @wu-test type=integration | scope=原工作区导入 | protects=导入丢失组件配置筛选信息
def test_original_workspace_import_is_lossless(tmp_path):
    doc = fixture.document()
    components = doc["manifest"]["components"]
    refs = {"charts": [], "kpis": [], "filters": "filters.json", "table": "table.json"}
    for key, c in components.items():
        if c["family"] == "table":
            (tmp_path / "table.json").write_text(json.dumps(c["config"]))
            continue
        path = key + ".json"
        (tmp_path / path).write_text(json.dumps(c["config"]))
        refs["charts" if c["family"] == "chart" else "kpis"].append(path)
    (tmp_path / "filters.json").write_text(
        '[{"id":"region","fields":["region"],"type":"multi-select","options":[]}]'
    )
    (tmp_path / "dashboard.json").write_text(
        json.dumps(
            {"schemaVersion": 1, "meta": {"title": "Original"}, "components": refs}
        )
    )
    result, _ = import_workspace(tmp_path, "imported")
    validate(result)
    for key, c in components.items():
        imported = result["manifest"]["components"].get(
            c["config"].get("id", key)
            if c["family"] != "table"
            else c["config"].get("id", "import-table")
        )
        assert imported["kind"] == "legacy" and imported["family"] == c["family"]
        assert imported["config"] == c["config"]
    assert (
        result["manifest"]["originalWorkspace"]["filters"][0]["type"] == "multi-select"
    )
    assert result["manifest"]["components"]["chart-c01"]["config"]["code"] == "c01"
