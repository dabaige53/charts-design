use super::*;

fn projects(root: &std::path::Path, project: bool) -> LocalProjects {
    LocalProjects::new(
        Service::new(
            &root.join("runtime"),
            None,
            project.then(|| root.join("default")).as_deref(),
        )
        .unwrap(),
        Lifetime::new(0.0).unwrap(),
    )
}

// @wu-test type=integration | scope=local MCP project routing | protects=absolute project selectors remain request scoped, normalize to one service and cannot select files or relative paths
#[test]
fn local_project_resolution_is_cached_and_never_changes_the_default() {
    let root = tempfile::tempdir().unwrap();
    let gateway = projects(root.path(), true);
    let (default, initial) = gateway.resolve(json!({"dashboardId":"main"})).unwrap();
    assert_eq!(initial, json!({"dashboardId":"main"}));
    let path = root.path().join("nested/project");
    let (selected, args) = gateway
        .resolve(json!({"projectRoot":path,"dashboardId":"main"}))
        .unwrap();
    assert_eq!(args, json!({"dashboardId":"main"}));
    assert_eq!(selected.project_root.as_ref(), Some(&path));
    assert_ne!(selected.store.runtime_root, default.store.runtime_root);
    let (again, _) = gateway
        .resolve(json!({"projectRoot":path.join("../project")}))
        .unwrap();
    assert!(Arc::ptr_eq(&selected, &again));
    let (unchanged, _) = gateway.resolve(json!({})).unwrap();
    assert!(Arc::ptr_eq(&default, &unchanged));
    let decorated = gateway
        .decorate("dashboard_get", &json!({}), json!({"ok":true}), &selected)
        .unwrap();
    assert_eq!(decorated["projectRoot"], json!(path));
    assert!(gateway.previews.lock().unwrap().is_empty());
    assert_eq!(
        gateway.resolve(json!([])).err().unwrap().code,
        "INVALID_ARGUMENT"
    );
    for value in [json!(""), json!("relative/path"), json!(null), json!(42)] {
        assert_eq!(
            gateway
                .resolve(json!({"projectRoot":value}))
                .err()
                .unwrap()
                .code,
            "INVALID_PROJECT"
        );
    }
    let file = root.path().join("file");
    std::fs::write(&file, b"not a directory").unwrap();
    assert_eq!(
        gateway
            .resolve(json!({"projectRoot":file}))
            .err()
            .unwrap()
            .code,
        "INVALID_PROJECT"
    );
}

// @wu-test type=behavior | scope=MCP idle accounting | protects=in-flight requests prevent expiration and dropping the final activity restarts the idle interval
#[test]
fn lifetime_uses_active_requests_and_rejects_invalid_durations() {
    for seconds in [-1.0, f64::INFINITY, f64::NAN] {
        assert_eq!(
            Lifetime::new(seconds).err().unwrap().code,
            "INVALID_ARGUMENT"
        );
    }
    let unlimited = Lifetime::new(0.0).unwrap();
    assert_eq!(unlimited.seconds(), None);
    assert!(!unlimited.expired());
    let bounded = Lifetime::new(60.0).unwrap();
    assert_eq!(bounded.seconds(), Some(60.0));
    bounded.state.lock().unwrap().0 = Instant::now() - Duration::from_secs(61);
    assert!(bounded.expired());
    let first = bounded.activity();
    let second = bounded.activity();
    bounded.state.lock().unwrap().0 = Instant::now() - Duration::from_secs(61);
    assert!(!bounded.expired());
    drop(first);
    assert_eq!(bounded.state.lock().unwrap().1, 1);
    drop(second);
    assert_eq!(bounded.state.lock().unwrap().1, 0);
    assert!(!bounded.expired());
}

// @wu-test type=integration | scope=MCP write response modes | protects=default writes return compact receipts, full mode preserves the document and subsequent reads address the selected project
#[test]
fn mcp_writes_validate_arguments_and_preserve_explicit_response_modes() {
    let root = tempfile::tempdir().unwrap();
    let gateway = Arc::new(projects(root.path(), false));
    let mcp = Mcp::new(gateway.clone(), Lifetime::new(0.0).unwrap()).unwrap();
    assert_eq!(
        mcp.call("missing_tool", json!({})).unwrap_err().code,
        "UNKNOWN_TOOL"
    );
    assert_eq!(
        mcp.call(
            "dashboard_create",
            json!({"dashboardId":"main","title":"Main"})
        )
        .unwrap_err()
        .code,
        "PROJECT_REQUIRED"
    );
    let project = root.path().join("chosen project");
    let created = mcp
        .call(
            "dashboard_create",
            json!({"projectRoot":project,"dashboardId":"main","title":"Main"}),
        )
        .unwrap();
    assert!(created.get("document").is_none());
    assert_eq!(created["dashboardId"], "main");
    assert_eq!(created["revision"], 1);
    assert_eq!(created["projectRoot"], json!(project));
    assert_eq!(mcp.call("dashboard_patch", json!({"projectRoot":project,"dashboardId":"main","expectedRevision":1,"operations":[],"responseMode":"invalid"})).unwrap_err().code, "INVALID_ARGUMENT");
    let updated = mcp.call("dashboard_patch", json!({"projectRoot":project,"dashboardId":"main","expectedRevision":1,"operations":[{"op":"set_title","value":"Reviewed"}],"responseMode":"full"})).unwrap();
    assert_eq!(updated["document"]["manifest"]["title"], "Reviewed");
    assert_eq!(updated["document"]["revision"], 2);
    let read = mcp
        .call(
            "dashboard_get",
            json!({"projectRoot":project,"dashboardId":"main"}),
        )
        .unwrap();
    assert_eq!(read["document"]["revision"], 2);
    let wrapped = tool_result(read.clone()).unwrap();
    assert_eq!(wrapped.is_error, Some(false));
    assert_eq!(wrapped.structured_content, Some(read));
    assert!(mcp
        .public()
        .iter()
        .all(|tool| contract::author_tool(tool.name.as_ref())));
    assert!(mcp.get_tool("dashboard_patch").is_some());
    assert!(mcp.get_tool("missing").is_none());
    let info = serde_json::to_value(mcp.get_info()).unwrap();
    assert_eq!(info["serverInfo"]["name"], "charts-design");
    assert!(info["capabilities"]["resources"].is_object());
}

// @wu-test type=integration | scope=MCP resources and project-bound transport | protects=complete large results are recovered only from valid resource IDs and resource discovery separates client and author tools
#[test]
fn resources_validate_routes_and_restore_project_bound_results() {
    let root = tempfile::tempdir().unwrap();
    let gateway = Arc::new(projects(root.path(), true));
    let mcp = Mcp::new(gateway.clone(), Lifetime::new(0.0).unwrap()).unwrap();
    for uri in [
        "charts://catalog",
        "charts://contract",
        "charts://declarations",
        "charts://layouts",
        "charts://examples",
        "charts://examples/academic-report",
    ] {
        let resource = mcp.resource(uri).unwrap();
        assert_eq!(resource["uri"], uri);
        assert_eq!(resource["mimeType"], "application/json");
        let value: Value = serde_json::from_str(resource["text"].as_str().unwrap()).unwrap();
        if uri == "charts://contract" {
            assert!(value["tools"].get("dashboard_submit").is_some());
            assert!(value["tools"].get("dashboard_patch").is_none());
            assert!(value["clientTools"].get("dashboard_patch").is_some());
        } else {
            assert!(value.is_object() || value.is_array());
        }
    }
    let ui = mcp.resource(&assets::ui_resource_uri()).unwrap();
    assert_eq!(ui["mimeType"], "text/html;profile=mcp-app");
    assert!(ui["text"]
        .as_str()
        .unwrap()
        .contains("window.__chartsBoot="));
    assert_eq!(ui["_meta"]["ui"]["csp"]["connectDomains"], json!([]));
    assert_eq!(
        mcp.resource("ui://charts-design/old.html")
            .unwrap_err()
            .code,
        "UI_BUILD_EXPIRED"
    );
    assert_eq!(
        mcp.resource("charts://missing").unwrap_err().code,
        "NOT_FOUND"
    );
    let project = root.path().join("results & reports");
    let large = "审阅完整结果".repeat(20000);
    let document = super::super::model::apply_operations(
        &super::super::model::new_document("large", "Complete review").unwrap(),
        &[json!({"op":"put_component","id":"report","value":{"kind":"text","title":"Complete review","text":large}})],
    )
    .unwrap();
    let manifest = mcp
        .call(
            "dashboard_create",
            json!({"projectRoot":project,"dashboardId":"large","document":document,"responseMode":"full"}),
        )
        .unwrap();
    let id = manifest["transport"]["requestId"].as_str().unwrap();
    let query = url::form_urlencoded::Serializer::new(String::new())
        .append_pair("projectRoot", project.to_str().unwrap())
        .finish();
    let uri = format!("charts://result/{id}?{query}");
    assert_eq!(manifest["transport"]["resourceUri"], uri);
    let resource = mcp.resource(&uri).unwrap();
    let recovered: Value = serde_json::from_str(resource["text"].as_str().unwrap()).unwrap();
    assert_eq!(
        recovered["document"]["manifest"]["components"]["report"]["text"],
        large
    );
    assert_eq!(recovered["document"]["revision"], 1);
    assert_eq!(recovered["projectRoot"], json!(project));
    for suffix in [
        "?unexpected=1",
        "?projectRoot=",
        "?projectRoot=a&projectRoot=b",
        "#fragment",
    ] {
        assert_eq!(
            mcp.resource(&format!("charts://result/{id}{suffix}"))
                .unwrap_err()
                .code,
            "INVALID_RESOURCE"
        );
    }
    for id in ["short".to_owned(), "A".repeat(32), "a".repeat(33)] {
        assert_eq!(
            mcp.resource(&format!("charts://result/{id}"))
                .unwrap_err()
                .code,
            "INVALID_RESOURCE"
        );
    }
    let mut error = Error::new("TEST_CODE", "Trace me");
    error.request_id = Some("trace".into());
    let protocol = serde_json::to_value(protocol_error(error)).unwrap();
    assert_eq!(
        protocol["data"],
        json!({"code":"TEST_CODE","requestId":"trace"})
    );
    assert_eq!(
        tool_result(json!({"ok":false,"error":{"code":"TEST_CODE"}}))
            .unwrap()
            .is_error,
        Some(true)
    );
}

// @wu-test type=integration | scope=MCP protocol handlers | protects=resource listing, resource errors and tool failures retain their protocol shape over the official in-memory transport
#[tokio::test]
async fn protocol_lists_resources_reads_contents_and_returns_tool_errors() {
    use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
    let root = tempfile::tempdir().unwrap();
    let mcp = Mcp::new(
        Arc::new(projects(root.path(), true)),
        Lifetime::new(0.0).unwrap(),
    )
    .unwrap();
    let (client, server_io) = tokio::io::duplex(1024 * 1024);
    let server =
        tokio::spawn(async move { mcp.serve(server_io).await.unwrap().waiting().await.unwrap() });
    let (reader, mut writer) = tokio::io::split(client);
    let mut reader = BufReader::new(reader);
    let requests = [
        json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"resource-contract-test","version":"1"}}}),
        json!({"jsonrpc":"2.0","id":2,"method":"resources/list","params":{}}),
        json!({"jsonrpc":"2.0","id":3,"method":"resources/read","params":{"uri":"charts://layouts"}}),
        json!({"jsonrpc":"2.0","id":4,"method":"resources/read","params":{"uri":"charts://missing"}}),
        json!({"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"runtime_keepalive","arguments":{}}}),
        json!({"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"dashboard_get","arguments":{"dashboardId":"absent"}}}),
    ];
    for request in requests {
        writer
            .write_all(format!("{request}\n").as_bytes())
            .await
            .unwrap();
        writer.flush().await.unwrap();
        let mut line = String::new();
        tokio::time::timeout(Duration::from_secs(10), reader.read_line(&mut line))
            .await
            .unwrap()
            .unwrap();
        let response: Value = serde_json::from_str(&line).unwrap();
        assert_eq!(response["id"], request["id"]);
        match request["id"].as_i64().unwrap() {
            1 => {
                assert_eq!(response["result"]["serverInfo"]["name"], "charts-design");
                writer
                    .write_all(b"{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}\n")
                    .await
                    .unwrap();
            }
            2 => assert!(response["result"]["resources"]
                .as_array()
                .unwrap()
                .iter()
                .any(|v| v["uri"] == "charts://contract")),
            3 => assert_eq!(response["result"]["contents"][0]["uri"], "charts://layouts"),
            4 => assert_eq!(response["error"]["data"]["code"], "NOT_FOUND"),
            5 => assert_eq!(response["result"]["isError"], false),
            6 => {
                assert_eq!(response["result"]["isError"], true);
                assert_eq!(
                    response["result"]["structuredContent"]["error"]["code"],
                    "NOT_FOUND"
                );
            }
            _ => unreachable!(),
        }
    }
    drop(writer);
    drop(reader);
    tokio::time::timeout(Duration::from_secs(10), server)
        .await
        .unwrap()
        .unwrap();
}
