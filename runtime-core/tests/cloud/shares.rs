//! Publication and reviewed physical deletion against a disposable PostgreSQL database.
use charts_design_core::runtime::{
    cloud::CloudDatabase,
    object_storage::Storage,
    operations,
    service::Service,
    share_annotations::ShareAnnotations,
    shares::{self, CloudShares},
    versions::Versions,
};
use serde_json::{json, Value};
use std::fs;

use super::database::{Database, ENVIRONMENT};

fn create_page(service: &Service, id: &str) -> i64 {
    let saved=service.call("dashboard_submit", &json!({"dashboardId":id,"createTitle":"Sales","operations":[
        {"op":"put_source","id":"fixture","value":{"kind":"fixture","name":"Sales"}},
        {"op":"put_dataset","id":"sales","meta":{"sourceId":"fixture","fields":{"region":{"type":"string"},"amount":{"type":"number"}}},"rows":[{"region":"East","amount":10},{"region":"West","amount":20}]},
        {"op":"put_component","id":"table","value":{"kind":"table","title":"Sales","datasetId":"sales"}}
    ]})).unwrap();
    assert_eq!(saved["ok"], true);
    let revision = saved["revision"].as_i64().unwrap();
    Versions::new(&service.store)
        .unwrap()
        .publish(id, revision, revision)
        .unwrap();
    revision
}

// @wu-test type=integration | scope=cloud fixed-version sharing and physical deletion | protects=published data leaks across versions or survives an approved deletion while retained data must stay readable
#[test]
fn cloud_publications_authorize_only_referenced_files_and_delete_reviewed_versions() {
    let _environment = ENVIRONMENT.lock().unwrap_or_else(|e| e.into_inner());
    let fixture = Database::new();
    fixture.legacy_project("share-project");
    let service = fixture.service("share-project", "author-cache");
    assert!(!service.store.cos_enabled);
    let revision = create_page(&service, "sales");
    let other_revision = create_page(&service, "regions");
    let migration = operations::migrate_cos(
        "share-project",
        &fixture.path("workspaces"),
        true,
        &["region".into()],
    )
    .unwrap();
    assert_eq!(migration["action"], "migrated");
    let service = fixture.service("share-project", "asset-cache");
    assert!(service.store.cos_enabled);
    let storage = Storage::publication().unwrap();
    storage
        .put(
            "cleaner-status.json",
            &serde_json::to_vec(&json!({"completedAt":shares::now()})).unwrap(),
            "application/json",
        )
        .unwrap();
    let manager = CloudShares::new(storage, "https://charts.test").unwrap();
    let pages = [json!({"dashboardId":"regions","expectedRevision":other_revision})];
    let receipt = manager
        .publish(
            &service,
            "sales",
            revision,
            "7d",
            Some("12345678"),
            Some(&pages),
            None,
            "annotate",
        )
        .unwrap();
    let id = receipt["shareId"].as_str().unwrap();
    let control = manager.authenticate(id, "12345678").unwrap();
    assert_eq!(control["registered"], true);
    assert_eq!(control["project"], "share-project");
    assert_eq!(receipt["pages"].as_array().unwrap().len(), 2);
    let document = Versions::new(&service.store)
        .unwrap()
        .read("sales", revision)
        .unwrap();
    let reference = &document["snapshot"]["datasetRefs"]["sales"];
    let registry = service.store.cloud_assets().unwrap();
    let object = registry
        .call("object_get", &json!({"version":reference["version"]}))
        .unwrap();
    let object_id = object["id"].as_str().unwrap();
    let shard = object["descriptor"]["shards"][0].as_str().unwrap();
    let expected = registry.read_file(&object, shard).unwrap();
    assert_eq!(
        shares::authorized_file(&service.store, &document, object_id, shard).unwrap(),
        expected
    );
    assert_eq!(
        shares::authorized_file(&service.store, &document, object_id, "query.sqlite3")
            .unwrap_err()
            .code,
        "FORBIDDEN"
    );
    assert_eq!(
        shares::authorized_file(&service.store, &document, "missing", shard)
            .unwrap_err()
            .code,
        "FORBIDDEN"
    );
    let mut unrelated = document.clone();
    unrelated["manifest"]["components"] = json!({});
    assert_eq!(
        shares::authorized_file(&service.store, &unrelated, object_id, shard)
            .unwrap_err()
            .code,
        "FORBIDDEN"
    );
    let webpage = shares::web_document(
        &service.store,
        &document,
        |object, name| format!("/data/{object}/{name}"),
        false,
        false,
    )
    .unwrap();
    assert_eq!(webpage["staticFiles"]["sales"].as_array().unwrap().len(), 2);
    assert!(webpage["manifest"].get("sources").is_none());
    for entry in object["descriptor"]["options"]
        .as_object()
        .unwrap()
        .values()
    {
        for name in entry["files"].as_array().unwrap() {
            let name = name.as_str().unwrap();
            assert_eq!(
                shares::authorized_file(&service.store, &document, object_id, name).unwrap(),
                registry.read_file(&object, name).unwrap()
            );
        }
    }
    let frozen: Value =
        serde_json::from_slice(&manager.content(id, "document.json", None).unwrap()).unwrap();
    let data_path = frozen["staticFiles"]["sales"][0].as_str().unwrap();
    assert!(!manager.content(id, data_path, None).unwrap().is_empty());
    assert_eq!(frozen["staticPages"].as_array().unwrap().len(), 2);
    let next=service.call("dashboard_submit",&json!({"dashboardId":"sales","expectedRevision":revision,"operations":[{"op":"set_title","value":"New draft"}]})).unwrap()["revision"].as_i64().unwrap();
    assert_eq!(
        serde_json::from_slice::<Value>(&manager.content(id, "document.json", None).unwrap())
            .unwrap(),
        frozen
    );
    assert_eq!(
        shares::version_delete_checkpoint(&service.store, "sales", next, revision, "")
            .unwrap_err()
            .code,
        "CONFIRMATION_REQUIRED"
    );
    let preview = shares::version_delete_preview(&service.store, "sales", next, revision).unwrap();
    assert!(preview["shares"]
        .as_array()
        .unwrap()
        .iter()
        .any(|s| s["shareId"] == id));
    assert!(preview["shares"]
        .as_array()
        .unwrap()
        .iter()
        .all(|s| s["url"]
            .as_str()
            .unwrap()
            .starts_with("https://charts.test/s/")));
    let token = preview["token"].as_str().unwrap();
    let deleted =
        shares::version_delete_checkpoint(&service.store, "sales", next, revision, token).unwrap();
    assert_eq!(deleted["state"], "complete");
    assert_eq!(manager.control(id).unwrap_err().code, "SHARE_EXPIRED");
    assert_eq!(
        shares::delete_version_job(registry, &deleted).unwrap(),
        deleted
    );
    let job_id = deleted["id"].as_str().unwrap();
    assert_eq!(
        shares::version_delete_status(&service.store, "sales", job_id, false).unwrap()["state"],
        "complete"
    );
    assert_eq!(
        shares::version_delete_status(&service.store, "sales", job_id, true).unwrap()["state"],
        "complete"
    );
    assert_eq!(
        Versions::new(&service.store)
            .unwrap()
            .read("sales", revision)
            .unwrap_err()
            .code,
        "NOT_FOUND"
    );
    assert_eq!(
        Versions::new(&service.store)
            .unwrap()
            .read("sales", next)
            .unwrap()["manifest"]["title"],
        "New draft"
    );
    assert_eq!(service.store.data.all_rows(reference).unwrap().len(), 2);
    assert!(manager
        .storage
        .list(&format!("shares/{id}/"))
        .unwrap()
        .is_empty());
    assert!(!shares::cleanup_asset_jobs().unwrap()["failed"]
        .as_array()
        .unwrap()
        .iter()
        .any(|e| e["job"] == job_id));
    assert!(fs::metadata(fixture.path("private-assets")).is_ok());
}

// @wu-test type=integration | scope=durable remote publication feedback | protects=the remote annotation backend loses idempotent writes, changes pinned versions or accepts writes after revocation
#[test]
fn remote_annotations_keep_idempotency_version_and_retirement_guards() {
    let _environment = ENVIRONMENT.lock().unwrap_or_else(|e| e.into_inner());
    let _fixture = Database::new();
    let database = CloudDatabase::new()
        .unwrap()
        .with_function("charts_share_annotations")
        .unwrap();
    let annotations = ShareAnnotations::Remote(database);
    assert_eq!(annotations.kind(), "postgres-v1");
    let id = "1234567890abcdef1234567890abcdef";
    let definition = json!({"shareId":id,"owner":"owner","pages":[{"id":"sales","revision":3}],"expiresAt":null,"stagingUntil":shares::now()+3600,"annotationMode":"annotate","sourceDigest":"stable"});
    assert_eq!(
        annotations.call("ready", &json!({"shareId":id})).unwrap()["ready"],
        true
    );
    annotations.call("configure", &definition).unwrap();
    annotations
        .call("activate", &json!({"shareId":id}))
        .unwrap();
    let note = json!({"shareId":id,"dashboardId":"sales","annotation":{"id":"first","text":"Review","context":{"designRevision":3}},"fingerprint":"same"});
    let first = annotations.call("append", &note).unwrap();
    assert_eq!(annotations.call("append", &note).unwrap(), first);
    assert_eq!(annotations.call("read", &note).unwrap(), json!([first]));
    let mut changed = note.clone();
    changed["fingerprint"] = json!("other");
    assert_eq!(
        annotations.call("append", &changed).unwrap_err().code,
        "ANNOTATION_CONFLICT"
    );
    changed["annotation"]["id"] = json!("second");
    changed["annotation"]["context"]["designRevision"] = json!(4);
    assert_eq!(
        annotations.call("append", &changed).unwrap_err().code,
        "REVISION_CONFLICT"
    );
    assert_eq!(
        annotations
            .call("cleanup_claim", &json!({"shareId":id,"now":shares::now()}))
            .unwrap()["claimed"],
        false
    );
    annotations.call("revoke", &json!({"shareId":id})).unwrap();
    assert_eq!(
        annotations.call("read", &note).unwrap_err().code,
        "SHARE_EXPIRED"
    );
    assert_eq!(
        annotations
            .call("cleanup_claim", &json!({"shareId":id,"now":shares::now()}))
            .unwrap()["claimed"],
        true
    );
    assert_eq!(
        annotations.call("configure", &definition).unwrap_err().code,
        "SHARE_EXPIRED"
    );
}
