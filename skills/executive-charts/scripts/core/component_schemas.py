"""Stable component schema registry shared by workspace validation."""
from __future__ import annotations

from typing import Any


KPI_TYPES = frozenset(f"mc{index:02d}" for index in range(1, 10))
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


def validate_chart_data(data: Any, path: str) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not isinstance(data, dict):
        return [{"code": "CHART_DATA_INVALID", "path": path, "message": "Chart data must be an object"}]
    if not data:
        return [{"code": "CHART_DATA_EMPTY", "path": path, "message": "Chart data must contain explicit business values"}]

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
    return errors
