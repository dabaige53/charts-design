"""Exercise the packaged authoring path against the same service used by MCP."""
import json
import os
import subprocess
import sys
from pathlib import Path

from dashboard_runtime.service import Service


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/executive-charts/scripts/mcp_author.py"


def author(*args, succeeds=True):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    assert (result.returncode == 0) == succeeds, result.stderr
    return result.stdout.strip() if succeeds else result.stderr


# @wu-test type=integration | scope=MCP authoring | protects=existing reports lose scope or unrelated declarations on revision
def test_filtered_report_edit(tmp_path):
    new, change = tmp_path / "new", tmp_path / "change"
    request, saved = tmp_path / "request.json", tmp_path / "saved.json"
    project = str(tmp_path / "project")
    runtime = Service(tmp_path / "cache", project_root=project)
    author("init", new, "--id", "month", "--example", "filtered-report")
    author("build", new, "--format", "create", "--project-root", project, "--out", request)
    runtime.call("dashboard_create", json.loads(request.read_text()))
    board = {"dashboardId": "month", "dataMode": "local"}
    original = runtime.call("dashboard_get", board)
    saved.write_text(json.dumps({**original, "projectRoot": project}))
    author("init", change, "--from-document", saved)
    path = Path(author("stage", change, "filters"))
    operation = json.loads(path.read_text())
    operation["value"][0]["label"] = "所属营业部"
    path.write_text(json.dumps(operation))
    assert author("stage", change, "filters") == str(path)
    author("build", change, "--format", "patch", "--project-root", project, "--out", request)
    wrong_project = author("build", change, "--format", "patch", "--project-root", "other",
                           "--out", request, succeeds=False)
    assert "project recorded by dashboard_get" in wrong_project
    patch = json.loads(request.read_text())
    assert patch["expectedRevision"] == original["document"]["revision"]
    assert patch["operations"] == [operation]
    batch = runtime.call("dashboard_edit_begin", {**board, "expectedRevision": patch["expectedRevision"]})
    updated = runtime.call("dashboard_patch", patch)["document"]
    assert updated["manifest"]["report"] == original["document"]["manifest"]["report"]
    assert updated["snapshot"]["datasetRefs"] == original["document"]["snapshot"]["datasetRefs"]
    reader_filters = [dict(item) for item in operation["value"]]
    reader_filters[-1]["values"] = ["甲"]
    result = runtime.call("dashboard_view", {
        **board, "expectedRevision": updated["revision"], "filters": reader_filters,
        "componentIds": ["table-a", "table-b"], "responseMode": "patch",
    })
    tables = result["computed"]["tables"]
    assert [tables[key]["totalRows"] for key in ("table-a", "table-b")] == [4, 2]
    receipt = runtime.call("dashboard_edit_finish", {
        **board, "expectedRevision": updated["revision"], "batchId": batch["batch_id"],
    })
    assert receipt["ok"], receipt
    saved.write_text(json.dumps(runtime.call("dashboard_get", board)))
    expected = tmp_path / "expected.json"
    expected.write_text(json.dumps(operation["value"]))
    author("check-filters", saved, expected)
    # A targeted table condition silently widened to both tables must fail the parity check.
    operation["value"][-1]["componentIds"] = ["table-a", "table-b"]
    expected.write_text(json.dumps(operation["value"]))
    assert "category-b.componentIds" in author("check-filters", saved, expected, succeeds=False)
    before = request.read_bytes()
    path.write_text(json.dumps(operation))
    error = author("build", change, "--out", request, succeeds=False)
    assert "Table filter requires exactly one consumer" in error
    assert request.read_bytes() == before
