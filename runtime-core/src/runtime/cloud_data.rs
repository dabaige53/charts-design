//! Durable dataset versions backed by cloud packages or legacy ordered chunks.
use super::{
    cloud::CloudDatabase,
    cloud_assets::CloudAssets,
    data::LocalData,
    error::{require, Error, Result},
};
use serde_json::{json, Map, Value};
use std::{
    collections::{HashSet, VecDeque},
    path::PathBuf,
    sync::{Arc, Mutex},
    thread::JoinHandle,
};

#[derive(Clone)]
pub struct CloudData {
    pub local: LocalData,
    pub project: String,
    pub database: CloudDatabase,
    pub assets: CloudAssets,
    pub cos_enabled: bool,
    pub(crate) restore: Arc<Mutex<()>>,
    partition_fields: Arc<Mutex<Vec<String>>>,
}
impl CloudData {
    pub fn new(local: LocalData, project: &str, cos_enabled: bool) -> Result<Self> {
        Ok(Self {
            local,
            project: project.into(),
            database: CloudDatabase::new()?,
            assets: CloudAssets::new(project)?,
            cos_enabled,
            restore: Arc::new(Mutex::new(())),
            partition_fields: Arc::new(Mutex::new(Vec::new())),
        })
    }
    pub fn set_partition_fields(&self, fields: &[String]) -> Result<()> {
        *self.partition_fields.lock().map_err(|_| {
            Error::new(
                "INTERNAL_ERROR",
                "Dataset partition configuration lock failed",
            )
        })? = fields.to_vec();
        Ok(())
    }
    pub fn describe(&self, version: &str) -> Result<Value> {
        check_version(version)?;
        let mut value =
            self.database
                .call("data_get", &self.project, &json!({"version":version}))?;
        require(
            !value.is_null(),
            "Unknown durable data version",
            "NOT_FOUND",
        )?;
        value["fields"] = ordered_fields(&value)?;
        Ok(value)
    }
    pub fn persist_cached(&self, reference: &Value) -> Result<Value> {
        self.persist_cached_progress(reference, &|_| {})
    }
    pub(crate) fn persist_cached_progress(
        &self,
        reference: &Value,
        progress: &dyn Fn(u64),
    ) -> Result<Value> {
        if self.cos_enabled {
            let partition_field = self
                .partition_fields
                .lock()
                .map_err(|_| {
                    Error::new(
                        "INTERNAL_ERROR",
                        "Dataset partition configuration lock failed",
                    )
                })?
                .iter()
                .find(|field| {
                    matches!(
                        reference["fields"][field.as_str()]["type"].as_str(),
                        Some("date" | "string")
                    )
                })
                .cloned();
            self.assets
                .save_dataset(&self.local, reference, partition_field.as_deref())?;
            progress(reference["rowCount"].as_u64().unwrap_or(0).div_ceil(500));
            return Ok(reference.clone());
        }
        let version = reference["version"]
            .as_str()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid data version"))?;
        check_version(version)?;
        let previous =
            self.database
                .call("data_get", &self.project, &json!({"version":version}))?;
        if !previous.is_null() {
            require(
                previous == *reference,
                "Remote data metadata differs",
                "DATA_CONFLICT",
            )?;
            return Ok(previous);
        }
        let mut chunk = Vec::with_capacity(500);
        let mut part = 0usize;
        self.local
            .for_each_row(reference, &[], None, &[], "", |row| {
                chunk.push(row);
                if chunk.len() == 500 {
                    self.database.call(
                        "data_chunk_put",
                        &self.project,
                        &json!({"version":version,"part":part,"rows":chunk}),
                    )?;
                    chunk.clear();
                    part += 1;
                    progress(part as u64);
                }
                Ok(())
            })?;
        if !chunk.is_empty() {
            self.database.call(
                "data_chunk_put",
                &self.project,
                &json!({"version":version,"part":part,"rows":chunk}),
            )?;
            progress(part as u64 + 1);
        }
        let saved =
            self.database
                .call("data_finish", &self.project, &json!({"metadata":reference}))?;
        require(
            saved == *reference,
            "Remote data metadata differs from this version",
            "DATA_CONFLICT",
        )?;
        Ok(saved)
    }
    pub fn ensure_version(&self, version: &str) -> Result<PathBuf> {
        check_version(version)?;
        if self.cos_enabled {
            // Always confirm authority before serving a cached package, including after deletion.
            let object = self
                .assets
                .call("object_get", &json!({"version":version}))?;
            require(
                !object.is_null(),
                "Data version is unavailable",
                "ASSET_UNAVAILABLE",
            )?;
            require(
                object["descriptor"]["queryFormat"] == 1,
                "Unsupported query file format",
                "DATA_CONFLICT",
            )?;
            let id = object["id"]
                .as_str()
                .ok_or_else(|| Error::new("DATA_CONFLICT", "Invalid object ID"))?;
            require(
                id.len() == 32 && id.bytes().all(|b| b.is_ascii_hexdigit()),
                "Invalid object ID",
                "DATA_CONFLICT",
            )?;
            let target = self
                .local
                .root
                .as_ref()
                .ok_or_else(|| Error::new("INVALID_CONFIG", "Cloud data needs a runtime cache"))?
                .join(format!("{id}.sqlite3"));
            let _guard = self
                .restore
                .lock()
                .map_err(|_| Error::new("INTERNAL_ERROR", "Dataset restore lock failed"))?;
            if !target.is_file() {
                self.assets
                    .download_file(&object, "query.sqlite3", &target)?;
            }
            let db = rusqlite::Connection::open_with_flags(
                &target,
                rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY,
            )?;
            let raw: String = db.query_row(
                "SELECT metadata FROM versions WHERE version=?",
                [version],
                |r| r.get(0),
            )?;
            let metadata: Value = serde_json::from_str(&raw)?;
            require(
                metadata == object["descriptor"]["metadata"],
                "Remote dataset metadata mismatch",
                "DATA_CONFLICT",
            )?;
            Ok(target.canonicalize()?)
        } else {
            let metadata = self.describe(version)?;
            let _guard = self
                .restore
                .lock()
                .map_err(|_| Error::new("INTERNAL_ERROR", "Dataset restore lock failed"))?;
            if self.local.describe(version).is_err() {
                let count = metadata["rowCount"]
                    .as_u64()
                    .ok_or_else(|| Error::new("DATA_CONFLICT", "Invalid row count"))?;
                let database = self.database.clone();
                let project = self.project.clone();
                let version = version.to_owned();
                let iterator = ChunkRows::new(count, 500, move |part| {
                    database.call(
                        "data_chunk_get",
                        &project,
                        &json!({"version":version,"part":part}),
                    )
                });
                let fields = ordered_fields(&metadata)?;
                let restored = self.local.import_iter(iterator, &fields)?;
                require(
                    restored == metadata,
                    "Remote dataset checksum mismatch",
                    "DATA_CONFLICT",
                )?;
            } else {
                require(
                    self.local.describe(version)? == metadata,
                    "Cached dataset metadata mismatch",
                    "DATA_CONFLICT",
                )?;
            }
            self.local
                .path
                .as_ref()
                .ok_or_else(|| Error::new("INVALID_CONFIG", "Cloud data needs a runtime cache"))?
                .canonicalize()
                .map_err(Into::into)
        }
    }
    pub fn repartition(&self, reference: &Value, field: &str) -> Result<Value> {
        require(
            self.cos_enabled,
            "Repartitioning requires COS project storage",
            "UNSUPPORTED_OPERATION",
        )?;
        let version = reference["version"]
            .as_str()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid data version"))?;
        check_version(version)?;
        require(
            matches!(
                reference["fields"][field]["type"].as_str(),
                Some("string" | "date")
            ),
            "Partition field must be a declared string or date field",
            "INVALID_ARGUMENT",
        )?;
        let object = self
            .assets
            .call("object_get", &json!({"version":version}))?;
        require(
            !object.is_null() && object["descriptor"]["metadata"] == *reference,
            "Remote data metadata differs",
            "DATA_CONFLICT",
        )?;
        if object["descriptor"]["partitionIndex"]["field"] == field {
            return Ok(reference.clone());
        }
        let mut keys = reference["fieldOrder"]
            .as_array()
            .cloned()
            .unwrap_or_default();
        require(
            keys.len() > 1,
            "Repartitioning requires at least two fields for a replacement version",
            "UNSUPPORTED_OPERATION",
        )?;
        let first = keys[0] == field;
        keys.retain(|v| v != field);
        if first {
            keys.push(json!(field));
        } else {
            keys.insert(0, json!(field));
        }
        let fields: Map<String, Value> = keys
            .iter()
            .map(|k| {
                let k = k.as_str().unwrap();
                (k.to_string(), reference["fields"][k].clone())
            })
            .collect();
        let directory = tempfile::tempdir()?;
        let target = LocalData::new(Some(directory.path()))?;
        let path = self.ensure_version(version)?;
        self.local.mount_version(version, &path)?;
        // A bounded channel retains stream order without materializing the dataset.
        let (send, receive) = std::sync::mpsc::sync_channel(512);
        let local = self.local.clone();
        let reference = reference.clone();
        let source = reference.clone();
        let worker = std::thread::spawn(move || {
            local.for_each_row(&source, &[], None, &[], "", |row| {
                send.send(Ok(row))
                    .map_err(|_| Error::new("DATA_INCOMPLETE", "Repartition import stopped"))
            })
        });
        let imported = target.import_iter(receive, &Value::Object(fields));
        let source_result = worker
            .join()
            .map_err(|_| Error::new("DATA_INCOMPLETE", "Repartition source stopped"))?;
        source_result?;
        let replacement = imported?;
        require(
            replacement["rowCount"] == reference["rowCount"]
                && replacement["fields"] == reference["fields"],
            "Repartitioning changed the source data metadata",
            "DATA_CONFLICT",
        )?;
        let object = self
            .assets
            .save_dataset(&target, &replacement, Some(field))?;
        require(
            object["descriptor"]["metadata"] == replacement
                && object["descriptor"]["partitionIndex"]["field"] == field,
            "Replacement version already exists with a different layout",
            "DATA_CONFLICT",
        )?;
        Ok(replacement)
    }
}
fn check_version(version: &str) -> Result<()> {
    require(
        version.len() == 64
            && version
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "Invalid data version",
        "INVALID_ARGUMENT",
    )
}
pub(crate) fn ordered_fields(metadata: &Value) -> Result<Value> {
    let source = metadata["fields"]
        .as_object()
        .ok_or_else(|| Error::new("DATA_CONFLICT", "Invalid dataset fields"))?;
    let fallback = source.keys().map(|key| json!(key)).collect::<Vec<_>>();
    let order = match metadata.get("fieldOrder") {
        Some(value) => value
            .as_array()
            .ok_or_else(|| Error::new("DATA_CONFLICT", "Invalid field order"))?,
        None => &fallback,
    };
    require(
        order.len() == source.len(),
        "Invalid field order",
        "DATA_CONFLICT",
    )?;
    let mut fields = Map::new();
    let mut seen = HashSet::new();
    for key in order {
        let key = key
            .as_str()
            .ok_or_else(|| Error::new("DATA_CONFLICT", "Invalid field order"))?;
        require(
            seen.insert(key) && source.contains_key(key),
            "Invalid field order",
            "DATA_CONFLICT",
        )?;
        fields.insert(key.into(), source[key].clone());
    }
    Ok(Value::Object(fields))
}

/// Fetch up to four chunks ahead, emit rows in content-hash order, and join all
/// workers on either successful completion or an early import error.
pub(crate) struct ChunkRows {
    count: u64,
    size: u64,
    next_part: u64,
    pending: VecDeque<(u64, JoinHandle<Result<Value>>)>,
    rows: VecDeque<Value>,
    fetch: Arc<dyn Fn(u64) -> Result<Value> + Send + Sync>,
    progress: Option<Arc<dyn Fn(u64) + Send + Sync>>,
    failed: bool,
}
impl ChunkRows {
    pub(crate) fn new(
        count: u64,
        size: u64,
        fetch: impl Fn(u64) -> Result<Value> + Send + Sync + 'static,
    ) -> Self {
        Self {
            count,
            size,
            next_part: 0,
            pending: VecDeque::new(),
            rows: VecDeque::new(),
            fetch: Arc::new(fetch),
            progress: None,
            failed: false,
        }
    }
    pub(crate) fn with_progress(mut self, progress: impl Fn(u64) + Send + Sync + 'static) -> Self {
        self.progress = Some(Arc::new(progress));
        self
    }
}
impl Iterator for ChunkRows {
    type Item = Result<Value>;
    fn next(&mut self) -> Option<Self::Item> {
        if self.failed {
            return None;
        }
        if let Some(row) = self.rows.pop_front() {
            return Some(Ok(row));
        }
        while self.pending.len() < 4 && self.next_part < self.count.div_ceil(self.size) {
            let part = self.next_part;
            self.next_part += 1;
            let fetch = self.fetch.clone();
            self.pending
                .push_back((part, std::thread::spawn(move || fetch(part))));
        }
        let (part, worker) = self.pending.pop_front()?;
        let result = worker
            .join()
            .map_err(|_| Error::new("DATA_INCOMPLETE", "Dataset chunk worker stopped"))
            .and_then(|result| result)
            .and_then(|value| {
                let Value::Array(rows) = value else {
                    return Err(Error::new(
                        "DATA_INCOMPLETE",
                        "Remote data chunk is missing",
                    ));
                };
                require(
                    rows.len() as u64 == self.size.min(self.count - part * self.size),
                    "Remote data chunk has an invalid row count",
                    "DATA_INCOMPLETE",
                )?;
                Ok(rows)
            });
        match result {
            Ok(rows) => {
                self.rows = rows.into();
                if let Some(progress) = &self.progress {
                    progress(part + 1);
                }
                self.rows.pop_front().map(Ok)
            }
            Err(error) => {
                self.failed = true;
                Some(Err(error))
            }
        }
    }
}
impl Drop for ChunkRows {
    fn drop(&mut self) {
        for (_, worker) in self.pending.drain(..) {
            let _ = worker.join();
        }
    }
}

#[cfg(test)]
#[path = "../../tests/unit/cloud_data.rs"]
mod tests;
