use super::*;

fn definition(id: &str, mode: &str) -> Value {
    json!({"shareId":id,"owner":"owner","pages":[{"id":"board","revision":2}],"expiresAt":null,"stagingUntil":super::super::shares::now()+3600,"annotationMode":mode,"sourceDigest":"digest"})
}

// @wu-test type=boundary | scope=publication annotation staging and retirement | protects=expired uploads cannot be reactivated and cleanup handles incomplete databases without reopening retired share IDs
#[test]
fn expired_staging_and_incomplete_databases_retire_permanently() {
    let root = tempfile::tempdir().unwrap();
    let storage = Storage::private(root.path().to_owned(), "test").unwrap();
    let notes = ShareAnnotations::for_storage(&storage).unwrap();
    let id = "0123456789abcdef0123456789abcdef";
    assert_eq!(
        notes.call("ready", &json!({"shareId":id})).unwrap()["ready"],
        true
    );
    assert_eq!(
        notes
            .call("read", &json!({"shareId":id,"dashboardId":"board"}))
            .unwrap_err()
            .code,
        "SHARE_UNAVAILABLE"
    );
    let mut expired = definition(id, "annotate");
    expired["stagingUntil"] = json!(0);
    notes.call("configure", &expired).unwrap();
    assert_eq!(
        notes
            .call("activate", &json!({"shareId":id}))
            .unwrap_err()
            .code,
        "SHARE_EXPIRED"
    );
    assert_eq!(
        notes.call("configure", &expired).unwrap_err().code,
        "SHARE_EXPIRED"
    );
    assert_eq!(
        notes.call("cleanup_claim", &json!({"shareId":id})).unwrap()["claimed"],
        true
    );
    assert_eq!(
        notes
            .call("ready", &json!({"shareId":id}))
            .unwrap_err()
            .code,
        "SHARE_EXPIRED"
    );
    assert_eq!(
        notes.call("delete", &json!({"shareId":id})).unwrap()["deleted"],
        true
    );
    let incomplete = "11111111111111111111111111111111";
    let path = root
        .path()
        .join("shares")
        .join(incomplete)
        .join("annotations.sqlite3");
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    Connection::open(path).unwrap();
    assert_eq!(
        notes
            .call("delete", &json!({"shareId":incomplete}))
            .unwrap()["deleted"],
        true
    );
    assert_eq!(
        notes
            .call("configure", &definition(incomplete, "view"))
            .unwrap_err()
            .code,
        "SHARE_EXPIRED"
    );
    assert_eq!(
        notes.call("ready", &json!({})).unwrap_err().code,
        "INVALID_ARGUMENT"
    );
    assert_eq!(
        notes
            .call("ready", &json!({"shareId":"../outside"}))
            .unwrap_err()
            .code,
        "INVALID_ARGUMENT"
    );
}

// @wu-test type=boundary | scope=share annotation append limits | protects=the 101st unique note fails atomically while idempotent retries remain available and read-only shares cannot accept notes
#[test]
fn annotation_limits_keep_successful_retries_and_read_only_access_intact() {
    let root = tempfile::tempdir().unwrap();
    let storage = Storage::private(root.path().to_owned(), "test").unwrap();
    let notes = ShareAnnotations::for_storage(&storage).unwrap();
    let id = "22222222222222222222222222222222";
    notes
        .call("configure", &definition(id, "annotate"))
        .unwrap();
    notes.call("activate", &json!({"shareId":id})).unwrap();
    let payload = |n| json!({"shareId":id,"dashboardId":"board","annotation":{"id":format!("note-{n}"),"text":"Review","context":{"designRevision":2}},"fingerprint":format!("fingerprint-{n}")});
    for n in 0..100 {
        assert_eq!(
            notes.call("append", &payload(n)).unwrap()["id"],
            format!("note-{n}")
        );
    }
    assert_eq!(
        notes.call("append", &payload(100)).unwrap_err().code,
        "ANNOTATION_LIMIT"
    );
    assert_eq!(notes.call("append", &payload(0)).unwrap()["id"], "note-0");
    assert_eq!(
        notes
            .call("read", &payload(0))
            .unwrap()
            .as_array()
            .unwrap()
            .len(),
        100
    );
    assert_eq!(
        notes.call("invalid", &payload(0)).unwrap_err().code,
        "INVALID_ARGUMENT"
    );
    assert_eq!(
        notes.call("read", &json!({"shareId":id})).unwrap_err().code,
        "INVALID_ARGUMENT"
    );
    let read_only = "33333333333333333333333333333333";
    notes
        .call("configure", &definition(read_only, "view"))
        .unwrap();
    notes
        .call("activate", &json!({"shareId":read_only}))
        .unwrap();
    let mut blocked = payload(0);
    blocked["shareId"] = json!(read_only);
    assert_eq!(
        notes.call("append", &blocked).unwrap_err().code,
        "FORBIDDEN"
    );
    assert_eq!(notes.call("read", &blocked).unwrap(), json!([]));
    let mut retried = definition(id, "annotate");
    retried["expiresAt"] = json!(super::super::shares::now() + 3600);
    assert!(notes.call("configure", &retried).unwrap()["expiresAt"].is_null());
}
