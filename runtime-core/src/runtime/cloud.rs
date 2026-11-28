//! Durable cloud adapters. Configuration errors never fall back to local storage.
pub use super::cloud_assets::{decode_document, encode_document, CloudAssets};
pub use super::cloud_assets::{restore_file, save_file};
pub use super::cloud_data::CloudData;
use super::error::{require, Error, Result};
pub use super::shares::{version_delete_checkpoint, version_delete_preview, version_delete_status};
use postgres_native_tls::MakeTlsConnector;
use serde_json::{json, Value};
use std::{env, time::Duration};

pub fn cloud_enabled() -> Result<bool> {
    let backend = env::var("CHARTS_STORAGE_BACKEND").unwrap_or_else(|_| "local".into());
    require(
        matches!(
            backend.as_str(),
            "local" | "cloudbase" | "cloudflare" | "neon"
        ),
        "Unknown CHARTS_STORAGE_BACKEND",
        "INVALID_CONFIG",
    )?;
    Ok(matches!(backend.as_str(), "cloudbase" | "neon"))
}

#[derive(Clone)]
pub struct CloudDatabase {
    pub backend: String,
    pub function: String,
    pub url: String,
    key: String,
    database_url: String,
}

fn database_error(code: &str) -> Option<Error> {
    let status = match code {
        "NOT_FOUND" | "NO_SAVED_VERSION" => 404,
        "FORBIDDEN" => 403,
        "SHARE_EXPIRED" | "SHARE_UNAVAILABLE" => 410,
        "INVALID_BATCH" => 400,
        "REVISION_CONFLICT"
        | "ANNOTATION_CONFLICT"
        | "ALREADY_EXISTS"
        | "DATA_CONFLICT"
        | "DATA_INCOMPLETE"
        | "CHECKPOINT_IN_USE"
        | "PLAN_CHANGED"
        | "ASSET_UNAVAILABLE"
        | "REVISION_DELETED"
        | "CONFIRMATION_REQUIRED"
        | "STORAGE_MIGRATED"
        | "ANNOTATION_LIMIT" => 409,
        _ => return None,
    };
    Some(
        Error::new(
            code,
            if code == "NO_SAVED_VERSION" {
                "暂无已保存版本"
            } else {
                code
            },
        )
        .with_status(status),
    )
}

impl CloudDatabase {
    pub fn new() -> Result<Self> {
        let backend = env::var("CHARTS_DATABASE_BACKEND").unwrap_or_else(|_| {
            if env::var("CHARTS_STORAGE_BACKEND").as_deref() == Ok("neon") {
                "neon".into()
            } else {
                "cloudbase".into()
            }
        });
        require(
            matches!(backend.as_str(), "cloudbase" | "neon"),
            "Unknown CHARTS_DATABASE_BACKEND",
            "INVALID_CONFIG",
        )?;
        let mut db = Self {
            backend,
            function: "charts_runtime".into(),
            url: String::new(),
            key: String::new(),
            database_url: String::new(),
        };
        if db.backend == "neon" {
            db.database_url = env::var("DATABASE_URL").unwrap_or_default();
            require(
                !db.database_url.is_empty(),
                "Configure DATABASE_URL",
                "INVALID_CONFIG",
            )?;
        } else {
            let environment = env::var("CLOUDBASE_ENV_ID").unwrap_or_default();
            require(
                !environment.is_empty()
                    && environment
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b == b'-'),
                "Configure CLOUDBASE_ENV_ID",
                "INVALID_CONFIG",
            )?;
            db.key = env::var("CLOUDBASE_API_KEY").unwrap_or_default();
            require(
                !db.key.is_empty(),
                "Configure the server CloudBase API Key",
                "INVALID_CONFIG",
            )?;
            db.url = format!("https://{environment}.api.tcloudbasegateway.com/v1/rdb/rest/rpc");
        }
        Ok(db)
    }

    pub fn with_function(&self, function: &str) -> Result<Self> {
        require(
            matches!(
                function,
                "charts_runtime"
                    | "charts_assets"
                    | "charts_release"
                    | "charts_delete_checkpoint"
                    | "charts_data_inventory"
                    | "charts_share_annotations"
            ),
            "Unknown PostgreSQL function",
            "INVALID_CONFIG",
        )?;
        let mut database = self.clone();
        database.function = function.into();
        Ok(database)
    }

    pub fn call(&self, action: &str, project: &str, payload: &Value) -> Result<Value> {
        require(
            payload.is_object(),
            "RPC payload must be an object",
            "INVALID_ARGUMENT",
        )?;
        if self.backend == "neon" {
            return self.neon(action, project, payload);
        }
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(60))
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .map_err(|_| {
                Error::new(
                    "CLOUD_DATABASE_UNAVAILABLE",
                    "PostgreSQL gateway is unavailable; no local fallback was used",
                )
                .with_status(503)
            })?;
        let response = client
            .post(format!("{}/{}", self.url, self.function))
            .bearer_auth(&self.key)
            .json(&json!({"action":action,"project":project,"payload":payload}))
            .send()
            .map_err(|_| {
                Error::new(
                    "CLOUD_DATABASE_UNAVAILABLE",
                    "PostgreSQL gateway is unavailable; no local fallback was used",
                )
                .with_status(503)
            })?;
        let status = response.status();
        let result: Value = response.json().map_err(|_| {
            Error::new(
                "CLOUD_DATABASE_FAILED",
                "PostgreSQL gateway returned invalid JSON",
            )
            .with_status(503)
        })?;
        if !status.is_success() {
            return Err(
                database_error(result["message"].as_str().unwrap_or("")).unwrap_or_else(|| {
                    Error::new(
                        "CLOUD_DATABASE_FAILED",
                        format!("PostgreSQL gateway returned HTTP {}", status.as_u16()),
                    )
                    .with_status(503)
                }),
            );
        }
        Ok(result)
    }

    fn neon(&self, action: &str, project: &str, payload: &Value) -> Result<Value> {
        let connector = native_tls::TlsConnector::new().map_err(|_| {
            Error::new(
                "CLOUD_DATABASE_UNAVAILABLE",
                "Cannot initialize PostgreSQL TLS",
            )
            .with_status(503)
        })?;
        let mut config: postgres::Config = self
            .database_url
            .parse()
            .map_err(|_| Error::new("INVALID_CONFIG", "Invalid DATABASE_URL"))?;
        config.connect_timeout(Duration::from_secs(60));
        let map_error = |error: postgres::Error| {
            error
                .as_db_error()
                .and_then(|e| database_error(e.message()))
                .unwrap_or_else(|| {
                    Error::new(
                        "CLOUD_DATABASE_FAILED",
                        "PostgreSQL request failed; no local fallback was used",
                    )
                    .with_status(503)
                })
        };
        let mut client = config
            .connect(MakeTlsConnector::new(connector))
            .map_err(map_error)?;
        let templates: Value =
            serde_json::from_str(include_str!("../../resources/cloud-sql.json"))?;
        let board = json!({"board": payload["board"]});
        let row = if self.function == "charts_runtime" {
            match action {
                "annotation_read" => client.query_one(templates["_ANNOTATION_READ"].as_str().unwrap(), &[&project, &board, &payload["includeTargets"].as_bool().unwrap_or(false)]),
                "annotation_write" => {
                    let args = json!({"board":payload["board"],"expected":payload["expected"],"previousNotes":payload["previousNotes"],"at":payload["at"]});
                    client.query_one(templates["_ANNOTATION_WRITE"].as_str().unwrap(), &[&project,&board,&project,&args,&payload["notes"]])
                }
                "annotation_append" => {
                    let mut transaction = client.transaction().map_err(map_error)?;
                    transaction.query_one("SELECT pg_advisory_xact_lock(hashtextextended('charts:' || $1, 0))", &[&project]).map_err(map_error)?;
                    let note = &payload["note"];
                    let component = if note.get("anchor").is_none() { note["componentId"].as_str() } else { None };
                    let at = payload["at"].as_str().unwrap_or("");
                    let row = transaction.query_one(templates["_ANNOTATION_APPEND"].as_str().unwrap(), &[&project,&board,note,&at,&component]).map_err(map_error)?;
                    transaction.commit().map_err(map_error)?;
                    return row.try_get(0).map_err(map_error);
                }
                "display_revision" => client.query_one("SELECT public.charts_runtime('readable', $1, $2)->'revision'", &[&project,&board]),
                "generations_match" => {
                    let row = client.query_one("SELECT NOT EXISTS (SELECT FROM jsonb_each($1) AS page(board,generation) WHERE page.generation IS DISTINCT FROM public.charts_runtime('generation',$2,jsonb_build_object('board',page.board)))", &[&payload["pages"],&project]).map_err(map_error)?;
                    return Ok(json!(row.get::<_, bool>(0)));
                }
                _ => client.query_one("SELECT public.charts_runtime($1,$2,$3)", &[&action,&project,payload]),
            }
        } else {
            client.query_one(&format!("SELECT public.{}($1,$2,$3)", self.function), &[&action,&project,payload])
        }.map_err(map_error)?;
        row.try_get(0).map_err(map_error)
    }
}

/// External storage and publication operations keep one dispatch path.
pub fn call(
    service: &super::service::Service,
    tool: &str,
    args: &serde_json::Value,
) -> Result<serde_json::Value> {
    use super::service::{integer, string};
    super::contract::validate_args(tool, args)?;
    if tool.starts_with("dataset_") {
        return super::transfer::call(service, tool, args);
    }
    let shares = super::local_shares::LocalShares::new(service)?;
    let board = string(args, "dashboardId")?;
    match tool {
        "dashboard_share_publish" => shares.publish(
            board,
            integer(args, "revision")?,
            args["expiration"].as_str().unwrap_or("7d"),
            args["annotationMode"].as_str().unwrap_or("view"),
            string(args, "requestId")?,
        ),
        "dashboard_share_replace" => shares.replace(
            board,
            string(args, "shareId")?,
            integer(args, "expectedRevision")?,
            args["expiration"].as_str().unwrap_or("7d"),
        ),
        "dashboard_share_status" => shares.status(board, args["shareId"].as_str()),
        "dashboard_share_delete" => shares.revoke(board, string(args, "shareId")?),
        _ => Err(Error::new("UNKNOWN_TOOL", "Unknown cloud operation")),
    }
}
