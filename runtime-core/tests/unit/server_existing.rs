use super::*;
use axum::body::to_bytes;
use tower::ServiceExt;
fn host() -> (tempfile::TempDir, Arc<RemoteServer>) {
    let directory = tempfile::tempdir().unwrap();
    let settings=Settings::from_options(&json!({"workspace":directory.path().join("projects"),"runtime_root":directory.path().join("runtime"),"token":["native-test-author-credential"],"secret":"native-test-signing-secret-at-least-32-bytes","port":8080,"public_url":"http://127.0.0.1:8080"})).unwrap();
    let server = Arc::new(RemoteServer::new(settings).unwrap());
    (directory, server)
}
fn input(path: &str, token: &str, body: Value) -> HttpInput {
    let mut headers = HeaderMap::new();
    headers.insert("host", "127.0.0.1:8080".parse().unwrap());
    headers.insert("content-type", "application/json".parse().unwrap());
    headers.insert("authorization", format!("Bearer {token}").parse().unwrap());
    HttpInput {
        method: Method::POST,
        path: path.into(),
        query: BTreeMap::new(),
        headers,
        body: serde_json::to_vec(&body).unwrap(),
        archive: None,
        peer: "127.0.0.1".into(),
        verified: None,
    }
}
fn board(server: &RemoteServer, id: &str) -> Arc<Service> {
    let service = server.service("project").unwrap();
    service.store.create(id, id, None).unwrap();
    service
        .store
        .checkpoint(id, 1, "saved", false, None)
        .unwrap();
    service
}
fn share_token(server: &RemoteServer, args: Value) -> String {
    server.share("project", &args).unwrap()["url"]
        .as_str()
        .unwrap()
        .split_once("#token=")
        .unwrap()
        .1
        .into()
}
#[test]
fn signing_roundtrip_rejects_tamper_kind_and_expiry() {
    let signer = Signer::new(b"01234567890123456789012345678901".to_vec()).unwrap();
    let token = signer
        .sign(&json!({"k":"file","exp":now()+10,"f":"数据/结果.json"}))
        .unwrap();
    assert_eq!(
        signer.verify(&token, "file").unwrap()["f"],
        "数据/结果.json"
    );
    assert!(signer.verify(&format!("x{token}"), "file").is_none());
    assert!(signer.verify(&token, "share").is_none());
    let expired = signer.sign(&json!({"k":"file","exp":now()-1})).unwrap();
    assert!(signer.verify(&expired, "file").is_none());
}
#[test]
fn stable_secret_is_atomically_shared_by_concurrent_starts() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("secret");
    let workers: Vec<_> = (0..8)
        .map(|_| {
            let path = path.clone();
            std::thread::spawn(move || load_secret(&path).unwrap())
        })
        .collect();
    let keys: Vec<_> = workers.into_iter().map(|w| w.join().unwrap()).collect();
    assert!(keys[0].len() >= 32);
    assert!(keys.iter().all(|key| key == &keys[0]));
}
#[test]
fn project_resolution_is_explicit_and_cannot_escape_workspace() {
    let (_dir, server) = host();
    let (a, _) = server.resolve(json!({"projectRoot":"sales"})).unwrap();
    let (b, _) = server.resolve(json!({})).unwrap();
    assert_eq!(a.project_name, "sales");
    assert_eq!(b.project_name, "default");
    for path in ["../outside", "/etc", "", "x/y"] {
        assert!(server.resolve(json!({"projectRoot":path})).is_err());
    }
}
#[cfg(unix)]
#[test]
fn a_project_symlink_cannot_escape_workspace() {
    let (dir, server) = host();
    let outside = dir.path().join("outside");
    fs::create_dir(&outside).unwrap();
    std::os::unix::fs::symlink(&outside, server.settings.workspace.join("escape")).unwrap();
    assert_eq!(
        server.service("escape").err().unwrap().code,
        "PROJECT_OUTSIDE_WORKSPACE"
    );
}
#[test]
fn multipage_scope_preserves_primary_and_revokes_every_containing_link() {
    let (_dir, server) = host();
    board(&server, "zmain");
    board(&server, "apage");
    let token = share_token(
        &server,
        json!({"dashboardId":"zmain","dashboardIds":["apage"]}),
    );
    let principal = server.principal(&token, "project").unwrap();
    assert_eq!(principal.primary.as_deref(), Some("zmain"));
    assert!(!principal.edit);
    assert!(principal.board("apage").is_ok());
    assert!(principal.board("other").is_err());
    let result = server
        .call_viewer("project", "dashboard_get", json!({}), &principal)
        .unwrap();
    assert_eq!(result["document"]["id"], "zmain");
    server.generation("project", "apage", true).unwrap();
    assert_eq!(
        server.principal(&token, "project").err().unwrap().code,
        "UNAUTHORIZED"
    );
}
#[test]
fn readers_are_pinned_to_saved_versions_and_cannot_write() {
    let (_dir, server) = host();
    let service = board(&server, "main");
    service.call("dashboard_patch",&json!({"dashboardId":"main","expectedRevision":1,"operations":[{"op":"set_title","value":"draft"}]})).unwrap();
    let token = share_token(&server, json!({"dashboardId":"main"}));
    let principal = server.principal(&token, "project").unwrap();
    let result = server
        .call_viewer(
            "project",
            "dashboard_get",
            json!({"dashboardId":"main"}),
            &principal,
        )
        .unwrap();
    assert_eq!(result["document"]["revision"], 1);
    assert_eq!(
        server
            .call_viewer(
                "project",
                "dashboard_patch",
                json!({"dashboardId":"main"}),
                &principal
            )
            .err()
            .unwrap()
            .code,
        "FORBIDDEN"
    );
    assert_eq!(
        server
            .call_viewer(
                "project",
                "dashboard_view",
                json!({"dashboardId":"main","expectedRevision":2}),
                &principal
            )
            .err()
            .unwrap()
            .code,
        "REVISION_CONFLICT"
    );
    let info = server
        .call_viewer(
            "project",
            "runtime_info",
            json!({"dashboardId":"main"}),
            &principal,
        )
        .unwrap();
    assert!(info.get("moduleRoot").is_none());
    assert!(info.get("runtimeRoot").is_none());
}
#[test]
fn annotation_identity_and_scope_are_independent_of_content() {
    let (_dir, server) = host();
    let service = board(&server, "main");
    let note = json!({"id":"note-one","text":"核对来源","createdAt":"2026-01-01T00:00:00Z","anchor":{"scope":"page","kind":"area","quote":"","rect":{"x":0.1,"y":0.1,"width":0.2,"height":0.1}},"author":{"name":"forged","verified":true}});
    let payload = json!({"append":note,"authorName":" Reader "});
    assert_eq!(
        annotation_response(&service, "main", Some(1), false, false, Some(&payload))
            .err()
            .unwrap()
            .code,
        "FORBIDDEN"
    );
    let first =
        annotation_response(&service, "main", Some(1), true, false, Some(&payload)).unwrap();
    let retry =
        annotation_response(&service, "main", Some(1), true, false, Some(&payload)).unwrap();
    assert_eq!(first, retry);
    let stored = annotation_response(&service, "main", Some(1), true, false, None).unwrap();
    assert_eq!(stored["annotations"].as_array().unwrap().len(), 1);
    assert_eq!(
        stored["annotations"][0]["author"],
        json!({"name":"Reader","verified":false})
    );
    assert_eq!(service.store.revision("main").unwrap(), 1);
    assert!(annotation_response(
        &service,
        "main",
        Some(1),
        true,
        false,
        Some(&json!({"annotations":[],"expectedAnnotations":[]}))
    )
    .is_err());
}
#[test]
fn host_and_origin_checks_reject_rebinding() {
    let (_dir, server) = host();
    let mut request = input(
        "/api/v1/catalog",
        "native-test-author-credential",
        json!({}),
    );
    assert!(server.settings.host_guard(&request.headers).is_ok());
    request
        .headers
        .insert("host", "evil.example".parse().unwrap());
    assert!(server.settings.host_guard(&request.headers).is_err());
    request
        .headers
        .insert("host", "127.0.0.1:8080".parse().unwrap());
    request
        .headers
        .insert("origin", "https://evil.example".parse().unwrap());
    assert!(server.settings.host_guard(&request.headers).is_err());
}
// @wu-test type=boundary | scope=trusted proxies | protects=forged forwarding headers bypass access-key rate limits
#[test]
fn forwarded_addresses_are_used_only_from_trusted_proxies() {
    let (_dir, server) = host();
    let mut settings = server.settings.clone();
    settings.forwarded_allow_ips = "127.0.0.1,10.0.0.0/8".into();
    let mut headers = HeaderMap::new();
    headers.insert("x-forwarded-for", "192.0.2.5, 10.0.0.3".parse().unwrap());
    assert_eq!(settings.client_ip("127.0.0.1", &headers), "192.0.2.5");
    assert_eq!(settings.client_ip("198.51.100.4", &headers), "198.51.100.4");
    headers.insert("x-forwarded-for", "forged, 192.0.2.5".parse().unwrap());
    assert_eq!(settings.client_ip("127.0.0.1", &headers), "127.0.0.1");
}
#[tokio::test]
async fn http_auth_is_enforced_before_body_or_project_lookup() {
    let (_dir, server) = host();
    let app = router(server, CancellationToken::new()).unwrap();
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/mcp")
                .header("Host", "127.0.0.1:8080")
                .body(Body::from("not-json"))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), 401);
    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/v1/p/missing/tools/dashboard_get")
                .header("Host", "127.0.0.1:8080")
                .body(Body::from("not-json"))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), 401);
}
// @wu-test type=integration | scope=workspace HTTP authentication | protects=unauthorized peers cannot occupy request-body readers or create unknown projects
#[tokio::test]
async fn workspace_authentication_precedes_body_consumption() {
    let (_dir, server) = host();
    let workspace = server.settings.workspace.clone();
    let app = router(server, CancellationToken::new()).unwrap();
    for path in [
        "/api/v1/p/missing/tools/dashboard_get",
        "/api/v1/p/missing/annotations/main",
        "/%61pi/v1/p/missing/tools/dashboard_get",
        "/api/v1/catalog",
        "/api/v1/share",
    ] {
        let (writer, reader) = tokio::io::duplex(16);
        let pending = Request::builder()
            .method("POST")
            .uri(path)
            .header("Host", "127.0.0.1:8080")
            .header("Content-Type", "application/json")
            .body(Body::from_stream(tokio_util::io::ReaderStream::new(reader)))
            .unwrap();
        let response = tokio::time::timeout(Duration::from_secs(2), app.clone().oneshot(pending))
            .await
            .expect("Authentication must not await untrusted body bytes")
            .unwrap();
        assert_eq!(response.status(), 401, "{path}");
        drop(writer);
        let oversized = Request::builder()
            .method("POST")
            .uri(path)
            .header("Host", "127.0.0.1:8080")
            .header("Content-Type", "application/json")
            .header("Content-Length", MAX_BODY + 1)
            .body(Body::empty())
            .unwrap();
        let response = tokio::time::timeout(Duration::from_secs(2), app.clone().oneshot(oversized))
            .await
            .expect("Authentication must precede body-size errors")
            .unwrap();
        assert_eq!(response.status(), 401, "{path}");
    }
    assert!(!workspace.join("missing").exists());
}
// @wu-test type=integration | scope=MCP HTTP authentication | protects=prefix aliases cannot bypass the exact endpoint's author check
#[tokio::test]
async fn mcp_descendants_cannot_bypass_author_authentication() {
    let (_dir, server) = host();
    board(&server, "main");
    let reader = share_token(&server, json!({"dashboardId":"main","access":"view"}));
    let app = router(server, CancellationToken::new()).unwrap();
    for path in ["/mcp/", "/mcp/anything"] {
        for token in ["", reader.as_str(), "native-test-author-credential"] {
            let mut request = Request::builder()
                .method("POST")
                .uri(path)
                .header("Host", "127.0.0.1:8080")
                .header("Content-Type", "application/json")
                .header("Accept", "application/json, text/event-stream");
            if !token.is_empty() {
                request = request.header("Authorization", format!("Bearer {token}"));
            }
            let response = app.clone().oneshot(request.body(Body::from(
                serde_json::to_vec(&json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"route-boundary","version":"1"}}})).unwrap(),
            )).unwrap()).await.unwrap();
            assert_eq!(response.status(), 404, "Unexpected MCP alias: {path}");
        }
    }
    for token in ["", reader.as_str()] {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp")
                    .header("Host", "127.0.0.1:8080")
                    .header("Authorization", format!("Bearer {token}"))
                    .body(Body::from("not-json"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), 401);
    }
}
#[tokio::test]
async fn http_rejects_oversized_and_wrong_content_type() {
    let (_dir, server) = host();
    let service = board(&server, "main");
    drop(service);
    let app = router(server, CancellationToken::new()).unwrap();
    let make = |kind: &str, len: usize| {
        Request::builder()
            .method("POST")
            .uri("/api/v1/p/project/tools/dashboard_get")
            .header("Host", "127.0.0.1:8080")
            .header("Authorization", "Bearer native-test-author-credential")
            .header("Content-Type", kind)
            .header("Content-Length", len)
            .body(Body::from("{}"))
            .unwrap()
    };
    assert_eq!(
        app.clone()
            .oneshot(make("application/json", MAX_BODY + 1))
            .await
            .unwrap()
            .status(),
        413
    );
    assert_eq!(
        app.oneshot(make("text/plain", 2)).await.unwrap().status(),
        415
    );
}
#[tokio::test]
async fn official_mcp_transport_initializes_and_exposes_only_author_tools() {
    let (_dir, server) = host();
    let app = router(server, CancellationToken::new()).unwrap();
    let request = |body: Value, session: Option<&str>| {
        let mut builder = Request::builder()
            .method("POST")
            .uri("/mcp")
            .header("Host", "127.0.0.1:8080")
            .header("Authorization", "Bearer native-test-author-credential")
            .header("Content-Type", "application/json")
            .header("Accept", "application/json, text/event-stream")
            .header("MCP-Protocol-Version", "2025-06-18");
        if let Some(session) = session {
            builder = builder.header("Mcp-Session-Id", session);
        }
        builder
            .body(Body::from(serde_json::to_vec(&body).unwrap()))
            .unwrap()
    };
    let response=app.clone().oneshot(request(json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"native-test","version":"1"}}}),None)).await.unwrap();
    assert_eq!(response.status(), 200);
    let session = response
        .headers()
        .get("mcp-session-id")
        .unwrap()
        .to_str()
        .unwrap()
        .to_owned();
    let _ = to_bytes(response.into_body(), MAX_BODY).await.unwrap();
    let notified = app
        .clone()
        .oneshot(request(
            json!({"jsonrpc":"2.0","method":"notifications/initialized"}),
            Some(&session),
        ))
        .await
        .unwrap();
    assert!(notified.status().is_success());
    let response = app
        .oneshot(request(
            json!({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}),
            Some(&session),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), 200);
    let bytes = to_bytes(response.into_body(), MAX_BODY).await.unwrap();
    let text = String::from_utf8(bytes.to_vec()).unwrap();
    assert!(text.contains("dashboard_submit"));
    assert!(!text.contains("\"name\":\"dashboard_patch\""));
    assert!(!text.contains("\"name\":\"dashboard_export_open\""));
}
