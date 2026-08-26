import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "cli.js"


def run_cli(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(CLI), *(str(arg) for arg in args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def write_html(path: Path, body: str, head: str = "") -> None:
    path.write_text(
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width"><title>Board</title>'
        f"{head}</head><body>{body}</body></html>",
        encoding="utf-8",
    )


def test_inspect_html_reports_broken_dom_references_and_local_assets(tmp_path: Path) -> None:
    html = tmp_path / "board.html"
    write_html(html, '<label for="missing">Metric</label><a href="#missing">Open</a>', '<script src="missing.js"></script>')

    result = run_cli("dashboard", "inspect-html", html, "--strict", "--json")

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["command"] == "dashboard.inspect-html"
    assert {issue["code"] for issue in payload["errors"]} == {"ASSET_NOT_FOUND", "DOM_REFERENCE_MISSING"}


def test_inspect_html_enforces_preservation_manifest(tmp_path: Path) -> None:
    html = tmp_path / "board.html"
    manifest = tmp_path / "preservation.json"
    write_html(html, '<main id="revenue"><h1>Revenue</h1></main>')
    manifest.write_text(json.dumps({
        "requiredIds": ["revenue", "profit"],
        "requiredText": ["Revenue", "Board approved"],
        "forbiddenText": ["Revenue"],
        "components": [{"id": "profit-chart"}],
    }), encoding="utf-8")

    result = run_cli("dashboard", "inspect-html", html, "--manifest", manifest, "--json")

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert {issue["code"] for issue in payload["errors"]} == {
        "MANIFEST_COMPONENT_MISSING", "MANIFEST_ID_MISSING", "PRESERVED_TEXT_MISSING", "FORBIDDEN_TEXT_FOUND"
    }
    assert payload["evidence"]["manifest"] == str(manifest.resolve())


def test_compare_html_reports_preservation_regressions(tmp_path: Path) -> None:
    before = tmp_path / "before.html"
    after = tmp_path / "after.html"
    write_html(before, '<main id="revenue"><h1>Revenue</h1><p>Board approved</p></main>')
    write_html(after, '<main id="revenue"><h1>Revenue</h1></main>')

    result = run_cli("dashboard", "compare-html", before, after, "--json")

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["command"] == "dashboard.compare-html"
    assert any(issue["code"] == "PRESERVED_TEXT_MISSING" and issue["path"] == "text:Board approved" for issue in payload["errors"])


def test_runtime_mode_has_explicit_machine_readable_failure(tmp_path: Path) -> None:
    html = tmp_path / "board.html"
    write_html(html, '<main id="app">Board</main>')

    result = run_cli("dashboard", "inspect-html", html, "--runtime", "--json")

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["errors"] == [{
        "code": "RUNTIME_UNSUPPORTED",
        "path": "runtime",
        "message": "Runtime inspection requires a browser adapter and is not available in this offline CLI.",
    }]


def test_validate_rejects_unknown_kpi_type_and_mismatched_chart_vectors(tmp_path: Path) -> None:
    workspace = tmp_path / "board"
    (workspace / "kpis").mkdir(parents=True)
    (workspace / "charts").mkdir()
    (workspace / "dashboard.json").write_text(json.dumps({
        "schemaVersion": 1, "meta": {"title": "Board"},
        "components": {"filters": "filters.json", "kpis": ["kpis/k.json"], "charts": ["charts/c.json"], "table": "table.json"},
    }), encoding="utf-8")
    (workspace / "filters.json").write_text("[]", encoding="utf-8")
    (workspace / "table.json").write_text('{"columns":[],"rows":[]}', encoding="utf-8")
    (workspace / "kpis" / "k.json").write_text('{"id":"k","type":"mc10","label":"Revenue","value":"1","unit":"元"}', encoding="utf-8")
    (workspace / "charts" / "c.json").write_text('{"id":"c","code":"c01","title":"Trend","unit":"元","data":{"categories":["A","B"],"values":[1]}}', encoding="utf-8")

    result = run_cli("dashboard", "validate", workspace, "--strict", "--json")

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert {error["code"] for error in payload["errors"]} >= {"KPI_TYPE_INVALID", "CHART_DATA_LENGTH_MISMATCH"}


def test_validate_rejects_invalid_chart_data_collection_shapes(tmp_path: Path) -> None:
    workspace = tmp_path / "board"
    (workspace / "charts").mkdir(parents=True)
    (workspace / "dashboard.json").write_text(json.dumps({
        "schemaVersion": 1, "meta": {"title": "Board"},
        "components": {"filters": "filters.json", "kpis": [], "charts": ["charts/c.json"], "table": "table.json"},
    }), encoding="utf-8")
    (workspace / "filters.json").write_text("[]", encoding="utf-8")
    (workspace / "table.json").write_text('{"columns":[],"rows":[]}', encoding="utf-8")
    (workspace / "charts" / "c.json").write_text('{"id":"c","code":"r01","title":"Network","unit":"count","data":{"nodes":{},"links":[],"series":{}}}', encoding="utf-8")

    result = run_cli("dashboard", "validate", workspace, "--strict", "--json")

    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert [error["code"] for error in payload["errors"]].count("CHART_DATA_ARRAY_REQUIRED") == 2


def test_build_inspect_html_is_a_failing_gate(tmp_path: Path) -> None:
    workspace = tmp_path / "board"
    output = tmp_path / "board.html"
    manifest = tmp_path / "preservation.json"
    assert run_cli("dashboard", "init", workspace, "--title", "Board", "--json").returncode == 0
    assert run_cli("dashboard", "add", "kpi", workspace, "revenue", "--label", "Revenue", "--value", "1", "--unit", "元", "--json").returncode == 0
    manifest.write_text('{"requiredText":["Legal approval marker"]}', encoding="utf-8")

    result = run_cli("dashboard", "build", workspace, "--output", output, "--inspect-html", "--manifest", manifest, "--json")

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["command"] == "dashboard.build"
    assert payload["inspection"]["ok"] is False
    assert payload["errors"][0]["code"] == "PRESERVED_TEXT_MISSING"
