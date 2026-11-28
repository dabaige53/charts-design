use super::*;
use std::{
    io::{BufRead, BufReader, Read, Write},
    net::TcpListener,
    thread,
};

fn gateway(status: u16, body: &str) -> (CloudDatabase, thread::JoinHandle<Value>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let body = body.to_owned();
    let request = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        stream
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut reader = BufReader::new(stream.try_clone().unwrap());
        let mut headers = Vec::new();
        let mut length = 0;
        loop {
            let mut line = String::new();
            reader.read_line(&mut line).unwrap();
            if line == "\r\n" {
                break;
            }
            if let Some(value) = line.to_ascii_lowercase().strip_prefix("content-length:") {
                length = value.trim().parse().unwrap();
            }
            headers.push(line);
        }
        let mut data = vec![0; length];
        reader.read_exact(&mut data).unwrap();
        assert!(headers[0].starts_with("POST /rpc/charts_runtime "));
        assert!(headers.iter().any(|header| {
            header.split_once(':').is_some_and(|(name, value)| {
                name.eq_ignore_ascii_case("authorization") && value.trim() == "Bearer test-key"
            })
        }));
        write!(stream, "HTTP/1.1 {status} Response\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len()).unwrap();
        serde_json::from_slice(&data).unwrap()
    });
    (
        CloudDatabase {
            backend: "cloudbase".into(),
            function: "charts_runtime".into(),
            url: format!("http://{address}/rpc"),
            key: "test-key".into(),
            database_url: String::new(),
        },
        request,
    )
}

// @wu-test type=integration | scope=database gateway RPC contract | protects=cloud errors lose conflict semantics or a failed gateway silently falls back to local state
#[test]
fn gateway_preserves_rpc_arguments_errors_and_unavailable_state() {
    let (database, request) = gateway(200, r#"{"saved":true,"revision":4}"#);
    let payload = json!({"board":"sales","expected":3});
    assert_eq!(
        database.call("commit", "finance", &payload).unwrap(),
        json!({"saved":true,"revision":4})
    );
    assert_eq!(
        request.join().unwrap(),
        json!({"action":"commit","project":"finance","payload":payload})
    );
    assert_eq!(
        database.with_function("charts_assets").unwrap().function,
        "charts_assets"
    );
    assert_eq!(
        database.with_function("not_allowed").err().unwrap().code,
        "INVALID_CONFIG"
    );
    assert_eq!(
        database
            .call("commit", "finance", &json!([]))
            .unwrap_err()
            .code,
        "INVALID_ARGUMENT"
    );

    for (code, status) in [
        ("NOT_FOUND", 404),
        ("NO_SAVED_VERSION", 404),
        ("FORBIDDEN", 403),
        ("SHARE_EXPIRED", 410),
        ("SHARE_UNAVAILABLE", 410),
        ("INVALID_BATCH", 400),
        ("REVISION_CONFLICT", 409),
        ("ANNOTATION_CONFLICT", 409),
        ("ALREADY_EXISTS", 409),
        ("DATA_CONFLICT", 409),
        ("DATA_INCOMPLETE", 409),
        ("CHECKPOINT_IN_USE", 409),
        ("PLAN_CHANGED", 409),
        ("ASSET_UNAVAILABLE", 409),
        ("REVISION_DELETED", 409),
        ("CONFIRMATION_REQUIRED", 409),
        ("STORAGE_MIGRATED", 409),
        ("ANNOTATION_LIMIT", 409),
    ] {
        let (database, request) = gateway(400, &json!({"message":code}).to_string());
        let error = database.call("commit", "finance", &payload).unwrap_err();
        assert_eq!(error.code, code);
        assert_eq!(error.status, status);
        request.join().unwrap();
    }
    for (body, status, code) in [
        ("not JSON", 200, "CLOUD_DATABASE_FAILED"),
        (
            r#"{"message":"unknown failure"}"#,
            502,
            "CLOUD_DATABASE_FAILED",
        ),
    ] {
        let (database, request) = gateway(status, body);
        let error = database.call("list", "finance", &json!({})).unwrap_err();
        assert_eq!(error.code, code);
        assert_eq!(error.status, 503);
        request.join().unwrap();
    }
    let error = database.call("list", "finance", &json!({})).unwrap_err();
    assert_eq!(error.code, "CLOUD_DATABASE_UNAVAILABLE");
    assert_eq!(error.status, 503);
}
