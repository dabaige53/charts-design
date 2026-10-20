"""Stable component schema registry shared by workspace validation."""
from __future__ import annotations

from typing import Any
import math
import re


KPI_TYPES = frozenset(f"mc{index:02d}" for index in range(1, 10))


def validate_kpi_comparisons(kpi: dict[str, Any], path: str) -> list[dict[str, str]]:
    """Do not silently turn an ambiguous nonzero comparison into a neutral badge."""
    errors = []
    for field in ("yoy", "mom", "leftYoy", "rightYoy"):
        value = kpi.get(field)
        message = None
        if value is None:
            continue
        if type(value) in (int, float):
            if not math.isfinite(value):
                message = "Comparison must be finite or null"
        elif isinstance(value, str):
            text = value.strip()
            match = re.match(r"^[¥$€]?\s*([0-9][0-9.,]*)", text)
            if match:
                try:
                    nonzero = float(match[1].replace(',', '')) != 0
                except ValueError:
                    nonzero = True
                if nonzero:
                    message = "Nonzero comparison text needs an explicit + or - sign; use a numeric value when available"
        else:
            message = "Comparison must be a number, signed display text, or null"
        if message:
            errors.append({"code": "KPI_COMPARISON_INVALID", "path": f"{path}.{field}", "message": message})
    return errors


def validate_kpi_presentation(kpi: dict[str, Any], path: str) -> list[dict[str, str]]:
    """Require the data rendered by specialized KPI cards, preserving zero."""
    errors = validate_kpi_comparisons(kpi, path)

    def error(field, message):
        errors.append({"code": "KPI_PRESENTATION_INVALID", "path": f"{path}.{field}", "message": message})

    card_type = kpi.get("type")
    if card_type in ("mc04", "mc05"):
        value = str(kpi.get("value", "")).replace(",", "")
        if not re.match(r"^\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value):
            error("value", "Progress and gauge cards need a numeric display value")
    if card_type == "mc03":
        months, data = kpi.get("sparkMonths"), kpi.get("sparkData")
        if not isinstance(months, list) or not months or not all(isinstance(m, str) for m in months):
            error("sparkMonths", "Declare non-empty sparkline period labels")
        if not isinstance(data, list) or not data or not all(
            type(v) in (int, float) and math.isfinite(v) for v in data
        ):
            error("sparkData", "Declare explicit finite sparkline values")
        elif isinstance(months, list) and len(months) != len(data):
            error("sparkData", "Sparkline periods and values must have equal lengths")
    if card_type == "mc06":
        for field in ("leftTitle", "leftVal", "rightTitle", "rightVal"):
            if kpi.get(field) in (None, ""):
                error(field, "Declare both metrics and their labels")
    if card_type == "mc09":
        widths = []
        for field in ("segLeftWidth", "segRightWidth"):
            try:
                value = float(str(kpi.get(field, "")).removesuffix("%"))
            except ValueError:
                value = float("nan")
            if not math.isfinite(value) or not 0 <= value <= 100:
                error(field, "Declare a segment percentage from 0 to 100")
            widths.append(value)
        if all(math.isfinite(v) for v in widths) and not math.isclose(sum(widths), 100):
            error("segLeftWidth", "Segment percentages must sum to 100")
        for field in ("subLabel", "subVal"):
            if kpi.get(field) in (None, ""):
                error(field, "Declare the segment label and value")
    return errors


CHART_CODES = (
    "c01", "c02", "c03", "c04", "c05", "c06", "c07", "c08",
    "d01", "d02", "d03", "d04", "f01", "f02", "f03",
    "fn01", "fn02", "fn03", "fn04", "k01", "k02", "k03", "k04", "k05", "k06",
    "m01", "m02", "m03", "m04", "r01", "r02", "r03", "r04", "r05",
    "t01", "t02", "t03", "t04", "t05", "t06",
)
CHART_SCHEMA_REGISTRY = {
    code: f"{''.join(character for character in code if character.isalpha())}-family-data-v1"
    for code in CHART_CODES
}


SPECIALIZED_DATA_VALIDATOR_CODES = frozenset(("t06", "c02", "t05", "c04", "k01", "r01", "k02"))
STRICT_CHART_CODES = frozenset(CHART_CODES)

CHART_ARRAY_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "c01": (("categories", "string"), ("values", "number")),
    "c02": (("categories", "string"), ("values", "number")),
    "c03": (("clusters", "string"), ("budget", "number"), ("actual", "number")),
    "c04": (("fleets", "string"), ("deviations", "number")),
    "c05": (("categories", "string"), ("scores", "number")),
    "c06": (("hubs", "string"), ("offSeason", "number"), ("peakSeason", "number")),
    "c07": (("clusters", "string"), ("base2024", "number"), ("curr2025", "number")),
    "c08": (("categories", "string"), ("domestic", "number"), ("intl", "number")),
    "d01": (("brackets", "string"), ("counts", "number")),
    "d02": (("categories", "string"), ("boxData", "array")),
    "d03": (("plfRange", "string"), ("density", "number")),
    "d04": (("days", "string"), ("hours", "string"), ("data", "array")),
    "f01": (("stages", "object"),),
    "f02": (("nodes", "object"), ("links", "object")),
    "f03": (("cohorts", "string"), ("months", "string"), ("matrix", "array")),
    "fn01": (("categories", "string"), ("baseSteps", "number"), ("deltas", "number"), ("labels", "string")),
    "fn02": (("quarters", "string"), ("revenue", "number"), ("cost", "number")),
    "fn03": (("variables", "string"), ("negative", "number"), ("positive", "number")),
    "fn04": (("nodes", "string"), ("east", "number"), ("south", "number"), ("north", "number"), ("west", "number")),
    "k01": (("demographics", "object"),),
    "k02": (("hubs", "string"), ("appDirect", "number"), ("corpDirect", "number"), ("ota", "number")),
    "k03": (("assets", "object"),),
    "k04": (("causes", "string"), ("counts", "number"), ("cumPercent", "number")),
    "k05": (("shares", "object"),),
    "k06": (("hierarchy", "object"),),
    "m01": (("metrics", "string"), ("actual", "number")),
    "m02": (("quarters", "string"), ("baseline", "number"), ("optimistic", "number"), ("pessimistic", "number")),
    "m03": (("airports", "string"), ("overage", "number")),
    "r01": (("routes", "array"),),
    "r02": (("clusters", "array"),),
    "r03": (("dimensions", "string"), ("matrix", "array")),
    "r04": (("nodes", "object"), ("links", "object")),
    "r05": (("indicators", "object"), ("seriesData", "object")),
    "t01": (("months", "string"), ("rpk", "number")),
    "t02": (("quarters", "string"), ("actual", "nullable_number"), ("forecast", "nullable_number")),
    "t03": (("segments", "string"), ("rates", "number")),
    "t04": (("quarters", "string"), ("premium", "number"), ("economy", "number"), ("cargo", "number"), ("ancillary", "number")),
    "t05": (("stages", "string"), ("lines", "object")),
}

CHART_EQUAL_LENGTH_GROUPS: dict[str, tuple[tuple[str, ...], ...]] = {
    code: (tuple(key for key, _ in fields),)
    for code, fields in CHART_ARRAY_FIELDS.items()
    if code not in {"d04", "f01", "f02", "f03", "k01", "k03", "k05", "k06", "r01", "r02", "r03", "r04", "r05", "t05"}
}
CHART_EQUAL_LENGTH_GROUPS.update({
    "d02": (("categories", "boxData"),),
    "m01": (("metrics", "actual"),),
})

CHART_PRESENTATION_CONTRACTS: dict[str, dict[str, Any]] = {
    "t06": {"axis": ("x", "leftY", "rightY"), "series": 2, "tooltip": 2, "units": 2},
    "c01": {"axis": ("x", "y"), "series": 1, "tooltip": 1, "units": 1},
    "c02": {"axis": ("x", "y"), "series": 1, "tooltip": 1, "units": 1},
    "r01": {"axis": ("x", "y"), "series": 1, "tooltip": 2, "units": 2, "numeric": (("thresholds", "x"), ("thresholds", "y"))},
    "fn01": {"axis": ("x", "y"), "series": 1, "tooltip": 1, "units": 1},
    "f01": {"axis": (), "series": 1, "tooltip": 1, "units": 1},
    "fn03": {"axis": ("x", "y"), "series": 2, "tooltip": 2, "units": 1},
    "c08": {"axis": ("x", "y"), "series": 2, "tooltip": 2, "units": 2},
    "c05": {"axis": ("x", "y"), "series": 2, "tooltip": 2, "units": 2, "labels": 3, "numeric": (("thresholds", "high"), ("thresholds", "medium"))},
    "c07": {"axis": ("x", "y"), "series": 2, "tooltip": 2, "units": 2},
    "t01": {"axis": ("x", "y"), "series": 1, "tooltip": 1, "units": 1},
    "t03": {"axis": ("x", "y"), "series": 1, "tooltip": 1, "units": 1},
    "k05": {"axis": (), "series": 0, "tooltip": 1, "units": 1, "numeric": (("totals", "value"),)},
    "d02": {"axis": ("x", "y"), "series": 1, "tooltip": 5, "units": 5},
    "r03": {"axis": ("x", "y"), "series": 1, "tooltip": 1, "units": 1, "domain": (("domains", "visualMap"),)},
    "c03": {"axis": ("x", "y"), "series": 2, "tooltip": 2, "units": 2},
    "fn02": {"axis": ("x", "y"), "series": 2, "tooltip": 2, "units": 2},
    "f02": {"axis": (), "series": 1, "tooltip": 1, "units": 1},
    "c04": {"axis": ("x", "y"), "series": 1, "tooltip": 1, "units": 1},
    "m03": {"axis": ("x", "y"), "series": 1, "tooltip": 1, "units": 1, "labels": 2, "numeric": (("thresholds", "warning"),)},
    "fn04": {"axis": ("x", "y"), "series": 4, "tooltip": 4, "units": 4},
    "d01": {"axis": ("x", "y"), "series": 1, "tooltip": 1, "units": 1},
    "d03": {"axis": ("x", "y"), "series": 1, "tooltip": 1, "units": 1, "labels": 2},
    "t04": {"axis": ("x", "y"), "series": 4, "tooltip": 4, "units": 4},
    "t02": {"axis": ("x", "y"), "series": 2, "tooltip": 2, "units": 2, "labels": 2, "numeric": (("thresholds", "forecastStartIndex"),)},
    "k02": {"axis": ("x", "y"), "series": 3, "tooltip": 3, "units": 3},
    "r02": {"axis": ("x", "y"), "series": 1, "tooltip": 4, "units": 4},
    "f03": {"axis": ("x", "y"), "series": 1, "tooltip": 1, "units": 1, "domain": (("domains", "visualMap"),)},
    "m01": {"axis": ("x", "y"), "series": 1, "tooltip": 1, "units": 1, "labels": 2, "numeric": (("thresholds", "target"),)},
    "d04": {"axis": ("x", "y"), "series": 1, "tooltip": 1, "units": 1, "domain": (("domains", "visualMap"),)},
    "r04": {"axis": (), "series": 1, "tooltip": 1, "units": 1, "labels": 4, "numeric": (("thresholds", "primaryNodeSize"),)},
    "c06": {"axis": ("x", "y"), "series": 2, "tooltip": 2, "units": 2, "labels": 2, "numeric": (("thresholds", "target"),)},
    "t05": {"axis": ("x", "y"), "series": "lines", "tooltip": 1, "units": 1},
    "k01": {"axis": (), "series": 0, "tooltip": 1, "units": 1},
    "k04": {"axis": ("x", "y"), "series": 2, "tooltip": 2, "units": 2, "labels": 2, "numeric": (("thresholds", "primaryShare"),)},
    "k03": {"axis": (), "series": 1, "tooltip": 1, "units": 1},
    "k06": {"axis": (), "series": 1, "tooltip": 1, "units": 1, "labels": 2, "numeric": (("thresholds", "primaryShare"),)},
    "m02": {"axis": ("x", "y"), "series": 3, "tooltip": 3, "units": 3},
    "r05": {"axis": (), "series": 2, "tooltip": 2, "units": 2, "domain": (("domains", "indicators"),)},
    "m04": {"axis": (), "series": 1, "tooltip": 1, "units": 1, "labels": 2, "domain": (("domains", "value"),)},
}

CHART_TABLE_HEADER_COUNTS: dict[str, int | str] = {
    "c01": 2, "c02": 2, "c03": 5, "c04": 2, "c05": 3, "c06": 4, "c07": 5, "c08": 4,
    "d01": 3, "d02": 4, "d03": 3, "d04": 3,
    "f01": 3, "f02": 3, "f03": "months+1",
    "fn01": 3, "fn02": 4, "fn03": 3, "fn04": 5,
    "k01": 2, "k02": 4, "k03": 3, "k04": 4, "k05": 3, "k06": 4,
    "m01": 4, "m02": 4, "m03": 3, "m04": 4,
    "r01": 4, "r02": 5, "r03": 3, "r04": 3, "r05": 4,
    "t01": 3, "t02": 3, "t03": 3, "t04": 5, "t05": "stages+1", "t06": 3,
}


def validate_chart_data(
    data: Any,
    path: str,
    *,
    code: str | None = None,
    strict: bool = False,
    presentation: Any = None,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not isinstance(data, dict):
        return [{"code": "CHART_DATA_INVALID", "path": path, "message": "Chart data must be an object"}]
    if not data:
        errors.append({"code": "CHART_DATA_EMPTY", "path": path, "message": "Chart data must contain explicit business values"})
        if not (strict and code in STRICT_CHART_CODES):
            return errors

    def array_required(key: str) -> None:
        if key in data and not isinstance(data[key], list):
            errors.append({"code": "CHART_DATA_ARRAY_REQUIRED", "path": f"{path}.{key}", "message": f"Chart data {key} must be an array"})

    for key in ("categories", "values", "x", "y", "nodes", "links", "series"):
        array_required(key)
    for left, right in (("categories", "values"), ("x", "y")):
        if isinstance(data.get(left), list) and isinstance(data.get(right), list) and len(data[left]) != len(data[right]):
            errors.append({
                "code": "CHART_DATA_LENGTH_MISMATCH", "path": path,
                "message": f"Chart data {left} and {right} must have equal lengths",
            })
    if strict and code in STRICT_CHART_CODES:
        _validate_strict_data(code, data, path, errors)
        _validate_strict_presentation(code, data, presentation, path, errors)
    return errors


def _append_error(errors: list[dict[str, str]], code: str, path: str, message: str) -> None:
    errors.append({"code": code, "path": path, "message": message})


def _required(data: dict[str, Any], key: str, path: str, errors: list[dict[str, str]]) -> Any:
    if key not in data:
        _append_error(errors, "CHART_DATA_FIELD_MISSING", f"{path}.{key}", f"Chart data {key} is required")
        return None
    return data[key]


def _array(
    data: dict[str, Any], key: str, path: str, errors: list[dict[str, str]], item_type: str,
) -> list[Any] | None:
    value = _required(data, key, path, errors)
    if value is None:
        return None
    if not isinstance(value, list):
        _append_error(errors, "CHART_DATA_TYPE_INVALID", f"{path}.{key}", f"Chart data {key} must be an array")
        return None
    if not value:
        _append_error(errors, "CHART_DATA_EMPTY", f"{path}.{key}", f"Chart data {key} must contain at least one item")
        return value
    validators = {
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "nullable_number": lambda item: item is None or (isinstance(item, (int, float)) and not isinstance(item, bool)),
        "string": lambda item: isinstance(item, str) and bool(item),
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
    }
    if not all(validators[item_type](item) for item in value):
        _append_error(
            errors, "CHART_DATA_TYPE_INVALID", f"{path}.{key}",
            f"Chart data {key} must contain only {item_type} values",
        )
    return value


def _equal_lengths(
    arrays: list[tuple[str, list[Any] | None]], path: str, errors: list[dict[str, str]],
) -> None:
    present = [(name, values) for name, values in arrays if values is not None]
    if len(present) > 1 and len({len(values) for _, values in present}) != 1:
        names = ", ".join(name for name, _ in present)
        _append_error(
            errors, "CHART_DATA_LENGTH_MISMATCH", path,
            f"Chart data arrays {names} must have equal lengths",
        )


def _validate_strict_data(
    code: str, data: dict[str, Any], path: str, errors: list[dict[str, str]],
) -> None:
    if code not in SPECIALIZED_DATA_VALIDATOR_CODES:
        _validate_registered_data(code, data, path, errors)
        return
    paired_arrays = {
        "c02": (("categories", "string"), ("values", "number")),
        "c04": (("fleets", "string"), ("deviations", "number")),
        "k02": (
            ("hubs", "string"), ("appDirect", "number"),
            ("corpDirect", "number"), ("ota", "number"),
        ),
    }
    if code in paired_arrays:
        values = [(key, _array(data, key, path, errors, item_type)) for key, item_type in paired_arrays[code]]
        _equal_lengths(values, path, errors)
        return

    if code == "t06":
        for granularity in ("month", "quarter"):
            current = _required(data, granularity, path, errors)
            current_path = f"{path}.{granularity}"
            if current is None:
                continue
            if not isinstance(current, dict):
                _append_error(errors, "CHART_DATA_TYPE_INVALID", current_path, f"{granularity} data must be an object")
                continue
            arrays = [
                ("categories", _array(current, "categories", current_path, errors, "string")),
                ("revenue", _array(current, "revenue", current_path, errors, "number")),
                ("yieldGrowth", _array(current, "yieldGrowth", current_path, errors, "number")),
            ]
            _equal_lengths(arrays, current_path, errors)
        return

    if code == "t05":
        stages = _array(data, "stages", path, errors, "string")
        lines = _array(data, "lines", path, errors, "object")
        if lines is None:
            return
        for index, line in enumerate(lines):
            if not isinstance(line, dict):
                continue
            line_path = f"{path}.lines[{index}]"
            for key in ("name", "color"):
                value = _required(line, key, line_path, errors)
                if value is not None and (not isinstance(value, str) or not value):
                    _append_error(errors, "CHART_DATA_TYPE_INVALID", f"{line_path}.{key}", f"Line {key} must be a string")
            line_data = _array(line, "data", line_path, errors, "number")
            _equal_lengths([("stages", stages), ("data", line_data)], line_path, errors)
        return

    if code == "k01":
        demographics = _array(data, "demographics", path, errors, "object")
        if demographics is None:
            return
        for index, item in enumerate(demographics):
            if not isinstance(item, dict):
                continue
            item_path = f"{path}.demographics[{index}]"
            value = _required(item, "value", item_path, errors)
            if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                _append_error(errors, "CHART_DATA_TYPE_INVALID", f"{item_path}.value", "Demographic value must be numeric")
            name = _required(item, "name", item_path, errors)
            if name is not None and (not isinstance(name, str) or not name):
                _append_error(errors, "CHART_DATA_TYPE_INVALID", f"{item_path}.name", "Demographic name must be a string")
            style = _required(item, "itemStyle", item_path, errors)
            color = style.get("color") if isinstance(style, dict) else None
            if not isinstance(style, dict) or not isinstance(color, str) or not color:
                _append_error(errors, "CHART_DATA_TYPE_INVALID", f"{item_path}.itemStyle.color", "Demographic color must be a string")
        return

    routes = _array(data, "routes", path, errors, "array")
    if routes is None:
        return
    for index, route in enumerate(routes):
        if not isinstance(route, list):
            continue
        valid = (
            len(route) == 3
            and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in route[:2])
            and isinstance(route[2], str) and bool(route[2])
        )
        if not valid:
            _append_error(
                errors, "CHART_DATA_TYPE_INVALID", f"{path}.routes[{index}]",
                "Each route must be [numeric x, numeric y, non-empty label]",
            )


def _validate_registered_data(
    code: str, data: dict[str, Any], path: str, errors: list[dict[str, str]],
) -> None:
    arrays: dict[str, list[Any] | None] = {}
    for key, item_type in CHART_ARRAY_FIELDS.get(code, ()):
        arrays[key] = _array(data, key, path, errors, item_type)
    for group in CHART_EQUAL_LENGTH_GROUPS.get(code, ()):
        _equal_lengths([(key, arrays.get(key)) for key in group], path, errors)

    def object_fields(key: str, required: dict[str, str]) -> None:
        for index, item in enumerate(arrays.get(key) or []):
            if not isinstance(item, dict):
                continue
            item_path = f"{path}.{key}[{index}]"
            for field, expected in required.items():
                value = _required(item, field, item_path, errors)
                valid = {
                    "string": isinstance(value, str) and bool(value),
                    "number": isinstance(value, (int, float)) and not isinstance(value, bool),
                    "array": isinstance(value, list),
                }[expected]
                if value is not None and not valid:
                    _append_error(errors, "CHART_DATA_TYPE_INVALID", f"{item_path}.{field}", f"{field} must be {expected}")

    if code == "d02":
        for index, values in enumerate(arrays.get("boxData") or []):
            valid = len(values) == 5 and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values)
            if not valid:
                _append_error(errors, "CHART_DATA_TYPE_INVALID", f"{path}.boxData[{index}]", "Box data must contain five numeric values")
    elif code in {"f01", "k01", "k03", "k05"}:
        key = {"f01": "stages", "k01": "demographics", "k03": "assets", "k05": "shares"}[code]
        object_fields(key, {"name": "string", "value": "number"})
    elif code in {"f02", "r04"}:
        object_fields("nodes", {"name": "string"})
        required = {"source": "string", "target": "string"}
        if code == "f02":
            required["value"] = "number"
        object_fields("links", required)
        node_names = {item.get("name") for item in arrays.get("nodes") or [] if isinstance(item, dict)}
        for index, link in enumerate(arrays.get("links") or []):
            if isinstance(link, dict) and (link.get("source") not in node_names or link.get("target") not in node_names):
                _append_error(errors, "CHART_DATA_REFERENCE_INVALID", f"{path}.links[{index}]", "Link endpoints must reference declared nodes")
    elif code in {"d04", "f03", "r03"}:
        matrix_key = "data" if code == "d04" else "matrix"
        expected = {
            "d04": len(arrays.get("days") or []) * len(arrays.get("hours") or []),
            "f03": len(arrays.get("cohorts") or []) * len(arrays.get("months") or []),
            "r03": len(arrays.get("dimensions") or []) ** 2,
        }[code]
        matrix = arrays.get(matrix_key) or []
        if len(matrix) != expected:
            _append_error(errors, "CHART_DATA_LENGTH_MISMATCH", f"{path}.{matrix_key}", f"Matrix must contain {expected} cells")
        for index, cell in enumerate(matrix):
            valid = len(cell) == 3 and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in cell)
            if not valid:
                _append_error(errors, "CHART_DATA_TYPE_INVALID", f"{path}.{matrix_key}[{index}]", "Matrix cells must be [numeric x, numeric y, numeric value]")
    elif code == "k06":
        def validate_tree(nodes: list[Any], tree_path: str) -> None:
            for index, node in enumerate(nodes):
                node_path = f"{tree_path}[{index}]"
                if not isinstance(node, dict):
                    continue
                name = node.get("name")
                if not isinstance(name, str) or not name:
                    _append_error(errors, "CHART_DATA_TYPE_INVALID", f"{node_path}.name", "Tree node name must be a string")
                children = node.get("children")
                value = node.get("value")
                if isinstance(children, list) and children:
                    validate_tree(children, f"{node_path}.children")
                elif not isinstance(value, (int, float)) or isinstance(value, bool):
                    _append_error(errors, "CHART_DATA_TYPE_INVALID", f"{node_path}.value", "Tree leaf value must be numeric")
        validate_tree(arrays.get("hierarchy") or [], f"{path}.hierarchy")
    elif code == "r02":
        for index, point in enumerate(arrays.get("clusters") or []):
            valid = (
                len(point) == 4
                and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in point[:3])
                and isinstance(point[3], str) and bool(point[3])
            )
            if not valid:
                _append_error(errors, "CHART_DATA_TYPE_INVALID", f"{path}.clusters[{index}]", "Bubble points must be [numeric x, numeric y, numeric size, non-empty label]")
    elif code == "r05":
        object_fields("indicators", {"name": "string", "max": "number"})
        object_fields("seriesData", {"name": "string", "value": "array"})
        expected = len(arrays.get("indicators") or [])
        if len(arrays.get("seriesData") or []) != 2:
            _append_error(errors, "CHART_DATA_LENGTH_MISMATCH", f"{path}.seriesData", "Radar data must contain two comparison series")
        for index, series in enumerate(arrays.get("seriesData") or []):
            values = series.get("value") if isinstance(series, dict) else None
            valid = isinstance(values, list) and len(values) == expected and all(
                isinstance(value, (int, float)) and not isinstance(value, bool) for value in values
            )
            if not valid:
                _append_error(errors, "CHART_DATA_LENGTH_MISMATCH", f"{path}.seriesData[{index}].value", f"Radar series must contain {expected} numeric values")

    if code == "m01":
        target = _required(data, "target", path, errors)
        if target is not None and (not isinstance(target, (int, float)) or isinstance(target, bool)):
            _append_error(errors, "CHART_DATA_TYPE_INVALID", f"{path}.target", "Target must be numeric")
    if code == "m04":
        rate = _required(data, "rate", path, errors)
        target = _required(data, "target", path, errors)
        if rate is not None and (not isinstance(rate, (int, float)) or isinstance(rate, bool)):
            _append_error(errors, "CHART_DATA_TYPE_INVALID", f"{path}.rate", "Rate must be numeric")
        if target is not None and not isinstance(target, (str, int, float)):
            _append_error(errors, "CHART_DATA_TYPE_INVALID", f"{path}.target", "Target must be a display string or number")


def _validate_strict_presentation(
    code: str,
    data: dict[str, Any],
    presentation: Any,
    data_path: str,
    errors: list[dict[str, str]],
) -> None:
    path = data_path.rsplit(".data", 1)[0] + ".presentation"
    if presentation is None:
        _append_error(errors, "CHART_PRESENTATION_MISSING", path, "Strict chart generation requires presentation metadata")
        return
    if not isinstance(presentation, dict):
        _append_error(errors, "CHART_PRESENTATION_TYPE_INVALID", path, "Chart presentation must be an object")
        return

    contract = CHART_PRESENTATION_CONTRACTS[code]
    axis_keys = contract["axis"]
    axis_labels = presentation.get("axisLabels")
    if axis_keys and (
        not isinstance(axis_labels, dict)
        or any(not isinstance(axis_labels.get(key), str) or not axis_labels[key] for key in axis_keys)
    ):
        _append_error(errors, "CHART_PRESENTATION_FIELD_MISSING", f"{path}.axisLabels", f"axisLabels must declare {', '.join(axis_keys)}")

    series_count = contract["series"]
    if series_count == "lines":
        series_count = len(data.get("lines", [])) if isinstance(data.get("lines"), list) else 0
    for key, expected in (
        ("seriesLabels", series_count),
        ("tooltipValueLabels", contract["tooltip"]),
        ("units", contract["units"]),
        ("labels", contract.get("labels", 0)),
    ):
        if expected == 0:
            continue
        value = presentation.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            _append_error(errors, "CHART_PRESENTATION_FIELD_MISSING", f"{path}.{key}", f"presentation {key} must be a string array")
        elif len(value) != expected:
            _append_error(errors, "CHART_PRESENTATION_LENGTH_MISMATCH", f"{path}.{key}", f"presentation {key} must contain {expected} values")

    table_count = CHART_TABLE_HEADER_COUNTS[code]
    if table_count == "months+1":
        table_count = len(data.get("months", [])) + 1
    elif table_count == "stages+1":
        table_count = len(data.get("stages", [])) + 1
    table_headers = presentation.get("tableHeaders")
    if not isinstance(table_headers, list) or not all(isinstance(item, str) and item for item in table_headers):
        _append_error(errors, "CHART_PRESENTATION_FIELD_MISSING", f"{path}.tableHeaders", "presentation tableHeaders must be a string array")
    elif len(table_headers) != table_count:
        _append_error(errors, "CHART_PRESENTATION_LENGTH_MISMATCH", f"{path}.tableHeaders", f"presentation tableHeaders must contain {table_count} values")

    for parent, key in contract.get("numeric", ()):
        container = presentation.get(parent)
        value = container.get(key) if isinstance(container, dict) else None
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            _append_error(errors, "CHART_PRESENTATION_FIELD_MISSING", f"{path}.{parent}.{key}", f"{parent}.{key} must be numeric")

    for parent, key in contract.get("domain", ()):
        container = presentation.get(parent)
        value = container.get(key) if isinstance(container, dict) else None
        valid_pair = isinstance(value, list) and len(value) == 2 and all(
            isinstance(item, (int, float)) and not isinstance(item, bool) for item in value
        )
        if code == "r05" and key == "indicators":
            expected = len(data.get("indicators", [])) if isinstance(data.get("indicators"), list) else 0
            valid_pair = isinstance(value, list) and len(value) == expected and all(
                isinstance(pair, list) and len(pair) == 2 and all(
                    isinstance(item, (int, float)) and not isinstance(item, bool) for item in pair
                ) for pair in value
            )
        if not valid_pair:
            _append_error(errors, "CHART_PRESENTATION_FIELD_MISSING", f"{path}.{parent}.{key}", f"{parent}.{key} must declare numeric domain pairs")
