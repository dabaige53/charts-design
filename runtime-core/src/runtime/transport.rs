//! Bounded MCP responses and metadata-only diagnostics with no persisted live rows.
use super::error::{require, Error, Result};
use base64::{engine::general_purpose::STANDARD, Engine};
use rusqlite::{params, params_from_iter, Connection, OptionalExtension};
use serde_json::{json, Map, Value};
use std::{
    collections::VecDeque,
    path::{Path, PathBuf},
    sync::Mutex,
    time::{Instant, SystemTime, UNIX_EPOCH},
};
use uuid::Uuid;
pub const INLINE_LIMIT: usize = 48_000;
pub const CHUNK_SIZE: usize = 24_000;
pub const TRANSIENT_LIMIT: usize = 48 * 1024 * 1024;
fn now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}
struct Transient {
    id: String,
    expires: f64,
    encoded: String,
}
struct State {
    results: Connection,
    events: Connection,
    inserts: usize,
    transient: VecDeque<Transient>,
    bytes: usize,
}
pub struct Transport {
    pub path: PathBuf,
    pub cache_path: PathBuf,
    state: Mutex<State>,
}
impl Transport {
    pub fn new(root: &Path) -> Result<Self> {
        super::exports::private_directory(root)?;
        let cache_path = root.join("transport-results.sqlite3");
        let path = root.join("transport-diagnostics.sqlite3");
        let results = Connection::open(&cache_path)?;
        let events = Connection::open(&path)?;
        for db in [&results, &events] {
            db.busy_timeout(std::time::Duration::from_secs(10))?;
            db.execute_batch("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;")?;
        }
        super::exports::private_file(&cache_path)?;
        super::exports::private_file(&path)?;
        results.execute_batch("CREATE TABLE IF NOT EXISTS results(request_id TEXT PRIMARY KEY,expires REAL,encoded TEXT)")?;
        events.execute_batch("CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at REAL,request_id TEXT,tool TEXT,stage TEXT,code TEXT,bytes INTEGER)")?;
        let columns: Vec<String> = events
            .prepare("PRAGMA table_info(events)")?
            .query_map([], |r| r.get(1))?
            .collect::<std::result::Result<_, _>>()?;
        for (name, kind) in [
            ("dashboard_id", "TEXT"),
            ("duration_ms", "REAL"),
            ("revision", "INTEGER"),
            ("backend_build_id", "TEXT"),
            ("cache_hits", "INTEGER"),
        ] {
            if !columns.iter().any(|c| c == name) {
                events.execute_batch(&format!("ALTER TABLE events ADD COLUMN {name} {kind}"))?;
            }
        }
        Ok(Self {
            path,
            cache_path,
            state: Mutex::new(State {
                results,
                events,
                inserts: 0,
                transient: VecDeque::new(),
                bytes: 0,
            }),
        })
    }
    fn lock(&self) -> Result<std::sync::MutexGuard<'_, State>> {
        self.state
            .lock()
            .map_err(|_| Error::new("INTERNAL_ERROR", "Transport lock failed"))
    }
    pub fn log(
        &self,
        request_id: &str,
        tool: &str,
        stage: &str,
        code: &str,
        bytes: usize,
        details: &Value,
    ) -> Result<()> {
        self.log_many(&[json!({"requestId":request_id,"tool":tool,"stage":stage,"code":code,"bytes":bytes,"dashboardId":details["dashboardId"],"durationMs":details["durationMs"],"revision":details["revision"],"cacheHits":details["cacheHits"]})])
    }
    pub fn log_many(&self, records: &[Value]) -> Result<()> {
        if records.is_empty() {
            return Ok(());
        }
        let mut state = self.lock()?;
        let prune = state.inserts + records.len() >= 50;
        {
            let tx = state.events.transaction()?;
            let at = now();
            for r in records {
                tx.execute("INSERT INTO events(at,request_id,tool,stage,code,bytes,dashboard_id,duration_ms,revision,backend_build_id,cache_hits) VALUES(?,?,?,?,?,?,?,?,?,?,?)",params![at,r["requestId"].as_str().unwrap_or(""),r["tool"].as_str().unwrap_or(""),r["stage"].as_str().unwrap_or(""),r["code"].as_str().unwrap_or(""),r["bytes"].as_u64().unwrap_or(0)as i64,r["dashboardId"].as_str(),r["durationMs"].as_f64(),r["revision"].as_i64(),super::assets::backend_build_id(),r["cacheHits"].as_i64()])?;
            }
            if prune {
                tx.execute(
                    "DELETE FROM events WHERE id <= (SELECT coalesce(max(id),0)-2000 FROM events)",
                    [],
                )?;
            }
            tx.commit()?;
        }
        state.inserts = if prune {
            0
        } else {
            state.inserts + records.len()
        };
        Ok(())
    }
    fn prune(state: &mut State, budget: usize) {
        let at = now();
        while state
            .transient
            .front()
            .is_some_and(|v| v.expires < at || state.bytes > budget)
        {
            if let Some(old) = state.transient.pop_front() {
                state.bytes -= old.encoded.len();
            }
        }
    }
    pub fn encode(&self, result: &Value, tool: &str) -> Result<(Value, Option<String>)> {
        let id = result["requestId"]
            .as_str()
            .map(String::from)
            .unwrap_or_else(|| Uuid::new_v4().simple().to_string());
        let start = Instant::now();
        let text = serde_json::to_string(result)?;
        let details = json!({"dashboardId":result.get("dashboardId").or_else(||result.get("id")).unwrap_or(&result["document"]["id"]),"durationMs":start.elapsed().as_secs_f64()*1000.0});
        self.log(&id, tool, "serialized", "", text.len(), &details)?;
        if text.len() <= INLINE_LIMIT {
            return Ok((result.clone(), Some(text)));
        }
        let bytes = text.len();
        let encoded = STANDARD.encode(text);
        let chunks = encoded.len().div_ceil(CHUNK_SIZE);
        {
            let mut state = self.lock()?;
            let at = now();
            if result["transient"] == true {
                require(
                    encoded.len() <= TRANSIENT_LIMIT,
                    "Live response exceeds the transport limit; request fewer components or rows.",
                    "RESULT_TOO_LARGE",
                )?;
                if let Some(index) = state.transient.iter().position(|v| v.id == id) {
                    let old = state.transient.remove(index).unwrap();
                    state.bytes -= old.encoded.len();
                }
                Self::prune(&mut state, TRANSIENT_LIMIT - encoded.len());
                state.bytes += encoded.len();
                state.transient.push_back(Transient {
                    id: id.clone(),
                    expires: at + 300.0,
                    encoded,
                });
            } else {
                state
                    .results
                    .execute("DELETE FROM results WHERE expires < ?", [at])?;
                state.results.execute(
                    "INSERT OR REPLACE INTO results VALUES(?,?,?)",
                    params![id, at + 86400.0, encoded],
                )?;
            }
        }
        self.log(&id, tool, "chunked", "", bytes, &details)?;
        Ok((
            json!({"transport":{"encoding":"base64-json-v1","requestId":id,"chunks":chunks,"bytes":bytes}}),
            None,
        ))
    }
    pub fn result_text(&self, id: &str) -> Result<String> {
        let mut state = self.lock()?;
        Self::prune(&mut state, TRANSIENT_LIMIT);
        let encoded = if let Some(v) = state.transient.iter().find(|v| v.id == id) {
            Some(v.encoded.clone())
        } else {
            state
                .results
                .query_row(
                    "SELECT encoded FROM results WHERE request_id=? AND expires>=?",
                    params![id, now()],
                    |r| r.get::<_, String>(0),
                )
                .optional()?
        }
        .ok_or_else(|| {
            Error::new(
                "RESULT_EXPIRED",
                "Response unavailable; inspect current state before retrying.",
            )
        })?;
        String::from_utf8(
            STANDARD
                .decode(encoded)
                .map_err(|e| Error::new("INVALID_RESULT", e.to_string()))?,
        )
        .map_err(|e| Error::new("INVALID_RESULT", e.to_string()))
    }
    pub fn chunk(&self, args: &Value) -> Result<Value> {
        let id = args["requestId"]
            .as_str()
            .ok_or_else(|| Error::new("INVALID_CHUNK", "Invalid response request ID"))?;
        let index = args["index"]
            .as_u64()
            .ok_or_else(|| Error::new("INVALID_CHUNK", "Invalid response chunk index"))?;
        let offset = index
            .checked_mul(CHUNK_SIZE as u64)
            .filter(|v| *v < i64::MAX as u64)
            .ok_or_else(|| Error::new("INVALID_CHUNK", "Invalid response chunk index"))?;
        let (value, total) = {
            let mut state = self.lock()?;
            Self::prune(&mut state, TRANSIENT_LIMIT);
            if let Some(v) = state.transient.iter().find(|v| v.id == id) {
                let start = offset as usize;
                require(
                    start < v.encoded.len(),
                    "Invalid response chunk index",
                    "INVALID_CHUNK",
                )?;
                (
                    v.encoded[start..(start + CHUNK_SIZE).min(v.encoded.len())].to_owned(),
                    v.encoded.len(),
                )
            } else {
                let row:Option<(i64,String)>=state.results.query_row("SELECT length(encoded),substr(encoded,?,?) FROM results WHERE request_id=? AND expires>=?",params![offset as i64+1,CHUNK_SIZE as i64,id,now()],|r|Ok((r.get(0)?,r.get(1)?))).optional()?;
                let (total, text) = row.ok_or_else(|| {
                    Error::new(
                        "RESULT_EXPIRED",
                        "Preview response expired; reload the dashboard.",
                    )
                })?;
                require(
                    offset < (total as u64),
                    "Invalid response chunk index",
                    "INVALID_CHUNK",
                )?;
                (text, total as usize)
            }
        };
        if index == 0 || offset as usize + CHUNK_SIZE >= total {
            self.log(
                id,
                "runtime_result_chunk",
                if index == 0 {
                    "read_start"
                } else {
                    "read_complete"
                },
                "",
                value.len(),
                &json!({}),
            )?;
        }
        Ok(json!({"requestId":id,"index":index,"data":value}))
    }
    pub fn diagnostics(&self, args: &Value) -> Result<Value> {
        let limit = args["limit"].as_i64().unwrap_or(30).clamp(1, 100);
        let mut clauses = Vec::new();
        let mut params: Vec<rusqlite::types::Value> = Vec::new();
        for (field, column) in [
            ("requestId", "request_id"),
            ("dashboardId", "dashboard_id"),
            ("stage", "stage"),
            ("code", "code"),
        ] {
            if let Some(value) = args[field].as_str().filter(|s| !s.is_empty()) {
                clauses.push(format!("{column}=?"));
                params.push(value.to_owned().into());
            }
        }
        params.push(limit.into());
        let state = self.lock()?;
        let sql = format!(
            "SELECT * FROM events WHERE {} ORDER BY id DESC LIMIT ?",
            if clauses.is_empty() {
                "1=1".into()
            } else {
                clauses.join(" AND ")
            }
        );
        let mut statement = state.events.prepare(&sql)?;
        let names: Vec<String> = statement.column_names().map(|s| s.to_string()).collect();
        let rows = statement
            .query_map(params_from_iter(params.iter()), |r| {
                let mut output = Map::new();
                for (i, name) in names.iter().enumerate() {
                    use rusqlite::types::ValueRef;
                    let value = match r.get_ref(i)? {
                        ValueRef::Null => Value::Null,
                        ValueRef::Integer(v) => json!(v),
                        ValueRef::Real(v) => json!(v),
                        ValueRef::Text(v) => json!(String::from_utf8_lossy(v)),
                        ValueRef::Blob(_) => Value::Null,
                    };
                    output.insert(name.clone(), value);
                }
                Ok(Value::Object(output))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        Ok(json!({"events":rows}))
    }
}
