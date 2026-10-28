#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automation test suite for McKinsey-grade executive charts and dashboards.
"""
import os
import sys
import subprocess
import json
import tempfile
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "executive-charts", "scripts")


def dashboard_config(output_file):
    html = Path(output_file).read_text(encoding="utf-8")
    start_tag = '<script id="dashboard-data">'
    start = html.index(start_tag) + len(start_tag)
    config_script = html[start:html.index("</script>", start)]
    program = "const window = {};\n" + config_script + "\nconsole.log(JSON.stringify(window.DASHBOARD_CONFIG));"
    result = subprocess.run(["node", "-"], input=program, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_chart_generation(tmp_path):
    print("Testing standalone chart generation (t06)...")
    out_file = tmp_path / "chart.html"
    cmd = [
        sys.executable,
        os.path.join(SCRIPTS_DIR, "generate_chart.py"),
        "--code", "t06",
        "--title", "测试趋势图",
        "--output", out_file
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"generate_chart.py failed: {res.stderr}"
    html = out_file.read_text(encoding="utf-8")
    assert "测试趋势图" in html
    assert 'data-explain-chart="T06"' in html
    print("✓ Standalone chart test passed!")

def test_dashboard_generation(tmp_path):
    print("Testing custom dashboard composition...")
    out_file = tmp_path / "dashboard.html"
    cmd = [
        sys.executable,
        os.path.join(SCRIPTS_DIR, "generate_dashboard.py"),
        "--charts", "c01,t06,r01,fn01",
        "--title", "测试研判看板",
        "--output", out_file
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"generate_dashboard.py failed: {res.stderr}"
    config = dashboard_config(out_file)
    assert config["meta"]["title"] == "测试研判看板"
    assert [chart["code"] for chart in config["charts"]] == ["c01", "t06", "r01", "fn01"]
    print("✓ Dashboard composition test passed!")

def test_preset_generation(tmp_path):
    print("Testing retail_ecommerce preset...")
    out_file = tmp_path / "retail.html"
    cmd = [
        sys.executable,
        os.path.join(SCRIPTS_DIR, "generate_dashboard.py"),
        "--preset", "retail_ecommerce",
        "--output", out_file
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"generate_dashboard.py preset failed: {res.stderr}"
    config = dashboard_config(out_file)
    assert config["meta"]["title"] == "零售连锁集团核心运营效能与商品战略研判看板"
    assert "kpi-gmv" in [kpi["id"] for kpi in config["kpis"]]
    print("✓ Retail preset test passed!")

def test_config_generation(tmp_path):
    print("Testing custom JSON config generation...")
    cfg_file = tmp_path / "config.json"
    out_file = tmp_path / "configured.html"
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {"title": "自定义测试看板", "org": "测试部"},
            "filters": [
                {
                    "key": "month",
                    "label": "统计月份",
                    "type": "select",
                    "options": [{"value": "2026-07", "label": "2026年7月", "default": True}]
                },
                {
                    "key": "region",
                    "label": "大区",
                    "type": "multi-select",
                    "options": [{"value": "华东", "label": "华东", "default": True}, {"value": "华南", "label": "华南", "default": True}]
                }
            ],
            "charts": ["c01", "t06", "k01"]
        }, f)
    cmd = [
        sys.executable,
        os.path.join(SCRIPTS_DIR, "generate_dashboard.py"),
        "--config", cfg_file,
        "--output", out_file
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"generate_dashboard.py --config failed: {res.stderr}"
    config = dashboard_config(out_file)
    assert config["meta"]["title"] == "自定义测试看板"
    assert [item["key"] for item in config["filters"]] == ["month", "region"]
    assert [option["value"] for option in config["filters"][1]["options"]] == ["华东", "华南"]
    assert [chart["code"] for chart in config["charts"]] == ["c01", "t06", "k01"]
    print("✓ Custom JSON config test passed!")

def test_from_csv_generation(tmp_path):
    print("Testing --from-csv automated generation...")
    sample_csv = tmp_path / "sales.csv"
    out_file = tmp_path / "csv-dashboard.html"
    with open(sample_csv, "w", encoding="utf-8") as f:
        f.write('"门店","大区","销售额","同比","毛利率"\n')
        f.write('"上海旗舰店","华东","¥4,500 万","+16.2%","35.4%"\n')
        f.write('"北京国贸店","华北","¥3,800 万","+11.5%","31.8%"\n')
        f.write('"深圳湾店","华南","¥3,600 万","+8.4%","29.6%"\n')
    cmd = [
        sys.executable,
        os.path.join(SCRIPTS_DIR, "generate_dashboard.py"),
        "--from-csv", sample_csv,
        "--output", out_file
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"generate_dashboard.py --from-csv failed: {res.stderr}"
    assert os.path.exists(out_file), "Output file was not created"
    with open(out_file, "r", encoding="utf-8") as f:
        html = f.read()
        assert "上海旗舰店" in html, "Store name not in generated HTML"
        assert "民航" not in html, "Aviation mock leaked into retail CSV dashboard"
    print("✓ CSV automated generation test passed!")

def run_cli(*args):
    cmd = ["node", os.path.join(PROJECT_ROOT, "bin", "cli.js"), *args]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res


def test_generated_html_inspector_contract():
    print("Testing generated HTML inspector contract...")
    with tempfile.TemporaryDirectory(prefix="charts-design-html-inspector-") as tmp:
        valid_html = os.path.join(tmp, "valid.html")
        duplicate_html = os.path.join(tmp, "duplicate.html")
        with open(valid_html, "w", encoding="utf-8") as f:
            f.write("""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>Valid</title></head><body><main id=\"app\"></main></body></html>""")
        with open(duplicate_html, "w", encoding="utf-8") as f:
            f.write("""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>Duplicate</title></head><body><div id=\"same\"></div><div id=\"same\"></div></body></html>""")

        valid = run_cli("dashboard", "inspect-html", valid_html, "--strict", "--json")
        assert valid.returncode == 0, valid.stdout + valid.stderr
        valid_payload = json.loads(valid.stdout)
        assert valid_payload["ok"] is True
        assert valid_payload["command"] == "dashboard.inspect-html"
        assert valid_payload["summary"]["duplicateIds"] == 0

        duplicate = run_cli("dashboard", "inspect-html", duplicate_html, "--strict", "--json")
        assert duplicate.returncode != 0
        duplicate_payload = json.loads(duplicate.stdout)
        assert duplicate_payload["ok"] is False
        assert duplicate_payload["errors"] == [{
            "code": "DOM_ID_DUPLICATE",
            "path": "#same",
            "message": "DOM id must be unique: same",
        }]
    print("✓ Generated HTML inspector contract test passed!")

def test_workspace_generation():
    print("Testing composable dashboard workspace...")
    with tempfile.TemporaryDirectory(prefix="charts-design-workspace-") as tmp:
        workspace = os.path.join(tmp, "board")
        chart_file = os.path.join(tmp, "regional-sales.chart.json")
        output_file = os.path.join(tmp, "board.html")
        with open(chart_file, "w", encoding="utf-8") as f:
            json.dump({
                "id": "regional-sales",
                "code": "c01",
                "title": "各区域营业收入",
                "unit": "万元",
                "data": {"categories": ["华东", "华南"], "values": [128, 96]},
                "presentation": {
                    "axisLabels": {"x": "区域", "y": "营业收入"},
                    "seriesLabels": ["营业收入"],
                    "tooltipValueLabels": ["营业收入"],
                    "units": ["万元"],
                    "tableHeaders": ["区域", "营业收入"],
                },
            }, f, ensure_ascii=False)

        commands = [
            ("dashboard", "init", workspace, "--title", "销售经营看板", "--org", "经营分析部", "--json"),
            ("dashboard", "add", "kpi", workspace, "revenue", "--label", "营业收入", "--value", "224", "--unit", "万元", "--json"),
            ("dashboard", "add", "chart", workspace, "regional-sales", "--from", chart_file, "--json"),
            ("dashboard", "validate", workspace, "--strict", "--json"),
            ("dashboard", "build", workspace, "--output", output_file, "--json"),
        ]
        for args in commands:
            res = run_cli(*args)
            assert res.returncode == 0, f"CLI {' '.join(args)} failed: {res.stdout}\n{res.stderr}"
            payload = json.loads(res.stdout)
            assert payload["ok"] is True, payload

        inspect_res = run_cli("dashboard", "inspect", workspace, "--json")
        inspect_payload = json.loads(inspect_res.stdout)
        assert inspect_payload["summary"]["counts"] == {
            "filters": 0,
            "kpis": 1,
            "charts": 1,
            "tableRows": 0,
        }
        assert "values" not in inspect_res.stdout, "inspect should not dump chart data"
        assert os.path.exists(output_file), "Workspace build did not create HTML"
        with open(output_file, "r", encoding="utf-8") as f:
            html = f.read()
            assert "销售经营看板" in html
            assert "各区域营业收入" in html
            assert 'filters: []' in html, "Explicit zero filters should not fall back to a preset"
    print("✓ Composable workspace test passed!")


def test_workspace_filter_scope_contract():
    print("Testing explicit workspace filter scope...")
    with tempfile.TemporaryDirectory(prefix="charts-design-filter-scope-") as tmp:
        workspace = os.path.join(tmp, "board")
        assert run_cli("dashboard", "init", workspace, "--title", "Scoped board", "--json").returncode == 0
        add_filter = run_cli(
            "dashboard", "add", "filter", workspace, "region",
            "--label", "大区", "--option", "east=华东",
            "--field", "region", "--consumer", "revenue", "--consumer", "regional-sales", "--json",
        )
        assert add_filter.returncode == 0, add_filter.stdout + add_filter.stderr
        with open(os.path.join(workspace, "filters.json"), encoding="utf-8") as f:
            filters = json.load(f)
        assert filters[0]["fields"] == ["region"]
        assert filters[0]["componentIds"] == ["revenue", "regional-sales"]

        filters[0].pop("fields")
        with open(os.path.join(workspace, "filters.json"), "w", encoding="utf-8") as f:
            json.dump(filters, f, ensure_ascii=False)
        invalid = run_cli("dashboard", "validate", workspace, "--strict", "--json")
        assert invalid.returncode == 2
        assert any(error["code"] == "FILTER_FIELDS_MISSING" for error in json.loads(invalid.stdout)["errors"])
    print("✓ Explicit workspace filter scope test passed!")

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="charts-design-generation-") as tmp:
        tmp_path = Path(tmp)
        test_chart_generation(tmp_path)
        test_dashboard_generation(tmp_path)
        test_preset_generation(tmp_path)
        test_config_generation(tmp_path)
        test_from_csv_generation(tmp_path)
    test_generated_html_inspector_contract()
    test_workspace_generation()
    test_workspace_filter_scope_contract()
    print("All tests successfully completed!")
