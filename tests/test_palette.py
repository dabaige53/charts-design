"""Verify the single color source and the 红涨绿跌 direction rule."""
import json
import importlib
from pathlib import Path
import re
import subprocess
import sys

SCRIPTS = Path(__file__).parents[1] / "skills" / "executive-charts" / "scripts"
sys.path.insert(0, str(SCRIPTS))

template = importlib.import_module('core.dashboard_template')
TEMPLATE, generate_dashboard_html = template.TEMPLATE, template.generate_dashboard_html
palette = importlib.import_module('core.palette')
CATEGORICAL, PALETTE = palette.CATEGORICAL, palette.PALETTE
generate_standalone_chart = importlib.import_module('generate_chart').generate_standalone_chart

RED, GREEN = "#A4453C", "#2F6B55"


def run_renderer(scenario):
    html = generate_dashboard_html("", "Palette")
    source = next(script for script in re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S)
                  if "class DashboardApp" in script)
    source = source.rsplit("})();", 1)[0] + "window.testAPI = {DashboardApp, DashboardRenderer, StateStore, trendTextClass};})();"
    program = "\n".join([
        "const window = {}; const document = {readyState: 'complete'};",
        source,
        "const {DashboardApp, DashboardRenderer, StateStore, trendTextClass} = window.testAPI;",
        scenario,
    ])
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_palette_maps_red_to_increase_and_green_to_decrease():
    assert PALETTE["positive"] == RED
    assert PALETTE["negative"] == GREEN


def test_series_identity_colors_never_reuse_change_colors():
    assert RED not in CATEGORICAL
    assert GREEN not in CATEGORICAL
    assert len(set(CATEGORICAL)) == len(CATEGORICAL)


def test_generated_documents_share_the_palette(tmp_path):
    dashboard = generate_dashboard_html("", "Palette")
    tailwind_match = re.search(r"colors: (\{.*?\}),", dashboard)
    echarts_match = re.search(r"palette: (\{.*?\}),\n", dashboard)
    assert tailwind_match is not None and echarts_match is not None
    tailwind = json.loads(tailwind_match.group(1))
    echarts = json.loads(echarts_match.group(1))
    assert tailwind["positive"] == echarts["positive"] == RED
    assert tailwind["negative"] == echarts["negative"] == GREEN
    assert "slate" not in tailwind

    target = tmp_path / "chart.html"
    generate_standalone_chart("c04", output_path=str(target))
    standalone = target.read_text(encoding="utf-8")
    assert f"--color-positive: {RED};" in standalone
    assert f'"positive": "{RED}"' in standalone

    for document in (dashboard, standalone):
        assert not re.search(r"__(TAILWIND_COLORS|TAILWIND_THEME|ECHARTS_PALETTE|CATEGORICAL_COLORS)__", document)


def test_shell_markup_uses_tokens_instead_of_semantic_hex():
    assert RED not in TEMPLATE
    assert GREEN not in TEMPLATE


def test_signed_changes_color_by_direction():
    result = run_renderer("""
const values = ['+12.6% YoY', '-2.1月 YoY', '−3.0%', '↑ 4', '▼ 2', '0.0%', '+0', '—', '持平', 5, -5, 0, undefined];
const classes = Object.fromEntries(values.map(value => [String(value), trendTextClass(value, 'neutral')]));
const container = {innerHTML: '', children: []};
const root = {getElementById: () => container};
new DashboardRenderer({config: {kpis: [
  {id: 'deltas', type: 'mc02', label: '营收', value: '224', yoy: '+12.6%', mom: '-1.2%', subVal: '+¥24 万'}
]}}, root).renderKPIs();
console.log(JSON.stringify({classes, card: container.innerHTML}));
""")
    classes = result["classes"]
    for value in ("+12.6% YoY", "↑ 4", "5"):
        assert classes[value] == "text-positive"
    for value in ("-2.1月 YoY", "−3.0%", "▼ 2", "-5"):
        assert classes[value] == "text-negative"
    for value in ("0.0%", "+0", "—", "持平", "0", "undefined"):
        assert classes[value] == "neutral"

    card = result["card"]
    assert "text-positive border-positive/20 font-mono\">同比 +12.6%" in card
    assert "text-negative border-negative/20 font-mono\">环比 -1.2%" in card
    assert "text-positive font-semibold\">+¥24 万" in card


def test_numeric_comparisons_show_sign_and_direction():
    result = run_renderer("""
const container = {innerHTML: '', children: []};
new DashboardRenderer({config: {kpis: [
  {id: 'numeric', type: 'mc02', label: '销量', value: 100, yoy: 12.4, mom: -1}
]}}, {getElementById: () => container}).renderKPIs();
console.log(JSON.stringify(container.innerHTML));
""")
    assert '同比 +12.4' in result
    assert '环比 -1' in result
    assert 'text-positive border-positive/20' in result
    assert 'text-negative border-negative/20' in result
