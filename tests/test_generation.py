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

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "executive-charts", "scripts")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "tests", "test_output")

def test_chart_generation():
    print("Testing standalone chart generation (t06)...")
    out_file = os.path.join(OUTPUT_DIR, "test_chart_t06.html")
    cmd = [
        sys.executable,
        os.path.join(SCRIPTS_DIR, "generate_chart.py"),
        "--code", "t06",
        "--output", out_file
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"generate_chart.py failed: {res.stderr}"
    assert os.path.exists(out_file), "Output file was not created"
    print("✓ Standalone chart test passed!")

def test_dashboard_generation():
    print("Testing custom dashboard composition...")
    out_file = os.path.join(OUTPUT_DIR, "test_dashboard_custom.html")
    cmd = [
        sys.executable,
        os.path.join(SCRIPTS_DIR, "generate_dashboard.py"),
        "--charts", "c01,t06,r01,fn01",
        "--title", "测试研判看板",
        "--output", out_file
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"generate_dashboard.py failed: {res.stderr}"
    assert os.path.exists(out_file), "Output file was not created"
    print("✓ Dashboard composition test passed!")

def test_preset_generation():
    print("Testing retail_ecommerce preset...")
    out_file = os.path.join(OUTPUT_DIR, "test_retail_preset.html")
    cmd = [
        sys.executable,
        os.path.join(SCRIPTS_DIR, "generate_dashboard.py"),
        "--preset", "retail_ecommerce",
        "--output", out_file
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"generate_dashboard.py preset failed: {res.stderr}"
    assert os.path.exists(out_file), "Output file was not created"
    print("✓ Retail preset test passed!")

def test_config_generation():
    import json
    print("Testing custom JSON config generation...")
    cfg_file = os.path.join(OUTPUT_DIR, "sample_cfg.json")
    out_file = os.path.join(OUTPUT_DIR, "test_config_dashboard.html")
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
    assert os.path.exists(out_file), "Output file was not created"
    print("✓ Custom JSON config test passed!")

def test_from_csv_generation():
    print("Testing --from-csv automated generation...")
    sample_csv = os.path.join(OUTPUT_DIR, "sample_sales.csv")
    out_file = os.path.join(OUTPUT_DIR, "test_csv_dashboard.html")
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

def test_workspace_generation():
    print("Testing composable dashboard workspace...")
    with tempfile.TemporaryDirectory(prefix="charts-design-workspace-") as tmp:
        workspace = os.path.join(tmp, "board")
        data_file = os.path.join(tmp, "regional-sales.json")
        output_file = os.path.join(tmp, "board.html")
        with open(data_file, "w", encoding="utf-8") as f:
            json.dump({
                "categories": ["华东", "华南"],
                "values": [128, 96],
                "unit": "万元"
            }, f, ensure_ascii=False)

        commands = [
            ("dashboard", "init", workspace, "--title", "销售经营看板", "--org", "经营分析部", "--json"),
            ("dashboard", "add", "kpi", workspace, "revenue", "--label", "营业收入", "--value", "224", "--unit", "万元", "--json"),
            ("dashboard", "add", "chart", workspace, "regional-sales", "--code", "c01", "--title", "各区域营业收入", "--unit", "万元", "--data-file", data_file, "--json"),
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

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    test_chart_generation()
    test_dashboard_generation()
    test_preset_generation()
    test_config_generation()
    test_from_csv_generation()
    test_workspace_generation()
    print("All tests successfully completed!")
