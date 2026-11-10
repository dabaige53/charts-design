"""Exercise workspace assets and the retired HTML build command."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).parents[1]
WORKSPACE = ROOT / "skills" / "executive-charts" / "scripts" / "dashboard_workspace.py"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-B", str(WORKSPACE), *(str(value) for value in args)],
        capture_output=True, text=True, cwd=ROOT,
    )


# @wu-test type=integration | scope=Workspace资产管理 | protects=移除生成器后无法保存或校验业务组件
def test_workspace_asset_commands(tmp_path):
    workspace = tmp_path / "board"
    chart = ROOT / "skills" / "executive-charts" / "references" / "quickstart" / "regional-sales.chart.json"
    table = ROOT / "skills" / "executive-charts" / "references" / "quickstart" / "sales.table.json"
    commands = [
        ("init", workspace, "--title", "销售经营看板", "--json"),
        ("add", "kpi", workspace, "revenue", "--label", "营业收入", "--value", "224", "--unit", "万元", "--json"),
        ("add", "chart", workspace, "regional-sales", "--from", chart, "--json"),
        ("table", "set", workspace, "--from", table, "--json"),
        ("meta", "set", workspace, "--org", "经营分析部", "--json"),
        ("validate", workspace, "--strict", "--json"),
    ]
    for arguments in commands:
        result = run_cli(*arguments)
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)["ok"] is True
    result = run_cli("inspect", workspace, "--json")
    payload = json.loads(result.stdout)
    assert payload["summary"]["counts"] == {"filters": 0, "kpis": 1, "charts": 1, "tableRows": 2}
    assert payload["summary"]["org"] == "经营分析部"
    assert "values" not in result.stdout
    saved_chart = json.loads((workspace / "charts" / "regional-sales.json").read_text())
    assert saved_chart["data"] == json.loads(chart.read_text())["data"]


# @wu-test type=integration | scope=Workspace筛选配置 | protects=筛选范围未保存或缺字段未报错
def test_workspace_filter_scope_contract(tmp_path):
    workspace = tmp_path / "board"
    assert run_cli("init", workspace, "--json").returncode == 0
    result = run_cli(
        "add", "filter", workspace, "region", "--label", "大区", "--option", "east=华东",
        "--field", "region", "--consumer", "revenue", "--consumer", "regional-sales", "--json",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    path = workspace / "filters.json"
    filters = json.loads(path.read_text())
    assert filters[0]["fields"] == ["region"]
    assert filters[0]["componentIds"] == ["revenue", "regional-sales"]
    filters[0].pop("fields")
    path.write_text(json.dumps(filters), encoding="utf-8")
    invalid = run_cli("validate", workspace, "--strict", "--json")
    assert invalid.returncode == 2
    assert any(error["code"] == "FILTER_FIELDS_MISSING" for error in json.loads(invalid.stdout)["errors"])


# @wu-test type=boundary | scope=Workspace旧build命令 | protects=移除生成器后构建误报成功或覆盖旧交付文件
@pytest.mark.parametrize("json_mode", [False, True])
def test_removed_build_reports_explicit_error_without_writing(tmp_path, json_mode):
    output = tmp_path / "board.html"
    output.write_text("Existing delivery", encoding="utf-8")
    arguments = ["build", tmp_path / "board", "--output", output]
    if json_mode:
        arguments.append("--json")
    result = run_cli(*arguments)
    assert result.returncode == 2
    if json_mode:
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert payload["command"] == "dashboard.build"
        assert payload["errors"][0]["code"] == "HTML_GENERATOR_REMOVED"
    else:
        assert "HTML_GENERATOR_REMOVED" in result.stderr
    assert output.read_text() == "Existing delivery"


# @wu-test type=integration | scope=CSV导入 | protects=移除渲染代码后原始单元格数值或单位丢失
def test_csv_import_preserves_source_data_without_generating_components(tmp_path):
    source = tmp_path / "sales.csv"
    source.write_text(
        '\ufeff门店,区域,销售额(万元),同比\n上海店,华东,128,+5%\n深圳店,华南,0,-2%\n',
        encoding="utf-8",
    )
    workspace = tmp_path / "board"
    result = run_cli("import-csv", workspace, "--csv", source, "--title", "销售看板", "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["summary"]["counts"] == {"filters": 2, "kpis": 0, "charts": 0, "tableRows": 2}
    table = json.loads((workspace / "table.json").read_text())
    assert table["columns"][2]["unit"] == "万元"
    assert table["rows"][0] == {
        "col_0": "上海店", "col_1": "华东", "col_2": "128", "rawCol_2": 128,
        "col_3": "+5%", "rawCol_3": 5,
    }
    assert table["rows"][1]["col_2"] == "0"
    assert table["rows"][1]["rawCol_2"] == 0
    assert table["rows"][1]["rawCol_3"] == -2
    manifest = json.loads((workspace / "dashboard.json").read_text())
    assert manifest["draft"]["csvProfile"]["suggestedChartCount"] == 4
    assert not list(workspace.rglob("*.html"))
