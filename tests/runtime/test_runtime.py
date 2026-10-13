import json
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from dashboard_runtime import assets
from dashboard_runtime.demo import document
from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.model import DashboardError, apply_operations, validate
from dashboard_runtime.query import QueryRunner
from dashboard_runtime.service import Service


@pytest.fixture
def service(tmp_path):
    s = Service(tmp_path / "store")
    s.store.create("demo", "Historical compatibility document", document())
    return s


def test_contract_and_ratio_definition():
    doc = document()
    assert validate(doc)
    assert doc["manifest"]["metrics"]["load-factor"]["aggregation"] == "ratio"
    assert len(doc["snapshot"]["datasets"]["sales"]) == 6


@pytest.mark.parametrize("bad", ["scatter", "heatmap", "waterfall", "unknown"])
def test_incompatible_charts_rejected(bad):
    with pytest.raises(DashboardError):
        apply_operations(
            document(), [{"op": "set_chart", "id": "trend", "chartType": bad}]
        )


@pytest.mark.parametrize("kind", ["bar", "line", "area", "pie", "funnel"])
def test_compatible_charts(kind):
    assert (
        apply_operations(
            document(), [{"op": "set_chart", "id": "trend", "chartType": kind}]
        )["manifest"]["components"]["trend"]["chartType"]
        == kind
    )


def test_atomic_rollback(service):
    with pytest.raises(DashboardError):
        service.call(
            "dashboard_patch",
            {
                "dashboardId": "demo",
                "expectedRevision": 1,
                "operations": [
                    {"op": "set_title", "value": "Must not persist"},
                    {"op": "set_chart", "id": "trend", "chartType": "scatter"},
                ],
            },
        )
    assert service.store.get("demo")["revision"] == 1
    assert "Must not" not in service.store.get("demo")["manifest"]["title"]


def test_concurrent_edits_have_one_winner(service):
    def edit(n):
        try:
            return service.call(
                "dashboard_patch",
                {
                    "dashboardId": "demo",
                    "expectedRevision": 1,
                    "operations": [{"op": "set_title", "value": str(n)}],
                },
            )
        except DashboardError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, [1, 2]))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert "REVISION_CONFLICT" in results


def test_restore_creates_new_revision(service):
    old = service.store.get("demo")
    service.store.mutate("demo", 1, [{"op": "set_title", "value": "New title"}])
    restored = service.store.mutate("demo", 2, restore_revision=1)
    assert restored["revision"] == 3
    assert restored["manifest"] == old["manifest"]
    assert len(service.store.history("demo")) == 3


def test_layout_overlap_and_wrong_field():
    doc = document()
    doc["manifest"]["layout"]["desktop"][1]["x"] = 0
    with pytest.raises(DashboardError):
        validate(doc)
    doc = document()
    doc["manifest"]["components"]["trend"]["x"] = "missing"
    with pytest.raises(DashboardError):
        validate(doc)


def test_remove_cleans_filters_and_all_layouts():
    doc = apply_operations(document(), [{"op": "remove_component", "id": "trend"}])
    assert "trend" not in doc["manifest"]["filters"][0]["componentIds"]
    for layout in doc["manifest"]["layout"].values():
        assert all(p["id"] != "trend" for p in layout)


def test_nan_and_wrong_scale():
    doc = document()
    doc["snapshot"]["datasets"]["sales"][0]["revenue"] = float("nan")
    with pytest.raises(DashboardError):
        validate(doc)
    doc = document()
    doc["manifest"]["metrics"]["load-factor"]["scale"] = "percentage-points"
    with pytest.raises(DashboardError):
        validate(doc)


def test_declared_sources_cannot_claim_runtime_execution(service):
    result = service.call(
        "dashboard_patch",
        {
            "dashboardId": "demo",
            "expectedRevision": 1,
            "operations": [
                {
                    "op": "put_source",
                    "id": "extra",
                    "value": {"kind": "file", "verification": "runtime-executed"},
                }
            ],
        },
    )
    assert (
        result["document"]["manifest"]["sources"]["extra"]["verification"] == "supplied"
    )


def test_csv_import_and_inspect(service):
    result = service.call(
        "dataset_import",
        {
            "dashboardId": "demo",
            "expectedRevision": 1,
            "datasetId": "imported",
            "csvText": "region,value,postcode\nEast,12,00123\nSouth,10,00234",
        },
    )
    row = result["document"]["snapshot"]["datasets"]["imported"][0]
    assert row == {"region": "East", "value": 12, "postcode": "00123"}
    semantic = service.call(
        "semantic_inspect", {"dashboardId": "demo", "componentId": "load"}
    )
    assert semantic["metrics"]["load-factor"]["denominator"] == "seats"
    assert (
        service.call("query_inspect", {"dashboardId": "demo", "componentId": "trend"})[
            "source"
        ]["kind"]
        == "fixture"
    )


@pytest.fixture
def runner(tmp_path):
    db = tmp_path / "source.sqlite"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE sales (region TEXT, value REAL); INSERT INTO sales VALUES ('East',12),('South',10);"
    )
    con.close()
    config = tmp_path / "sources.json"
    config.write_text(json.dumps({"analytics": {"engine": "sqlite", "path": str(db)}}))
    return QueryRunner(config), config


def test_readonly_sql_and_captured_provenance(runner):
    query, _ = runner
    rows, fields, source = query.execute(
        "analytics",
        "SELECT region, value FROM sales WHERE value > :minimum",
        {"minimum": 11},
    )
    assert rows == [{"region": "East", "value": 12}]
    assert fields["value"]["type"] == "number"
    assert source["query"]["parameters"] == {"minimum": 11}
    assert source["verification"] == "runtime-executed"


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM sales",
        "DROP TABLE sales",
        "PRAGMA table_info(sales)",
        "ATTACH DATABASE '/tmp/forbidden.sqlite' AS other",
        "SELECT load_extension('bad')",
        "SELECT 1; SELECT 2",
        "CREATE TABLE evil (x)",
    ],
)
def test_sql_side_effects_rejected(runner, sql):
    with pytest.raises(DashboardError):
        runner[0].execute("analytics", sql)


def test_sql_alias_and_row_limits(runner):
    with pytest.raises(DashboardError):
        runner[0].execute("/etc/passwd", "SELECT 1")
    with pytest.raises(DashboardError):
        runner[0].execute(
            "analytics",
            "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<10001) SELECT x FROM n",
        )


def test_query_saved_atomically(tmp_path, runner):
    s = Service(tmp_path / "newstore", runner[1])
    s.store.create("empty", "Query test")
    result = s.call(
        "query_execute",
        {
            "dashboardId": "empty",
            "expectedRevision": 1,
            "datasetId": "result",
            "connection": "analytics",
            "sql": "SELECT * FROM sales",
        },
    )
    assert result["document"]["revision"] == 2
    source = list(result["document"]["manifest"]["sources"].values())[0]
    assert source["verification"] == "runtime-executed"
    assert source["query"]["sql"] == "SELECT * FROM sales"


def test_export_escapes_script_in_data(tmp_path, monkeypatch):
    tmp_path.joinpath("app.js").write_text("window.loaded=true;")
    tmp_path.joinpath("app.css").write_text("body{}")
    monkeypatch.setattr(assets, "DIST", tmp_path)
    doc = document()
    doc["manifest"]["title"] = "</script><script>alert(1)</script>"
    text = assets.export_document(doc)
    assert "<script>alert(1)</script>" not in text
    assert "\\u003c/script\\u003e" in text


def test_http_auth_origin_and_conflict(service):
    server = RuntimeHTTPServer(service, 0, token="testing-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def request(tool, args, headers=None):
        r = Request(
            base + "/api/tools/" + tool,
            data=json.dumps(args).encode(),
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        return json.load(urlopen(r))

    try:
        with pytest.raises(HTTPError) as e:
            request("dashboard_list", {})
        assert e.value.code == 401
        with pytest.raises(HTTPError) as e:
            request(
                "dashboard_list",
                {},
                {
                    "Authorization": "Bearer testing-token",
                    "Origin": "https://evil.example",
                },
            )
        assert e.value.code == 403
        result = request(
            "dashboard_get",
            {"dashboardId": "demo"},
            {"Authorization": "Bearer testing-token"},
        )
        assert result["document"]["revision"] == 1
        with pytest.raises(HTTPError) as e:
            request(
                "dashboard_patch",
                {
                    "dashboardId": "demo",
                    "expectedRevision": 2,
                    "operations": [{"op": "set_title", "value": "oops"}],
                },
                {"Authorization": "Bearer testing-token"},
            )
        assert e.value.code == 409
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_cli_roundtrip(tmp_path):
    def run(*args):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "dashboard_runtime",
                "--root",
                str(tmp_path / "cli"),
                *args,
            ],
            text=True,
            capture_output=True,
        )

    result = run("init", "sample", "--demo")
    assert result.returncode == 0, result.stderr
    assert json.loads(run("validate", "sample").stdout) == {"valid": True}
    assert run("init", "sample").returncode == 2
    export = tmp_path / "doc.json"
    assert (
        run("export", "sample", "--format", "json", "--output", str(export)).returncode
        == 0
    )
    assert json.loads(export.read_text())["id"] == "sample"


def test_page_metadata_and_description_contract():
    doc = apply_operations(
        document(),
        [
            {
                "op": "set_meta",
                "value": {
                    "subtitle": "Business overview",
                    "org": "Operations",
                    "system": "Finance",
                    "statusText": "Monthly",
                },
            }
        ],
    )
    assert doc["manifest"]["meta"]["subtitle"] == "Business overview"
    assert (
        apply_operations(doc, [{"op": "set_meta", "value": {}}])["manifest"]["meta"]
        == {}
    )
    for bad in ({"subtitle": 7}, {"subtitle": "x" * 1001}, {"unknown": "value"}):
        with pytest.raises(DashboardError):
            apply_operations(doc, [{"op": "set_meta", "value": bad}])
    doc["manifest"]["components"]["total"]["subtitle"] = 7
    with pytest.raises(DashboardError):
        validate(doc)


@pytest.mark.parametrize(
    "presentation",
    [
        {"type": "mc99"},
        {"type": {}},
        {"type": "mc03"},
        {"type": "mc03", "timeField": "missing"},
        {"type": "mc06"},
    ],
)
def test_invalid_kpi_presentation_rejected(presentation):
    doc = document()
    doc["manifest"]["components"]["total"]["presentation"] = presentation
    with pytest.raises(DashboardError):
        validate(doc)


def test_annotations_validate_and_persist(service):
    note = {'id': 'review-1', 'componentId': 'trend', 'text': '核对收入', 'createdAt': '2026-10-12T10:00:00Z'}
    result = service.call('dashboard_patch', {'dashboardId': 'demo', 'expectedRevision': 1, 'operations': [{'op': 'set_annotations', 'value': [note]}]})
    assert result['document']['manifest']['annotations'] == [note]
    assert service.store.get('demo')['manifest']['annotations'] == [note]
    for invalid in [{**note, 'text': ' '}, {**note, 'componentId': 'missing'}, {**note, 'text': 'x' * 4001}]:
        with pytest.raises(DashboardError):
            service.call('dashboard_patch', {'dashboardId': 'demo', 'expectedRevision': 2, 'operations': [{'op': 'set_annotations', 'value': [invalid]}]})
    assert service.store.get('demo')['revision'] == 2


def test_mcp_rejects_extra_chart_system(tmp_path):
    service = Service(tmp_path)
    with pytest.raises(DashboardError) as failure:
        service.call('dashboard_create', {'dashboardId': 'extra', 'document': document()})
    assert failure.value.code == 'UNSUPPORTED_CHART_FAMILY'
    assert service.call('dashboard_list', {}) == {'dashboards': []}
    service.call('dashboard_create', {'dashboardId': 'original'})
    native = document()['manifest']['components']['trend']
    with pytest.raises(DashboardError):
        service.call('dashboard_patch', {'dashboardId': 'original', 'expectedRevision': 1, 'operations': [{'op': 'put_component', 'id': 'extra', 'value': native}]})
    assert service.store.get('original')['revision'] == 1
    assert 'chartType' not in service.call('chart_declarations', {})
    assert len(service.call('chart_catalog', {})['charts']) == 40
    assert all('code' in item and 'type' not in item for item in service.call('chart_catalog', {})['charts'])
