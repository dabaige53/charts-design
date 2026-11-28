use super::*;

// @wu-test type=integration | scope=partitioned Parquet export cache | protects=partition and option metadata remain complete and a corrupt cached shard is rebuilt before delivery
#[test]
fn partitioned_packages_validate_metadata_and_repair_corrupt_cached_bytes() {
    let directory = tempfile::tempdir().unwrap();
    let data = LocalData::new(Some(&directory.path().join("data"))).unwrap();
    let fields = json!({"region":{"type":"string"},"amount":{"type":"number"}});
    let reference = data
        .import_rows(
            &[
                json!({"region":"East","amount":10}),
                json!({"region":"West","amount":20}),
                json!({"amount":30}),
            ],
            &fields,
        )
        .unwrap();
    let cache = directory.path().join("cache");
    let target = directory.path().join("first");
    let first = copy_parquet_package(
        &target,
        &data,
        &reference,
        &cache,
        Some("region"),
        true,
        false,
    )
    .unwrap();
    assert_eq!(first["cacheHit"], false);
    assert_eq!(
        first["partitionIndex"]["entries"].as_array().unwrap().len(),
        3
    );
    assert_eq!(first["options"].as_object().unwrap().len(), 2);
    let copied = copy_parquet_package(
        &directory.path().join("second"),
        &data,
        &reference,
        &cache,
        Some("region"),
        true,
        false,
    )
    .unwrap();
    assert_eq!(copied["cacheHit"], true);
    let cached = fs::read_dir(cache.join("parquet-v1"))
        .unwrap()
        .map(|e| e.unwrap().path())
        .find(|p| p.is_dir())
        .unwrap();
    let name = first["files"][0]["path"].as_str().unwrap();
    let mut bytes = fs::read(cached.join(name)).unwrap();
    bytes[0] ^= 0xff;
    fs::write(cached.join(name), bytes).unwrap();
    let repaired = copy_parquet_package(
        &directory.path().join("repaired"),
        &data,
        &reference,
        &cache,
        Some("region"),
        true,
        false,
    )
    .unwrap();
    assert_eq!(repaired["cacheHit"], false);
    assert_eq!(
        digest(&directory.path().join("repaired").join(name)).unwrap(),
        first["files"][0]["sha256"]
    );
    assert_eq!(
        inspect_parquet(&target.join(name)).unwrap()["format"],
        "parquet-v1"
    );
    assert_eq!(
        copy_parquet_package(
            &target,
            &data,
            &reference,
            &cache,
            Some("amount"),
            false,
            false
        )
        .unwrap_err()
        .code,
        "INVALID_ARGUMENT"
    );
    let mut changed = reference.clone();
    changed["rowCount"] = json!(4);
    assert_eq!(
        copy_parquet_package(
            &target,
            &data,
            &changed,
            &directory.path().join("new-cache"),
            None,
            false,
            false
        )
        .unwrap_err()
        .code,
        "DATA_CONFLICT"
    );
    let receipt: Value =
        serde_json::from_slice(&fs::read(cached.join("receipt.json")).unwrap()).unwrap();
    for pointer in [
        "/format",
        "/version",
        "/rowCount",
        "/fieldOrder",
        "/files/0/path",
        "/files/0/rowCount",
        "/files/0/bytes",
        "/files/0/sha256",
        "/missingColumn",
        "/ordinalColumn",
        "/partitionIndex/field",
        "/partitionIndex/entries",
    ] {
        let mut invalid = receipt.clone();
        *invalid.pointer_mut(pointer).unwrap() = Value::Null;
        fs::write(
            cached.join("receipt.json"),
            serde_json::to_vec(&invalid).unwrap(),
        )
        .unwrap();
        assert!(
            valid_receipt(&cached, &reference, Some("region"), true, false).is_none(),
            "accepted {pointer}"
        );
    }
    fs::write(
        cached.join("receipt.json"),
        serde_json::to_vec(&receipt).unwrap(),
    )
    .unwrap();
    assert!(valid_receipt(&cached, &reference, Some("region"), false, false).is_none());
    assert!(valid_receipt(&cached, &reference, None, true, false).is_none());
    assert!(valid_receipt(&cached, &reference, Some("region"), true, true).is_none());
}

// @wu-test type=integration | scope=JSON static data shards | protects=legacy JSON export does not drop rows at the 5000-row boundary or turn missing values into null
#[test]
fn json_shards_round_trip_full_rows_and_keep_their_size_boundary() {
    let directory = tempfile::tempdir().unwrap();
    fs::create_dir(directory.path().join("data")).unwrap();
    let data = LocalData::new(Some(&directory.path().join("database"))).unwrap();
    let rows = (0..5001)
        .map(|n| {
            if n == 5000 {
                json!({"position":n})
            } else {
                json!({"position":n,"optional":null})
            }
        })
        .collect::<Vec<_>>();
    let (files, count) = write_json_shards(directory.path(), "sales", &data, None, &rows).unwrap();
    assert_eq!(files.len(), 2);
    assert_eq!(count, 5001);
    let mut decoded = vec![];
    for path in &files {
        let mut decoder =
            flate2::read::GzDecoder::new(File::open(directory.path().join(path)).unwrap());
        let mut raw = vec![];
        decoder.read_to_end(&mut raw).unwrap();
        decoded.extend(serde_json::from_slice::<Vec<Value>>(&raw).unwrap());
    }
    assert_eq!(decoded, rows);
    assert!(decoded[5000].get("optional").is_none());
    assert_eq!(
        write_json_shards(directory.path(), "empty", &data, None, &[]).unwrap(),
        (vec![], 0)
    );
    let reference = data
        .import_rows(
            &[json!({"amount":1}), json!({"amount":null}), json!({})],
            &json!({"amount":{"type":"number"}}),
        )
        .unwrap();
    assert_eq!(
        write_json_shards(directory.path(), "stored", &data, Some(&reference), &[])
            .unwrap()
            .1,
        3
    );
    let huge = json!({"text":"x".repeat(16*1024*1024)});
    assert_eq!(
        write_json_shards(directory.path(), "oversized", &data, None, &[huge])
            .unwrap_err()
            .code,
        "PAYLOAD_TOO_LARGE"
    );
    assert!(!directory.path().join("data/oversized-0.json.gz").exists());
}

// @wu-test type=integration | scope=complete JSON static site | protects=exports include complete selected data while stripping author-only fields and reuse one immutable UI archive
#[test]
fn json_static_site_is_self_contained_and_removes_author_capabilities() {
    let directory = tempfile::tempdir().unwrap();
    let service = super::super::service::Service::new(
        &directory.path().join("runtime"),
        None,
        Some(&directory.path().join("project")),
    )
    .unwrap();
    let saved=service.call("dashboard_submit",&json!({"dashboardId":"sales","createTitle":"Sales","operations":[
        {"op":"put_source","id":"fixture","value":{"kind":"fixture","name":"Sales"}},
        {"op":"put_dataset","id":"sales","meta":{"sourceId":"fixture","fields":{"region":{"type":"string"},"amount":{"type":"number"}}},"rows":[{"region":"East","amount":10},{"region":"West","amount":20}]},
        {"op":"put_component","id":"table","value":{"kind":"table","title":"Sales","datasetId":"sales"}},
        {"op":"set_filters","value":[{"id":"region","field":"region","op":"in","values":["East"],"componentIds":["table"]}]}
    ]})).unwrap();
    assert_eq!(saved["ok"], true);
    let mut document = service.store.get("sales", false).unwrap();
    document["browserLinks"] = json!({"editUrl":"secret"});
    document["annotationAccess"] = json!({"token":"secret"});
    document["publicationApiBase"] = json!("secret");
    let result = export_site(
        &service.store,
        "sales",
        None,
        Some(&document),
        "json",
        false,
    )
    .unwrap();
    let site = PathBuf::from(result["export"]["directory"].as_str().unwrap());
    let exported: Value =
        serde_json::from_slice(&fs::read(site.join("document.json")).unwrap()).unwrap();
    assert!(exported.get("browserLinks").is_none());
    assert!(exported.get("annotationAccess").is_none());
    assert!(exported.get("publicationApiBase").is_none());
    assert!(exported["manifest"].get("sources").is_none());
    assert_eq!(result["export"]["manifest"]["datasets"]["sales"], 2);
    assert_eq!(result["export"]["manifest"]["dataFormat"], "json");
    assert_eq!(
        exported["staticFilterOptions"]["region"],
        json!(["East", "West"])
    );
    let mut zip =
        zip::ZipArchive::new(File::open(result["export"]["path"].as_str().unwrap()).unwrap())
            .unwrap();
    for name in [
        "index.html",
        "document.json",
        "app.js",
        "app.css",
        "static-worker.js",
        "export-manifest.json",
    ] {
        assert!(zip.by_name(name).is_ok(), "{name}");
    }
    let next = export_site(&service.store, "sales", None, None, "json", false).unwrap();
    assert_ne!(next["export"]["id"], result["export"]["id"]);
    assert_eq!(next["export"]["manifest"]["revision"], saved["revision"]);
    assert_eq!(
        export_site(&service.store, "sales", None, None, "invalid", false)
            .unwrap_err()
            .code,
        "INVALID_ARGUMENT"
    );
}
