//! Fixed-version publication through a configured service, with durable retry identity.
//! Bearer credentials stay in this process; only the saved ZIP is uploaded.
use super::{
    error::{require, Error, Result},
    serialization::json_bytes,
    service::Service,
    shares::{checked_annotation_mode, checked_id},
    versions::Versions,
};
use fs2::FileExt;
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    env,
    fs::{self, File, OpenOptions},
    io::Read,
    path::{Path, PathBuf},
    time::Duration,
};
use url::Url;
use uuid::Uuid;

pub struct LocalShares<'a> {
    pub service: &'a Service,
    pub url: String,
    token: String,
    pub project: String,
    pub root: PathBuf,
    pub path: PathBuf,
    pub source: String,
    parquet_layout: String,
}
impl<'a> LocalShares<'a> {
    pub fn new(service: &'a Service) -> Result<Self> {
        let project_root = service
            .project_root
            .as_deref()
            .ok_or_else(|| Error::new("PROJECT_REQUIRED", "A workspace project is required"))?;
        let url = env::var("CHARTS_SHARE_SERVICE_URL")
            .unwrap_or_default()
            .trim_end_matches('/')
            .to_owned();
        require(
            !url.is_empty(),
            "Configure CHARTS_SHARE_SERVICE_URL on the author workspace",
            "CLOUD_SHARE_NOT_CONFIGURED",
        )?;
        require(
            service
                .store
                .database
                .as_ref()
                .is_none_or(|db| db.backend != "cloudbase"),
            "Use a local or self-hosted workspace to publish a new share",
            "INVALID_CONFIG",
        )?;
        let token = env::var("CHARTS_SHARE_SERVICE_TOKEN").unwrap_or_default();
        let project = env::var("CHARTS_SHARE_SERVICE_PROJECT").unwrap_or_else(|_| "default".into());
        let parquet_layout =
            env::var("CHARTS_SHARE_PARQUET_LAYOUT").unwrap_or_else(|_| "sharded".into());
        require(
            matches!(parquet_layout.as_str(), "sharded" | "single"),
            "CHARTS_SHARE_PARQUET_LAYOUT must be sharded or single",
            "INVALID_CONFIG",
        )?;
        validate_service_url(&url)?;
        require(
            !token.is_empty() && !token.contains(['\r', '\n']),
            "Configure CHARTS_SHARE_SERVICE_TOKEN in the local server environment",
            "INVALID_CONFIG",
        )?;
        require(
            (1..=64).contains(&project.len())
                && project
                    .bytes()
                    .next()
                    .is_some_and(|b| b.is_ascii_alphanumeric())
                && project
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-'),
            "CHARTS_SHARE_SERVICE_PROJECT must name the authorized destination project",
            "INVALID_CONFIG",
        )?;
        let root = project_root.canonicalize()?.join("dashboards");
        fs::create_dir_all(&root)?;
        let path = root.join("share-references.sqlite3");
        let mut value = Self {
            service,
            url,
            token,
            project,
            root,
            path,
            source: String::new(),
            parquet_layout,
        };
        let db = value.connect()?;
        db.execute_batch("CREATE TABLE IF NOT EXISTS identity(id INTEGER PRIMARY KEY CHECK(id=1),source TEXT NOT NULL);CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,board TEXT NOT NULL,fingerprint TEXT NOT NULL,revision INTEGER NOT NULL,service_url TEXT NOT NULL,project TEXT NOT NULL,archive TEXT,archive_sha TEXT,receipt TEXT,state TEXT NOT NULL,created_at REAL NOT NULL);CREATE INDEX IF NOT EXISTS requests_board ON requests(board,created_at);")?;
        db.execute(
            "INSERT OR IGNORE INTO identity VALUES(1,?)",
            [Uuid::new_v4().to_string()],
        )?;
        value.source = db.query_row("SELECT source FROM identity WHERE id=1", [], |row| {
            row.get(0)
        })?;
        super::exports::private_file(&value.path)?;
        Ok(value)
    }
    fn connect(&self) -> Result<Connection> {
        let db = Connection::open(&self.path)?;
        db.busy_timeout(Duration::from_secs(10))?;
        Ok(db)
    }
    fn request(
        &self,
        method: &str,
        path: &str,
        headers: &[(&str, &str)],
        archive: Option<&Path>,
    ) -> Result<Value> {
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(120))
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .map_err(|_| unavailable())?;
        let method = reqwest::Method::from_bytes(method.as_bytes())
            .map_err(|_| Error::new("INVALID_ARGUMENT", "Invalid publication method"))?;
        let mut request = client
            .request(method, format!("{}{path}", self.url))
            .bearer_auth(&self.token)
            .header(
                "User-Agent",
                concat!("Charts-Design-Publisher/", env!("CARGO_PKG_VERSION")),
            );
        for (name, value) in headers {
            request = request.header(*name, *value);
        }
        if let Some(archive) = archive {
            let file = File::open(archive).map_err(|_| unavailable())?;
            let size = file.metadata().map_err(|_| unavailable())?.len();
            request = request
                .header(reqwest::header::CONTENT_LENGTH, size)
                .body(reqwest::blocking::Body::new(file));
        }
        let response = request.send().map_err(|_| unavailable())?;
        let status = response.status();
        let limit = if status.is_success() {
            16 * 1024 * 1024
        } else {
            1024 * 1024
        };
        let mut raw = Vec::new();
        response
            .take(limit + 1)
            .read_to_end(&mut raw)
            .map_err(|_| unavailable())?;
        if !status.is_success() {
            let details = serde_json::from_slice::<Value>(&raw).unwrap_or(Value::Null);
            let error = &details["error"];
            return Err(Error::new(
                error["code"]
                    .as_str()
                    .filter(|s| !s.is_empty())
                    .unwrap_or("SHARE_SERVICE_FAILED"),
                error["message"]
                    .as_str()
                    .filter(|s| !s.is_empty())
                    .unwrap_or("Share service rejected the request"),
            )
            .with_status(status.as_u16()));
        }
        require(
            raw.len() as u64 <= limit,
            "Share service returned too much data",
            "PAYLOAD_TOO_LARGE",
        )?;
        let value: Value = serde_json::from_slice(&raw).map_err(|_| unavailable())?;
        require(
            value.is_object() && value["ok"] != false,
            "Share service did not confirm the request",
            "SHARE_SERVICE_FAILED",
        )?;
        Ok(value)
    }
    fn with_lock<T>(&self, id: &str, operation: impl FnOnce() -> Result<T>) -> Result<T> {
        let root = self.root.join(".share-locks");
        fs::create_dir_all(&root)?;
        let lock = OpenOptions::new()
            .create(true)
            .read(true)
            .write(true)
            .truncate(false)
            .open(root.join(format!("{id}.lock")))?;
        lock.lock_exclusive()?;
        let result = operation();
        FileExt::unlock(&lock)?;
        result
    }
    fn row(db: &Connection, id: &str) -> Result<Option<Value>> {
        Ok(db.query_row("SELECT id,board,fingerprint,revision,service_url,project,archive,archive_sha,receipt,state,created_at FROM requests WHERE id=?",[id],request_row).optional()?)
    }
    fn reference(&self, board: &str, share: &str) -> Result<(Value, Value)> {
        super::model::check_identifier(board)?;
        checked_id(share)?;
        let db = self.connect()?;
        let mut statement=db.prepare("SELECT id,board,fingerprint,revision,service_url,project,archive,archive_sha,receipt,state,created_at FROM requests WHERE board=? AND receipt IS NOT NULL")?;
        let rows = statement
            .query_map([board], request_row)?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        for row in rows {
            let receipt: Value = serde_json::from_str(row["receipt"].as_str().unwrap_or(""))?;
            if receipt["shareId"] == share {
                require(
                    row["service_url"] == self.url && row["project"] == self.project,
                    "Configure the original share service to access this publication",
                    "SHARE_SERVICE_MISMATCH",
                )?;
                return Ok((row, receipt));
            }
        }
        Err(Error::new(
            "FORBIDDEN",
            "This share does not belong to this local project and dashboard",
        )
        .with_status(403))
    }
    fn owner_path(&self, board: &str, share: &str) -> String {
        let query = url::form_urlencoded::Serializer::new(String::new())
            .append_pair("source", &self.source)
            .append_pair("project", &self.project)
            .append_pair("dashboardId", board)
            .finish();
        format!("/api/v1/publications/{share}?{query}")
    }
    pub fn publish(
        &self,
        board: &str,
        revision: i64,
        expiration: &str,
        mode: &str,
        request_id: &str,
    ) -> Result<Value> {
        super::model::check_identifier(board)?;
        require(revision > 0, "Choose a saved revision", "INVALID_ARGUMENT")?;
        let id = Uuid::parse_str(request_id).map_err(|_| {
            Error::new(
                "INVALID_ARGUMENT",
                "Use a stable UUID v4 requestId when retrying",
            )
        })?;
        require(
            id.get_version_num() == 4
                && id.get_variant() == uuid::Variant::RFC4122
                && id.to_string() == request_id,
            "Use a stable UUID v4 requestId when retrying",
            "INVALID_ARGUMENT",
        )?;
        require(
            matches!(expiration, "never" | "7d" | "30d"),
            "Invalid share options",
            "INVALID_ARGUMENT",
        )?;
        checked_annotation_mode(mode)?;
        let versions = Versions::new(&self.service.store)?;
        let fingerprint = hex::encode(Sha256::digest(json_bytes(&json!([
            board,
            revision,
            null,
            expiration,
            mode,
            self.url,
            self.project
        ]))?));
        self.with_lock(request_id,||{let db=self.connect()?;let mut row=Self::row(&db,request_id)?;drop(db);if let Some(previous)=&row{require(previous["fingerprint"]==fingerprint,"This request ID was used for different share options","IDEMPOTENCY_CONFLICT")?;if let Some(receipt)=previous["receipt"].as_str(){let receipt:Value=serde_json::from_str(receipt)?;self.feedback(board,super::service::string(&receipt,"shareId")?)?;return Ok(receipt);}}else{let doc=versions.read(board,revision)?;require(super::model::live_datasets(&doc).as_object().is_none_or(|m|m.is_empty()),"实时 SQL 看板请通过运行服务查看","LIVE_DATA_REQUIRES_RUNTIME")?;require(self.service.doctor(&doc,"full",true)?["passed"]==true,"Saved version checks failed.","DOCTOR_FAILED")?;let db=self.connect()?;db.execute("INSERT INTO requests(id,board,fingerprint,revision,service_url,project,state,created_at) VALUES(?,?,?,?,?,?,?,?)",params![request_id,board,fingerprint,revision,self.url,self.project,"uploading",chrono::Utc::now().timestamp_millis()as f64/1000.0])?;row=Self::row(&db,request_id)?;}let row=row.ok_or_else(||Error::new("SHARE_SERVICE_FAILED","Publication retry record is missing"))?;
            let archive=if let Some(path)=row["archive"].as_str(){let path=PathBuf::from(path);require(path.is_file()&&checksum(&path).ok().as_deref()==row["archive_sha"].as_str(),"The pending publication copy is missing or changed; inspect the existing request before creating another share","SHARE_RETRY_ASSET_MISSING")?;path}else{let exported=super::deployment::export_site(&self.service.store,board,None,Some(&versions.read(board,revision)?),"parquet",self.parquet_layout=="single")?;let archive=PathBuf::from(super::service::string(&exported["export"],"path")?);self.connect()?.execute("UPDATE requests SET archive=?,archive_sha=? WHERE id=?",params![archive.to_string_lossy(),checksum(&archive)?,request_id])?;archive};
            let receipt=self.request("POST","/api/v1/publications",&[("Content-Type","application/zip"),("X-Charts-Source",&self.source),("X-Charts-Project",&self.project),("X-Charts-Request",request_id),("X-Charts-Expiration",expiration),("X-Charts-Annotation-Mode",mode)],Some(&archive))?;let valid_share=receipt["shareId"].as_str().is_some_and(|id|checked_id(id).is_ok());let valid_key=receipt["accessKey"].as_str().is_some_and(|key|key.len()==8&&key.bytes().all(|b|b.is_ascii_digit()));require(valid_share&&valid_key&&receipt["url"].as_str().is_some_and(|s|!s.is_empty())&&receipt["revision"]==revision&&receipt.get("annotationMode").and_then(Value::as_str).unwrap_or("view")==mode,"Share service returned a different publication","SHARE_SERVICE_FAILED")?;self.connect()?.execute("UPDATE requests SET receipt=?,state=? WHERE id=?",params![serde_json::to_string(&receipt)?,"active",request_id])?;Ok(receipt)})
    }
    pub fn feedback(&self, board: &str, share: &str) -> Result<Value> {
        let (_, receipt) = self.reference(board, share)?;
        let result = self.request("GET", &self.owner_path(board, share), &[], None)?;
        require(
            result["shareId"] == share && result["revision"] == receipt["revision"],
            "Feedback belongs to another publication",
            "SHARE_SERVICE_FAILED",
        )?;
        Ok(result)
    }
    pub fn status(&self, board: &str, share: Option<&str>) -> Result<Value> {
        super::model::check_identifier(board)?;
        if let Some(share) = share {
            checked_id(share)?;
        }
        let db = self.connect()?;
        let mut statement=db.prepare("SELECT id,board,fingerprint,revision,service_url,project,archive,archive_sha,receipt,state,created_at FROM requests WHERE board=? AND receipt IS NOT NULL ORDER BY created_at DESC")?;
        let rows = statement
            .query_map([board], request_row)?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        let mut statement=db.prepare("SELECT id,revision,state FROM requests WHERE board=? AND receipt IS NULL ORDER BY created_at DESC")?;
        let pending=statement.query_map([board],|r|Ok(json!({"requestId":r.get::<_,String>(0)?,"revision":r.get::<_,i64>(1)?,"state":r.get::<_,String>(2)?})))?.collect::<std::result::Result<Vec<_>,_>>()?;
        let mut shares = vec![];
        for row in rows {
            let receipt: Value = serde_json::from_str(row["receipt"].as_str().unwrap_or(""))?;
            if share.is_some_and(|share| receipt["shareId"] != share) {
                continue;
            }
            let due = receipt["expiresAt"]
                .as_f64()
                .is_some_and(|at| super::shares::now() as f64 >= at);
            let mut result = json!({});
            for key in [
                "shareId",
                "url",
                "revision",
                "expiresAt",
                "pages",
                "annotationMode",
            ] {
                if let Some(value) = receipt.get(key) {
                    result[key] = value.clone();
                }
            }
            result["state"] = if due && row["state"] == "active" {
                json!("expired")
            } else {
                row["state"].clone()
            };
            result["cleanupState"] = if due || row["state"] == "revoked" {
                receipt["cleanup"]
                    .get("cleanupState")
                    .cloned()
                    .unwrap_or(json!("pending"))
            } else {
                json!(if receipt["expiresAt"].is_null() {
                    "not_scheduled"
                } else {
                    "scheduled"
                })
            };
            let query = url::form_urlencoded::Serializer::new(String::new())
                .append_pair("dashboardId", board)
                .finish();
            result["feedbackEndpoint"] = json!(format!(
                "/api/publications/{}/feedback?{query}",
                super::service::string(&receipt, "shareId")?
            ));
            result["localReference"] = json!(true);
            shares.push(result);
        }
        Ok(json!({"shares":shares,"pendingRequests":pending,"cleanupExecutor":"share-service"}))
    }
    pub fn revoke(&self, board: &str, share: &str) -> Result<Value> {
        let (row, _) = self.reference(board, share)?;
        let id = super::service::string(&row, "id")?.to_owned();
        self.with_lock(&id, || {
            let (row, mut receipt) = self.reference(board, share)?;
            let cleanup = &receipt["cleanup"];
            if row["state"] == "revoked" && cleanup["cleanupState"] == "complete" {
                let mut result = json!({"shareId":share,"revoked":true});
                if let Some(cleanup) = cleanup.as_object() {
                    result.as_object_mut().unwrap().extend(cleanup.clone());
                }
                return Ok(result);
            }
            let result = self.request("DELETE", &self.owner_path(board, share), &[], None)?;
            require(
                result["revoked"] == true,
                "Share service did not confirm revocation",
                "SHARE_SERVICE_FAILED",
            )?;
            receipt["cleanup"] = json!({});
            for key in ["cleanupState", "cleanupExecutor"] {
                if let Some(value) = result.get(key) {
                    receipt["cleanup"][key] = value.clone();
                }
            }
            self.connect()?.execute(
                "UPDATE requests SET state=?,receipt=? WHERE id=?",
                params![
                    "revoked",
                    serde_json::to_string(&receipt)?,
                    super::service::string(&row, "id")?
                ],
            )?;
            Ok(result)
        })
    }
    pub fn replace(
        &self,
        board: &str,
        share: &str,
        revision: i64,
        expiration: &str,
    ) -> Result<Value> {
        let (_, previous) = self.reference(board, share)?;
        let digest = Sha256::digest(json_bytes(&json!([
            self.source,
            board,
            share,
            revision,
            expiration
        ]))?);
        let mut identity = [0u8; 16];
        identity.copy_from_slice(&digest[..16]);
        let request_id = uuid::Builder::from_random_bytes(identity)
            .into_uuid()
            .to_string();
        let mut result = self.publish(
            board,
            revision,
            expiration,
            previous["annotationMode"].as_str().unwrap_or("view"),
            &request_id,
        )?;
        let revoked = self.revoke(board, share);
        result["previousShareId"] = json!(share);
        result["previousRevoked"] = json!(revoked.is_ok());
        if let Err(error) = revoked {
            result["followUp"] = json!("dashboard_share_delete");
            result["warning"] = error.json()["error"].clone();
        }
        Ok(result)
    }
}
fn unavailable() -> Error {
    Error::new(
        "SHARE_SERVICE_UNAVAILABLE",
        "Could not confirm the share service response. Retry the same request.",
    )
    .with_status(503)
}
fn checksum(path: &Path) -> Result<String> {
    let mut file = File::open(path)?;
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 1024 * 1024];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        hash.update(&buffer[..count]);
    }
    Ok(hex::encode(hash.finalize()))
}
fn request_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<Value> {
    Ok(
        json!({"id":row.get::<_,String>(0)?,"board":row.get::<_,String>(1)?,"fingerprint":row.get::<_,String>(2)?,"revision":row.get::<_,i64>(3)?,"service_url":row.get::<_,String>(4)?,"project":row.get::<_,String>(5)?,"archive":row.get::<_,Option<String>>(6)?,"archive_sha":row.get::<_,Option<String>>(7)?,"receipt":row.get::<_,Option<String>>(8)?,"state":row.get::<_,String>(9)?,"created_at":row.get::<_,f64>(10)?}),
    )
}
fn validate_service_url(value: &str) -> Result<()> {
    let parsed =
        Url::parse(value).map_err(|_| Error::new("INVALID_CONFIG", "Invalid share service URL"))?;
    require(parsed.host_str().is_some()&&parsed.username().is_empty()&&parsed.password().is_none()&&parsed.query().is_none()&&parsed.fragment().is_none()&&(parsed.scheme()=="https"||parsed.scheme()=="http"&&matches!(parsed.host_str(),Some("127.0.0.1"|"localhost"|"::1"|"[::1]"))),"Configure an HTTPS CHARTS_SHARE_SERVICE_URL (loopback HTTP is allowed for local verification)","INVALID_CONFIG")
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn publication_service_credentials_require_a_trusted_origin() {
        for url in [
            "https://shares.example/path",
            "http://localhost:8123",
            "http://127.0.0.1:8123",
            "http://[::1]:8123",
        ] {
            validate_service_url(url).unwrap();
        }
        for url in [
            "http://shares.example",
            "https://user:password@shares.example",
            "https://shares.example/?token=x",
            "https://shares.example/#key=x",
        ] {
            assert!(validate_service_url(url).is_err(), "{url}");
        }
    }
}
