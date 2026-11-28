use super::*;
use axum::body::to_bytes;
use std::io::Read;

const AUTHOR: &str = "local-test-author-session";

fn local() -> (tempfile::TempDir, Arc<LocalState>) {
    let root = tempfile::tempdir().unwrap();
    let service = Arc::new(
        Service::new(
            &root.path().join("runtime"),
            None,
            Some(&root.path().join("project")),
        )
        .unwrap(),
    );
    let document = model::apply_operations(
        &model::new_document("main", "Saved title").unwrap(),
        &[json!({"op":"put_component","id":"findings","value":{"kind":"text","title":"Findings","text":"Reviewed figures"}})],
    ).unwrap();
    service
        .store
        .create("main", "Saved title", Some(&document))
        .unwrap();
    service
        .store
        .checkpoint("main", 1, "saved", false, None)
        .unwrap();
    service
        .store
        .create("other", "Other dashboard", None)
        .unwrap();
    service
        .store
        .checkpoint("other", 1, "saved", false, None)
        .unwrap();
    let state = Arc::new(LocalState {
        service,
        token: AUTHOR.into(),
        port: 8765,
        lifetime: Lifetime::new(300.0).unwrap(),
    });
    (root, state)
}

fn remote() -> (tempfile::TempDir, RemoteServer) {
    let root = tempfile::tempdir().unwrap();
    let settings = Settings::from_options(&json!({"workspace":root.path().join("projects"),"runtime_root":root.path().join("runtime"),"token":[AUTHOR],"secret":"http-regression-signing-secret-at-least-32-bytes","port":8765,"public_url":"http://127.0.0.1:8765"})).unwrap();
    let server = RemoteServer::new(settings).unwrap();
    let service = server.service("project").unwrap();
    service.store.create("main", "Published", None).unwrap();
    service
        .store
        .checkpoint("main", 1, "saved", false, None)
        .unwrap();
    (root, server)
}

fn input(method: Method, path: &str, token: &str, body: Value) -> HttpInput {
    let mut headers = HeaderMap::new();
    headers.insert("host", "127.0.0.1:8765".parse().unwrap());
    headers.insert(
        "content-type",
        "application/json; charset=utf-8".parse().unwrap(),
    );
    headers.insert("authorization", format!("bEaReR {token} ").parse().unwrap());
    HttpInput {
        method,
        path: path.into(),
        query: BTreeMap::new(),
        headers,
        body: serde_json::to_vec(&body).unwrap(),
        archive: None,
        peer: "127.0.0.1".into(),
        verified: None,
    }
}

fn json_output(output: HttpOutput) -> Value {
    assert_eq!(output.status, 200);
    assert_eq!(output.kind, "application/json");
    match output.payload {
        Payload::Bytes(bytes) => serde_json::from_slice(&bytes).unwrap(),
        Payload::File(_) => panic!("Expected a JSON response, received a file"),
    }
}

fn text_output(output: HttpOutput) -> String {
    match output.payload {
        Payload::Bytes(bytes) => String::from_utf8(bytes).unwrap(),
        Payload::File(_) => panic!("Expected inline HTML, received a file"),
    }
}

// @wu-test type=integration | scope=local preview authorization | protects=reader tokens remain bound to one saved page, cannot write and never reveal the author's edit URL
#[test]
fn local_reader_routes_use_saved_content_and_enforce_page_scope() {
    let (_root, state) = local();
    let reader = state.preview_token("main").unwrap();
    assert_eq!(
        json_output(
            state
                .handle(&input(Method::GET, "/health", "", json!({})))
                .unwrap()
        ),
        json!({"ok":true})
    );
    assert!(state.principal(AUTHOR).unwrap().edit);
    assert!(!state.principal(&reader).unwrap().edit);
    for token in [
        "invalid".to_owned(),
        "view.%%.bad".to_owned(),
        format!("{reader}x"),
        format!("view.{}.bad", URL_SAFE_NO_PAD.encode([0xff])),
    ] {
        assert_eq!(state.principal(&token).err().unwrap().code, "UNAUTHORIZED");
    }
    assert!(state.preview_token("../main").is_err());
    let links = json_output(
        state
            .handle(&input(
                Method::GET,
                "/api/browser-links/main",
                &reader,
                json!({}),
            ))
            .unwrap(),
    );
    assert!(links.get("editUrl").is_none());
    assert_eq!(
        links["viewUrl"],
        format!("http://127.0.0.1:8765/view/main#token={reader}")
    );
    let links = json_output(
        state
            .handle(&input(
                Method::GET,
                "/api/browser-links/main",
                AUTHOR,
                json!({}),
            ))
            .unwrap(),
    );
    assert_eq!(
        links["editUrl"],
        format!("http://127.0.0.1:8765/edit/main#token={AUTHOR}")
    );
    assert_eq!(
        state
            .handle(&input(
                Method::GET,
                "/api/browser-links/other",
                &reader,
                json!({})
            ))
            .err()
            .unwrap()
            .code,
        "FORBIDDEN"
    );
    assert_eq!(
        state
            .handle(&input(
                Method::GET,
                "/api/browser-links/main",
                "",
                json!({})
            ))
            .err()
            .unwrap()
            .status,
        401
    );
    let updated = json_output(state.handle(&input(Method::POST, "/api/tools/dashboard_patch", AUTHOR, json!({"projectRoot":"ignored","dashboardId":"main","expectedRevision":1,"operations":[{"op":"set_title","value":"Unpublished draft"}]}))).unwrap());
    assert_eq!(updated["document"]["revision"], 2);
    let read = json_output(
        state
            .handle(&input(
                Method::POST,
                "/api/tools/dashboard_get",
                &reader,
                json!({}),
            ))
            .unwrap(),
    );
    assert_eq!(read["document"]["revision"], 1);
    assert_eq!(read["document"]["manifest"]["title"], "Saved title");
    assert_eq!(read["projectRoot"], json!(state.service.project_root));
    let full = json_output(
        state
            .handle(&input(
                Method::POST,
                "/api/tools/dashboard_get",
                AUTHOR,
                json!({"dashboardId":"main"}),
            ))
            .unwrap(),
    );
    assert_eq!(full["document"]["revision"], 2);
    let list = json_output(
        state
            .handle(&input(
                Method::POST,
                "/api/tools/dashboard_list",
                &reader,
                json!({}),
            ))
            .unwrap(),
    );
    assert_eq!(list["dashboards"].as_array().unwrap().len(), 1);
    assert_eq!(list["dashboards"][0]["id"], "main");
    assert_eq!(
        state
            .handle(&input(
                Method::POST,
                "/api/tools/dashboard_patch",
                &reader,
                json!({"dashboardId":"main"})
            ))
            .err()
            .unwrap()
            .code,
        "FORBIDDEN"
    );
    assert_eq!(
        state
            .handle(&input(
                Method::POST,
                "/api/tools/dashboard_get",
                &reader,
                json!({"dashboardId":"other"})
            ))
            .err()
            .unwrap()
            .code,
        "FORBIDDEN"
    );
    assert_eq!(
        state
            .handle(&input(
                Method::POST,
                "/api/tools/dashboard_view",
                &reader,
                json!({"expectedRevision":2})
            ))
            .err()
            .unwrap()
            .code,
        "REVISION_CONFLICT"
    );
    let view = json_output(
        state
            .handle(&input(
                Method::POST,
                "/api/tools/dashboard_view",
                &reader,
                json!({}),
            ))
            .unwrap(),
    );
    assert_eq!(view["document"]["revision"], 1);
    let preview = text_output(
        state
            .handle(&input(Method::GET, "/view/main", "", json!({})))
            .unwrap(),
    );
    assert!(preview.contains("\"readOnly\":true"));
    assert!(preview.contains("\"canManageAnnotations\":false"));
    let edit = text_output(
        state
            .handle(&input(Method::GET, "/edit/main", "", json!({})))
            .unwrap(),
    );
    assert!(edit.contains("\"canManageAnnotations\":true"));
    let exported = text_output(
        state
            .handle(&input(Method::GET, "/api/export/main", &reader, json!({})))
            .unwrap(),
    );
    assert!(exported.contains("Saved title"));
    assert!(!exported.contains("Unpublished draft"));
    let mut request = input(Method::GET, "/health", "", json!({}));
    request
        .headers
        .insert("host", "evil.example".parse().unwrap());
    assert_eq!(state.handle(&request).err().unwrap().code, "INVALID_HOST");
    request
        .headers
        .insert("host", "localhost:8765".parse().unwrap());
    request
        .headers
        .insert("origin", "https://evil.example".parse().unwrap());
    assert_eq!(state.handle(&request).err().unwrap().code, "INVALID_ORIGIN");
    request
        .headers
        .insert("origin", "http://localhost:8765".parse().unwrap());
    assert!(state.handle(&request).is_ok());
    for (method, path) in [
        (Method::GET, "/absent"),
        (Method::POST, "/outside"),
        (Method::POST, "/api/absent"),
        (Method::DELETE, "/health"),
    ] {
        assert_eq!(
            state
                .handle(&input(method, path, AUTHOR, json!({})))
                .err()
                .unwrap()
                .code,
            "NOT_FOUND"
        );
    }
}

// @wu-test type=integration | scope=local HTTP annotations | protects=reader additions keep unverified identity, author replacement uses optimistic concurrency and target resolution does not advance content revisions
#[test]
fn annotations_keep_separate_revision_and_author_management_rules() {
    let (_root, state) = local();
    let reader = state.preview_token("main").unwrap();
    let note = json!({"id":"note","componentId":"findings","text":"核对说明","createdAt":"2026-11-28","anchor":{"scope":"component","kind":"area","quote":"","rect":{"x":0.1,"y":0.1,"width":0.4,"height":0.2}},"author":{"name":"Forged","verified":true}});
    let added = json_output(
        state
            .handle(&input(
                Method::POST,
                "/api/annotations/main",
                &reader,
                json!({"append":note,"authorName":" Reader ","revision":1}),
            ))
            .unwrap(),
    );
    assert_eq!(added["targetRevision"], 1);
    assert_eq!(state.service.store.revision("main").unwrap(), 1);
    let read = json_output(
        state
            .handle(&input(
                Method::GET,
                "/api/annotations/main",
                &reader,
                json!({}),
            ))
            .unwrap(),
    );
    assert_eq!(read["canManageAnnotations"], false);
    assert_eq!(
        read["annotations"][0]["author"],
        json!({"name":"Reader","verified":false})
    );
    assert_eq!(read["targets"]["note"]["componentExists"], true);
    assert_eq!(read["targets"]["note"]["title"], "Findings");
    for body in [
        json!({"dashboardId":"other","append":note}),
        json!({"expectedAnnotations":read["annotations"],"annotations":[]}),
    ] {
        assert_eq!(
            state
                .handle(&input(Method::POST, "/api/annotations/main", &reader, body))
                .err()
                .unwrap()
                .code,
            "FORBIDDEN"
        );
    }
    for body in [
        json!({"append":note,"annotations":[]}),
        json!({"append":[],"authorName":"Reader"}),
        json!({"append":note,"authorName":5}),
        json!({"append":note,"authorName":"名".repeat(81)}),
        json!({"append":note,"revision":0}),
        json!({"expectedAnnotations":[],"annotations":[],"expectedRevision":0}),
        json!({"annotations":[]}),
    ] {
        assert_eq!(
            state
                .handle(&input(Method::POST, "/api/annotations/main", AUTHOR, body))
                .err()
                .unwrap()
                .code,
            "INVALID_ARGUMENT"
        );
    }
    let changed = state.service.call("dashboard_patch", &json!({"dashboardId":"main","expectedRevision":1,"operations":[{"op":"remove_component","id":"findings"}]})).unwrap();
    let revision = changed["document"]["revision"].as_i64().unwrap();
    let manager =
        annotation_response(&state.service, "main", Some(revision), true, true, None).unwrap();
    assert_eq!(manager["targets"]["note"]["componentExists"], false);
    let historical =
        annotation_response(&state.service, "main", Some(1), false, false, None).unwrap();
    assert_eq!(historical["targets"]["note"]["componentExists"], true);
    let page = json!({"id":"page-note","text":"General review","createdAt":"2026-11-28"});
    annotation_response(
        &state.service,
        "main",
        None,
        true,
        true,
        Some(&json!({"append":page})),
    )
    .unwrap();
    let current = annotation_response(&state.service, "main", None, true, true, None).unwrap();
    assert_eq!(current["targets"]["page-note"]["sourcePath"], "manifest");
    assert_eq!(current["annotations"][1]["author"]["name"], "作者");
    let removed = json_output(
        state
            .handle(&input(
                Method::POST,
                "/api/annotations/main",
                AUTHOR,
                json!({"expectedAnnotations":current["annotations"],"annotations":[]}),
            ))
            .unwrap(),
    );
    assert_eq!(removed["annotations"], json!([]));
    assert_eq!(state.service.store.revision("main").unwrap(), revision);
    let legacy = Service::new(
        &tempfile::tempdir().unwrap().path().join("legacy"),
        None,
        None,
    )
    .unwrap();
    assert_eq!(
        annotation_response(&legacy, "main", None, true, true, None)
            .unwrap_err()
            .code,
        "PROJECT_REQUIRED"
    );
}

// @wu-test type=boundary | scope=HTTP body and parameter parsing | protects=declared and streamed limits are both enforced, uploads remain on disk and invalid JSON or revision selectors fail before service execution
#[tokio::test]
async fn request_parser_bounds_streams_and_preserves_upload_and_peer_metadata() {
    let request = Request::builder()
        .method("POST")
        .uri("/api/example?revision=2&query=two+words")
        .header("Content-Type", "application/json; charset=utf-8")
        .header("Cookie", "first=one; session=token=with-equals; last=three")
        .extension(ConnectInfo("192.0.2.4:443".parse::<SocketAddr>().unwrap()))
        .body(Body::from("{\"revision\":3}"))
        .unwrap();
    let parsed = read_input(request, false).await.unwrap();
    assert_eq!(parsed.peer, "192.0.2.4");
    assert_eq!(parsed.query["query"], "two words");
    assert_eq!(parsed.cookie("session"), "token=with-equals");
    assert_eq!(parsed.cookie("absent"), "");
    assert_eq!(parsed.revision(None).unwrap(), Some(2));
    assert_eq!(
        parsed.revision(Some(&parsed.json().unwrap())).unwrap(),
        Some(3)
    );
    assert!(parsed.archive.is_none());
    let mut invalid = input(Method::POST, "/api/test", AUTHOR, json!([]));
    assert_eq!(invalid.json().unwrap_err().code, "INVALID_REQUEST");
    invalid.body = b"not-json".to_vec();
    assert_eq!(invalid.json().unwrap_err().code, "INVALID_REQUEST");
    invalid
        .headers
        .insert("content-type", "text/plain".parse().unwrap());
    assert_eq!(invalid.json().unwrap_err().status, 415);
    for revision in [json!(0), json!(-1), json!("2"), json!(null)] {
        assert!(invalid
            .revision(Some(&json!({"revision":revision})))
            .is_err());
    }
    invalid
        .query
        .insert("revision".into(), "not-an-integer".into());
    assert!(invalid.revision(None).is_err());
    for (path, length) in [
        ("/api/test", (MAX_BODY + 1).to_string()),
        ("/s/share/", "4097".into()),
        ("/s/share/api/annotations", (40 * 1024 + 1).to_string()),
        ("/health", "invalid".into()),
    ] {
        let request = Request::builder()
            .uri(path)
            .header("Content-Length", length)
            .body(Body::empty())
            .unwrap();
        assert_eq!(read_input(request, false).await.err().unwrap().status, 413);
    }
    let request = Request::builder()
        .uri("/s/share/")
        .body(Body::from(vec![0; 4097]))
        .unwrap();
    assert_eq!(
        read_input(request, false).await.err().unwrap().code,
        "PAYLOAD_TOO_LARGE"
    );
    let bytes = b"a real archive body, streamed to a private temporary file";
    let request = Request::builder()
        .method("POST")
        .uri("/api/v1/publications")
        .header("Content-Length", bytes.len())
        .body(Body::from(bytes.as_slice()))
        .unwrap();
    let parsed = read_input(request, true).await.unwrap();
    assert!(parsed.body.is_empty());
    let archive = parsed.archive.as_ref().unwrap().path().to_path_buf();
    assert_eq!(fs::read(&archive).unwrap(), bytes);
    drop(parsed);
    assert!(!archive.exists());
}

// @wu-test type=behavior | scope=HTTP responses | protects=compressed payloads round-trip, HEAD retains length without a body and file downloads preserve bytes and security headers
#[tokio::test]
async fn response_encoding_file_streaming_and_error_statuses_are_consistent() {
    let bytes = "reviewed result 数据 ".repeat(200).into_bytes();
    let response = HttpOutput::raw(bytes.clone(), "text/plain")
        .with_header("X-Check", "present")
        .with_header("bad header", "ignored")
        .with_header("X-Bad", "invalid\nvalue")
        .response(true, false);
    assert_eq!(response.headers()["content-encoding"], "gzip");
    assert_eq!(response.headers()["vary"], "Accept-Encoding");
    assert_eq!(response.headers()["x-check"], "present");
    assert!(response.headers().get("x-bad").is_none());
    assert_eq!(response.headers()["x-content-type-options"], "nosniff");
    assert_eq!(response.headers()["x-frame-options"], "DENY");
    let compressed = to_bytes(response.into_body(), MAX_BODY).await.unwrap();
    let mut decoded = Vec::new();
    flate2::read::GzDecoder::new(compressed.as_ref())
        .read_to_end(&mut decoded)
        .unwrap();
    assert_eq!(decoded, bytes);
    let response = HttpOutput::raw(bytes.clone(), "text/plain").response(false, true);
    assert_eq!(
        response.headers()["content-length"].to_str().unwrap(),
        bytes.len().to_string()
    );
    assert!(to_bytes(response.into_body(), MAX_BODY)
        .await
        .unwrap()
        .is_empty());
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("download.bin");
    fs::write(&path, &bytes).unwrap();
    for head in [false, true] {
        let output = HttpOutput {
            status: 200,
            kind: "application/octet-stream".into(),
            headers: vec![],
            payload: Payload::File(fs::File::open(&path).unwrap()),
        };
        let response = output.response(true, head);
        assert!(response.headers().get("content-encoding").is_none());
        assert_eq!(
            response.headers()["content-length"].to_str().unwrap(),
            bytes.len().to_string()
        );
        let body = to_bytes(response.into_body(), MAX_BODY).await.unwrap();
        assert_eq!(body.as_ref(), if head { &[] } else { bytes.as_slice() });
    }
    for (code, status) in [
        ("FORBIDDEN", 403),
        ("UNAUTHORIZED", 401),
        ("INVALID_ACCESS_KEY", 401),
        ("NOT_FOUND", 404),
        ("LINK_EXPIRED", 404),
        ("SHARE_EXPIRED", 410),
        ("SHARE_UNAVAILABLE", 410),
        ("REVISION_CONFLICT", 409),
        ("ANNOTATION_CONFLICT", 409),
        ("ANNOTATION_LIMIT", 409),
        ("SHARE_RATE_LIMITED", 429),
        ("INVALID_REQUEST", 400),
    ] {
        let output = HttpOutput::failure(Error::new(code, "Rejected"));
        assert_eq!(output.status, status);
        let body = text_output(output);
        assert_eq!(
            serde_json::from_str::<Value>(&body).unwrap()["error"]["code"],
            code
        );
    }
    assert_eq!(
        HttpOutput::failure(Error::new("SPECIAL", "Override").with_status(418)).status,
        418
    );
}

// @wu-test type=integration | scope=local HTTP adapter | protects=HEAD handling and parser failures pass through the same no-store response envelope without opening a listener
#[tokio::test]
async fn local_http_adapter_returns_head_and_authorization_errors() {
    let (_root, state) = local();
    let head = local_http(
        State(state.clone()),
        Request::builder()
            .method("HEAD")
            .uri("/health")
            .header("Host", "127.0.0.1:8765")
            .body(Body::empty())
            .unwrap(),
    )
    .await;
    assert_eq!(head.status(), 200);
    assert_eq!(head.headers()["content-length"], "11");
    assert!(to_bytes(head.into_body(), MAX_BODY)
        .await
        .unwrap()
        .is_empty());
    let denied = local_http(
        State(state.clone()),
        Request::builder()
            .method("POST")
            .uri("/api/tools/dashboard_get")
            .header("Host", "127.0.0.1:8765")
            .header("Content-Type", "application/json")
            .body(Body::from("{}"))
            .unwrap(),
    )
    .await;
    assert_eq!(denied.status(), 401);
    assert_eq!(denied.headers()["cache-control"], "private, no-store");
    let large = local_http(
        State(state),
        Request::builder()
            .method("POST")
            .uri("/api/tools/dashboard_get")
            .header("Content-Length", MAX_BODY + 1)
            .body(Body::empty())
            .unwrap(),
    )
    .await;
    assert_eq!(large.status(), 413);
}

// @wu-test type=integration | scope=signed HTTP downloads | protects=valid exports stream intact while signed traversal, symlink escapes, expired tokens and unavailable files remain inaccessible
#[tokio::test]
async fn signed_downloads_allow_only_existing_project_exports() {
    let (_root, server) = remote();
    let project = server.settings.workspace.join("project");
    let exports = project.join("dashboards/exports");
    fs::create_dir_all(&exports).unwrap();
    fs::write(exports.join("data.csv"), b"region,amount\nEast,12\n").unwrap();
    let token = |file: &str, expiry: i64| {
        server
            .signer
            .sign(&json!({"k":"file","p":"project","f":file,"exp":expiry}))
            .unwrap()
    };
    let valid = token("dashboards/exports/data.csv", now() + 60);
    let output = server
        .handle(&input(
            Method::GET,
            &format!("/files/{valid}"),
            "",
            json!({}),
        ))
        .unwrap();
    assert!(output
        .headers
        .iter()
        .any(|(name, value)| name == "Content-Disposition" && value.contains("data.csv")));
    let response = output.response(false, false);
    assert_eq!(
        to_bytes(response.into_body(), MAX_BODY)
            .await
            .unwrap()
            .as_ref(),
        b"region,amount\nEast,12\n"
    );
    fs::write(project.join("private.txt"), b"project-private").unwrap();
    for file in ["private.txt", "dashboards/exports/../../private.txt"] {
        let signed = token(file, now() + 60);
        assert_eq!(
            server
                .handle(&input(
                    Method::GET,
                    &format!("/files/{signed}"),
                    "",
                    json!({})
                ))
                .err()
                .unwrap()
                .code,
            "FORBIDDEN"
        );
    }
    let missing = token("dashboards/exports/missing.csv", now() + 60);
    assert_eq!(
        server
            .handle(&input(
                Method::GET,
                &format!("/files/{missing}"),
                "",
                json!({})
            ))
            .err()
            .unwrap()
            .code,
        "LINK_EXPIRED"
    );
    let expired = token("dashboards/exports/data.csv", now() - 1);
    assert_eq!(
        server
            .handle(&input(
                Method::GET,
                &format!("/files/{expired}"),
                "",
                json!({})
            ))
            .err()
            .unwrap()
            .status,
        404
    );
    assert_eq!(
        server
            .handle(&input(Method::GET, "/files/invalid", "", json!({})))
            .err()
            .unwrap()
            .code,
        "LINK_EXPIRED"
    );
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(project.join("private.txt"), exports.join("escape.csv"))
            .unwrap();
        let signed = token("dashboards/exports/escape.csv", now() + 60);
        assert_eq!(
            server
                .handle(&input(
                    Method::GET,
                    &format!("/files/{signed}"),
                    "",
                    json!({})
                ))
                .err()
                .unwrap()
                .code,
            "FORBIDDEN"
        );
    }
}

// @wu-test type=integration | scope=workspace HTTP routing and access boundary | protects=catalogs, annotations and static resources preserve author scope while malformed paths and publication identities are rejected
#[test]
fn workspace_routes_and_publication_identity_validate_explicit_scope() {
    let (_root, server) = remote();
    let health = json_output(
        server
            .handle(&input(Method::GET, "/health", "", json!({})))
            .unwrap(),
    );
    assert_eq!(health["role"], "workspace");
    assert_eq!(health["storage"], "sqlite");
    let catalog = json_output(
        server
            .handle(&input(Method::POST, "/api/v1/catalog", AUTHOR, json!({})))
            .unwrap(),
    );
    assert!(catalog["projects"]
        .as_array()
        .unwrap()
        .iter()
        .any(|v| v["name"] == "project"));
    let share = json_output(server.handle(&input(Method::POST, "/api/v1/share", AUTHOR, json!({"project":"project","dashboardId":"main","access":"view","annotationMode":"annotate"}))).unwrap());
    let reader = share["url"]
        .as_str()
        .unwrap()
        .split_once("#token=")
        .unwrap()
        .1;
    let mut request = input(
        Method::GET,
        "/api/v1/p/project/annotations/main",
        reader,
        json!({}),
    );
    request.verified = Some(ProjectPrincipal {
        project: "project".into(),
        principal: server.principal(reader, "project").unwrap(),
    });
    let annotations = json_output(server.handle(&request).unwrap());
    assert_eq!(annotations["independentSave"], true);
    assert_eq!(annotations["canAnnotate"], true);
    assert_eq!(annotations["canManageAnnotations"], false);
    let wrong = input(
        Method::POST,
        "/api/v1/p/project/annotations/main",
        AUTHOR,
        json!({"dashboardId":"other","append":{}}),
    );
    assert_eq!(server.handle(&wrong).err().unwrap().code, "FORBIDDEN");
    for path in ["/", "/edit/project/main", "/view/project/main"] {
        assert!(text_output(
            server
                .handle(&input(Method::GET, path, "", json!({})))
                .unwrap()
        )
        .contains("window.__chartsBoot="));
    }
    for name in assets::UI_RESOURCES {
        let asset = server
            .handle(&input(
                Method::GET,
                &format!("/assets/{name}"),
                "",
                json!({}),
            ))
            .unwrap();
        assert!(asset
            .headers
            .iter()
            .any(|(name, value)| name == "Cache-Control" && value == "no-cache"));
        match asset.payload {
            Payload::Bytes(bytes) => assert!(!bytes.is_empty()),
            Payload::File(_) => panic!("Asset must be inline"),
        }
    }
    assert_eq!(
        server
            .handle(&input(Method::GET, "/assets/private.txt", "", json!({})))
            .err()
            .unwrap()
            .code,
        "NOT_FOUND"
    );
    assert_eq!(
        server
            .handle(&input(Method::GET, "/view/../main", "", json!({})))
            .err()
            .unwrap()
            .code,
        "INVALID_PROJECT"
    );
    assert_eq!(decoded_path("/%ff").unwrap_err().code, "INVALID_REQUEST");
    assert_eq!(decoded_path("/%61pi/v1").unwrap(), vec!["api", "v1"]);
    let source = Uuid::new_v4().to_string();
    let identity = server
        .publication_source(Some("project"), Some(&source))
        .unwrap();
    assert_eq!(identity.len(), 64);
    assert_eq!(
        server
            .publication_source(Some("project"), Some(&source))
            .unwrap(),
        identity
    );
    assert_ne!(
        server
            .publication_source(Some("other"), Some(&source))
            .unwrap(),
        identity
    );
    for (project, source) in [
        (None, Some(source.as_str())),
        (Some("../project"), Some(source.as_str())),
        (Some("project"), None),
        (Some("project"), Some("not-a-uuid")),
        (
            Some("project"),
            Some("00000000-0000-0000-0000-000000000000"),
        ),
    ] {
        assert!(server.publication_source(project, source).is_err());
    }
    let mut origin = input(Method::POST, "/s/share/", "", json!({}));
    assert!(server.same_origin(&origin).is_ok());
    origin
        .headers
        .insert("origin", "http://127.0.0.1:8765".parse().unwrap());
    assert!(server.same_origin(&origin).is_ok());
    origin
        .headers
        .insert("origin", "https://different.example".parse().unwrap());
    assert_eq!(server.same_origin(&origin).unwrap_err().status, 403);
    for _ in 0..5 {
        server.key_attempt("share", "192.0.2.1").unwrap();
    }
    assert_eq!(
        server.key_attempt("share", "192.0.2.1").unwrap_err().code,
        "SHARE_RATE_LIMITED"
    );
    server.key_attempt("share", "192.0.2.2").unwrap();
    server
        .attempts
        .lock()
        .unwrap()
        .insert(("share".into(), "192.0.2.1".into()), (5, now() - 1));
    server.key_attempt("share", "192.0.2.1").unwrap();
    let form = text_output(access_form(
        "/safe?x=\"value\"",
        "<script>attack</script>",
        401,
    ));
    assert!(!form.contains("<script>attack</script>"));
    assert!(form.contains("&lt;script&gt;attack&lt;/script&gt;"));
    assert!(form.contains("&quot;value&quot;"));
}
