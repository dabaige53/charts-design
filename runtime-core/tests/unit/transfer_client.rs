use super::*;
use crate::runtime::{server, service::Service};
use std::{net::TcpListener, sync::atomic::AtomicBool, thread};
use tokio_util::sync::CancellationToken;

struct Host {
    _directory: tempfile::TempDir,
    server: Arc<server::RemoteServer>,
    endpoint: String,
    cancel: CancellationToken,
    worker: Option<thread::JoinHandle<()>>,
}

impl Host {
    fn new() -> Self {
        let directory = tempfile::tempdir().unwrap();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let address = listener.local_addr().unwrap();
        let public = format!("http://{address}");
        let settings = server::Settings::from_options(&json!({
            "workspace":directory.path().join("projects"),
            "runtime_root":directory.path().join("runtime"),
            "token":["transfer-test-author-credential"],
            "secret":"transfer-test-secret-with-at-least-32-bytes",
            "port":address.port(),"public_url":public,"stateless":true
        }))
        .unwrap();
        let server = Arc::new(server::RemoteServer::new(settings).unwrap());
        let cancel = CancellationToken::new();
        let stop = cancel.clone();
        let application = server::router(server.clone(), stop.clone()).unwrap();
        let worker = thread::spawn(move || {
            tokio::runtime::Builder::new_multi_thread()
                .worker_threads(2)
                .enable_all()
                .build()
                .unwrap()
                .block_on(async move {
                    let listener = tokio::net::TcpListener::from_std(listener).unwrap();
                    axum::serve(
                        listener,
                        application.into_make_service_with_connect_info::<std::net::SocketAddr>(),
                    )
                    .with_graceful_shutdown(stop.cancelled_owned())
                    .await
                    .unwrap();
                });
        });
        Self {
            _directory: directory,
            server,
            endpoint: format!("{public}/mcp"),
            cancel,
            worker: Some(worker),
        }
    }

    fn connect(&self, project: &str) -> Result<Arc<Remote>> {
        Arc::new(Remote {
            client: Client::builder()
                .no_proxy()
                .timeout(Duration::from_secs(10))
                .build()
                .unwrap(),
            endpoint: self.endpoint.clone(),
            token: "transfer-test-author-credential".into(),
            project: project.into(),
            session: Mutex::new(None),
            protocol: Mutex::new("2025-11-25".into()),
            next_id: AtomicU64::new(1),
        })
        .initialize()
    }
}
impl Drop for Host {
    fn drop(&mut self) {
        self.cancel.cancel();
        if let Some(worker) = self.worker.take() {
            worker.join().unwrap();
        }
    }
}

fn source(directory: &Path) -> (Service, Value, Value) {
    let service = Service::new(
        &directory.join("runtime"),
        None,
        Some(&directory.join("project")),
    )
    .unwrap();
    let created = service.call("dashboard_submit", &json!({"dashboardId":"sales","createTitle":"Sales","operations":[
        {"op":"put_source","id":"fixture","value":{"kind":"fixture","name":"Sales"}},
        {"op":"put_dataset","id":"sales","meta":{"sourceId":"fixture","fields":{"amount":{"type":"number"},"region":{"type":"string"}}},"rows":[{"amount":10,"region":"East"},{"amount":20,"region":"West"}]},
        {"op":"put_component","id":"detail","value":{"kind":"table","title":"Details","datasetId":"sales"}}
    ]})).unwrap();
    let document = service.store.get("sales", false).unwrap();
    let reference = document["snapshot"]["datasetRefs"]["sales"].clone();
    let manifest = json!({"projectRoot":directory.join("project"),"pages":[{
        "dashboardId":"sales","draftRevision":created["revision"],"componentCount":1,
        "datasets":[{"id":"sales","version":reference["version"],"rowCount":reference["rowCount"],"bytes":reference["bytes"]}]
    }]});
    (service, reference, manifest)
}

// @wu-test type=integration | scope=native transfer client over HTTP MCP | protects=bulk upload, persisted resume state and project import cannot be completed by the native client
#[test]
fn native_client_imports_verifies_and_resumes_a_real_project() {
    let host = Host::new();
    let directory = tempfile::tempdir().unwrap();
    let (local, reference, manifest) = source(directory.path());
    let note = json!({"id":"review","componentId":"detail","text":"Check totals","createdAt":"2026-11-01T00:00:00Z"});
    local.store.append_annotation("sales", &note, None).unwrap();
    let source_notes = local.store.annotation_state("sales", false).unwrap()["annotations"].clone();
    let path = directory.path().join("manifest.json");
    fs::write(&path, serde_json::to_vec(&manifest).unwrap()).unwrap();
    let mut options = json!({"manifest":path,"project":"destination","state":directory.path().join("state.json"),"check_only":true});
    let checked = command_with(&options, |project| host.connect(project)).unwrap();
    assert_eq!(checked, json!({"checkedPages":1,"checkedDatasets":1}));
    assert!(host
        .server
        .service("destination")
        .unwrap()
        .store
        .list()
        .unwrap()
        .as_array()
        .unwrap()
        .is_empty());
    options["check_only"] = json!(false);
    let receipt = command_with(&options, |project| host.connect(project)).unwrap();
    assert_eq!(receipt["state"], "complete");
    assert_eq!(receipt["importedPages"], 1);
    assert_eq!(receipt["transferredDatasets"], 1);
    let destination = host.server.service("destination").unwrap();
    let imported = destination.store.get("sales", false).unwrap();
    assert_eq!(imported["manifest"]["title"], "Sales");
    assert_eq!(imported["snapshot"]["datasetRefs"]["sales"], reference);
    assert_eq!(
        destination.store.data.all_rows(&reference).unwrap(),
        vec![
            json!({"amount":10,"region":"East"}),
            json!({"amount":20,"region":"West"})
        ]
    );
    assert_eq!(
        destination.store.annotation_state("sales", false).unwrap()["annotations"],
        source_notes
    );
    let state = load_json(&directory.path().join("state.json")).unwrap();
    assert_eq!(state["created"], json!(["sales"]));
    assert_eq!(state["bulk"], json!([reference["version"]]));
    assert_eq!(
        command_with(&options, |project| host.connect(project)).unwrap()["state"],
        "complete"
    );
    assert_eq!(destination.store.revision("sales").unwrap(), 1);

    let output = directory.path().join("download.json");
    let read = remote_command_with(
        &json!({"action":"read","project":"destination","dashboard":"sales","output":output}),
        |p| host.connect(p),
    )
    .unwrap();
    assert_eq!(read["componentIds"], json!(["detail"]));
    assert_eq!(
        load_json(&output).unwrap()["document"]["manifest"]["title"],
        "Sales"
    );
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            fs::metadata(output).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }
    destination.call("dashboard_patch", &json!({"dashboardId":"sales","expectedRevision":1,"operations":[{"op":"set_title","value":"Independent destination edit"}]})).unwrap();
    assert_eq!(
        command_with(&options, |p| host.connect(p))
            .unwrap_err()
            .code,
        "DATA_CONFLICT"
    );
    assert_eq!(
        destination.store.get("sales", false).unwrap()["manifest"]["title"],
        "Independent destination edit"
    );
}

// @wu-test type=integration | scope=native standalone upload | protects=JSONL blank lines and missing fields change data versions or unsupported resume state is silently accepted
#[test]
fn native_remote_upload_streams_jsonl_and_checks_resume_identity() {
    let host = Host::new();
    let directory = tempfile::tempdir().unwrap();
    let root = directory.path();
    let fields = json!({"amount":{"type":"number"},"flag":{"type":"boolean"}});
    fs::write(
        root.join("fields.json"),
        serde_json::to_vec(&fields).unwrap(),
    )
    .unwrap();
    fs::write(
        root.join("rows.jsonl"),
        "{\"amount\":1,\"flag\":true}\n\n{\"amount\":2}\n{\"amount\":3,\"flag\":null}\n",
    )
    .unwrap();
    let options = json!({"action":"upload","project":"uploaded","root":root,"rows":root.join("rows.jsonl"),"fields":root.join("fields.json"),"state":root.join("state.json"),"output":root.join("ref.json"),"legacy":true});
    let receipt = remote_command_with(&options, |p| host.connect(p)).unwrap();
    assert_eq!(receipt["rowCount"], 3);
    let reference = load_json(&root.join("ref.json")).unwrap();
    assert_eq!(
        host.server
            .service("uploaded")
            .unwrap()
            .store
            .data
            .all_rows(&reference)
            .unwrap(),
        vec![
            json!({"amount":1,"flag":true}),
            json!({"amount":2}),
            json!({"amount":3,"flag":null})
        ]
    );
    assert_eq!(
        load_json(&root.join("state.json")).unwrap()["bulk"],
        json!([])
    );
    let mut resume = options.clone();
    resume.as_object_mut().unwrap().remove("rows");
    resume["ref"] = json!(root.join("ref.json"));
    resume["resume_staged"] = reference["version"].clone();
    assert_eq!(
        remote_command_with(&resume, |p| host.connect(p)).unwrap()["version"],
        reference["version"]
    );
    resume["resume_staged"] = json!("0".repeat(64));
    assert_eq!(
        remote_command_with(&resume, |p| host.connect(p))
            .unwrap_err()
            .code,
        "INVALID_ARGUMENT"
    );
    resume.as_object_mut().unwrap().remove("resume_staged");
    resume["check_only"] = json!(true);
    assert_eq!(
        remote_command_with(&resume, |p| host.connect(p)).unwrap()["checked"],
        true
    );
    let mut invalid = options.clone();
    invalid["ref"] = json!(root.join("ref.json"));
    assert_eq!(
        source_reference(&invalid).unwrap_err().code,
        "INVALID_ARGUMENT"
    );
    invalid.as_object_mut().unwrap().remove("ref");
    invalid["rows"] = json!(root.join("rows.json"));
    fs::write(root.join("rows.json"), br#"{"amount":1}"#).unwrap();
    assert_eq!(
        source_reference(&invalid).unwrap_err().code,
        "INVALID_ARGUMENT"
    );
    fs::write(root.join("rows.json"), br#"[{"amount":1,"flag":true}]"#).unwrap();
    assert_eq!(source_reference(&invalid).unwrap()["rowCount"], 1);
    assert_eq!(
        remote_command_with(
            &json!({"action":"delete","project":"uploaded","output":root.join("x")}),
            |p| host.connect(p)
        )
        .unwrap_err()
        .code,
        "INVALID_ARGUMENT"
    );
}

// @wu-test type=boundary | scope=project transfer manifest | protects=stale revisions, missing datasets and duplicate selections overwrite a different source snapshot
#[test]
fn project_manifest_rejects_stale_or_incomplete_selection() {
    let directory = tempfile::tempdir().unwrap();
    let (_local, _, manifest) = source(directory.path());
    let (_, documents, references) = read_project(&manifest).unwrap();
    assert_eq!(documents.len(), 1);
    assert_eq!(references.len(), 1);
    let mut invalid = manifest.clone();
    invalid["pages"][0]["draftRevision"] = json!(99);
    assert_eq!(
        read_project(&invalid).unwrap_err().code,
        "REVISION_CONFLICT"
    );
    invalid = manifest.clone();
    invalid["pages"][0]["componentCount"] = json!(0);
    assert_eq!(read_project(&invalid).unwrap_err().code, "DATA_CONFLICT");
    invalid = manifest.clone();
    invalid["pages"][0]["datasets"] = json!([]);
    assert_eq!(read_project(&invalid).unwrap_err().code, "INVALID_ARGUMENT");
    invalid = manifest.clone();
    invalid["pages"][0]["datasets"][0]["rowCount"] = json!(99);
    assert_eq!(read_project(&invalid).unwrap_err().code, "DATA_CONFLICT");
    invalid = manifest.clone();
    invalid["pages"] = json!([manifest["pages"][0], manifest["pages"][0]]);
    assert_eq!(read_project(&invalid).unwrap_err().code, "INVALID_ARGUMENT");
    invalid = manifest.clone();
    invalid["pages"][0]["datasets"] = json!([
        manifest["pages"][0]["datasets"][0],
        manifest["pages"][0]["datasets"][0]
    ]);
    assert_eq!(read_project(&invalid).unwrap_err().code, "INVALID_ARGUMENT");
    invalid["pages"][0]["dashboardId"] = json!("missing");
    assert_eq!(read_project(&invalid).unwrap_err().code, "NOT_FOUND");
    let doc = json!({"revision":5,"dataVersion":"v","computed":{},"progressive":true,"loading":true,"manifest":{"title":"Sales"}});
    assert_eq!(
        normalized(&doc),
        json!({"revision":1,"manifest":{"title":"Sales"}})
    );
}

struct Scripted {
    calls: Mutex<Vec<(String, Value)>>,
    responses: Mutex<std::collections::VecDeque<Value>>,
}
impl ToolCaller for Scripted {
    fn call(&self, tool: &str, args: &Value) -> Result<Value> {
        self.calls.lock().unwrap().push((tool.into(), args.clone()));
        Ok(self
            .responses
            .lock()
            .unwrap()
            .pop_front()
            .expect("unexpected transfer call"))
    }
}

// @wu-test type=boundary | scope=transfer finalize recovery | protects=failed staged uploads retain stale receipts or a different completed reference is reported as success
#[test]
fn transfer_recovery_validates_final_state_and_retains_retryable_state() {
    let directory = tempfile::tempdir().unwrap();
    let data = LocalData::new(Some(&directory.path().join("data"))).unwrap();
    let reference = data
        .import_rows(&[json!({"v":1})], &json!({"v":{"type":"number"}}))
        .unwrap();
    for (index, responses, expected) in [
        (
            0,
            vec![
                json!({"state":"running"}),
                json!({"state":"complete","ref":reference}),
            ],
            None,
        ),
        (
            1,
            vec![
                json!({"state":"cleanup_required"}),
                json!({"state":"complete","ref":reference}),
            ],
            None,
        ),
        (
            2,
            vec![
                json!({"state":"unknown"}),
                json!({"state":"failed","code":"DATA_INCOMPLETE"}),
            ],
            Some("TRANSFER_FAILED"),
        ),
        (
            3,
            vec![json!({"state":"complete","ref":{}})],
            Some("DATA_CONFLICT"),
        ),
        (
            4,
            vec![json!({"state":"unexpected"})],
            Some("TRANSFER_PROTOCOL_ERROR"),
        ),
    ] {
        let caller = Arc::new(Scripted {
            calls: Mutex::new(vec![]),
            responses: Mutex::new(responses.into()),
        });
        let options = json!({"state":directory.path().join(format!("state-{index}.json"))});
        let mut client = TransferClient::new(
            caller.clone(),
            directory.path(),
            "https://example.test/mcp",
            "project",
            &options,
            false,
        )
        .unwrap();
        let version = reference["version"].as_str().unwrap();
        client.state["uploads"][version] = json!("a".repeat(64));
        client.add("staged", version);
        let result = client.transfer(&reference, true);
        match expected {
            Some(code) => assert_eq!(result.unwrap_err().code, code),
            None => assert_eq!(result.unwrap(), reference),
        }
        if index == 2 {
            assert!(!client.contains("staged", version));
        }
        assert!(options["state"]
            .as_str()
            .is_some_and(|path| Path::new(path).is_file()));
        if index == 1 {
            assert_eq!(caller.calls.lock().unwrap()[1].0, "dataset_transfer_finish");
        }
    }
    let caller = Arc::new(Scripted {
        calls: Mutex::new(vec![]),
        responses: Mutex::new(
            vec![json!({"state":"unknown","receivedParts":{"0":"wrong-hash"}})].into(),
        ),
    });
    let options = json!({"state":directory.path().join("conflict.json")});
    let client = TransferClient::new(
        caller,
        directory.path(),
        "https://example.test/mcp",
        "project",
        &options,
        false,
    )
    .unwrap();
    assert_eq!(
        client
            .upload_window(&json!({}), vec![(0, vec![json!({"v":1})])], true)
            .unwrap_err()
            .code,
        "DATA_CONFLICT"
    );
    assert_eq!(
        diagnostic_code(Some("includes sensitive contents!")),
        "MCP_ERROR"
    );
    assert_eq!(diagnostic_code(Some("DATA_INCOMPLETE")), "DATA_INCOMPLETE");
}

// @wu-test type=boundary | scope=transfer state validation | protects=malformed state, unsupported bulk continuation and changed local data silently start a new upload
#[test]
fn transfer_state_and_source_boundaries_fail_before_network_writes() {
    let directory = tempfile::tempdir().unwrap();
    let caller = Arc::new(Scripted {
        calls: Mutex::new(vec![]),
        responses: Mutex::new(vec![].into()),
    });
    let path = directory.path().join("state.json");
    for concurrency in [json!(0), json!(5), json!("2"), json!(-1)] {
        assert_eq!(
            TransferClient::new(
                caller.clone(),
                directory.path(),
                "https://example.test/mcp",
                "project",
                &json!({"state":path,"concurrency":concurrency}),
                false
            )
            .err()
            .unwrap()
            .code,
            "INVALID_ARGUMENT"
        );
    }
    let mut client = TransferClient::new(
        caller.clone(),
        directory.path(),
        "https://example.test/mcp",
        "project",
        &json!({"state":path}),
        false,
    )
    .unwrap();
    let version = "a".repeat(64);
    client.add("bulk", &version);
    assert_eq!(
        client.uses_bulk(&version).unwrap_err().code,
        "CAPABILITY_MISSING"
    );
    client.save().unwrap();
    let mut state = client.state.clone();
    drop(client);
    for key in ["created", "staged", "bulk", "uploads"] {
        let mut invalid = state.clone();
        invalid[key] = json!(false);
        save_private(&path, &invalid).unwrap();
        assert_eq!(
            TransferClient::new(
                caller.clone(),
                directory.path(),
                "https://example.test/mcp",
                "project",
                &json!({"state":path}),
                false
            )
            .err()
            .unwrap()
            .code,
            "INVALID_ARGUMENT"
        );
    }
    state["uploads"] = json!({"invalid":"broken"});
    save_private(&path, &state).unwrap();
    assert_eq!(
        TransferClient::new(
            caller.clone(),
            directory.path(),
            "https://example.test/mcp",
            "project",
            &json!({"state":path}),
            false
        )
        .err()
        .unwrap()
        .code,
        "INVALID_ARGUMENT"
    );
    let reference = json!({"version":"a".repeat(64),"rowCount":1,"fields":{"v":{"type":"number"}},"fieldOrder":["v"]});
    assert_eq!(
        for_batches(directory.path(), &reference, 250, |_, _| Ok(()))
            .unwrap_err()
            .code,
        "NOT_FOUND"
    );
    assert!(caller.calls.lock().unwrap().is_empty());
}

struct Stub {
    endpoint: String,
    stop: Arc<AtomicBool>,
    worker: Option<thread::JoinHandle<()>>,
}
impl Stub {
    fn new(handle: impl Fn(Value) -> (u16, &'static str, String) + Send + 'static) -> Self {
        use std::io::Write;
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let endpoint = format!("http://{}/mcp", listener.local_addr().unwrap());
        let stop = Arc::new(AtomicBool::new(false));
        let stopped = stop.clone();
        let worker = thread::spawn(move || {
            while !stopped.load(Ordering::SeqCst) {
                let (mut stream, _) = match listener.accept() {
                    Ok(pair) => pair,
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(2));
                        continue;
                    }
                    Err(e) => panic!("{e}"),
                };
                stream
                    .set_read_timeout(Some(Duration::from_secs(5)))
                    .unwrap();
                let mut reader = BufReader::new(stream.try_clone().unwrap());
                let mut length = 0;
                let mut first = String::new();
                reader.read_line(&mut first).unwrap();
                loop {
                    let mut line = String::new();
                    reader.read_line(&mut line).unwrap();
                    if line == "\r\n" {
                        break;
                    }
                    if let Some((name, value)) = line.split_once(':') {
                        if name.eq_ignore_ascii_case("content-length") {
                            length = value.trim().parse().unwrap()
                        }
                    }
                }
                let mut body = vec![0; length];
                reader.read_exact(&mut body).unwrap();
                let (status, kind, body) =
                    handle(serde_json::from_slice(&body).unwrap_or(Value::Null));
                write!(stream,"HTTP/1.1 {status} Response\r\nContent-Type: {kind}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",body.len()).unwrap();
            }
        });
        Self {
            endpoint,
            stop,
            worker: Some(worker),
        }
    }
    fn remote(&self) -> Remote {
        Remote {
            client: Client::builder()
                .no_proxy()
                .timeout(Duration::from_secs(5))
                .build()
                .unwrap(),
            endpoint: self.endpoint.clone(),
            token: "test-token".into(),
            project: "project".into(),
            session: Mutex::new(None),
            protocol: Mutex::new("2025-11-25".into()),
            next_id: AtomicU64::new(1),
        }
    }
}
impl Drop for Stub {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(worker) = self.worker.take() {
            worker.join().unwrap();
        }
    }
}

// @wu-test type=boundary | scope=HTTP MCP response validation | protects=wrong request IDs, HTTP failures and non-JSON tool results are accepted or expose remote error text
#[test]
fn remote_protocol_rejects_mismatched_or_malformed_responses() {
    for (status, kind, body, code) in [
        (401, "application/json", "{}", "MCP_UNAUTHORIZED"),
        (403, "application/json", "{}", "MCP_UNAUTHORIZED"),
        (500, "application/json", "{}", "MCP_HTTP_ERROR"),
        (200, "text/plain", "{}", "TRANSFER_PROTOCOL_ERROR"),
        (
            200,
            "application/json",
            "not json",
            "TRANSFER_PROTOCOL_ERROR",
        ),
        (
            200,
            "application/json",
            r#"{"jsonrpc":"2.0","id":99,"result":{}}"#,
            "TRANSFER_PROTOCOL_ERROR",
        ),
        (
            200,
            "application/json",
            r#"{"jsonrpc":"2.0","id":1,"error":{"message":"private database information"}}"#,
            "MCP_RPC_ERROR",
        ),
        (
            200,
            "application/json",
            r#"{"jsonrpc":"2.0","id":1}"#,
            "TRANSFER_PROTOCOL_ERROR",
        ),
    ] {
        let stub = Stub::new(move |_| (status, kind, body.into()));
        let error = stub.remote().rpc("tools/list", &json!({})).unwrap_err();
        assert_eq!(error.code, code);
        assert!(!error.message.contains("private database"));
    }
    let stub = Stub::new(|request| {
        (
            200,
            "text/event-stream",
            format!(
                "data: {{\"jsonrpc\":\"2.0\",\"id\":{},\"result\":{{\"tools\":[]}}}}\n\n",
                request["id"]
            ),
        )
    });
    assert_eq!(
        stub.remote().rpc("tools/list", &json!({})).unwrap(),
        json!({"tools":[]})
    );
    for result in [
        json!({"content":[{"text":"not json"}]}),
        json!({"content":[]}),
        json!({"structuredContent":{"ok":false,"error":{"code":"bad private text"}},"isError":true}),
    ] {
        let stub = Stub::new(move |request| {
            (
                200,
                "application/json",
                json!({"jsonrpc":"2.0","id":request["id"],"result":result}).to_string(),
            )
        });
        let error = stub
            .remote()
            .request_tool("dashboard_get", &json!({}))
            .unwrap_err();
        assert!(["TRANSFER_PROTOCOL_ERROR", "MCP_ERROR"].contains(&error.code.as_str()));
        assert!(!error.message.contains("private text"));
    }
}

// @wu-test type=integration | scope=MCP chunk reconstruction and capability discovery | protects=truncated large results and incompatible tool schemas enter the transfer workflow
#[test]
fn remote_assembles_bounded_chunks_and_discovers_hidden_transfer_contracts() {
    let expected = json!({"ok":true,"document":{"id":"sales","body":"x".repeat(10000)}});
    let bytes = serde_json::to_vec(&expected).unwrap();
    let size = bytes.len();
    let encoded = STANDARD.encode(&bytes);
    let stub = Stub::new(move |request| {
        let tool = request["params"]["name"].as_str().unwrap_or("");
        let value = if tool == "runtime_result_chunk" {
            json!({"requestId":"r1","index":0,"data":encoded})
        } else {
            json!({"transport":{"encoding":"base64-json-v1","bytes":size,"chunks":1,"requestId":"r1"}})
        };
        (200,"application/json",json!({"jsonrpc":"2.0","id":request["id"],"result":{"content":[{"text":value.to_string()}]}}).to_string())
    });
    assert_eq!(
        stub.remote()
            .call("dashboard_get", &json!({"dashboardId":"sales"}))
            .unwrap(),
        expected
    );
    let stub = Stub::new(|request| {
        let result = if request["method"] == "tools/list" {
            json!({"tools":[]})
        } else {
            json!({"contents":[{"text":json!({"clientTools":{"dataset_transfer_status":{"properties":{"uploadId":{},"ref":{},"parts":{}}}}}).to_string()}]})
        };
        (
            200,
            "application/json",
            json!({"jsonrpc":"2.0","id":request["id"],"result":result}).to_string(),
        )
    });
    assert!(stub
        .remote()
        .require_tools(&[("dataset_transfer_status", &["uploadId", "ref", "parts"])])
        .unwrap()
        .contains_key("dataset_transfer_status"));
    assert_eq!(
        stub.remote()
            .require_tools(&[("missing", &[])])
            .unwrap_err()
            .code,
        "CAPABILITY_MISSING"
    );
    let stub = Stub::new(|request| {
        (200,"application/json",json!({"jsonrpc":"2.0","id":request["id"],"result":{"tools":[],"nextCursor":"repeated"}}).to_string())
    });
    assert_eq!(
        stub.remote().require_tools(&[]).unwrap_err().code,
        "TRANSFER_PROTOCOL_ERROR"
    );
    for transport in [
        json!({"encoding":"unknown"}),
        json!({"encoding":"base64-json-v1","bytes":MAX_RESPONSE+1}),
        json!({"encoding":"base64-json-v1","bytes":1,"chunks":5000}),
    ] {
        let stub = Stub::new(move |request| {
            (200,"application/json",json!({"jsonrpc":"2.0","id":request["id"],"result":{"structuredContent":{"transport":transport}}}).to_string())
        });
        assert_eq!(
            stub.remote()
                .call("dashboard_get", &json!({}))
                .unwrap_err()
                .code,
            "TRANSFER_PROTOCOL_ERROR"
        );
    }
}
