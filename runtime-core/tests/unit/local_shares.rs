use super::*;
use std::{io::Write, net::TcpListener, thread::JoinHandle, time::Instant};

type HttpMessage = (String, Vec<u8>);

fn replies(responses: Vec<(u16, Vec<u8>)>) -> (String, JoinHandle<Vec<HttpMessage>>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    let task = std::thread::spawn(move || {
        let mut requests = vec![];
        for (status, body) in responses {
            let start = Instant::now();
            let mut stream = loop {
                match listener.accept() {
                    Ok((stream, _)) => break stream,
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        assert!(
                            start.elapsed() < Duration::from_secs(15),
                            "publication request did not arrive"
                        );
                        std::thread::sleep(Duration::from_millis(2));
                    }
                    Err(error) => panic!("publication listener failed: {error}"),
                }
            };
            stream
                .set_read_timeout(Some(Duration::from_secs(10)))
                .unwrap();
            let mut request = vec![];
            let mut buffer = [0u8; 4096];
            let end = loop {
                let count = stream.read(&mut buffer).unwrap();
                assert!(count > 0);
                request.extend_from_slice(&buffer[..count]);
                if let Some(index) = request.windows(4).position(|part| part == b"\r\n\r\n") {
                    break index + 4;
                }
            };
            let headers = String::from_utf8(request[..end].to_vec()).unwrap();
            assert!(headers
                .to_ascii_lowercase()
                .contains("authorization: bearer local-test-token"));
            let length = headers
                .lines()
                .filter_map(|line| line.split_once(':'))
                .find(|(key, _)| key.eq_ignore_ascii_case("content-length"))
                .map_or(0, |(_, value)| value.trim().parse::<usize>().unwrap());
            while request.len() < end + length {
                let count = stream.read(&mut buffer).unwrap();
                assert!(count > 0);
                request.extend_from_slice(&buffer[..count]);
            }
            requests.push((headers, request[end..end + length].to_vec()));
            write!(
                stream,
                "HTTP/1.1 {status} Test\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                body.len()
            )
            .unwrap();
            let _ = stream.write_all(&body);
        }
        requests
    });
    (url, task)
}

fn local(service: &Service, url: String) -> LocalShares<'_> {
    let root = service.project_root.as_ref().unwrap().join("dashboards");
    let value = LocalShares {
        service,
        url,
        token: "local-test-token".into(),
        project: "default".into(),
        path: root.join("share-references.sqlite3"),
        root,
        source: "local-source".into(),
        parquet_layout: "sharded".into(),
    };
    value.connect().unwrap().execute_batch("CREATE TABLE requests(id TEXT PRIMARY KEY,board TEXT NOT NULL,fingerprint TEXT NOT NULL,revision INTEGER NOT NULL,service_url TEXT NOT NULL,project TEXT NOT NULL,archive TEXT,archive_sha TEXT,receipt TEXT,state TEXT NOT NULL,created_at REAL NOT NULL);").unwrap();
    value
}

fn remember(local: &LocalShares<'_>, id: &str, receipt: &Value) {
    local.connect().unwrap().execute("INSERT INTO requests(id,board,fingerprint,revision,service_url,project,receipt,state,created_at) VALUES(?,?,?,?,?,?,?,?,?)",params![id,"sales","old-request",receipt["revision"].as_i64().unwrap(),local.url,local.project,receipt.to_string(),"active",1.0]).unwrap();
}

// @wu-test type=integration | scope=share-service failure responses | protects=unconfirmed, malformed and oversized responses cannot be mistaken for saved publications or leak unbounded bytes
#[test]
fn publication_requests_preserve_server_errors_and_reject_unconfirmed_responses() {
    let directory = tempfile::tempdir().unwrap();
    let service = Service::new(
        &directory.path().join("runtime"),
        None,
        Some(&directory.path().join("project")),
    )
    .unwrap();
    let (url, task) = replies(vec![
        (
            403,
            br#"{"error":{"code":"FORBIDDEN","message":"different owner"}}"#.to_vec(),
        ),
        (500, b"not json".to_vec()),
        (200, b"not json".to_vec()),
        (200, br#"{"ok":false}"#.to_vec()),
        (200, b"[]".to_vec()),
        (200, vec![b'x'; 16 * 1024 * 1024 + 1]),
    ]);
    let local = local(&service, url);
    let forbidden = local.request("GET", "/owner", &[], None).unwrap_err();
    assert_eq!(forbidden.code, "FORBIDDEN");
    assert_eq!(forbidden.status, 403);
    for code in [
        "SHARE_SERVICE_FAILED",
        "SHARE_SERVICE_UNAVAILABLE",
        "SHARE_SERVICE_FAILED",
        "SHARE_SERVICE_FAILED",
        "PAYLOAD_TOO_LARGE",
    ] {
        assert_eq!(
            local.request("GET", "/owner", &[], None).unwrap_err().code,
            code
        );
    }
    assert_eq!(
        local
            .request("bad method", "/owner", &[], None)
            .unwrap_err()
            .code,
        "INVALID_ARGUMENT"
    );
    assert_eq!(task.join().unwrap().len(), 6);
}

// @wu-test type=integration | scope=local share replacement retries | protects=a new publication remains recoverable when revoking its predecessor fails and retrying does not upload another copy
#[test]
fn replacement_keeps_the_new_receipt_until_previous_revocation_is_confirmed() {
    let directory = tempfile::tempdir().unwrap();
    let service = Service::new(
        &directory.path().join("runtime"),
        None,
        Some(&directory.path().join("project")),
    )
    .unwrap();
    let saved = service
        .call(
            "dashboard_submit",
            &json!({"dashboardId":"sales","createTitle":"Sales","operations":[{"op":"set_title","value":"Sales"}]}),
        )
        .unwrap();
    let revision = saved["revision"].as_i64().unwrap();
    let old = "a".repeat(32);
    let new = "b".repeat(32);
    let receipt = json!({"shareId":new,"accessKey":"12345678","url":format!("https://share.test/s/{new}/"),"revision":revision,"annotationMode":"view","expiresAt":null});
    let (url, task) = replies(vec![
        (200, serde_json::to_vec(&receipt).unwrap()),
        (
            503,
            br#"{"error":{"code":"CLEANUP_UNAVAILABLE","message":"retry cleanup"}}"#.to_vec(),
        ),
        (
            200,
            serde_json::to_vec(&json!({"shareId":new,"revision":revision})).unwrap(),
        ),
        (
            200,
            br#"{"revoked":true,"cleanupState":"complete","cleanupExecutor":"test"}"#.to_vec(),
        ),
    ]);
    let mut local = local(&service, url);
    remember(
        &local,
        "old-request",
        &json!({"shareId":old,"revision":revision,"url":"https://share.test/old","expiresAt":null,"annotationMode":"view"}),
    );
    let first = local.replace("sales", &old, revision, "never").unwrap();
    assert_eq!(first["shareId"], new);
    assert_eq!(first["previousRevoked"], false);
    assert_eq!(first["followUp"], "dashboard_share_delete");
    assert_eq!(first["warning"]["code"], "CLEANUP_UNAVAILABLE");
    let retried = local.replace("sales", &old, revision, "never").unwrap();
    assert_eq!(retried["shareId"], new);
    assert_eq!(retried["previousRevoked"], true);
    assert_eq!(
        local.revoke("sales", &old).unwrap()["cleanupState"],
        "complete"
    );
    let status = local.status("sales", None).unwrap();
    assert_eq!(status["shares"].as_array().unwrap().len(), 2);
    assert_eq!(
        local.status("sales", Some(&old)).unwrap()["shares"][0]["state"],
        "revoked"
    );
    assert_eq!(
        local.status("sales", Some(&new)).unwrap()["shares"][0]["state"],
        "active"
    );
    assert_eq!(
        local.reference("different", &new).unwrap_err().code,
        "FORBIDDEN"
    );
    local.project = "different-destination".into();
    assert_eq!(
        local.reference("sales", &new).unwrap_err().code,
        "SHARE_SERVICE_MISMATCH"
    );
    let requests = task.join().unwrap();
    assert_eq!(
        requests
            .iter()
            .filter(|(headers, _)| headers.starts_with("POST "))
            .count(),
        1
    );
    assert!(requests[0]
        .0
        .to_ascii_lowercase()
        .contains("content-type: application/zip"));
    assert!(requests[0].1.starts_with(b"PK"));
    assert!(requests[1].0.starts_with("DELETE "));
    assert!(requests[2].0.starts_with("GET "));
    assert!(requests[3].0.starts_with("DELETE "));
}
#[test]
fn publication_service_credentials_require_a_trusted_origin() {
    for url in [
        "https://shares.example/path",
        "http://localhost:8123",
        "http://127.0.0.1:8123",
        "http://[::1]:8123",
    ] {
        validate_service_url(url).unwrap();
    }
    for url in [
        "http://shares.example",
        "https://user:password@shares.example",
        "https://shares.example/?token=x",
        "https://shares.example/#key=x",
    ] {
        assert!(validate_service_url(url).is_err(), "{url}");
    }
}
