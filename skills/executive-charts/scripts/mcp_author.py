"""Prepare a schema-v2 document or revision-bound patch from editable native operations."""
import argparse
import json
import os
import tempfile
from pathlib import Path

from dashboard_runtime.generation import CASES, generation_examples
from dashboard_runtime.model import apply_operations, identifier, new_document, validate


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def write_step(directory, number, op):
    # Only runtime identifiers enter filenames. JSON can contain arbitrary business labels.
    name = identifier(op["op"])
    if "id" in op:
        name += "-" + identifier(op["id"])
    prefix = f"{number:04d}-{name}"
    if name == "set_report_markdown":
        path = directory / (prefix + ".md")
        content = op["value"]
    else:
        path = directory / (prefix + ".json")
        content = encode(op)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(content)
    return path


def steps(work):
    result = []
    for path in sorted((work / "steps").iterdir()):
        if path.name.startswith("."):
            continue
        if path.suffix == ".md":
            op = {"op": "set_report_markdown", "value": path.read_text(encoding="utf-8")}
        elif path.suffix == ".json":
            op = read_json(path)
        else:
            raise ValueError(f"{path}: expected a numbered JSON operation or Markdown file")
        if not isinstance(op, dict) or not isinstance(op.get("op"), str):
            raise ValueError(f"{path}: expected one native operation")
        result.append((path, op))
    return result


def init(args):
    if args.from_document:
        if args.id or args.title or args.example or args.mode:
            raise ValueError("--from-document uses the original ID, title and mode")
        payload = read_json(args.from_document)
        original = payload.get("document", payload)
        # Keep the canonical artifact, excluding transport-only views and preloaded results.
        doc = validate({key: original[key] for key in ("schemaVersion", "id", "revision", "manifest", "snapshot")})
        operations = []
    else:
        if not args.id:
            raise ValueError("supply --id or --from-document")
        doc = new_document(args.id, args.title or args.id)
        operations = generation_examples(args.example)["operations"] if args.example else []
        if args.title:
            operations.append({"op": "set_title", "value": args.title})
        if args.mode:
            operations.append({"op": "set_view_mode", "value": args.mode})
    args.work.parent.mkdir(parents=True, exist_ok=True)
    if args.work.exists():
        raise FileExistsError(f"workspace already exists: {args.work}")
    with tempfile.TemporaryDirectory(dir=args.work.parent) as tmp:
        staging = Path(tmp) / "workspace"
        directory = staging / "steps"
        directory.mkdir(parents=True)
        state = {"existing": bool(args.from_document), "document": doc}
        if args.from_document and payload.get("projectRoot"):
            state["projectRoot"] = payload["projectRoot"]
        (staging / "base.json").write_text(encode(state), encoding="utf-8")
        for number, op in enumerate(operations, 1):
            write_step(directory, number, op)
        staging.rename(args.work)
    return args.work


def stage(args):
    state = read_json(args.work / "base.json")
    doc = state["document"]
    manifest = doc["manifest"]
    existing = steps(args.work)
    kinds = {"source": "put_source", "metric": "put_metric", "component": "put_component",
             "filters": "set_filters", "markdown": "set_report_markdown", "dataset": "put_dataset"}
    keyed = args.kind not in ("filters", "markdown")
    if keyed != bool(args.id):
        raise ValueError("source, dataset, metric and component need an ID; filters and markdown are page-wide")
    if keyed:
        identifier(args.id)
    op_name = kinds[args.kind]
    names = {op_name, "put_dataset_ref"} if args.kind == "dataset" else {op_name}
    for path, op in reversed(existing):
        if op["op"] in names and op.get("id") == args.id:
            if args.value:
                raise ValueError(f"edit the existing step: {path}")
            return path
    if args.value:
        value = args.value.read_text(encoding="utf-8") if args.kind == "markdown" else read_json(args.value)
    elif args.kind == "markdown":
        value = manifest.get("report", {}).get("markdown", "")
    elif args.kind == "filters":
        value = manifest["filters"]
    elif args.kind == "dataset":
        meta = manifest["datasets"][args.id]
        snapshot = doc["snapshot"]
        if args.id in snapshot["datasets"]:
            value = {"meta": meta, "rows": snapshot["datasets"][args.id]}
        else:
            value = {"meta": meta, "ref": snapshot["datasetRefs"][args.id]}
    else:
        value = manifest[args.kind + "s"][args.id]
    op = {"op": op_name, "value": value}
    if keyed:
        op["id"] = args.id
    if args.kind == "dataset":
        if not isinstance(value, dict) or set(value) not in ({"meta", "rows"}, {"meta", "ref"}):
            raise ValueError("dataset needs meta and exactly one of rows or ref")
        op = {"op": "put_dataset_ref" if "ref" in value else op_name, "id": args.id, **value}
    last = max((int(path.name.split("-")[0]) for path, _ in existing), default=0)
    return write_step(args.work / "steps", last + 1, op)


def build(args):
    state = read_json(args.work / "base.json")
    doc = state["document"]
    operations = [op for _, op in steps(args.work)]
    for op in operations:
        if op["op"] == "set_annotations":
            raise ValueError("edit annotations separately using expectedAnnotations")
        if op["op"] == "set_chart":
            raise ValueError("use set_original_chart for preset switching")
        if op["op"] == "put_component" and op.get("value", {}).get("kind") == "chart":
            previous = doc["manifest"]["components"].get(op["id"], {})
            if previous.get("kind") != "chart" or previous.get("chartType") != op["value"].get("chartType"):
                raise ValueError("use kind=legacy, family=chart for new MCP charts")
    candidate = apply_operations(doc, operations) if operations else validate(doc)
    if args.format == "document":
        return candidate
    if not args.project_root:
        raise ValueError("MCP request files require --project-root")
    request = {"projectRoot": args.project_root, "dashboardId": doc["id"]}
    if args.format == "patch":
        if not state["existing"] or not operations:
            raise ValueError("patch requires a dashboard_get base and at least one edit")
        original_project = state.get("projectRoot")
        if original_project and args.project_root != original_project:
            raise ValueError(f"patch must target the project recorded by dashboard_get: {original_project}")
        return {**request, "expectedRevision": doc["revision"], "operations": operations}
    if state["existing"]:
        raise ValueError("use patch for an existing dashboard")
    return {**request, "document": candidate}


def check_filters(args):
    payload = read_json(args.document)
    actual = payload.get("document", payload)["manifest"]["filters"]
    expected = read_json(args.expected)
    if not isinstance(expected, list):
        raise ValueError("expected a list of audited filters, including [] for a page with none")
    by_id = {item["id"]: item for item in actual}
    expected_ids = [item["id"] for item in expected]
    if len(expected_ids) != len(set(expected_ids)) or len(by_id) != len(actual):
        raise ValueError("duplicate filter IDs")
    errors = []
    for key in sorted(set(by_id) - set(expected_ids)):
        errors.append(f"{key}: unexpected filter")
    for item in expected:
        key = item["id"]
        if not {"field", "componentIds"} <= item.keys() or not isinstance(item["componentIds"], list):
            raise ValueError(f"{key}: record the source field and full list of consumers")
        if key not in by_id:
            errors.append(f"{key}: missing filter")
            continue
        fields = {"scope": "report", "selectionMode": "multiple", **by_id[key]}
        for field, value in item.items():
            observed = fields.get(field)
            if field == "componentIds":
                equal = isinstance(observed, list) and sorted(value) == sorted(observed)
            else:
                equal = field in fields and observed == value
            if not equal:
                errors.append(f"{key}.{field}: expected {value!r}, observed {observed!r}")
    if errors:
        raise ValueError("\n".join(errors))
    return f"{len(expected)} filters matched"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    start = commands.add_parser("init", help="create a fresh local authoring directory")
    start.add_argument("work", type=Path)
    start.add_argument("--from-document", type=Path, help="canonical document or dashboard_get result")
    start.add_argument("--id")
    start.add_argument("--title")
    start.add_argument("--mode", choices=["dashboard", "report", "filtered-report"])
    start.add_argument("--example", choices=sorted(CASES), help="explicitly initialize with a synthetic example")
    edit = commands.add_parser("stage", help="open an existing declaration as an editable step or stage a new value")
    edit.add_argument("work", type=Path)
    edit.add_argument("kind", choices=["source", "dataset", "metric", "component", "filters", "markdown"])
    edit.add_argument("id", nargs="?")
    edit.add_argument("--value", type=Path, help="native value file for a new step")
    compile_cmd = commands.add_parser("build", help="validate locally and write a document or MCP request")
    compile_cmd.add_argument("work", type=Path)
    compile_cmd.add_argument("--format", choices=["document", "create", "patch"], default="document")
    compile_cmd.add_argument("--project-root")
    compile_cmd.add_argument("--out", required=True, type=Path)
    check = commands.add_parser("check-filters", help="compare every filter ID and its consumers with the source audit")
    check.add_argument("document", type=Path)
    check.add_argument("expected", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "check-filters":
            print(check_filters(args))
            return
        if args.action in ("init", "stage"):
            print(init(args) if args.action == "init" else stage(args))
            return
        dest = args.out.resolve()
        if dest == (args.work / "base.json").resolve() or dest.is_relative_to((args.work / "steps").resolve()):
            raise ValueError("choose an output outside the authoring inputs")
        payload = encode(build(args))
        with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
            output = Path(tmp) / "result"
            output.write_text(payload, encoding="utf-8")
            os.replace(output, dest)
        print(dest)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        parser.exit(1, f"{args.action}: {exc}\n")


if __name__ == "__main__":
    main()
