"""Preset dashboards ship column-bound filters and keep table values intact."""
import json
from pathlib import Path
import re
import sys

import pytest

SCRIPTS = Path(__file__).parents[1] / "skills" / "executive-charts" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from generate_dashboard import PRESET_CONFIGS, generate_dashboard, legacy_filters_to_array
from test_palette import run_renderer


def built_config(tmp_path, **kwargs):
    target = tmp_path / "board.html"
    generate_dashboard(output_path=str(target), **kwargs)
    html = target.read_text(encoding="utf-8")
    filters = json.loads(re.search(r"filters: (\[.*?\]),\n\s+kpis:", html, re.S).group(1))
    table = json.loads(re.search(r"table: (\{.*?\}),\n\s+explanations:", html, re.S).group(1))
    return filters, table


def initial_row_count(filters, table):
    config = {"meta": {"title": "Preset"}, "filters": filters, "kpis": [], "charts": [], "table": table}
    return run_renderer(f"const config = {json.dumps(config, ensure_ascii=False)};" + """
const app = Object.create(DashboardApp.prototype);
app.state = new StateStore(config); app.config = app.state.config;
console.log(JSON.stringify(app.getFilteredTableRows().length));
""")


@pytest.mark.parametrize("preset", sorted(PRESET_CONFIGS))
def test_preset_filters_bind_table_columns_and_start_with_every_row(tmp_path, preset):
    filters, table = built_config(tmp_path, preset_name=preset)
    columns = {column["key"] for column in table["columns"]}
    assert filters
    for definition in filters:
        assert definition["fields"] and set(definition["fields"]) <= columns
        values = {row[definition["fields"][0]] for row in table["rows"]}
        assert {option["value"] for option in definition["options"]} - {"ALL"} == values
    assert initial_row_count(filters, table) == len(table["rows"])


def test_preset_dimensions_missing_from_a_custom_table_are_dropped(tmp_path):
    table = {"columns": [{"key": "region", "title": "区域"}], "rows": [{"region": "华东"}]}
    filters, _ = built_config(tmp_path, preset_name="executive_report", config_dict={"table": table})
    assert filters == []


def test_legacy_object_filters_bind_to_the_column_holding_their_values():
    legacy = {
        "labels": {"time": "周期", "hub": "枢纽", "fleet": "机型"},
        "seasons": [{"val": "2026S", "label": "2026 夏秋"}],
        "hubs": [{"val": "华东基地"}, {"val": "华南基地"}],
        "fleets": [{"val": "ALL"}, {"val": "WIDE"}],
    }
    table = {"columns": [{"key": "hub", "title": "基地"}, {"key": "fleet", "title": "机型"}],
             "rows": [{"hub": "华东基地", "fleet": "A350"}, {"hub": "华南基地", "fleet": "B737"}]}
    filters = legacy_filters_to_array(legacy, table)
    assert [(f["key"], f["label"], f["type"], f["fields"]) for f in filters] == [("hub", "枢纽", "multi-select", ["hub"])]
    assert [option["value"] for option in filters[0]["options"]] == ["华东基地", "华南基地"]
    assert initial_row_count(filters, table) == 2


def test_table_cells_and_csv_keep_zero_values():
    table = {"title": "明细", "columns": [{"key": "name", "title": "门店"}, {"key": "sales", "title": "销售额", "align": "right"},
                                          {"key": "note", "title": "备注"}],
             "rows": [{"name": "华东一店", "sales": 0, "note": ""}]}
    config = {"meta": {"title": "Zero"}, "filters": [], "kpis": [], "charts": [], "table": table}
    result = run_renderer(f"const config = {json.dumps(config, ensure_ascii=False)};" + """
const app = Object.create(DashboardApp.prototype);
app.state = new StateStore(config); app.config = app.state.config;
const elements = {};
app.getById = id => elements[id] ??= {innerHTML: '', textContent: '', disabled: false, classList: {add() {}, remove() {}, toggle() {}}};
app.renderTableEngine();
let csv = '';
globalThis.Blob = function(parts) { csv = parts.join(''); };
URL.createObjectURL = () => 'blob:test'; URL.revokeObjectURL = () => {};
document.createElement = () => ({click() {}});
app.showToast = () => {};
app.exportTableToCSV();
console.log(JSON.stringify({body: elements.main14ColTbody.innerHTML, csv}));
""")
    cells = re.findall(r"<td[^>]*>(.*?)</td>", result["body"], re.S)
    assert cells == ["华东一店", "0", "-"]
    assert result["csv"].splitlines()[-1] == '"华东一店","0",""'
