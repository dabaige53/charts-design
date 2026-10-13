"""Declarative table-to-component bindings and their generated runtime."""
from __future__ import annotations

import math

from .component_schemas import CHART_ARRAY_FIELDS


AGGREGATES = {"sum", "mean", "min", "max", "count"}
BOUND_KPI_TYPES = {"mc01", "mc02", "mc04", "mc05", "mc08"}


def validate_filter_bindings(resolved):
    errors = []
    table = resolved.get("table")
    if not isinstance(table, dict):
        return errors
    columns = table.get("columns", [])
    rows = table.get("rows", [])
    if not isinstance(columns, list) or not isinstance(rows, list):
        return errors
    fields = {c["key"] for c in columns if isinstance(c, dict) and isinstance(c.get("key"), str)}
    components = {}
    for kind in ("kpis", "charts"):
        items = resolved.get(kind, [])
        if isinstance(items, list):
            for index, item in enumerate(items):
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    components[item["id"]] = (kind, item, f"{kind}[{index}]")

    def error(code, path, message):
        errors.append({"code": code, "path": path, "message": message})

    def source_field(field, path, numeric=False):
        if not isinstance(field, str) or field not in fields:
            error("BINDING_FIELD_UNKNOWN", path, "Binding field must name a declared table column")
            return
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or field not in row:
                error("BINDING_ROW_FIELD_MISSING", f"table.rows[{index}].{field}", "Bound field is missing from this row")
            elif numeric and (
                isinstance(row[field], bool) or not isinstance(row[field], (int, float)) or not math.isfinite(row[field])
            ):
                error("BINDING_VALUE_INVALID", f"table.rows[{index}].{field}", "Aggregation needs finite numbers in the declared display unit")

    def metric(binding, path):
        if not isinstance(binding, dict):
            error("BINDING_INVALID", path, "Metric binding must be an object")
            return
        aggregate = binding.get("aggregate")
        if not isinstance(aggregate, str) or aggregate not in AGGREGATES:
            error("BINDING_AGGREGATE_INVALID", path, "Choose sum, mean, min, max, or count")
        source_field(binding.get("field"), f"{path}.field", numeric=aggregate != "count")

    filters = resolved.get("filters", [])
    for index, item in enumerate(filters if isinstance(filters, list) else []):
        if not isinstance(item, dict):
            continue
        path = f"filters[{index}]"
        for field in item.get("fields", []) if isinstance(item.get("fields"), list) else []:
            if not isinstance(field, str) or field not in fields:
                error("FILTER_FIELD_UNKNOWN", f"{path}.fields", "Filter fields must name declared table columns")
            else:
                source_field(field, f"{path}.fields")
        for component_id in item.get("componentIds", []) if isinstance(item.get("componentIds"), list) else []:
            if not isinstance(component_id, str) or component_id not in components:
                error("FILTER_CONSUMER_UNKNOWN", f"{path}.componentIds", f"Unknown filter consumer: {component_id}")
            elif not components[component_id][1].get("binding"):
                error("FILTER_BINDING_MISSING", components[component_id][2], "Filter consumers need an explicit binding to table rows")

    for kind, component, path in components.values():
        if "binding" not in component:
            continue
        binding = component["binding"]
        path += ".binding"
        if not isinstance(binding, dict):
            error("BINDING_INVALID", path, "Binding must be an object")
            continue
        if kind == "kpis":
            if component.get("type") not in BOUND_KPI_TYPES:
                error("BINDING_KPI_UNSUPPORTED", path, "Value aggregation supports mc01, mc02, mc04, mc05, and mc08; other card shapes need an adapter")
            metric(binding, path)
            precision = binding.get("precision", 0)
            if type(precision) is not int or not 0 <= precision <= 10:
                error("BINDING_PRECISION_INVALID", path, "precision must be an integer from 0 to 10")
        else:
            shape = CHART_ARRAY_FIELDS.get(str(component.get("code", "")).lower(), ())
            categories = [key for key, value_type in shape if value_type == "string"]
            numeric_fields = {key for key, value_type in shape if value_type in ("number", "nullable_number")}
            if len(categories) != 1 or not numeric_fields or len(shape) != len(numeric_fields) + 1:
                error("BINDING_CHART_UNSUPPORTED", path, "Grouped bindings require one category vector and numeric series; structured charts need an adapter")
                continue
            if binding.get("category") != categories[0]:
                error("BINDING_CATEGORY_INVALID", path, f"category must be {categories[0]}")
            source_field(binding.get("groupBy"), f"{path}.groupBy")
            series = binding.get("series")
            if not isinstance(series, dict) or set(series) != numeric_fields:
                error("BINDING_SERIES_INVALID", path, f"Bind every numeric series: {', '.join(sorted(numeric_fields))}")
            else:
                for key, value in series.items():
                    metric(value, f"{path}.series.{key}")
    return errors


FILTER_BINDINGS_JS = r"""
        const ComponentBindings = {
            aggregate(rows, binding) {
                const values = rows.map(row => row[binding.field]).filter(value => value != null);
                if (binding.aggregate === 'count') return values.length;
                if (binding.aggregate === 'sum') return values.reduce((sum, value) => sum + value, 0);
                if (!values.length) return null;
                if (binding.aggregate === 'mean') return values.reduce((sum, value) => sum + value, 0) / values.length;
                if (binding.aggregate === 'min') return values.reduce((a, b) => Math.min(a, b));
                if (binding.aggregate === 'max') return values.reduce((a, b) => Math.max(a, b));
                throw new Error('Unknown aggregation: ' + binding.aggregate);
            },
            kpiValue(rows, kpi) {
                const value = this.aggregate(rows, kpi.binding);
                if (value === null) return '—';
                const precision = kpi.binding.precision ?? 0;
                const formatted = value.toLocaleString('zh-CN', {minimumFractionDigits: precision, maximumFractionDigits: precision});
                return formatted + (kpi.unit ? (kpi.unit === '%' ? '' : ' ') + kpi.unit : '');
            },
            chartData(rows, chart) {
                const binding = chart.binding;
                const groups = new Map();
                rows.forEach(row => {
                    const category = String(row[binding.groupBy] ?? '—');
                    if (!groups.has(category)) groups.set(category, []);
                    groups.get(category).push(row);
                });
                const data = {...chart.data, [binding.category]: [...groups.keys()]};
                Object.entries(binding.series).forEach(([key, metric]) => {
                    data[key] = [...groups.values()].map(group => this.aggregate(group, metric));
                });
                return data;
            }
        };
"""
