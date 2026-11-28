use super::*;
use std::io::Write;
use std::sync::{Arc, Barrier};

fn test_manager(path: &Path) -> CloudShares {
    let storage = Storage::private(path.to_owned(), "test-timer").unwrap();
    put_json(
        &storage,
        "cleaner-status.json",
        &json!({"completedAt":now()}),
    )
    .unwrap();
    CloudShares::new(storage, "https://share.example.test/gateway/").unwrap()
}

fn saved_page(service: &Service, id: &str) -> i64 {
    let saved = service.call("dashboard_submit", &json!({
        "dashboardId":id,"createTitle":id,"operations":[
            {"op":"put_source","id":"fixture","value":{"kind":"fixture","name":"Sales"}},
            {"op":"put_dataset","id":"sales","meta":{"sourceId":"fixture","fields":{"region":{"type":"string"},"amount":{"type":"number"}}},"rows":[{"region":"East","amount":10},{"region":"West","amount":20}]},
            {"op":"put_component","id":"detail","value":{"kind":"table","title":"Sales","datasetId":"sales"}}
        ]
    })).unwrap();
    assert_eq!(saved["ok"], true);
    let revision = saved["revision"].as_i64().unwrap();
    let published = service
        .call(
            "dashboard_publish",
            &json!({"dashboardId":id,"expectedRevision":revision,"revision":revision}),
        )
        .unwrap();
    assert_eq!(published["publishedRevision"], revision);
    revision
}

// @wu-test type=integration | scope=fixed multi-page publications | protects=sharing uses published versions, isolates owner data and replaces links only after a complete new copy
#[test]
fn published_pages_remain_fixed_and_replacement_retires_the_old_link() {
    let root = tempfile::tempdir().unwrap();
    let service = Service::new(
        &root.path().join("runtime"),
        None,
        Some(&root.path().join("project")),
    )
    .unwrap();
    let manager = test_manager(&root.path().join("shares"));
    let revision = saved_page(&service, "overview");
    let second_revision = saved_page(&service, "detail");
    let pages = [json!({"dashboardId":"detail","expectedRevision":second_revision})];
    let id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    assert_eq!(
        manager
            .publish(
                &service,
                "overview",
                revision,
                "never",
                Some("bad"),
                None,
                None,
                "view"
            )
            .unwrap_err()
            .code,
        "INVALID_ARGUMENT"
    );
    assert_eq!(
        manager
            .publish(
                &service,
                "overview",
                revision + 1,
                "never",
                None,
                None,
                None,
                "view"
            )
            .unwrap_err()
            .code,
        "REVISION_CONFLICT"
    );
    let duplicate = [json!({"dashboardId":"overview","expectedRevision":revision})];
    assert_eq!(
        manager
            .publish(
                &service,
                "overview",
                revision,
                "never",
                None,
                Some(&duplicate),
                None,
                "view"
            )
            .unwrap_err()
            .code,
        "INVALID_ARGUMENT"
    );
    let receipt = manager
        .publish(
            &service,
            "overview",
            revision,
            "7d",
            Some("12345678"),
            Some(&pages),
            Some(id),
            "annotate",
        )
        .unwrap();
    assert_eq!(receipt["pages"].as_array().unwrap().len(), 2);
    assert_eq!(
        receipt["url"],
        format!("https://share.example.test/gateway/s/{id}/")
    );
    assert_eq!(receipt["cleanupExecutor"], "test-timer");
    assert_eq!(
        manager
            .publish(
                &service,
                "overview",
                revision,
                "7d",
                Some("12345678"),
                Some(&pages),
                Some(id),
                "annotate"
            )
            .unwrap(),
        receipt
    );
    assert_eq!(
        manager.quick_result(id, "87654321", "7d").unwrap_err().code,
        "REVISION_CONFLICT"
    );
    assert_eq!(
        manager.authenticate(id, "wrong").unwrap_err().code,
        "INVALID_ACCESS_KEY"
    );
    let control = manager.authenticate(id, "12345678").unwrap();
    let document: Value =
        serde_json::from_slice(&manager.content(id, "document.json", None).unwrap()).unwrap();
    let detail: Value = serde_json::from_slice(
        &manager
            .content(id, "pages/detail/document.json", Some(&control))
            .unwrap(),
    )
    .unwrap();
    assert_eq!(document["revision"], revision);
    assert_eq!(document["staticPages"].as_array().unwrap().len(), 2);
    assert_eq!(detail["revision"], second_revision);
    assert!(detail["staticFiles"]["sales"][0]
        .as_str()
        .unwrap()
        .starts_with("../../data/"));
    assert_eq!(
        document["annotationAccess"]["endpoint"],
        format!("/gateway/s/{id}/api/annotations")
    );
    assert!(document["manifest"].get("annotations").is_none());
    assert!(manager
        .content(id, "../control.json", Some(&control))
        .is_err());
    assert!(manager.content(id, "missing.json", Some(&control)).is_err());
    assert_eq!(
        manager
            .publication_page(id, Some("absent"), None)
            .unwrap_err()
            .code,
        "FORBIDDEN"
    );
    let note = json!({"id":"reader-note","componentId":"detail","text":"Please explain this amount","createdAt":"2026-11-28T00:00:00Z","anchor":{"scope":"component","kind":"element","quote":"","rect":{"x":0,"y":0,"width":1,"height":1}},"author":{"name":"Admin","verified":true},"view":{"revision":revision,"filters":[]}});
    let saved = manager
        .append_annotation(id, None, &note, Some("  Reader  "))
        .unwrap();
    assert_eq!(
        saved["annotation"]["author"],
        json!({"name":"Reader","verified":false})
    );
    assert_eq!(saved["annotation"]["context"]["designRevision"], revision);
    assert_eq!(
        manager
            .append_annotation(id, None, &note, Some("  Reader  "))
            .unwrap(),
        saved
    );
    assert_eq!(manager.annotations(id, None).unwrap()["count"], 1);
    assert_eq!(manager.annotations(id, Some("detail")).unwrap()["count"], 0);
    assert!(
        service.store.get("overview", false).unwrap()["manifest"]["annotations"]
            .as_array()
            .is_none_or(Vec::is_empty)
    );
    let mut wrong = note.clone();
    wrong["id"] = json!("wrong");
    wrong["view"]["revision"] = json!(revision + 1);
    assert_eq!(
        manager
            .append_annotation(id, None, &wrong, None)
            .unwrap_err()
            .code,
        "REVISION_CONFLICT"
    );
    wrong["view"]["revision"] = json!(revision);
    wrong["componentId"] = json!("not-published");
    assert_eq!(
        manager
            .append_annotation(id, None, &wrong, None)
            .unwrap_err()
            .code,
        "INVALID_ARGUMENT"
    );
    let status = manager.status(&service, "overview", None).unwrap();
    assert_eq!(status["shares"].as_array().unwrap().len(), 1);
    assert_eq!(status["shares"][0]["cleanupState"], "scheduled");
    let outsider = Service::new(
        &root.path().join("other-runtime"),
        None,
        Some(&root.path().join("other-project")),
    )
    .unwrap();
    assert_eq!(
        manager.status(&outsider, "overview", Some(id)).unwrap()["shares"],
        json!([])
    );
    assert_eq!(
        manager.revoke(&outsider, "overview", id).unwrap_err().code,
        "FORBIDDEN"
    );
    let replacement = manager
        .replace(&service, "overview", id, revision, "never")
        .unwrap();
    assert_eq!(replacement["previousRevoked"], true);
    assert_ne!(replacement["shareId"], receipt["shareId"]);
    assert_ne!(replacement["accessKey"], receipt["accessKey"]);
    assert_eq!(
        manager.authenticate(id, "12345678").unwrap_err().code,
        "SHARE_EXPIRED"
    );
    assert_eq!(
        manager.annotations(id, None).unwrap_err().code,
        "SHARE_EXPIRED"
    );
    let next = replacement["shareId"].as_str().unwrap();
    assert_eq!(
        manager.status(&service, "overview", Some(next)).unwrap()["shares"][0]["cleanupState"],
        "not_scheduled"
    );
    assert_eq!(
        manager.revoke(&service, "overview", next).unwrap()["revoked"],
        true
    );
    assert_eq!(
        cleanup_due(&manager.storage, Some(now())).unwrap()["removed"],
        2
    );
    assert!(manager
        .storage
        .list(&format!("shares/{next}/"))
        .unwrap()
        .is_empty());
}

// @wu-test type=behavior | scope=cloud browser document conversion | protects=private author fields stay out of read-only pages while exact datasets, options and partitions retain authorized URLs
#[test]
fn browser_documents_map_only_referenced_assets_and_redact_author_fields() {
    let reference = json!({"version":"version","fields":{"region":{"type":"string"}}});
    let document = json!({"schemaVersion":2,"id":"board","revision":4,"manifest":{"title":"Sales","sources":{"query":{"kind":"query","query":{"sql":"SELECT region FROM sales","credentials":"private"}},"file":{"kind":"fixture","path":"private.csv"}},"queries":{"hidden":"private"},"annotations":[{"text":"private"}],"components":{"table":{"kind":"table","datasetId":"sales"},"bound":{"kind":"legacy","binding":{"datasetId":"sales"}},"stat":{"kind":"legacy"}}},"snapshot":{"datasets":{"sales":[{"region":"secret"}]},"datasetRefs":{"sales":reference,"unused":{"version":"do-not-fetch"}},"componentDataRefs":{"stat":reference,"deleted":{"version":"do-not-fetch"}}},"computed":{"filterPages":{"all":{"values":["East"],"offset":0,"hasMore":false},"partial":{"values":["West"],"offset":1,"hasMore":false},"more":{"values":[],"offset":0,"hasMore":true}}},"statisticalArtifacts":{"stat":{"svg":"<svg/>","provenance":{"sql":"private"}}}});
    let asset = json!({"id":"asset1","descriptor":{"shards":["rows.parquet"],"options":{"region":{"field":"region","files":["regions.parquet"]},"legacy":"options.json.gz"},"partitionIndex":{"field":"region","entries":[{"value":"East","files":["rows.parquet"]}]}}});
    let mut seen = vec![];
    let web = web_document_with_assets(
        &document,
        |id, name| format!("/authorized/{id}/{name}"),
        false,
        true,
        |r| {
            seen.push(r.clone());
            Ok(asset.clone())
        },
    )
    .unwrap();
    assert_eq!(seen, vec![reference.clone(), reference]);
    assert_eq!(web["versionKey"], "board:4");
    assert_eq!(web["storageFormat"], "cos-v1");
    assert_eq!(
        web["staticFiles"]["sales"],
        json!(["/authorized/asset1/rows.parquet"])
    );
    assert_eq!(web["staticFiles"].as_object().unwrap().len(), 2);
    assert_eq!(
        web["staticComponentDatasets"],
        json!({"stat":"component-stat"})
    );
    assert_eq!(web["staticFilterOptions"], json!({"all":["East"]}));
    assert_eq!(
        web["staticOptions"]["sales"]["legacy"],
        "/authorized/asset1/options.json.gz"
    );
    assert_eq!(
        web["staticOptions"]["sales"]["region"]["files"],
        json!(["/authorized/asset1/regions.parquet"])
    );
    assert_eq!(
        web["staticPartitionIndexes"]["sales"]["entries"][0]["files"],
        json!(["/authorized/asset1/rows.parquet"])
    );
    assert_eq!(web["snapshot"]["datasets"], json!({}));
    assert_eq!(
        web["manifest"]["sources"],
        json!({"query":{"query":{"sql":"SELECT region FROM sales"}}})
    );
    assert!(web["manifest"].get("queries").is_none());
    assert!(web["manifest"].get("annotations").is_none());
    assert!(web["statisticalArtifacts"]["stat"]
        .get("provenance")
        .is_none());
    let editable = web_document_with_assets(
        &document,
        |id, name| format!("{id}/{name}"),
        true,
        false,
        |_| Ok(asset.clone()),
    )
    .unwrap();
    assert_eq!(
        editable["manifest"]["sources"],
        document["manifest"]["sources"]
    );
    assert_eq!(
        editable["manifest"]["annotations"],
        document["manifest"]["annotations"]
    );
    assert_eq!(
        web_document_with_assets(
            &document,
            |_, _| String::new(),
            false,
            false,
            |_| Ok(Value::Null)
        )
        .unwrap_err()
        .code,
        "ASSET_UNAVAILABLE"
    );
    for broken in [
        json!({"id":"x","descriptor":{}}),
        json!({"id":"x","descriptor":{"shards":[null]}}),
        json!({"id":"x","descriptor":{"shards":[],"options":{"region":{}}}}),
        json!({"id":"x","descriptor":{"shards":[],"options":{"region":{"files":[false]}}}}),
        json!({"id":"x","descriptor":{"shards":[],"partitionIndex":{"entries":"invalid"}}}),
        json!({"id":"x","descriptor":{"shards":[],"partitionIndex":{"entries":[{"files":null}]}}}),
        json!({"id":"x","descriptor":{"shards":[],"partitionIndex":{"entries":[{"files":[1]}]}}}),
    ] {
        assert!(web_document_with_assets(
            &document,
            |_, _| String::new(),
            false,
            false,
            |_| Ok(broken.clone())
        )
        .is_err());
    }
    assert_eq!(
        document["snapshot"]["datasets"]["sales"][0]["region"],
        "secret"
    );
}

fn publication_zip(document: &Value, manifest: &Value, additional: &[(&str, &[u8])]) -> Vec<u8> {
    let mut zip = zip::ZipWriter::new(Cursor::new(Vec::new()));
    for (name, raw) in [
        ("document.json", json_bytes(document).unwrap()),
        ("export-manifest.json", json_bytes(manifest).unwrap()),
    ] {
        zip.start_file(name, zip::write::SimpleFileOptions::default())
            .unwrap();
        zip.write_all(&raw).unwrap();
    }
    for (name, raw) in additional {
        zip.start_file(*name, zip::write::SimpleFileOptions::default())
            .unwrap();
        zip.write_all(raw).unwrap();
    }
    zip.finish().unwrap().into_inner()
}

// @wu-test type=boundary | scope=imported publication archives | protects=zip traversal, missing resources, version mismatches and reused request identities cannot publish misleading or unsafe copies
#[test]
fn imported_archives_reject_invalid_manifests_and_preserve_retry_identity() {
    let root = tempfile::tempdir().unwrap();
    let manager = test_manager(root.path());
    let source = "a".repeat(64);
    let secret = [3u8; 32];
    let document = json!({"schemaVersion":2,"id":"board","revision":3,"manifest":{"title":"Saved","components":{},"sources":{"private":"secret"},"annotations":[{"text":"author-only"}]},"snapshot":{"datasets":{"private":[1]}},"staticFiles":{"sales":["data/sales.json.gz"]}});
    let manifest = json!({"dashboardId":"board","revision":3});
    let zip = publication_zip(
        &document,
        &manifest,
        &[
            ("data/sales.json.gz", b"bytes"),
            ("app.js", b"untrusted-uploaded-script"),
        ],
    );
    let import = |bytes: &[u8], request: &str| {
        manager.import_site(bytes, &source, request, &secret, "view", "30d", None)
    };
    let receipt = import(&zip, "request").unwrap();
    let id = receipt["shareId"].as_str().unwrap();
    assert_eq!(import(&zip, "request").unwrap(), receipt);
    assert_eq!(
        manager.content(id, "app.js", None).unwrap(),
        fs::read(assets::dist().join("app.js")).unwrap()
    );
    let exported: Value =
        serde_json::from_slice(&manager.content(id, "document.json", None).unwrap()).unwrap();
    assert!(exported["manifest"].get("sources").is_none());
    assert!(exported["manifest"].get("annotations").is_none());
    assert_eq!(exported["snapshot"]["datasets"], json!({}));
    assert_eq!(manager.annotations(id, None).unwrap()["canAnnotate"], false);
    assert_eq!(
        manager
            .append_annotation(id, None, &json!({}), None)
            .unwrap_err()
            .code,
        "FORBIDDEN"
    );
    assert_eq!(
        manager.owner_control(id, &"b".repeat(64)).unwrap_err().code,
        "FORBIDDEN"
    );
    let mut changed = document.clone();
    changed["manifest"]["title"] = json!("Changed");
    assert_eq!(
        import(
            &publication_zip(&changed, &manifest, &[("data/sales.json.gz", b"bytes")]),
            "request"
        )
        .unwrap_err()
        .code,
        "REVISION_CONFLICT"
    );
    for name in [
        "../escape.json",
        "/absolute.json",
        "data/../escape.json",
        "data\\escape.json",
        "data//escape.json",
        "payload.exe",
    ] {
        assert_eq!(
            import(
                &publication_zip(&document, &manifest, &[(name, b"unsafe")]),
                "invalid-path"
            )
            .unwrap_err()
            .code,
            "INVALID_ARGUMENT"
        );
    }
    let mut invalid = document.clone();
    invalid["staticFiles"] = json!({"sales":["data/missing.parquet"]});
    assert_eq!(
        import(&publication_zip(&invalid, &manifest, &[]), "missing")
            .unwrap_err()
            .code,
        "INVALID_ARGUMENT"
    );
    invalid = document.clone();
    invalid["staticPages"] = json!([{"id":"other"}]);
    assert_eq!(
        import(&publication_zip(&invalid, &manifest, &[]), "multipage")
            .unwrap_err()
            .code,
        "INVALID_ARGUMENT"
    );
    invalid = document.clone();
    invalid["revision"] = json!(2);
    assert_eq!(
        import(&publication_zip(&invalid, &manifest, &[]), "wrong-version")
            .unwrap_err()
            .code,
        "REVISION_CONFLICT"
    );
    assert_eq!(
        import(b"not a zip", "invalid-zip").unwrap_err().code,
        "INVALID_ARGUMENT"
    );
    assert_eq!(
        manager
            .import_site(&zip, "bad", "request", &secret, "view", "never", None)
            .unwrap_err()
            .code,
        "INVALID_ARGUMENT"
    );
    assert_eq!(
        manager
            .import_site(&zip, &source, "request", b"short", "view", "never", None)
            .unwrap_err()
            .code,
        "INVALID_CONFIG"
    );
    manager.revoke_owner(id, &source).unwrap();
    assert_eq!(import(&zip, "request").unwrap_err().code, "SHARE_EXPIRED");
}
#[test]
fn publication_credentials_are_stable_and_strict() {
    assert!(checked_id("9a1b2c3d4e5f67890123456789abcdef0").is_err());
    assert!(checked_id("9a1b2c3d4e5f67890123456789abcdef").is_ok());
    assert!(!valid_key("１２３４５６７８"));
    assert_eq!(
        key_digest("12345678", "000102030405060708090a0b0c0d0e0f").unwrap(),
        "12ae3d7e7c927a3f0ffb20546d93fec4c042d88dd90105d26274152b4c00e63b"
    );
}
#[test]
fn share_feedback_retry_and_retirement_are_transactional() {
    let root = tempfile::tempdir().unwrap();
    let storage = Storage::private(root.path().to_owned(), "test-timer").unwrap();
    let annotations = ShareAnnotations::for_storage(&storage).unwrap();
    let id = "0123456789abcdef0123456789abcdef";
    let definition = json!({"shareId":id,"owner":"owner","pages":[{"id":"board","revision":3}],"expiresAt":null,"stagingUntil":now()+60,"annotationMode":"annotate","sourceDigest":"source"});
    annotations.call("configure", &definition).unwrap();
    let conflicting = merge(&definition, &json!({"sourceDigest":"other"}));
    assert_eq!(
        annotations
            .call("configure", &conflicting)
            .unwrap_err()
            .code,
        "REVISION_CONFLICT"
    );
    annotations
        .call("activate", &json!({"shareId":id}))
        .unwrap();
    let note = json!({"shareId":id,"dashboardId":"board","annotation":{"id":"note","text":"hello","context":{"designRevision":3}},"fingerprint":"same"});
    let first = annotations.call("append", &note).unwrap();
    assert_eq!(annotations.call("append", &note).unwrap(), first);
    assert_eq!(
        annotations
            .call("append", &merge(&note, &json!({"fingerprint":"different"})))
            .unwrap_err()
            .code,
        "ANNOTATION_CONFLICT"
    );
    assert_eq!(
        annotations
            .call("read", &note)
            .unwrap()
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(
        annotations
            .call("cleanup_claim", &json!({"shareId":id,"now":now()+1000}))
            .unwrap()["claimed"],
        false
    );
    annotations.call("revoke", &json!({"shareId":id})).unwrap();
    assert_eq!(
        annotations
            .call("cleanup_claim", &json!({"shareId":id,"now":now()}))
            .unwrap()["claimed"],
        true
    );
    assert_eq!(
        annotations.call("configure", &definition).unwrap_err().code,
        "SHARE_EXPIRED"
    );
}
#[test]
fn stale_intent_preserves_active_publication_and_sweeps_late_objects() {
    let root = tempfile::tempdir().unwrap();
    let storage = Storage::private(root.path().to_owned(), "test-timer").unwrap();
    let id = "abcdef0123456789abcdef0123456789";
    let annotations = ShareAnnotations::for_storage(&storage).unwrap();
    annotations.call("configure",&json!({"shareId":id,"owner":"owner","pages":[{"id":"board","revision":1}],"expiresAt":null,"stagingUntil":now()+100,"annotationMode":"view"})).unwrap();
    annotations
        .call("activate", &json!({"shareId":id}))
        .unwrap();
    put_json(
        &storage,
        &format!("publication-intents/{id}.json"),
        &json!({"shareId":id,"cleanupAfter":0}),
    )
    .unwrap();
    storage
        .put(
            &format!("shares/{id}/site/document.json"),
            b"{}",
            "application/json",
        )
        .unwrap();
    assert_eq!(cleanup_due(&storage, Some(now())).unwrap()["removed"], 0);
    assert!(storage
        .get(&format!("shares/{id}/site/document.json"))
        .unwrap()
        .is_some());
    assert!(storage
        .get(&format!("publication-intents/{id}.json"))
        .unwrap()
        .is_none());
    retire_id(&storage, id).unwrap();
    assert_eq!(cleanup_due(&storage, Some(now())).unwrap()["removed"], 1);
    storage
        .put(
            &format!("shares/{id}/site/late.json"),
            b"{}",
            "application/json",
        )
        .unwrap();
    assert_eq!(cleanup_due(&storage, Some(now())).unwrap()["removed"], 1);
    assert!(storage.get(&format!("retired/{id}")).unwrap().is_some());
}
#[test]
fn parallel_publication_feedback_stays_pinned_and_revocation_blocks_new_notes() {
    let root = tempfile::tempdir().unwrap();
    let storage = Storage::private(root.path().to_owned(), "test-timer").unwrap();
    let annotations = Arc::new(ShareAnnotations::for_storage(&storage).unwrap());
    let share = "feedbac00123456789abcdef01234567";
    annotations.call("configure", &json!({"shareId":share,"owner":"owner","pages":[{"id":"board","revision":7}],"expiresAt":null,"stagingUntil":now()+60,"annotationMode":"annotate","sourceDigest":"stable"})).unwrap();
    annotations
        .call("activate", &json!({"shareId":share}))
        .unwrap();
    let ready = Arc::new(Barrier::new(3));
    let writers = ["first", "second"].map(|id| {
        let annotations = Arc::clone(&annotations);
        let ready = Arc::clone(&ready);
        std::thread::spawn(move || {
            let payload = json!({"shareId":share,"dashboardId":"board","annotation":{"id":id,"text":id,"context":{"designRevision":7}},"fingerprint":id});
            ready.wait();
            let first = annotations.call("append", &payload).unwrap();
            assert_eq!(annotations.call("append", &payload).unwrap(), first);
        })
    });
    ready.wait();
    for writer in writers {
        writer.join().unwrap();
    }
    let payload = json!({"shareId":share,"dashboardId":"board"});
    let notes = annotations.call("read", &payload).unwrap();
    assert_eq!(notes.as_array().unwrap().len(), 2);
    let wrong_version = merge(
        &payload,
        &json!({"annotation":{"id":"third","context":{"designRevision":8}},"fingerprint":"third"}),
    );
    assert_eq!(
        annotations.call("append", &wrong_version).unwrap_err().code,
        "REVISION_CONFLICT"
    );
    assert_eq!(
        annotations
            .call("read", &merge(&payload, &json!({"dashboardId":"other"})))
            .unwrap_err()
            .code,
        "FORBIDDEN"
    );
    annotations.call("revoke", &payload).unwrap();
    assert_eq!(
        annotations.call("append", &wrong_version).unwrap_err().code,
        "SHARE_EXPIRED"
    );
}
#[cfg(unix)]
#[test]
fn failed_cleanup_keeps_its_job_and_never_deletes_outside_private_storage() {
    let root = tempfile::tempdir().unwrap();
    let outside = tempfile::tempdir().unwrap();
    let storage = Storage::private(root.path().to_owned(), "test-timer").unwrap();
    let share = "bad0cafe0123456789abcdef01234567";
    let prefix = format!("shares/{share}/");
    let job_key = format!("jobs/{share}.json");
    fs::create_dir_all(root.path().join("shares")).unwrap();
    fs::write(outside.path().join("keep.txt"), b"private author data").unwrap();
    let link = root.path().join("shares").join(share);
    std::os::unix::fs::symlink(outside.path(), &link).unwrap();
    put_json(
        &storage,
        &job_key,
        &json!({"shareId":share,"cleanupAfter":0,"state":"revoked"}),
    )
    .unwrap();
    let failed = cleanup_due(&storage, Some(now())).unwrap();
    assert_eq!(failed["removed"], 0);
    assert_eq!(failed["failed"].as_array().unwrap().len(), 1);
    assert!(storage.get(&job_key).unwrap().is_some());
    assert!(storage.get(&format!("retired/{share}")).unwrap().is_some());
    assert_eq!(
        fs::read(outside.path().join("keep.txt")).unwrap(),
        b"private author data"
    );
    fs::remove_file(&link).unwrap();
    storage
        .put(&format!("{prefix}late.json"), b"{}", "application/json")
        .unwrap();
    let retried = cleanup_due(&storage, Some(now())).unwrap();
    assert_eq!(retried, json!({"removed":1,"failed":[]}));
    assert!(storage.get(&job_key).unwrap().is_none());
    assert!(storage.list(&prefix).unwrap().is_empty());
    assert!(storage.get(&format!("retired/{share}")).unwrap().is_some());
    assert!(outside.path().join("keep.txt").is_file());
}
