use super::super::versions::Versions;
use super::*;
use std::sync::{mpsc, Arc, Barrier};
fn setup() -> (tempfile::TempDir, Store) {
    let root = tempfile::tempdir().unwrap();
    let store = Store::new(
        &root.path().join("cache"),
        Some(&root.path().join("project")),
    )
    .unwrap();
    (root, store)
}
fn annotation(id: &str, text: &str) -> Value {
    json!({"id":id,"text":text,"createdAt":"2026-11-28T00:00:00+00:00"})
}
#[test]
fn project_edits_annotations_and_mirrors_keep_independent_versions() {
    let (_root, store) = setup();
    store.create("board", "Before", None).unwrap();
    let changed = store
        .mutate(
            "board",
            1,
            Some(&[json!({"op":"set_title","value":"After"})]),
            None,
            false,
            None,
        )
        .unwrap();
    assert_eq!(changed["revision"], 2);
    assert_eq!(store.display_revision("board").unwrap(), Some(1));
    assert_eq!(
        store.readable("board").unwrap()["manifest"]["title"],
        "Before"
    );
    let repeated = store
        .mutate(
            "board",
            2,
            Some(&[json!({"op":"set_title","value":"After"})]),
            None,
            false,
            None,
        )
        .unwrap();
    assert_eq!(repeated["revision"], 2);
    let failed = store.mutate(
        "board",
        2,
        Some(&[
            json!({"op":"set_title","value":"Not committed"}),
            json!({"op":"set_theme","value":"invalid"}),
        ]),
        None,
        false,
        None,
    );
    assert!(failed.is_err());
    assert_eq!(
        store.get("board", false).unwrap()["manifest"]["title"],
        "After"
    );
    let saved = store
        .update_annotations(
            "board",
            2,
            &json!([]),
            &json!([annotation("note", "Keep this feedback")]),
        )
        .unwrap();
    assert_eq!(store.revision("board").unwrap(), 2);
    assert_eq!(saved["annotations"][0]["context"]["designRevision"], 2);
    assert_eq!(
        store
            .update_annotations("board", 2, &json!([]), &json!([]))
            .unwrap_err()
            .code,
        "ANNOTATION_CONFLICT"
    );
    let db = store.connect().unwrap();
    let count: i64 = db
        .query_row("SELECT count(*) FROM annotation_events", [], |r| r.get(0))
        .unwrap();
    fs::remove_file(store.root.join("board/annotations.json")).unwrap();
    store
        .update_annotations("board", 2, &saved["annotations"], &saved["annotations"])
        .unwrap();
    assert!(store.root.join("board/annotations.json").is_file());
    assert_eq!(
        db.query_row::<i64, _, _>("SELECT count(*) FROM annotation_events", [], |r| r.get(0))
            .unwrap(),
        count
    );
    drop(db);
    let restored = store
        .mutate("board", 2, None, Some(1), false, None)
        .unwrap();
    assert_eq!(restored["revision"], 3);
    assert_eq!(restored["manifest"]["title"], "Before");
    assert_eq!(restored["manifest"]["annotations"], saved["annotations"]);
    store
        .checkpoint("board", 3, "Reviewed", false, None)
        .unwrap();
    assert_eq!(store.display_revision("board").unwrap(), Some(3));
    assert!(store.root.join("board/checkpoints/3.json").is_file());
}
#[test]
fn releases_survive_checkpoint_retention_and_stale_deletion_is_rejected() {
    let (_root, store) = setup();
    store.create("board", "Saved", None).unwrap();
    let versions = Versions::new(&store).unwrap();
    versions.publish("board", 1, 1).unwrap();
    versions.publish("board", 1, 1).unwrap();
    assert_eq!(
        versions.status("board").unwrap()["releases"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    store
        .connect()
        .unwrap()
        .execute("DELETE FROM revisions WHERE board_id=?", ["board"])
        .unwrap();
    assert_eq!(
        versions.read("board", 1).unwrap()["manifest"]["title"],
        "Saved"
    );
    let old_plan = versions.delete_preview("board", 1, 1).unwrap();
    store
        .update_annotations(
            "board",
            1,
            &json!([]),
            &json!([annotation("note", "Changes review impact")]),
        )
        .unwrap();
    assert_eq!(
        versions
            .delete_checkpoint("board", 1, 1, old_plan["token"].as_str())
            .unwrap_err()
            .code,
        "PLAN_CHANGED"
    );
    let plan = versions.delete_preview("board", 1, 1).unwrap();
    assert_eq!(plan["clearsPublication"], true);
    versions
        .delete_checkpoint("board", 1, 1, plan["token"].as_str())
        .unwrap();
    assert_eq!(store.revision("board").unwrap(), 2);
    assert_eq!(
        store.get("board", false).unwrap()["manifest"]["annotations"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert!(versions.status("board").unwrap()["publishedRevision"].is_null());
    drop(versions);
    assert!(Versions::new(&store).unwrap().status("board").unwrap()["publishedRevision"].is_null());
    assert!(Versions::new(&store).unwrap().read("board", 1).is_err());
}
#[test]
fn annotation_compare_and_swap_and_parallel_appends_preserve_every_commit() {
    let (_root, store) = setup();
    store.create("board", "Review", None).unwrap();
    let store = Arc::new(store);
    let ready = Arc::new(Barrier::new(3));
    let writers = ["first", "second"].map(|id| {
        let store = Arc::clone(&store);
        let ready = Arc::clone(&ready);
        std::thread::spawn(move || {
            ready.wait();
            store.update_annotations("board", 1, &json!([]), &json!([annotation(id, id)]))
        })
    });
    ready.wait();
    let results = writers.map(|writer| writer.join().unwrap());
    assert_eq!(results.iter().filter(|result| result.is_ok()).count(), 1);
    assert_eq!(
        results
            .iter()
            .find_map(|result| result.as_ref().err())
            .unwrap()
            .code,
        "ANNOTATION_CONFLICT"
    );
    let ready = Arc::new(Barrier::new(3));
    let writers = ["third", "fourth"].map(|id| {
        let store = Arc::clone(&store);
        let ready = Arc::clone(&ready);
        std::thread::spawn(move || {
            ready.wait();
            store.append_annotation("board", &annotation(id, id), None)
        })
    });
    ready.wait();
    let receipts = writers.map(|writer| writer.join().unwrap().unwrap());
    for receipt in &receipts {
        let id = receipt["annotation"]["id"].as_str().unwrap();
        assert_eq!(
            store
                .append_annotation("board", &annotation(id, id), None)
                .unwrap(),
            *receipt
        );
    }
    let state = store.annotation_state("board", false).unwrap();
    assert_eq!(state["revision"], 1);
    assert_eq!(state["annotations"].as_array().unwrap().len(), 3);
    assert_eq!(
        serde_json::from_slice::<Value>(
            &fs::read(store.root.join("board/annotations.json")).unwrap()
        )
        .unwrap(),
        state["annotations"]
    );
    let events: Value = serde_json::from_slice(
        &fs::read(store.root.join("board/annotation-history.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(events.as_array().unwrap().len(), 3);
    assert_eq!(
        serde_json::from_str::<Value>(events[2]["payload"].as_str().unwrap()).unwrap(),
        state["annotations"]
    );
}
#[test]
fn annotation_retry_repairs_a_failed_mirror_after_database_commit() {
    let (_root, store) = setup();
    store.create("board", "Review", None).unwrap();
    let mirror = store.root.join("board/annotations.json");
    fs::remove_file(&mirror).unwrap();
    fs::create_dir(&mirror).unwrap();
    let note = annotation("note", "Committed once");
    assert!(store.append_annotation("board", &note, None).is_err());
    let state = store.annotation_state("board", false).unwrap();
    assert_eq!(state["annotations"].as_array().unwrap().len(), 1);
    fs::remove_dir(&mirror).unwrap();
    let receipt = store.append_annotation("board", &note, None).unwrap();
    assert_eq!(receipt["annotation"], state["annotations"][0]);
    assert_eq!(
        serde_json::from_slice::<Value>(&fs::read(&mirror).unwrap()).unwrap(),
        state["annotations"]
    );
    assert_eq!(store.revision("board").unwrap(), 1);
    let db = store.connect().unwrap();
    assert_eq!(
        db.query_row::<i64, _, _>(
            "SELECT count(*) FROM annotation_events WHERE board_id=?",
            ["board"],
            |row| row.get(0)
        )
        .unwrap(),
        1
    );
}
#[test]
fn annotation_cas_accepts_browser_number_round_trips_without_new_revisions() {
    let (_root, store) = setup();
    store.create("board", "Review", None).unwrap();
    let mut note = annotation("note", "Same position");
    note["anchor"] = json!({"scope":"page","kind":"area","quote":"","rect":{"x":0.0,"y":0.0,"width":1.0,"height":1.0}});
    store.append_annotation("board", &note, None).unwrap();
    let original = store.annotation_state("board", false).unwrap()["annotations"].clone();
    let mut browser = original.clone();
    browser[0]["anchor"]["rect"] = json!({"x":0,"y":0,"width":1,"height":1});
    assert_ne!(original, browser);
    store
        .update_annotations("board", 1, &browser, &browser)
        .unwrap();
    let unchanged = store
        .mutate(
            "board",
            1,
            Some(&[json!({"op":"set_annotations","value":browser})]),
            None,
            false,
            None,
        )
        .unwrap();
    assert_eq!(unchanged["revision"], 1);
    let db = store.connect().unwrap();
    assert_eq!(
        db.query_row::<i64, _, _>("SELECT count(*) FROM annotation_events", [], |row| row
            .get(0))
            .unwrap(),
        1
    );
    assert_eq!(
        store.annotation_state("board", false).unwrap()["annotations"],
        original
    );
    let mut edited = browser.clone();
    edited[0]["text"] = json!("Updated feedback");
    store
        .update_annotations("board", 1, &browser, &edited)
        .unwrap();
    assert_eq!(store.revision("board").unwrap(), 1);
    assert_eq!(
        store.annotation_state("board", false).unwrap()["annotations"][0]["text"],
        "Updated feedback"
    );
    assert_eq!(
        db.query_row::<i64, _, _>("SELECT count(*) FROM annotation_events", [], |row| row
            .get(0))
            .unwrap(),
        2
    );
}
#[test]
fn cleared_publication_head_stays_cleared_after_reopening_with_an_older_release() {
    let (root, store) = setup();
    store.create("board", "First release", None).unwrap();
    // This is the original release table format, before version_heads existed.
    let db = store.connect().unwrap();
    db.execute_batch("CREATE TABLE releases(id INTEGER PRIMARY KEY AUTOINCREMENT,board_id TEXT NOT NULL,revision INTEGER NOT NULL,created_at TEXT NOT NULL,document TEXT NOT NULL); INSERT INTO releases(board_id,revision,created_at,document) SELECT id,revision,'2026-11-26',document FROM boards;").unwrap();
    drop(db);
    let versions = Versions::new(&store).unwrap();
    assert_eq!(versions.status("board").unwrap()["publishedRevision"], 1);
    store
        .mutate(
            "board",
            1,
            Some(&[json!({"op":"set_title","value":"Second release"})]),
            None,
            false,
            None,
        )
        .unwrap();
    store.checkpoint("board", 2, "Second", false, None).unwrap();
    versions.publish("board", 2, 2).unwrap();
    let plan = versions.delete_preview("board", 2, 2).unwrap();
    versions
        .delete_checkpoint("board", 2, 2, plan["token"].as_str())
        .unwrap();
    drop(versions);
    drop(store);
    let reopened = Store::new(
        &root.path().join("new-cache"),
        Some(&root.path().join("project")),
    )
    .unwrap();
    let versions = Versions::new(&reopened).unwrap();
    let status = versions.status("board").unwrap();
    assert!(status["publishedRevision"].is_null());
    assert_eq!(status["draftRevision"], 3);
    assert_eq!(status["savedRevision"], 1);
    assert_eq!(
        versions.read("board", 1).unwrap()["manifest"]["title"],
        "First release"
    );
    assert_eq!(
        reopened.get("board", false).unwrap()["manifest"]["title"],
        "Second release"
    );
    assert_eq!(versions.read("board", 2).unwrap_err().code, "NOT_FOUND");
}
#[test]
fn repeated_version_reads_do_not_wait_for_an_unrelated_writer() {
    let (_root, store) = setup();
    store.create("board", "Published", None).unwrap();
    Versions::new(&store)
        .unwrap()
        .publish("board", 1, 1)
        .unwrap();
    let store = Arc::new(store);
    let writer = store.connect().unwrap();
    writer.execute_batch("BEGIN IMMEDIATE").unwrap();
    let (sender, receiver) = mpsc::channel();
    let reader_store = Arc::clone(&store);
    let reader = std::thread::spawn(move || {
        let versions = Versions::new(&reader_store).unwrap();
        sender
            .send((versions.status("board"), versions.read("board", 1)))
            .unwrap();
    });
    let result = receiver.recv_timeout(Duration::from_secs(2));
    writer.execute_batch("ROLLBACK").unwrap();
    reader.join().unwrap();
    let (status, document) = result.expect("saved-version reads must not take a SQLite write lock");
    assert_eq!(status.unwrap()["publishedRevision"], 1);
    assert_eq!(document.unwrap()["manifest"]["title"], "Published");
}
#[test]
fn legacy_sqlite_document_and_migration_preserve_immutable_data() {
    let root = tempfile::tempdir().unwrap();
    let source = Store::new(&root.path().join("legacy"), None).unwrap();
    let mut doc = model::new_document("board", "历史文档").unwrap();
    doc["manifest"]["sources"] = json!({"source":{"kind":"declared"}});
    doc["manifest"]["datasets"] = json!({"data":{"sourceId":"source","fields":{"z":{"type":"number"},"a":{"type":"string"}}}});
    doc["manifest"]["annotations"] = json!([annotation("note", "Original")]);
    let context = json!({"designRevision":7,"dataVersions":{"historical":{"version":"a".repeat(64)}},"filters":[{"field":"a","op":"in","values":["北京"]}]});
    doc["manifest"]["annotations"][0]["context"] = context.clone();
    doc["snapshot"]["datasets"] = json!({"data":[{"z":1.0,"a":"北京"},{"a":null},{"z":-0.0}]});
    source.create("board", "历史文档", Some(&doc)).unwrap();
    let original = source.get("board", false).unwrap();
    let reference = original["snapshot"]["datasetRefs"]["data"].clone();
    let original_rows = source.data.all_rows(&reference).unwrap();
    let target = root.path().join("project");
    let cache = root.path().join("cache");
    let boards = vec!["board".to_owned()];
    let preview = migrate_project(&source.root, &target, &cache, &boards, false).unwrap();
    assert_eq!(preview["applied"], false);
    assert!(!target.exists());
    migrate_project(&source.root, &target, &cache, &boards, true).unwrap();
    let migrated = Store::new(&cache, Some(&target)).unwrap();
    let current = migrated.get("board", false).unwrap();
    assert_eq!(current["snapshot"], original["snapshot"]);
    assert_eq!(current["manifest"]["annotations"][0]["id"], "note");
    assert_eq!(current["manifest"]["annotations"][0]["context"], context);
    assert_eq!(migrated.data.all_rows(&reference).unwrap(), original_rows);
    assert_eq!(
        migrated
            .history("board", 0, 50)
            .unwrap()
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert!(target.join("dashboards/board/checkpoints/1.json").is_file());
}
