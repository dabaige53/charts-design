//! Transactional project lifecycle, immutable checkpoints and durable cloud state.
use super::{
    cloud::{self, CloudDatabase},
    data::LocalData,
    error::{require, Error, Result},
    model,
    serialization::{equivalent_json, json_bytes, utcnow},
    structure,
};
use fs2::FileExt;
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::{json, Value};
use std::{
    collections::HashSet,
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    sync::OnceLock,
    time::Duration,
};
pub fn defaults() -> Value {
    json!({"history":{"keepCheckpoints":100},"loading":{"debounceMs":150,"maxConcurrent":4,"pageSize":50}})
}
pub fn write_json(path: &Path, value: &Value) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| Error::new("INVALID_PATH", "File needs a parent directory"))?;
    fs::create_dir_all(parent)?;
    let name = path.file_name().and_then(|s| s.to_str()).unwrap_or("asset");
    let temp = parent.join(format!(".{name}.{}.tmp", uuid::Uuid::new_v4().simple()));
    let result = (|| -> Result<()> {
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = options.open(&temp)?;
        file.write_all(&serde_json::to_vec_pretty(value)?)?;
        file.flush()?;
        fs::rename(&temp, path)?;
        Ok(())
    })();
    let _ = fs::remove_file(&temp);
    result
}
fn raw(v: &Value) -> Result<String> {
    String::from_utf8(json_bytes(v)?).map_err(|_| Error::new("INVALID_JSON", "Expected UTF-8 JSON"))
}
fn parse(s: String) -> Result<Value> {
    Ok(serde_json::from_str(&s)?)
}
fn revision_from(doc: &Value) -> Result<i64> {
    doc["revision"]
        .as_i64()
        .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Invalid revision"))
}
fn arr(v: &Value) -> Vec<Value> {
    v.as_array().cloned().unwrap_or_default()
}
fn notes(doc: &Value) -> Value {
    doc["manifest"]
        .get("annotations")
        .cloned()
        .unwrap_or_else(|| json!([]))
}
fn ensure_dir(path: &Path) -> Result<PathBuf> {
    fs::create_dir_all(path)?;
    Ok(path.canonicalize()?)
}

pub struct Store {
    pub root: PathBuf,
    pub path: PathBuf,
    pub project_root: Option<PathBuf>,
    pub runtime_root: PathBuf,
    pub config: Value,
    pub data: LocalData,
    pub database: Option<CloudDatabase>,
    pub project: String,
    pub cos_enabled: bool,
    pub(crate) versions_initialized: OnceLock<()>,
}
impl Store {
    pub fn new(root: &Path, project: Option<&Path>) -> Result<Self> {
        let runtime_root = ensure_dir(root)?;
        let project_root = project.map(ensure_dir).transpose()?;
        if cloud::cloud_enabled()? {
            let project_root = project_root.ok_or_else(|| {
                Error::new("PROJECT_REQUIRED", "Cloud storage requires a named project")
            })?;
            let project = project_root
                .file_name()
                .and_then(|s| s.to_str())
                .ok_or_else(|| {
                    Error::new("INVALID_PROJECT", "Cloud storage requires a named project")
                })?
                .to_owned();
            let database = CloudDatabase::new()?;
            let config = database.call("ensure", &project, &json!({"config":defaults()}))?;
            let cos_enabled = config["storageFormat"] == "cos-v1";
            let root = ensure_dir(&project_root.join("dashboards"))?;
            let data =
                LocalData::with_cloud(&runtime_root.join("data-cache"), &project, cos_enabled)?;
            let partition_fields = config["storage"]["partitionFields"]
                .as_array()
                .into_iter()
                .flatten()
                .map(|v| {
                    v.as_str().map(str::to_owned).ok_or_else(|| {
                        Error::new("INVALID_CONFIG", "Partition fields must be strings")
                    })
                })
                .collect::<Result<Vec<_>>>()?;
            data.set_partition_fields(&partition_fields)?;
            return Ok(Self {
                path: root.join("dashboards.sqlite3"),
                root,
                project_root: Some(project_root),
                runtime_root,
                config,
                data,
                database: Some(database),
                project,
                cos_enabled,
                versions_initialized: OnceLock::new(),
            });
        }
        let config = if let Some(project) = &project_root {
            let path = project.join("charts-project.json");
            if !path.exists() {
                write_json(&path, &defaults())?;
            }
            let mut config = defaults();
            let saved: Value = serde_json::from_slice(&fs::read(path)?)?;
            for key in ["history", "loading"] {
                if let Some(extra) = saved.get(key) {
                    let extra = extra.as_object().ok_or_else(|| {
                        Error::new("INVALID_CONFIG", "Project settings must be objects")
                    })?;
                    config[key].as_object_mut().unwrap().extend(extra.clone());
                }
            }
            require(
                config["history"]["keepCheckpoints"]
                    .as_i64()
                    .is_some_and(|n| (1..=10000).contains(&n)),
                "Invalid checkpoint retention",
                "INVALID_DOCUMENT",
            )?;
            config
        } else {
            defaults()
        };
        let root = if let Some(project) = &project_root {
            ensure_dir(&project.join("dashboards"))?
        } else {
            runtime_root.clone()
        };
        let data_root = project_root
            .as_ref()
            .map(|p| p.join("data"))
            .unwrap_or_else(|| root.clone());
        let data = LocalData::new(Some(&data_root))?;
        let store = Self {
            path: root.join("dashboards.sqlite3"),
            root,
            project: project_root
                .as_ref()
                .and_then(|p| p.file_name())
                .map(|s| s.to_string_lossy().into_owned())
                .unwrap_or_default(),
            project_root,
            runtime_root,
            config,
            data,
            database: None,
            cos_enabled: false,
            versions_initialized: OnceLock::new(),
        };
        let db = store.connect()?;
        db.execute_batch("PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS boards(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,document TEXT NOT NULL);CREATE TABLE IF NOT EXISTS revisions(board_id TEXT NOT NULL,revision INTEGER NOT NULL,created_at TEXT NOT NULL,action TEXT NOT NULL,document TEXT NOT NULL,PRIMARY KEY(board_id,revision));")?;
        if store.is_project() {
            db.execute_batch("CREATE TABLE IF NOT EXISTS checkpoint_meta(board_id TEXT,revision INTEGER,name TEXT,published INTEGER DEFAULT 0,PRIMARY KEY(board_id,revision));CREATE TABLE IF NOT EXISTS batches(board_id TEXT PRIMARY KEY,batch_id TEXT,base_revision INTEGER);CREATE TABLE IF NOT EXISTS annotations(board_id TEXT PRIMARY KEY,payload TEXT);CREATE TABLE IF NOT EXISTS annotation_events(board_id TEXT,at TEXT,revision INTEGER,payload TEXT);CREATE INDEX IF NOT EXISTS annotation_events_board ON annotation_events(board_id);")?;
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = fs::set_permissions(&store.path, fs::Permissions::from_mode(0o600));
        }
        Ok(store)
    }
    pub fn is_project(&self) -> bool {
        self.project_root.is_some()
    }
    pub fn connect(&self) -> Result<Connection> {
        require(
            self.database.is_none(),
            "Cloud projects use PostgreSQL transactions",
            "UNSUPPORTED_OPERATION",
        )?;
        let db = Connection::open(&self.path)?;
        db.busy_timeout(Duration::from_secs(10))?;
        Ok(db)
    }
    /// Reuse the data adapter's private storage client and checked ACL.
    pub fn cloud_assets(&self) -> Result<&cloud::CloudAssets> {
        self.data
            .cloud
            .as_ref()
            .map(|data| &data.assets)
            .ok_or_else(|| {
                Error::new(
                    "UNSUPPORTED_OPERATION",
                    "Cloud assets require a cloud project",
                )
            })
    }
    pub fn decode(&self, doc: &Value) -> Result<Value> {
        if self.database.is_some() {
            self.cloud_assets()?.hydrate_document(doc)
        } else {
            Ok(doc.clone())
        }
    }
    pub fn encode(&self, doc: &Value, previous: Option<&Value>) -> Result<Value> {
        if !self.cos_enabled {
            return Ok(doc.clone());
        }
        if model::live_datasets(doc)
            .as_object()
            .is_some_and(|o| !o.is_empty())
        {
            return self.cloud_assets()?.save_document(doc);
        }
        let changed = previous
            .filter(|p| {
                p.get("computed").is_some()
                    && model::live_datasets(p)
                        .as_object()
                        .is_none_or(|m| m.is_empty())
            })
            .and_then(|p| {
                let same = ["metrics", "datasets", "filters"]
                    .iter()
                    .all(|k| p["manifest"][*k] == doc["manifest"][*k])
                    && ["datasetRefs", "componentDataRefs"]
                        .iter()
                        .all(|k| p["snapshot"].get(*k) == doc["snapshot"].get(*k));
                if same {
                    Some(
                        doc["manifest"]["components"]
                            .as_object()
                            .into_iter()
                            .flatten()
                            .filter(|(k, c)| p["manifest"]["components"].get(*k) != Some(*c))
                            .map(|(k, _)| k.clone())
                            .collect::<Vec<_>>(),
                    )
                } else {
                    None
                }
            });
        let view = super::view::LocalView::new(self.data.clone(), None);
        let prepared = view.prepare_select(doc, None, None, None, changed.as_deref(), false)?;
        let mut computed = prepared["computed"].clone();
        if let Some(filters) = doc["manifest"]["filters"].as_array() {
            for selection in filters {
                if selection["op"] != "in"
                    || selection["required"] != true
                    || selection["selectionMode"] != "single"
                {
                    continue;
                }
                let id = selection["id"].as_str().unwrap_or("");
                let unchanged = selection["componentIds"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .all(|v| {
                        !changed.as_ref().is_some_and(|changed| {
                            v.as_str().is_some_and(|v| changed.iter().any(|c| c == v))
                        })
                    });
                let previous_page = if changed.is_some() && unchanged {
                    previous.and_then(|p| p["computed"]["filterPages"].get(id))
                } else {
                    None
                };
                let page = if let Some(page) = previous_page {
                    page.clone()
                } else {
                    view.filter_options(doc, id, "", 0, 100)?
                };
                if page["hasMore"] == false && json_bytes(&page["values"])?.len() <= 4096 {
                    if !computed["filterPages"].is_object() {
                        computed["filterPages"] = json!({});
                    }
                    computed["filterPages"][id] = page;
                }
            }
        }
        if let (Some(previous), Some(changed)) = (previous, changed) {
            for group in ["components", "tables", "grouped"] {
                let mut values = serde_json::Map::new();
                if let Some(old) = previous["computed"][group].as_object() {
                    for (key, value) in old {
                        if doc["manifest"]["components"].get(key).is_some()
                            && !changed.contains(key)
                        {
                            values.insert(key.clone(), value.clone());
                        }
                    }
                }
                if let Some(new) = computed[group].as_object() {
                    values.extend(new.clone());
                }
                computed[group] = Value::Object(values);
            }
        }
        let mut saved = doc.clone();
        saved["computed"] = computed;
        saved["statisticalArtifacts"] =
            super::statistics::statistical_artifacts(&self.statistical_document(doc)?);
        self.cloud_assets()?.save_document(&saved)
    }
    pub fn compact(&self, document: &Value) -> Result<Value> {
        let mut doc = document.clone();
        doc.as_object_mut()
            .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Document must be an object"))?
            .remove("computed");
        let embedded = doc["snapshot"]["datasets"]
            .as_object()
            .ok_or_else(|| Error::new("INVALID_DOCUMENT", "snapshot.datasets must be an object"))?
            .clone();
        if doc["snapshot"].get("datasetRefs").is_none() {
            doc["snapshot"]["datasetRefs"] = json!({});
        }
        for (key, rows) in embedded {
            let fields = &doc["manifest"]["datasets"][&key]["fields"];
            let rows = rows
                .as_array()
                .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Rows must be an array"))?;
            let reference = self.data.import_rows(rows, fields)?;
            doc["snapshot"]["datasetRefs"][&key] = reference;
        }
        doc["snapshot"]["datasets"] = json!({});
        if doc["snapshot"].get("componentDataRefs").is_none() {
            doc["snapshot"]["componentDataRefs"] = json!({});
        }
        let components = doc["manifest"]["components"]
            .as_object()
            .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Components must be an object"))?
            .clone();
        for (key, component) in components {
            let mut c = component.clone();
            structure::normalize_component(&mut c)?;
            if c["kind"] == "legacy" && c["family"] == "table" {
                if !c["binding"].is_object() || c["binding"] == json!({}) {
                    let rows = arr(&c["config"]["rows"]);
                    if !rows.is_empty() {
                        let fields = model::inferred_fields(&rows)?;
                        let reference = self.data.import_rows(&rows, &fields)?;
                        c["config"]["rows"] = json!([]);
                        c["config"]["rowsRef"] = reference["version"].clone();
                        doc["snapshot"]["componentDataRefs"][&key] = reference;
                    } else if c["config"]["rowsRef"]
                        != doc["snapshot"]["componentDataRefs"][&key]["version"]
                    {
                        doc["snapshot"]["componentDataRefs"]
                            .as_object_mut()
                            .unwrap()
                            .remove(&key);
                    }
                } else {
                    c["config"]["rows"] = json!([]);
                }
            }
            doc["manifest"]["components"][&key] = c;
        }
        let names: HashSet<String> = doc["manifest"]["components"]
            .as_object()
            .unwrap()
            .keys()
            .cloned()
            .collect();
        doc["snapshot"]["componentDataRefs"]
            .as_object_mut()
            .unwrap()
            .retain(|k, _| names.contains(k));
        for reference in doc["snapshot"]["datasetRefs"]
            .as_object()
            .into_iter()
            .flatten()
            .map(|(_, v)| v)
            .chain(
                doc["snapshot"]["componentDataRefs"]
                    .as_object()
                    .into_iter()
                    .flatten()
                    .map(|(_, v)| v),
            )
        {
            let version = reference["version"].as_str().ok_or_else(|| {
                Error::new(
                    "INVALID_DOCUMENT",
                    "Local data version must be a content hash",
                )
            })?;
            require(
                self.data.describe(version)? == *reference,
                "Local data reference does not match its immutable version",
                "INVALID_DOCUMENT",
            )?;
        }
        self.statistical_document(&doc)?;
        model::validate(&doc)?;
        Ok(doc)
    }
    pub fn statistical_document(&self, document: &Value) -> Result<Value> {
        let mut doc = document.clone();
        let components = doc["manifest"]["components"]
            .as_object()
            .into_iter()
            .flatten()
            .filter(|(_, v)| v["kind"] == "statistical")
            .map(|(_, v)| v.clone())
            .collect::<Vec<_>>();
        for c in components {
            let key = c["datasetId"].as_str().unwrap_or("");
            if let Some(reference) = doc["snapshot"]["datasetRefs"].get(key).cloned() {
                require(
                    reference["rowCount"].as_u64().is_some_and(|n| n <= 5000),
                    "Statistical plots accept at most 5000 raw rows",
                    "INVALID_DOCUMENT",
                )?;
                doc["snapshot"]["datasets"][key] = json!(self.data.all_rows(&reference)?);
            }
            super::statistics::validate_statistical(&doc, &c)?;
        }
        Ok(doc)
    }
    pub fn hydrate(&self, document: &Value) -> Result<Value> {
        let mut doc = document.clone();
        let refs = doc["snapshot"]["datasetRefs"]
            .as_object()
            .cloned()
            .unwrap_or_default();
        let tables = doc["snapshot"]["componentDataRefs"]
            .as_object()
            .cloned()
            .unwrap_or_default();
        let count: u64 = refs
            .values()
            .chain(tables.values())
            .map(|r| r["rowCount"].as_u64().unwrap_or(u64::MAX))
            .fold(0, u64::saturating_add);
        require(
            count <= model::MAX_ROWS as u64,
            "Large local data cannot be embedded in a snapshot; use dataset_export for full CSV",
            "LOCAL_DATA_REQUIRED",
        )?;
        for (key, r) in refs {
            doc["snapshot"]["datasets"][key] = json!(self.data.all_rows(&r)?);
        }
        for (key, r) in tables {
            if doc["manifest"]["components"].get(&key).is_some() {
                doc["manifest"]["components"][&key]["config"]["rows"] =
                    json!(self.data.all_rows(&r)?);
                doc["manifest"]["components"][&key]["config"]
                    .as_object_mut()
                    .unwrap()
                    .remove("rowsRef");
            }
        }
        doc["snapshot"]
            .as_object_mut()
            .unwrap()
            .remove("datasetRefs");
        doc["snapshot"]
            .as_object_mut()
            .unwrap()
            .remove("componentDataRefs");
        model::validate(&doc)?;
        Ok(doc)
    }
    pub fn compatible(&self, doc: &Value) -> Result<Value> {
        if self.is_project() || doc["snapshot"]["localMode"] == true {
            return Ok(doc.clone());
        }
        let count = doc["snapshot"]["datasetRefs"]
            .as_object()
            .into_iter()
            .flatten()
            .chain(
                doc["snapshot"]["componentDataRefs"]
                    .as_object()
                    .into_iter()
                    .flatten(),
            )
            .map(|(_, r)| r["rowCount"].as_u64().unwrap_or(u64::MAX))
            .fold(0, u64::saturating_add);
        if count <= model::MAX_ROWS as u64 {
            self.hydrate(doc)
        } else {
            Ok(doc.clone())
        }
    }
    pub fn create(&self, board: &str, title: &str, document: Option<&Value>) -> Result<Value> {
        model::check_identifier(board)?;
        let mut doc = if let Some(doc) = document {
            doc.clone()
        } else {
            model::new_document(board, title)?
        };
        doc["id"] = json!(board);
        doc["revision"] = json!(1);
        model::validate(&doc)?;
        for (key, c) in doc["manifest"]["components"].as_object().unwrap() {
            model::validate_component_content(c, key)?;
        }
        doc = self.compact(&doc)?;
        if let Some(db) = &self.database {
            let mut n = notes(&doc);
            Self::note_context(&doc, &mut n, &json!([]), document.is_some());
            doc["manifest"]["annotations"] = n;
            return self.decode(&db.call(
                "create",
                &self.project,
                &json!({"board":board,"document":self.encode(&doc,None)?,"at":utcnow()}),
            )?);
        }
        let mut db = self.connect()?;
        let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        let raw = raw(&doc)?;
        match tx.execute("INSERT INTO boards VALUES(?,?,?)", params![board, 1, raw]) {
            Ok(_) => {}
            Err(rusqlite::Error::SqliteFailure(e, _))
                if e.code == rusqlite::ErrorCode::ConstraintViolation =>
            {
                return Err(
                    Error::new("ALREADY_EXISTS", "Dashboard already exists").with_status(409)
                )
            }
            Err(e) => return Err(e.into()),
        };
        tx.execute(
            "INSERT INTO revisions VALUES(?,?,?,?,?)",
            params![board, 1, utcnow(), "create", raw],
        )?;
        if self.is_project() {
            let mut n = notes(&doc);
            self.save_notes(&tx, &doc, &mut n, None)?;
        }
        tx.commit()?;
        if self.is_project() {
            self.sync_mirrors(board, true, true, true, None, false)?;
            self.get(board, true)
        } else {
            self.compatible(&doc)
        }
    }
    pub fn get(&self, board: &str, hydrate: bool) -> Result<Value> {
        model::check_identifier(board)?;
        if let Some(db) = &self.database {
            return self.decode(&db.call("get", &self.project, &json!({"board":board}))?);
        }
        let db = self.connect()?;
        let stored: Option<String> = db
            .query_row("SELECT document FROM boards WHERE id=?", [board], |r| {
                r.get(0)
            })
            .optional()?;
        let mut doc = parse(
            stored
                .ok_or_else(|| Error::new("NOT_FOUND", "Dashboard not found").with_status(404))?,
        )?;
        if self.is_project() {
            doc["manifest"]["annotations"] = Self::read_notes(&db, board)?;
        }
        if hydrate {
            self.compatible(&doc)
        } else {
            Ok(doc)
        }
    }
    pub fn list(&self) -> Result<Value> {
        if let Some(db) = &self.database {
            return db.call("list", &self.project, &json!({}));
        }
        let db = self.connect()?;
        let mut statement=db.prepare("SELECT id,revision,json_extract(document,'$.manifest.title') AS title FROM boards ORDER BY id")?;
        let result=statement.query_map([],|r|Ok(json!({"id":r.get::<_,String>(0)?,"revision":r.get::<_,i64>(1)?,"title":r.get::<_,Option<String>>(2)?})))?.collect::<std::result::Result<Vec<_>,_>>()?;
        Ok(json!(result))
    }
    pub fn revision(&self, board: &str) -> Result<i64> {
        model::check_identifier(board)?;
        if self.database.is_some() {
            return revision_from(&self.get(board, false)?);
        }
        let db = self.connect()?;
        db.query_row("SELECT revision FROM boards WHERE id=?", [board], |r| {
            r.get(0)
        })
        .optional()?
        .ok_or_else(|| Error::new("NOT_FOUND", "Dashboard not found").with_status(404))
    }
    pub fn display_revision(&self, board: &str) -> Result<Option<i64>> {
        model::check_identifier(board)?;
        if let Some(db) = &self.database {
            let r = if db.backend == "neon" {
                db.call("display_revision", &self.project, &json!({"board":board}))?
            } else {
                db.call("readable", &self.project, &json!({"board":board}))?["revision"].clone()
            };
            require(r.as_i64().is_some(), "暂无已保存版本", "NO_SAVED_VERSION")?;
            return Ok(r.as_i64());
        }
        let db = self.connect()?;
        Ok(db.query_row(
            "SELECT max(revision) FROM revisions WHERE board_id=?",
            [board],
            |r| r.get(0),
        )?)
    }
    pub fn readable(&self, board: &str) -> Result<Value> {
        if let Some(db) = &self.database {
            let doc = db.call("readable", &self.project, &json!({"board":board}))?;
            require(!doc.is_null(), "暂无已保存版本", "NO_SAVED_VERSION")?;
            return self.decode(&doc);
        }
        let mut db = self.connect()?;
        let tx = db.transaction()?;
        let stored: Option<String> = tx
            .query_row(
                "SELECT document FROM revisions WHERE board_id=? ORDER BY revision DESC LIMIT 1",
                [board],
                |r| r.get(0),
            )
            .optional()?;
        let mut doc =
            parse(stored.ok_or_else(|| Error::new("NO_SAVED_VERSION", "暂无已保存版本"))?)?;
        if self.is_project() {
            doc["manifest"]["annotations"] = Self::read_notes(&tx, board)?;
        }
        Ok(doc)
    }
    fn read_notes(db: &Connection, board: &str) -> Result<Value> {
        let stored: Option<String> = db
            .query_row(
                "SELECT payload FROM annotations WHERE board_id=?",
                [board],
                |r| r.get(0),
            )
            .optional()?;
        stored
            .map(parse)
            .transpose()
            .map(|v| v.unwrap_or_else(|| json!([])))
    }
    pub fn note_context(doc: &Value, notes: &mut Value, previous: &Value, preserve_incoming: bool) {
        if let Some(notes) = notes.as_array_mut() {
            for note in notes {
                let old = previous
                    .as_array()
                    .into_iter()
                    .flatten()
                    .find(|n| n["id"] == note["id"]);
                if let Some(old) = old {
                    note["context"] = old.get("context").cloned().unwrap_or_else(|| json!({}));
                } else if !(preserve_incoming && note["context"].is_object()) {
                    let filters = doc["manifest"]["filters"]
                        .as_array()
                        .cloned()
                        .or_else(|| note["view"]["filters"].as_array().cloned())
                        .unwrap_or_default();
                    note["context"] = json!({"designRevision":doc["revision"],"dataVersions":doc["snapshot"].get("datasetRefs").cloned().unwrap_or_else(||json!({})),"filters":filters});
                }
            }
        }
    }
    fn save_notes(
        &self,
        db: &Connection,
        doc: &Value,
        notes: &mut Value,
        previous: Option<&Value>,
    ) -> Result<bool> {
        let board = doc["id"].as_str().unwrap_or("");
        let old = if let Some(p) = previous {
            p.clone()
        } else {
            Self::read_notes(db, board)?
        };
        Self::note_context(doc, notes, &old, false);
        if !equivalent_json(notes, &old) {
            db.execute(
                "INSERT OR REPLACE INTO annotations VALUES(?,?)",
                params![board, raw(notes)?],
            )?;
            db.execute(
                "INSERT INTO annotation_events VALUES(?,?,?,?)",
                params![board, utcnow(), revision_from(doc)?, raw(notes)?],
            )?;
            return Ok(true);
        }
        Ok(false)
    }
    fn annotation_state_db(
        &self,
        db: &Connection,
        board: &str,
        include_targets: bool,
    ) -> Result<Value> {
        // Feedback reads only small metadata; chart declarations and business rows
        // stay inside SQLite instead of being decoded on every annotation save.
        let state = db.query_row(
            "SELECT revision, json_extract(document,'$.manifest.title'), json_extract(document,'$.manifest.viewMode'), json_extract(document,'$.manifest.filters'), json_extract(document,'$.snapshot.datasetRefs') FROM boards WHERE id=?",
            [board],
            |r| Ok((r.get::<_,i64>(0)?,r.get::<_,String>(1)?,r.get::<_,Option<String>>(2)?,r.get::<_,Option<String>>(3)?,r.get::<_,Option<String>>(4)?)),
        ).optional()?.ok_or_else(|| Error::new("NOT_FOUND", "Dashboard not found").with_status(404))?;
        let components = if include_targets {
            let mut statement = db.prepare("SELECT c.key,json_extract(c.value,'$.title'),json_extract(c.value,'$.kind') FROM boards,json_each(document,'$.manifest.components') AS c WHERE boards.id=?")?;
            let values = statement.query_map([board], |r| Ok((r.get::<_,String>(0)?,json!({"title":r.get::<_,Option<String>>(1)?.unwrap_or_default(),"kind":r.get::<_,Option<String>>(2)?}))))?
                .collect::<std::result::Result<serde_json::Map<String,Value>,_>>()?;
            Value::Object(values)
        } else {
            Value::Null
        };
        Ok(
            json!({"id":board,"revision":state.0,"title":state.1,"annotations":Self::read_notes(db,board)?,"components":components,"viewMode":state.2,"filters":parse(state.3.unwrap_or_else(||"[]".into()))?,"datasetRefs":parse(state.4.unwrap_or_else(||"{}".into()))?}),
        )
    }
    pub fn annotation_state(&self, board: &str, include_targets: bool) -> Result<Value> {
        model::check_identifier(board)?;
        if let Some(db) = &self.database {
            if db.backend == "neon" {
                return db.call(
                    "annotation_read",
                    &self.project,
                    &json!({"board":board,"includeTargets":include_targets}),
                );
            }
            let doc = db.call("get", &self.project, &json!({"board":board}))?;
            return Ok(
                json!({"id":board,"revision":doc["revision"],"title":doc["manifest"]["title"],"annotations":notes(&doc),"components":if include_targets{doc["manifest"]["components"].clone()}else{Value::Null},"viewMode":doc["manifest"]["viewMode"],"filters":doc["manifest"]["filters"],"datasetRefs":doc["snapshot"].get("datasetRefs").cloned().unwrap_or_else(||json!({}))}),
            );
        }
        let mut db = self.connect()?;
        let tx = db.transaction()?;
        self.annotation_state_db(&tx, board, include_targets)
    }
    pub fn update_annotations(
        &self,
        board: &str,
        expected: i64,
        previous: &Value,
        notes: &Value,
    ) -> Result<Value> {
        model::check_identifier(board)?;
        let mut notes = notes.clone();
        if let Some(db) = &self.database {
            let state = self.annotation_state(board, true)?;
            Self::check_annotation_state(&state, expected, previous)?;
            model::validate_annotations(&notes, Some(&state["components"]))?;
            let doc = json!({"revision":expected,"snapshot":{"datasetRefs":state["datasetRefs"]},"manifest":{"filters":state["filters"]}});
            Self::note_context(&doc, &mut notes, previous, false);
            if equivalent_json(&notes, previous) {
                return Ok(json!({"dashboardId":board,"revision":expected,"annotations":notes}));
            }
            let mut args =
                json!({"board":board,"expected":expected,"previousNotes":previous,"at":utcnow()});
            if db.backend == "neon" {
                args["notes"] = notes;
                return db.call("annotation_write", &self.project, &args);
            }
            let mut stored = db.call("get", &self.project, &json!({"board":board}))?;
            stored["manifest"]["annotations"] = notes;
            args["document"] = stored;
            let saved = db.call("commit", &self.project, &args)?;
            return Ok(
                json!({"dashboardId":board,"revision":saved["revision"],"annotations":saved["manifest"]["annotations"]}),
            );
        }
        let mut db = self.connect()?;
        let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        let state = self.annotation_state_db(&tx, board, true)?;
        Self::check_annotation_state(&state, expected, previous)?;
        model::validate_annotations(&notes, Some(&state["components"]))?;
        let doc = json!({"id":board,"revision":expected,"manifest":{"filters":state["filters"]},"snapshot":{"datasetRefs":state["datasetRefs"]}});
        self.save_notes(&tx, &doc, &mut notes, Some(previous))?;
        tx.commit()?;
        self.sync_mirrors(board, false, true, false, Some(&[]), false)?;
        Ok(json!({"dashboardId":board,"revision":expected,"annotations":notes}))
    }
    fn check_annotation_state(state: &Value, expected: i64, previous: &Value) -> Result<()> {
        if state["revision"] != expected {
            return Err(Error::new(
                "REVISION_CONFLICT",
                "页面已更新，请重新打开批注。当前输入已保留。",
            )
            .with_status(409));
        }
        if !equivalent_json(&state["annotations"], previous) {
            return Err(Error::new(
                "ANNOTATION_CONFLICT",
                "批注已被其他页面更新，请重新打开批注。当前输入已保留。",
            )
            .with_status(409));
        }
        Ok(())
    }
    pub fn append_annotation(
        &self,
        board: &str,
        note: &Value,
        context_document: Option<&Value>,
    ) -> Result<Value> {
        model::check_identifier(board)?;
        model::validate_annotations(&json!([note]), None)?;
        if let Some(context) = context_document {
            require(
                context["id"] == board,
                "Annotation context belongs to another dashboard",
                "INVALID_ARGUMENT",
            )?;
            model::validate_annotations(&json!([note]), context["manifest"].get("components"))?;
        }
        if let Some(db) = &self.database {
            if db.backend == "neon" && context_document.is_none() {
                let mut result = db.call(
                    "annotation_append",
                    &self.project,
                    &json!({"board":board,"note":note,"at":utcnow()}),
                )?;
                let limit = result
                    .as_object_mut()
                    .and_then(|m| m.remove("limitReached"))
                    .unwrap_or(Value::Null);
                require(
                    !result["annotation"].is_null(),
                    if limit == true {
                        "At most 100 annotations per document"
                    } else {
                        "Unknown annotation component"
                    },
                    "INVALID_DOCUMENT",
                )?;
                return Ok(result);
            }
            for attempt in 0..5 {
                let mut doc = db.call("get", &self.project, &json!({"board":board}))?;
                let previous = notes(&doc);
                if let Some(existing) = arr(&previous).into_iter().find(|n| n["id"] == note["id"]) {
                    return Ok(
                        json!({"dashboardId":board,"revision":doc["revision"],"annotation":existing}),
                    );
                }
                let mut additions = json!([note]);
                Self::note_context(
                    context_document.unwrap_or(&doc),
                    &mut additions,
                    &json!([]),
                    false,
                );
                let new_note = additions[0].clone();
                let mut all = arr(&previous);
                all.push(new_note.clone());
                let all = json!(all);
                model::validate_annotations(
                    &all,
                    if context_document.is_some() {
                        None
                    } else {
                        doc["manifest"].get("components")
                    },
                )?;
                doc["manifest"]["annotations"] = all;
                match db.call("commit",&self.project,&json!({"board":board,"expected":doc["revision"],"previousNotes":previous,"document":doc,"at":utcnow()})){Ok(_)=>return Ok(json!({"dashboardId":board,"revision":doc["revision"],"annotation":new_note,"independentSave":true})),Err(e)if ["REVISION_CONFLICT","ANNOTATION_CONFLICT"].contains(&e.code.as_str())=>{if attempt==4{return Err(Error::new("ANNOTATION_SAVE_RETRY","批注暂未保存，请重试。").with_status(503));}},Err(e)=>return Err(e)}
            }
            return Err(
                Error::new("ANNOTATION_SAVE_RETRY", "批注暂未保存，请重试。").with_status(503),
            );
        }
        let mut db = self.connect()?;
        let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        let state = self.annotation_state_db(
            &tx,
            board,
            !note["componentId"].is_null() && note.get("anchor").is_none(),
        )?;
        let previous = &state["annotations"];
        let existing = arr(previous).into_iter().find(|n| n["id"] == note["id"]);
        let mut saved = note.clone();
        if existing.is_none() {
            let mut all = arr(previous);
            all.push(saved.clone());
            let mut all = json!(all);
            model::validate_annotations(
                &all,
                if state["components"].is_null() {
                    None
                } else {
                    Some(&state["components"])
                },
            )?;
            let fallback = json!({"id":board,"revision":state["revision"],"manifest":{"filters":state["filters"]},"snapshot":{"datasetRefs":state["datasetRefs"]}});
            self.save_notes(
                &tx,
                context_document.unwrap_or(&fallback),
                &mut all,
                Some(previous),
            )?;
            saved = all.as_array().unwrap().last().unwrap().clone();
        }
        tx.commit()?;
        self.sync_mirrors(board, false, true, false, Some(&[]), false)?;
        Ok(
            json!({"dashboardId":board,"revision":state["revision"],"annotation":existing.unwrap_or(saved)}),
        )
    }
    pub fn mutate(
        &self,
        board: &str,
        expected: i64,
        operations: Option<&[Value]>,
        restore_revision: Option<i64>,
        use_current_data: bool,
        expected_annotations: Option<&Value>,
    ) -> Result<Value> {
        model::check_identifier(board)?;
        require(
            expected > 0,
            "expectedRevision is required",
            "INVALID_DOCUMENT",
        )?;
        if self.database.is_some() {
            return self.cloud_mutate(
                board,
                expected,
                operations,
                restore_revision,
                use_current_data,
                expected_annotations,
            );
        }
        let mut db = self.connect()?;
        let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        let row: Option<(i64, String)> = tx
            .query_row(
                "SELECT revision,document FROM boards WHERE id=?",
                [board],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .optional()?;
        let (revision, raw_current) =
            row.ok_or_else(|| Error::new("NOT_FOUND", "Dashboard not found").with_status(404))?;
        require(revision==expected,format!("Expected revision {expected}; current revision is {revision}. Reload before editing."),"REVISION_CONFLICT")?;
        let mut current = parse(raw_current)?;
        if self.is_project() {
            current["manifest"]["annotations"] = Self::read_notes(&tx, board)?;
        }
        let previous = notes(&current);
        if let Some(expected_notes) = expected_annotations {
            require(
                restore_revision.is_none()
                    && operations.is_some_and(|o| {
                        !o.is_empty() && o.iter().all(|o| o["op"] == "set_annotations")
                    }),
                "Independent annotation saves may only replace annotations",
                "INVALID_DOCUMENT",
            )?;
            require(
                equivalent_json(&previous, expected_notes),
                "批注已被其他页面更新，请重试以保留最新批注。",
                "ANNOTATION_CONFLICT",
            )?;
        }
        let mut doc = if let Some(old) = restore_revision {
            let mut stored: Option<String> = tx
                .query_row(
                    "SELECT document FROM revisions WHERE board_id=? AND revision=?",
                    params![board, old],
                    |r| r.get(0),
                )
                .optional()?;
            if stored.is_none() && self.is_project() {
                let exists:bool=tx.query_row("SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name='releases')",[],|r|r.get(0))?;
                if exists {
                    stored=tx.query_row("SELECT document FROM releases WHERE board_id=? AND revision=? ORDER BY id DESC LIMIT 1",params![board,old],|r|r.get(0)).optional()?;
                }
            }
            let mut restored = parse(
                stored.ok_or_else(|| Error::new("INVALID_DOCUMENT", "Checkpoint not found"))?,
            )?;
            if self.is_project() {
                restored["manifest"]["annotations"] = previous.clone();
                if use_current_data {
                    restored["snapshot"] = current["snapshot"].clone();
                }
            }
            restored
        } else {
            let ops = operations
                .ok_or_else(|| Error::new("INVALID_DOCUMENT", "operations must be an array"))?;
            let mut changed = model::apply_operations(&current, ops)?;
            if self.is_project() && !ops.iter().any(|o| o["op"] == "set_annotations") {
                changed["manifest"]["annotations"] = previous.clone();
            }
            changed
        };
        if self.is_project() {
            doc["revision"] = json!(expected);
            doc = self.compact(&doc)?;
            if equivalent_json(&doc, &current) {
                tx.commit()?;
                return self.compatible(&current);
            }
            if expected_annotations.is_none() {
                doc["revision"] = json!(expected + 1);
            }
            let mut new_notes = notes(&doc);
            let changed = self.save_notes(&tx, &doc, &mut new_notes, Some(&previous))?;
            doc["manifest"]["annotations"] = new_notes;
            let mut stored = doc.clone();
            stored["manifest"]
                .as_object_mut()
                .unwrap()
                .remove("annotations");
            if expected_annotations.is_none() {
                tx.execute(
                    "UPDATE boards SET revision=?,document=? WHERE id=?",
                    params![expected + 1, raw(&stored)?, board],
                )?;
            }
            tx.commit()?;
            self.sync_mirrors(
                board,
                expected_annotations.is_none(),
                changed,
                false,
                Some(&[]),
                false,
            )?;
            Ok(doc)
        } else {
            doc["revision"] = json!(expected + 1);
            doc = self.compact(&doc)?;
            let raw = raw(&doc)?;
            tx.execute(
                "UPDATE boards SET revision=?,document=? WHERE id=?",
                params![expected + 1, raw, board],
            )?;
            let action = restore_revision
                .map(|r| format!("restore:{r}"))
                .unwrap_or_else(|| {
                    operations
                        .unwrap_or(&[])
                        .iter()
                        .filter_map(|o| o["op"].as_str())
                        .collect::<Vec<_>>()
                        .join(",")
                });
            tx.execute(
                "INSERT INTO revisions VALUES(?,?,?,?,?)",
                params![board, expected + 1, utcnow(), action, raw],
            )?;
            tx.execute(
                "DELETE FROM revisions WHERE board_id=? AND revision<=?",
                params![board, expected + 1 - 100],
            )?;
            tx.commit()?;
            self.compatible(&doc)
        }
    }
    fn cloud_mutate(
        &self,
        board: &str,
        expected: i64,
        operations: Option<&[Value]>,
        restore_revision: Option<i64>,
        use_current_data: bool,
        expected_annotations: Option<&Value>,
    ) -> Result<Value> {
        let db = self.database.as_ref().unwrap();
        let current = self.get(board, false)?;
        require(
            current["revision"] == expected,
            "Reload before editing",
            "REVISION_CONFLICT",
        )?;
        let previous = notes(&current);
        if let Some(expected_notes) = expected_annotations {
            require(
                restore_revision.is_none()
                    && operations.is_some_and(|o| {
                        !o.is_empty() && o.iter().all(|o| o["op"] == "set_annotations")
                    }),
                "Independent annotation saves may only replace annotations",
                "INVALID_DOCUMENT",
            )?;
            require(
                equivalent_json(&previous, expected_notes),
                "Reload annotations",
                "ANNOTATION_CONFLICT",
            )?;
        }
        let mut doc = if let Some(revision) = restore_revision {
            let mut restored = super::versions::Versions::new(self)?.read(board, revision)?;
            restored["manifest"]["annotations"] = previous.clone();
            if use_current_data {
                restored["snapshot"] = current["snapshot"].clone();
            }
            restored
        } else {
            let ops = operations
                .ok_or_else(|| Error::new("INVALID_DOCUMENT", "operations must be an array"))?;
            let mut doc = model::apply_operations(&current, ops)?;
            if !ops.iter().any(|o| o["op"] == "set_annotations") {
                doc["manifest"]["annotations"] = previous.clone();
            }
            doc
        };
        doc["revision"] = json!(expected);
        doc = self.compact(&doc)?;
        let mut comparable = current.clone();
        comparable.as_object_mut().unwrap().remove("computed");
        if equivalent_json(&doc, &comparable) {
            return Ok(current);
        }
        if expected_annotations.is_none() {
            doc["revision"] = json!(expected + 1);
        }
        let mut new_notes = notes(&doc);
        Self::note_context(&doc, &mut new_notes, &previous, false);
        doc["manifest"]["annotations"] = new_notes;
        self.decode(&db.call("commit",&self.project,&json!({"board":board,"expected":expected,"document":self.encode(&doc,Some(&current))?,"previousNotes":previous,"at":utcnow(),"restore":restore_revision.is_some(),"revision":restore_revision}))?)
    }
    pub fn begin(&self, board: &str, expected: i64) -> Result<Value> {
        if let Some(db) = &self.database {
            return db.call("begin",&self.project,&json!({"board":board,"expected":expected,"batch":uuid::Uuid::new_v4().simple().to_string()}));
        }
        require(
            self.revision(board)? == expected,
            "Reload before editing",
            "REVISION_CONFLICT",
        )?;
        let db = self.connect()?;
        db.execute(
            "INSERT OR IGNORE INTO batches VALUES(?,?,?)",
            params![board, uuid::Uuid::new_v4().simple().to_string(), expected],
        )?;
        Ok(db.query_row("SELECT * FROM batches WHERE board_id=?",[board],|r|Ok(json!({"board_id":r.get::<_,String>(0)?,"batch_id":r.get::<_,String>(1)?,"base_revision":r.get::<_,i64>(2)?})))?)
    }
    pub fn checkpoint(
        &self,
        board: &str,
        expected: i64,
        name: &str,
        published: bool,
        batch_id: Option<&str>,
    ) -> Result<Value> {
        if let Some(db) = &self.database {
            db.call("checkpoint",&self.project,&json!({"board":board,"expected":expected,"name":name,"protected":published,"batch":batch_id,"at":utcnow(),"keep":self.config["history"]["keepCheckpoints"]}))?;
        } else {
            let mut db = self.connect()?;
            let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
            let row: Option<(i64, String)> = tx
                .query_row(
                    "SELECT revision,document FROM boards WHERE id=?",
                    [board],
                    |r| Ok((r.get(0)?, r.get(1)?)),
                )
                .optional()?;
            let (revision, document) =
                row.ok_or_else(|| Error::new("REVISION_CONFLICT", "Reload before checkpoint"))?;
            require(
                revision == expected,
                "Reload before checkpoint",
                "REVISION_CONFLICT",
            )?;
            if let Some(batch) = batch_id {
                let existing: Option<String> = tx
                    .query_row(
                        "SELECT batch_id FROM batches WHERE board_id=?",
                        [board],
                        |r| r.get(0),
                    )
                    .optional()?;
                require(
                    existing.as_deref() == Some(batch),
                    "Unknown edit batch",
                    "INVALID_DOCUMENT",
                )?;
            }
            tx.execute(
                "INSERT OR IGNORE INTO revisions VALUES(?,?,?,?,?)",
                params![board, expected, utcnow(), "checkpoint", document],
            )?;
            if !name.is_empty() || published {
                tx.execute(
                    "INSERT OR REPLACE INTO checkpoint_meta VALUES(?,?,?,?)",
                    params![board, expected, name, i64::from(published)],
                )?;
            }
            tx.execute("DELETE FROM batches WHERE board_id=?", [board])?;
            tx.commit()?;
            self.sync_mirrors(board, false, false, true, Some(&[expected]), false)?;
        }
        Ok(json!({"dashboardId":board,"revision":expected,"name":name,"published":published}))
    }
    pub fn history(&self, board: &str, offset: usize, limit: usize) -> Result<Value> {
        require(
            limit > 0 && limit <= 10000,
            "Invalid history pagination",
            "INVALID_DOCUMENT",
        )?;
        if let Some(db) = &self.database {
            return db.call(
                "history",
                &self.project,
                &json!({"board":board,"offset":offset,"limit":limit}),
            );
        }
        if !self.is_project() {
            self.get(board, false)?;
        }
        let db = self.connect()?;
        let sql = if self.is_project() {
            "SELECT r.revision,r.created_at,r.action,m.name,coalesce(m.published,0) FROM revisions r LEFT JOIN checkpoint_meta m ON r.board_id=m.board_id AND r.revision=m.revision WHERE r.board_id=? ORDER BY r.revision DESC LIMIT ? OFFSET ?"
        } else {
            "SELECT revision,created_at,action,NULL,0 FROM revisions WHERE board_id=? ORDER BY revision DESC LIMIT ? OFFSET ?"
        };
        let mut stmt = db.prepare(sql)?;
        let result=stmt.query_map(params![board,if self.is_project(){limit as i64}else{100_i64},i64::try_from(offset).map_err(|_|Error::new("INVALID_ARGUMENT","History offset is too large"))?],|r|{let mut value=json!({"revision":r.get::<_,i64>(0)?,"created_at":r.get::<_,String>(1)?,"action":r.get::<_,String>(2)?});if self.is_project(){value["name"]=json!(r.get::<_,Option<String>>(3)?);value["published"]=json!(r.get::<_,i64>(4)?);}Ok(value)})?.collect::<std::result::Result<Vec<_>,_>>()?;
        Ok(json!(result))
    }
    pub fn label_checkpoint(
        &self,
        board: &str,
        expected: i64,
        revision: i64,
        name: &str,
        published: bool,
    ) -> Result<Value> {
        require(
            !name.trim().is_empty() || published,
            "A name or published marker is required",
            "INVALID_DOCUMENT",
        )?;
        if let Some(db) = &self.database {
            db.call("label",&self.project,&json!({"board":board,"expected":expected,"revision":revision,"name":name,"protected":published}))?;
        } else {
            let mut db = self.connect()?;
            let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
            let current: Option<i64> = tx
                .query_row("SELECT revision FROM boards WHERE id=?", [board], |r| {
                    r.get(0)
                })
                .optional()?;
            require(
                current == Some(expected),
                "Reload before labeling",
                "REVISION_CONFLICT",
            )?;
            let exists: bool = tx.query_row(
                "SELECT EXISTS(SELECT 1 FROM revisions WHERE board_id=? AND revision=?)",
                params![board, revision],
                |r| r.get(0),
            )?;
            require(exists, "Checkpoint not found", "INVALID_DOCUMENT")?;
            tx.execute(
                "INSERT OR REPLACE INTO checkpoint_meta VALUES(?,?,?,?)",
                params![board, revision, name, i64::from(published)],
            )?;
            tx.commit()?;
            self.sync_mirrors(board, false, false, true, Some(&[]), false)?;
        }
        Ok(json!({"revision":revision,"name":name,"published":published}))
    }
    pub fn diff(&self, board: &str, first: i64, second: i64) -> Result<Value> {
        let mut docs = vec![];
        if let Some(db) = &self.database {
            for revision in [first, second] {
                let current = self.get(board, false)?;
                docs.push(if current["revision"] == revision {
                    current
                } else {
                    self.decode(&db.call(
                        "revision_get",
                        &self.project,
                        &json!({"board":board,"revision":revision}),
                    )?)?
                });
            }
        } else {
            let db = self.connect()?;
            for revision in [first, second] {
                let mut stored: Option<String> = db
                    .query_row(
                        "SELECT document FROM revisions WHERE board_id=? AND revision=?",
                        params![board, revision],
                        |r| r.get(0),
                    )
                    .optional()?;
                if stored.is_none() {
                    stored = db
                        .query_row(
                            "SELECT document FROM boards WHERE id=? AND revision=?",
                            params![board, revision],
                            |r| r.get(0),
                        )
                        .optional()?;
                }
                docs.push(parse(stored.ok_or_else(|| {
                    Error::new("INVALID_DOCUMENT", "Checkpoint not found")
                })?)?);
            }
        }
        let a = sorted_pretty(&docs[0])?;
        let b = sorted_pretty(&docs[1])?;
        let diff = similar::TextDiff::from_lines(&a, &b)
            .unified_diff()
            .header(&first.to_string(), &second.to_string())
            .to_string();
        Ok(
            json!({"diff":diff.trim_end_matches('\n'),"semanticChanges":semantic_diff(&docs[0],&docs[1])}),
        )
    }
    pub fn sync_mirrors(
        &self,
        board: &str,
        draft: bool,
        annotations: bool,
        history: bool,
        checkpoints: Option<&[i64]>,
        rewrite: bool,
    ) -> Result<()> {
        if !self.is_project() || self.database.is_some() {
            return Ok(());
        }
        let folder = self.root.join(board);
        fs::create_dir_all(&folder)?;
        let lock = OpenOptions::new()
            .create(true)
            .read(true)
            .write(true)
            .truncate(false)
            .open(folder.join(".mirror.lock"))?;
        lock.lock_exclusive()?;
        let mut db = self.connect()?;
        let tx = db.transaction()?;
        if draft {
            let stored: String =
                tx.query_row("SELECT document FROM boards WHERE id=?", [board], |r| {
                    r.get(0)
                })?;
            write_json(&folder.join("draft.json"), &parse(stored)?)?;
        }
        if annotations {
            write_json(
                &folder.join("annotations.json"),
                &Self::read_notes(&tx, board)?,
            )?;
            let mut stmt=tx.prepare("SELECT board_id,at,revision,payload FROM annotation_events WHERE board_id=? ORDER BY rowid")?;
            let events=stmt.query_map([board],|r|Ok(json!({"board_id":r.get::<_,String>(0)?,"at":r.get::<_,String>(1)?,"revision":r.get::<_,i64>(2)?,"payload":r.get::<_,String>(3)?})))?.collect::<std::result::Result<Vec<_>,_>>()?;
            write_json(&folder.join("annotation-history.json"), &json!(events))?;
        }
        if history {
            let mut stmt=tx.prepare("SELECT r.revision,r.created_at,r.action,m.name,m.published FROM revisions r LEFT JOIN checkpoint_meta m ON r.board_id=m.board_id AND r.revision=m.revision WHERE r.board_id=? ORDER BY r.revision DESC")?;
            let h=stmt.query_map([board],|r|Ok(json!({"revision":r.get::<_,i64>(0)?,"created_at":r.get::<_,String>(1)?,"action":r.get::<_,String>(2)?,"name":r.get::<_,Option<String>>(3)?,"published":r.get::<_,Option<i64>>(4)?})))?.collect::<std::result::Result<Vec<_>,_>>()?;
            write_json(&folder.join("history.json"), &json!(h))?;
        }
        let directory = folder.join("checkpoints");
        let revisions = if let Some(revisions) = checkpoints {
            revisions.to_vec()
        } else {
            let mut stmt = tx.prepare("SELECT revision FROM revisions WHERE board_id=?")?;
            let list = stmt
                .query_map([board], |r| r.get(0))?
                .collect::<std::result::Result<Vec<i64>, _>>()?;
            if directory.exists() {
                for entry in fs::read_dir(&directory)? {
                    let path = entry?.path();
                    if path.extension().and_then(|s| s.to_str()) == Some("json") {
                        let old = path
                            .file_stem()
                            .and_then(|s| s.to_str())
                            .and_then(|s| s.parse::<i64>().ok());
                        if rewrite || old.is_none_or(|n| !list.contains(&n)) {
                            fs::remove_file(path)?;
                        }
                    }
                }
            }
            list
        };
        for revision in revisions {
            let path = directory.join(format!("{revision}.json"));
            let stored: Option<String> = tx
                .query_row(
                    "SELECT document FROM revisions WHERE board_id=? AND revision=?",
                    params![board, revision],
                    |r| r.get(0),
                )
                .optional()?;
            if let Some(stored) = stored {
                if !path.exists() {
                    write_json(&path, &parse(stored)?)?;
                }
            } else if path.exists() {
                fs::remove_file(path)?;
            }
        }
        tx.commit()?;
        FileExt::unlock(&lock)?;
        Ok(())
    }
    pub fn migrate(&self, board: &str, expected: i64) -> Result<Value> {
        require(
            self.database.is_none(),
            "Cloud projects already use durable data versions",
            "ALREADY_MIGRATED",
        )?;
        model::check_identifier(board)?;
        let backup_id = format!("{board}-{}", uuid::Uuid::new_v4().simple());
        let folder = self.root.join("backups");
        fs::create_dir_all(&folder)?;
        let mut db = self.connect()?;
        let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        let row: Option<(i64, String)> = tx
            .query_row(
                "SELECT revision,document FROM boards WHERE id=?",
                [board],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .optional()?;
        let (revision, document) =
            row.ok_or_else(|| Error::new("NOT_FOUND", "Dashboard not found"))?;
        require(
            revision == expected,
            "Reload before migrating",
            "REVISION_CONFLICT",
        )?;
        let mut stmt = tx.prepare(
            "SELECT board_id,revision,created_at,action,document FROM revisions WHERE board_id=?",
        )?;
        let revisions=stmt.query_map([board],|r|Ok(json!({"board_id":r.get::<_,String>(0)?,"revision":r.get::<_,i64>(1)?,"created_at":r.get::<_,String>(2)?,"action":r.get::<_,String>(3)?,"document":r.get::<_,String>(4)?})))?.collect::<std::result::Result<Vec<_>,_>>()?;
        drop(stmt);
        write_json(
            &folder.join(format!("{backup_id}.json")),
            &json!({"board":{"id":board,"revision":revision,"document":document},"revisions":revisions}),
        )?;
        let mut current = self.compact(&parse(document)?)?;
        current["snapshot"]["localMode"] = json!(true);
        tx.execute(
            "UPDATE boards SET document=? WHERE id=?",
            params![raw(&current)?, board],
        )?;
        for old in &revisions {
            let old_doc = parse(old["document"].as_str().unwrap_or("").to_owned())?;
            let doc = self.compact(&old_doc)?;
            tx.execute(
                "UPDATE revisions SET document=? WHERE board_id=? AND revision=?",
                params![raw(&doc)?, board, old["revision"].as_i64().unwrap_or(0)],
            )?;
        }
        tx.commit()?;
        self.sync_mirrors(board, true, true, true, None, true)?;
        Ok(json!({"backupId":backup_id,"revision":expected,"revisionsMigrated":revisions.len()}))
    }
    pub fn rollback_migration(&self, board: &str, expected: i64, backup_id: &str) -> Result<Value> {
        require(
            self.database.is_none(),
            "Local SQLite migration backups are not cloud revisions",
            "UNSUPPORTED_OPERATION",
        )?;
        require(
            backup_id.starts_with(&format!("{board}-"))
                && backup_id
                    .chars()
                    .all(|c| c.is_alphanumeric() || c == '-' || c == '_'),
            "Invalid migration backup id",
            "INVALID_DOCUMENT",
        )?;
        let path = self.root.join("backups").join(format!("{backup_id}.json"));
        require(
            path.is_file(),
            "Migration backup not found",
            "INVALID_DOCUMENT",
        )?;
        let backup: Value = serde_json::from_slice(&fs::read(path)?)?;
        let old = &backup["board"];
        require(
            old["id"] == board,
            "Migration backup belongs to another dashboard",
            "INVALID_DOCUMENT",
        )?;
        let mut db = self.connect()?;
        let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        let current: Option<i64> = tx
            .query_row("SELECT revision FROM boards WHERE id=?", [board], |r| {
                r.get(0)
            })
            .optional()?;
        require(
            current == Some(expected),
            "Reload before rollback",
            "REVISION_CONFLICT",
        )?;
        let mut doc = parse(old["document"].as_str().unwrap_or("").to_owned())?;
        doc["revision"] = json!(expected + 1);
        model::validate(&doc)?;
        let raw = raw(&doc)?;
        tx.execute(
            "UPDATE boards SET revision=?,document=? WHERE id=?",
            params![expected + 1, raw, board],
        )?;
        tx.execute(
            "INSERT INTO revisions VALUES(?,?,?,?,?)",
            params![board, expected + 1, utcnow(), "migration-rollback", raw],
        )?;
        tx.commit()?;
        Ok(doc)
    }
}
fn sorted_pretty(value: &Value) -> Result<String> {
    fn sorted(v: &Value) -> Value {
        match v {
            Value::Object(m) => {
                let mut keys: Vec<_> = m.keys().collect();
                keys.sort();
                Value::Object(
                    keys.into_iter()
                        .map(|k| (k.clone(), sorted(&m[k])))
                        .collect(),
                )
            }
            Value::Array(a) => json!(a.iter().map(sorted).collect::<Vec<_>>()),
            _ => v.clone(),
        }
    }
    Ok(serde_json::to_string_pretty(&sorted(value))?)
}
pub fn semantic_diff(before: &Value, after: &Value) -> Value {
    fn compare(path: Vec<String>, old: &Value, new: &Value, out: &mut Vec<Value>) {
        if equivalent_json(old, new) {
            return;
        }
        if let (Some(a), Some(b)) = (old.as_object(), new.as_object()) {
            let mut keys: Vec<_> = a.keys().chain(b.keys()).collect();
            keys.sort();
            keys.dedup();
            for key in keys {
                let mut p = path.clone();
                p.push(key.clone());
                compare(p, &old[key], &new[key], out);
            }
        } else {
            out.push(json!({"path":path,"change":if new.is_null(){"removed"}else if old.is_null(){"added"}else{"changed"}}));
        }
    }
    let a = &before["manifest"];
    let b = &after["manifest"];
    let mut changes = vec![];
    compare(
        vec!["metrics".into()],
        &a["metrics"],
        &b["metrics"],
        &mut changes,
    );
    compare(
        vec!["filters".into()],
        &a["filters"],
        &b["filters"],
        &mut changes,
    );
    let mut keys: Vec<_> = a["components"]
        .as_object()
        .into_iter()
        .flatten()
        .map(|(k, _)| k.clone())
        .chain(
            b["components"]
                .as_object()
                .into_iter()
                .flatten()
                .map(|(k, _)| k.clone()),
        )
        .collect();
    keys.sort();
    keys.dedup();
    for cid in keys {
        let old = &a["components"][&cid];
        let new = &b["components"][&cid];
        if old.is_null() || new.is_null() {
            compare(
                vec!["components".into(), cid],
                &if old.is_null() {
                    Value::Null
                } else {
                    json!(true)
                },
                &if new.is_null() {
                    Value::Null
                } else {
                    json!(true)
                },
                &mut changes,
            );
            continue;
        }
        for field in ["binding", "datasetId", "measures", "analysis"] {
            compare(
                vec!["components".into(), cid.clone(), field.into()],
                &old[field],
                &new[field],
                &mut changes,
            );
        }
        for field in ["explanation", "presentation", "encoding"] {
            compare(
                vec![
                    "components".into(),
                    cid.clone(),
                    "config".into(),
                    field.into(),
                ],
                &old["config"][field],
                &new["config"][field],
                &mut changes,
            );
        }
    }
    let count = changes.len();
    changes.truncate(200);
    json!({"count":count,"changes":changes,"truncated":count>200})
}

pub fn migrate_project(
    source: &Path,
    project: &Path,
    runtime: &Path,
    boards: &[String],
    apply: bool,
) -> Result<Value> {
    let source = Store::new(source, None)?;
    let mut inventory = vec![];
    let mut versions = serde_json::Map::new();
    for board in boards {
        let doc = source.get(board, false)?;
        let db = source.connect()?;
        let mut stmt =
            db.prepare("SELECT document FROM revisions WHERE board_id=? ORDER BY revision")?;
        let history = stmt
            .query_map([board], |r| r.get::<_, String>(0))?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        let mut documents = vec![doc.clone()];
        for raw in &history {
            documents.push(serde_json::from_str(raw)?);
        }
        for d in documents {
            for group in ["datasetRefs", "componentDataRefs"] {
                if let Some(refs) = d["snapshot"][group].as_object() {
                    for r in refs.values() {
                        let key = r["version"].as_str().ok_or_else(|| {
                            Error::new("INVALID_DOCUMENT", "Invalid data version")
                        })?;
                        versions.insert(key.into(), r.clone());
                    }
                }
            }
        }
        inventory.push(json!({"board":board,"revision":doc["revision"],"components":doc["manifest"]["components"].as_object().map_or(0,|m|m.len()),"annotations":arr(&notes(&doc)).len(),"checkpoints":history.len()}));
    }
    let mut summary = json!({"boards":inventory,"dataVersions":versions.len(),"rows":versions.values().map(|r|r["rowCount"].as_u64().unwrap_or(0)).sum::<u64>(),"applied":false});
    if !apply {
        return Ok(summary);
    }
    let target = Store::new(runtime, Some(project))?;
    require(
        !target.list()?.as_array().into_iter().flatten().any(|r| {
            r["id"]
                .as_str()
                .is_some_and(|id| boards.iter().any(|b| b == id))
        }),
        "Destination already contains a selected dashboard",
        "INVALID_DOCUMENT",
    )?;
    for reference in versions.values() {
        let mut fields = serde_json::Map::new();
        let keys = reference["fieldOrder"]
            .as_array()
            .cloned()
            .unwrap_or_else(|| {
                reference["fields"]
                    .as_object()
                    .into_iter()
                    .flatten()
                    .map(|(k, _)| json!(k))
                    .collect()
            });
        for key in keys {
            let key = key
                .as_str()
                .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Invalid field order"))?;
            fields.insert(key.to_owned(), reference["fields"][key].clone());
        }
        let source_data = source.data.clone();
        let source_ref = reference.clone();
        let (tx, rx) = std::sync::mpsc::sync_channel::<Result<Value>>(128);
        let producer = std::thread::spawn(move || {
            let result = source_data.for_each_row(&source_ref, &[], None, &[], "", |row| {
                tx.send(Ok(row))
                    .map_err(|_| Error::new("TRANSFER_CANCELLED", "Dataset receiver closed"))
            });
            if let Err(error) = result {
                let _ = tx.send(Err(error));
            }
        });
        let copied = target.data.import_iter(rx, &Value::Object(fields));
        producer
            .join()
            .map_err(|_| Error::new("MIGRATION_FAILED", "Source reader stopped"))?;
        require(
            copied? == *reference,
            "Migrated dataset differs from source",
            "INVALID_DOCUMENT",
        )?;
    }
    for board in boards {
        let mut doc = source.get(board, false)?;
        let old = source.connect()?;
        let mut db = target.connect()?;
        let transaction = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        let mut stmt=old.prepare("SELECT revision,created_at,action,document FROM revisions WHERE board_id=? ORDER BY revision")?;
        let history = stmt
            .query_map([board], |r| {
                Ok((
                    r.get::<_, i64>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, String>(2)?,
                    r.get::<_, String>(3)?,
                ))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        for (revision, at, action, raw_doc) in history {
            let mut historic: Value = serde_json::from_str(&raw_doc)?;
            let notes = historic["manifest"]
                .as_object_mut()
                .unwrap()
                .remove("annotations")
                .unwrap_or_else(|| json!([]));
            transaction.execute(
                "INSERT INTO annotation_events VALUES(?,?,?,?)",
                params![board, at, revision, raw(&notes)?],
            )?;
            transaction.execute(
                "INSERT INTO revisions VALUES(?,?,?,?,?)",
                params![board, revision, at, action, raw(&historic)?],
            )?;
        }
        let mut current_notes = doc["manifest"]
            .as_object_mut()
            .unwrap()
            .remove("annotations")
            .unwrap_or_else(|| json!([]));
        target.save_notes(&transaction, &doc, &mut current_notes, None)?;
        transaction.execute(
            "INSERT INTO boards VALUES(?,?,?)",
            params![board, revision_from(&doc)?, raw(&doc)?],
        )?;
        transaction.commit()?;
        target.sync_mirrors(board, true, true, true, None, false)?;
        let restored = target.get(board, false)?;
        let expected = source.get(board, false)?;
        require(
            restored["manifest"]["components"] == expected["manifest"]["components"],
            "Component migration mismatch",
            "INVALID_DOCUMENT",
        )?;
        require(
            restored["snapshot"] == expected["snapshot"],
            "Data reference migration mismatch",
            "INVALID_DOCUMENT",
        )?;
        let note_ids = |d: &Value| {
            arr(&notes(d))
                .into_iter()
                .map(|n| n["id"].clone())
                .collect::<Vec<_>>()
        };
        require(
            note_ids(&restored) == note_ids(&expected),
            "Annotation migration mismatch",
            "INVALID_DOCUMENT",
        )?;
    }
    summary["applied"] = json!(true);
    write_json(&target.root.join("migration-report.json"), &summary)?;
    Ok(summary)
}

#[cfg(test)]
mod runtime_storage_tests {
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
        assert!(
            Versions::new(&store).unwrap().status("board").unwrap()["publishedRevision"].is_null()
        );
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
        let (status, document) =
            result.expect("saved-version reads must not take a SQLite write lock");
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
}
