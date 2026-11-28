use charts_design_core::runtime::{
    doctor, model,
    service::Service,
    store::{self, Store},
};
use serde_json::{json, Value};
use std::{fs, path::Path};
use tempfile::TempDir;

fn service(root: &Path, project: bool, sources: Option<&Path>) -> Service {
    Service::new(
        &root.join("cache"),
        sources,
        project.then(|| root.join("project")).as_deref(),
    )
    .unwrap()
}

fn sales_operations() -> Vec<Value> {
    vec![
        json!({"op":"put_source","id":"source","value":{"kind":"file","name":"Reviewed fixture"}}),
        json!({"op":"put_dataset","id":"sales","meta":{"sourceId":"source","fields":{
            "region":{"type":"string"},"month":{"type":"date"},"amount":{"type":"number"},"baseline":{"type":"number"}
        }},"rows":[
            {"region":"East","month":"2026-01-01","amount":12,"baseline":10},
            {"region":"West","month":"2026-01-01","amount":20,"baseline":16},
            {"region":"East","month":"2026-02-01","amount":18,"baseline":15}
        ]}),
        json!({"op":"put_metric","id":"revenue","value":{"datasetId":"sales","field":"amount","aggregation":"sum","label":"Revenue","unit":"USD","definition":"Net booked revenue","status":"reviewed"}}),
        json!({"op":"put_metric","id":"prior","value":{"datasetId":"sales","field":"baseline","aggregation":"sum","label":"Prior revenue","unit":"USD","definition":"Comparable prior revenue","status":"reviewed"}}),
        json!({"op":"put_component","id":"total","value":{"kind":"kpi","title":"Revenue","datasetId":"sales","measures":["revenue"]}}),
        json!({"op":"put_component","id":"detail","value":{"kind":"table","title":"Rows","datasetId":"sales"}}),
        json!({"op":"set_filters","value":[{"id":"region","field":"region","op":"in","values":[],"componentIds":["total","detail"]}]}),
    ]
}

fn saved(service: &Service) -> i64 {
    let result = service
        .call(
            "dashboard_submit",
            &json!({"dashboardId":"board","createTitle":"Sales","operations":sales_operations()}),
        )
        .unwrap();
    assert_eq!(result["ok"], true, "{result}");
    result["revision"].as_i64().unwrap()
}

fn error(service: &Service, tool: &str, args: Value, code: &str) {
    let failure = service.call(tool, &args).unwrap_err();
    assert_eq!(failure.code, code, "{tool}: {failure:?}");
    assert!(
        failure.request_id.is_some(),
        "diagnostics must retain the failed request"
    );
}

// @wu-test type=integration | scope=saved version lifecycle | protects=edit batches, historical queries and reviewed deletion cannot alter a draft or publication silently
#[test]
fn saved_versions_batches_and_reviewed_deletion_preserve_separate_heads() {
    let root = TempDir::new().unwrap();
    let service = service(root.path(), true, None);
    let first = saved(&service);
    let batch = service
        .call(
            "dashboard_edit_begin",
            &json!({"dashboardId":"board","expectedRevision":first}),
        )
        .unwrap();
    assert_eq!(
        service
            .call(
                "dashboard_edit_begin",
                &json!({"dashboardId":"board","expectedRevision":first})
            )
            .unwrap(),
        batch
    );
    let edited = service.call("dashboard_patch", &json!({"dashboardId":"board","expectedRevision":first,"operations":[{"op":"set_title","value":"Revised sales"}]})).unwrap();
    let second = edited["document"]["revision"].as_i64().unwrap();
    assert_eq!(second, first + 1);
    assert_eq!(
        service.store.readable("board").unwrap()["manifest"]["title"],
        "Sales"
    );
    error(
        &service,
        "dashboard_edit_finish",
        json!({"dashboardId":"board","expectedRevision":second,"batchId":"wrong"}),
        "INVALID_DOCUMENT",
    );
    let finished = service.call("dashboard_edit_finish", &json!({"dashboardId":"board","expectedRevision":second,"batchId":batch["batch_id"],"name":"Reviewed"})).unwrap();
    assert_eq!(finished["ok"], true);
    assert_eq!(finished["checkpoint"]["revision"], second);
    assert_eq!(finished["nextAction"], "dashboard_preview");
    let diff = service
        .call(
            "dashboard_history_diff",
            &json!({"dashboardId":"board","fromRevision":first,"toRevision":second}),
        )
        .unwrap();
    assert!(diff["diff"].as_str().unwrap().contains("Revised sales"));
    let history = service
        .call(
            "dashboard_history",
            &json!({"dashboardId":"board","offset":0,"limit":2}),
        )
        .unwrap();
    assert_eq!(history["history"][0]["revision"], second);
    assert_eq!(history["history"][0]["name"], "Reviewed");
    assert_eq!(history["history"].as_array().unwrap().len(), 2);
    let labeled = service.call("dashboard_version_label", &json!({"dashboardId":"board","expectedRevision":second,"revision":first,"name":"Baseline","published":true})).unwrap();
    assert_eq!(labeled["name"], "Baseline");
    let published = service
        .call(
            "dashboard_publish",
            &json!({"dashboardId":"board","expectedRevision":second,"revision":first}),
        )
        .unwrap();
    assert_eq!(published["publishedRevision"], first);
    let historical = service.call("dashboard_version_query", &json!({"dashboardId":"board","revision":first,"operation":"details","request":{"componentId":"detail","sort":[{"field":"amount","direction":"desc"}],"limit":1}})).unwrap();
    assert_eq!(historical["rows"][0]["amount"], 20);
    assert_eq!(historical["totalRows"], 3);
    let historical_view = service.call("dashboard_version_query", &json!({"dashboardId":"board","revision":first,"operation":"view","request":{"responseMode":"patch","componentIds":["total"],"includeEvidence":true}})).unwrap();
    assert_eq!(historical_view["revision"], first);
    assert_eq!(
        historical_view["evidence"]["total"]["metrics"]["revenue"]["unit"],
        "USD"
    );
    let options = service.call("dashboard_version_query", &json!({"dashboardId":"board","revision":first,"operation":"options","request":{"filterId":"region"}})).unwrap();
    assert_eq!(options["values"], json!(["East", "West"]));
    let semantics = service.call("dashboard_version_query", &json!({"dashboardId":"board","revision":first,"operation":"semantic","request":{"componentId":"total"}})).unwrap();
    assert_eq!(semantics["certified"], false);
    assert_eq!(
        semantics["metrics"]["revenue"]["definition"],
        "Net booked revenue"
    );
    let csv = service.call("dashboard_version_query", &json!({"dashboardId":"board","revision":first,"operation":"export","request":{"datasetId":"sales"}})).unwrap();
    assert_eq!(csv["export"]["rowCount"], 3);
    error(
        &service,
        "dashboard_version_query",
        json!({"dashboardId":"board","revision":first,"operation":"delete"}),
        "INVALID_ARGUMENT",
    );
    error(
        &service,
        "dashboard_version_query",
        json!({"dashboardId":"board","revision":first,"operation":"view","request":[]}),
        "INVALID_ARGUMENT",
    );
    let restored = service.call("dashboard_restore", &json!({"dashboardId":"board","expectedRevision":second,"revision":first,"useCurrentData":true})).unwrap();
    let third = restored["document"]["revision"].as_i64().unwrap();
    assert_eq!(restored["document"]["manifest"]["title"], "Sales");
    let before = service
        .call("dashboard_version_status", &json!({"dashboardId":"board"}))
        .unwrap();
    assert_eq!(before["draftRevision"], third);
    assert_eq!(before["savedRevision"], second);
    assert_eq!(before["publishedRevision"], first);
    error(
        &service,
        "dashboard_version_delete",
        json!({"dashboardId":"board","expectedRevision":third,"revision":first}),
        "CONFIRMATION_REQUIRED",
    );
    let plan = service
        .call(
            "dashboard_version_delete_preview",
            &json!({"dashboardId":"board","expectedRevision":third,"revision":first}),
        )
        .unwrap();
    assert_eq!(plan["clearsPublication"], true);
    service.call("dashboard_annotations_update", &json!({"dashboardId":"board","append":{"id":"note","text":"Review changed","createdAt":"2026-11-28"}})).unwrap();
    error(
        &service,
        "dashboard_version_delete",
        json!({"dashboardId":"board","expectedRevision":third,"revision":first,"confirmation":plan["token"]}),
        "PLAN_CHANGED",
    );
    let plan = service
        .call(
            "dashboard_version_delete_preview",
            &json!({"dashboardId":"board","expectedRevision":third,"revision":first}),
        )
        .unwrap();
    let deleted = service.call("dashboard_version_delete", &json!({"dashboardId":"board","expectedRevision":third,"revision":first,"confirmation":plan["token"]})).unwrap();
    assert_eq!(deleted["deleted"], true);
    assert_eq!(service.store.revision("board").unwrap(), third);
    let state = service
        .call("dashboard_version_status", &json!({"dashboardId":"board"}))
        .unwrap();
    assert!(state["publishedRevision"].is_null());
    error(
        &service,
        "dashboard_version_get",
        json!({"dashboardId":"board","revision":first}),
        "NOT_FOUND",
    );
    error(
        &service,
        "dashboard_version_delete_status",
        json!({"dashboardId":"board","jobId":"local"}),
        "UNSUPPORTED_OPERATION",
    );
    assert_eq!(
        service
            .call(
                "dashboard_annotations",
                &json!({"dashboardId":"board","includeTargets":false})
            )
            .unwrap()["count"],
        1
    );
}

// @wu-test type=integration | scope=annotation target resolution | protects=comments retain original anchors and remain independently saved when components are removed
#[test]
fn annotation_targets_and_conflicts_are_explicit_after_structure_changes() {
    let root = TempDir::new().unwrap();
    let service = service(root.path(), true, None);
    let revision = saved(&service);
    let anchor = json!({"scope":"component","kind":"area","quote":"Revenue","rect":{"x":0.1,"y":0.2,"width":0.3,"height":0.4}});
    let note = json!({"id":"note","componentId":"total","text":"Check source","createdAt":"2026-11-28","anchor":anchor});
    service
        .call(
            "dashboard_annotations_update",
            &json!({"dashboardId":"board","append":note}),
        )
        .unwrap();
    let notes = service
        .call("dashboard_annotations", &json!({"dashboardId":"board"}))
        .unwrap();
    assert_eq!(notes["targets"]["note"]["componentExists"], true);
    assert_eq!(notes["targets"]["note"]["title"], "Revenue");
    assert_eq!(
        notes["annotations"][0]["context"]["designRevision"],
        revision
    );
    error(
        &service,
        "dashboard_annotations_update",
        json!({"dashboardId":"board","append":note,"expectedRevision":revision}),
        "INVALID_ARGUMENT",
    );
    error(
        &service,
        "dashboard_annotations_update",
        json!({"dashboardId":"board","expectedRevision":revision,"expectedAnnotations":{},"annotations":[]}),
        "INVALID_ARGUMENT",
    );
    error(
        &service,
        "dashboard_annotations",
        json!({"dashboardId":"board","includeTargets":"yes"}),
        "INVALID_ARGUMENT",
    );
    service.call("dashboard_patch", &json!({"dashboardId":"board","expectedRevision":revision,"operations":[{"op":"remove_component","id":"total"}]})).unwrap();
    let result = service
        .call("dashboard_annotations", &json!({"dashboardId":"board"}))
        .unwrap();
    assert_eq!(result["count"], 1);
    assert_eq!(result["targets"]["note"]["componentExists"], false);
    assert_eq!(
        result["annotations"][0]["context"]["designRevision"],
        revision
    );
    error(
        &service,
        "dashboard_annotations_update",
        json!({"dashboardId":"board","expectedRevision":revision,"expectedAnnotations":notes["annotations"],"annotations":[]}),
        "REVISION_CONFLICT",
    );
}

// @wu-test type=integration | scope=imported annotation provenance | protects=creating a destination at revision one must retain the original annotation revision, data versions and filters without trusting forged context on subsequent edits
#[test]
fn importing_annotations_preserves_source_context_and_recomputes_new_notes() {
    let root = TempDir::new().unwrap();
    let source = service(&root.path().join("source"), true, None);
    let source_revision = saved(&source);
    assert!(source_revision > 1);
    let annotated = source.store.append_annotation(
        "board",
        &json!({"id":"original-note","componentId":"total","text":"Source review","createdAt":"2026-11-28"}),
        None,
    ).unwrap()["annotation"].clone();
    let context = annotated["context"].clone();
    let original = source.store.get("board", false).unwrap();
    assert_eq!(context["designRevision"], source_revision);
    assert_eq!(context["dataVersions"], original["snapshot"]["datasetRefs"]);
    assert_eq!(context["filters"], original["manifest"]["filters"]);
    source.call("dashboard_patch", &json!({"dashboardId":"board","expectedRevision":source_revision,"operations":[{"op":"set_title","value":"Newer source draft"}]})).unwrap();
    let document = source
        .store
        .hydrate(&source.store.get("board", false).unwrap())
        .unwrap();
    assert_eq!(document["revision"], source_revision + 1);

    let destination_root = root.path().join("destination");
    let destination = service(&destination_root, true, None);
    let imported = destination
        .store
        .create("board", "Imported", Some(&document))
        .unwrap();
    assert_eq!(imported["revision"], 1);
    assert_eq!(imported["manifest"]["annotations"], json!([annotated]));
    assert_eq!(imported["manifest"]["annotations"][0]["context"], context);
    assert_eq!(
        destination.store.readable("board").unwrap()["manifest"]["annotations"][0]["context"],
        context
    );
    let compact = destination.store.get("board", false).unwrap();
    assert_eq!(
        compact["snapshot"]["datasetRefs"],
        original["snapshot"]["datasetRefs"]
    );
    let new_context = json!({"designRevision":1,"dataVersions":compact["snapshot"]["datasetRefs"],"filters":compact["manifest"]["filters"]});
    let added = destination.store.append_annotation(
        "board",
        &json!({"id":"destination-note","text":"Destination review","createdAt":"2026-11-28","context":{"designRevision":999,"dataVersions":{},"filters":[]}}),
        None,
    ).unwrap();
    assert_eq!(added["annotation"]["context"], new_context);
    let previous =
        destination.store.annotation_state("board", false).unwrap()["annotations"].clone();
    let mut edited = previous.clone();
    edited[0]["text"] = json!("Reviewed again");
    edited[0]["context"] = json!({"designRevision":999});
    let updated = destination
        .store
        .update_annotations("board", 1, &previous, &edited)
        .unwrap();
    assert_eq!(updated["annotations"][0]["context"], context);
    assert_eq!(updated["annotations"][1]["context"], new_context);
    assert_eq!(destination.store.revision("board").unwrap(), 1);
    drop(destination);
    let reopened = service(&destination_root, true, None);
    assert_eq!(
        reopened.store.get("board", false).unwrap()["manifest"]["annotations"],
        updated["annotations"]
    );

    let mut without_context = model::new_document("fresh", "Imported without provenance").unwrap();
    without_context["manifest"]["annotations"] =
        json!([{"id":"note","text":"Initial review","createdAt":"2026-11-28"}]);
    let initialized = reopened
        .store
        .create("fresh", "Imported", Some(&without_context))
        .unwrap();
    assert_eq!(
        initialized["manifest"]["annotations"][0]["context"],
        json!({"designRevision":1,"dataVersions":{},"filters":[]})
    );
}

// @wu-test type=integration | scope=legacy SQLite migrations | protects=legacy edits, data references and migration rollback remain readable without project-only APIs
#[test]
fn legacy_store_migration_and_rollback_keep_rows_and_history() {
    let root = TempDir::new().unwrap();
    let service = service(root.path(), false, None);
    let doc = model::apply_operations(
        &model::new_document("board", "Legacy").unwrap(),
        &sales_operations(),
    )
    .unwrap();
    let created = service
        .call(
            "dashboard_create",
            &json!({"dashboardId":"board","document":doc}),
        )
        .unwrap();
    assert_eq!(created["document"]["revision"], 1);
    assert_eq!(
        created["document"]["manifest"]["sources"]["source"]["verification"],
        "supplied"
    );
    error(
        &service,
        "dashboard_submit",
        json!({"dashboardId":"board","expectedRevision":1}),
        "PROJECT_REQUIRED",
    );
    let migration = service
        .call(
            "dashboard_migrate",
            &json!({"dashboardId":"board","expectedRevision":1}),
        )
        .unwrap();
    let backup = migration["migration"]["backupId"].clone();
    assert_eq!(migration["migration"]["revisionsMigrated"], 1);
    assert_eq!(migration["document"]["snapshot"]["localMode"], true);
    let compact = service.store.get("board", false).unwrap();
    assert_eq!(compact["snapshot"]["datasetRefs"]["sales"]["rowCount"], 3);
    let inspect = service
        .call("dashboard_data_inspect", &json!({"dashboardId":"board"}))
        .unwrap();
    assert!(inspect["configBytes"].as_u64().unwrap() > 0);
    assert_eq!(inspect["datasets"]["sales"]["rowCount"], 3);
    error(
        &service,
        "dashboard_migration_rollback",
        json!({"dashboardId":"board","expectedRevision":1,"backupId":"../outside"}),
        "INVALID_DOCUMENT",
    );
    let rolled = service
        .call(
            "dashboard_migration_rollback",
            &json!({"dashboardId":"board","expectedRevision":1,"backupId":backup}),
        )
        .unwrap();
    assert_eq!(rolled["document"]["revision"], 2);
    let rows = service.call("component_data", &json!({"dashboardId":"board","componentId":"detail","sort":[{"field":"amount","direction":"asc"}]})).unwrap();
    assert_eq!(rows["rows"][0]["amount"], 12);
    assert_eq!(rows["totalRows"], 3);
    let history = service
        .call("dashboard_history", &json!({"dashboardId":"board"}))
        .unwrap();
    assert_eq!(history["history"][0]["action"], "migration-rollback");
    let annotations = service
        .call("dashboard_annotations", &json!({"dashboardId":"board"}))
        .unwrap();
    assert_eq!(annotations["independentSave"], false);
    assert_eq!(annotations["count"], 0);
    let list = service.call("dashboard_list", &json!({})).unwrap();
    assert_eq!(list["dashboards"].as_array().unwrap().len(), 1);
    error(
        &service,
        "dashboard_migrate",
        json!({"dashboardId":"board","expectedRevision":1}),
        "REVISION_CONFLICT",
    );
}

// @wu-test type=integration | scope=live SQL service | protects=live reads use current source data while exports and previews cannot persist transient rows
#[test]
fn live_sql_reads_remain_transient_and_snapshot_refresh_retains_types() {
    let root = TempDir::new().unwrap();
    let path = root.path().join("source.sqlite3");
    let db = rusqlite::Connection::open(&path).unwrap();
    db.execute_batch("CREATE TABLE sales(region TEXT,amount REAL); INSERT INTO sales VALUES('East',12),('West',20);").unwrap();
    let config = root.path().join("sources.json");
    fs::write(
        &config,
        json!({"sales":{"engine":"sqlite","path":path}}).to_string(),
    )
    .unwrap();
    let service = service(root.path(), true, Some(&config));
    service
        .call("dashboard_create", &json!({"dashboardId":"board"}))
        .unwrap();
    let query = json!({"dashboardId":"board","datasetId":"sales","expectedRevision":1,"connection":"sales","sql":"SELECT region, amount FROM sales","mode":"live","fields":{"region":{"type":"string"},"amount":{"type":"number"}}});
    let imported = service.call("query_execute", &query).unwrap();
    assert_eq!(
        imported["document"]["manifest"]["datasets"]["sales"]["mode"],
        "live"
    );
    assert!(imported["document"]["snapshot"]["datasetRefs"]["sales"].is_null());
    let result = service.call("dashboard_submit", &json!({"dashboardId":"board","expectedRevision":2,"operations":[{"op":"put_component","id":"detail","value":{"kind":"table","datasetId":"sales","title":"Live rows"}},{"op":"set_filters","value":[{"id":"region","field":"region","op":"in","values":[],"componentIds":["detail"]}]}]})).unwrap();
    assert_eq!(result["ok"], true, "{result}");
    let revision = result["revision"].as_i64().unwrap();
    db.execute("INSERT INTO sales VALUES('South',40)", [])
        .unwrap();
    let preview = service.call("dataset_preview", &json!({"dashboardId":"board","datasetId":"sales","expectedRevision":revision,"limit":2,"offset":1})).unwrap();
    assert_eq!(preview["totalRows"], 3);
    assert_eq!(preview["rows"].as_array().unwrap().len(), 2);
    let detail = service
        .call(
            "component_data",
            &json!({"dashboardId":"board","componentId":"detail","limit":10}),
        )
        .unwrap();
    assert_eq!(detail["transient"], true);
    assert_eq!(detail["totalRows"], 3);
    let options = service
        .call(
            "dashboard_filter_options",
            &json!({"dashboardId":"board","filterId":"region","search":"south"}),
        )
        .unwrap();
    assert_eq!(options["transient"], true);
    assert_eq!(options["values"], json!(["South"]));
    let exported = service
        .call(
            "dataset_export",
            &json!({"dashboardId":"board","datasetId":"sales"}),
        )
        .unwrap();
    assert_eq!(exported["transient"], true);
    assert!(exported["export"]["path"].is_null());
    assert_eq!(exported["export"]["rowCount"], 3);
    let view = service
        .call(
            "dashboard_view",
            &json!({"dashboardId":"board","responseMode":"patch","componentIds":["detail"]}),
        )
        .unwrap();
    assert_eq!(view["transient"], true);
    error(
        &service,
        "dashboard_export",
        json!({"dashboardId":"board","format":"html"}),
        "LIVE_DATA_REQUIRES_RUNTIME",
    );
    let exported = service
        .call(
            "dashboard_export",
            &json!({"dashboardId":"board","format":"json"}),
        )
        .unwrap();
    let content: Value =
        serde_json::from_slice(&fs::read(exported["export"]["path"].as_str().unwrap()).unwrap())
            .unwrap();
    assert!(content["snapshot"]["datasets"]["sales"].is_null());
    assert!(content["snapshot"]["datasetRefs"]["sales"].is_null());
    let source_id = imported["document"]["manifest"]["datasets"]["sales"]["sourceId"].clone();
    error(
        &service,
        "dashboard_patch",
        json!({"dashboardId":"board","expectedRevision":revision,"operations":[{"op":"put_source","id":source_id,"value":{"kind":"file"}}]}),
        "INVALID_OPERATION",
    );
    let snapshot = service.call("query_execute", &json!({"dashboardId":"board","datasetId":"sales","expectedRevision":revision,"connection":"sales","sql":"SELECT region, amount FROM sales WHERE 0"})).unwrap();
    assert_eq!(
        snapshot["document"]["manifest"]["datasets"]["sales"]["fields"]["amount"]["type"],
        "number"
    );
    assert_eq!(
        snapshot["document"]["snapshot"]["datasetRefs"]["sales"]["rowCount"],
        0
    );
    let info = service
        .call(
            "query_inspect",
            &json!({"dashboardId":"board","componentId":"detail"}),
        )
        .unwrap();
    assert!(info["note"].as_str().unwrap().contains("immutable"));
}

// @wu-test type=integration | scope=SQLite table attach | protects=table attachment validates the revision before importing and preserves declared field order
#[test]
fn attach_preview_and_preloaded_options_share_real_immutable_data() {
    let root = TempDir::new().unwrap();
    let path = root.path().join("source.sqlite3");
    let db = rusqlite::Connection::open(&path).unwrap();
    db.execute_batch("CREATE TABLE sales(region TEXT,amount REAL); INSERT INTO sales VALUES('East',12),('West',20);").unwrap();
    let config = root.path().join("sources.json");
    fs::write(
        &config,
        json!({"sales":{"engine":"sqlite","path":path}}).to_string(),
    )
    .unwrap();
    let mut service = service(root.path(), true, Some(&config));
    service
        .call("dashboard_create", &json!({"dashboardId":"board"}))
        .unwrap();
    error(
        &service,
        "dataset_attach",
        json!({"dashboardId":"board","datasetId":"sales","expectedRevision":999,"connection":"sales","table":"sales"}),
        "REVISION_CONFLICT",
    );
    let attached = service.call("dataset_attach", &json!({"dashboardId":"board","datasetId":"sales","expectedRevision":1,"connection":"sales","table":"sales"})).unwrap();
    assert_eq!(attached["import"]["rowCount"], 2);
    assert_eq!(
        attached["document"]["snapshot"]["datasetRefs"]["sales"]["fieldOrder"],
        json!(["region", "amount"])
    );
    let added = service.call("dashboard_submit", &json!({"dashboardId":"board","expectedRevision":2,"operations":[{"op":"put_component","id":"detail","value":{"kind":"table","datasetId":"sales","title":"Details"}},{"op":"set_filters","value":[{"id":"region","field":"region","op":"in","values":[],"componentIds":["detail"]}]}]})).unwrap();
    assert_eq!(added["ok"], true);
    service.store.config["loading"]["preloadFilterIds"] = json!(["region"]);
    let first = service
        .call("dashboard_get", &json!({"dashboardId":"board"}))
        .unwrap();
    assert_eq!(
        first["document"]["computed"]["filterOptions"]["region"],
        json!(["East", "West"])
    );
    let cached = service
        .call("dashboard_get", &json!({"dashboardId":"board"}))
        .unwrap();
    assert_eq!(
        cached["document"]["computed"]["filterPages"]["region"],
        first["document"]["computed"]["filterPages"]["region"]
    );
    let dir = service.store.runtime_root.join("filter-options");
    let cache = fs::read_dir(&dir).unwrap().next().unwrap().unwrap().path();
    fs::write(&cache, b"invalid cache").unwrap();
    let repaired = service
        .call("dashboard_get", &json!({"dashboardId":"board"}))
        .unwrap();
    assert_eq!(
        repaired["document"]["computed"]["filterOptions"]["region"],
        json!(["East", "West"])
    );
    assert!(serde_json::from_slice::<Value>(&fs::read(&cache).unwrap()).is_ok());
    let revision = added["revision"].clone();
    let changed = service.call("dashboard_patch", &json!({"dashboardId":"board","expectedRevision":revision,"operations":[{"op":"set_title","value":"Unsaved"}]})).unwrap();
    let saved_view = service.call("dashboard_view", &json!({"dashboardId":"board","expectedRevision":revision,"responseMode":"patch","componentIds":["detail"]})).unwrap();
    assert_eq!(saved_view["revision"], revision);
    error(
        &service,
        "dashboard_view",
        json!({"dashboardId":"board","dataVersion":"stale","expectedRevision":changed["document"]["revision"]}),
        "REVISION_CONFLICT",
    );
    assert_eq!(
        doctor::data_version(&service.store.get("board", false).unwrap()).unwrap(),
        first["document"]["dataVersion"].as_str().unwrap()
    );
}

// @wu-test type=boundary | scope=service argument validation | protects=malformed read, edit and diagnostic requests cannot mutate valid project state
#[test]
fn service_invalid_arguments_fail_with_traceable_errors() {
    let root = TempDir::new().unwrap();
    let service = service(root.path(), true, None);
    let revision = saved(&service);
    for (tool, args, code) in [
        ("unknown", json!({}), "UNKNOWN_TOOL"),
        ("dashboard_list", json!([]), "INVALID_ARGUMENT"),
        (
            "dashboard_submit",
            json!({"dashboardId":"board","createTitle":"Duplicate","expectedRevision":revision}),
            "INVALID_ARGUMENT",
        ),
        (
            "dashboard_patch",
            json!({"dashboardId":"board","expectedRevision":revision,"operations":{}}),
            "INVALID_ARGUMENT",
        ),
        (
            "dashboard_patch",
            json!({"dashboardId":"board","expectedRevision":revision,"expectedAnnotations":{},"operations":[{"op":"set_title","value":"Other"}]}),
            "INVALID_ARGUMENT",
        ),
        (
            "dashboard_patch",
            json!({"dashboardId":"board","expectedRevision":revision,"operations":[{"op":"set_chart","id":"detail","chartType":"bar"}]}),
            "UNSUPPORTED_CHART_FAMILY",
        ),
        (
            "dashboard_submit",
            json!({"dashboardId":"board","expectedRevision":revision,"operations":[{"op":"set_annotations","value":[]}]}),
            "INVALID_ARGUMENT",
        ),
        (
            "dashboard_view",
            json!({"dashboardId":"board","includeEvidence":"yes"}),
            "INVALID_ARGUMENT",
        ),
        (
            "dashboard_view",
            json!({"dashboardId":"board","includeEvidence":true,"responseMode":"full"}),
            "INVALID_ARGUMENT",
        ),
        (
            "dashboard_view",
            json!({"dashboardId":"board","responseMode":"patch","componentIds":[1]}),
            "INVALID_ARGUMENT",
        ),
        (
            "dashboard_view",
            json!({"dashboardId":"board","responseMode":"patch","includeFilterOptions":1}),
            "INVALID_ARGUMENT",
        ),
        (
            "dashboard_view",
            json!({"dashboardId":"board","responseMode":"patch","tableStates":[]}),
            "INVALID_ARGUMENT",
        ),
        (
            "component_data",
            json!({"dashboardId":"board","componentId":"detail","limit":0}),
            "INVALID_ARGUMENT",
        ),
        (
            "component_data",
            json!({"dashboardId":"board","componentId":"detail","offset":-1}),
            "INVALID_ARGUMENT",
        ),
        (
            "component_data",
            json!({"dashboardId":"board","componentId":"detail","search":"x".repeat(1001)}),
            "INVALID_ARGUMENT",
        ),
        (
            "component_data",
            json!({"dashboardId":"board","componentId":"missing"}),
            "INVALID_ARGUMENT",
        ),
        (
            "dataset_export",
            json!({"dashboardId":"board","datasetId":"missing"}),
            "INVALID_ARGUMENT",
        ),
        (
            "dashboard_history",
            json!({"dashboardId":"board","limit":0}),
            "INVALID_DOCUMENT",
        ),
        (
            "dashboard_doctor",
            json!({"dashboardId":"board","mode":"invalid"}),
            "INVALID_ARGUMENT",
        ),
        (
            "runtime_report_error",
            json!({"requestId":"x".repeat(65)}),
            "INVALID_ARGUMENT",
        ),
        (
            "runtime_report_error",
            json!({"code":"EXECUTE"}),
            "INVALID_ARGUMENT",
        ),
        (
            "runtime_report_error",
            json!({"code":"CLIENT_DATA_APPLIED","durationMs":-1}),
            "INVALID_ARGUMENT",
        ),
    ] {
        error(&service, tool, args, code);
    }
    assert_eq!(service.store.revision("board").unwrap(), revision);
    assert_eq!(
        service.call("runtime_keepalive", &json!({})).unwrap(),
        json!({"ok":true})
    );
    assert_eq!(
        service
            .call("dashboard_validate", &json!({"dashboardId":"board"}))
            .unwrap(),
        json!({"valid":true})
    );
    let report = service
        .call(
            "runtime_report_error",
            &json!({"requestId":"client-request","code":"CLIENT_DATA_APPLIED","durationMs":12.5}),
        )
        .unwrap();
    assert_eq!(report["ok"], true);
    let diagnostics = service
        .call(
            "runtime_diagnostics",
            &json!({"requestId":"client-request"}),
        )
        .unwrap();
    assert!(diagnostics.to_string().contains("CLIENT_DATA_APPLIED"));
    let info = service
        .call("runtime_info", &json!({"dashboardId":"board"}))
        .unwrap();
    assert_eq!(info["dashboardRevision"], revision);
    assert_eq!(info["runtimeLanguage"], "rust");
}

// @wu-test type=integration | scope=project persistence configuration | protects=invalid project metadata cannot redirect assets or discard existing checkpoints
#[test]
fn project_configuration_and_checkpoint_boundaries_preserve_existing_state() {
    let root = TempDir::new().unwrap();
    let mut defaults = store::defaults();
    let project = root.path().join("project");
    fs::create_dir_all(&project).unwrap();
    defaults["loading"]["pageSize"] = json!(20);
    store::write_json(&project.join("charts-project.json"), &defaults).unwrap();
    let service = service(root.path(), true, None);
    assert_eq!(service.store.config["loading"]["pageSize"], 20);
    let revision = saved(&service);
    assert!(service.store.cloud_assets().is_err());
    assert_eq!(
        service
            .store
            .label_checkpoint("board", revision, revision, "", false)
            .unwrap_err()
            .code,
        "INVALID_DOCUMENT"
    );
    assert_eq!(
        service
            .store
            .label_checkpoint("board", revision + 1, revision, "Name", false)
            .unwrap_err()
            .code,
        "REVISION_CONFLICT"
    );
    assert_eq!(
        service
            .store
            .label_checkpoint("board", revision, 999, "Name", false)
            .unwrap_err()
            .code,
        "INVALID_DOCUMENT"
    );
    assert_eq!(
        service.store.diff("board", revision, 999).unwrap_err().code,
        "INVALID_DOCUMENT"
    );
    assert_eq!(
        service
            .store
            .checkpoint("missing", 1, "Name", false, None)
            .unwrap_err()
            .code,
        "REVISION_CONFLICT"
    );
    assert_eq!(
        service.store.begin("board", revision + 1).unwrap_err().code,
        "REVISION_CONFLICT"
    );
    let old = service.store.get("board", false).unwrap();
    let reference = old["snapshot"]["datasetRefs"]["sales"].clone();
    let new_data = service
        .store
        .data
        .import_rows(
            &[json!({"region":"Latest","month":"2026-03-01","amount":99,"baseline":80})],
            &old["manifest"]["datasets"]["sales"]["fields"],
        )
        .unwrap();
    let changed = service.store.mutate("board", revision, Some(&[json!({"op":"put_dataset_ref","id":"sales","meta":old["manifest"]["datasets"]["sales"],"ref":new_data})]), None, false, None).unwrap();
    let next = changed["revision"].as_i64().unwrap();
    let restored = service
        .store
        .mutate("board", next, None, Some(revision), true, None)
        .unwrap();
    assert_eq!(
        restored["snapshot"]["datasetRefs"]["sales"]["version"],
        new_data["version"]
    );
    let original = service
        .store
        .mutate("board", next, None, Some(revision), false, None)
        .unwrap();
    assert_eq!(
        original["snapshot"]["datasetRefs"]["sales"]["version"],
        reference["version"]
    );
    drop(service);
    let reopened = Store::new(&root.path().join("new-cache"), Some(&project)).unwrap();
    assert_eq!(
        reopened.get("board", false).unwrap()["snapshot"]["datasetRefs"]["sales"]["version"],
        reference["version"]
    );
    assert_eq!(
        reopened
            .history("board", 0, 100)
            .unwrap()
            .as_array()
            .unwrap()
            .len(),
        2
    );
}
