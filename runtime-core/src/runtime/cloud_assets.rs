//! Immutable cloud packages and recoverable PostgreSQL reference operations.
use super::{
    cloud::CloudDatabase,
    data::LocalData,
    error::{require, Error, Result},
    object_storage::{file_digest, Storage},
    serialization::{json_bytes, python_json},
};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    path::Path,
    sync::{Arc, Mutex},
};

#[derive(Clone)]
pub struct CloudAssets {
    pub project: String,
    pub database: CloudDatabase,
    storage: Arc<Mutex<Option<Storage>>>,
}
impl CloudAssets {
    pub fn new(project: &str) -> Result<Self> {
        Ok(Self::with_database(
            project,
            CloudDatabase::new()?.with_function("charts_assets")?,
        ))
    }
    pub fn with_database(project: &str, database: CloudDatabase) -> Self {
        Self {
            project: project.into(),
            database,
            storage: Arc::new(Mutex::new(None)),
        }
    }
    fn storage(&self) -> Result<Storage> {
        let mut storage = self
            .storage
            .lock()
            .map_err(|_| Error::new("INTERNAL_ERROR", "Asset storage lock failed"))?;
        if storage.is_none() {
            *storage = Some(Storage::assets()?);
        }
        Ok(storage.as_ref().unwrap().clone())
    }
    pub fn call(&self, action: &str, payload: &Value) -> Result<Value> {
        self.database.call(action, &self.project, payload)
    }
    pub fn delete_prefix(&self, prefix: &str) -> Result<()> {
        self.storage()?.delete_prefix(prefix)
    }
    pub fn read_file(&self, object: &Value, name: &str) -> Result<Vec<u8>> {
        let entry = object["descriptor"]["files"]
            .get(name)
            .ok_or_else(|| Error::new("NOT_FOUND", "Object file is not registered"))?;
        let prefix = object["prefix"]
            .as_str()
            .ok_or_else(|| Error::new("DATA_CONFLICT", "Object prefix is missing"))?;
        let bytes = entry["bytes"]
            .as_u64()
            .ok_or_else(|| Error::new("DATA_CONFLICT", "Object byte count is missing"))?;
        let raw = self
            .storage()?
            .get_bounded(&format!("{prefix}{name}"), bytes)?
            .ok_or_else(|| Error::new("CLOUD_FILE_MISSING", "Cloud object is missing"))?;
        require(
            raw.len() as u64 == bytes
                && hex::encode(Sha256::digest(&raw)) == entry["sha256"].as_str().unwrap_or(""),
            "Cloud object checksum mismatch",
            "CLOUD_FILE_CORRUPT",
        )?;
        Ok(raw)
    }
    pub fn download_file(&self, object: &Value, name: &str, target: &Path) -> Result<()> {
        let entry = object["descriptor"]["files"]
            .get(name)
            .ok_or_else(|| Error::new("NOT_FOUND", "Object file is not registered"))?;
        let prefix = object["prefix"]
            .as_str()
            .ok_or_else(|| Error::new("DATA_CONFLICT", "Object prefix is missing"))?;
        let bytes = entry["bytes"]
            .as_u64()
            .ok_or_else(|| Error::new("DATA_CONFLICT", "Object byte count is missing"))?;
        require(
            self.storage()?.download_file(
                &format!("{prefix}{name}"),
                target,
                Some(bytes),
                entry["sha256"].as_str().unwrap_or(""),
            )?,
            "Cloud object is missing",
            "CLOUD_FILE_MISSING",
        )
    }
    fn put(
        storage: &Storage,
        object: &Value,
        files: &mut Map<String, Value>,
        name: &str,
        raw: &[u8],
        kind: &str,
    ) -> Result<()> {
        let prefix = object["prefix"]
            .as_str()
            .ok_or_else(|| Error::new("DATA_CONFLICT", "Object prefix is missing"))?;
        storage.put(&format!("{prefix}{name}"), raw, kind)?;
        files.insert(
            name.into(),
            json!({"bytes":raw.len(),"sha256":hex::encode(Sha256::digest(raw))}),
        );
        Ok(())
    }
    pub fn save_dataset(
        &self,
        data: &LocalData,
        reference: &Value,
        partition_field: Option<&str>,
    ) -> Result<Value> {
        let version = reference["version"]
            .as_str()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid data version"))?;
        require(
            version.len() == 64
                && version
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
            "Invalid data version",
            "INVALID_ARGUMENT",
        )?;
        let existing = self.call("object_get", &json!({"version":version}))?;
        if !existing.is_null() {
            require(
                existing["descriptor"]["metadata"] == *reference,
                "Remote data metadata differs",
                "DATA_CONFLICT",
            )?;
            return Ok(existing);
        }
        let temp = tempfile::tempdir()?;
        let package = temp.path().join("package");
        fs::create_dir(&package)?;
        let (source, metadata) = data.sqlite_source(reference)?;
        require(
            metadata == *reference,
            "Local data reference differs",
            "DATA_CONFLICT",
        )?;
        let receipt = crate::export_parquet_with_options(
            &source,
            version,
            &package,
            &crate::ExportOptions {
                partition_field: partition_field.map(str::to_owned),
                include_options: true,
                single_file: false,
            },
        )
        .map_err(|_| Error::new("PARQUET_EXPORT_FAILED", "Native Parquet export failed"))?;
        let receipt = serde_json::to_value(receipt)?;
        let query = temp.path().join("query.sqlite3");
        {
            let mut db = rusqlite::Connection::open(&query)?;
            db.execute(
                "ATTACH DATABASE ? AS source",
                [source.to_string_lossy().as_ref()],
            )?;
            let tx = db.transaction()?;
            tx.execute_batch(&format!("CREATE TABLE d_{version} AS SELECT * FROM source.d_{version} ORDER BY rowid;CREATE TABLE versions(version TEXT PRIMARY KEY,metadata TEXT NOT NULL)"))?;
            tx.execute(
                "INSERT INTO versions VALUES(?,?)",
                rusqlite::params![version, serde_json::to_string(reference)?],
            )?;
            for i in 0..reference["fieldOrder"].as_array().map_or(0, Vec::len) {
                tx.execute_batch(&format!("CREATE INDEX i_{i} ON d_{version}(c{i})"))?;
            }
            tx.commit()?;
        }
        let object=self.call("reserve",&json!({"id":uuid::Uuid::new_v4().simple().to_string(),"kind":"dataset","version":version}))?;
        let storage = self.storage()?;
        let mut files = Map::new();
        let mut resources = receipt["files"].as_array().cloned().unwrap_or_default();
        if let Some(options) = receipt["options"].as_object() {
            for values in options.values() {
                resources.extend(values.as_array().cloned().unwrap_or_default());
            }
        }
        let prefix = object["prefix"]
            .as_str()
            .ok_or_else(|| Error::new("DATA_CONFLICT", "Object prefix is missing"))?;
        for window in resources.chunks(4) {
            let uploaded = std::thread::scope(|scope| {
                let workers = window
                    .iter()
                    .map(|entry| {
                        let storage = &storage;
                        let package = &package;
                        scope.spawn(move || -> Result<(String, Value)> {
                            let name = entry["path"].as_str().ok_or_else(|| {
                                Error::new("DATA_CONFLICT", "Invalid Parquet receipt")
                            })?;
                            let path = package.join(name);
                            let (bytes, hash) = file_digest(&path)?;
                            require(
                                entry["sha256"] == hash && entry["bytes"] == bytes,
                                "Parquet receipt checksum mismatch",
                                "DATA_CONFLICT",
                            )?;
                            storage.put_file(
                                &format!("{prefix}{name}"),
                                &path,
                                "application/octet-stream",
                            )?;
                            Ok((name.to_string(), json!({"bytes":bytes,"sha256":hash})))
                        })
                    })
                    .collect::<Vec<_>>();
                workers
                    .into_iter()
                    .map(|worker| {
                        worker
                            .join()
                            .map_err(|_| {
                                Error::new("CLOUD_STORAGE_FAILED", "Asset upload worker stopped")
                            })
                            .and_then(|result| result)
                    })
                    .collect::<Vec<_>>()
            });
            for result in uploaded {
                let (name, metadata) = result?;
                files.insert(name, metadata);
            }
        }
        let (bytes, hash) = file_digest(&query)?;
        storage.put_file(
            &format!("{prefix}query.sqlite3"),
            &query,
            "application/octet-stream",
        )?;
        files.insert("query.sqlite3".into(), json!({"bytes":bytes,"sha256":hash}));
        let mut descriptor = json!({"format":"cos-dataset-v1","queryFormat":1,"metadata":reference,"files":files,"bytes":files.values().map(|e|e["bytes"].as_u64().unwrap_or(0)).sum::<u64>()});
        for (key, value) in parquet_resources(&receipt)?.as_object().unwrap() {
            descriptor[key] = value.clone();
        }
        let manifest = json_bytes(&descriptor)?;
        Self::put(
            &storage,
            &object,
            &mut files,
            "manifest.json",
            &manifest,
            "application/json",
        )?;
        descriptor["files"] = json!(files);
        descriptor["bytes"] = json!(files
            .values()
            .map(|e| e["bytes"].as_u64().unwrap_or(0))
            .sum::<u64>());
        self.call("ready", &json!({"id":object["id"],"descriptor":descriptor}))
    }
    pub fn save_document(&self, doc: &Value) -> Result<Value> {
        let mut content = doc.clone();
        if let Some(manifest) = content["manifest"].as_object_mut() {
            manifest.remove("annotations");
        }
        let build = super::assets::backend_build_id();
        let identity = json!({"id":content["id"],"revision":content["revision"],"manifest":content["manifest"],"snapshot":content["snapshot"],"engineBuild":build});
        let digest = hex::encode(Sha256::digest(
            python_json(&identity, true, true)?.as_bytes(),
        ));
        let mut object = self.call("object_get", &json!({"kind":"document","version":digest}))?;
        if object.is_null() {
            object=self.call("reserve",&json!({"id":uuid::Uuid::new_v4().simple().to_string(),"kind":"document","version":digest}))?;
            let mut files = Map::new();
            Self::put(
                &self.storage()?,
                &object,
                &mut files,
                "document.json",
                &json_bytes(&content)?,
                "application/json",
            )?;
            let bytes = files
                .values()
                .map(|e| e["bytes"].as_u64().unwrap_or(0))
                .sum::<u64>();
            self.call("ready",&json!({"id":object["id"],"descriptor":{"format":"cos-document-v1","queryFormat":1,"engineBuild":build,"files":files,"bytes":bytes}}))?;
        }
        let components:Map<String,Value>=doc["manifest"]["components"].as_object().into_iter().flat_map(|m|m.iter()).map(|(key,value)|(key.clone(),json!({"title":value.get("title").cloned().unwrap_or(json!("")),"kind":value["kind"]}))).collect();
        Ok(
            json!({"id":doc["id"],"revision":doc["revision"],"cosObject":object["id"],"manifest":{"title":doc["manifest"]["title"],"viewMode":doc["manifest"]["viewMode"],"filters":doc["manifest"]["filters"],"components":components,"annotations":doc["manifest"].get("annotations").cloned().unwrap_or(json!([]))},"snapshot":{"datasetRefs":doc["snapshot"].get("datasetRefs").cloned().unwrap_or(json!({})),"componentDataRefs":doc["snapshot"].get("componentDataRefs").cloned().unwrap_or(json!({}))}}),
        )
    }
    pub fn hydrate_document(&self, envelope: &Value) -> Result<Value> {
        if envelope.get("cosObject").is_none() {
            return Ok(envelope.clone());
        }
        let object = self.call("object_get", &json!({"id":envelope["cosObject"]}))?;
        require(
            !object.is_null(),
            "Version content is unavailable",
            "ASSET_UNAVAILABLE",
        )?;
        let mut document: Value =
            serde_json::from_slice(&self.read_file(&object, "document.json")?)?;
        document["revision"] = envelope["revision"].clone();
        document["manifest"]["annotations"] = envelope["manifest"]
            .get("annotations")
            .cloned()
            .unwrap_or(json!([]));
        Ok(document)
    }
    pub fn delete_job(&self, job: &Value) -> Result<Value> {
        super::shares::delete_version_job(self, job)
    }
}
pub fn parquet_resources(receipt: &Value) -> Result<Value> {
    let options:Map<String,Value>=receipt["options"].as_object().into_iter().flat_map(|m|m.iter()).map(|(field,files)|(field.clone(),json!({"field":field,"files":files.as_array().into_iter().flatten().map(|f|f["path"].clone()).collect::<Vec<_>>()}))).collect();
    let mut result = json!({"dataFormat":receipt["format"],"shards":receipt["files"].as_array().into_iter().flatten().map(|v|v["path"].clone()).collect::<Vec<_>>(),"options":options});
    if let Some(index) = receipt.get("partitionIndex") {
        result["partitionIndex"] = index.clone();
    }
    Ok(result)
}
pub fn encode_document(project: &str, doc: &Value) -> Result<Value> {
    CloudAssets::new(project)?.save_document(doc)
}
pub fn decode_document(project: &str, doc: &Value) -> Result<Value> {
    if doc.get("cosObject").is_none() {
        Ok(doc.clone())
    } else {
        CloudAssets::new(project)?.hydrate_document(doc)
    }
}

pub fn save_file(project: &str, relative: &str, path: &Path) -> Result<String> {
    let mut staged = tempfile::NamedTempFile::new()?;
    std::io::copy(&mut fs::File::open(path)?, &mut staged)?;
    let (_, digest) = file_digest(staged.path())?;
    let key = format!("{project}/{digest}");
    Storage::assets()?.put_file(
        &key,
        staged.path(),
        mime_guess::from_path(path).first_or_octet_stream().as_ref(),
    )?;
    CloudDatabase::new()?.call("file_put", project, &json!({"path":relative,"key":key}))?;
    Ok(key)
}
pub fn restore_file(project: &str, relative: &str, target: &Path) -> Result<bool> {
    let key = CloudDatabase::new()?.call("file_get", project, &json!({"path":relative}))?;
    if key.is_null() {
        return Ok(false);
    }
    let key = key
        .as_str()
        .ok_or_else(|| Error::new("DATA_CONFLICT", "Invalid file reference"))?;
    require(
        Storage::assets()?.download_file(
            key,
            target,
            None,
            key.rsplit('/').next().unwrap_or(""),
        )?,
        "Stored file is missing",
        "CLOUD_FILE_MISSING",
    )?;
    Ok(true)
}
