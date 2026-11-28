use super::*;

// @wu-test type=integration | scope=managed JSON and HTML exports | protects=chunked downloads preserve exact bytes and public snapshots strip author state without changing configuration exports
#[test]
fn managed_exports_preserve_configuration_but_redact_snapshot_capabilities() {
    let directory = tempfile::tempdir().unwrap();
    let document = json!({"id":"sales","revision":4,"manifest":{"title":"</script><script>untrusted()</script>","components":{},"sources":{"private":"secret-source"},"annotations":[{"text":"secret-annotation"}]},"snapshot":{"datasets":{"sales":[{"amount":10}]}},"browserLinks":{"editUrl":"secret-url"},"annotationAccess":{"canManageAnnotations":true}});
    let exported = export_dashboard(directory.path(), &document, "json").unwrap();
    let id = exported["export"]["id"].as_str().unwrap();
    let size = exported["export"]["bytes"].as_u64().unwrap();
    let mut offset = 0;
    let mut raw = vec![];
    loop {
        let part = read_export(directory.path(), "sales", id, "json", offset, 7).unwrap();
        raw.extend(STANDARD.decode(part["content"].as_str().unwrap()).unwrap());
        offset = part["nextOffset"].as_u64().unwrap();
        if part["hasMore"] == false {
            break;
        }
    }
    assert_eq!(raw.len() as u64, size);
    assert_eq!(serde_json::from_slice::<Value>(&raw).unwrap(), document);
    assert_eq!(
        read_export(directory.path(), "sales", id, "json", size, 1).unwrap()["content"],
        ""
    );
    assert!(read_export(directory.path(), "sales", id, "json", size + 1, 1).is_err());
    assert!(read_export(directory.path(), "sales", id, "json", 0, 0).is_err());
    assert!(read_export(directory.path(), "sales", id, "json", 0, 262145).is_err());
    let html = export_dashboard(directory.path(), &document, "html").unwrap();
    let html = fs::read_to_string(html["export"]["path"].as_str().unwrap()).unwrap();
    for private in [
        "secret-source",
        "secret-annotation",
        "secret-url",
        "</script><script>untrusted()",
    ] {
        assert!(!html.contains(private), "{private}");
    }
    assert!(html.contains("\\u003c/script>"));
    assert!(export_dashboard(directory.path(), &document, "csv").is_err());
    assert!(export_target(directory.path(), "sales", "invalid", "json").is_err());
    assert!(export_target(directory.path(), "sales", id, "exe").is_err());
    assert_eq!(
        export_path(directory.path(), "missing", id, "json")
            .unwrap_err()
            .code,
        "NOT_FOUND"
    );
    assert_eq!(
        open_export(directory.path(), "sales", id, "json", "run")
            .unwrap_err()
            .code,
        "INVALID_ARGUMENT"
    );
    #[cfg(not(target_os = "macos"))]
    assert_eq!(
        open_export(directory.path(), "sales", id, "json", "open")
            .unwrap_err()
            .code,
        "INVALID_ARGUMENT"
    );
}

// @wu-test type=boundary | scope=managed export symlinks | protects=an export ID cannot read or create files outside its project through a replaced parent directory
#[cfg(unix)]
#[test]
fn managed_exports_reject_parent_links_outside_the_project() {
    let root = tempfile::tempdir().unwrap();
    let outside = tempfile::tempdir().unwrap();
    fs::create_dir(root.path().join("exports")).unwrap();
    let id = "a".repeat(32);
    std::os::unix::fs::symlink(outside.path(), root.path().join("exports").join(&id)).unwrap();
    fs::write(outside.path().join("sales.json"), b"secret").unwrap();
    assert_eq!(
        export_target(root.path(), "sales", &id, "json")
            .unwrap_err()
            .code,
        "INVALID_PATH"
    );
    assert_eq!(
        fs::read(outside.path().join("sales.json")).unwrap(),
        b"secret"
    );
}
