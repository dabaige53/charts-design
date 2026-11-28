//! Private static publications, immutable credentials and transactional feedback.
//! Cleanup is an explicit cloud/timer entry point and never runs during author requests.
use super::{
    assets,
    cloud::{cloud_enabled, CloudDatabase},
    cloud_assets::{parquet_resources, CloudAssets},
    deployment,
    error::{require, Error, Result},
    model,
    object_storage::Storage,
    serialization::{canonical_json, json_bytes, utcnow},
    service::Service,
    share_annotations::ShareAnnotations,
    store::Store,
    versions::Versions,
};
use hmac::{Hmac, Mac};
use pbkdf2::pbkdf2_hmac;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet, HashSet},
    env, fs,
    io::{Cursor, Read, Seek},
    path::{Component, Path, PathBuf},
};
use subtle::ConstantTimeEq;
use url::Url;

pub fn now() -> i64 {
    chrono::Utc::now().timestamp()
}
pub fn checked_id(value: &str) -> Result<&str> {
    require(
        value.len() == 32
            && value
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "Invalid cloud share ID",
        "INVALID_ARGUMENT",
    )?;
    Ok(value)
}
pub fn checked_annotation_mode(mode: &str) -> Result<&str> {
    require(
        matches!(mode, "view" | "annotate"),
        "annotationMode must be view or annotate",
        "INVALID_ARGUMENT",
    )?;
    Ok(mode)
}
fn valid_key(key: &str) -> bool {
    key.len() == 8 && key.bytes().all(|b| b.is_ascii_digit())
}
pub fn key_digest(key: &str, salt: &str) -> Result<String> {
    let salt = hex::decode(salt)
        .map_err(|_| Error::new("SHARE_UNAVAILABLE", "Invalid publication credential"))?;
    require(
        salt.len() == 16,
        "Invalid publication credential",
        "SHARE_UNAVAILABLE",
    )?;
    let mut output = [0u8; 32];
    pbkdf2_hmac::<Sha256>(key.as_bytes(), &salt, 200_000, &mut output);
    Ok(hex::encode(output))
}
fn equal(a: &str, b: &str) -> bool {
    bool::from(a.as_bytes().ct_eq(b.as_bytes()))
}
fn salt() -> String {
    let mut bytes = [0u8; 16];
    for chunk in bytes.chunks_exact_mut(4) {
        chunk.copy_from_slice(&uuid::Uuid::new_v4().as_bytes()[..4]);
    }
    hex::encode(bytes)
}
fn access_key() -> String {
    loop {
        let bytes = uuid::Uuid::new_v4();
        let number = u32::from_be_bytes(bytes.as_bytes()[..4].try_into().unwrap());
        if number < 4_200_000_000 {
            return format!("{:08}", number % 100_000_000);
        }
    }
}
fn lifetime(expiration: &str) -> Result<Option<i64>> {
    match expiration {
        "never" => Ok(None),
        "7d" => Ok(Some(7 * 86400)),
        "30d" => Ok(Some(30 * 86400)),
        _ => Err(Error::new(
            "INVALID_ARGUMENT",
            "expiration must be never, 7d or 30d",
        )),
    }
}
fn string<'a>(v: &'a Value, key: &str) -> Result<&'a str> {
    super::service::string(v, key)
}
fn integer(v: &Value, key: &str) -> Result<i64> {
    super::service::integer(v, key)
}
fn merge(base: &Value, updates: &Value) -> Value {
    let mut value = base.clone();
    if let (Some(dest), Some(source)) = (value.as_object_mut(), updates.as_object()) {
        dest.extend(source.clone());
    }
    value
}
fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(v) => *v,
        Value::String(v) => !v.is_empty(),
        Value::Array(v) => !v.is_empty(),
        Value::Object(v) => !v.is_empty(),
        Value::Number(v) => v.as_f64().is_some_and(|v| v != 0.0),
    }
}
fn alive(control: &Value) -> bool {
    control["expiresAt"].is_null() || control["expiresAt"].as_i64().is_some_and(|v| now() < v)
}
fn put_json(storage: &Storage, key: &str, value: &Value) -> Result<()> {
    storage.put(key, &json_bytes(value)?, "application/json")
}
fn get_json(storage: &Storage, key: &str) -> Result<Option<Value>> {
    storage
        .get(key)?
        .map(|b| serde_json::from_slice(&b).map_err(Into::into))
        .transpose()
}
fn asset_database() -> Result<CloudDatabase> {
    CloudDatabase::new()?.with_function("charts_assets")
}
fn store_assets(store: &Store) -> Result<Option<CloudAssets>> {
    store
        .database
        .as_ref()
        .map(|_| store.cloud_assets().cloned())
        .transpose()
}
fn owner(store: &Store) -> Result<String> {
    let path = store
        .project_root
        .as_deref()
        .unwrap_or(&store.root)
        .canonicalize()?;
    Ok(hex::encode(Sha256::digest(
        path.to_string_lossy().as_bytes(),
    )))
}
pub fn retire_id(storage: &Storage, share_id: &str) -> Result<()> {
    storage.put(
        &format!("retired/{}", checked_id(share_id)?),
        b"",
        "application/octet-stream",
    )
}
fn index_html() -> String {
    format!(
        r#"<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{}<link rel="stylesheet" href="app.css"></head><body><div id="root"></div><script>window.__chartsBoot={{mode:"static"}}</script><script src="app.js"></script></body></html>"#,
        assets::favicon_link()
    )
}
fn walk_files(root: &Path) -> Result<Vec<PathBuf>> {
    fn visit(path: &Path, files: &mut Vec<PathBuf>) -> Result<()> {
        for entry in fs::read_dir(path)? {
            let entry = entry?;
            if entry.file_type()?.is_dir() {
                visit(&entry.path(), files)?;
            } else if entry.file_type()?.is_file() {
                files.push(entry.path());
            }
        }
        Ok(())
    }
    let mut files = vec![];
    visit(root, &mut files)?;
    files.sort();
    Ok(files)
}
fn relative_to(path: &Path, base: &Path) -> String {
    let target = path.components().collect::<Vec<_>>();
    let origin = base.components().collect::<Vec<_>>();
    let common = target
        .iter()
        .zip(&origin)
        .take_while(|(a, b)| a == b)
        .count();
    let mut relative = PathBuf::new();
    for _ in common..origin.len() {
        relative.push("..");
    }
    for part in &target[common..] {
        relative.push(part.as_os_str());
    }
    relative.to_string_lossy().replace('\\', "/")
}

pub struct CloudShares {
    pub storage: Storage,
    pub public_url: String,
    pub executor: String,
}
impl CloudShares {
    pub fn new(storage: Storage, public_url: &str) -> Result<Self> {
        let parsed = Url::parse(public_url).map_err(|_| {
            Error::new(
                "CLOUD_SHARE_NOT_CONFIGURED",
                "Configure CHARTS_PUBLIC_URL as the HTTPS cloud gateway address",
            )
        })?;
        require(
            parsed.scheme() == "https"
                && parsed.host_str().is_some()
                && parsed.query().is_none()
                && parsed.fragment().is_none(),
            "Configure CHARTS_PUBLIC_URL as the HTTPS cloud gateway address",
            "CLOUD_SHARE_NOT_CONFIGURED",
        )?;
        Ok(Self {
            executor: storage.executor().to_owned(),
            storage,
            public_url: public_url.trim_end_matches('/').to_owned(),
        })
    }
    pub fn from_environment(public_url: Option<&str>) -> Result<Self> {
        Self::new(
            Storage::publication()?,
            public_url.unwrap_or(&env::var("CHARTS_PUBLIC_URL").unwrap_or_default()),
        )
    }
    fn not_retired(&self, share_id: &str) -> Result<()> {
        require(
            self.storage
                .get(&format!("retired/{}", checked_id(share_id)?))?
                .is_none(),
            "Share has expired or been revoked",
            "SHARE_EXPIRED",
        )
    }
    fn annotation_store(&self) -> Result<ShareAnnotations> {
        ShareAnnotations::for_storage(&self.storage)
    }
    fn heartbeat(&self) -> Result<()> {
        let status = get_json(&self.storage, "cleaner-status.json")?;
        require(
            status
                .as_ref()
                .and_then(|s| s["completedAt"].as_f64())
                .is_some_and(|at| (now() as f64) - at < 7.0 * 3600.0),
            "Confirm a successful six-hour cloud cleanup invocation before publishing",
            "CLOUD_CLEANER_UNAVAILABLE",
        )
    }
    fn configure_annotations(&self, control: &mut Value, force: bool) -> Result<()> {
        if control["annotationMode"] != "annotate" && !force {
            return Ok(());
        }
        let db = self.annotation_store()?;
        let share = string(control, "shareId")?.to_owned();
        db.call("ready", &json!({"shareId":share}))?;
        let intent = format!("publication-intents/{share}.json");
        if self.storage.get(&intent)?.is_none() {
            put_json(
                &self.storage,
                &intent,
                &json!({"shareId":share,"cleanupAfter":control["stagingUntil"]}),
            )?;
        }
        let result=db.call("configure",&json!({"shareId":share,"owner":control["owner"],"pages":control["pages"],"expiresAt":control["expiresAt"],"stagingUntil":control["stagingUntil"],"annotationMode":control.get("annotationMode").cloned().unwrap_or(json!("view")),"sourceDigest":control["sourceDigest"]}))?;
        control["expiresAt"] = result["expiresAt"].clone();
        control["stagingUntil"] = result["stagingUntil"].clone();
        control["cleanupAfter"] = result["stagingUntil"].clone();
        control["annotationsStorage"] = json!(db.kind());
        Ok(())
    }
    fn activate(&self, control: &Value, job: &Value) -> Result<()> {
        let share = string(control, "shareId")?;
        let result = (|| -> Result<()> {
            self.not_retired(share)?;
            require(
                now() < integer(job, "stagingUntil")?,
                "Publication staging has expired",
                "SHARE_EXPIRED",
            )?;
            put_json(
                &self.storage,
                &format!("shares/{share}/control.json"),
                control,
            )?;
            put_json(&self.storage, &format!("jobs/{share}.json"), job)?;
            if truthy(&control["annotationsStorage"]) {
                self.annotation_store()?
                    .call("activate", &json!({"shareId":share}))?;
            }
            Ok(())
        })();
        if self.storage.get(&format!("retired/{share}"))?.is_some() {
            put_json(
                &self.storage,
                &format!("jobs/{share}.json"),
                &merge(job, &json!({"state":"revoked","cleanupAfter":0})),
            )?;
            self.not_retired(share)?;
        }
        result?;
        if truthy(&control["annotationsStorage"]) {
            self.storage
                .delete_prefix(&format!("publication-intents/{share}.json"))?;
        }
        Ok(())
    }
    fn publication_document(&self, document: &Value, share: &str, mode: &str) -> Result<Value> {
        let mut doc = document.clone();
        let object = doc
            .as_object_mut()
            .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Publication must be an object"))?;
        for field in [
            "browserLinks",
            "publicationApiBase",
            "annotationAccess",
            "publication",
            "annotationsOpen",
        ] {
            object.remove(field);
        }
        doc["manifest"]
            .as_object_mut()
            .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Manifest must be an object"))?
            .remove("annotations");
        doc["publication"] = json!({"shareId":share,"revision":doc["revision"]});
        doc["annotationAccess"] = json!({"endpoint":format!("{}/s/{share}/api/annotations",Url::parse(&self.public_url).unwrap().path().trim_end_matches('/')),"canRead":true,"canAnnotate":mode=="annotate","canManageAnnotations":false,"scope":format!("share:{share}"),"author":{"name":"访客","verified":false}});
        Ok(doc)
    }
    pub fn control(&self, share: &str) -> Result<Value> {
        self.not_retired(share)?;
        let control = get_json(&self.storage, &format!("shares/{share}/control.json"))?
            .ok_or_else(|| Error::new("SHARE_UNAVAILABLE", "分享不存在或已删除"))?;
        if cloud_enabled()? {
            let registered = asset_database()?.call("share_access", "", &json!({"id":share}))?;
            require(
                registered.is_null() && !truthy(&control["registered"])
                    || !registered.is_null() && registered["state"] == "active",
                "分享已撤销或尚未完成",
                "SHARE_EXPIRED",
            )?;
        }
        require(
            control["state"] == "active" && alive(&control),
            "分享已过期或已撤销",
            "SHARE_EXPIRED",
        )?;
        Ok(control)
    }
    pub fn quick_result(&self, share: &str, key: &str, expiration: &str) -> Result<Option<Value>> {
        self.not_retired(share)?;
        let raw = get_json(&self.storage, &format!("shares/{share}/control.json"))?;
        let registered = if cloud_enabled()? {
            let registered = asset_database()?.call("share_access", "", &json!({"id":share}))?;
            require(
                registered.is_null() || registered["state"] != "revoked",
                "Share was revoked",
                "SHARE_EXPIRED",
            )?;
            registered
        } else {
            Value::Null
        };
        let Some(control) = raw else {
            return Ok(None);
        };
        if registered["state"] == "uploading" {
            return Ok(None);
        }
        require(
            valid_key(key)
                && equal(
                    &key_digest(key, string(&control, "salt")?)?,
                    string(&control, "keyHash")?,
                ),
            "Share retry uses another access key",
            "REVISION_CONFLICT",
        )?;
        require(
            control["state"] == "active" && alive(&control),
            "Share has expired or been revoked",
            "SHARE_EXPIRED",
        )?;
        require(
            !truthy(&control["registered"]) || !registered.is_null(),
            "Share is unavailable",
            "SHARE_UNAVAILABLE",
        )?;
        let job = get_json(&self.storage, &format!("jobs/{share}.json"))?;
        if job.as_ref().is_none_or(|j| j["state"] != "active") {
            return Ok(None);
        }
        if truthy(&control["annotationsStorage"]) {
            self.annotation_store()?
                .call("activate", &json!({"shareId":share}))?;
            self.not_retired(share)?;
            self.storage
                .delete_prefix(&format!("publication-intents/{share}.json"))?;
        }
        Ok(Some(self.receipt(share, key, expiration, &control)))
    }
    fn receipt(&self, share: &str, key: &str, expiration: &str, control: &Value) -> Value {
        let url = format!("{}/s/{share}/", self.public_url);
        let mode = control["annotationMode"].as_str().unwrap_or("view");
        json!({"shareId":share,"url":url,"accessUrl":format!("{url}#key={key}"),"accessKey":key,"expiration":expiration,"expiresAt":control["expiresAt"],"revision":control["revision"],"pages":control["pages"],"cleanupExecutor":self.executor,"annotationMode":mode})
    }
    fn stage(&self, share: &str, job: &Value) -> Result<Value> {
        self.not_retired(share)?;
        let key = format!("jobs/{share}.json");
        if let Some(previous) = get_json(&self.storage, &key)? {
            require(
                previous["revision"] == job["revision"],
                "Share request targets another revision",
                "REVISION_CONFLICT",
            )?;
            require(
                matches!(previous["state"].as_str(), Some("uploading" | "active")),
                "Share was revoked",
                "SHARE_EXPIRED",
            )?;
            let mut next = merge(&previous, job);
            for key in ["expiresAt", "stagingUntil", "cleanupAfter"] {
                next[key] = previous[key].clone();
            }
            return Ok(next);
        }
        put_json(&self.storage, &key, job)?;
        Ok(job.clone())
    }

    #[allow(clippy::too_many_arguments)]
    pub fn publish(
        &self,
        service: &Service,
        board: &str,
        expected: i64,
        expiration: &str,
        key: Option<&str>,
        pages: Option<&[Value]>,
        share_id: Option<&str>,
        mode: &str,
    ) -> Result<Value> {
        let mode = checked_annotation_mode(mode)?;
        let duration = lifetime(expiration)?;
        let key = key.map(str::to_owned).unwrap_or_else(access_key);
        require(
            valid_key(&key),
            "accessKey must contain exactly eight ASCII digits",
            "INVALID_ARGUMENT",
        )?;
        let versions = if service.project_root.is_some() {
            Some(Versions::new(&service.store)?)
        } else {
            None
        };
        let document = if let Some(versions) = &versions {
            require(
                versions.status(board)?["publishedRevision"] == expected,
                "Publish the saved version before sharing it",
                "REVISION_CONFLICT",
            )?;
            versions.read(board, expected)?
        } else {
            let doc = service.store.get(board, false)?;
            require(
                doc["revision"] == expected,
                "Reload before sharing",
                "REVISION_CONFLICT",
            )?;
            doc
        };
        let mut documents = vec![(board.to_owned(), document)];
        if let Some(pages) = pages {
            let versions = versions.as_ref().ok_or_else(|| {
                Error::new(
                    "INVALID_ARGUMENT",
                    "Multiple pages require a project and a page list",
                )
            })?;
            let mut seen = HashSet::from([board.to_owned()]);
            for page in pages {
                let id = string(page, "dashboardId")?;
                model::check_identifier(id)?;
                let revision = integer(page, "expectedRevision")?;
                require(
                    seen.insert(id.into()),
                    "Duplicate share page",
                    "INVALID_ARGUMENT",
                )?;
                require(
                    versions.status(id)?["publishedRevision"] == revision,
                    "Publish each selected page before sharing it",
                    "REVISION_CONFLICT",
                )?;
                documents.push((id.into(), versions.read(id, revision)?));
            }
        }
        require(
            !documents
                .iter()
                .any(|(_, d)| truthy(&model::live_datasets(d))),
            "实时 SQL 看板请通过运行服务查看",
            "LIVE_DATA_REQUIRES_RUNTIME",
        )?;
        self.heartbeat()?;
        self.storage.check_private()?;
        if let Some(id) = share_id {
            if let Some(previous) = self.quick_result(id, &key, expiration)? {
                return Ok(previous);
            }
        }
        let share = share_id
            .map(str::to_owned)
            .unwrap_or_else(|| uuid::Uuid::new_v4().simple().to_string());
        checked_id(&share)?;
        if service.store.cos_enabled {
            return self.publish_cos(service, &documents, expiration, &key, &share, mode);
        }
        let time = now();
        let mut job=self.stage(&share,&json!({"shareId":share,"state":"uploading","cleanupAfter":time+3600,"stagingUntil":time+3600,"expiresAt":duration.map(|seconds|time+seconds),"owner":owner(&service.store)?,"dashboardId":board,"revision":documents[0].1["revision"],"pages":documents.iter().map(|(id,d)|json!({"id":id,"revision":d["revision"]})).collect::<Vec<_>>(),"annotationMode":mode}))?;
        self.configure_annotations(&mut job, false)?;
        put_json(&self.storage, &format!("jobs/{share}.json"), &job)?;
        let registry = store_assets(&service.store)?;
        if let Some(registry) = &registry {
            registry.call("share_register",&json!({"id":share,"pages":job["pages"],"state":"uploading","expiresAt":job["expiresAt"]}))?;
        }
        let temporary = tempfile::tempdir()?;
        let exported = deployment::export_site(
            &service.store,
            board,
            Some(temporary.path()),
            Some(&documents[0].1),
            "auto",
            false,
        )?;
        let site = PathBuf::from(string(&exported["export"], "directory")?);
        let mut entries = vec![
            json!({"id":board,"title":documents[0].1["manifest"]["title"],"path":"document.json","revision":documents[0].1["revision"]}),
        ];
        if documents.len() > 1 {
            let mut shards = BTreeMap::new();
            for path in walk_files(&site.join("data"))? {
                shards.insert(hex::encode(Sha256::digest(fs::read(&path)?)), path);
            }
            for (id, doc) in documents.iter().skip(1) {
                let exported = deployment::export_site(
                    &service.store,
                    id,
                    Some(temporary.path()),
                    Some(doc),
                    "auto",
                    false,
                )?;
                let page_site = PathBuf::from(string(&exported["export"], "directory")?);
                let target = site.join("pages").join(id);
                fs::create_dir_all(&target)?;
                let mut page: Value =
                    serde_json::from_slice(&fs::read(page_site.join("document.json"))?)?;
                let datasets = page["staticFiles"]
                    .as_object_mut()
                    .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Static files required"))?;
                for paths in datasets.values_mut() {
                    let mut reused = vec![];
                    for name in paths
                        .as_array()
                        .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Invalid static file list"))?
                    {
                        let name = name.as_str().ok_or_else(|| {
                            Error::new("INVALID_DOCUMENT", "Invalid static file name")
                        })?;
                        let raw = fs::read(page_site.join(name))?;
                        let digest = hex::encode(Sha256::digest(&raw));
                        let destination = if let Some(existing) = shards.get(&digest) {
                            existing.clone()
                        } else {
                            let destination = target.join(name);
                            fs::create_dir_all(destination.parent().unwrap())?;
                            fs::write(&destination, raw)?;
                            shards.insert(digest, destination.clone());
                            destination
                        };
                        reused.push(json!(relative_to(&destination, &target)));
                    }
                    *paths = json!(reused);
                }
                fs::write(target.join("document.json"), json_bytes(&page)?)?;
                entries.push(json!({"id":id,"title":doc["manifest"]["title"],"path":format!("pages/{id}/document.json"),"revision":doc["revision"]}));
            }
            let mut root: Value = serde_json::from_slice(&fs::read(site.join("document.json"))?)?;
            root["staticPages"] = json!(entries);
            fs::write(site.join("document.json"), json_bytes(&root)?)?;
        }
        for entry in &entries {
            let path = site.join(string(entry, "path")?);
            let doc: Value = serde_json::from_slice(&fs::read(&path)?)?;
            fs::write(
                &path,
                json_bytes(&self.publication_document(&doc, &share, mode)?)?,
            )?;
        }
        let mut files = vec![];
        let mut total = 0u64;
        for path in walk_files(&site)? {
            let name = path
                .strip_prefix(&site)
                .unwrap()
                .to_string_lossy()
                .replace('\\', "/");
            let raw = fs::read(&path)?;
            total += raw.len() as u64;
            self.storage.put(
                &format!("shares/{share}/site/{name}"),
                &raw,
                mime_guess::from_path(&path)
                    .first_or_octet_stream()
                    .as_ref(),
            )?;
            files.push(name);
        }
        let salt = salt();
        let control = json!({"shareId":share,"state":"active","dashboardId":board,"revision":documents[0].1["revision"],"owner":job["owner"],"createdAt":integer(&job,"stagingUntil")?-3600,"expiresAt":job["expiresAt"],"salt":salt,"keyHash":key_digest(&key,&salt)?,"files":files,"pages":entries,"registered":registry.is_some(),"annotationMode":mode,"annotationsStorage":job["annotationsStorage"]});
        self.activate(
            &control,
            &merge(
                &job,
                &json!({"state":"active","cleanupAfter":job["expiresAt"],"pages":entries}),
            ),
        )?;
        if let Some(registry) = &registry {
            registry.call("share_register",&json!({"id":share,"pages":job["pages"],"state":"active","expiresAt":job["expiresAt"],"bytes":total}))?;
        }
        Ok(self.receipt(&share, &key, expiration, &control))
    }
    pub fn index_project(&self, store: &Store) -> Result<()> {
        let registry = store.cloud_assets()?;
        let project_owner = owner(store)?;
        for key in self.storage.list("jobs/")? {
            let Some(job) = get_json(&self.storage, &key)? else {
                continue;
            };
            if job["owner"] != project_owner {
                continue;
            }
            let id = string(&job, "shareId")?;
            if !registry
                .database
                .call("share_access", "", &json!({"id":id}))?
                .is_null()
            {
                continue;
            }
            let pages = if truthy(&job["pages"]) {
                job["pages"].clone()
            } else {
                json!([{"id":job["dashboardId"],"revision":job["revision"]}])
            };
            registry.call("share_register",&json!({"id":id,"pages":pages,"state":job["state"],"expiresAt":job["expiresAt"],"bytes":self.storage.size_prefix(&format!("shares/{id}/"))?,"stagingUntil":job.get("stagingUntil").unwrap_or(&job["cleanupAfter"])}))?;
        }
        Ok(())
    }
    fn publish_cos(
        &self,
        service: &Service,
        documents: &[(String, Value)],
        expiration: &str,
        key: &str,
        share: &str,
        mode: &str,
    ) -> Result<Value> {
        assets::require_preview()?;
        let time = now();
        let duration = lifetime(expiration)?;
        let pages=documents.iter().enumerate().map(|(index,(board,doc))|json!({"id":board,"title":doc["manifest"]["title"],"revision":doc["revision"],"path":if index==0{"document.json".to_owned()}else{format!("pages/{board}/document.json")}})).collect::<Vec<_>>();
        let registry = service.store.cloud_assets()?;
        let mut job=self.stage(share,&json!({"shareId":share,"state":"uploading","cleanupAfter":time+3600,"stagingUntil":time+3600,"expiresAt":duration.map(|seconds|time+seconds),"owner":owner(&service.store)?,"dashboardId":pages[0]["id"],"revision":pages[0]["revision"],"pages":pages,"annotationMode":mode}))?;
        self.configure_annotations(&mut job, false)?;
        put_json(&self.storage, &format!("jobs/{share}.json"), &job)?;
        registry.call("share_register",&json!({"id":share,"pages":pages,"state":"uploading","expiresAt":job["expiresAt"],"stagingUntil":job["stagingUntil"]}))?;
        let mut files = vec![];
        let mut asset_files = Map::new();
        let mut total = 0usize;
        let mut datasets = Map::new();
        let mut converted = HashSet::new();
        for (index, ((board, doc), page)) in documents.iter().zip(&pages).enumerate() {
            let mut objects = Map::new();
            for reference in used_references(doc).values() {
                let version = string(reference, "version")?;
                if !datasets.contains_key(version) {
                    let mut object = registry.call("object_get", &json!({"version":version}))?;
                    require(
                        !object.is_null(),
                        "Dataset files unavailable",
                        "ASSET_UNAVAILABLE",
                    )?;
                    require(
                        object["descriptor"]["metadata"] == *reference,
                        "Remote data metadata differs",
                        "DATA_CONFLICT",
                    )?;
                    if object["descriptor"]["dataFormat"] != "parquet-v1" {
                        let temporary = tempfile::tempdir()?;
                        let receipt = deployment::copy_parquet_package(
                            temporary.path(),
                            &service.store.data,
                            reference,
                            &service.store.runtime_root.join("parquet-cache"),
                            object["descriptor"]["partitionIndex"]["field"].as_str(),
                            true,
                            false,
                        )?;
                        let resources = parquet_resources(&receipt)?;
                        let mut names = resources["shards"].as_array().cloned().unwrap_or_default();
                        for option in resources["options"]
                            .as_object()
                            .into_iter()
                            .flatten()
                            .map(|(_, v)| v)
                        {
                            names.extend(option["files"].as_array().cloned().unwrap_or_default());
                        }
                        for name in names {
                            let name = name.as_str().ok_or_else(|| {
                                Error::new("DATA_CONFLICT", "Invalid Parquet file")
                            })?;
                            let path = format!("data/{}/{name}", string(&object, "id")?);
                            let raw = fs::read(temporary.path().join(name))?;
                            self.put_site(share, &path, &raw, &mut files, &mut total)?;
                        }
                        object["descriptor"] = merge(&object["descriptor"], &resources);
                        converted.insert(string(&object, "id")?.to_owned());
                    }
                    datasets.insert(version.to_owned(), object);
                }
                objects.insert(version.to_owned(), datasets[version].clone());
            }
            let web = web_document_with_assets(
                doc,
                |object, name| {
                    let path = format!("data/{object}/{name}");
                    if !converted.contains(object) {
                        asset_files.insert(path.clone(),json!({"object":object,"name":name,"board":board,"revision":doc["revision"]}));
                    }
                    if index == 0 {
                        path
                    } else {
                        format!("../../{path}")
                    }
                },
                false,
                false,
                |reference| {
                    objects
                        .get(string(reference, "version")?)
                        .cloned()
                        .ok_or_else(|| Error::new("ASSET_UNAVAILABLE", "Dataset files unavailable"))
                },
            )?;
            let mut web = self.publication_document(&web, share, mode)?;
            if index == 0 {
                web["staticPages"] = json!(pages);
            }
            self.put_site(
                share,
                string(page, "path")?,
                &json_bytes(&web)?,
                &mut files,
                &mut total,
            )?;
        }
        for name in ["app.js", "app.css", "static-worker.js"] {
            self.put_site(
                share,
                name,
                &fs::read(assets::dist().join(name))?,
                &mut files,
                &mut total,
            )?;
        }
        self.put_site(
            share,
            "index.html",
            index_html().as_bytes(),
            &mut files,
            &mut total,
        )?;
        let salt = salt();
        let mut all_files = files.clone();
        all_files.extend(asset_files.keys().cloned());
        let control = merge(
            &job,
            &json!({"state":"active","createdAt":integer(&job,"stagingUntil")?-3600,"salt":salt,"keyHash":key_digest(key,&salt)?,"files":all_files,"assetFiles":asset_files,"project":service.store.project,"registered":true}),
        );
        self.activate(
            &control,
            &merge(
                &job,
                &json!({"state":"active","cleanupAfter":job["expiresAt"]}),
            ),
        )?;
        registry.call("share_register",&json!({"id":share,"pages":pages,"state":"active","expiresAt":job["expiresAt"],"bytes":total}))?;
        Ok(self.receipt(share, key, expiration, &control))
    }
    fn put_site(
        &self,
        share: &str,
        name: &str,
        raw: &[u8],
        files: &mut Vec<String>,
        total: &mut usize,
    ) -> Result<()> {
        self.storage.put(
            &format!("shares/{share}/site/{name}"),
            raw,
            mime_guess::from_path(name).first_or_octet_stream().as_ref(),
        )?;
        files.push(name.into());
        *total += raw.len();
        Ok(())
    }

    #[allow(clippy::too_many_arguments)]
    pub fn import_site_path(
        &self,
        archive: &Path,
        source_key: &str,
        request_id: &str,
        secret: &[u8],
        mode: &str,
        expiration: &str,
        key: Option<&str>,
    ) -> Result<Value> {
        let file = fs::File::open(archive)?;
        self.import_site_reader(file, source_key, request_id, secret, mode, expiration, key)
    }
    #[allow(clippy::too_many_arguments)]
    pub fn import_site(
        &self,
        archive: &[u8],
        source_key: &str,
        request_id: &str,
        secret: &[u8],
        mode: &str,
        expiration: &str,
        key: Option<&str>,
    ) -> Result<Value> {
        self.import_site_reader(
            Cursor::new(archive),
            source_key,
            request_id,
            secret,
            mode,
            expiration,
            key,
        )
    }
    #[allow(clippy::too_many_arguments)]
    fn import_site_reader<R: Read + Seek>(
        &self,
        archive: R,
        source_key: &str,
        request_id: &str,
        secret: &[u8],
        mode: &str,
        expiration: &str,
        key: Option<&str>,
    ) -> Result<Value> {
        assets::require_preview()?;
        let mode = checked_annotation_mode(mode)?;
        let duration = lifetime(expiration)?;
        require(
            source_key.len() == 64
                && source_key
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
            "Invalid author project identity",
            "INVALID_ARGUMENT",
        )?;
        require(
            !request_id.is_empty() && request_id.chars().count() <= 128,
            "requestId is required",
            "INVALID_ARGUMENT",
        )?;
        require(
            secret.len() >= 32,
            "Stable server secret required",
            "INVALID_CONFIG",
        )?;
        let identity = json_bytes(&json!([source_key, request_id]))?;
        let mut signed = Hmac::<Sha256>::new_from_slice(secret)
            .map_err(|_| Error::new("INVALID_CONFIG", "Invalid server secret"))?;
        signed.update(b"local-publication:");
        signed.update(&identity);
        let share = hex::encode(signed.finalize().into_bytes())[..32].to_owned();
        self.not_retired(&share)?;
        let mut signed = Hmac::<Sha256>::new_from_slice(secret)
            .map_err(|_| Error::new("INVALID_CONFIG", "Invalid server secret"))?;
        signed.update(b"local-publication-key:");
        signed.update(&identity);
        let derived = signed.finalize().into_bytes();
        let number = derived
            .iter()
            .fold(0u64, |n, b| (n * 256 + u64::from(*b)) % 100_000_000);
        let key = key
            .map(str::to_owned)
            .unwrap_or_else(|| format!("{number:08}"));
        require(valid_key(&key), "Invalid access key", "INVALID_ARGUMENT")?;
        let mut package = zip::ZipArchive::new(archive).map_err(zip_error)?;
        require(
            package.len() <= 10000,
            "Publication package exceeds the 512 MiB limit",
            "PAYLOAD_TOO_LARGE",
        )?;
        let mut files = BTreeMap::<String, usize>::new();
        let mut seen = HashSet::new();
        let mut size = 0u64;
        for i in 0..package.len() {
            let entry = package.by_index(i).map_err(zip_error)?;
            size = size.checked_add(entry.size()).ok_or_else(|| {
                Error::new("PAYLOAD_TOO_LARGE", "Publication package is too large")
            })?;
            require(
                size <= 512 * 1024 * 1024,
                "Publication package exceeds the 512 MiB limit",
                "PAYLOAD_TOO_LARGE",
            )?;
            let decoded_name = entry.name().map_err(zip_error)?;
            let name = decoded_name.as_ref();
            let path = Path::new(name);
            let normalized = name.trim_end_matches('/');
            require(
                !name.is_empty()
                    && !path.is_absolute()
                    && !name.contains('\\')
                    && normalized
                        .split('/')
                        .all(|part| !part.is_empty() && part != "." && part != "..")
                    && seen.insert(name.to_owned())
                    && entry
                        .unix_mode()
                        .is_none_or(|mode| mode & 0o170000 != 0o120000),
                "Invalid publication file path",
                "INVALID_ARGUMENT",
            )?;
            if entry.is_dir() {
                continue;
            }
            require(
                entry.size() <= 64 * 1024 * 1024,
                "Publication file is too large",
                "PAYLOAD_TOO_LARGE",
            )?;
            let allowed = matches!(
                name,
                "index.html"
                    | "app.js"
                    | "app.css"
                    | "static-worker.js"
                    | "document.json"
                    | "export-manifest.json"
                    | "README.txt"
            ) || matches!(name.split('/').next(), Some("data" | "pages"))
                && matches!(
                    path.extension().and_then(|s| s.to_str()),
                    Some("json" | "gz" | "parquet")
                );
            require(
                allowed,
                "Unsupported publication resource",
                "INVALID_ARGUMENT",
            )?;
            files.insert(name.to_owned(), i);
        }
        require(
            files.contains_key("document.json") && files.contains_key("export-manifest.json"),
            "Export a complete static site first",
            "INVALID_ARGUMENT",
        )?;
        let mut fingerprint = Sha256::new();
        fingerprint.update(json_bytes(&json!([mode, expiration, key]))?);
        for (name, index) in &files {
            let mut entry = package.by_index(*index).map_err(zip_error)?;
            let mut hash = Sha256::new();
            let mut buffer = [0u8; 64 * 1024];
            let mut count = 0u64;
            loop {
                let read = entry.read(&mut buffer)?;
                if read == 0 {
                    break;
                }
                count += read as u64;
                require(
                    count <= 64 * 1024 * 1024,
                    "Publication file is too large",
                    "PAYLOAD_TOO_LARGE",
                )?;
                hash.update(&buffer[..read]);
            }
            require(
                count == entry.size(),
                "Publication file size differs",
                "INVALID_ARGUMENT",
            )?;
            fingerprint.update(json_bytes(&json!([name, hex::encode(hash.finalize())]))?);
        }
        let digest = hex::encode(fingerprint.finalize());
        let mut document: Value =
            serde_json::from_slice(&zip_read(&mut package, files["document.json"])?)?;
        let manifest: Value =
            serde_json::from_slice(&zip_read(&mut package, files["export-manifest.json"])?)?;
        require(
            document.is_object()
                && document["schemaVersion"] == 2
                && document["manifest"].is_object()
                && document["manifest"]["components"].is_object(),
            "Invalid publication document",
            "INVALID_ARGUMENT",
        )?;
        let board = model::identifier(&document["id"], "dashboard id")?;
        let revision = integer(&document, "revision")?;
        require(
            revision >= 1 && manifest["revision"] == revision && manifest["dashboardId"] == board,
            "Export version does not match document",
            "REVISION_CONFLICT",
        )?;
        require(
            !truthy(&document["staticPages"]),
            "Import one saved page per request",
            "INVALID_ARGUMENT",
        )?;
        let static_files = document["staticFiles"]
            .as_object()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Static data files required"))?;
        let mut used = BTreeSet::new();
        for names in static_files.values() {
            for name in names
                .as_array()
                .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid static data manifest"))?
            {
                let name = name.as_str().ok_or_else(|| {
                    Error::new("INVALID_ARGUMENT", "Invalid static data manifest")
                })?;
                require(
                    name.starts_with("data/") && files.contains_key(name),
                    "A published data resource is missing",
                    "INVALID_ARGUMENT",
                )?;
                used.insert(name.to_owned());
            }
        }
        require(
            !truthy(&document["staticOptions"]) && !truthy(&document["staticPartitionIndexes"]),
            "Local export must contain self-contained data shards",
            "INVALID_ARGUMENT",
        )?;
        let pages = json!([{"id":board,"title":document["manifest"].get("title").cloned().unwrap_or(json!(board)),"path":"document.json","revision":revision}]);
        if let Some(previous) = get_json(&self.storage, &format!("jobs/{share}.json"))? {
            require(
                previous["owner"] == source_key && previous["sourceDigest"] == digest,
                "requestId already identifies another publication",
                "REVISION_CONFLICT",
            )?;
            if let Some(result) = self.quick_result(&share, &key, expiration)? {
                return Ok(result);
            }
        }
        self.heartbeat()?;
        self.storage.check_private()?;
        let time = now();
        let mut job = json!({"shareId":share,"state":"uploading","owner":source_key,"dashboardId":board,"revision":revision,"pages":pages,"annotationMode":mode,"sourceDigest":digest,"expiresAt":duration.map(|seconds|time+seconds),"cleanupAfter":time+3600,"stagingUntil":time+3600});
        self.configure_annotations(&mut job, true)?;
        job = self.stage(&share, &job)?;
        put_json(&self.storage, &format!("jobs/{share}.json"), &job)?;
        let mut uploaded = vec![];
        let mut total = 0usize;
        for name in used {
            self.put_site(
                &share,
                &name,
                &zip_read(&mut package, files[&name])?,
                &mut uploaded,
                &mut total,
            )?;
        }
        for name in ["app.js", "app.css", "static-worker.js"] {
            self.put_site(
                &share,
                name,
                &fs::read(assets::dist().join(name))?,
                &mut uploaded,
                &mut total,
            )?;
        }
        for field in ["sources", "queries", "annotations"] {
            document["manifest"].as_object_mut().unwrap().remove(field);
        }
        document = self.publication_document(&document, &share, mode)?;
        document["snapshot"] = json!({"datasets":{}});
        self.put_site(
            &share,
            "document.json",
            &json_bytes(&document)?,
            &mut uploaded,
            &mut total,
        )?;
        self.put_site(
            &share,
            "index.html",
            index_html().as_bytes(),
            &mut uploaded,
            &mut total,
        )?;
        let salt = salt();
        let control = merge(
            &job,
            &json!({"state":"active","files":uploaded,"registered":false,"createdAt":integer(&job,"stagingUntil")?-3600,"salt":salt,"keyHash":key_digest(&key,&salt)?}),
        );
        self.activate(
            &control,
            &merge(
                &job,
                &json!({"state":"active","cleanupAfter":job["expiresAt"]}),
            ),
        )?;
        Ok(self.receipt(&share, &key, expiration, &control))
    }
    pub fn authenticate(&self, share: &str, key: &str) -> Result<Value> {
        let control = self.control(share)?;
        require(
            valid_key(key)
                && equal(
                    &key_digest(key, string(&control, "salt")?)?,
                    string(&control, "keyHash")?,
                ),
            "访问密钥错误",
            "INVALID_ACCESS_KEY",
        )?;
        Ok(control)
    }
    pub fn publication_page(
        &self,
        share: &str,
        board: Option<&str>,
        control: Option<&Value>,
    ) -> Result<Value> {
        let fetched;
        let control = if let Some(control) = control {
            control
        } else {
            fetched = self.control(share)?;
            &fetched
        };
        let board = board.unwrap_or(string(control, "dashboardId")?);
        model::check_identifier(board)?;
        control["pages"]
            .as_array()
            .into_iter()
            .flatten()
            .find(|p| p["id"] == board)
            .cloned()
            .ok_or_else(|| Error::new("FORBIDDEN", "此分享不包含该页面"))
    }
    pub fn annotations(&self, share: &str, board: Option<&str>) -> Result<Value> {
        let control = self.control(share)?;
        let page = self.publication_page(share, board, Some(&control))?;
        let notes = if control["annotationMode"] == "annotate" {
            self.annotation_store()?
                .call("read", &json!({"shareId":share,"dashboardId":page["id"]}))?
        } else {
            json!([])
        };
        self.control(share)?;
        Ok(
            json!({"shareId":share,"dashboardId":page["id"],"revision":page["revision"],"count":notes.as_array().map_or(0,Vec::len),"annotations":notes,"independentSave":true,"canAnnotate":control["annotationMode"]=="annotate","canManageAnnotations":false,"author":{"name":"访客","verified":false}}),
        )
    }
    pub fn append_annotation(
        &self,
        share: &str,
        board: Option<&str>,
        note: &Value,
        author_name: Option<&str>,
    ) -> Result<Value> {
        let control = self.control(share)?;
        require(
            control["annotationMode"] == "annotate",
            "此分享仅允许查看",
            "FORBIDDEN",
        )?;
        let page = self.publication_page(share, board, Some(&control))?;
        require(
            note.is_object(),
            "Annotation must be an object",
            "INVALID_ARGUMENT",
        )?;
        let mut clean = Map::new();
        for key in ["id", "componentId", "text", "createdAt", "anchor", "view"] {
            if let Some(value) = note.get(key) {
                clean.insert(key.into(), value.clone());
            }
        }
        let mut clean = Value::Object(clean);
        model::validate_annotations(&json!([clean]), None)?;
        require(
            clean.get("anchor").is_some(),
            "位置批注必须提供锚点",
            "INVALID_ARGUMENT",
        )?;
        require(
            author_name.is_none_or(|s| s.chars().count() <= 80),
            "署名最多 80 字",
            "INVALID_ARGUMENT",
        )?;
        require(
            json_bytes(&clean)?.len() <= 32 * 1024,
            "Annotation is too large",
            "PAYLOAD_TOO_LARGE",
        )?;
        let document: Value = serde_json::from_slice(&self.content(
            share,
            string(&page, "path")?,
            Some(&control),
        )?)?;
        require(
            clean["componentId"].is_null()
                || clean["componentId"]
                    .as_str()
                    .is_some_and(|id| document["manifest"]["components"].get(id).is_some()),
            "此位置不属于分享版本",
            "INVALID_ARGUMENT",
        )?;
        let view = clean.get("view").cloned().unwrap_or(json!({}));
        require(
            view.is_object(),
            "Invalid annotation view",
            "INVALID_ARGUMENT",
        )?;
        require(
            view.get("revision").unwrap_or(&page["revision"]) == &page["revision"],
            "批注必须针对当前分享版本",
            "REVISION_CONFLICT",
        )?;
        let author = author_name.unwrap_or("").trim();
        clean["author"] = json!({"name":if author.is_empty(){"访客"}else{author},"verified":false});
        let fingerprint = hex::encode(Sha256::digest(canonical_json(&clean)?.as_bytes()));
        clean["context"] = json!({"shareId":share,"designRevision":page["revision"],"filters":view.get("filters").cloned().unwrap_or(json!([]))});
        clean["receivedAt"] = json!(utcnow());
        let saved=self.annotation_store()?.call("append",&json!({"shareId":share,"dashboardId":page["id"],"annotation":clean,"fingerprint":fingerprint}))?;
        self.control(share)?;
        Ok(
            json!({"shareId":share,"dashboardId":page["id"],"revision":page["revision"],"annotation":saved,"independentSave":true}),
        )
    }
    pub fn owner_control(&self, share: &str, source_key: &str) -> Result<Value> {
        let control = self.control(share)?;
        require(
            equal(string(&control, "owner")?, source_key),
            "Share belongs to another author project",
            "FORBIDDEN",
        )?;
        Ok(control)
    }
    pub fn revoke_owner(&self, share: &str, source_key: &str) -> Result<Value> {
        self.revoke_control(&self.owner_control(share, source_key)?)
    }
    fn revoke_control(&self, control: &Value) -> Result<Value> {
        let share = string(control, "shareId")?;
        let job = json!({"shareId":share,"state":"revoked","expiresAt":control["expiresAt"],"cleanupAfter":now(),"owner":control["owner"],"dashboardId":control["dashboardId"],"revision":control["revision"],"annotationMode":control.get("annotationMode").cloned().unwrap_or(json!("view")),"annotationsStorage":control["annotationsStorage"]});
        put_json(&self.storage, &format!("jobs/{share}.json"), &job)?;
        if truthy(&control["annotationsStorage"]) {
            self.annotation_store()?
                .call("revoke", &json!({"shareId":share}))?;
        }
        retire_id(&self.storage, share)?;
        put_json(
            &self.storage,
            &format!("shares/{share}/control.json"),
            &merge(control, &json!({"state":"revoked"})),
        )?;
        Ok(
            json!({"shareId":share,"revoked":true,"cleanupState":"pending","cleanupExecutor":self.executor}),
        )
    }
    pub fn replace(
        &self,
        service: &Service,
        board: &str,
        share: &str,
        expected: i64,
        expiration: &str,
    ) -> Result<Value> {
        let previous = self.control(share)?;
        require(
            previous["owner"] == owner(&service.store)? && previous["dashboardId"] == board,
            "Share belongs to another project/dashboard",
            "FORBIDDEN",
        )?;
        let mut key = access_key();
        while equal(
            &key_digest(&key, string(&previous, "salt")?)?,
            string(&previous, "keyHash")?,
        ) {
            key = access_key();
        }
        let mut pages = vec![];
        if let Some(previous_pages) = previous["pages"].as_array() {
            if previous_pages.len() > 1 {
                let versions = Versions::new(&service.store)?;
                for page in previous_pages.iter().skip(1) {
                    let id = string(page, "id")?;
                    let revision = versions.status(id)?["publishedRevision"].clone();
                    require(
                        !revision.is_null(),
                        "Publish each selected page before sharing it",
                        "REVISION_CONFLICT",
                    )?;
                    pages.push(json!({"dashboardId":id,"expectedRevision":revision}));
                }
            }
        }
        let mut result = self.publish(
            service,
            board,
            expected,
            expiration,
            Some(&key),
            if service.project_root.is_some() {
                Some(&pages)
            } else {
                None
            },
            None,
            previous["annotationMode"].as_str().unwrap_or("view"),
        )?;
        let revoked = (|| -> Result<()> {
            let key = format!("jobs/{}.json", string(&result, "shareId")?);
            let job = get_json(&self.storage, &key)?
                .ok_or_else(|| Error::new("NOT_FOUND", "New share job is missing"))?;
            put_json(
                &self.storage,
                &key,
                &merge(&job, &json!({"replacesShareId":share})),
            )?;
            self.revoke(service, board, share)?;
            Ok(())
        })();
        result["previousShareId"] = json!(share);
        result["previousRevoked"] = json!(revoked.is_ok());
        if let Err(error) = revoked {
            result["followUp"] = json!("dashboard_share_delete");
            result["warning"] = json!({"code":"PREVIOUS_SHARE_REVOKE_FAILED","type":error.code});
        }
        Ok(result)
    }
    pub fn content(&self, share: &str, name: &str, control: Option<&Value>) -> Result<Vec<u8>> {
        checked_id(share)?;
        let fetched;
        let control = if let Some(control) = control {
            control
        } else {
            fetched = self.control(share)?;
            &fetched
        };
        let path = Path::new(name);
        require(
            !path.is_absolute()
                && !name.contains('\\')
                && path.components().all(|p| matches!(p, Component::Normal(_)))
                && control["files"]
                    .as_array()
                    .is_some_and(|files| files.iter().any(|v| v == name)),
            "分享文件不存在",
            "NOT_FOUND",
        )?;
        if let Some(entry) = control["assetFiles"].get(name) {
            let registry = CloudAssets::new(string(control, "project")?)?;
            let object = registry.call("object_get", &json!({"id":entry["object"]}))?;
            require(!object.is_null(), "分享数据已删除", "SHARE_UNAVAILABLE")?;
            return registry.read_file(&object, string(entry, "name")?);
        }
        self.storage
            .get(&format!("shares/{share}/site/{name}"))?
            .ok_or_else(|| Error::new("NOT_FOUND", "分享文件不存在"))
    }
    pub fn revoke(&self, service: &Service, board: &str, share: &str) -> Result<Value> {
        let control = self.control(share)?;
        require(
            control["owner"] == owner(&service.store)? && control["dashboardId"] == board,
            "Share belongs to another project/dashboard",
            "FORBIDDEN",
        )?;
        if let Some(registry) = store_assets(&service.store)? {
            self.index_project(&service.store)?;
            registry.call("share_revoke", &json!({"id":share}))?;
        }
        self.revoke_control(&control)
    }
    pub fn status(&self, service: &Service, board: &str, share: Option<&str>) -> Result<Value> {
        if let Some(id) = share {
            checked_id(id)?;
        }
        let owner = owner(&service.store)?;
        let keys = if let Some(id) = share {
            vec![format!("jobs/{id}.json")]
        } else {
            self.storage.list("jobs/")?
        };
        let mut shares = vec![];
        for key in keys {
            let Some(job) = get_json(&self.storage, &key)? else {
                continue;
            };
            if job["owner"] != owner || job["dashboardId"] != board {
                continue;
            }
            let due = job["cleanupAfter"]
                .as_i64()
                .is_some_and(|deadline| now() >= deadline);
            shares.push(json!({"shareId":job["shareId"],"state":if due&&job["state"]=="active"{json!("expired")}else{job["state"].clone()},"revision":job["revision"],"expiresAt":job["expiresAt"],"pages":job.get("pages").cloned().unwrap_or(json!([])),"annotationMode":job.get("annotationMode").cloned().unwrap_or(json!("view")),"replacesShareId":job["replacesShareId"],"cleanupState":if due{"pending"}else if truthy(&job["cleanupAfter"]){"scheduled"}else{"not_scheduled"},"url":format!("{}/s/{}/",self.public_url,string(&job,"shareId")?)}));
        }
        Ok(json!({"shares":shares,"cleanupExecutor":self.executor}))
    }
}
fn zip_error(_: zip::result::ZipError) -> Error {
    Error::new("INVALID_ARGUMENT", "Invalid publication ZIP")
}
fn zip_read<R: Read + Seek>(package: &mut zip::ZipArchive<R>, index: usize) -> Result<Vec<u8>> {
    let mut file = package.by_index(index).map_err(zip_error)?;
    let expected = file.size();
    require(
        expected <= 64 * 1024 * 1024,
        "Publication file is too large",
        "PAYLOAD_TOO_LARGE",
    )?;
    let mut bytes = Vec::new();
    std::io::Read::by_ref(&mut file)
        .take(64 * 1024 * 1024 + 1)
        .read_to_end(&mut bytes)?;
    require(
        bytes.len() as u64 == expected,
        "Publication file size differs",
        "INVALID_ARGUMENT",
    )?;
    Ok(bytes)
}

fn used_references(doc: &Value) -> Map<String, Value> {
    let used = doc["manifest"]["components"]
        .as_object()
        .into_iter()
        .flatten()
        .map(|(_, c)| {
            c["datasetId"]
                .as_str()
                .or(c["binding"]["datasetId"].as_str())
                .unwrap_or("")
        })
        .collect::<HashSet<_>>();
    let mut refs = doc["snapshot"]["datasetRefs"]
        .as_object()
        .into_iter()
        .flatten()
        .filter(|(id, _)| used.contains(id.as_str()))
        .map(|(id, r)| (id.clone(), r.clone()))
        .collect::<Map<String, Value>>();
    for (id, reference) in doc["snapshot"]["componentDataRefs"]
        .as_object()
        .into_iter()
        .flatten()
    {
        if doc["manifest"]["components"].get(id).is_some() {
            refs.insert(format!("component-{id}"), reference.clone());
        }
    }
    refs
}
pub fn web_document<F: FnMut(&str, &str) -> String>(
    store: &Store,
    document: &Value,
    url_for: F,
    editable: bool,
    show_sql: bool,
) -> Result<Value> {
    let registry = store.cloud_assets()?;
    web_document_with_assets(document, url_for, editable, show_sql, |reference| {
        registry.call("object_get", &json!({"version":reference["version"]}))
    })
}
fn web_document_with_assets<F: FnMut(&str, &str) -> String, G: FnMut(&Value) -> Result<Value>>(
    document: &Value,
    mut url_for: F,
    editable: bool,
    show_sql: bool,
    mut dataset_asset: G,
) -> Result<Value> {
    let mut doc = document.clone();
    if !editable {
        let manifest = doc["manifest"]
            .as_object_mut()
            .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Manifest must be an object"))?;
        let sources = manifest.remove("sources").unwrap_or(json!({}));
        if show_sql {
            manifest.insert(
                "sources".into(),
                Value::Object(
                    sources
                        .as_object()
                        .into_iter()
                        .flatten()
                        .filter(|(_, source)| source["kind"] == "query")
                        .map(|(key, source)| {
                            (key.clone(), json!({"query":{"sql":source["query"]["sql"]}}))
                        })
                        .collect(),
                ),
            );
        }
        for key in ["queries", "annotations"] {
            manifest.remove(key);
        }
        for artifact in doc
            .get_mut("statisticalArtifacts")
            .and_then(Value::as_object_mut)
            .into_iter()
            .flatten()
            .map(|(_, v)| v)
        {
            if let Some(object) = artifact.as_object_mut() {
                object.remove("provenance");
            }
        }
    }
    doc["progressive"] = json!(true);
    if truthy(&model::live_datasets(&doc)) {
        return Ok(doc);
    }
    for key in [
        "staticFiles",
        "staticOptions",
        "staticPartitionIndexes",
        "staticComponentDatasets",
        "staticDatasetFields",
    ] {
        doc[key] = json!({});
    }
    doc["staticFilterOptions"] = Value::Object(
        doc["computed"]["filterPages"]
            .as_object()
            .into_iter()
            .flatten()
            .filter(|(_, page)| !truthy(&page["hasMore"]) && !truthy(&page["offset"]))
            .map(|(id, page)| (id.clone(), page["values"].clone()))
            .collect(),
    );
    doc["storageFormat"] = json!("cos-v1");
    doc["versionKey"] = json!(format!(
        "{}:{}",
        string(&doc, "id")?,
        integer(&doc, "revision")?
    ));
    let refs = used_references(&doc);
    for (id, reference) in document["snapshot"]["componentDataRefs"]
        .as_object()
        .into_iter()
        .flatten()
    {
        if document["manifest"]["components"].get(id).is_some() {
            let key = format!("component-{id}");
            doc["staticComponentDatasets"][id] = json!(key);
            doc["staticDatasetFields"][&key] = reference["fields"].clone();
        }
    }
    for (key, reference) in refs {
        let object = dataset_asset(&reference)?;
        require(
            !object.is_null(),
            "Dataset files unavailable",
            "ASSET_UNAVAILABLE",
        )?;
        let id = string(&object, "id")?;
        let descriptor = &object["descriptor"];
        let mut files = vec![];
        for name in descriptor["shards"]
            .as_array()
            .ok_or_else(|| Error::new("ASSET_UNAVAILABLE", "Dataset shards are unavailable"))?
        {
            files.push(json!(url_for(
                id,
                name.as_str()
                    .ok_or_else(|| Error::new("DATA_CONFLICT", "Invalid shard path"))?
            )));
        }
        doc["staticFiles"][&key] = json!(files);
        let mut options = Map::new();
        for (field, entry) in descriptor["options"].as_object().into_iter().flatten() {
            let value = if let Some(name) = entry.as_str() {
                json!(url_for(id, name))
            } else {
                let mut files = vec![];
                for name in entry["files"]
                    .as_array()
                    .ok_or_else(|| Error::new("DATA_CONFLICT", "Invalid option resource"))?
                {
                    files.push(json!(url_for(
                        id,
                        name.as_str()
                            .ok_or_else(|| Error::new("DATA_CONFLICT", "Invalid option path"))?
                    )));
                }
                json!({"field":entry["field"],"files":files})
            };
            options.insert(field.clone(), value);
        }
        doc["staticOptions"][&key] = Value::Object(options);
        if truthy(&descriptor["partitionIndex"]) {
            let index = &descriptor["partitionIndex"];
            let mut entries = vec![];
            for entry in index["entries"]
                .as_array()
                .ok_or_else(|| Error::new("DATA_CONFLICT", "Invalid partition index"))?
            {
                let mut files = vec![];
                for name in entry["files"]
                    .as_array()
                    .ok_or_else(|| Error::new("DATA_CONFLICT", "Invalid partition resource"))?
                {
                    files.push(json!(url_for(
                        id,
                        name.as_str()
                            .ok_or_else(|| Error::new("DATA_CONFLICT", "Invalid partition path"))?
                    )));
                }
                entries.push(json!({"value":entry["value"],"files":files}));
            }
            doc["staticPartitionIndexes"][&key] = json!({"field":index["field"],"entries":entries});
        }
    }
    doc["snapshot"]["datasets"] = json!({});
    Ok(doc)
}
pub fn authorized_file(
    store: &Store,
    document: &Value,
    object_id: &str,
    name: &str,
) -> Result<Vec<u8>> {
    let registry = store.cloud_assets()?;
    let object = registry.call("object_get", &json!({"id":object_id}))?;
    require(
        !object.is_null()
            && object["kind"] == "dataset"
            && used_references(document)
                .values()
                .any(|reference| reference["version"] == object["version"]),
        "File is outside the selected version",
        "FORBIDDEN",
    )?;
    let descriptor = &object["descriptor"];
    let allowed = descriptor["shards"]
        .as_array()
        .into_iter()
        .flatten()
        .any(|v| v == name)
        || descriptor["options"]
            .as_object()
            .into_iter()
            .flatten()
            .any(|(_, entry)| {
                entry == name
                    || entry["files"]
                        .as_array()
                        .into_iter()
                        .flatten()
                        .any(|v| v == name)
            });
    require(allowed, "File is not a browser data resource", "FORBIDDEN")?;
    registry.read_file(&object, name)
}

/// Run only from the configured cloud/timer cleanup command, never from MCP requests.
pub fn cleanup_due(storage: &Storage, at: Option<i64>) -> Result<Value> {
    let now = at.unwrap_or_else(now);
    let mut removed = 0usize;
    let mut failed = vec![];
    let mut handled = HashSet::new();
    let registry_configured = cloud_enabled()?
        || env::var("CHARTS_STORAGE_BACKEND").as_deref() != Ok("cloudflare")
            && env::var("CLOUDBASE_API_KEY").is_ok_and(|v| !v.is_empty());
    for key in storage.list("publication-intents/")? {
        let result = (|| -> Result<()> {
            let Some(intent) = get_json(storage, &key)? else {
                return Ok(());
            };
            let share = checked_id(string(&intent, "shareId")?)?;
            handled.insert(share.to_owned());
            require(
                key == format!("publication-intents/{share}.json"),
                "Invalid publication intent",
                "INVALID_ARGUMENT",
            )?;
            if integer(&intent, "cleanupAfter")? > now
                && storage.get(&format!("retired/{share}"))?.is_none()
            {
                return Ok(());
            }
            if registry_configured {
                let registry = asset_database()?;
                let registered = registry.call("share_access", "", &json!({"id":share}))?;
                if !registered.is_null()
                    && !truthy(&registry.call(
                        "share_cleanup_claim",
                        string(&registered, "project")?,
                        &json!({"id":share,"now":now}),
                    )?)
                {
                    return Ok(());
                }
            }
            let claim = ShareAnnotations::for_storage(storage)?
                .call("cleanup_claim", &json!({"shareId":share,"now":now}))?;
            if claim["claimed"] != true {
                if claim["state"] == "active" {
                    storage.delete_prefix(&key)?;
                } else {
                    put_json(
                        storage,
                        &key,
                        &merge(&intent, &json!({"cleanupAfter":claim["stagingUntil"]})),
                    )?;
                }
                return Ok(());
            }
            retire_id(storage, share)?;
            storage.delete_prefix(&format!("shares/{share}/"))?;
            storage.delete_prefix(&format!("jobs/{share}.json"))?;
            storage.delete_prefix(&key)?;
            removed += 1;
            Ok(())
        })();
        if let Err(error) = result {
            failed.push(json!({"job":key,"type":error.code}));
        }
    }
    for key in storage.list("jobs/")? {
        let result = (|| -> Result<()> {
            let Some(job) = get_json(storage, &key)? else {
                return Ok(());
            };
            let share = checked_id(string(&job, "shareId")?)?;
            handled.insert(share.to_owned());
            require(
                key == format!("jobs/{share}.json"),
                "Invalid cleanup job",
                "INVALID_ARGUMENT",
            )?;
            let mut deadline = job["cleanupAfter"].clone();
            let registry = if registry_configured {
                Some(asset_database()?)
            } else {
                None
            };
            let mut registered = if let Some(registry) = &registry {
                registry.call("share_access", "", &json!({"id":share}))?
            } else {
                Value::Null
            };
            if !registered.is_null() {
                deadline = match registered["state"].as_str() {
                    Some("uploading") => registered["stagingUntil"].clone(),
                    Some("revoked") => json!(0),
                    Some("active") => registered["expiresAt"].clone(),
                    _ => deadline,
                };
            }
            let retired = storage.get(&format!("retired/{share}"))?.is_some();
            if retired {
                deadline = json!(0);
                if !registered.is_null() && registered["state"] != "revoked" {
                    registry.as_ref().unwrap().call(
                        "share_revoke",
                        string(&registered, "project")?,
                        &json!({"id":share}),
                    )?;
                    registered["state"] = json!("revoked");
                }
            }
            if deadline.is_null() || deadline.as_i64().is_some_and(|d| d > now) {
                return Ok(());
            }
            require(
                deadline.as_i64().is_some(),
                "Invalid cleanup deadline",
                "INVALID_ARGUMENT",
            )?;
            if !registered.is_null()
                && !truthy(&registry.as_ref().unwrap().call(
                    "share_cleanup_claim",
                    string(&registered, "project")?,
                    &json!({"id":share,"now":now}),
                )?)
            {
                return Ok(());
            }
            if truthy(&job["annotationsStorage"]) {
                let claimed=ShareAnnotations::for_storage(storage)?.call("cleanup_claim",&json!({"shareId":share,"now":now,"revoked":retired||job["state"]=="revoked"||registered["state"]=="revoked"}))?;
                if claimed["claimed"] != true {
                    return Ok(());
                }
            }
            retire_id(storage, share)?;
            storage.delete_prefix(&format!("shares/{share}/"))?;
            if job["annotationsStorage"] == "postgres-v1" {
                CloudDatabase::new()?
                    .with_function("charts_share_annotations")?
                    .call("delete", "", &json!({"shareId":share}))?;
            }
            storage.delete_prefix(&format!("jobs/{share}.json"))?;
            removed += 1;
            Ok(())
        })();
        if let Err(error) = result {
            failed.push(json!({"job":key,"type":error.code}));
        }
    }
    for key in storage.list("retired/")? {
        let result = (|| -> Result<()> {
            let share = checked_id(key.strip_prefix("retired/").unwrap_or(""))?;
            require(
                key == format!("retired/{share}"),
                "Invalid retired share ID",
                "INVALID_ARGUMENT",
            )?;
            if handled.contains(share) {
                return Ok(());
            }
            let prefix = format!("shares/{share}/");
            if !storage.list(&prefix)?.is_empty() {
                storage.delete_prefix(&prefix)?;
                removed += 1;
            }
            Ok(())
        })();
        if let Err(error) = result {
            failed.push(json!({"job":key,"type":error.code}));
        }
    }
    Ok(json!({"removed":removed,"failed":failed}))
}
pub fn version_delete_preview(
    store: &Store,
    board: &str,
    expected: i64,
    revision: i64,
) -> Result<Value> {
    let manager = CloudShares::from_environment(None)?;
    manager.index_project(store)?;
    let mut plan=store.cloud_assets()?.call("delete_preview",&json!({"board":board,"expected":expected,"revision":revision,"token":uuid::Uuid::new_v4().simple().to_string()}))?;
    if let Some(shares) = plan["shares"].as_array_mut() {
        for share in shares {
            share["url"] = json!(format!(
                "{}/s/{}/",
                manager.public_url,
                string(share, "shareId")?
            ));
        }
    }
    Ok(plan)
}
pub fn version_delete_status(
    store: &Store,
    board: &str,
    job_id: &str,
    retry: bool,
) -> Result<Value> {
    let assets = store.cloud_assets()?;
    let job = assets.call("delete_status", &json!({"board":board,"id":job_id}))?;
    if retry {
        delete_version_job(assets, &job)
    } else {
        Ok(job)
    }
}
pub fn version_delete_checkpoint(
    store: &Store,
    board: &str,
    expected: i64,
    revision: i64,
    confirmation: &str,
) -> Result<Value> {
    require(
        !confirmation.is_empty(),
        "Review deletion impact first",
        "CONFIRMATION_REQUIRED",
    )?;
    let assets = store.cloud_assets()?;
    let job = assets.call(
        "delete_begin",
        &json!({"board":board,"expected":expected,"revision":revision,"token":confirmation}),
    )?;
    delete_version_job(assets, &job)
}
pub fn delete_version_job(assets: &CloudAssets, job: &Value) -> Result<Value> {
    if job["state"] == "complete" {
        return Ok(job.clone());
    }
    let mut completed = job["completed"].as_array().cloned().unwrap_or_default();
    let result = (|| -> Result<Value> {
        for share in job["plan"]["shares"].as_array().into_iter().flatten() {
            let id = checked_id(string(share, "shareId")?)?;
            let key = json!(format!("share:{id}"));
            if completed.contains(&key) {
                continue;
            }
            let storage = Storage::publication()?;
            let metadata = get_json(&storage, &format!("shares/{id}/control.json"))?
                .or(get_json(&storage, &format!("jobs/{id}.json"))?);
            retire_id(&storage, id)?;
            if metadata
                .as_ref()
                .is_some_and(|m| truthy(&m["annotationsStorage"]))
            {
                ShareAnnotations::for_storage(&storage)?.call("delete", &json!({"shareId":id}))?;
            }
            storage.delete_prefix(&format!("shares/{id}/"))?;
            storage.delete_prefix(&format!("jobs/{id}.json"))?;
            storage.delete_prefix(&format!("publication-intents/{id}.json"))?;
            completed.push(key);
            assets.call(
                "delete_progress",
                &json!({"id":job["id"],"completed":completed}),
            )?;
        }
        for object in job["plan"]["objects"].as_array().into_iter().flatten() {
            let key = json!(format!("object:{}", string(object, "id")?));
            if completed.contains(&key) {
                continue;
            }
            assets.delete_prefix(string(object, "prefix")?)?;
            completed.push(key);
            assets.call(
                "delete_progress",
                &json!({"id":job["id"],"completed":completed}),
            )?;
        }
        assets.call("delete_finish", &json!({"id":job["id"]}))
    })();
    match result {
        Ok(result) => Ok(result),
        Err(error) => assets.call(
            "delete_progress",
            &json!({"id":job["id"],"completed":completed,"error":error.code}),
        ),
    }
}
pub fn cleanup_asset_jobs() -> Result<Value> {
    let database = asset_database()?;
    let pending = database.call("pending", "", &json!({}))?;
    let mut removed = 0;
    let mut failed = vec![];
    for entry in pending
        .as_array()
        .ok_or_else(|| Error::new("CLOUD_DATABASE_FAILED", "Invalid deletion job list"))?
    {
        let assets = CloudAssets::with_database(string(entry, "project")?, database.clone());
        let job = assets.call(
            "delete_status",
            &json!({"id":entry["id"],"board":entry["board"]}),
        )?;
        let outcome = delete_version_job(&assets, &job)?;
        if outcome["state"] == "complete" {
            removed += 1;
        } else {
            failed.push(json!({"job":entry["id"],"type":outcome["error"]}));
        }
    }
    Ok(json!({"removed":removed,"failed":failed}))
}

#[cfg(test)]
#[path = "../../tests/unit/shares.rs"]
mod tests;
