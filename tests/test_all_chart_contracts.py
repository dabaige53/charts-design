from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys


SCRIPTS = Path(__file__).parents[1] / "skills" / "executive-charts" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core.component_schemas import (
    CHART_ARRAY_FIELDS,
    CHART_PRESENTATION_CONTRACTS,
    CHART_TABLE_HEADER_COUNTS,
)
from dashboard_workspace import validate_resolved
from generate_chart import generate_standalone_chart
from generate_dashboard import CHARTS_MAP


def _catalog_components() -> dict[str, dict]:
    definitions = ",\n".join(
        f"{json.dumps(code)}: ({source})" for code, source in CHARTS_MAP.items()
    )
    program = f"const charts = {{{definitions}}}; console.log(JSON.stringify(Object.fromEntries(Object.entries(charts).map(([code, component]) => [code, {{ data: component.data, defaultGranularity: component.defaultGranularity }}]))));"
    completed = subprocess.run(["node", "-"], input=program, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


CATALOG = _catalog_components()


def _presentation(code: str, data: dict) -> dict:
    contract = CHART_PRESENTATION_CONTRACTS[code]
    presentation: dict = {}
    if contract["axis"]:
        presentation["axisLabels"] = {key: f"{code}-axis-{key}" for key in contract["axis"]}

    series_count = contract["series"]
    if series_count == "lines":
        series_count = len(data["lines"])
    if series_count:
        presentation["seriesLabels"] = [f"{code}-series-{index}" for index in range(series_count)]
    presentation["tooltipValueLabels"] = [
        f"{code}-tooltip-{index}" for index in range(contract["tooltip"])
    ]
    presentation["units"] = [f"u{index}" for index in range(contract["units"])]

    label_count = contract.get("labels", 0)
    if label_count:
        presentation["labels"] = [f"{code}-label-{index}" for index in range(label_count)]

    for parent, key in contract.get("numeric", ()):
        values = presentation.setdefault(parent, {})
        values[key] = {
            "high": 80,
            "medium": 60,
            "forecastStartIndex": 1,
            "primaryNodeSize": 20,
        }.get(key, 50)

    for parent, key in contract.get("domain", ()):
        values = presentation.setdefault(parent, {})
        if code == "r05" and key == "indicators":
            values[key] = [[0, 100] for _ in data["indicators"]]
        else:
            values[key] = [0, 100]

    table_count = CHART_TABLE_HEADER_COUNTS[code]
    if table_count == "months+1":
        table_count = len(data["months"]) + 1
    elif table_count == "stages+1":
        table_count = len(data["stages"]) + 1
    presentation["tableHeaders"] = [f"{code}-column-{index}" for index in range(table_count)]
    return presentation


def _resolved(code: str) -> dict:
    data = deepcopy(CATALOG[code]["data"])
    return {
        "meta": {"title": "All chart contracts"},
        "filters": [],
        "kpis": [],
        "charts": [{
            "id": f"chart-{code}",
            "code": code,
            "title": f"Chart {code}",
            "unit": "declared",
            "data": data,
            "presentation": _presentation(code, data),
        }],
        "table": {"columns": [], "rows": []},
    }


def test_every_registered_chart_has_a_complete_strict_generation_contract() -> None:
    assert set(CHARTS_MAP) == set(CHART_PRESENTATION_CONTRACTS) == set(CHART_TABLE_HEADER_COUNTS)
    for code in CHARTS_MAP:
        errors, _ = validate_resolved(_resolved(code), strict=True)
        assert errors == [], (code, errors)


def test_every_registered_chart_rejects_a_missing_primary_data_field() -> None:
    for code in CHARTS_MAP:
        resolved = _resolved(code)
        data = resolved["charts"][0]["data"]
        if code == "t06":
            del data["month"]
        elif code == "m04":
            del data["rate"]
        else:
            del data[CHART_ARRAY_FIELDS[code][0][0]]
        errors, _ = validate_resolved(resolved, strict=True)
        assert any(error["code"] == "CHART_DATA_FIELD_MISSING" for error in errors), (code, errors)


def test_every_registered_renderer_consumes_explicit_headers_and_builds_consistent_tables() -> None:
    configs = {code: _resolved(code)["charts"][0] for code in CHARTS_MAP}
    definitions = ",\n".join(
        f"{json.dumps(code)}: ({source})" for code, source in CHARTS_MAP.items()
    )
    program = "\n".join([
        "const echarts = { graphic: { LinearGradient: function (...args) { this.args = args; } } };",
        "const tokens = { commonOption: {}, axisTitleStyleX: {}, axisTitleStyleY: {}, palette: new Proxy({}, { get: (_, key) => `#${String(key).slice(0, 6)}` }) };",
        f"const charts = {{{definitions}}};",
        f"const configs = {json.dumps(configs, ensure_ascii=False)};",
        "const rendered = {};",
        "for (const [code, base] of Object.entries(charts)) {",
        "  const cfg = { ...base, ...configs[code] };",
        "  try {",
        "    const granularity = cfg.defaultGranularity || 'month';",
        "    const option = cfg.optionBuilder(cfg.data, granularity, tokens, cfg);",
        "    const table = cfg.tableDataExtractor(cfg.data, granularity, cfg);",
        "    rendered[code] = { option, table };",
        "  } catch (error) { rendered[code] = { error: error.stack || String(error) }; }",
        "}",
        "console.log(JSON.stringify(rendered));",
    ])
    completed = subprocess.run(["node", "-"], input=program, check=True, capture_output=True, text=True)
    rendered = json.loads(completed.stdout)

    for code, result in rendered.items():
        assert "error" not in result, (code, result.get("error"))
        expected_headers = configs[code]["presentation"]["tableHeaders"]
        assert result["table"]["headers"] == expected_headers, code
        assert result["table"]["rows"], code
        assert all(len(row) == len(expected_headers) for row in result["table"]["rows"]), code
        option_text = json.dumps(result["option"], ensure_ascii=False)
        for label in configs[code]["presentation"].get("axisLabels", {}).values():
            assert label in option_text, (code, label)
        for label in configs[code]["presentation"].get("seriesLabels", []):
            assert label in option_text, (code, label)


def test_standalone_generator_accepts_a_strict_business_component_config(tmp_path: Path) -> None:
    component = _resolved("c01")["charts"][0]
    target = tmp_path / "chart-c01.html"
    generate_standalone_chart("c01", output_path=str(target), chart_config=component)
    html = target.read_text(encoding="utf-8")
    assert component["title"] in html
    assert component["presentation"]["tableHeaders"][0] in html
    assert json.dumps(component["data"], ensure_ascii=False) in html
    assert ">C01<" not in html
    assert "viewToggleLabel" not in html
    assert 'id="granularityTabs"' not in html
    assert '<polyline points="15 3 21 3 21 9"' in html


def test_structured_chart_tooltips_keep_shape_specific_business_labels() -> None:
    codes = ("d02", "r02", "r03", "d04", "f02", "f03", "r04")
    configs = {code: _resolved(code)["charts"][0] for code in codes}
    definitions = ",\n".join(
        f"{json.dumps(code)}: ({CHARTS_MAP[code]})" for code in codes
    )
    program = "\n".join([
        "const echarts = { graphic: { LinearGradient: function (...args) { this.args = args; } } };",
        "const tokens = { commonOption: {}, axisTitleStyleX: {}, axisTitleStyleY: {}, palette: new Proxy({}, { get: (_, key) => `#${String(key).slice(0, 6)}` }) };",
        f"const charts = {{{definitions}}};",
        f"const configs = {json.dumps(configs, ensure_ascii=False)};",
        "const output = {};",
        "for (const code of Object.keys(charts)) {",
        "  const cfg = { ...charts[code], ...configs[code] };",
        "  const option = cfg.optionBuilder(cfg.data, cfg.defaultGranularity || 'month', tokens, cfg);",
        "  let sample;",
        "  if (code === 'd02') sample = { name: cfg.data.categories[0], value: [0, ...cfg.data.boxData[0]] };",
        "  if (code === 'r02') sample = { data: cfg.data.clusters[0], value: cfg.data.clusters[0] };",
        "  if (code === 'r03' || code === 'f03') sample = { value: cfg.data.matrix[0] };",
        "  if (code === 'd04') sample = { value: cfg.data.data[0] };",
        "  if (code === 'f02') sample = { data: cfg.data.links[0], value: cfg.data.links[0].value, name: cfg.data.links[0].source };",
        "  if (code === 'r04') sample = { data: cfg.data.nodes[0], name: cfg.data.nodes[0].name, value: cfg.data.nodes[0].value };",
        "  output[code] = option.tooltip.formatter(sample);",
        "}",
        "console.log(JSON.stringify(output));",
    ])
    completed = subprocess.run(["node", "-"], input=program, check=True, capture_output=True, text=True)
    rendered = json.loads(completed.stdout)
    for code, tooltip in rendered.items():
        assert configs[code]["presentation"]["tooltipValueLabels"][0] in tooltip, code
