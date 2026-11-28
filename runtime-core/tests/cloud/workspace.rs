//! Real PostgreSQL contracts, isolated from operator databases and credentials.
use charts_design_core::runtime::{
    cloud::{self, CloudDatabase},
    cloud_assets,
    cloud_data::CloudData,
    data::LocalData,
    operations,
    query::QueryRunner,
    service::Service,
    versions::Versions,
};
use postgres::{Client, NoTls};
use serde_json::json;
use std::{env, fs};

use super::database::{Database, ENVIRONMENT};

fn create_sales(service: &Service) -> i64 {
    service
        .call(
            "dashboard_submit",
            &json!({"dashboardId":"sales", "createTitle":"Sales", "operations":[
                {"op":"put_source","id":"fixture","value":{"kind":"fixture","name":"Sales"}},
                {"op":"put_dataset","id":"sales","meta":{"sourceId":"fixture","fields":{
                    "region":{"type":"string"},"amount":{"type":"number"},"day":{"type":"date"}
                }},"rows":[
                    {"region":"East","amount":10,"day":"2026-01-01"},
                    {"region":"West","amount":20,"day":"2026-01-02"},
                    {"region":"East","amount":30,"day":"2026-01-03"}
                ]},
                {"op":"put_component","id":"detail","value":{"kind":"table","title":"Sales","datasetId":"sales"}}
            ]}),
        )
        .unwrap()["revision"]
        .as_i64()
        .unwrap()
}

// @wu-test type=integration | scope=PostgreSQL author storage and immutable assets | protects=Rust migration loses saved data, annotations, file hashes or checkpoint references after a cache restart
#[test]
fn postgres_workspaces_survive_asset_migration_and_cache_restarts() {
    let _environment = ENVIRONMENT.lock().unwrap_or_else(|e| e.into_inner());
    let fixture = Database::new();
    assert!(cloud::cloud_enabled().unwrap());
    fixture.legacy_project("sales-project");
    let service = fixture.service("sales-project", "legacy-cache");
    assert!(!service.store.cos_enabled);
    let first = create_sales(&service);
    let first_document = service.store.get("sales", false).unwrap();
    let reference = first_document["snapshot"]["datasetRefs"]["sales"].clone();
    assert_eq!(service.store.list().unwrap()[0]["id"], "sales");
    assert_eq!(
        service.store.display_revision("sales").unwrap(),
        Some(first)
    );
    assert_eq!(service.store.readable("sales").unwrap()["revision"], first);
    assert_eq!(service.store.revision("sales").unwrap(), first);
    assert!(service.store.connect().is_err());
    let database = CloudDatabase::new().unwrap();
    assert!(database
        .call("generations_match", "sales-project", &json!({"pages":{}}))
        .unwrap()
        .as_bool()
        .unwrap());

    let note = json!({"id":"review", "componentId":"detail", "text":"Verify regional totals", "createdAt":"2026-11-28T00:00:00Z"});
    let appended = service
        .store
        .append_annotation("sales", &note, None)
        .unwrap();
    assert_eq!(appended["annotation"]["text"], note["text"]);
    assert_eq!(
        service
            .store
            .append_annotation("sales", &note, None)
            .unwrap()["annotation"],
        appended["annotation"]
    );
    let state = service.store.annotation_state("sales", true).unwrap();
    assert_eq!(state["annotations"].as_array().unwrap().len(), 1);
    assert_eq!(state["components"]["detail"]["kind"], "table");
    let mut changed = state["annotations"].clone();
    changed[0]["text"] = json!("Confirmed regional totals");
    let updated = service
        .store
        .update_annotations("sales", first, &state["annotations"], &changed)
        .unwrap();
    assert_eq!(updated["annotations"][0]["text"], changed[0]["text"]);
    assert_eq!(
        service
            .store
            .update_annotations("sales", first, &state["annotations"], &json!([]))
            .unwrap_err()
            .code,
        "ANNOTATION_CONFLICT"
    );
    let second = service
        .call("dashboard_submit", &json!({"dashboardId":"sales","expectedRevision":first,"operations":[{"op":"set_title","value":"Reviewed sales"}]}))
        .unwrap()["revision"]
        .as_i64()
        .unwrap();
    assert!(second > first);
    assert_eq!(
        service.store.begin("sales", first).unwrap_err().code,
        "REVISION_CONFLICT"
    );
    let batch = service.store.begin("sales", second).unwrap();
    assert!(batch.is_object());
    service
        .store
        .checkpoint("sales", second, "Reviewed", false, None)
        .unwrap();
    service
        .store
        .label_checkpoint("sales", second, first, "Original", false)
        .unwrap();
    assert_eq!(
        service
            .store
            .history("sales", 0, 10)
            .unwrap()
            .as_array()
            .unwrap()
            .iter()
            .map(|entry| entry["revision"].as_i64().unwrap())
            .collect::<Vec<_>>(),
        vec![second, first, 1]
    );
    assert!(!service
        .store
        .diff("sales", first, second)
        .unwrap()
        .is_null());
    let versions = Versions::new(&service.store).unwrap();
    assert_eq!(
        versions.read("sales", first).unwrap()["manifest"]["title"],
        "Sales"
    );
    assert_eq!(
        versions.publish("sales", second, first).unwrap()["publishedRevision"],
        first
    );
    assert_eq!(versions.status("sales").unwrap()["savedRevision"], second);

    let restored = fixture.service("sales-project", "cold-legacy-cache");
    assert_eq!(restored.store.data.all_rows(&reference).unwrap().len(), 3);
    assert_eq!(
        restored.store.data.all_rows(&reference).unwrap()[2]["amount"],
        30
    );
    assert_eq!(
        restored
            .store
            .data
            .describe(reference["version"].as_str().unwrap())
            .unwrap(),
        reference
    );
    assert_eq!(
        restored.store.get("sales", true).unwrap()["manifest"]["annotations"][0]["text"],
        "Confirmed regional totals"
    );

    let uploaded = fixture.path("input.csv");
    fs::write(&uploaded, "region,amount\nEast,10\n").unwrap();
    let key = cloud_assets::save_file("sales-project", "sources/sales.csv", &uploaded).unwrap();
    assert!(key.starts_with("sales-project/"));
    let downloaded = fixture.path("restored.csv");
    assert!(cloud_assets::restore_file("sales-project", "sources/sales.csv", &downloaded).unwrap());
    assert_eq!(fs::read(&uploaded).unwrap(), fs::read(&downloaded).unwrap());
    assert!(
        !cloud_assets::restore_file("sales-project", "sources/absent.csv", &downloaded).unwrap()
    );

    let plan = operations::migrate_cos(
        "sales-project",
        &fixture.path("workspaces"),
        false,
        &["region".into()],
    )
    .unwrap();
    assert_eq!(plan["action"], "plan");
    assert_eq!(plan["datasets"], 1);
    let migrated = operations::migrate_cos(
        "sales-project",
        &fixture.path("workspaces"),
        true,
        &["region".into()],
    )
    .unwrap();
    assert_eq!(migrated["action"], "migrated");
    assert_eq!(migrated["format"], "cos-v1");
    assert_eq!(
        operations::migrate_cos("sales-project", &fixture.path("workspaces"), true, &[]).unwrap()
            ["action"],
        "already_migrated"
    );

    let migrated_service = fixture.service("sales-project", "cold-asset-cache");
    assert!(migrated_service.store.cos_enabled);
    let saved = migrated_service.store.get("sales", true).unwrap();
    assert_eq!(saved["manifest"]["title"], "Reviewed sales");
    assert_eq!(
        migrated_service
            .store
            .data
            .all_rows(&reference)
            .unwrap()
            .len(),
        3
    );
    assert_eq!(
        migrated_service.store.data.all_rows(&reference).unwrap()[1]["region"],
        "West"
    );
    let assets = migrated_service.store.cloud_assets().unwrap();
    let object = assets
        .call("object_get", &json!({"version":reference["version"]}))
        .unwrap();
    assert_eq!(object["descriptor"]["partitionIndex"]["field"], "region");
    assert!(!assets
        .read_file(&object, "manifest.json")
        .unwrap()
        .is_empty());
    assert_eq!(
        assets
            .save_dataset(&service.store.data, &reference, Some("region"))
            .unwrap(),
        object
    );
    let mut false_reference = reference.clone();
    false_reference["rowCount"] = json!(99);
    assert_eq!(
        assets
            .save_dataset(&service.store.data, &false_reference, None)
            .unwrap_err()
            .code,
        "DATA_CONFLICT"
    );
    assert_eq!(
        assets
            .read_file(&object, "not-registered")
            .unwrap_err()
            .code,
        "NOT_FOUND"
    );
    let mut corrupt_descriptor = object.clone();
    corrupt_descriptor["descriptor"]["files"]["manifest.json"]["sha256"] = json!("0".repeat(64));
    assert_eq!(
        assets
            .read_file(&corrupt_descriptor, "manifest.json")
            .unwrap_err()
            .code,
        "CLOUD_FILE_CORRUPT"
    );
    let target = fixture.path("protected-download");
    fs::write(&target, "keep").unwrap();
    assert_eq!(
        assets
            .download_file(&corrupt_descriptor, "manifest.json", &target)
            .unwrap_err()
            .code,
        "CLOUD_FILE_CORRUPT"
    );
    assert_eq!(fs::read(&target).unwrap(), b"keep");

    let envelope = cloud_assets::encode_document("sales-project", &saved).unwrap();
    let mut revised_envelope = envelope.clone();
    revised_envelope["manifest"]["annotations"] = changed.clone();
    assert_eq!(
        cloud_assets::decode_document("sales-project", &revised_envelope).unwrap()["manifest"]
            ["annotations"],
        changed
    );
    assert_eq!(
        cloud_assets::decode_document("sales-project", &saved).unwrap(),
        saved
    );
    assert_eq!(
        assets
            .hydrate_document(&json!({"cosObject":"not-registered"}))
            .unwrap_err()
            .code,
        "ASSET_UNAVAILABLE"
    );
    let asset_data = migrated_service.store.data.cloud.as_ref().unwrap();
    assert_eq!(
        asset_data.ensure_version(&"a".repeat(64)).unwrap_err().code,
        "ASSET_UNAVAILABLE"
    );
    let cached = asset_data
        .ensure_version(reference["version"].as_str().unwrap())
        .unwrap();
    {
        let database = rusqlite::Connection::open(&cached).unwrap();
        database
            .execute("UPDATE versions SET metadata='{}'", [])
            .unwrap();
        assert_eq!(
            asset_data
                .ensure_version(reference["version"].as_str().unwrap())
                .unwrap_err()
                .code,
            "DATA_CONFLICT"
        );
        database
            .execute("UPDATE versions SET metadata=?", [reference.to_string()])
            .unwrap();
    }
    assert_eq!(
        asset_data.repartition(&reference, "region").unwrap(),
        reference
    );
    let repartitioned = asset_data.repartition(&reference, "day").unwrap();
    assert_ne!(repartitioned["version"], reference["version"]);
    assert_eq!(repartitioned["rowCount"], reference["rowCount"]);
    assert_eq!(
        asset_data
            .repartition(&reference, "amount")
            .unwrap_err()
            .code,
        "INVALID_ARGUMENT"
    );
    assert_eq!(
        service
            .store
            .data
            .cloud
            .as_ref()
            .unwrap()
            .repartition(&reference, "region")
            .unwrap_err()
            .code,
        "UNSUPPORTED_OPERATION"
    );

    let next = migrated_service
        .call("dashboard_submit", &json!({"dashboardId":"sales","expectedRevision":second,"operations":[{"op":"set_title","value":"Asset-backed sales"}]}))
        .unwrap()["revision"].as_i64().unwrap();
    assert_eq!(
        Versions::new(&migrated_service.store)
            .unwrap()
            .read("sales", first)
            .unwrap()["manifest"]["title"],
        "Sales"
    );
    assert_eq!(
        fixture
            .service("sales-project", "final-cache")
            .store
            .readable("sales")
            .unwrap()["revision"],
        next
    );
    let cleanup = operations::cleanup().unwrap();
    assert!(cleanup["failed"].as_array().unwrap().is_empty());
}

// @wu-test type=integration | scope=PostgreSQL chunk restore and account permissions | protects=large legacy datasets lose field order, cross-project access or partial writes bypass checksum and role gates
#[test]
fn postgres_chunks_preserve_order_and_database_roles_are_restricted() {
    let _environment = ENVIRONMENT.lock().unwrap_or_else(|e| e.into_inner());
    let fixture = Database::new();
    let database = CloudDatabase::new().unwrap();
    fixture.legacy_project("chunk-project");
    assert_eq!(
        database
            .call("ensure", "chunk-project", &json!({"config":{}}))
            .unwrap()["storageFormat"],
        "postgres"
    );
    let local = LocalData::new(Some(&fixture.path("source-data"))).unwrap();
    let fields = json!({"position":{"type":"number"},"region":{"type":"string"}});
    let rows = (0..1203)
        .map(|n| json!({"position":n,"region":if n%2==0 {"East"} else {"West"}}))
        .collect::<Vec<_>>();
    let reference = local.import_rows(&rows, &fields).unwrap();
    let durable = CloudData::new(local, "chunk-project", false).unwrap();
    assert_eq!(durable.persist_cached(&reference).unwrap(), reference);
    assert_eq!(durable.persist_cached(&reference).unwrap(), reference);
    let restored =
        LocalData::with_cloud(&fixture.path("restored-data"), "chunk-project", false).unwrap();
    assert_eq!(restored.all_rows(&reference).unwrap(), rows);
    assert_eq!(restored.all_rows(&reference).unwrap(), rows);
    let other_project = CloudData::new(
        LocalData::new(Some(&fixture.path("other-data"))).unwrap(),
        "other-project",
        false,
    )
    .unwrap();
    assert_eq!(
        other_project
            .describe(reference["version"].as_str().unwrap())
            .unwrap_err()
            .code,
        "NOT_FOUND"
    );
    assert_eq!(
        other_project.ensure_version("../data").unwrap_err().code,
        "INVALID_ARGUMENT"
    );
    let empty = durable.local.import_rows(&[], &fields).unwrap();
    durable.persist_cached(&empty).unwrap();
    assert!(restored.all_rows(&empty).unwrap().is_empty());
    let mut wrong = reference.clone();
    wrong["rowCount"] = json!(1204);
    assert_eq!(
        durable.persist_cached(&wrong).unwrap_err().code,
        "DATA_CONFLICT"
    );

    let mut runtime = Client::connect(&fixture.runtime_url, NoTls).unwrap();
    for sql in [
        "SELECT * FROM charts.datasets",
        "CREATE ROLE cannot_escape",
        "CREATE DATABASE cannot_escape",
    ] {
        assert!(
            runtime.batch_execute(sql).is_err(),
            "runtime permission escape: {sql}"
        );
    }
    let unknown = database.with_function("pg_sleep");
    assert_eq!(unknown.err().unwrap().code, "INVALID_CONFIG");
    assert_eq!(
        database
            .call("ensure", "chunk-project", &json!([]))
            .unwrap_err()
            .code,
        "INVALID_ARGUMENT"
    );
    assert!(database
        .with_function("charts_data_inventory")
        .unwrap()
        .call("inventory", "chunk-project", &json!({}))
        .is_ok());

    fixture.legacy_project("unfinished-project");
    database
        .call("ensure", "unfinished-project", &json!({"config":{}}))
        .unwrap();
    database
        .call(
            "data_chunk_put",
            "unfinished-project",
            &json!({"version":"f".repeat(64),"part":0,"rows":[{"n":1}]}),
        )
        .unwrap();
    assert_eq!(
        operations::migrate_cos(
            "unfinished-project",
            &fixture.path("workspaces"),
            false,
            &[]
        )
        .unwrap()["unfinishedChunks"],
        1
    );
    assert_eq!(
        operations::migrate_cos("unfinished-project", &fixture.path("workspaces"), true, &[])
            .unwrap_err()
            .code,
        "DATA_INCOMPLETE"
    );

    env::set_var("DATABASE_URL", &fixture.owner_url);
    operations::run(&["migrate-neon".into()]).unwrap().unwrap();
    assert_eq!(
        CloudDatabase::new()
            .unwrap()
            .call("list", "chunk-project", &json!({}))
            .unwrap_err()
            .code,
        "FORBIDDEN"
    );
    let mut owner = Client::connect(&fixture.owner_url, NoTls).unwrap();
    owner.execute("UPDATE charts.neon_migrations SET digest='changed' WHERE name=(SELECT min(name) FROM charts.neon_migrations)", &[]).unwrap();
    assert_eq!(
        operations::migrate_neon().unwrap_err().code,
        "MIGRATION_CONFLICT"
    );
    for (backend, enabled) in [
        ("local", false),
        ("cloudflare", false),
        ("cloudbase", true),
        ("neon", true),
    ] {
        env::set_var("CHARTS_STORAGE_BACKEND", backend);
        assert_eq!(cloud::cloud_enabled().unwrap(), enabled);
    }
    env::set_var("CHARTS_STORAGE_BACKEND", "unknown");
    assert_eq!(cloud::cloud_enabled().unwrap_err().code, "INVALID_CONFIG");
    env::set_var("CHARTS_DATABASE_BACKEND", "unknown");
    assert_eq!(CloudDatabase::new().err().unwrap().code, "INVALID_CONFIG");
    env::set_var("CHARTS_DATABASE_BACKEND", "neon");
    env::set_var("DATABASE_URL", "");
    assert_eq!(CloudDatabase::new().err().unwrap().code, "INVALID_CONFIG");
    env::set_var("DATABASE_URL", "not a database connection");
    assert_eq!(
        CloudDatabase::new()
            .unwrap()
            .call("list", "chunk-project", &json!({}))
            .unwrap_err()
            .code,
        "INVALID_CONFIG"
    );
    env::set_var("CHARTS_DATABASE_BACKEND", "cloudbase");
    env::set_var("CLOUDBASE_ENV_ID", "invalid/id");
    assert_eq!(CloudDatabase::new().err().unwrap().code, "INVALID_CONFIG");
    env::set_var("CLOUDBASE_ENV_ID", "test-environment");
    env::set_var("CLOUDBASE_API_KEY", "");
    assert_eq!(CloudDatabase::new().err().unwrap().code, "INVALID_CONFIG");
    env::set_var("CLOUDBASE_API_KEY", "synthetic-test-key");
    let gateway = CloudDatabase::new().unwrap();
    assert_eq!(
        gateway.url,
        "https://test-environment.api.tcloudbasegateway.com/v1/rdb/rest/rpc"
    );
    for function in [
        "charts_runtime",
        "charts_assets",
        "charts_release",
        "charts_delete_checkpoint",
        "charts_data_inventory",
        "charts_share_annotations",
    ] {
        assert_eq!(gateway.with_function(function).unwrap().function, function);
    }
}

// @wu-test type=integration | scope=maintenance readiness and retry bounds | protects=deployment reports a broken runtime as healthy or waits indefinitely after a failed startup
#[test]
fn maintenance_healthchecks_retry_only_within_the_requested_window() {
    use std::{
        io::{Read, Write},
        net::TcpListener,
        thread,
    };
    let _environment = ENVIRONMENT.lock().unwrap_or_else(|e| e.into_inner());
    let _fixture = Database::new();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    env::set_var(
        "CHARTS_PORT",
        listener.local_addr().unwrap().port().to_string(),
    );
    let responses = thread::spawn(move || {
        for (status, body) in [
            (503, r#"{"ok":false}"#),
            (200, "invalid JSON"),
            (200, r#"{"ok":false}"#),
            (200, r#"{"ok":true,"version":"test-runtime"}"#),
        ] {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = [0; 1024];
            let n = stream.read(&mut request).unwrap();
            assert!(std::str::from_utf8(&request[..n])
                .unwrap()
                .starts_with("GET /health "));
            write!(stream, "HTTP/1.1 {status} Response\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len()).unwrap();
        }
    });
    assert_eq!(
        operations::healthcheck(5.0).unwrap()["version"],
        "test-runtime"
    );
    responses.join().unwrap();
    assert_eq!(
        operations::healthcheck(0.0).unwrap_err().code,
        "HEALTHCHECK_FAILED"
    );
    env::set_var("CHARTS_PORT", "invalid");
    assert_eq!(
        operations::healthcheck(0.0).unwrap_err().code,
        "INVALID_CONFIG"
    );
    for wait in [f64::NAN, -1.0, 301.0] {
        assert_eq!(
            operations::healthcheck(wait).unwrap_err().code,
            "INVALID_ARGUMENT"
        );
    }
    env::remove_var("TENCENTCLOUD_RUNENV");
    assert_eq!(
        operations::cleanup_server().unwrap_err().code,
        "INVALID_CONFIG"
    );
}

// @wu-test type=integration | scope=cleanup function HTTP entry point | protects=failed cleanup is acknowledged as success or the native event function cannot serve health and durable cleanup requests
#[cfg(unix)]
#[test]
fn cleanup_event_server_preserves_failures_and_exits_gracefully() {
    use std::{
        process::{Child, Command, Stdio},
        thread,
        time::{Duration, Instant},
    };
    struct Cleanup(Child);
    impl Drop for Cleanup {
        fn drop(&mut self) {
            if self.0.try_wait().ok().flatten().is_some() {
                return;
            }
            let _ = Command::new("kill")
                .args(["-INT", &self.0.id().to_string()])
                .status();
            for _ in 0..100 {
                if self.0.try_wait().ok().flatten().is_some() {
                    return;
                }
                thread::sleep(Duration::from_millis(20));
            }
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
    let _environment = ENVIRONMENT.lock().unwrap_or_else(|e| e.into_inner());
    let fixture = Database::new();
    let mut process = Cleanup(
        Command::new(env!("CARGO_BIN_EXE_charts-design-core"))
            .arg("cleanup-server")
            .env("TENCENTCLOUD_RUNENV", "SCF")
            .stdout(Stdio::null())
            .spawn()
            .unwrap(),
    );
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .unwrap();
    let started = Instant::now();
    let health = loop {
        if let Ok(response) = client.get("http://127.0.0.1:9000/health").send() {
            break response.json::<serde_json::Value>().unwrap();
        }
        assert!(
            process.0.try_wait().unwrap().is_none(),
            "cleanup server exited before readiness"
        );
        assert!(started.elapsed() < Duration::from_secs(10));
        thread::sleep(Duration::from_millis(20));
    };
    assert_eq!(health["role"], "cleanup");
    assert_eq!(health["version"], env!("CARGO_PKG_VERSION"));
    let ready = client
        .post("http://127.0.0.1:9000/event-invoke")
        .send()
        .unwrap();
    assert!(ready.status().is_success());
    assert!(ready.json::<serde_json::Value>().unwrap()["failed"]
        .as_array()
        .unwrap()
        .is_empty());
    let bad_job = fixture.path("private-shares/publication-intents/invalid.json");
    fs::create_dir_all(bad_job.parent().unwrap()).unwrap();
    fs::write(&bad_job, "corrupt").unwrap();
    let failure = client
        .post("http://127.0.0.1:9000/event-invoke")
        .send()
        .unwrap();
    assert_eq!(failure.status().as_u16(), 500);
    assert_eq!(
        failure.json::<serde_json::Value>().unwrap()["error"]["code"],
        "CLEANUP_FAILED"
    );
    assert!(bad_job.exists());
    fs::remove_file(&bad_job).unwrap();
    assert!(Command::new("kill")
        .args(["-INT", &process.0.id().to_string()])
        .status()
        .unwrap()
        .success());
    let stopping = Instant::now();
    loop {
        if let Some(status) = process.0.try_wait().unwrap() {
            assert!(status.success());
            break;
        }
        assert!(
            stopping.elapsed() < Duration::from_secs(5),
            "cleanup did not stop gracefully"
        );
        thread::sleep(Duration::from_millis(20));
    }
}

// @wu-test type=integration | scope=PostgreSQL query encoding, schema and read-only transactions | protects=Rust binds dates or scalars incorrectly, truncates results, leaks source writes or ignores timeouts
#[test]
fn postgres_queries_preserve_types_and_reject_side_effects() {
    let _environment = ENVIRONMENT.lock().unwrap_or_else(|e| e.into_inner());
    let fixture = Database::new();
    env::set_var("CHARTS_TEST_QUERY_URL", &fixture.runtime_url);
    let configuration = fixture.path("sources.json");
    fs::write(
        &configuration,
        r#"{"test":{"engine":"postgresql","dsnEnv":"CHARTS_TEST_QUERY_URL"}}"#,
    )
    .unwrap();
    let runner = QueryRunner::new(Some(&configuration)).unwrap();
    let parameters = json!([
        true,
        12,
        345,
        67890,
        1.5,
        2.5,
        12.25,
        "2026-11-28",
        "hello",
        null,
        "scalar"
    ]);
    let query = "SELECT %s::bool AS flag,%s::int2 AS small,%s::int4 AS medium,%s::int8 AS large,%s::float4 AS single,%s::float8 AS double,%s::numeric AS decimal,%s::date AS day,%s::text AS label,%s::text AS absent,%s::jsonb AS scalar";
    let result = runner
        .execute(
            "test",
            query,
            Some(&parameters),
            3.0,
            None,
            Some("postgresql"),
        )
        .unwrap();
    assert_eq!(
        result.rows[0],
        json!({"flag":true,"small":12,"medium":345,"large":67890,"single":1.5,"double":2.5,"decimal":12.25,"day":"2026-11-28","label":"hello","absent":null,"scalar":"scalar"})
    );
    assert_eq!(result.fields["day"]["type"], "date");
    assert_eq!(result.source["query"]["parameters"], parameters);
    let values = runner.execute("test", "SELECT '12:34:56'::time AS clock,'2026-11-28 12:34:56'::timestamp AS local,'2026-11-28 12:34:56+00'::timestamptz AS instant,'550e8400-e29b-41d4-a716-446655440000'::uuid AS uuid, 'quoted'::varchar AS text, 'a'::char AS fixed, 'name'::name AS name, '12'::json AS json", None, 3.0, None, None).unwrap();
    assert_eq!(values.rows[0]["clock"], "12:34:56");
    assert_eq!(values.rows[0]["local"], "2026-11-28T12:34:56");
    assert_eq!(values.rows[0]["instant"], "2026-11-28T12:34:56+00:00");
    assert_eq!(
        values.rows[0]["uuid"],
        "550e8400-e29b-41d4-a716-446655440000"
    );
    assert_eq!(values.rows[0]["json"], 12);
    let temporal = runner.execute("test", "SELECT %s::time AS clock,%s::timestamp AS local,%s::timestamptz AS instant,%s::uuid AS uuid", Some(&json!(["12:34:56","2026-11-28 12:34:56","2026-11-28 12:34:56+00","550e8400-e29b-41d4-a716-446655440000"])), 3.0, None, None).unwrap();
    for key in ["clock", "local", "instant", "uuid"] {
        assert_eq!(temporal.rows[0][key], values.rows[0][key]);
    }
    let named = runner
        .execute(
            "test",
            "SELECT %(n)s::int AS n, '100%%'::text AS percent",
            Some(&json!({"n":23})),
            3.0,
            None,
            None,
        )
        .unwrap();
    assert_eq!(named.rows[0], json!({"n":23,"percent":"100%"}));
    let empty = runner
        .execute(
            "test",
            "SELECT 1 AS amount WHERE false",
            None,
            3.0,
            None,
            None,
        )
        .unwrap();
    assert!(empty.rows.is_empty());
    assert_eq!(empty.fields["amount"]["type"], "string");
    let bools = runner
        .execute(
            "test",
            "SELECT 1 AS flag",
            None,
            3.0,
            Some(&json!({"flag":{"type":"boolean"}})),
            None,
        )
        .unwrap();
    assert_eq!(bools.rows[0]["flag"], true);

    for query in [
        "CREATE TABLE forbidden(value integer)",
        "SELECT 1; SELECT 2",
        "SELECT * FROM charts.datasets",
        "SELECT '{}'::jsonb AS nested",
        "SELECT ARRAY[1] AS nested",
        "SELECT 'NaN'::float8 AS value",
        "SELECT 'Infinity'::float4 AS value",
        "SELECT 1 AS duplicate, 2 AS duplicate",
        "SELECT generate_series(1,10001) AS value",
    ] {
        assert!(
            runner
                .execute("test", query, None, 3.0, None, None)
                .is_err(),
            "unsafe or lossy query: {query}"
        );
    }
    assert_eq!(
        runner
            .execute("test", "SELECT pg_sleep(1)", None, 0.02, None, None)
            .err()
            .unwrap()
            .code,
        "QUERY_TIMEOUT"
    );
    assert_eq!(
        runner
            .execute(
                "test",
                "SELECT 1 AS actual",
                None,
                3.0,
                Some(&json!({"other":{"type":"number"}})),
                None
            )
            .err()
            .unwrap()
            .code,
        "QUERY_SCHEMA_CHANGED"
    );
    for (query, parameters) in [
        ("SELECT %s::int", json!([])),
        ("SELECT %(missing)s::int", json!({"n":1})),
        ("SELECT %(n", json!({"n":1})),
        ("SELECT %(n)x", json!({"n":1})),
        ("SELECT %q", json!([1])),
        ("SELECT %s::int", json!([1, 2])),
        ("SELECT %s::int", json!([{}])),
        ("SELECT %s::int2", json!([100000])),
    ] {
        assert!(runner
            .execute("test", query, Some(&parameters), 3.0, None, None)
            .is_err());
    }
    assert_eq!(
        runner.sqlite_path("test").unwrap_err().code,
        "SOURCE_NOT_ALLOWED"
    );
    env::remove_var("CHARTS_TEST_QUERY_URL");
    assert_eq!(
        runner
            .execute("test", "SELECT 1", None, 3.0, None, None)
            .err()
            .unwrap()
            .code,
        "INVALID_CONFIG"
    );
}
