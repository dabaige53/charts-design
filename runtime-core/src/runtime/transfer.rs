//! Resumable, bounded dataset transfers with content-address verification.
#[path = "transfer_client.rs"]
mod client;
use super::{
    cloud_data::{ordered_fields, ChunkRows, CloudData},
    error::{require, Error, Result},
    object_storage::Storage,
    serialization::json_bytes,
    service::{string, Service},
};
use base64::{engine::general_purpose::STANDARD, Engine};
pub use client::{command, remote_command};
use flate2::{bufread::GzDecoder, Compression, GzBuilder};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{HashMap, HashSet},
    io::{Cursor, Read, Write},
    sync::{Arc, Mutex, OnceLock, Weak},
};

pub const TRANSFER_ROWS: u64 = 250;
pub const BULK_ROWS: u64 = 5_000;
pub const BULK_COMPRESSED: usize = 8 * 1024 * 1024;
pub const BULK_DECODED: usize = 16 * 1024 * 1024;
pub const BULK_ENCODING: &str = "gzip-json-v1";
const BULK_ENCODED: usize = 4 * BULK_COMPRESSED.div_ceil(3);
const TRANSFER_DECODED: usize = 2 * 1024 * 1024;

pub fn reference(value: &Value) -> Result<(&str, u64)> {
    let version = value["version"]
        .as_str()
        .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid data version"))?;
    check_identifier(version, "Invalid data version")?;
    let count = value["rowCount"]
        .as_u64()
        .filter(|n| *n <= 10_000_000)
        .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid row count"))?;
    let fields = value["fields"]
        .as_object()
        .filter(|m| !m.is_empty())
        .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid data fields"))?;
    let order = value["fieldOrder"]
        .as_array()
        .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid field order"))?;
    let keys = order
        .iter()
        .map(Value::as_str)
        .collect::<Option<HashSet<_>>>()
        .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid field order"))?;
    require(
        order.len() == fields.len()
            && keys.len() == fields.len()
            && fields.keys().all(|key| keys.contains(key.as_str())),
        "Invalid field order",
        "INVALID_ARGUMENT",
    )?;
    Ok((version, count))
}
fn check_identifier(value: &str, message: &str) -> Result<()> {
    require(
        value.len() == 64
            && value
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        message,
        "INVALID_ARGUMENT",
    )
}
fn upload_reference<'a>(upload: &str, value: &'a Value, separate: bool) -> Result<(&'a str, u64)> {
    let (version, count) = reference(value)?;
    check_identifier(upload, "Invalid upload ID")?;
    require(
        !separate || upload != version,
        "Upload ID must differ from data version",
        "INVALID_ARGUMENT",
    )?;
    Ok((version, count))
}
pub fn encode_bulk(raw: &[u8]) -> Result<String> {
    require(
        raw.len() <= BULK_DECODED,
        "Bulk chunk exceeds 16 MiB decoded",
        "INVALID_ARGUMENT",
    )?;
    let compressed = gzip(raw)?;
    require(
        compressed.len() <= BULK_COMPRESSED,
        "Bulk chunk exceeds 8 MiB compressed",
        "INVALID_ARGUMENT",
    )?;
    Ok(STANDARD.encode(compressed))
}
fn gzip(raw: &[u8]) -> Result<Vec<u8>> {
    let mut encoder = GzBuilder::new()
        .mtime(0)
        .write(Vec::new(), Compression::new(3));
    encoder.write_all(raw)?;
    Ok(encoder.finish()?)
}
pub fn bulk_binary(payload: &str) -> Result<Vec<u8>> {
    require(
        payload.len() <= BULK_ENCODED,
        "Bulk chunk exceeds encoded size limit",
        "INVALID_ARGUMENT",
    )?;
    let compressed = STANDARD
        .decode(payload)
        .map_err(|_| Error::new("INVALID_DOCUMENT", "Invalid bulk chunk Base64"))?;
    require(
        compressed.len() <= BULK_COMPRESSED,
        "Bulk chunk exceeds 8 MiB compressed",
        "INVALID_ARGUMENT",
    )?;
    Ok(compressed)
}
fn decompress(compressed: &[u8], limit: usize) -> Result<Vec<u8>> {
    require(
        compressed.len() <= BULK_COMPRESSED,
        "Transfer chunk exceeds compressed size limit",
        "INVALID_ARGUMENT",
    )?;
    let mut decoder = GzDecoder::new(Cursor::new(compressed));
    let mut raw = Vec::new();
    decoder
        .by_ref()
        .take((limit + 1) as u64)
        .read_to_end(&mut raw)
        .map_err(|_| Error::new("INVALID_DOCUMENT", "Invalid transfer chunk gzip"))?;
    require(
        raw.len() <= limit,
        "Transfer chunk exceeds decoded size limit",
        "INVALID_ARGUMENT",
    )?;
    require(
        decoder.get_ref().position() == compressed.len() as u64,
        "Invalid transfer chunk gzip trailing data",
        "INVALID_DOCUMENT",
    )?;
    Ok(raw)
}
pub fn bulk_raw(compressed: &[u8]) -> Result<Vec<u8>> {
    decompress(compressed, BULK_DECODED)
}
pub fn bulk_rows(raw: &[u8], expected: u64) -> Result<Value> {
    let value: Value = serde_json::from_slice(raw)
        .map_err(|_| Error::new("INVALID_DOCUMENT", "Invalid bulk chunk JSON"))?;
    require(
        value
            .as_array()
            .is_some_and(|rows| rows.len() as u64 == expected && rows.iter().all(Value::is_object)),
        "Invalid chunk rows",
        "INVALID_ARGUMENT",
    )?;
    require(
        json_bytes(&value)? == raw,
        "Bulk chunk must use canonical JSON",
        "INVALID_ARGUMENT",
    )?;
    Ok(value)
}

trait TransferBackend: Send + Sync {
    fn metadata(&self, version: &str) -> Result<Value>;
    fn storage(&self) -> Result<Storage>;
    fn save(
        &self,
        rows: ChunkRows,
        reference: &Value,
        progress: Arc<dyn Fn(u64) + Send + Sync>,
    ) -> Result<Value>;
}
struct CloudBackend(Arc<CloudData>);
impl TransferBackend for CloudBackend {
    fn metadata(&self, version: &str) -> Result<Value> {
        self.0
            .database
            .call("data_get", &self.0.project, &json!({"version":version}))
    }
    fn storage(&self) -> Result<Storage> {
        Storage::publication()
    }
    fn save(
        &self,
        rows: ChunkRows,
        reference: &Value,
        progress: Arc<dyn Fn(u64) + Send + Sync>,
    ) -> Result<Value> {
        let _guard = self
            .0
            .restore
            .lock()
            .map_err(|_| Error::new("INTERNAL_ERROR", "Dataset restore lock failed"))?;
        let checked = self
            .0
            .local
            .import_iter(rows, &ordered_fields(reference)?)?;
        require(
            checked == *reference,
            "Transferred data checksum mismatch",
            "DATA_CONFLICT",
        )?;
        let saved = self
            .0
            .persist_cached_progress(&checked, progress.as_ref())?;
        require(
            saved == *reference,
            "Remote data metadata differs",
            "DATA_CONFLICT",
        )?;
        Ok(saved)
    }
}
#[derive(Default)]
struct Registry {
    states: Mutex<HashMap<String, Value>>,
    storage: Mutex<Option<Storage>>,
    writes: Mutex<HashMap<String, Weak<Mutex<()>>>>,
}
#[derive(Clone)]
struct Transfers {
    backend: Arc<dyn TransferBackend>,
    registry: Arc<Registry>,
    project: String,
}
impl Transfers {
    fn cloud(data: Arc<CloudData>) -> Result<Self> {
        static PROJECTS: OnceLock<Mutex<HashMap<String, Arc<Registry>>>> = OnceLock::new();
        let identity = format!(
            "{}\0{}\0{}",
            data.project,
            data.database.backend,
            data.local
                .path
                .as_ref()
                .map(|p| p.to_string_lossy())
                .unwrap_or_default()
        );
        let registry = PROJECTS
            .get_or_init(Mutex::default)
            .lock()
            .map_err(|_| Error::new("INTERNAL_ERROR", "Transfer registry unavailable"))?
            .entry(identity)
            .or_default()
            .clone();
        Ok(Self {
            project: data.project.clone(),
            backend: Arc::new(CloudBackend(data)),
            registry,
        })
    }
    fn storage(&self) -> Result<Storage> {
        let mut slot = self
            .registry
            .storage
            .lock()
            .map_err(|_| Error::new("INTERNAL_ERROR", "Transfer storage lock failed"))?;
        if slot.is_none() {
            let storage = self.backend.storage()?;
            storage.check_private()?;
            *slot = Some(storage);
        }
        Ok(slot.as_ref().unwrap().clone())
    }
    fn prefix(&self, upload: &str, bulk: bool) -> String {
        format!(
            "transfers/{}/{upload}/{}",
            self.project,
            if bulk { "bulk-v1/" } else { "" }
        )
    }
    fn cleanup(&self, upload: &str) -> Result<()> {
        check_identifier(upload, "Invalid upload ID")?;
        self.storage()?.delete_prefix(&self.prefix(upload, false))
    }
    fn saved(&self, reference: &Value) -> Result<Option<Value>> {
        let (version, _) = super::transfer::reference(reference)?;
        let saved = self.backend.metadata(version)?;
        if saved.is_null() {
            return Ok(None);
        }
        require(
            saved == *reference,
            "Remote data metadata differs",
            "DATA_CONFLICT",
        )?;
        Ok(Some(saved))
    }
    fn chunk(
        &self,
        upload: &str,
        reference: &Value,
        part: u64,
        rows: Option<&Value>,
        bulk: bool,
        payload: Option<&Value>,
    ) -> Result<Value> {
        let (_, count) = upload_reference(upload, reference, true)?;
        let size = if bulk { BULK_ROWS } else { TRANSFER_ROWS };
        require(
            part < count.div_ceil(size),
            "Invalid chunk number",
            "INVALID_ARGUMENT",
        )?;
        let expected = size.min(count - part * size);
        let (raw, compressed) = if bulk {
            require(
                rows.is_none_or(Value::is_null),
                "Bulk chunks do not accept rows",
                "INVALID_ARGUMENT",
            )?;
            let payload = payload.and_then(Value::as_str).ok_or_else(|| {
                Error::new("INVALID_ARGUMENT", "Bulk chunks require a Base64 payload")
            })?;
            let compressed = bulk_binary(payload)?;
            let raw = bulk_raw(&compressed)?;
            bulk_rows(&raw, expected)?;
            (raw, compressed)
        } else {
            require(
                payload.is_none_or(Value::is_null),
                "Compressed chunks require gzip-json-v1 encoding",
                "INVALID_ARGUMENT",
            )?;
            let rows = rows.ok_or_else(|| {
                Error::new("INVALID_ARGUMENT", "Transfer chunk rows are required")
            })?;
            require(
                rows.as_array().is_some_and(|rows| {
                    rows.len() as u64 == expected && rows.iter().all(Value::is_object)
                }),
                "Invalid chunk rows",
                "INVALID_ARGUMENT",
            )?;
            let raw = json_bytes(rows)?;
            require(
                raw.len() <= TRANSFER_DECODED,
                "Chunk exceeds 2 MiB",
                "INVALID_ARGUMENT",
            )?;
            let compressed = gzip(&raw)?;
            (raw, compressed)
        };
        if self.saved(reference)?.is_some() {
            return Ok(json!({"complete":true,"part":part}));
        }
        let storage = self.storage()?;
        let key = format!("{}{part}", self.prefix(upload, bulk));
        let lock = {
            let mut locks = self
                .registry
                .writes
                .lock()
                .map_err(|_| Error::new("INTERNAL_ERROR", "Transfer write lock failed"))?;
            if locks.len() > 4096 {
                locks.retain(|_, lock| lock.strong_count() > 0);
            }
            if let Some(lock) = locks.get(&key).and_then(Weak::upgrade) {
                lock
            } else {
                let lock = Arc::new(Mutex::new(()));
                locks.insert(key.clone(), Arc::downgrade(&lock));
                lock
            }
        };
        let _guard = lock
            .lock()
            .map_err(|_| Error::new("INTERNAL_ERROR", "Transfer write lock failed"))?;
        if let Some(previous) = storage.get_bounded(&key, BULK_COMPRESSED as u64)? {
            require(
                decompress(
                    &previous,
                    if bulk { BULK_DECODED } else { TRANSFER_DECODED },
                )? == raw,
                "Transfer chunk differs",
                "DATA_CONFLICT",
            )?;
        } else {
            storage.put(&key, &compressed, "application/gzip")?;
        }
        Ok(json!({"complete":false,"part":part}))
    }
    fn progress(&self, upload: &str, phase: &str, completed: u64, total: u64) {
        if let Ok(mut states) = self.registry.states.lock() {
            if let Some(state) = states
                .get_mut(upload)
                .filter(|state| state["state"] == "running")
            {
                state["phase"] = json!(phase);
                state["completed"] = json!(completed);
                state["total"] = json!(total);
            }
        }
    }
    fn finish(&self, upload: &str, reference: &Value, bulk: bool) -> Result<Value> {
        let (_, count) = upload_reference(upload, reference, true)?;
        if let Some(saved) = self.saved(reference)? {
            self.cleanup(upload)?;
            return Ok(json!({"state":"complete","ref":saved}));
        }
        let size = if bulk { BULK_ROWS } else { TRANSFER_ROWS };
        let total = count.div_ceil(size);
        {
            let mut states = self
                .registry
                .states
                .lock()
                .map_err(|_| Error::new("INTERNAL_ERROR", "Transfer state lock failed"))?;
            if let Some(state) = states
                .get(upload)
                .filter(|state| state["state"] == "running")
            {
                require(
                    state["ref"] == *reference && state["bulk"] == bulk,
                    "Upload already in use",
                    "DATA_CONFLICT",
                )?;
                return Ok(json!({"state":"running"}));
            }
            states.insert(upload.into(), json!({"state":"running","ref":reference,"phase":"reading","completed":0,"total":total,"bulk":bulk}));
        }
        let manager = self.clone();
        let upload = upload.to_string();
        let state_id = upload.clone();
        let reference = reference.clone();
        let spawn = std::thread::Builder::new()
            .name("dataset-transfer".into())
            .spawn(move || {
                let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    manager.finalize(&upload, &reference, bulk)
                }));
                let result = match outcome {
                    Ok(Ok(value)) => value,
                    Ok(Err(error)) => json!({"state":"failed","code":error.code}),
                    Err(_) => json!({"state":"failed","code":"TRANSFER_FAILED"}),
                };
                if let Ok(mut states) = manager.registry.states.lock() {
                    states.insert(upload, result);
                }
            });
        if spawn.is_err() {
            self.registry
                .states
                .lock()
                .map_err(|_| Error::new("INTERNAL_ERROR", "Transfer state lock failed"))?
                .insert(state_id, json!({"state":"failed","code":"TRANSFER_FAILED"}));
            return Err(Error::new(
                "TRANSFER_FAILED",
                "Could not start dataset transfer",
            ));
        }
        Ok(json!({"state":"running"}))
    }
    fn finalize(&self, upload: &str, reference: &Value, bulk: bool) -> Result<Value> {
        let (_, count) = super::transfer::reference(reference)?;
        let size = if bulk { BULK_ROWS } else { TRANSFER_ROWS };
        let total = count.div_ceil(size);
        let storage = self.storage()?;
        let prefix = self.prefix(upload, bulk);
        let reading = self.clone();
        let reading_id = upload.to_string();
        let rows = ChunkRows::new(count, size, move |part| {
            let compressed = storage
                .get_bounded(&format!("{prefix}{part}"), BULK_COMPRESSED as u64)?
                .ok_or_else(|| Error::new("DATA_INCOMPLETE", "A transfer chunk is missing"))?;
            let raw = decompress(
                &compressed,
                if bulk { BULK_DECODED } else { TRANSFER_DECODED },
            )?;
            let expected = size.min(count - part * size);
            bulk_rows(&raw, expected)
        })
        .with_progress(move |completed| reading.progress(&reading_id, "reading", completed, total));
        let saving = self.clone();
        let saving_id = upload.to_string();
        let progress = Arc::new(move |completed| {
            saving.progress(&saving_id, "saving", completed, count.div_ceil(500))
        });
        let saved = self.backend.save(rows, reference, progress)?;
        self.progress(upload, "cleanup", 0, 1);
        self.cleanup(upload)?;
        Ok(json!({"state":"complete","ref":saved}))
    }
    fn status(
        &self,
        upload: &str,
        reference: &Value,
        parts: Option<&Value>,
        bulk: bool,
    ) -> Result<Value> {
        let (_, count) = upload_reference(upload, reference, false)?;
        let saved = self.saved(reference)?;
        let state = self
            .registry
            .states
            .lock()
            .map_err(|_| Error::new("INTERNAL_ERROR", "Transfer state lock failed"))?
            .get(upload)
            .cloned()
            .unwrap_or_else(|| json!({"state":"unknown"}));
        if state["state"] == "running" {
            require(
                state["bulk"] == bulk && state["ref"] == *reference,
                "Upload already in use",
                "DATA_CONFLICT",
            )?;
        }
        let mut result = if let Some(saved) = saved {
            if state["state"] == "running" {
                state
            } else {
                json!({"state":if state["state"]=="complete" {"complete"}else{"cleanup_required"},"ref":saved})
            }
        } else {
            state
        };
        // Internal reference and encoding are not exposed during a running job.
        if result["state"] == "running" {
            let object = result.as_object_mut().unwrap();
            object.remove("ref");
            object.remove("bulk");
        }
        if let Some(parts) = parts.filter(|value| !value.is_null()) {
            let size = if bulk { BULK_ROWS } else { TRANSFER_ROWS };
            let total = count.div_ceil(size);
            let parts = parts
                .as_array()
                .filter(|parts| parts.len() <= if bulk { 4 } else { 128 })
                .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid transfer receipt parts"))?;
            let mut seen = HashSet::new();
            let parts = parts
                .iter()
                .map(|part| {
                    part.as_u64()
                        .filter(|part| *part < total && seen.insert(*part))
                        .ok_or_else(|| {
                            Error::new("INVALID_ARGUMENT", "Invalid transfer receipt parts")
                        })
                })
                .collect::<Result<Vec<_>>>()?;
            let mut received = Map::new();
            if result["state"] != "complete" && result["state"] != "cleanup_required" {
                let storage = self.storage()?;
                let prefix = self.prefix(upload, bulk);
                for window in parts.chunks(4) {
                    let fetched = std::thread::scope(|scope| {
                        let workers = window
                            .iter()
                            .map(|part| {
                                let storage = &storage;
                                let prefix = &prefix;
                                scope.spawn(move || {
                                    storage.get_bounded(
                                        &format!("{prefix}{part}"),
                                        BULK_COMPRESSED as u64,
                                    )
                                })
                            })
                            .collect::<Vec<_>>();
                        workers
                            .into_iter()
                            .map(|worker| {
                                worker
                                    .join()
                                    .map_err(|_| {
                                        Error::new(
                                            "TRANSFER_FAILED",
                                            "Transfer receipt worker stopped",
                                        )
                                    })
                                    .and_then(|result| result)
                            })
                            .collect::<Vec<_>>()
                    });
                    for (part, raw) in window.iter().zip(fetched) {
                        if let Some(compressed) = raw? {
                            let raw = decompress(
                                &compressed,
                                if bulk { BULK_DECODED } else { TRANSFER_DECODED },
                            )?;
                            received
                                .insert(part.to_string(), json!(hex::encode(Sha256::digest(&raw))));
                        }
                    }
                }
            }
            result["receivedParts"] = Value::Object(received);
        }
        Ok(result)
    }
}

pub fn call(service: &Service, tool: &str, args: &Value) -> Result<Value> {
    let data = service
        .store
        .data
        .cloud
        .as_ref()
        .ok_or_else(|| {
            Error::new(
                "UNSUPPORTED_OPERATION",
                "Dataset cloud operations require cloud project storage",
            )
        })?
        .clone();
    if tool == "dataset_storage_inventory" {
        let database = service
            .store
            .database
            .as_ref()
            .ok_or_else(|| Error::new("PROJECT_REQUIRED", "Cloud project required"))?
            .with_function("charts_data_inventory")?;
        let mut result = database.call("inventory", &service.store.project, &json!({}))?;
        let mut cos = data.assets.call("inventory", &json!({}))?;
        if let Some(object) = cos.as_object_mut() {
            object.remove("documents");
        }
        result["cos"] = cos;
        return Ok(result);
    }
    if tool == "dataset_repartition" {
        require(
            data.cos_enabled,
            "Repartitioning requires COS project storage",
            "UNSUPPORTED_OPERATION",
        )?;
        let board = string(args, "dashboardId")?;
        let dataset = string(args, "datasetId")?;
        let doc = service.store.get(board, false)?;
        let reference = doc["snapshot"]["datasetRefs"]
            .get(dataset)
            .ok_or_else(|| Error::new("NOT_FOUND", "Dataset has no immutable version"))?;
        require(
            reference["version"] == args["expectedVersion"],
            "Dataset version changed",
            "DATA_CONFLICT",
        )?;
        let field = string(args, "field")?;
        let replacement = data.repartition(reference, field)?;
        return Ok(
            json!({"dashboardId":board,"datasetId":dataset,"previousVersion":reference["version"],"ref":replacement,"partitionField":field}),
        );
    }
    let bulk = match args.get("encoding") {
        None | Some(Value::Null) => false,
        Some(value) if value == BULK_ENCODING => true,
        _ => {
            return Err(Error::new(
                "INVALID_ARGUMENT",
                "Unsupported transfer encoding",
            ))
        }
    };
    let manager = Transfers::cloud(data)?;
    let upload = string(args, "uploadId")?;
    match tool {
        "dataset_transfer_chunk" => manager.chunk(
            upload,
            &args["ref"],
            args["part"]
                .as_u64()
                .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid chunk number"))?,
            args.get("rows"),
            bulk,
            args.get("payload"),
        ),
        "dataset_transfer_finish" => manager.finish(upload, &args["ref"], bulk),
        "dataset_transfer_status" => manager.status(upload, &args["ref"], args.get("parts"), bulk),
        "dataset_transfer_cleanup" => {
            manager.cleanup(upload)?;
            Ok(json!({"ok":true}))
        }
        _ => Err(Error::new(
            "UNKNOWN_TOOL",
            "Unsupported dataset transfer operation",
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::runtime::data::LocalData;
    use std::time::{Duration, Instant};

    struct Backend {
        local: LocalData,
        storage: Storage,
        references: Mutex<HashMap<String, Value>>,
    }
    impl TransferBackend for Backend {
        fn metadata(&self, version: &str) -> Result<Value> {
            Ok(self
                .references
                .lock()
                .unwrap()
                .get(version)
                .cloned()
                .unwrap_or(Value::Null))
        }
        fn storage(&self) -> Result<Storage> {
            Ok(self.storage.clone())
        }
        fn save(
            &self,
            rows: ChunkRows,
            reference: &Value,
            progress: Arc<dyn Fn(u64) + Send + Sync>,
        ) -> Result<Value> {
            let imported = self.local.import_iter(rows, &ordered_fields(reference)?)?;
            require(
                imported == *reference,
                "Transfer checksum mismatch",
                "DATA_CONFLICT",
            )?;
            self.references.lock().unwrap().insert(
                reference["version"].as_str().unwrap().into(),
                imported.clone(),
            );
            progress(reference["rowCount"].as_u64().unwrap().div_ceil(500));
            Ok(imported)
        }
    }
    fn setup(path: &std::path::Path) -> (Transfers, Arc<Backend>, Value, Vec<Value>) {
        let rows = (0..501)
            .map(|index| {
                if index % 5 == 0 {
                    json!({"label":"华东","value":index})
                } else {
                    json!({"label":null,"value":index,"enabled":index%2==0})
                }
            })
            .collect::<Vec<_>>();
        let source = LocalData::new(None).unwrap();
        let reference = source.import_rows(&rows, &json!({"label":{"type":"string"},"value":{"type":"number"},"enabled":{"type":"boolean"}})).unwrap();
        let backend = Arc::new(Backend {
            local: LocalData::new(Some(&path.join("data"))).unwrap(),
            storage: Storage::private(path.join("objects"), "test").unwrap(),
            references: Mutex::new(HashMap::new()),
        });
        let manager = Transfers {
            backend: backend.clone(),
            registry: Arc::new(Registry::default()),
            project: "test".into(),
        };
        (manager, backend, reference, rows)
    }
    fn completed(manager: &Transfers, upload: &str, reference: &Value, bulk: bool) -> Value {
        let start = Instant::now();
        loop {
            let result = manager.status(upload, reference, None, bulk).unwrap();
            if result["state"] != "running" {
                return result;
            }
            assert!(
                start.elapsed() < Duration::from_secs(5),
                "transfer did not finish"
            );
            std::thread::sleep(Duration::from_millis(5));
        }
    }

    // @wu-test type=boundary | scope=compressed transfer payload | protects=oversized decompression, appended gzip members and noncanonical JSON cannot enter a dataset
    #[test]
    fn bulk_payload_is_bounded_and_exact() {
        let rows = json!([{"value":1.0,"label":"华东"},{"value":null}]);
        let raw = json_bytes(&rows).unwrap();
        let encoded = encode_bulk(&raw).unwrap();
        let compressed = bulk_binary(&encoded).unwrap();
        assert_eq!(bulk_rows(&bulk_raw(&compressed).unwrap(), 2).unwrap(), rows);
        let mut trailing = compressed.clone();
        trailing.extend_from_slice(&compressed);
        assert!(bulk_raw(&trailing).is_err());
        assert!(bulk_binary("not base64!").is_err());
        assert!(bulk_rows(b"[ {\"value\":1} ]", 1).is_err());
        assert!(bulk_rows(b"[1]", 1).is_err());
        let bomb = gzip(&vec![b' '; BULK_DECODED + 1]).unwrap();
        assert!(bulk_raw(&bomb).is_err());
        assert!(reference(&json!({"version":"a".repeat(64),"rowCount":1,"fields":{"v":{"type":"number"}},"fieldOrder":["v","v"]})).is_err());
    }

    // @wu-test type=integration | scope=resumable native transfer | protects=duplicate chunks stay idempotent, receipts match canonical hashes and completed references retain source data
    #[test]
    fn native_transfer_validates_receipts_and_commits_once() {
        let directory = tempfile::tempdir().unwrap();
        let (manager, backend, reference, rows) = setup(directory.path());
        let upload = "a".repeat(64);
        let first = json!(&rows[..250]);
        assert_eq!(
            manager
                .chunk(&upload, &reference, 0, Some(&first), false, None)
                .unwrap(),
            json!({"complete":false,"part":0})
        );
        manager
            .chunk(&upload, &reference, 0, Some(&first), false, None)
            .unwrap();
        let mut changed = first.clone();
        changed[0]["value"] = json!(9999);
        assert_eq!(
            manager
                .chunk(&upload, &reference, 0, Some(&changed), false, None)
                .unwrap_err()
                .code,
            "DATA_CONFLICT"
        );
        let status = manager
            .status(&upload, &reference, Some(&json!([0, 1, 2])), false)
            .unwrap();
        assert_eq!(
            status["receivedParts"]["0"],
            hex::encode(Sha256::digest(json_bytes(&first).unwrap()))
        );
        assert!(status["receivedParts"].get("1").is_none());
        manager
            .chunk(
                &upload,
                &reference,
                1,
                Some(&json!(&rows[250..500])),
                false,
                None,
            )
            .unwrap();
        manager
            .chunk(
                &upload,
                &reference,
                2,
                Some(&json!(&rows[500..])),
                false,
                None,
            )
            .unwrap();
        assert_eq!(
            manager.finish(&upload, &reference, false).unwrap()["state"],
            "running"
        );
        let result = completed(&manager, &upload, &reference, false);
        assert_eq!(result, json!({"state":"complete","ref":reference}));
        assert_eq!(backend.local.all_rows(&reference).unwrap(), rows);
        assert!(backend
            .storage
            .list(&manager.prefix(&upload, false))
            .unwrap()
            .is_empty());
        assert_eq!(manager.finish(&upload, &reference, false).unwrap(), result);
        assert_eq!(
            manager
                .chunk(&upload, &reference, 0, Some(&first), false, None)
                .unwrap()["complete"],
            true
        );
    }

    // @wu-test type=integration | scope=transfer integrity failures | protects=missing chunks and mismatched content hashes never publish remote metadata
    #[test]
    fn incomplete_and_conflicting_transfers_never_publish() {
        let directory = tempfile::tempdir().unwrap();
        let (manager, backend, reference, rows) = setup(directory.path());
        let upload = "b".repeat(64);
        manager.finish(&upload, &reference, false).unwrap();
        assert_eq!(
            completed(&manager, &upload, &reference, false)["code"],
            "DATA_INCOMPLETE"
        );
        let mut wrong = reference.clone();
        wrong["version"] = json!("f".repeat(64));
        let payload = json!(encode_bulk(&json_bytes(&json!(rows)).unwrap()).unwrap());
        manager
            .chunk(&upload, &wrong, 0, None, true, Some(&payload))
            .unwrap();
        manager.finish(&upload, &wrong, true).unwrap();
        assert_eq!(
            completed(&manager, &upload, &wrong, true)["code"],
            "DATA_CONFLICT"
        );
        assert!(backend.references.lock().unwrap().is_empty());
        assert!(manager
            .status(&upload, &wrong, Some(&json!([0, 0])), true)
            .is_err());
    }
}
