//! Deployment operations use the same native storage and validation code.
use super::{
    assets,
    cloud::{self, CloudAssets},
    error::{require, Error, Result},
    object_storage::Storage,
    serialization::{canonical_json, json_bytes},
    shares,
    store::Store,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs,
    io::Read,
    path::Path,
    sync::Arc,
    time::{Duration, Instant},
};

pub fn cleanup() -> Result<Value> {
    let storage = Storage::publication()?;
    let mut result = shares::cleanup_due(&storage, None)?;
    if cloud::cloud_enabled()?
        || (std::env::var("CHARTS_STORAGE_BACKEND").as_deref() != Ok("cloudflare")
            && std::env::var("CLOUDBASE_API_KEY").is_ok_and(|value| !value.is_empty()))
    {
        let assets = shares::cleanup_asset_jobs()?;
        result["removed"] = json!(
            result["removed"].as_u64().unwrap_or(0) + assets["removed"].as_u64().unwrap_or(0)
        );
        if let Some(failed) = assets["failed"].as_array() {
            result["failed"]
                .as_array_mut()
                .ok_or_else(|| Error::new("CLEANUP_FAILED", "Invalid cleanup result"))?
                .extend(failed.iter().cloned());
        }
    }
    require(
        result["failed"].as_array().is_some_and(Vec::is_empty),
        "Cloud share cleanup failed; jobs retained for retry",
        "CLEANUP_FAILED",
    )?;
    storage.put(
        "cleaner-status.json",
        &serde_json::to_vec(
            &json!({"executor":storage.executor(),"completedAt":chrono::Utc::now().timestamp()}),
        )?,
        "application/json",
    )?;
    Ok(result)
}

pub fn healthcheck(wait: f64) -> Result<Value> {
    require(
        wait.is_finite() && (0.0..=300.0).contains(&wait),
        "wait-seconds must be from 0 to 300",
        "INVALID_ARGUMENT",
    )?;
    let port = std::env::var("CHARTS_PORT")
        .unwrap_or_else(|_| "8000".into())
        .parse::<u16>()
        .map_err(|_| Error::new("INVALID_CONFIG", "Invalid health port"))?;
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(4))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| Error::new("HEALTHCHECK_FAILED", "Cannot initialize health client"))?;
    let started = Instant::now();
    loop {
        if let Ok(response) = client.get(format!("http://127.0.0.1:{port}/health")).send() {
            if response.status().is_success() {
                if let Ok(value) = response.json::<Value>() {
                    if value["ok"] == true {
                        return Ok(value);
                    }
                }
            }
        }
        if started.elapsed().as_secs_f64() >= wait {
            return Err(Error::new(
                "HEALTHCHECK_FAILED",
                "Runtime health check failed",
            ));
        }
        std::thread::sleep(Duration::from_millis(250));
    }
}
pub fn cleanup_server() -> Result<()> {
    require(
        std::env::var("TENCENTCLOUD_RUNENV").as_deref() == Ok("SCF"),
        "cleanup-server is a Tencent SCF event function",
        "INVALID_CONFIG",
    )?;
    let runtime = tokio::runtime::Runtime::new()?;
    runtime.block_on(async {
        async fn invoke() -> axum::response::Response {
            use axum::response::IntoResponse;
            static LOCK: tokio::sync::Mutex<()> = tokio::sync::Mutex::const_new(());
            let _guard = LOCK.lock().await;
            match tokio::task::spawn_blocking(cleanup).await {
                Ok(Ok(value)) => axum::Json(value).into_response(),
                Ok(Err(error)) => (
                    axum::http::StatusCode::INTERNAL_SERVER_ERROR,
                    axum::Json(error.json()),
                )
                    .into_response(),
                Err(_) => (
                    axum::http::StatusCode::INTERNAL_SERVER_ERROR,
                    axum::Json(
                        Error::new("CLEANUP_FAILED", "Cleanup worker failed; retry is safe").json(),
                    ),
                )
                    .into_response(),
            }
        }
        let app = axum::Router::new()
            .route(
                "/health",
                axum::routing::get(|| async {
                    axum::Json(
                        json!({"ok":true,"role":"cleanup","version":env!("CARGO_PKG_VERSION")}),
                    )
                }),
            )
            .route("/event-invoke", axum::routing::post(invoke))
            .layer(axum::extract::DefaultBodyLimit::max(64 * 1024));
        let listener = tokio::net::TcpListener::bind("0.0.0.0:9000").await?;
        axum::serve(listener, app)
            .with_graceful_shutdown(async {
                let _ = tokio::signal::ctrl_c().await;
            })
            .await
            .map_err(Error::from)
    })
}
pub fn adapt_migration(source: &str, role: &str) -> Result<String> {
    let valid = role.len() <= 63
        && !role.is_empty()
        && role
            .bytes()
            .enumerate()
            .all(|(i, b)| b == b'_' || b.is_ascii_lowercase() || (i > 0 && b.is_ascii_digit()));
    require(
        valid
            && !['\0'].iter().any(|c| role.contains(*c))
            && !["public", "anon", "authenticated", "service_role"].contains(&role),
        "CHARTS_NEON_RUNTIME_ROLE must name a separate PostgreSQL login role",
        "INVALID_CONFIG",
    )?;
    let source = source.replace(
        "auth.role() IS DISTINCT FROM 'service_role'",
        &format!("session_user IS DISTINCT FROM '{role}'"),
    );
    let removed = regex::Regex::new(r",\s*anon,\s*authenticated")
        .unwrap()
        .replace_all(&source, "");
    Ok(regex::Regex::new(r"\bservice_role\b")
        .unwrap()
        .replace_all(&removed, role)
        .into_owned())
}
pub fn migrate_neon() -> Result<Value> {
    let role = std::env::var("CHARTS_NEON_RUNTIME_ROLE")
        .map_err(|_| Error::new("INVALID_CONFIG", "Set CHARTS_NEON_RUNTIME_ROLE"))?;
    adapt_migration("", &role)?;
    let dsn = std::env::var("DATABASE_URL").map_err(|_| {
        Error::new(
            "INVALID_CONFIG",
            "Set DATABASE_URL to the migration owner connection",
        )
    })?;
    let config: postgres::Config = dsn
        .parse()
        .map_err(|_| Error::new("INVALID_CONFIG", "Invalid migration connection"))?;
    let tls = postgres_native_tls::MakeTlsConnector::new(
        native_tls::TlsConnector::new()
            .map_err(|_| Error::new("TLS_FAILED", "Cannot configure TLS"))?,
    );
    let mut client = config.connect(tls).map_err(|_| {
        Error::new(
            "DATABASE_UNAVAILABLE",
            "Cannot connect to migration database",
        )
    })?;
    let mut tx = client
        .transaction()
        .map_err(|_| Error::new("MIGRATION_FAILED", "Cannot begin migration"))?;
    let failed = |_: postgres::Error| {
        Error::new(
            "MIGRATION_FAILED",
            "Database migration failed; transaction rolled back",
        )
    };
    tx.batch_execute("SELECT pg_advisory_xact_lock(hashtextextended('charts:neon:migrations', 0))")
        .map_err(failed)?;
    let info=tx.query_opt("SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,pg_has_role($1,current_user,'MEMBER'),current_user=$1 FROM pg_roles WHERE rolname=$1",&[&role]).map_err(failed)?;
    require(
        info.is_some_and(|row| row.get::<_, bool>(0) && (1..6).all(|i| !row.get::<_, bool>(i))),
        "Runtime role must be an existing unprivileged login, separate from the migration owner",
        "INVALID_CONFIG",
    )?;
    tx.batch_execute("CREATE SCHEMA IF NOT EXISTS charts; REVOKE ALL ON SCHEMA charts FROM PUBLIC; CREATE TABLE IF NOT EXISTS charts.neon_migrations(name text PRIMARY KEY,digest text NOT NULL,runtime_role text NOT NULL); REVOKE ALL ON charts.neon_migrations FROM PUBLIC").map_err(failed)?;
    let applied: BTreeMap<String, (String, String)> = tx
        .query(
            "SELECT name,digest,runtime_role FROM charts.neon_migrations",
            &[],
        )
        .map_err(failed)?
        .into_iter()
        .map(|row| (row.get(0), (row.get(1), row.get(2))))
        .collect();
    let mut files: BTreeMap<String, String> = BTreeMap::new();
    for entry in fs::read_dir(assets::package_root().join("cloudbase/migrations"))? {
        let path = entry?.path();
        if path.extension().is_some_and(|v| v == "sql") {
            files.insert(
                path.file_name().unwrap().to_string_lossy().into_owned(),
                fs::read_to_string(path)?,
            );
        }
    }
    require(
        !files.is_empty() && applied.keys().all(|name| files.contains_key(name)),
        "Migration files do not match applied history",
        "MIGRATION_CONFLICT",
    )?;
    let mut count = 0;
    for (name, source) in files {
        let digest = hex::encode(Sha256::digest(source.as_bytes()));
        if let Some(previous) = applied.get(&name) {
            require(
                previous == &(digest, role.clone()),
                format!("Migration or runtime role changed: {name}"),
                "MIGRATION_CONFLICT",
            )?;
            continue;
        }
        tx.batch_execute(&adapt_migration(&source, &role)?)
            .map_err(failed)?;
        tx.execute(
            "INSERT INTO charts.neon_migrations VALUES($1,$2,$3)",
            &[&name, &digest, &role],
        )
        .map_err(failed)?;
        count += 1;
    }
    tx.batch_execute("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA charts FROM PUBLIC")
        .map_err(failed)?;
    tx.commit().map_err(failed)?;
    Ok(json!({"ok":true,"applied":count,"runtimeRole":role}))
}
fn migration_identity(snapshot: &Value) -> Result<String> {
    let mut documents = snapshot["documents"]
        .as_array()
        .cloned()
        .unwrap_or_default();
    let mut datasets = snapshot["datasets"].as_array().cloned().unwrap_or_default();
    documents.sort_by_cached_key(|doc| {
        (
            doc["source"].to_string(),
            doc["board"].to_string(),
            doc["revision"].as_i64().unwrap_or(0),
            canonical_json(&doc["document"]).unwrap_or_default(),
        )
    });
    datasets.sort_by_cached_key(|doc| doc["version"].to_string());
    canonical_json(&json!({"documents":documents,"datasets":datasets}))
}
fn verify_dataset(assets: &CloudAssets, object: &Value, reference: &Value) -> Result<()> {
    let descriptor = &object["descriptor"];
    require(
        descriptor["metadata"] == *reference,
        "Dataset metadata changed",
        "DATA_CONFLICT",
    )?;
    let temporary = tempfile::tempdir()?;
    let target = temporary.path().join("read-back.parquet");
    let mut count = 0;
    let fields = reference["fieldOrder"].clone();
    let inspect = |name: &str, fields: &Value| -> Result<u64> {
        assets.download_file(object, name, &target)?;
        let result = super::deployment::inspect_parquet(&target)?;
        require(
            result["fieldOrder"] == *fields,
            "Uploaded dataset fields differ",
            "DATA_CONFLICT",
        )?;
        Ok(result["rowCount"].as_u64().unwrap_or(0))
    };
    for name in descriptor["shards"].as_array().into_iter().flatten() {
        let name = name
            .as_str()
            .ok_or_else(|| Error::new("DATA_CONFLICT", "Invalid shard"))?;
        if name.ends_with(".parquet") {
            count += inspect(name, &fields)?;
        } else {
            let compressed = temporary.path().join("read-back.json.gz");
            assets.download_file(object, name, &compressed)?;
            let mut output = Vec::new();
            flate2::read::GzDecoder::new(fs::File::open(&compressed)?)
                .take(64 * 1024 * 1024 + 1)
                .read_to_end(&mut output)?;
            require(
                output.len() <= 64 * 1024 * 1024,
                "Decoded data shard exceeds 64 MiB",
                "DATA_CONFLICT",
            )?;
            let value: Value = serde_json::from_slice(&output)?;
            count += value
                .as_array()
                .or_else(|| value["rows"].as_array())
                .ok_or_else(|| Error::new("DATA_CONFLICT", "Invalid data shard"))?
                .len() as u64;
        }
    }
    require(
        reference["rowCount"].as_u64() == Some(count),
        "Uploaded dataset row count differs",
        "DATA_INCOMPLETE",
    )?;
    for entry in descriptor["options"]
        .as_object()
        .into_iter()
        .flatten()
        .map(|(_, v)| v)
    {
        if let Some(name) = entry.as_str() {
            assets.download_file(object, name, &temporary.path().join("read-back-options"))?;
        } else {
            for file in entry["files"].as_array().into_iter().flatten() {
                inspect(
                    file.as_str()
                        .ok_or_else(|| Error::new("DATA_CONFLICT", "Invalid option file"))?,
                    &json!([entry["field"]]),
                )?;
            }
        }
    }
    assets.download_file(
        object,
        "query.sqlite3",
        &temporary.path().join("query.sqlite3"),
    )?;
    Ok(())
}
pub fn migrate_cos(
    project: &str,
    workspace: &Path,
    apply: bool,
    partition_fields: &[String],
) -> Result<Value> {
    require(
        !project.is_empty()
            && project.len() <= 64
            && project
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-'),
        "Invalid project",
        "INVALID_ARGUMENT",
    )?;
    let assets = CloudAssets::new(project)?;
    let original = assets.call("migration_snapshot", &json!({}))?;
    let mut result = json!({"project":project,"format":original["format"],"datasets":original["datasets"].as_array().map_or(0,Vec::len),"documents":original["documents"].as_array().into_iter().flatten().filter(|d|matches!(d["source"].as_str(),Some("draft"|"checkpoint"|"release"))).count(),"logicalBytes":original["datasets"].as_array().into_iter().flatten().map(|d|d["bytes"].as_u64().unwrap_or(0)).sum::<u64>(),"unfinishedChunks":original["unfinishedChunks"],"action":if original["format"]=="cos-v1"{"already_migrated"}else{"plan"}});
    if !apply || original["format"] == "cos-v1" {
        return Ok(result);
    }
    require(
        original["unfinishedChunks"] == 0,
        "Recover or explicitly clean unfinished transfers before migration",
        "DATA_INCOMPLETE",
    )?;
    let temporary = tempfile::tempdir()?;
    let mut store = Store::new(temporary.path(), Some(&workspace.join(project)))?;
    store.data.set_partition_fields(partition_fields)?;
    for reference in original["datasets"].as_array().into_iter().flatten() {
        let mut object = assets.call("object_get", &json!({"version":reference["version"]}))?;
        if object.is_null() {
            store
                .data
                .describe(super::service::string(reference, "version")?)?;
            object = assets.save_dataset(
                &store.data,
                reference,
                partition_fields
                    .iter()
                    .find(|f| reference["fields"].get(f.as_str()).is_some())
                    .map(String::as_str),
            )?;
        }
        verify_dataset(&assets, &object, reference)?;
    }
    store.cos_enabled = true;
    if let Some(cloud) = &mut store.data.cloud {
        Arc::make_mut(cloud).cos_enabled = true;
    }
    let mut documents = Vec::new();
    let mut content = BTreeMap::new();
    for entry in original["documents"].as_array().into_iter().flatten() {
        if !matches!(
            entry["source"].as_str(),
            Some("draft" | "checkpoint" | "release")
        ) {
            continue;
        }
        let doc = store.compact(&assets.hydrate_document(&entry["document"])?)?;
        let digest = hex::encode(Sha256::digest(json_bytes(&doc)?));
        if !content.contains_key(&digest) {
            let encoded = store.encode(&doc, None)?;
            let restored = assets.hydrate_document(&encoded)?;
            require(
                restored["manifest"] == doc["manifest"] && restored["snapshot"] == doc["snapshot"],
                "Uploaded version differs",
                "DATA_CONFLICT",
            )?;
            content.insert(digest.clone(), encoded);
        }
        let mut entry = entry.clone();
        entry["document"] = content[&digest].clone();
        documents.push(entry);
    }
    shares::CloudShares::from_environment(None)?.index_project(&store)?;
    let latest = assets.call("migration_snapshot", &json!({}))?;
    require(
        migration_identity(&original)? == migration_identity(&latest)?,
        "Project changed while migrating; source data retained",
        "PLAN_CHANGED",
    )?;
    let switched = assets.call(
        "migration_commit",
        &json!({"epoch":latest["epoch"],"documents":documents,"partitionFields":partition_fields}),
    )?;
    if let Some(fields) = switched.as_object() {
        result.as_object_mut().unwrap().extend(fields.clone());
    }
    result["action"] = json!("migrated");
    Ok(result)
}
pub fn run(args: &[String]) -> Option<Result<()>> {
    let name = args.first()?.as_str();
    if ![
        "cleanup",
        "cleanup-server",
        "healthcheck",
        "migrate-neon",
        "migrate-cos",
    ]
    .contains(&name)
    {
        return None;
    }
    Some((|| {
        let result = match name {
            "cleanup" => {
                require(
                    args.len() == 1,
                    "cleanup takes no arguments",
                    "INVALID_ARGUMENT",
                )?;
                cleanup()?
            }
            "cleanup-server" => {
                require(
                    args.len() == 1,
                    "cleanup-server takes no arguments",
                    "INVALID_ARGUMENT",
                )?;
                cleanup_server()?;
                return Ok(());
            }
            "healthcheck" => {
                let wait = if args.len() == 1 {
                    0.0
                } else {
                    require(
                        args.len() == 3 && args[1] == "--wait-seconds",
                        "Use healthcheck [--wait-seconds N]",
                        "INVALID_ARGUMENT",
                    )?;
                    args[2]
                        .parse::<f64>()
                        .map_err(|_| Error::new("INVALID_ARGUMENT", "Invalid wait duration"))?
                };
                healthcheck(wait)?
            }
            "migrate-neon" => {
                require(
                    args.len() == 1,
                    "migrate-neon takes configuration from environment",
                    "INVALID_ARGUMENT",
                )?;
                migrate_neon()?
            }
            _ => {
                let mut project = None;
                let mut workspace = None;
                let mut fields = Vec::new();
                let mut apply = false;
                let mut iter = args[1..].iter();
                while let Some(flag) = iter.next() {
                    if flag == "--apply" {
                        require(!apply, "Duplicate --apply", "INVALID_ARGUMENT")?;
                        apply = true;
                        continue;
                    }
                    let value = iter.next().ok_or_else(|| {
                        Error::new("INVALID_ARGUMENT", "Missing migration argument")
                    })?;
                    match flag.as_str() {
                        "--project" => project = Some(value.as_str()),
                        "--workspace" => workspace = Some(value.as_str()),
                        "--partition-field" => fields.push(value.clone()),
                        _ => {
                            return Err(Error::new(
                                "INVALID_ARGUMENT",
                                "Unknown migration argument",
                            ))
                        }
                    }
                }
                migrate_cos(
                    project
                        .ok_or_else(|| Error::new("INVALID_ARGUMENT", "--project is required"))?,
                    Path::new(workspace.ok_or_else(|| {
                        Error::new("INVALID_ARGUMENT", "--workspace is required")
                    })?),
                    apply,
                    &fields,
                )?
            }
        };
        println!("{}", serde_json::to_string(&result)?);
        Ok(())
    })())
}

#[cfg(test)]
#[path = "../../tests/unit/operations.rs"]
mod tests;
