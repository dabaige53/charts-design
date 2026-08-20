#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automation test suite for McKinsey-grade executive charts and dashboards.
"""
import os
import sys
import subprocess

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

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    test_chart_generation()
    test_dashboard_generation()
    print("All tests successfully completed!")
