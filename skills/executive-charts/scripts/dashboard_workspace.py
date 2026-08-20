#!/usr/bin/env python3
"""Composable dashboard workspace commands for the charts-design CLI."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from generate_dashboard import CHARTS_MAP, generate_dashboard
from core.csv_profiler import profile_csv


SCHEMA_VERSION = 1
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


class WorkspaceError(Exception):
    def __init__(self, code: str, message: str, path: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkspaceError("FILE_NOT_FOUND", f"File not found: {path}", str(path)) from exc
    except json.JSONDecodeError as exc:
        raise WorkspaceError(
            "INVALID_JSON",
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {path}",
            str(path),
        ) from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def workspace_root(raw_path: str) -> Path:
    return Path(raw_path).expanduser().resolve()


def manifest_path(root: Path) -> Path:
    return root / "dashboard.json"


def load_manifest(root: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path(root))
    if not isinstance(manifest, dict):
        raise WorkspaceError("INVALID_MANIFEST", "dashboard.json must contain an object", "dashboard.json")
    if manifest.get("schemaVersion") != SCHEMA_VERSION:
        raise WorkspaceError(
            "SCHEMA_VERSION_UNSUPPORTED",
            f"Expected schemaVersion {SCHEMA_VERSION}",
            "dashboard.json.schemaVersion",
        )
    return manifest


def safe_component_path(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise WorkspaceError("PATH_OUTSIDE_WORKSPACE", f"Path escapes workspace: {relative_path}", relative_path) from exc
    return candidate


def component_refs(manifest: dict[str, Any], kind: str) -> list[str]:
    components = manifest.setdefault("components", {})
    refs = components.setdefault(kind, [])
    if not isinstance(refs, list):
        raise WorkspaceError("INVALID_MANIFEST", f"components.{kind} must be an array", f"dashboard.json.components.{kind}")
    return refs


def summary(root: Path, manifest: dict[str, Any], resolved: dict[str, Any] | None = None) -> dict[str, Any]:
    if resolved is None:
        resolved, _ = resolve_workspace(root, manifest)
    return {
        "schemaVersion": manifest.get("schemaVersion"),
        "title": resolved.get("meta", {}).get("title", ""),
        "org": resolved.get("meta", {}).get("org", ""),
        "counts": {
            "filters": len(resolved.get("filters", [])),
            "kpis": len(resolved.get("kpis", [])),
            "charts": len(resolved.get("charts", [])),
            "tableRows": len(resolved.get("table", {}).get("rows", [])),
        },
        "kpis": [
            {"id": item.get("id"), "label": item.get("label"), "unit": item.get("unit")}
            for item in resolved.get("kpis", [])
            if isinstance(item, dict)
        ],
        "charts": [
            {"id": item.get("id"), "code": item.get("code"), "title": item.get("title")}
            if isinstance(item, dict)
            else {"id": None, "code": item, "title": None}
            for item in resolved.get("charts", [])
        ],
    }


def resolve_workspace(root: Path, manifest: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    components = manifest.get("components", {})
    errors: list[dict[str, str]] = []
    resolved: dict[str, Any] = {
        "meta": manifest.get("meta", {}),
        "filters": [],
        "kpis": [],
        "charts": [],
        "table": {"title": "数据明细", "columns": [], "rows": []},
        "explanations": {},
    }

    filters_ref = components.get("filters", "filters.json")
    table_ref = components.get("table", "table.json")
    for key, ref, fallback in (
        ("filters", filters_ref, []),
        ("table", table_ref, resolved["table"]),
    ):
        if not ref:
            resolved[key] = fallback
            continue
        try:
            resolved[key] = read_json(safe_component_path(root, ref))
        except WorkspaceError as exc:
            errors.append({"code": exc.code, "path": exc.path or str(ref), "message": exc.message})

    for kind in ("kpis", "charts"):
        for ref in components.get(kind, []):
            try:
                item = read_json(safe_component_path(root, ref))
                resolved[kind].append(item)
            except WorkspaceError as exc:
                errors.append({"code": exc.code, "path": exc.path or str(ref), "message": exc.message})

    return resolved, errors


def validate_resolved(resolved: dict[str, Any], strict: bool) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    def error(code: str, path: str, message: str) -> None:
        errors.append({"code": code, "path": path, "message": message})

    def warning(code: str, path: str, message: str) -> None:
        warnings.append({"code": code, "path": path, "message": message})

    meta = resolved.get("meta")
    if not isinstance(meta, dict):
        error("META_INVALID", "meta", "meta must be an object")
    elif not meta.get("title"):
        (error if strict else warning)("META_TITLE_MISSING", "meta.title", "Dashboard title is missing")

    filters = resolved.get("filters")
    if not isinstance(filters, list):
        error("FILTERS_NOT_ARRAY", "filters", "filters must be an array so 0-N dimensions remain explicit")
    else:
        seen_keys: set[str] = set()
        for index, item in enumerate(filters):
            path = f"filters[{index}]"
            if not isinstance(item, dict):
                error("FILTER_INVALID", path, "Filter must be an object")
                continue
            key = item.get("key") or item.get("id")
            if not key:
                error("FILTER_KEY_MISSING", f"{path}.key", "Filter key is required")
            elif key in seen_keys:
                error("FILTER_KEY_DUPLICATE", f"{path}.key", f"Duplicate filter key: {key}")
            else:
                seen_keys.add(key)
            if item.get("type") not in ("select", "multi-select"):
                error("FILTER_TYPE_INVALID", f"{path}.type", "Filter type must be select or multi-select")
            if not isinstance(item.get("options"), list):
                error("FILTER_OPTIONS_INVALID", f"{path}.options", "Filter options must be an array")

    for kind in ("kpis", "charts"):
        if not isinstance(resolved.get(kind), list):
            error(f"{kind.upper()}_NOT_ARRAY", kind, f"{kind} must be an array")

    seen_ids: set[str] = set()
    for index, item in enumerate(resolved.get("kpis", [])):
        path = f"kpis[{index}]"
        if not isinstance(item, dict):
            error("KPI_INVALID", path, "KPI must be an object")
            continue
        item_id = item.get("id")
        if not item_id or item_id in seen_ids:
            error("KPI_ID_INVALID", f"{path}.id", "KPI id must be present and unique")
        else:
            seen_ids.add(item_id)
        for field in ("label", "value"):
            if item.get(field) in (None, ""):
                error("KPI_FIELD_MISSING", f"{path}.{field}", f"KPI {field} is required")
        if strict and not item.get("unit"):
            error("KPI_UNIT_MISSING", f"{path}.unit", "Declare a unit for the KPI")

    for index, item in enumerate(resolved.get("charts", [])):
        path = f"charts[{index}]"
        if not isinstance(item, dict):
            error("CHART_INVALID", path, "Workspace charts must be component objects")
            continue
        item_id = item.get("id")
        if not item_id or item_id in seen_ids:
            error("CHART_ID_INVALID", f"{path}.id", "Chart id must be present and unique")
        else:
            seen_ids.add(item_id)
        code = str(item.get("code", "")).lower()
        if code not in CHARTS_MAP:
            error("CHART_CODE_UNKNOWN", f"{path}.code", f"Unknown chart code: {code or '<missing>'}")
        if not item.get("title"):
            error("CHART_TITLE_MISSING", f"{path}.title", "Chart title is required")
        if "data" not in item:
            error("CHART_DATA_MISSING", f"{path}.data", "Chart data is required; catalog demo data is not used in workspace builds")
        if strict and not item.get("unit") and not (isinstance(item.get("data"), dict) and item["data"].get("unit")):
            error("CHART_UNIT_MISSING", f"{path}.unit", "Declare the metric unit in the chart or its data")

    if not resolved.get("kpis") and not resolved.get("charts"):
        error("DASHBOARD_EMPTY", "components", "Add at least one KPI or chart before building")

    table = resolved.get("table")
    if not isinstance(table, dict):
        error("TABLE_INVALID", "table", "table must be an object")
    else:
        if not isinstance(table.get("columns", []), list) or not isinstance(table.get("rows", []), list):
            error("TABLE_SHAPE_INVALID", "table", "table.columns and table.rows must be arrays")
        if strict:
            for index, column in enumerate(table.get("columns", [])):
                if not isinstance(column, dict) or not column.get("key") or not column.get("title"):
                    error("TABLE_COLUMN_INVALID", f"table.columns[{index}]", "Each table column needs key and title")
                elif column.get("align") == "right" and not column.get("unit"):
                    error("TABLE_UNIT_MISSING", f"table.columns[{index}].unit", "Numeric table columns must declare a unit")

    return errors, warnings


def emit(command: str, payload: dict[str, Any], json_mode: bool) -> None:
    envelope = {"ok": True, "command": command, **payload}
    if json_mode:
        print(json.dumps(envelope, ensure_ascii=False))
        return
    print(f"✓ {command}")
    if "workspace" in payload:
        print(f"  workspace: {payload['workspace']}")
    if "summary" in payload:
        counts = payload["summary"]["counts"]
        print(
            "  components: "
            f"{counts['filters']} filters, {counts['kpis']} KPIs, "
            f"{counts['charts']} charts, {counts['tableRows']} table rows"
        )
    for item in payload.get("warnings", []):
        print(f"  warning [{item['code']}]: {item['message']}")


def parse_option(raw: str, default_values: set[str]) -> dict[str, Any]:
    value, separator, label = raw.partition("=")
    if not separator or not value or not label:
        raise WorkspaceError("OPTION_INVALID", f"Expected --option value=label, got: {raw}")
    return {"value": value, "label": label, "default": value in default_values}


def infer_display_unit(value: Any) -> str:
    text = str(value)
    for unit in ("元/㎡/天", "元/㎡", "亿元", "万元", "%", "天", "家", "人", "个"):
        if unit in text:
            return unit
    return "count"


def ensure_id(value: str) -> None:
    if not ID_PATTERN.match(value):
        raise WorkspaceError("ID_INVALID", f"Use lowercase letters, digits, _ or - for id: {value}")


def cmd_init(args: argparse.Namespace) -> None:
    root = workspace_root(args.workspace)
    if root.exists() and any(root.iterdir()) and not args.force:
        raise WorkspaceError("WORKSPACE_NOT_EMPTY", f"Workspace is not empty: {root}", str(root))
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "meta": {
            "title": args.title or "经营决策看板",
            "subtitle": args.subtitle or "",
            "org": args.org or "",
            "system": args.system or "",
        },
        "components": {
            "filters": "filters.json",
            "kpis": [],
            "charts": [],
            "table": "table.json",
        },
    }
    write_json(manifest_path(root), manifest)
    write_json(root / "filters.json", [])
    write_json(root / "table.json", {"title": "数据明细", "columns": [], "rows": []})
    (root / "kpis").mkdir(exist_ok=True)
    (root / "charts").mkdir(exist_ok=True)
    emit("dashboard.init", {"workspace": str(root), "summary": summary(root, manifest)}, args.json)


def cmd_import_csv(args: argparse.Namespace) -> None:
    root = workspace_root(args.workspace)
    if root.exists() and any(root.iterdir()) and not args.force:
        raise WorkspaceError("WORKSPACE_NOT_EMPTY", f"Workspace is not empty: {root}", str(root))
    config = profile_csv(args.csv, custom_title=args.title)
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_init(argparse.Namespace(
            workspace=str(root), title=config.get("meta", {}).get("title"),
            subtitle=config.get("meta", {}).get("subtitle"), org=args.org or "",
            system="", force=args.force, json=False,
        ))
    manifest = load_manifest(root)
    write_json(root / "filters.json", config.get("filters", []))
    write_json(root / "table.json", config.get("table", {"title": "数据明细", "columns": [], "rows": []}))
    for index, kpi in enumerate(config.get("kpis", []), start=1):
        item_id = kpi.get("id") or f"kpi-{index}"
        kpi.setdefault("unit", infer_display_unit(kpi.get("value", "")))
        write_json(root / "kpis" / f"{item_id}.json", kpi)
        component_refs(manifest, "kpis").append(f"kpis/{item_id}.json")
    # Profiler chart JS is intentionally not imported as final workspace components.
    manifest.setdefault("draft", {})["csvProfile"] = {
        "source": str(Path(args.csv).expanduser().resolve()),
        "suggestedChartCount": len(config.get("charts", [])),
        "note": "Add explicit chart components after reviewing the inferred fields.",
    }
    write_json(manifest_path(root), manifest)
    resolved, _ = resolve_workspace(root, manifest)
    emit(
        "dashboard.import-csv",
        {
            "workspace": str(root),
            "summary": summary(root, manifest, resolved),
            "warnings": [{
                "code": "CSV_PROFILE_IS_DRAFT",
                "path": "dashboard.json.draft.csvProfile",
                "message": "CSV inference imported filters, KPIs and table only; add reviewed chart components explicitly.",
            }],
        },
        args.json,
    )


def cmd_inspect(args: argparse.Namespace) -> None:
    root = workspace_root(args.workspace)
    manifest = load_manifest(root)
    resolved, resolve_errors = resolve_workspace(root, manifest)
    emit(
        "dashboard.inspect",
        {"workspace": str(root), "summary": summary(root, manifest, resolved), "errors": resolve_errors},
        args.json,
    )


def cmd_validate(args: argparse.Namespace) -> None:
    root = workspace_root(args.workspace)
    manifest = load_manifest(root)
    resolved, errors = resolve_workspace(root, manifest)
    validation_errors, warnings = validate_resolved(resolved, args.strict)
    errors.extend(validation_errors)
    payload = {
        "workspace": str(root),
        "valid": not errors,
        "summary": summary(root, manifest, resolved),
        "errors": errors,
        "warnings": warnings,
    }
    if errors:
        raise WorkspaceError("VALIDATION_FAILED", json.dumps(payload, ensure_ascii=False))
    emit("dashboard.validate", payload, args.json)


def cmd_meta_set(args: argparse.Namespace) -> None:
    root = workspace_root(args.workspace)
    manifest = load_manifest(root)
    updates = {key: getattr(args, key) for key in ("title", "subtitle", "org", "system", "statusText") if getattr(args, key) is not None}
    if not updates:
        raise WorkspaceError("NO_CHANGES", "Provide at least one meta field to update")
    manifest.setdefault("meta", {}).update(updates)
    write_json(manifest_path(root), manifest)
    emit("dashboard.meta.set", {"workspace": str(root), "summary": summary(root, manifest)}, args.json)


def cmd_add_filter(args: argparse.Namespace) -> None:
    root = workspace_root(args.workspace)
    ensure_id(args.id)
    manifest = load_manifest(root)
    filters_path = safe_component_path(root, manifest.get("components", {}).get("filters", "filters.json"))
    filters = read_json(filters_path)
    if not isinstance(filters, list):
        raise WorkspaceError("FILTERS_NOT_ARRAY", "filters.json must contain an array", str(filters_path))
    if any(isinstance(item, dict) and (item.get("id") == args.id or item.get("key") == args.id) for item in filters):
        raise WorkspaceError("COMPONENT_EXISTS", f"Filter already exists: {args.id}")
    default_values = set(args.default or [])
    item = {
        "id": args.id,
        "key": args.key or args.id,
        "label": args.label,
        "type": args.type,
        "options": [parse_option(raw, default_values) for raw in args.option],
    }
    filters.append(item)
    write_json(filters_path, filters)
    emit("dashboard.add.filter", {"workspace": str(root), "component": {"id": args.id, "path": str(filters_path)}}, args.json)


def cmd_add_component(args: argparse.Namespace, kind: str) -> None:
    root = workspace_root(args.workspace)
    ensure_id(args.id)
    manifest = load_manifest(root)
    refs = component_refs(manifest, kind)
    relative_path = f"{kind}/{args.id}.json"
    path = safe_component_path(root, relative_path)
    if path.exists() and not args.replace:
        raise WorkspaceError("COMPONENT_EXISTS", f"Component already exists: {args.id}", relative_path)

    if args.from_file:
        item = read_json(Path(args.from_file).expanduser().resolve())
        if not isinstance(item, dict):
            raise WorkspaceError("COMPONENT_INVALID", "Component file must contain an object", args.from_file)
        item["id"] = args.id
    elif kind == "kpis":
        if not args.label or args.value == "":
            raise WorkspaceError("KPI_FIELDS_MISSING", "KPI needs --label and --value, or use --from")
        value = args.value
        if args.unit and args.unit not in value:
            value = f"{value} {args.unit}".strip()
        item = {"id": args.id, "type": args.type, "label": args.label, "value": value, "unit": args.unit or ""}
        if args.yoy:
            item["yoy"] = args.yoy
        if args.status:
            item["status"] = args.status
    else:
        if not args.code or not args.title:
            raise WorkspaceError("CHART_FIELDS_MISSING", "Chart needs --code and --title, or use --from")
        data: Any = {}
        if args.data_file:
            data = read_json(Path(args.data_file).expanduser().resolve())
        item = {
            "id": args.id,
            "code": args.code.lower(),
            "title": args.title,
            "subtitle": args.subtitle or "",
            "unit": args.unit or "",
            "data": data,
        }

    write_json(path, item)
    if relative_path not in refs:
        refs.append(relative_path)
    write_json(manifest_path(root), manifest)
    emit(f"dashboard.add.{kind[:-1]}", {"workspace": str(root), "component": {"id": args.id, "path": str(path)}}, args.json)


def cmd_set_table(args: argparse.Namespace) -> None:
    root = workspace_root(args.workspace)
    manifest = load_manifest(root)
    source = read_json(Path(args.from_file).expanduser().resolve())
    if not isinstance(source, dict):
        raise WorkspaceError("TABLE_INVALID", "Table file must contain an object", args.from_file)
    table_path = safe_component_path(root, manifest.get("components", {}).get("table", "table.json"))
    write_json(table_path, source)
    emit("dashboard.table.set", {"workspace": str(root), "component": {"path": str(table_path)}}, args.json)


def cmd_build(args: argparse.Namespace) -> None:
    root = workspace_root(args.workspace)
    manifest = load_manifest(root)
    resolved, errors = resolve_workspace(root, manifest)
    validation_errors, warnings = validate_resolved(resolved, strict=True)
    errors.extend(validation_errors)
    if errors:
        payload = {"workspace": str(root), "valid": False, "errors": errors, "warnings": warnings}
        raise WorkspaceError("VALIDATION_FAILED", json.dumps(payload, ensure_ascii=False))
    output = Path(args.output).expanduser().resolve()
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        generate_dashboard(
            config_dict=resolved,
            output_path=str(output),
            auto_open=args.open,
            allow_preset_fallback=False,
        )
    emit(
        "dashboard.build",
        {
            "workspace": str(root),
            "output": str(output),
            "bytes": output.stat().st_size,
            "summary": summary(root, manifest, resolved),
            "warnings": warnings,
        },
        args.json,
    )


def add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Emit one stable JSON object to stdout")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Composable dashboard workspace editor and builder")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create an empty dashboard workspace")
    init_parser.add_argument("workspace")
    init_parser.add_argument("--title")
    init_parser.add_argument("--subtitle")
    init_parser.add_argument("--org")
    init_parser.add_argument("--system")
    init_parser.add_argument("--force", action="store_true")
    add_json_flag(init_parser)
    init_parser.set_defaults(func=cmd_init)

    csv_parser = subparsers.add_parser("import-csv", help="Create a reviewable draft workspace from CSV")
    csv_parser.add_argument("workspace")
    csv_parser.add_argument("--csv", required=True)
    csv_parser.add_argument("--title")
    csv_parser.add_argument("--org")
    csv_parser.add_argument("--force", action="store_true")
    add_json_flag(csv_parser)
    csv_parser.set_defaults(func=cmd_import_csv)

    inspect_parser = subparsers.add_parser("inspect", help="Show a bounded component summary")
    inspect_parser.add_argument("workspace")
    add_json_flag(inspect_parser)
    inspect_parser.set_defaults(func=cmd_inspect)

    validate_parser = subparsers.add_parser("validate", help="Validate workspace references and component schemas")
    validate_parser.add_argument("workspace")
    validate_parser.add_argument("--strict", action="store_true")
    add_json_flag(validate_parser)
    validate_parser.set_defaults(func=cmd_validate)

    meta_parser = subparsers.add_parser("meta", help="Update dashboard metadata")
    meta_subparsers = meta_parser.add_subparsers(dest="meta_command", required=True)
    meta_set = meta_subparsers.add_parser("set", help="Set one or more metadata fields")
    meta_set.add_argument("workspace")
    meta_set.add_argument("--title")
    meta_set.add_argument("--subtitle")
    meta_set.add_argument("--org")
    meta_set.add_argument("--system")
    meta_set.add_argument("--status-text", dest="statusText")
    add_json_flag(meta_set)
    meta_set.set_defaults(func=cmd_meta_set)

    add_parser = subparsers.add_parser("add", help="Add one dashboard building block")
    add_subparsers = add_parser.add_subparsers(dest="kind", required=True)

    filter_parser = add_subparsers.add_parser("filter", help="Append one filter definition")
    filter_parser.add_argument("workspace")
    filter_parser.add_argument("id")
    filter_parser.add_argument("--key")
    filter_parser.add_argument("--label", required=True)
    filter_parser.add_argument("--type", choices=("select", "multi-select"), default="select")
    filter_parser.add_argument("--option", action="append", default=[], help="Repeat value=label")
    filter_parser.add_argument("--default", action="append", help="Repeat a default option value")
    add_json_flag(filter_parser)
    filter_parser.set_defaults(func=cmd_add_filter)

    kpi_parser = add_subparsers.add_parser("kpi", help="Add one KPI component")
    kpi_parser.add_argument("workspace")
    kpi_parser.add_argument("id")
    kpi_parser.add_argument("--label", required=False)
    kpi_parser.add_argument("--value", default="")
    kpi_parser.add_argument("--unit")
    kpi_parser.add_argument("--type", default="mc01")
    kpi_parser.add_argument("--yoy")
    kpi_parser.add_argument("--status")
    kpi_parser.add_argument("--from", dest="from_file")
    kpi_parser.add_argument("--replace", action="store_true")
    add_json_flag(kpi_parser)
    kpi_parser.set_defaults(func=lambda args: cmd_add_component(args, "kpis"))

    chart_parser = add_subparsers.add_parser("chart", help="Add one chart component")
    chart_parser.add_argument("workspace")
    chart_parser.add_argument("id")
    chart_parser.add_argument("--code")
    chart_parser.add_argument("--title")
    chart_parser.add_argument("--subtitle")
    chart_parser.add_argument("--unit")
    chart_parser.add_argument("--data-file")
    chart_parser.add_argument("--from", dest="from_file")
    chart_parser.add_argument("--replace", action="store_true")
    add_json_flag(chart_parser)
    chart_parser.set_defaults(func=lambda args: cmd_add_component(args, "charts"))

    table_parser = subparsers.add_parser("table", help="Set the dashboard table from one component file")
    table_subparsers = table_parser.add_subparsers(dest="table_command", required=True)
    table_set = table_subparsers.add_parser("set", help="Replace table.json from a component file")
    table_set.add_argument("workspace")
    table_set.add_argument("--from", dest="from_file", required=True)
    add_json_flag(table_set)
    table_set.set_defaults(func=cmd_set_table)

    build_cmd = subparsers.add_parser("build", help="Strictly validate and compile a workspace to HTML")
    build_cmd.add_argument("workspace")
    build_cmd.add_argument("--output", "-o", required=True)
    build_cmd.add_argument("--open", action="store_true")
    add_json_flag(build_cmd)
    build_cmd.set_defaults(func=cmd_build)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except WorkspaceError as exc:
        json_mode = bool(getattr(args, "json", False))
        details: dict[str, Any]
        try:
            details = json.loads(exc.message)
        except json.JSONDecodeError:
            details = {"errors": [{"code": exc.code, "path": exc.path, "message": exc.message}]}
        envelope = {"ok": False, "command": getattr(args, "command", "dashboard"), **details}
        if json_mode:
            print(json.dumps(envelope, ensure_ascii=False))
        else:
            print(f"Error [{exc.code}]: {exc.message}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
