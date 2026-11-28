//! Immutable SQLite datasets, bounded result caches and streaming native queries.
use super::{
    error::{require, Error, Result},
    serialization::canonical_json,
};
use rusqlite::{
    functions::FunctionFlags,
    params_from_iter,
    types::{Value as SqlValue, ValueRef},
    Connection, OpenFlags, OptionalExtension,
};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, HashMap, HashSet, VecDeque},
    fs,
    io::Write,
    path::{Path, PathBuf},
    sync::{Arc, Condvar, Mutex},
    time::{Duration, Instant},
};

pub const MAX_RESULT_ROWS: usize = 100_000;
const OPTION_PROBE_ROWS: usize = 4096;
const OPTION_PROBE_BYTES: usize = 512 * 1024;
type Pending = Arc<(Mutex<Option<Result<Value>>>, Condvar)>;
#[derive(Default)]
struct CacheState {
    values: HashMap<String, (Value, usize)>,
    order: VecDeque<String>,
    pending: HashMap<String, Pending>,
    bytes: usize,
}
struct PendingOwner<'a> {
    state: &'a Mutex<CacheState>,
    key: &'a str,
    pending: &'a Pending,
    completed: bool,
}
impl Drop for PendingOwner<'_> {
    fn drop(&mut self) {
        if self.completed {
            return;
        }
        // A failed owner must never strand requests already waiting on this
        // calculation. Keep unwinding the original panic after this cleanup.
        if let Ok(mut state) = self.state.lock() {
            if state
                .pending
                .get(self.key)
                .is_some_and(|pending| Arc::ptr_eq(pending, self.pending))
            {
                state.pending.remove(self.key);
            }
        }
        let (lock, ready) = &**self.pending;
        if let Ok(mut value) = lock.lock() {
            if value.is_none() {
                *value = Some(Err(Error::new(
                    "INTERNAL_ERROR",
                    "Query calculation stopped before completion",
                )));
            }
        }
        ready.notify_all();
    }
}
#[derive(Clone)]
pub struct QueryCache {
    state: Arc<Mutex<CacheState>>,
    max_bytes: usize,
    max_entries: usize,
}
impl Default for QueryCache {
    fn default() -> Self {
        Self::new(32 * 1024 * 1024, 256)
    }
}
impl QueryCache {
    pub fn new(max_bytes: usize, max_entries: usize) -> Self {
        Self {
            state: Arc::new(Mutex::new(CacheState::default())),
            max_bytes,
            max_entries,
        }
    }
    pub fn get<F: FnOnce() -> Result<Value>>(
        &self,
        key: String,
        compute: F,
    ) -> Result<(Value, bool)> {
        let (pending, owner) = {
            let mut s = self
                .state
                .lock()
                .map_err(|_| Error::new("INTERNAL_ERROR", "Cache lock failed"))?;
            if let Some((v, _)) = s.values.get(&key) {
                let v = v.clone();
                s.order.retain(|k| k != &key);
                s.order.push_back(key);
                return Ok((v, true));
            }
            match s.pending.get(&key) {
                Some(p) => (p.clone(), false),
                None => {
                    let p = Arc::new((Mutex::new(None), Condvar::new()));
                    s.pending.insert(key.clone(), p.clone());
                    (p, true)
                }
            }
        };
        if !owner {
            let (lock, ready) = &*pending;
            let mut v = lock
                .lock()
                .map_err(|_| Error::new("INTERNAL_ERROR", "Cache lock failed"))?;
            while v.is_none() {
                v = ready
                    .wait(v)
                    .map_err(|_| Error::new("INTERNAL_ERROR", "Cache wait failed"))?;
            }
            return v.as_ref().unwrap().clone().map(|v| (v, true));
        }
        let mut owner = PendingOwner {
            state: &self.state,
            key: &key,
            pending: &pending,
            completed: false,
        };
        let value = compute();
        {
            let mut s = self
                .state
                .lock()
                .map_err(|_| Error::new("INTERNAL_ERROR", "Cache lock failed"))?;
            if let Ok(v) = &value {
                let size = canonical_json(v)
                    .map(|raw| raw.len() + key.len())
                    .unwrap_or(usize::MAX);
                if size <= self.max_bytes / 4 {
                    s.values.insert(key.clone(), (v.clone(), size));
                    s.order.push_back(key.clone());
                    s.bytes += size;
                    while s.bytes > self.max_bytes || s.values.len() > self.max_entries {
                        if let Some(k) = s.order.pop_front() {
                            if let Some((_, n)) = s.values.remove(&k) {
                                s.bytes -= n;
                            }
                        } else {
                            break;
                        }
                    }
                }
            }
            s.pending.remove(&key);
        }
        let (lock, ready) = &*pending;
        *lock
            .lock()
            .map_err(|_| Error::new("INTERNAL_ERROR", "Cache lock failed"))? = Some(value.clone());
        ready.notify_all();
        owner.completed = true;
        value.map(|v| (v, false))
    }
}

pub fn semantic_filters(filters: &[Value]) -> Result<Value> {
    let mut result = Vec::new();
    for f in filters {
        let values = f["values"].as_array().cloned().unwrap_or_default();
        if values.is_empty() {
            continue;
        }
        let values = if f["op"] == "in" {
            let mut unique = BTreeMap::new();
            for v in values {
                unique.insert(canonical_json(&v)?, v);
            }
            unique.into_values().collect()
        } else {
            values
        };
        result.push(json!({"field":f["field"],"op":f["op"],"values":values}));
    }
    result.sort_by_cached_key(|v| canonical_json(v).unwrap_or_default());
    Ok(Value::Array(result))
}
pub(crate) fn sql_value(v: &Value) -> Result<SqlValue> {
    Ok(match v {
        Value::Null => SqlValue::Null,
        Value::Bool(b) => SqlValue::Integer(i64::from(*b)),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                SqlValue::Integer(i)
            } else if let Some(f) = n.as_f64() {
                require(f.is_finite(), "Non-finite number", "INVALID_ARGUMENT")?;
                SqlValue::Real(f)
            } else {
                return Err(Error::new(
                    "INVALID_ARGUMENT",
                    "Number is outside SQLite range",
                ));
            }
        }
        Value::String(s) => SqlValue::Text(s.clone()),
        _ => return Err(Error::new("INVALID_ARGUMENT", "Expected scalar value")),
    })
}
pub(crate) fn json_sql(v: ValueRef<'_>) -> rusqlite::Result<Value> {
    Ok(match v {
        ValueRef::Null => Value::Null,
        ValueRef::Integer(i) => json!(i),
        ValueRef::Real(f) => serde_json::Number::from_f64(f)
            .map(Value::Number)
            .ok_or_else(|| {
                rusqlite::Error::FromSqlConversionFailure(
                    0,
                    rusqlite::types::Type::Real,
                    "Non-finite SQL number".into(),
                )
            })?,
        ValueRef::Text(s) => Value::String(
            std::str::from_utf8(s)
                .map_err(|e| {
                    rusqlite::Error::FromSqlConversionFailure(
                        0,
                        rusqlite::types::Type::Text,
                        Box::new(e),
                    )
                })?
                .to_owned(),
        ),
        ValueRef::Blob(_) => {
            return Err(rusqlite::Error::InvalidColumnType(
                0,
                "value".into(),
                rusqlite::types::Type::Blob,
            ))
        }
    })
}
fn text_value(v: &Value, kind: &str, null_word: bool) -> String {
    match v {
        Value::Null => {
            if null_word {
                "null".into()
            } else {
                String::new()
            }
        }
        Value::Bool(b) => b.to_string(),
        Value::Number(n) if kind == "boolean" => {
            if n.as_i64().unwrap_or(0) != 0 {
                "true".into()
            } else {
                "false".into()
            }
        }
        Value::Number(n) => {
            if let Some(f) = n.as_f64() {
                if f.fract() == 0.0 {
                    format!("{f:.0}")
                } else {
                    n.to_string()
                }
            } else {
                n.to_string()
            }
        }
        Value::String(s) => s.clone(),
        _ => String::new(),
    }
}
fn sort_number(v: &Value) -> Option<f64> {
    let s = text_value(v, "", false)
        .chars()
        .filter(|c| c.is_ascii_digit() || *c == '.' || *c == '-')
        .collect::<String>();
    let mut end = 0;
    let mut digits = false;
    let mut dot = false;
    for (i, c) in s.char_indices() {
        if c.is_ascii_digit() {
            digits = true;
            end = i + 1;
        } else if c == '-' && i == 0 {
            end = 1;
        } else if c == '.' && !dot {
            dot = true;
            end = i + 1;
        } else {
            break;
        }
    }
    if !digits {
        return None;
    }
    s[..end].parse::<f64>().ok().filter(|v| v.is_finite())
}
pub fn time_grain(v: &Value, grain: &str) -> Result<Value> {
    if v.is_null() {
        return Ok(Value::Null);
    }
    let text = text_value(v, "", false);
    let valid = text.len() >= 7
        && text.as_bytes()[..4].iter().all(u8::is_ascii_digit)
        && text.as_bytes()[4] == b'-'
        && text.as_bytes()[5..7].iter().all(u8::is_ascii_digit)
        && (text.len() == 7 || text.as_bytes()[7] == b'-');
    require(
        valid,
        "Time grouping requires ISO dates",
        "INVALID_ARGUMENT",
    )?;
    let month: u32 = text[5..7]
        .parse()
        .map_err(|_| Error::new("INVALID_ARGUMENT", "Time grouping requires ISO dates"))?;
    require(
        (1..=12).contains(&month),
        "Time grouping requires ISO dates",
        "INVALID_ARGUMENT",
    )?;
    Ok(json!(if grain == "month" {
        text[..7].to_string()
    } else {
        format!("{} Q{}", &text[..4], (month - 1) / 3 + 1)
    }))
}

type PageCursorCache = (HashMap<String, (i64, Value)>, VecDeque<String>);

#[derive(Clone)]
pub struct LocalData {
    pub root: Option<PathBuf>,
    pub path: Option<PathBuf>,
    pub cache: QueryCache,
    pub cloud: Option<Arc<super::cloud::CloudData>>,
    memory: Option<Arc<Mutex<Connection>>>,
    mounts: Arc<Mutex<HashMap<String, PathBuf>>>,
    cursors: Arc<Mutex<PageCursorCache>>,
}
impl LocalData {
    pub fn new(root: Option<&Path>) -> Result<Self> {
        if let Some(p) = root {
            fs::create_dir_all(p)?;
        }
        let this = Self {
            root: root.map(Path::to_path_buf),
            path: root.map(|p| p.join("data.sqlite3")),
            cache: QueryCache::default(),
            cloud: None,
            memory: if root.is_none() {
                Some(Arc::new(Mutex::new(Connection::open_in_memory()?)))
            } else {
                None
            },
            mounts: Arc::new(Mutex::new(HashMap::new())),
            cursors: Arc::new(Mutex::new((HashMap::new(), VecDeque::new()))),
        };
        this.with_connection(|db|{db.execute_batch("CREATE TABLE IF NOT EXISTS versions(version TEXT PRIMARY KEY, metadata TEXT NOT NULL)")?;Ok(())})?;
        Ok(this)
    }
    pub fn with_cloud(root: &Path, project: &str, cos_enabled: bool) -> Result<Self> {
        let mut local = Self::new(Some(root))?;
        local.cloud = Some(Arc::new(super::cloud::CloudData::new(
            local.clone(),
            project,
            cos_enabled,
        )?));
        Ok(local)
    }
    pub fn set_partition_fields(&self, fields: &[String]) -> Result<()> {
        if let Some(cloud) = &self.cloud {
            cloud.set_partition_fields(fields)?;
        }
        Ok(())
    }
    pub fn validate_reference(&self, reference: &Value) -> Result<()> {
        if let Some(cloud) = &self.cloud {
            cloud.ensure_version(
                reference["version"]
                    .as_str()
                    .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid data version"))?,
            )?;
        }
        Ok(())
    }
    pub fn mount_version(&self, version: &str, path: &Path) -> Result<()> {
        check_version(version)?;
        self.mounts
            .lock()
            .map_err(|_| Error::new("INTERNAL_ERROR", "Dataset mount lock failed"))?
            .insert(version.into(), path.canonicalize()?);
        Ok(())
    }
    pub fn with_connection<T, F: FnOnce(&mut Connection) -> Result<T>>(&self, run: F) -> Result<T> {
        if let Some(path) = &self.path {
            let mut db = Connection::open(path)?;
            setup(&db)?;
            run(&mut db)
        } else {
            let mut db = self
                .memory
                .as_ref()
                .unwrap()
                .lock()
                .map_err(|_| Error::new("INTERNAL_ERROR", "Dataset connection lock failed"))?;
            setup(&db)?;
            run(&mut db)
        }
    }
    pub fn import_rows(&self, rows: &[Value], fields: &Value) -> Result<Value> {
        self.import_iter(rows.iter().cloned().map(Ok), fields)
    }
    pub fn import_iter<I: IntoIterator<Item = Result<Value>>>(
        &self,
        rows: I,
        fields: &Value,
    ) -> Result<Value> {
        let map = fields.as_object().ok_or_else(|| {
            Error::new(
                "INVALID_ARGUMENT",
                "fields must be a nonempty field metadata mapping",
            )
        })?;
        require(
            !map.is_empty(),
            "fields must be a nonempty field metadata mapping",
            "INVALID_ARGUMENT",
        )?;
        let keys = map.keys().cloned().collect::<Vec<_>>();
        let mut digest = Sha256::new();
        digest.update(canonical_json(fields)?.as_bytes());
        let mut sorted = keys.clone();
        sorted.sort();
        if keys != sorted {
            digest.update(b"\0fieldOrder:");
            digest.update(canonical_json(&json!(keys))?.as_bytes());
        }
        let reference = self.with_connection(|db| {
            let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
            let columns = (0..keys.len()).map(|i| format!("c{i}")).collect::<Vec<_>>();
            tx.execute_batch(&format!("CREATE TABLE staging ({}, _missing TEXT)", columns.join(",")))?;
            let insert = format!("INSERT INTO staging VALUES ({})", vec!["?"; keys.len() + 1].join(","));
            let (mut count, mut bytes, mut has_missing) = (0u64, 0u64, false);
            {
                let mut statement = tx.prepare(&insert)?;
                for row in rows {
                    let row = row?;
                    let values = row.as_object().ok_or_else(|| {
                        Error::new("INVALID_ARGUMENT", "Each row must be a field mapping")
                    })?;
                    require(
                        values.keys().all(|key| map.contains_key(key)),
                        "Each row must have no undeclared fields",
                        "INVALID_ARGUMENT",
                    )?;
                    let mut selected = Vec::with_capacity(keys.len());
                    let mut missing = Vec::new();
                    for key in &keys {
                        let value = values.get(key).cloned().unwrap_or(Value::Null);
                        let kind = map[key]["type"].as_str().unwrap_or("");
                        let valid = value.is_null() || match kind {
                            "number" => value.is_number()
                                && value.as_f64().is_some_and(f64::is_finite)
                                && (value.as_i64().is_some() || value.is_f64()),
                            "boolean" => value.is_boolean(),
                            "string" | "date" => value.is_string(),
                            _ => false,
                        };
                        require(valid, format!("Invalid scalar value for field: {key}"), "INVALID_ARGUMENT")?;
                        if !values.contains_key(key) {
                            missing.push(key.clone());
                        }
                        selected.push(value);
                    }
                    let raw = canonical_json(&json!(selected))?;
                    digest.update((raw.len() as u64).to_be_bytes());
                    digest.update(raw.as_bytes());
                    let mask = if missing.is_empty() {
                        None
                    } else {
                        Some(canonical_json(&json!(missing))?)
                    };
                    if let Some(mask) = &mask {
                        digest.update(mask.as_bytes());
                        has_missing = true;
                    }
                    digest.update(b"\0");
                    bytes += raw.len() as u64;
                    let mut parameters = selected.iter().map(sql_value).collect::<Result<Vec<_>>>()?;
                    parameters.push(mask.map(SqlValue::Text).unwrap_or(SqlValue::Null));
                    statement.execute(params_from_iter(parameters))?;
                    count += 1;
                }
            }
            let version = format!("{:x}", digest.finalize());
            let mut reference = json!({"version":version,"rowCount":count,"fields":fields,"fieldOrder":keys,"bytes":bytes});
            if has_missing {
                reference["hasMissingFields"] = json!(true);
            }
            let existing: Option<String> = tx.query_row(
                "SELECT metadata FROM versions WHERE version=?", [&version], |row| row.get(0),
            ).optional()?;
            if let Some(raw) = existing {
                tx.execute_batch("DROP TABLE staging")?;
                tx.commit()?;
                return metadata(&raw);
            }
            tx.execute_batch(&format!("ALTER TABLE staging RENAME TO d_{version}"))?;
            tx.execute("INSERT INTO versions VALUES (?,?)", rusqlite::params![version, canonical_json(&reference)?])?;
            tx.commit()?;
            Ok(reference)
        })?;
        if let Some(cloud) = &self.cloud {
            cloud.persist_cached(&reference)?;
        }
        Ok(reference)
    }
    pub fn import_sqlite(&self, path: &Path, table: &str, fields: Option<&Value>) -> Result<Value> {
        require(
            !table.is_empty(),
            "table must be a table name",
            "INVALID_ARGUMENT",
        )?;
        let db =
            Connection::open_with_flags(path.canonicalize()?, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
        db.execute_batch("PRAGMA query_only=ON")?;
        let exists: bool = db.query_row(
            "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name=?)",
            [table],
            |r| r.get(0),
        )?;
        require(exists, "Unknown SQLite table", "INVALID_ARGUMENT")?;
        let quoted = format!("\"{}\"", table.replace('"', "\"\""));
        let mut stmt = db.prepare(&format!("SELECT * FROM {quoted}"))?;
        let keys = stmt
            .column_names()
            .map(|s| s.to_string())
            .collect::<Vec<_>>();
        let inferred;
        if let Some(f) = fields {
            inferred = f.clone();
        } else {
            let mut types = Map::new();
            let mut info = db.prepare(&format!("PRAGMA table_info({quoted})"))?;
            let mut rows = info.query([])?;
            while let Some(row) = rows.next()? {
                let key: String = row.get(1)?;
                let ty: String = row.get(2)?;
                let numeric = ["INT", "REAL", "FLOA", "DOUB", "NUM", "DEC"]
                    .iter()
                    .any(|v| ty.to_uppercase().contains(v));
                types.insert(key, json!({"type":if numeric{"number"}else{"string"}}));
            }
            inferred = Value::Object(keys.iter().map(|k| (k.clone(), types[k].clone())).collect());
        }
        let mut rows = stmt.query([])?;
        let iter = std::iter::from_fn(|| match rows.next() {
            Ok(Some(r)) => Some((|| {
                let mut out = Map::new();
                for (i, k) in keys.iter().enumerate() {
                    let mut v = json_sql(r.get_ref(i)?)?;
                    if inferred[k]["type"] == "boolean" && matches!(v.as_i64(), Some(0 | 1)) {
                        v = json!(v.as_i64() == Some(1));
                    }
                    out.insert(k.clone(), v);
                }
                Ok(Value::Object(out))
            })()),
            Ok(None) => None,
            Err(e) => Some(Err(e.into())),
        });
        self.import_iter(iter, &inferred)
    }
    fn version(&self, db: &Connection, reference: &Value) -> Result<(String, Value)> {
        let version = reference["version"]
            .as_str()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid data version"))?;
        check_version(version)?;
        if let Some(cloud) = &self.cloud {
            let path = cloud.ensure_version(version)?;
            if self.path.as_ref().is_none_or(|p| p != &path) {
                self.mount_version(version, &path)?;
            }
        }
        let found: Option<String> = db
            .query_row(
                "SELECT metadata FROM versions WHERE version=?",
                [version],
                |r| r.get(0),
            )
            .optional()?;
        if let Some(raw) = found {
            return Ok((format!("d_{version}"), metadata(&raw)?));
        }
        let mounted = self
            .mounts
            .lock()
            .map_err(|_| Error::new("INTERNAL_ERROR", "Dataset mount lock failed"))?
            .get(version)
            .cloned();
        if let Some(path) = mounted {
            let alias = format!("a_{version}");
            let mut statement = db.prepare("PRAGMA database_list")?;
            let exists = statement
                .query_map([], |r| r.get::<_, String>(1))?
                .filter_map(std::result::Result::ok)
                .any(|s| s == alias);
            drop(statement);
            if !exists {
                let url = url::Url::from_file_path(&path)
                    .map_err(|_| Error::new("INVALID_PATH", "Invalid query file"))?;
                db.execute(
                    &format!("ATTACH DATABASE ? AS {alias}"),
                    [format!("{url}?mode=ro")],
                )?;
            }
            let raw: String = db.query_row(
                &format!("SELECT metadata FROM {alias}.versions WHERE version=?"),
                [version],
                |r| r.get(0),
            )?;
            return Ok((format!("{alias}.d_{version}"), metadata(&raw)?));
        }
        Err(Error::new("INVALID_ARGUMENT", "Unknown data version"))
    }
    pub fn describe(&self, version: &str) -> Result<Value> {
        if let Some(cloud) = &self.cloud {
            return cloud.describe(version);
        }
        self.with_connection(|db| Ok(self.version(db, &json!({"version":version}))?.1))
    }
    pub fn sqlite_source(&self, reference: &Value) -> Result<(PathBuf, Value)> {
        self.with_connection(|db| {
            let (table, meta) = self.version(db, reference)?;
            let alias = table.split_once('.').map(|v| v.0).unwrap_or("main");
            let mut stmt = db.prepare("PRAGMA database_list")?;
            let mut rows = stmt.query([])?;
            while let Some(r) = rows.next()? {
                if r.get::<_, String>(1)? == alias {
                    return Ok((PathBuf::from(r.get::<_, String>(2)?).canonicalize()?, meta));
                }
            }
            Err(Error::new("INVALID_PATH", "Memory data has no query file"))
        })
    }
    pub fn prepare_indexes(&self, reference: &Value, keys: &[String]) -> Result<()> {
        self.with_connection(|db| {
            let (table, m) = self.version(db, reference)?;
            indexes(
                db,
                &table,
                &m["fields"],
                &keys.iter().map(|k| json!({"field":k})).collect::<Vec<_>>(),
                &[],
            )
        })
    }
    // Keep the explicit selection axes shared by native callers and MCP views.
    #[allow(clippy::too_many_arguments)]
    pub fn rows(
        &self,
        reference: &Value,
        filters: &[Value],
        columns: Option<&[String]>,
        sort: &[Value],
        offset: u64,
        limit: usize,
        search: &str,
    ) -> Result<Value> {
        require(
            limit > 0 && limit <= MAX_RESULT_ROWS && offset <= i64::MAX as u64,
            "Invalid row pagination",
            "INVALID_ARGUMENT",
        )?;
        let start = Instant::now();
        self.with_connection(|db|{let(table,meta)=self.version(db,reference)?;let fields=&meta["fields"];indexes(db,&table,fields,filters,sort)?;let(where_sql,params)=where_clause(fields,filters,search)?;let(keys,selected,order)=selection(fields,columns,sort)?;let semantics=json!([reference["version"],semantic_filters(filters)?,search.to_lowercase()]);let total=if where_sql.is_empty(){meta["rowCount"].clone()}else{self.cache.get(canonical_json(&json!(["count",semantics]))?,||Ok(json!(db.query_row(&format!("SELECT COUNT(*) FROM {table}{where_sql}"),params_from_iter(params.iter()),|r|r.get::<_,i64>(0))?)))?.0};
            let mut seek=None;let mut direction="asc";if sort.len()==1 {let f=sort[0]["field"].as_str().unwrap_or("");let raw=raw_field(f);let field=if fields[f]["type"]=="string"&&fields[&raw]["type"]=="number"{raw.as_str()}else{f};if ["number","date","boolean"].contains(&fields[field]["type"].as_str().unwrap_or("")){seek=Some(column(fields,field)?);direction=sort[0]["direction"].as_str().unwrap_or("asc");}}
            let can_seek=sort.is_empty()||seek.is_some();let cursor_key=canonical_json(&json!([semantics,sort,keys,offset]))?;let previous=if offset>0&&can_seek{self.cursors.lock().map_err(|_|Error::new("INTERNAL_ERROR","Cursor lock failed"))?.0.get(&cursor_key).cloned()}else{None};let mut page_where=where_sql;let mut page_params=params;let mut page_offset=offset;if let Some((rowid,boundary))=previous {let clause;if let Some(col)=&seek {if boundary.is_null(){clause=if direction=="asc"{format!("({col} IS NOT NULL OR ({col} IS NULL AND rowid>?))")}else{format!("({col} IS NULL AND rowid>?)")};page_params.push(SqlValue::Integer(rowid));}else{let compare=if direction=="asc"{">"}else{"<"};clause=format!("({col}{compare}? OR ({col}=? AND rowid>?){})",if direction=="desc"{format!(" OR {col} IS NULL")}else{String::new()});page_params.extend([sql_value(&boundary)?,sql_value(&boundary)?,SqlValue::Integer(rowid)]);}}else{clause="rowid>?".into();page_params.push(SqlValue::Integer(rowid));}page_where.push_str(if page_where.is_empty(){" WHERE "}else{" AND "});page_where.push_str(&clause);page_offset=0;}
            page_params.extend([SqlValue::Integer(limit as i64),SqlValue::Integer(page_offset as i64)]);let sql=format!("SELECT {selected},_missing,rowid,{} FROM {table}{page_where}{order} LIMIT ? OFFSET ?",seek.as_deref().unwrap_or("NULL"));let mut stmt=db.prepare(&sql)?;let mut records=stmt.query(params_from_iter(page_params.iter()))?;let mut out=Vec::new();let mut boundary=None;while let Some(r)=records.next()?{out.push(decode_row(&keys,r,fields,Some(keys.len()))?);boundary=Some((r.get::<_,i64>(keys.len()+1)?,json_sql(r.get_ref(keys.len()+2)?)?));}
            if can_seek {if let Some(b)=boundary{let k=canonical_json(&json!([semantics,sort,keys,offset+out.len()as u64]))?;let mut c=self.cursors.lock().map_err(|_|Error::new("INTERNAL_ERROR","Cursor lock failed"))?;c.1.retain(|old|old!=&k);c.1.push_back(k.clone());c.0.insert(k,b);while c.1.len()>256{if let Some(k)=c.1.pop_front(){c.0.remove(&k);}}}}
            Ok(json!({"rows":out,"totalRows":total,"durationMs":start.elapsed().as_secs_f64()*1000.0}))
        })
    }
    // Grouping extends the same row-selection contract with its metric axes.
    #[allow(clippy::too_many_arguments)]
    pub fn grouped_rows(
        &self,
        reference: &Value,
        filters: &[Value],
        columns: Option<&[String]>,
        sort: &[Value],
        offset: u64,
        limit: usize,
        search: &str,
        groups: &[String],
        sums: &[String],
        calculated: Option<&Value>,
    ) -> Result<Value> {
        require(
            limit > 0 && limit <= MAX_RESULT_ROWS && offset <= i64::MAX as u64,
            "Invalid grouped table pagination",
            "INVALID_ARGUMENT",
        )?;
        if let Some(cols) = columns {
            require(
                cols.iter().all(|c| groups.contains(c) || sums.contains(c)),
                "Displayed columns must be grouped or summed",
                "INVALID_ARGUMENT",
            )?;
        }
        let start = Instant::now();
        self.with_connection(|db|{let(table,fields,where_sql,params)=self.grouped_query(db,reference,filters,groups,sums,search,calculated)?;let(keys,selected,order)=selection(&fields,columns,sort)?;let mut paged=params.clone();paged.extend([SqlValue::Integer(limit as i64),SqlValue::Integer(offset as i64)]);let mut stmt=db.prepare(&format!("SELECT {selected},COUNT(*) OVER() FROM {table}{where_sql}{order} LIMIT ? OFFSET ?"))?;let mut rows=stmt.query(params_from_iter(paged.iter()))?;let mut out=Vec::new();let mut total=0i64;while let Some(r)=rows.next()?{total=r.get(keys.len())?;out.push(decode_row(&keys,r,&fields,None)?);}if out.is_empty()&&offset>0 {total=db.query_row(&format!("SELECT COUNT(*) FROM {table}{where_sql}"),params_from_iter(params.iter()),|r|r.get(0))?;}Ok(json!({"rows":out,"totalRows":total,"durationMs":start.elapsed().as_secs_f64()*1000.0}))})
    }
    // Builds one SQL selection for both paged views and streaming CSV exports.
    #[allow(clippy::too_many_arguments)]
    fn grouped_query(
        &self,
        db: &Connection,
        reference: &Value,
        filters: &[Value],
        groups: &[String],
        sums: &[String],
        search: &str,
        calculated: Option<&Value>,
    ) -> Result<(String, Value, String, Vec<SqlValue>)> {
        let (table, metadata) = self.version(db, reference)?;
        let fields = &metadata["fields"];
        require(
            !groups.is_empty() && !groups.iter().any(|k| sums.contains(k)),
            "Invalid table grouping",
            "INVALID_ARGUMENT",
        )?;
        for k in groups.iter().chain(sums) {
            column(fields, k)?;
        }
        require(
            sums.iter().all(|k| fields[k]["type"] == "number"),
            "Table sums require numeric fields",
            "INVALID_ARGUMENT",
        )?;
        indexes(db, &table, fields, filters, &[])?;
        let (w, mut params) = where_clause(fields, filters, "")?;
        let mut expr = Vec::new();
        for k in field_keys(fields)? {
            let col = column(fields, &k)?;
            let e = if let Some(spec) = calculated.and_then(|v| v.get(&k)) {
                let n = column(fields, spec["numerator"].as_str().unwrap_or(""))?;
                let d = column(fields, spec["denominator"].as_str().unwrap_or(""))?;
                format!("CASE WHEN SUM({d})>0 THEN SUM({n})*1.0/SUM({d}) ELSE NULL END")
            } else if groups.contains(&k) {
                col.clone()
            } else if sums.contains(&k) {
                format!("SUM({col})")
            } else {
                "NULL".into()
            };
            expr.push(format!("{e} AS {col}"));
        }
        let cols = groups
            .iter()
            .map(|k| column(fields, k))
            .collect::<Result<Vec<_>>>()?;
        let query = format!(
            "(SELECT {},MIN(rowid) AS rowid,NULL AS _missing FROM {table}{w} GROUP BY {})",
            expr.join(","),
            cols.join(",")
        );
        let (search_where, p) = where_clause(fields, &[], search)?;
        params.extend(p);
        Ok((query, fields.clone(), search_where, params))
    }
    pub fn aggregate(
        &self,
        reference: &Value,
        metrics: &Value,
        filters: &[Value],
        groups: &[String],
        grain: Option<&str>,
    ) -> Result<Vec<Value>> {
        if let Some(g) = grain {
            require(
                ["month", "quarter"].contains(&g) && groups.len() == 1,
                "time_grain requires one date group and month or quarter",
                "INVALID_ARGUMENT",
            )?;
        }
        let metrics = metrics
            .as_object()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Metrics must be a mapping"))?;
        require(
            !groups.iter().any(|g| metrics.contains_key(g)),
            "Metric ids must differ from group fields",
            "INVALID_ARGUMENT",
        )?;
        self.with_connection(|db| {
            let (table, metadata) = self.version(db, reference)?;
            let fields = &metadata["fields"];
            let mut expressions = groups.iter().map(|key| column(fields, key)).collect::<Result<Vec<_>>>()?;
            if let Some(grain) = grain {
                require(fields[&groups[0]]["type"] == "date", "time_grain requires a date field", "INVALID_ARGUMENT")?;
                expressions = vec![format!("grain({},'{grain}')", expressions[0])];
            }
            indexes(db, &table, fields, filters, &[])?;
            let (mut where_sql, parameters) = where_clause(fields, filters, "")?;
            let sql = if metrics.values().any(|metric| metric["aggregation"] == "entity_ratio") {
                require(metrics.values().all(|metric| metric["aggregation"] == "entity_ratio"), "Entity ratios must be aggregated separately", "INVALID_ARGUMENT")?;
                let entities = metrics.values().map(|metric| metric["entityField"].as_str().unwrap_or("")).collect::<HashSet<_>>();
                require(entities.len() == 1, "Entity ratios must share one entity field", "INVALID_ARGUMENT")?;
                let entity = column(fields, entities.iter().next().unwrap())?;
                where_sql.push_str(if where_sql.is_empty() { " WHERE " } else { " AND " });
                where_sql.push_str(&format!("{entity} IS NOT NULL"));
                let mut inner = expressions.iter().enumerate().map(|(i, expression)| format!("{expression} AS g{i}")).collect::<Vec<_>>();
                let mut outer = (0..groups.len()).map(|i| format!("g{i}")).collect::<Vec<_>>();
                for (i, metric) in metrics.values().enumerate() {
                    let numerator = numeric_column(fields, metric, "numerator")?;
                    let denominator = numeric_column(fields, metric, "denominator")?;
                    inner.extend([format!("SUM({numerator}) AS n{i}"), format!("SUM({denominator}) AS d{i}")]);
                    outer.push(format!("SUM(CASE WHEN n{i}>0 THEN 1 ELSE 0 END)*1.0/NULLIF(SUM(CASE WHEN d{i}>0 THEN 1 ELSE 0 END),0)"));
                }
                let mut grouping = expressions;
                grouping.push(entity);
                let outer_grouping = if groups.is_empty() {
                    String::new()
                } else {
                    format!(" GROUP BY {}", (0..groups.len()).map(|i| format!("g{i}")).collect::<Vec<_>>().join(","))
                };
                format!("SELECT {} FROM (SELECT {} FROM {table}{where_sql} GROUP BY {}){outer_grouping}", outer.join(","), inner.join(","), grouping.join(","))
            } else {
                let mut measures = Vec::new();
                for metric in metrics.values() {
                    let operation = metric["aggregation"].as_str().unwrap_or("");
                    measures.push(match operation {
                        "count" => "COUNT(*)".into(),
                        "unique" => {
                            let column = column(fields, metric["field"].as_str().unwrap_or(""))?;
                            format!("CASE WHEN COUNT(DISTINCT {column})=1 AND COUNT({column})=COUNT(*) THEN MIN({column}) ELSE NULL END")
                        }
                        "ratio" => {
                            let numerator = numeric_column(fields, metric, "numerator")?;
                            let denominator = numeric_column(fields, metric, "denominator")?;
                            format!("SUM({numerator})*1.0/NULLIF(SUM({denominator}),0)")
                        }
                        "sum" | "avg" | "min" | "max" => format!("{operation}({})", numeric_column(fields, metric, "field")?),
                        _ => return Err(Error::new("INVALID_ARGUMENT", "Unsupported metric aggregation")),
                    });
                }
                require(!expressions.is_empty() || !measures.is_empty(), "At least one metric or group is required", "INVALID_ARGUMENT")?;
                let mut selected = expressions.clone();
                selected.extend(measures);
                let grouping = if expressions.is_empty() {
                    String::new()
                } else {
                    format!(" GROUP BY {} ORDER BY MIN(rowid)", expressions.join(","))
                };
                format!("SELECT {} FROM {table}{where_sql}{grouping}", selected.join(","))
            };
            let mut statement = db.prepare(&sql)?;
            let mut rows = statement.query(params_from_iter(parameters.iter()))?;
            let keys = groups.iter().chain(metrics.keys()).cloned().collect::<Vec<_>>();
            let mut out = Vec::new();
            while let Some(record) = rows.next()? {
                require(out.len() < MAX_RESULT_ROWS, "Result exceeds 100000 rows; use narrower filters or export CSV", "RESULT_TOO_LARGE")?;
                let mut row = Map::new();
                for (i, key) in keys.iter().enumerate() {
                    let mut value = json_sql(record.get_ref(i)?)?;
                    if i < groups.len() && fields[key]["type"] == "boolean" && !value.is_null() {
                        value = json!(value.as_i64().unwrap_or(0) != 0);
                    }
                    row.insert(key.clone(), value);
                }
                out.push(Value::Object(row));
            }
            Ok(out)
        })
    }
    pub fn distinct(
        &self,
        reference: &Value,
        field: &str,
        filters: &[Value],
    ) -> Result<Vec<Value>> {
        self.with_connection(|db| {
            let (table, m) = self.version(db, reference)?;
            let col = column(&m["fields"], field)?;
            let (w, p) = where_clause(&m["fields"], filters, "")?;
            indexes(db, &table, &m["fields"], filters, &[])?;
            let mut stmt = db.prepare(&format!(
                "SELECT {col} FROM {table}{w} GROUP BY {col} ORDER BY MIN(rowid) LIMIT {}",
                MAX_RESULT_ROWS + 1
            ))?;
            let mut rows = stmt.query(params_from_iter(p.iter()))?;
            let mut out = Vec::new();
            while let Some(r) = rows.next()? {
                require(
                    out.len() < MAX_RESULT_ROWS,
                    "Result exceeds 100000 rows; narrow the filters",
                    "RESULT_TOO_LARGE",
                )?;
                let mut v = json_sql(r.get_ref(0)?)?;
                if m["fields"][field]["type"] == "boolean" && !v.is_null() {
                    v = json!(v.as_i64().unwrap_or(0) != 0);
                }
                out.push(v);
            }
            Ok(out)
        })
    }
    pub fn option_page(
        &self,
        refs: &[Value],
        field: &str,
        search: &str,
        offset: u64,
        limit: usize,
    ) -> Result<Value> {
        for r in refs {
            self.validate_reference(r)?;
        }
        let mut versions = refs
            .iter()
            .map(|r| r["version"].clone())
            .collect::<Vec<_>>();
        versions.sort_by_key(Value::to_string);
        versions.dedup();
        self.cache
            .get(
                canonical_json(&json!([
                    "options",
                    versions,
                    field,
                    search.to_lowercase(),
                    offset,
                    limit
                ]))?,
                || self.option_page_extra(refs, field, search, offset, limit, None),
            )
            .map(|p| p.0)
    }
    pub fn option_page_extra(
        &self,
        refs: &[Value],
        field: &str,
        search: &str,
        offset: u64,
        limit: usize,
        extra: Option<(&str, &[Value])>,
    ) -> Result<Value> {
        require(
            search.chars().count() <= 1000
                && offset <= i64::MAX as u64
                && (1..=1000).contains(&limit),
            "Invalid option search or pagination",
            "INVALID_ARGUMENT",
        )?;
        self.with_connection(|db| {
            let mut selects = Vec::new();
            let mut versions = HashSet::new();
            let mut kind = String::new();
            // SQLite permits only a small number of attached databases. Merge
            // each source in a short-lived connection instead of attaching an
            // unbounded number of immutable cloud query files.
            if self.path.is_some()
                && refs.iter().map(|r| r["version"].to_string()).collect::<HashSet<_>>().len() > 8
            {
                db.execute_batch("PRAGMA temp_store=MEMORY; CREATE TEMP TABLE IF NOT EXISTS option_values(value); DELETE FROM option_values")?;
                let mut insert = db.prepare("INSERT INTO option_values VALUES (?)")?;
                for reference in refs {
                    if !versions.insert(reference["version"].clone()) {
                        continue;
                    }
                    self.with_connection(|source| {
                        let (table, metadata) = self.version(source, reference)?;
                        let column = column(&metadata["fields"], field)?;
                        kind = metadata["fields"][field]["type"].as_str().unwrap_or("").to_string();
                        let mut statement = source.prepare(&format!("SELECT {column} FROM {table} GROUP BY {column}"))?;
                        let mut rows = statement.query([])?;
                        while let Some(row) = rows.next()? {
                            insert.execute([sql_value(&json_sql(row.get_ref(0)?)?)?])?;
                        }
                        Ok(())
                    })?;
                }
                selects.push("SELECT value FROM option_values".into());
            } else {
                for reference in refs {
                    let (table, metadata) = self.version(db, reference)?;
                    if !versions.insert(metadata["version"].clone()) {
                        continue;
                    }
                    let column = column(&metadata["fields"], field)?;
                    kind = metadata["fields"][field]["type"].as_str().unwrap_or("").into();
                    selects.push(format!("SELECT {column} AS value FROM {table}"));
                }
            }
            if let Some((field_type, values)) = extra {
                kind = field_type.into();
                db.execute_batch("DROP TABLE IF EXISTS temp.live_options; CREATE TEMP TABLE live_options(value)")?;
                let mut statement = db.prepare("INSERT INTO live_options VALUES (?)")?;
                for value in values {
                    statement.execute([sql_value(value)?])?;
                }
                selects.push("SELECT value FROM live_options".into());
            }
            if selects.is_empty() {
                return Ok(json!({"values":[],"totalValues":0,"offset":offset,"hasMore":false}));
            }
            let source = format!("({})", selects.join(" UNION ALL "));
            let mut repeated = false;
            if !search.is_empty() {
                let mut statement = db.prepare(&format!("SELECT value FROM {source} LIMIT {OPTION_PROBE_ROWS}"))?;
                let mut rows = statement.query([])?;
                let (mut seen, mut count, mut bytes) = (HashSet::new(), 0usize, 0usize);
                while let Some(row) = rows.next()? {
                    let value = json_sql(row.get_ref(0)?)?;
                    let id = canonical_json(&value)?;
                    if !seen.contains(&id) {
                        let size = value.as_str().map(|s| s.chars().count() * 4 + 64).unwrap_or(32);
                        if bytes + size > OPTION_PROBE_BYTES {
                            break;
                        }
                        seen.insert(id);
                        bytes += size;
                    }
                    count += 1;
                }
                repeated = count > 0 && seen.len() * 2 <= count;
            }
            let where_clause = if search.is_empty() { "" } else { " WHERE search_text(value,?,?)" };
            let query = if repeated {
                format!("SELECT value FROM (SELECT value FROM {source} GROUP BY value LIMIT -1){where_clause}")
            } else {
                format!("SELECT value FROM {source}{where_clause} GROUP BY value")
            };
            let parameters = if search.is_empty() { Vec::new() } else {
                vec![SqlValue::Text(search.into()), SqlValue::Text(kind.clone())]
            };
            let mut paged = parameters.clone();
            paged.extend([SqlValue::Integer(limit as i64), SqlValue::Integer(offset as i64)]);
            let mut statement = db.prepare(&format!("SELECT value,COUNT(*) OVER() FROM ({query}) ORDER BY value LIMIT ? OFFSET ?"))?;
            let mut rows = statement.query(params_from_iter(paged.iter()))?;
            let mut values = Vec::new();
            let mut total = 0u64;
            while let Some(row) = rows.next()? {
                total = row.get::<_, i64>(1)? as u64;
                let mut value = json_sql(row.get_ref(0)?)?;
                if kind == "boolean" && !value.is_null() {
                    value = json!(value.as_i64().unwrap_or(0) != 0);
                }
                values.push(value);
            }
            if values.is_empty() && offset > 0 {
                total = db.query_row(&format!("SELECT COUNT(*) FROM ({query})"), params_from_iter(parameters.iter()), |row| row.get::<_, i64>(0))? as u64;
            }
            Ok(json!({"hasMore":offset + (values.len() as u64) < total,"values":values,"totalValues":total,"offset":offset}))
        })
    }
    pub fn for_each_row<F: FnMut(Value) -> Result<()>>(
        &self,
        reference: &Value,
        filters: &[Value],
        columns: Option<&[String]>,
        sort: &[Value],
        search: &str,
        mut visit: F,
    ) -> Result<()> {
        self.with_connection(|db| {
            let (table, m) = self.version(db, reference)?;
            let fields = &m["fields"];
            indexes(db, &table, fields, filters, sort)?;
            let (w, p) = where_clause(fields, filters, search)?;
            let (keys, selected, order) = selection(fields, columns, sort)?;
            let mut s = db.prepare(&format!(
                "SELECT {selected},_missing FROM {table}{w}{order}"
            ))?;
            let mut rows = s.query(params_from_iter(p.iter()))?;
            while let Some(r) = rows.next()? {
                visit(decode_row(&keys, r, fields, Some(keys.len()))?)?;
            }
            Ok(())
        })
    }
    pub fn all_rows(&self, reference: &Value) -> Result<Vec<Value>> {
        let mut out = Vec::new();
        self.for_each_row(reference, &[], None, &[], "", |r| {
            out.push(r);
            Ok(())
        })?;
        Ok(out)
    }
    // Exports use the complete row-selection and grouping contract of views.
    #[allow(clippy::too_many_arguments)]
    pub fn export_csv(
        &self,
        reference: &Value,
        output: Option<&Path>,
        filters: &[Value],
        columns: Option<&[String]>,
        sort: &[Value],
        search: &str,
        groups: Option<&[String]>,
        sums: Option<&[String]>,
        calculated: Option<&Value>,
    ) -> Result<Value> {
        let start = Instant::now();
        if let (Some(dest), Some(db)) = (output, &self.path) {
            let absolute = if dest.is_absolute() {
                dest.to_path_buf()
            } else {
                std::env::current_dir()?.join(dest)
            };
            require(
                absolute != *db && dest.canonicalize().ok() != db.canonicalize().ok(),
                "CSV output cannot overwrite the data database",
                "INVALID_PATH",
            )?;
        }
        let mut buffer = Vec::new();
        let writer: Box<dyn Write + '_> = if let Some(path) = output {
            Box::new(fs::File::create(path)?)
        } else {
            Box::new(&mut buffer)
        };
        let mut writer = writer;
        writer.write_all(&[0xef, 0xbb, 0xbf])?;
        let mut csv = csv::WriterBuilder::new()
            .terminator(csv::Terminator::CRLF)
            .from_writer(writer);
        let mut count = 0u64;
        self.with_connection(|db| {
            let (mut table, m) = self.version(db, reference)?;
            let fields = &m["fields"];
            let (mut w, mut p) = where_clause(fields, filters, search)?;
            let (keys, selected, order) = selection(fields, columns, sort)?;
            indexes(db, &table, fields, filters, sort)?;
            if let Some(groups) = groups.filter(|g| !g.is_empty()) {
                let (g, _, gw, gp) = self.grouped_query(
                    db,
                    reference,
                    filters,
                    groups,
                    sums.unwrap_or(&[]),
                    search,
                    calculated,
                )?;
                require(
                    keys.iter()
                        .all(|k| groups.contains(k) || sums.unwrap_or(&[]).contains(k)),
                    "Export columns must be grouped or summed",
                    "INVALID_ARGUMENT",
                )?;
                table = g;
                w = gw;
                p = gp;
            }
            csv.write_record(keys.iter().map(|k| safe_csv(&Value::String(k.clone()))))
                .map_err(csv_error)?;
            let mut s = db.prepare(&format!("SELECT {selected} FROM {table}{w}{order}"))?;
            let mut rows = s.query(params_from_iter(p.iter()))?;
            while let Some(r) = rows.next()? {
                let row = decode_row(&keys, r, fields, None)?;
                csv.write_record(keys.iter().map(|k| safe_csv(&row[k])))
                    .map_err(csv_error)?;
                count += 1;
            }
            Ok(())
        })?;
        csv.flush()?;
        drop(csv);
        let mut result =
            json!({"rowCount":count,"durationMs":start.elapsed().as_secs_f64()*1000.0});
        if let Some(p) = output {
            result["path"] = json!(p.canonicalize()?.to_string_lossy());
            result["bytes"] = json!(fs::metadata(p)?.len());
        } else {
            use base64::Engine;
            result["bytes"] = json!(buffer.len());
            result["content"] = json!(base64::engine::general_purpose::STANDARD.encode(buffer));
        }
        Ok(result)
    }
}
fn setup(db: &Connection) -> Result<()> {
    db.busy_timeout(Duration::from_secs(30))?;
    let flags = FunctionFlags::SQLITE_DETERMINISTIC | FunctionFlags::SQLITE_UTF8;
    for (name, null_word) in [("contains_text", false), ("search_text", true)] {
        db.create_scalar_function(name, 3, flags, move |ctx| {
            let value = json_sql(ctx.get_raw(0))?;
            let needle = ctx.get::<String>(1)?;
            let kind = ctx.get::<String>(2)?;
            Ok(text_value(&value, &kind, null_word)
                .to_lowercase()
                .contains(&needle.to_lowercase()))
        })?;
    }
    db.create_scalar_function("sort_number", 1, flags, |ctx| {
        Ok(sort_number(&json_sql(ctx.get_raw(0))?))
    })?;
    db.create_scalar_function("grain", 2, flags, |ctx| {
        let v = json_sql(ctx.get_raw(0))?;
        let g = ctx.get::<String>(1)?;
        let out =
            time_grain(&v, &g).map_err(|e| rusqlite::Error::UserFunctionError(Box::new(e)))?;
        Ok(out.as_str().map(str::to_owned))
    })?;
    Ok(())
}
fn check_version(v: &str) -> Result<()> {
    require(
        v.len() == 64
            && v.bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)),
        "Invalid data version",
        "INVALID_ARGUMENT",
    )
}
fn metadata(raw: &str) -> Result<Value> {
    let mut m: Value = serde_json::from_str(raw)?;
    let fields = m["fields"]
        .as_object()
        .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Invalid data metadata"))?;
    let order = m["fieldOrder"]
        .as_array()
        .map(|v| {
            v.iter()
                .filter_map(Value::as_str)
                .map(str::to_owned)
                .collect::<Vec<_>>()
        })
        .unwrap_or_else(|| fields.keys().cloned().collect());
    let ordered = order
        .iter()
        .map(|k| (k.clone(), fields[k].clone()))
        .collect::<Map<_, _>>();
    m["fields"] = Value::Object(ordered);
    Ok(m)
}
fn field_keys(fields: &Value) -> Result<Vec<String>> {
    Ok(fields
        .as_object()
        .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Fields must be a mapping"))?
        .keys()
        .cloned()
        .collect())
}
fn column(fields: &Value, key: &str) -> Result<String> {
    let keys = field_keys(fields)?;
    keys.iter()
        .position(|k| k == key)
        .map(|i| format!("c{i}"))
        .ok_or_else(|| Error::new("INVALID_ARGUMENT", format!("Unknown field: {key}")))
}
fn numeric_column(fields: &Value, metric: &Value, key: &str) -> Result<String> {
    let field = metric[key].as_str().unwrap_or("");
    require(
        fields[field]["type"] == "number",
        "Aggregation requires numeric field",
        "INVALID_ARGUMENT",
    )?;
    column(fields, field)
}
fn raw_field(s: &str) -> String {
    let mut chars = s.chars();
    match chars.next() {
        Some(c) => format!("raw{}{}", c.to_uppercase(), chars.as_str()),
        None => "raw".into(),
    }
}
fn indexes(
    db: &Connection,
    table: &str,
    fields: &Value,
    filters: &[Value],
    sort: &[Value],
) -> Result<()> {
    if table.contains('.') {
        return Ok(());
    }
    let mut keys = HashSet::new();
    for item in filters.iter().chain(sort) {
        if let Some(k) = item["field"].as_str() {
            keys.insert(k.to_string());
            let raw = raw_field(k);
            if fields[k]["type"] == "string" && fields[&raw]["type"] == "number" {
                keys.insert(raw);
            }
        }
    }
    for k in keys {
        let c = column(fields, &k)?;
        db.execute_batch(&format!(
            "CREATE INDEX IF NOT EXISTS i_{table}_{c} ON {table}({c})"
        ))?;
    }
    Ok(())
}
fn where_clause(
    fields: &Value,
    filters: &[Value],
    search: &str,
) -> Result<(String, Vec<SqlValue>)> {
    let mut clauses = Vec::new();
    let mut params = Vec::new();
    for f in filters {
        let key = f["field"].as_str().unwrap_or("");
        let col = column(fields, key)?;
        let values = f["values"].as_array().cloned().unwrap_or_default();
        if values.is_empty() {
            continue;
        }
        match f["op"].as_str().unwrap_or("") {
            "in" => {
                let present = values.iter().filter(|v| !v.is_null()).collect::<Vec<_>>();
                let mut alternatives = Vec::new();
                if !present.is_empty() {
                    alternatives.push(format!("{col} IN ({})", vec!["?"; present.len()].join(",")));
                    for v in present {
                        params.push(sql_value(v)?);
                    }
                }
                if values.iter().any(Value::is_null) {
                    alternatives.push(format!("{col} IS NULL AND NOT EXISTS(SELECT 1 FROM json_each(_missing) WHERE value=?)"));
                    params.push(SqlValue::Text(key.into()));
                }
                clauses.push(alternatives.join(" OR "));
            }
            "contains" => {
                clauses.push(format!("contains_text({col},?,?)"));
                params.extend([
                    SqlValue::Text(text_value(&values[0], "", false)),
                    SqlValue::Text(fields[key]["type"].as_str().unwrap_or("").into()),
                ]);
            }
            "range" if values.len() == 2 => {
                clauses.push(format!("{col} IS NOT NULL AND {col} BETWEEN ? AND ?"));
                params.extend(values.iter().map(sql_value).collect::<Result<Vec<_>>>()?);
            }
            _ => {
                return Err(Error::new(
                    "INVALID_ARGUMENT",
                    "Unsupported filter operation or invalid range",
                ))
            }
        }
    }
    if !search.is_empty() {
        let mut alternatives = Vec::new();
        for k in field_keys(fields)? {
            if k.starts_with("raw") || k.starts_with('_') {
                continue;
            }
            alternatives.push(format!("(search_text({},?,?) AND NOT EXISTS(SELECT 1 FROM json_each(_missing) WHERE value=?))",column(fields,&k)?));
            params.extend([
                SqlValue::Text(search.into()),
                SqlValue::Text(fields[&k]["type"].as_str().unwrap_or("").into()),
                SqlValue::Text(k),
            ]);
        }
        clauses.push(if alternatives.is_empty() {
            "0".into()
        } else {
            alternatives.join(" OR ")
        });
    }
    Ok((
        if clauses.is_empty() {
            String::new()
        } else {
            format!(
                " WHERE {}",
                clauses
                    .iter()
                    .map(|c| format!("({c})"))
                    .collect::<Vec<_>>()
                    .join(" AND ")
            )
        },
        params,
    ))
}
fn selection(
    fields: &Value,
    columns: Option<&[String]>,
    sort: &[Value],
) -> Result<(Vec<String>, String, String)> {
    let keys = columns
        .map(<[String]>::to_vec)
        .unwrap_or(field_keys(fields)?);
    require(
        !keys.is_empty(),
        "Select at least one column",
        "INVALID_ARGUMENT",
    )?;
    let selected = keys
        .iter()
        .map(|k| column(fields, k))
        .collect::<Result<Vec<_>>>()?
        .join(",");
    let mut order = Vec::new();
    for s in sort {
        let key = s["field"].as_str().unwrap_or("");
        let col = column(fields, key)?;
        let dir = s["direction"].as_str().unwrap_or("asc").to_lowercase();
        require(
            ["asc", "desc"].contains(&dir.as_str()),
            "Invalid sort direction",
            "INVALID_ARGUMENT",
        )?;
        if fields[key]["type"] == "string" {
            let raw = raw_field(key);
            if fields[&raw]["type"] == "number" {
                order.push(format!("{} {dir}", column(fields, &raw)?));
            } else {
                order.extend([
                    format!("(sort_number({col}) IS NULL) ASC"),
                    format!("sort_number({col}) {dir}"),
                    format!("CASE WHEN sort_number({col}) IS NULL THEN {col} END {dir}"),
                ]);
            }
        } else {
            order.push(format!("{col} {dir}"));
        }
    }
    order.push("rowid".into());
    Ok((keys, selected, format!(" ORDER BY {}", order.join(","))))
}
fn decode_row(
    keys: &[String],
    row: &rusqlite::Row<'_>,
    fields: &Value,
    missing: Option<usize>,
) -> Result<Value> {
    let omitted: Vec<String> = if let Some(i) = missing {
        row.get::<_, Option<String>>(i)?
            .map(|s| serde_json::from_str(&s))
            .transpose()?
            .unwrap_or_default()
    } else {
        Vec::new()
    };
    let mut out = Map::new();
    for (i, k) in keys.iter().enumerate() {
        if omitted.contains(k) {
            continue;
        }
        let mut v = json_sql(row.get_ref(i)?)?;
        if fields[k]["type"] == "boolean" && !v.is_null() {
            v = json!(v.as_i64().unwrap_or(0) != 0);
        }
        out.insert(k.clone(), v);
    }
    Ok(Value::Object(out))
}
fn safe_csv(v: &Value) -> String {
    let s = text_value(v, "", false);
    if v.is_string() && s.starts_with(['=', '+', '-', '@', '\t', '\r']) {
        format!("'{s}")
    } else {
        s
    }
}
fn csv_error(e: csv::Error) -> Error {
    Error::new("IO_ERROR", e.to_string())
}
