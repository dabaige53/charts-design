from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys


SCRIPTS = Path(__file__).parents[1] / "skills" / "executive-charts" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dashboard_workspace import validate_resolved
from generate_dashboard import CHARTS_MAP


PRESENTATIONS = {
    "t06": {
        "axisLabels": {"x": "Period", "leftY": "Revenue", "rightY": "Growth"},
        "seriesLabels": ["Revenue", "Growth"],
        "tooltipValueLabels": ["Revenue", "Growth"],
        "units": ["CNY", "%"],
        "tableHeaders": ["Period", "Revenue", "Growth"],
    },
    "c02": {
        "axisLabels": {"x": "Revenue", "y": "Aircraft"},
        "seriesLabels": ["Revenue"], "tooltipValueLabels": ["Revenue"], "units": ["CNY"],
        "tableHeaders": ["Aircraft", "Revenue"],
    },
    "t05": {
        "axisLabels": {"x": "Stage", "y": "CASK"},
        "seriesLabels": ["Widebody", "Narrowbody"],
        "tooltipValueLabels": ["CASK"], "units": ["cents/seat-km"],
        "tableHeaders": ["Series", "Before", "After"],
    },
    "c04": {
        "axisLabels": {"x": "Deviation", "y": "Fleet"},
        "seriesLabels": ["Deviation"], "tooltipValueLabels": ["Deviation"], "units": ["%"],
        "tableHeaders": ["Fleet", "Deviation"],
    },
    "k01": {"tooltipValueLabels": ["Share"], "units": ["%"], "tableHeaders": ["Segment", "Share"]},
    "r01": {
        "axisLabels": {"x": "Growth", "y": "Margin"},
        "seriesLabels": ["Routes"], "tooltipValueLabels": ["Growth", "Margin"],
        "units": ["%", "%"], "thresholds": {"x": 15, "y": 50},
        "tableHeaders": ["Route", "Growth", "Margin", "Quadrant"],
    },
    "k02": {
        "axisLabels": {"x": "Share", "y": "Hub"},
        "seriesLabels": ["App", "Corporate", "OTA"],
        "tooltipValueLabels": ["App", "Corporate", "OTA"], "units": ["%", "%", "%"],
        "tableHeaders": ["Hub", "App", "Corporate", "OTA"],
    },
}


DATA = {
    "t06": {
        "month": {"categories": ["Jan", "Feb"], "revenue": [1, 2], "yieldGrowth": [3, 4]},
        "quarter": {"categories": ["Q1"], "revenue": [3], "yieldGrowth": [5]},
    },
    "c02": {"categories": ["A", "B"], "values": [2, 1]},
    "t05": {
        "stages": ["Before", "After"],
        "lines": [
            {"name": "Widebody", "data": [45.2, 38.1], "color": "#123B5D"},
            {"name": "Narrowbody", "data": [36.5, 31.2], "color": "#0B2A42"},
        ],
    },
    "c04": {"fleets": ["Widebody", "Narrowbody"], "deviations": [18.2, -5.8]},
    "k01": {
        "demographics": [
            {"value": 60, "name": "Business", "itemStyle": {"color": "#123B5D"}},
            {"value": 40, "name": "Leisure", "itemStyle": {"color": "#8EA4B8"}},
        ]
    },
    "r01": {"routes": [[35.2, 68.5, "Route A"], [-4.8, 42.0, "Route B"]]},
    "k02": {
        "hubs": ["East", "South"], "appDirect": [48, 42],
        "corpDirect": [28, 25], "ota": [24, 33],
    },
}


def _resolved(code: str) -> dict:
    return {
        "meta": {"title": "Board"}, "filters": [], "kpis": [],
        "charts": [{
            "id": f"chart-{code}", "code": code, "title": code, "unit": "declared",
            "data": deepcopy(DATA[code]), "presentation": deepcopy(PRESENTATIONS[code]),
        }],
        "table": {"columns": [], "rows": []},
    }


def _errors(code: str) -> list[dict[str, str]]:
    return validate_resolved(_resolved(code), strict=True)[0]


def test_strict_mode_accepts_renderer_ready_specialized_chart_schemas() -> None:
    for code in DATA:
        assert _errors(code) == [], code


def test_strict_mode_rejects_missing_renderer_private_data_fields() -> None:
    private_fields = {
        "t06": ("month", "yieldGrowth"), "c02": (None, "categories"),
        "t05": (None, "lines"), "c04": (None, "deviations"),
        "k01": (None, "demographics"), "r01": (None, "routes"),
        "k02": (None, "corpDirect"),
    }
    for code, (parent, field) in private_fields.items():
        resolved = _resolved(code)
        data = resolved["charts"][0]["data"]
        del (data[parent] if parent else data)[field]
        errors, _ = validate_resolved(resolved, strict=True)
        assert any(error["code"] == "CHART_DATA_FIELD_MISSING" for error in errors), code


def test_strict_mode_rejects_specialized_chart_length_mismatches() -> None:
    mutations = {
        "t06": lambda data: data["month"]["revenue"].pop(),
        "c02": lambda data: data["values"].pop(),
        "t05": lambda data: data["lines"][0]["data"].pop(),
        "c04": lambda data: data["deviations"].pop(),
        "k02": lambda data: data["ota"].pop(),
    }
    for code, mutate in mutations.items():
        resolved = _resolved(code)
        mutate(resolved["charts"][0]["data"])
        errors, _ = validate_resolved(resolved, strict=True)
        assert any(error["code"] == "CHART_DATA_LENGTH_MISMATCH" for error in errors), code


def test_strict_mode_rejects_specialized_chart_wrong_value_types() -> None:
    mutations = {
        "t06": lambda data: data["month"]["revenue"].__setitem__(0, "1"),
        "c02": lambda data: data["categories"].__setitem__(0, 1),
        "t05": lambda data: data["lines"][0].__setitem__("color", 123),
        "c04": lambda data: data["deviations"].__setitem__(0, True),
        "k01": lambda data: data["demographics"][0].__setitem__("value", "60"),
        "r01": lambda data: data["routes"][0].__setitem__(2, 123),
        "k02": lambda data: data["appDirect"].__setitem__(0, "48"),
    }
    for code, mutate in mutations.items():
        resolved = _resolved(code)
        mutate(resolved["charts"][0]["data"])
        errors, _ = validate_resolved(resolved, strict=True)
        assert any(error["code"] == "CHART_DATA_TYPE_INVALID" for error in errors), code


def test_strict_mode_rejects_missing_or_misaligned_presentation() -> None:
    for code in DATA:
        missing = _resolved(code)
        del missing["charts"][0]["presentation"]
        errors, _ = validate_resolved(missing, strict=True)
        assert any(error["code"] == "CHART_PRESENTATION_MISSING" for error in errors), code

    mismatched = _resolved("k02")
    mismatched["charts"][0]["presentation"]["seriesLabels"].pop()
    errors, _ = validate_resolved(mismatched, strict=True)
    assert any(error["code"] == "CHART_PRESENTATION_LENGTH_MISMATCH" for error in errors)


def test_non_strict_mode_keeps_legacy_compatibility() -> None:
    compatible = _resolved("c02")
    del compatible["charts"][0]["presentation"]
    assert validate_resolved(compatible, strict=False)[0] == []

    legacy = _resolved("c02")
    legacy["charts"][0].update({"code": "c01", "data": {"categories": ["A"], "values": [1]}})
    del legacy["charts"][0]["presentation"]
    errors, _ = validate_resolved(legacy, strict=True)
    assert any(error["code"] == "CHART_PRESENTATION_MISSING" for error in errors)


def _render_specialized_contract(code: str) -> dict:
    chart = _resolved(code)["charts"][0]
    program = "\n".join([
        "const echarts = { graphic: { LinearGradient: (...args) => ({ args }) } };",
        "const tokens = {",
        "  commonOption: {}, axisTitleStyleX: {}, axisTitleStyleY: {},",
        "  palette: { rule: '#ddd', gridline: '#eee', primary: '#123', primarySoft: '#abc', ink: '#111', inkMuted: '#777', positive: '#080', negative: '#c00' }",
        "};",
        f"const cfg = {json.dumps(chart, ensure_ascii=False)};",
        f"const component = {{ ...({CHARTS_MAP[code]}), ...cfg }};",
        "const option = component.optionBuilder(component.data, 'month', tokens, component);",
        "const table = component.tableDataExtractor(component.data, 'month', component);",
        "const tooltip = option.tooltip?.formatter;",
        "let tooltipText = '';",
        "if (typeof tooltip === 'function') {",
        "  if (component.code === 'k01') tooltipText = tooltip({ name: 'Business', value: 60 });",
        "  if (component.code === 'r01') tooltipText = tooltip({ data: component.data.routes[0] });",
        "}",
        "console.log(JSON.stringify({ option, table, tooltipText }));",
    ])
    completed = subprocess.run(["node", "-e", program], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def test_specialized_renderers_consume_business_presentation_instead_of_catalog_labels() -> None:
    rendered = {code: _render_specialized_contract(code) for code in DATA}

    assert rendered["t06"]["option"]["xAxis"]["name"] == "Period"
    assert [axis["name"] for axis in rendered["t06"]["option"]["yAxis"]] == ["Revenue", "Growth"]
    assert [series["name"] for series in rendered["t06"]["option"]["series"]] == ["Revenue", "Growth"]

    for code in ("c02", "c04"):
        option = rendered[code]["option"]
        assert option["xAxis"]["name"] == PRESENTATIONS[code]["axisLabels"]["x"]
        assert option["yAxis"]["name"] == PRESENTATIONS[code]["axisLabels"]["y"]
        assert option["series"][0]["name"] == PRESENTATIONS[code]["seriesLabels"][0]

    assert [series["name"] for series in rendered["t05"]["option"]["series"]] == ["Widebody", "Narrowbody"]
    assert rendered["k01"]["tooltipText"] == "Business<br>Share: 60 %"
    assert rendered["r01"]["option"]["series"][0]["markLine"]["data"] == [{"xAxis": 15}, {"yAxis": 50}]
    assert "Growth" in rendered["r01"]["tooltipText"] and "Margin" in rendered["r01"]["tooltipText"]
    assert rendered["k02"]["option"]["legend"]["data"] == ["App", "Corporate", "OTA"]
    assert rendered["k02"]["table"]["headers"] == ["Hub", "App", "Corporate", "OTA"]
