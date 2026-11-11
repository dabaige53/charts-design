# ruff: noqa: E402 -- imports follow the shared generator search path.
from copy import deepcopy
from pathlib import Path
import sys


SCRIPTS = Path(__file__).parents[1] / "skills" / "executive-charts" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core.component_schemas import (
    CHART_ARRAY_FIELDS,
    CHART_PRESENTATION_CONTRACTS,
    CHART_TABLE_HEADER_COUNTS,
)
from core.chart_catalog import CHART_COMPONENTS
from dashboard_workspace import validate_resolved


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
    assert isinstance(table_count, int)
    presentation["tableHeaders"] = [f"{code}-column-{index}" for index in range(table_count)]
    return presentation


def _resolved(code: str) -> dict:
    data = deepcopy(CHART_COMPONENTS[code]["data"])
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


# @wu-test type=integration | scope=图表声明与校验 | protects=已支持图表无法通过严格数据校验
def test_every_registered_chart_has_a_complete_strict_data_contract() -> None:
    assert set(CHART_COMPONENTS) == set(CHART_PRESENTATION_CONTRACTS) == set(CHART_TABLE_HEADER_COUNTS)
    for code in CHART_COMPONENTS:
        errors, _ = validate_resolved(_resolved(code), strict=True)
        assert errors == [], (code, errors)


# @wu-test type=boundary | scope=图表数据校验 | protects=缺主数据字段的图表通过校验
def test_every_registered_chart_rejects_a_missing_primary_data_field() -> None:
    for code in CHART_COMPONENTS:
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
