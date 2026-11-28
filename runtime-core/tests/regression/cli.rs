use charts_design_core::runtime::{cli, model, service::Service};
use serde_json::{json, Value};
use std::{fs, path::Path};

fn args(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| value.to_string()).collect()
}

fn invoke(root: &Path, values: &[&str]) -> charts_design_core::runtime::error::Result<()> {
    let mut arguments = vec![
        "--project-root".into(),
        root.join("project").to_string_lossy().into_owned(),
        "--runtime-root".into(),
        root.join("runtime").to_string_lossy().into_owned(),
    ];
    arguments.extend(args(values));
    cli::run(&arguments)
}

// @wu-test type=boundary | scope=native CLI parsing | protects=invalid numeric arguments or command-specific options reach stateful operations
#[test]
fn cli_rejects_invalid_flags_and_preserves_repeated_and_literal_arguments() {
    for input in [
        vec![],
        vec!["unknown"],
        vec!["init"],
        vec!["init", "board", "--demo=true"],
        vec!["get", "board", "--title", "changed"],
        vec!["serve", "--port", "65536"],
        vec!["serve", "--port", "-1"],
        vec!["serve", "--port", "NaN"],
        vec!["serve", "--idle-timeout", "-1"],
        vec!["serve", "--idle-timeout", "NaN"],
        vec!["share", "project", "board", "--hours", "0"],
        vec!["patch", "board", "--expected", "0"],
        vec!["remote", "upload", "--concurrency", "5"],
        vec!["remote", "upload", "--concurrency", "0"],
        vec!["remote", "delete"],
        vec!["init", "board", "--title"],
    ] {
        assert_eq!(
            cli::parse(&args(&input)).unwrap_err().code,
            "INVALID_ARGUMENT",
            "{input:?}"
        );
    }
    let parsed = cli::parse(&args(&[
        "server",
        "--token",
        "one",
        "--token=two",
        "--allowed-host",
        "localhost",
        "--allowed-host=127.0.0.1",
        "--port=0",
        "--stateless",
        "--insecure-no-auth",
    ]))
    .unwrap();
    assert_eq!(parsed["token"], json!(["one", "two"]));
    assert_eq!(parsed["allowed_host"], json!(["localhost", "127.0.0.1"]));
    assert_eq!(parsed["port"], 0);
    assert_eq!(parsed["stateless"], true);
    assert_eq!(parsed["insecure_no_auth"], true);
    assert_eq!(
        cli::parse(&args(&["init", "--", "--literal"])).unwrap()["id"],
        "--literal"
    );
    assert_eq!(
        cli::parse(&args(&["validate", "--file=board.json"])).unwrap()["file"],
        "board.json"
    );
    assert_eq!(
        cli::parse(&args(&["share", "sales", "board", "--hours=0.5"])).unwrap()["project"],
        "sales"
    );
    assert_eq!(
        cli::parse(&args(&["mcp", "--idle-timeout", "0"])).unwrap()["idle_timeout"],
        0.0
    );
    assert_eq!(
        cli::parse(&args(&[
            "migrate-project",
            "--board",
            "one",
            "--board",
            "two",
            "--apply"
        ]))
        .unwrap()["board"],
        json!(["one", "two"])
    );
}

// @wu-test type=integration | scope=native CLI authoring | protects=CLI patches, saved revisions and exports diverge from the shared runtime
#[test]
fn cli_edits_saves_restores_and_exports_the_same_project() {
    let directory = tempfile::tempdir().unwrap();
    let root = directory.path();
    invoke(root, &["init", "sales", "--title", "Sales"]).unwrap();
    let service = Service::new(&root.join("runtime"), None, Some(&root.join("project"))).unwrap();
    assert_eq!(
        service.store.get("sales", false).unwrap()["manifest"]["title"],
        "Sales"
    );
    let operations = root.join("operations.json");
    fs::write(&operations, serde_json::to_vec(&json!([
        {"op":"set_title","value":"Updated sales"},
        {"op":"put_source","id":"fixture","value":{"kind":"fixture","name":"Sales"}},
        {"op":"put_dataset","id":"sales","meta":{"sourceId":"fixture","fields":{"amount":{"type":"number"}}},"rows":[{"amount":10},{"amount":20}]},
        {"op":"put_component","id":"detail","value":{"kind":"table","title":"Details","datasetId":"sales"}}
    ])).unwrap()).unwrap();
    invoke(
        root,
        &[
            "patch",
            "sales",
            "--expected",
            "1",
            "--file",
            operations.to_str().unwrap(),
        ],
    )
    .unwrap();
    assert_eq!(service.store.get("sales", false).unwrap()["revision"], 2);
    assert_eq!(
        invoke(
            root,
            &[
                "patch",
                "sales",
                "--expected",
                "1",
                "--file",
                operations.to_str().unwrap()
            ]
        )
        .unwrap_err()
        .code,
        "REVISION_CONFLICT"
    );
    let request = root.join("submit.json");
    fs::write(&request, br#"{"dashboardId":"sales","expectedRevision":2}"#).unwrap();
    invoke(
        root,
        &[
            "call",
            "dashboard_submit",
            "--json-file",
            request.to_str().unwrap(),
        ],
    )
    .unwrap();
    for command in ["list", "catalog", "contract"] {
        invoke(root, &[command]).unwrap();
    }
    for command in ["get", "validate", "history"] {
        invoke(root, &[command, "sales"]).unwrap();
    }
    let output = root.join("exports/sales.json");
    invoke(
        root,
        &[
            "export",
            "sales",
            "--format",
            "json",
            "--output",
            output.to_str().unwrap(),
        ],
    )
    .unwrap();
    let exported: Value = serde_json::from_slice(&fs::read(&output).unwrap()).unwrap();
    assert_eq!(exported["manifest"]["title"], "Updated sales");
    assert_eq!(
        exported["snapshot"]["datasets"]["sales"],
        json!([{"amount":10},{"amount":20}])
    );
    invoke(root, &["validate", "--file", output.to_str().unwrap()]).unwrap();
    let csv = root.join("exports/sales.csv");
    invoke(
        root,
        &[
            "export",
            "sales",
            "--format",
            "csv",
            "--dataset",
            "sales",
            "--output",
            csv.to_str().unwrap(),
        ],
    )
    .unwrap();
    assert_eq!(
        fs::read_to_string(csv).unwrap(),
        "\u{feff}amount\r\n10\r\n20\r\n"
    );
    let html = root.join("exports/sales.html");
    invoke(
        root,
        &["export", "sales", "--output", html.to_str().unwrap()],
    )
    .unwrap();
    assert!(fs::read_to_string(html).unwrap().contains("Updated sales"));
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            fs::metadata(output).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }
    service.call("dashboard_patch", &json!({"dashboardId":"sales","expectedRevision":2,"operations":[{"op":"set_title","value":"Draft"}]})).unwrap();
    invoke(
        root,
        &["restore", "sales", "--expected", "3", "--revision", "2"],
    )
    .unwrap();
    assert_eq!(
        service.store.get("sales", false).unwrap()["manifest"]["title"],
        "Updated sales"
    );
}

// @wu-test type=integration | scope=native CLI creation modes | protects=report initialization and explicit demos accidentally share or lose content
#[test]
fn cli_report_import_and_invalid_requests_preserve_project_state() {
    let directory = tempfile::tempdir().unwrap();
    let root = directory.path();
    invoke(
        root,
        &["init", "report", "--mode", "report", "--title", "Research"],
    )
    .unwrap();
    invoke(root, &["init", "demo", "--demo"]).unwrap();
    invoke(root, &["init", "report-demo", "--demo", "--mode", "report"]).unwrap();
    let service = Service::new(&root.join("runtime"), None, Some(&root.join("project"))).unwrap();
    assert_eq!(
        service.store.get("report", false).unwrap()["manifest"]["viewMode"],
        "report"
    );
    assert_eq!(
        service.store.get("report", false).unwrap()["manifest"]["components"],
        json!({})
    );
    assert!(
        !service.store.get("demo", false).unwrap()["manifest"]["components"]
            .as_object()
            .unwrap()
            .is_empty()
    );
    let doc = model::new_document("imported", "Imported").unwrap();
    let path = root.join("imported.json");
    fs::write(&path, serde_json::to_vec(&doc).unwrap()).unwrap();
    invoke(
        root,
        &["import", "imported", "--file", path.to_str().unwrap()],
    )
    .unwrap();
    assert_eq!(
        service.store.get("imported", false).unwrap()["manifest"]["title"],
        "Imported"
    );
    for input in [
        vec!["init", "invalid", "--mode", "unknown"],
        vec!["serve", "--view"],
        vec![
            "export",
            "imported",
            "--format",
            "pdf",
            "--output",
            path.to_str().unwrap(),
        ],
    ] {
        assert_eq!(invoke(root, &input).unwrap_err().code, "INVALID_ARGUMENT");
    }
    assert_eq!(
        invoke(
            root,
            &["call", "not_a_tool", "--json-file", path.to_str().unwrap()]
        )
        .unwrap_err()
        .code,
        "UNKNOWN_TOOL"
    );
    assert!(service.store.get("invalid", false).is_err());
    cli::run(&args(&["--help"])).unwrap();
    cli::run(&args(&["--version"])).unwrap();
    assert_eq!(
        cli::run(&args(&[
            "--root",
            root.join("standalone").to_str().unwrap(),
            "init",
            "missing-project"
        ]))
        .unwrap_err()
        .code,
        "PROJECT_REQUIRED"
    );
}

// @wu-test type=integration | scope=workspace import | protects=legacy chart/KPI/table source and layout are lost or file references escape the workspace
#[test]
fn workspace_import_retains_original_content_and_bounds_paths() {
    let directory = tempfile::tempdir().unwrap();
    let root = directory.path();
    for (name, value) in [
        (
            "dashboard.json",
            json!({"schemaVersion":1,"meta":{"title":"Legacy"},"components":{"charts":["chart.json","wide.json"],"kpis":["kpi.json"],"table":"table.json","filters":"filters.json"}}),
        ),
        (
            "chart.json",
            json!({"id":"trend","title":"Trend","code":"custom-trend","renderer":"echarts","type":"line","data":{"values":[1,2]},"echarts":{"xAxis":{"type":"category","data":["A","B"]},"yAxis":{"type":"value"},"series":[{"type":"line","data":[1,2]}]}}),
        ),
        (
            "wide.json",
            json!({"id":"wide","title":"Wide","colSpan":2,"code":"custom-wide","renderer":"html","html":"<div>Wide</div>"}),
        ),
        (
            "kpi.json",
            json!({"id":"revenue","type":"mc01","label":"Revenue","value":"30"}),
        ),
        (
            "table.json",
            json!({"id":"detail","title":"Details","columns":[{"key":"v","label":"Value"}],"rows":[{"v":30}]}),
        ),
        ("filters.json", json!([{"id":"region","values":["East"]}])),
    ] {
        fs::write(root.join(name), serde_json::to_vec(&value).unwrap()).unwrap();
    }
    let (doc, notes) = cli::import_workspace(root, "legacy").unwrap();
    assert_eq!(
        doc["manifest"]["components"]["trend"]["config"]["data"],
        json!({"values":[1, 2]})
    );
    assert_eq!(
        doc["manifest"]["originalWorkspace"]["filters"][0]["values"],
        json!(["East"])
    );
    assert!(!notes.as_array().unwrap().is_empty());
    assert_eq!(doc["manifest"]["layout"]["desktop"][0]["id"], "revenue");
    assert!(doc["manifest"]["layout"]["mobile"]
        .as_array()
        .unwrap()
        .iter()
        .all(|p| p["w"] == 4));
    invoke(
        root,
        &[
            "import-workspace",
            "legacy",
            "--path",
            root.to_str().unwrap(),
        ],
    )
    .unwrap();
    #[cfg(unix)]
    {
        let outside = tempfile::NamedTempFile::new().unwrap();
        fs::remove_file(root.join("chart.json")).unwrap();
        std::os::unix::fs::symlink(outside.path(), root.join("chart.json")).unwrap();
        assert_eq!(
            cli::import_workspace(root, "unsafe").unwrap_err().code,
            "PATH_OUTSIDE_WORKSPACE"
        );
    }
    fs::write(root.join("dashboard.json"), br#"{"schemaVersion":2}"#).unwrap();
    assert_eq!(
        cli::import_workspace(root, "invalid").unwrap_err().code,
        "INVALID_ARGUMENT"
    );
}

// @wu-test type=boundary | scope=native remote endpoint configuration | protects=credentials are sent to insecure URLs or invalid configuration creates an apparent successful output
#[test]
fn remote_cli_rejects_insecure_endpoints_and_missing_credentials() {
    let directory = tempfile::tempdir().unwrap();
    let output = directory.path().join("result.json");
    for (endpoint, token, expected) in [
        ("", "test-token", "CHARTS_MCP_URL must"),
        (
            "http://127.0.0.1:9/mcp",
            "test-token",
            "CHARTS_MCP_URL must",
        ),
        (
            "https://user:secret@127.0.0.1:9/mcp",
            "test-token",
            "CHARTS_MCP_URL must",
        ),
        (
            "https://127.0.0.1:9/mcp#fragment",
            "test-token",
            "CHARTS_MCP_URL must",
        ),
        ("https://127.0.0.1:9/mcp", "", "CHARTS_SERVER_TOKENS must"),
        (
            "https://127.0.0.1:9/mcp",
            "test\r\ntoken",
            "CHARTS_SERVER_TOKENS must",
        ),
        (
            "https://127.0.0.1:9/mcp",
            "test-token",
            "Could not confirm the MCP response",
        ),
    ] {
        let result = std::process::Command::new(env!("CARGO_BIN_EXE_charts-design-core"))
            .args([
                "remote",
                "read",
                "--project",
                "project",
                "--dashboard",
                "sales",
                "--output",
            ])
            .arg(&output)
            .env("CHARTS_MCP_URL", endpoint)
            .env("CHARTS_SERVER_TOKENS", token)
            .env("NO_PROXY", "127.0.0.1")
            .output()
            .unwrap();
        assert!(!result.status.success(), "{endpoint}");
        let error = String::from_utf8(result.stderr).unwrap();
        assert!(error.contains(expected), "{error}");
        assert!(!output.exists());
        assert!(result.stdout.is_empty());
        assert!(!error.contains("user:secret"));
    }
}
