//! One native MCP client for dashboard reads and resumable project uploads.
use super::{encode_bulk, reference, BULK_ENCODING, BULK_ROWS, TRANSFER_ROWS};
use crate::runtime::{
    cloud_data::ordered_fields,
    data::{json_sql, LocalData},
    error::{require, Error, Result},
    exports::private_file,
    model,
    object_storage::atomic_write,
    serialization::{json_bytes, python_json},
    service::string,
};
use base64::{engine::general_purpose::STANDARD, Engine};
use fs2::FileExt;
use reqwest::blocking::{Client, Response};
use rusqlite::{Connection, OpenFlags, OptionalExtension};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, HashSet},
    env, fs,
    io::{BufRead, BufReader, Read},
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex,
    },
    time::{Duration, Instant},
};

const MAX_RESPONSE: usize = 64 * 1024 * 1024;
const TRANSFER_TOOLS: &[(&str, &[&str])] = &[
    (
        "dataset_transfer_chunk",
        &["uploadId", "ref", "part", "rows"],
    ),
    ("dataset_transfer_finish", &["uploadId", "ref"]),
    ("dataset_transfer_status", &["uploadId", "ref", "parts"]),
];
trait ToolCaller: Send + Sync {
    fn call(&self, tool: &str, args: &Value) -> Result<Value>;
}
struct Remote {
    client: Client,
    endpoint: String,
    token: String,
    project: String,
    session: Mutex<Option<String>>,
    protocol: Mutex<String>,
    next_id: AtomicU64,
}
fn network_error() -> Error {
    Error::new(
        "MCP_UNAVAILABLE",
        "Could not confirm the MCP response; retain the state file and retry the same command",
    )
    .with_status(503)
}
fn protocol_error(message: &str) -> Error {
    Error::new("TRANSFER_PROTOCOL_ERROR", message)
}
fn diagnostic_code(value: Option<&str>) -> &str {
    value
        .filter(|code| {
            !code.is_empty()
                && code.len() <= 64
                && code
                    .bytes()
                    .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b'_')
        })
        .unwrap_or("MCP_ERROR")
}
impl Remote {
    fn connect(project: &str) -> Result<Arc<Self>> {
        model::check_identifier(project)?;
        let endpoint = env::var("CHARTS_MCP_URL").unwrap_or_default();
        let parsed = url::Url::parse(&endpoint).map_err(|_| {
            Error::new(
                "INVALID_CONFIG",
                "CHARTS_MCP_URL must be an HTTPS endpoint without embedded credentials",
            )
        })?;
        require(
            parsed.scheme() == "https"
                && parsed.host_str().is_some()
                && parsed.username().is_empty()
                && parsed.password().is_none()
                && parsed.fragment().is_none(),
            "CHARTS_MCP_URL must be an HTTPS endpoint without embedded credentials",
            "INVALID_CONFIG",
        )?;
        let token = env::var("CHARTS_SERVER_TOKENS")
            .unwrap_or_default()
            .split(',')
            .next()
            .unwrap_or("")
            .trim()
            .to_owned();
        require(
            !token.is_empty() && !token.contains(['\r', '\n']),
            "CHARTS_SERVER_TOKENS must contain a server token",
            "INVALID_CONFIG",
        )?;
        let client = Client::builder()
            .timeout(Duration::from_secs(120))
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .map_err(|_| network_error())?;
        let remote = Arc::new(Self {
            client,
            endpoint,
            token,
            project: project.into(),
            session: Mutex::new(None),
            protocol: Mutex::new("2025-11-25".into()),
            next_id: AtomicU64::new(1),
        });
        remote.initialize()
    }
    fn initialize(self: Arc<Self>) -> Result<Arc<Self>> {
        let initialized = self.rpc("initialize", &json!({"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"charts-design-transfer","version":env!("CARGO_PKG_VERSION")}}))?;
        let protocol = initialized["protocolVersion"]
            .as_str()
            .filter(|version| {
                ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"].contains(version)
            })
            .ok_or_else(|| {
                protocol_error("The MCP server selected an unsupported protocol version")
            })?;
        *self.protocol.lock().map_err(|_| network_error())? = protocol.to_owned();
        self.post(
            &json!({"jsonrpc":"2.0","method":"notifications/initialized"}),
            None,
        )?;
        Ok(self)
    }
    fn post(&self, body: &Value, expected_id: Option<u64>) -> Result<Value> {
        let session = self.session.lock().map_err(|_| network_error())?.clone();
        let protocol = self.protocol.lock().map_err(|_| network_error())?.clone();
        let mut request = self
            .client
            .post(&self.endpoint)
            .bearer_auth(&self.token)
            .header("Accept", "application/json, text/event-stream")
            .header("MCP-Protocol-Version", protocol)
            .json(body);
        if let Some(session) = session {
            request = request.header("Mcp-Session-Id", session);
        }
        let response = request.send().map_err(|_| network_error())?;
        let status = response.status();
        if !status.is_success() {
            return Err(Error::new(
                if matches!(status.as_u16(), 401 | 403) {
                    "MCP_UNAUTHORIZED"
                } else {
                    "MCP_HTTP_ERROR"
                },
                format!(
                    "MCP request returned HTTP {}; retain the state file before retrying",
                    status.as_u16()
                ),
            )
            .with_status(status.as_u16()));
        }
        if let Some(session) = response.headers().get("Mcp-Session-Id") {
            *self.session.lock().map_err(|_| network_error())? = Some(
                session
                    .to_str()
                    .map_err(|_| protocol_error("Invalid MCP session identifier"))?
                    .to_string(),
            );
        }
        let Some(id) = expected_id else {
            return Ok(Value::Null);
        };
        let value = response_value(response, id)?;
        require(
            value["jsonrpc"] == "2.0" && value["id"] == id,
            "MCP response does not match the request",
            "TRANSFER_PROTOCOL_ERROR",
        )?;
        if value.get("error").is_some() {
            return Err(Error::new(
                "MCP_RPC_ERROR",
                "MCP server rejected the request",
            ));
        }
        value
            .get("result")
            .cloned()
            .ok_or_else(|| protocol_error("MCP response is missing a result"))
    }
    fn rpc(&self, method: &str, params: &Value) -> Result<Value> {
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        self.post(
            &json!({"jsonrpc":"2.0","id":id,"method":method,"params":params}),
            Some(id),
        )
    }
    fn require_tools(&self, required: &[(&str, &[&str])]) -> Result<Map<String, Value>> {
        let mut available = Map::new();
        let mut cursor = None;
        let mut seen = HashSet::new();
        loop {
            let page = self.rpc(
                "tools/list",
                &cursor
                    .as_ref()
                    .map(|cursor| json!({"cursor":cursor}))
                    .unwrap_or_else(|| json!({})),
            )?;
            let tools = page["tools"]
                .as_array()
                .ok_or_else(|| protocol_error("MCP tools/list returned no tools array"))?;
            for tool in tools {
                let name = tool["name"]
                    .as_str()
                    .ok_or_else(|| protocol_error("MCP tool name is missing"))?;
                available.insert(name.into(), tool["inputSchema"].clone());
            }
            cursor = page["nextCursor"]
                .as_str()
                .filter(|value| !value.is_empty())
                .map(str::to_owned);
            let Some(value) = &cursor else {
                break;
            };
            require(
                seen.len() < 1024 && seen.insert(value.clone()),
                "MCP tool pagination did not advance",
                "TRANSFER_PROTOCOL_ERROR",
            )?;
        }
        if required
            .iter()
            .any(|(name, _)| !available.contains_key(*name))
        {
            let resource = self.rpc("resources/read", &json!({"uri":"charts://contract"}))?;
            let text = resource["contents"]
                .as_array()
                .and_then(|contents| contents.iter().find_map(|item| item["text"].as_str()))
                .ok_or_else(|| protocol_error("MCP contract resource is missing text"))?;
            let contract: Value = serde_json::from_str(text)
                .map_err(|_| protocol_error("MCP contract resource contains invalid JSON"))?;
            if let Some(clients) = contract["clientTools"].as_object() {
                available.extend(clients.clone());
            }
        }
        for (name, fields) in required {
            require(
                available
                    .get(*name)
                    .and_then(|schema| schema["properties"].as_object())
                    .is_some_and(|properties| {
                        fields.iter().all(|field| properties.contains_key(*field))
                    }),
                format!("{name}: update the target service before uploading"),
                "CAPABILITY_MISSING",
            )?;
        }
        Ok(available)
    }
    fn request_tool(&self, tool: &str, args: &Value) -> Result<Value> {
        let mut arguments = args
            .as_object()
            .cloned()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Tool arguments must be an object"))?;
        arguments.insert("projectRoot".into(), json!(self.project));
        let response = self.rpc("tools/call", &json!({"name":tool,"arguments":arguments}))?;
        let value = if let Some(value) = response
            .get("structuredContent")
            .filter(|value| !value.is_null())
        {
            value.clone()
        } else {
            let text = response["content"]
                .as_array()
                .and_then(|content| content.iter().find_map(|item| item["text"].as_str()))
                .ok_or_else(|| protocol_error("MCP tool response contains no JSON result"))?;
            serde_json::from_str(text)
                .map_err(|_| protocol_error("MCP tool response contains invalid JSON"))?
        };
        if response["isError"] == true || !value.is_object() || value["ok"] == false {
            return Err(Error::new(
                diagnostic_code(value["error"]["code"].as_str()),
                format!(
                    "{tool}: {}",
                    diagnostic_code(value["error"]["code"].as_str())
                ),
            ));
        }
        Ok(value)
    }
}
impl ToolCaller for Remote {
    fn call(&self, tool: &str, args: &Value) -> Result<Value> {
        let result = self.request_tool(tool, args)?;
        let Some(transport) = result.get("transport").filter(|value| !value.is_null()) else {
            return Ok(result);
        };
        require(
            transport["encoding"] == "base64-json-v1",
            "Unknown MCP response encoding",
            "TRANSFER_PROTOCOL_ERROR",
        )?;
        let expected = transport["bytes"]
            .as_u64()
            .filter(|bytes| *bytes <= MAX_RESPONSE as u64)
            .ok_or_else(|| protocol_error("MCP response exceeds the supported size"))?
            as usize;
        let count = transport["chunks"]
            .as_u64()
            .filter(|chunks| *chunks <= 4096)
            .ok_or_else(|| protocol_error("Invalid MCP response chunk count"))?;
        let id = transport["requestId"]
            .as_str()
            .ok_or_else(|| protocol_error("Missing MCP response request ID"))?;
        let encoded_limit = 4 * expected.div_ceil(3);
        let mut encoded = String::with_capacity(encoded_limit);
        for index in 0..count {
            let page = self.request_tool(
                "runtime_result_chunk",
                &json!({"requestId":id,"index":index}),
            )?;
            require(
                page["requestId"] == id && page["index"] == index,
                "MCP response chunk does not match the request",
                "TRANSFER_PROTOCOL_ERROR",
            )?;
            let data = page["data"]
                .as_str()
                .ok_or_else(|| protocol_error("MCP response chunk contains no data"))?;
            require(
                encoded.len() + data.len() <= encoded_limit,
                "MCP response byte count does not match",
                "TRANSFER_PROTOCOL_ERROR",
            )?;
            encoded.push_str(data);
        }
        let raw = STANDARD
            .decode(encoded)
            .map_err(|_| protocol_error("Invalid MCP response Base64"))?;
        require(
            raw.len() == expected,
            "MCP response byte count does not match",
            "TRANSFER_PROTOCOL_ERROR",
        )?;
        let value: Value = serde_json::from_slice(&raw)
            .map_err(|_| protocol_error("Invalid assembled MCP response JSON"))?;
        require(
            value.is_object() && value["ok"] != false,
            "Invalid or failed assembled MCP response",
            "MCP_ERROR",
        )?;
        Ok(value)
    }
}
impl Drop for Remote {
    fn drop(&mut self) {
        if let Ok(session) = self.session.lock() {
            if let Some(session) = session.as_ref() {
                let _ = self
                    .client
                    .delete(&self.endpoint)
                    .bearer_auth(&self.token)
                    .header("Mcp-Session-Id", session)
                    .timeout(Duration::from_secs(10))
                    .send();
            }
        }
    }
}
fn response_value(response: Response, id: u64) -> Result<Value> {
    let content_type = response
        .headers()
        .get("content-type")
        .and_then(|value| value.to_str().ok())
        .unwrap_or("")
        .to_string();
    if content_type.starts_with("text/event-stream") {
        return event_value(BufReader::new(response.take((MAX_RESPONSE + 1) as u64)), id);
    }
    require(
        content_type.starts_with("application/json"),
        "MCP response has an unsupported content type",
        "TRANSFER_PROTOCOL_ERROR",
    )?;
    let mut raw = Vec::new();
    response
        .take((MAX_RESPONSE + 1) as u64)
        .read_to_end(&mut raw)
        .map_err(|_| network_error())?;
    require(
        raw.len() <= MAX_RESPONSE,
        "MCP response exceeds the supported size",
        "TRANSFER_PROTOCOL_ERROR",
    )?;
    serde_json::from_slice(&raw).map_err(|_| protocol_error("MCP response contains invalid JSON"))
}
fn event_value(mut reader: impl BufRead, id: u64) -> Result<Value> {
    let mut event = String::new();
    let mut consumed = 0usize;
    loop {
        let mut line = String::new();
        let count = reader.read_line(&mut line).map_err(|_| network_error())?;
        consumed += count;
        require(
            consumed <= MAX_RESPONSE,
            "MCP event response exceeds the supported size",
            "TRANSFER_PROTOCOL_ERROR",
        )?;
        let line = line.trim_end_matches(['\r', '\n']);
        if line.is_empty() || count == 0 {
            if !event.is_empty() {
                let value: Value = serde_json::from_str(&event)
                    .map_err(|_| protocol_error("MCP event contains invalid JSON"))?;
                if value["id"] == id {
                    return Ok(value);
                }
                event.clear();
            }
            if count == 0 {
                return Err(protocol_error("MCP event stream ended before the response"));
            }
        } else if let Some(data) = line.strip_prefix("data:") {
            if !event.is_empty() {
                event.push('\n');
            }
            event.push_str(data.strip_prefix(' ').unwrap_or(data));
        }
    }
}
fn supports_bulk(available: &Map<String, Value>) -> bool {
    TRANSFER_TOOLS.iter().all(|(name, _)| {
        available[*name]["properties"]["encoding"]["enum"]
            .as_array()
            .is_some_and(|values| values.iter().any(|value| value == BULK_ENCODING))
    }) && available["dataset_transfer_chunk"]["properties"]
        .get("payload")
        .is_some()
}
fn save_private(path: &Path, value: &Value) -> Result<()> {
    atomic_write(path, python_json(value, false, false)?.as_bytes())?;
    private_file(path)
}
fn load_json(path: &Path) -> Result<Value> {
    Ok(serde_json::from_reader(fs::File::open(path)?)?)
}
fn output_path(path: &str) -> Result<PathBuf> {
    let path = Path::new(path);
    Ok(if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()?.join(path)
    })
}
fn emit(event: Value) {
    eprintln!("{event}");
}
fn seconds(value: Duration) -> f64 {
    (value.as_secs_f64() * 1000.0).round() / 1000.0
}

fn for_batches(
    root: &Path,
    value: &Value,
    size: u64,
    mut visit: impl FnMut(u64, Vec<Value>) -> Result<()>,
) -> Result<u64> {
    let (version, count) = reference(value)?;
    let source = root.join("data/data.sqlite3");
    require(
        source.is_file(),
        "Local data/data.sqlite3 is missing",
        "NOT_FOUND",
    )?;
    let db = Connection::open_with_flags(source, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    let metadata: Option<String> = db
        .query_row(
            "SELECT metadata FROM versions WHERE version=?",
            [version],
            |row| row.get(0),
        )
        .optional()?;
    let metadata: Value = metadata
        .as_deref()
        .map(serde_json::from_str)
        .transpose()?
        .ok_or_else(|| Error::new("NOT_FOUND", "Local data version is missing"))?;
    require(
        metadata == *value,
        "Local data reference differs from supplied metadata",
        "DATA_CONFLICT",
    )?;
    let fields = ordered_fields(value)?;
    let keys = fields
        .as_object()
        .unwrap()
        .keys()
        .cloned()
        .collect::<Vec<_>>();
    let columns = (0..keys.len())
        .map(|index| format!("c{index}"))
        .collect::<Vec<_>>()
        .join(",");
    let mut statement = db.prepare(&format!(
        "SELECT {columns},_missing FROM d_{version} ORDER BY rowid"
    ))?;
    let mut cursor = statement.query([])?;
    let (mut chunk, mut part, mut actual) = (Vec::new(), 0u64, 0u64);
    while let Some(row) = cursor.next()? {
        let missing: Option<String> = row.get(keys.len())?;
        let missing: Vec<String> = missing
            .as_deref()
            .map(serde_json::from_str)
            .transpose()?
            .unwrap_or_default();
        let missing = missing.into_iter().collect::<HashSet<_>>();
        let mut record = Map::new();
        for (index, key) in keys.iter().enumerate() {
            if missing.contains(key) {
                continue;
            }
            let mut item = json_sql(row.get_ref(index)?)?;
            if fields[key]["type"] == "boolean" && !item.is_null() {
                item = json!(item.as_i64().unwrap_or(0) != 0);
            }
            record.insert(key.clone(), item);
        }
        chunk.push(Value::Object(record));
        actual += 1;
        if chunk.len() as u64 == size {
            visit(part, std::mem::take(&mut chunk))?;
            part += 1;
        }
    }
    if !chunk.is_empty() {
        visit(part, chunk)?;
    }
    require(
        actual == count,
        "Local row count differs from the data reference",
        "DATA_CONFLICT",
    )?;
    Ok(actual)
}

struct TransferClient {
    call: Arc<dyn ToolCaller>,
    root: PathBuf,
    path: PathBuf,
    state: Value,
    concurrency: usize,
    bulk_available: bool,
    legacy: bool,
    _lock: fs::File,
}
impl TransferClient {
    fn new(
        call: Arc<dyn ToolCaller>,
        root: &Path,
        endpoint: &str,
        project: &str,
        options: &Value,
        bulk_available: bool,
    ) -> Result<Self> {
        let concurrency = options.get("concurrency").map_or(Ok(4), |value| {
            value.as_u64().ok_or_else(|| {
                Error::new(
                    "INVALID_ARGUMENT",
                    "Upload concurrency must be between 1 and 4",
                )
            })
        })? as usize;
        require(
            (1..=4).contains(&concurrency),
            "Upload concurrency must be between 1 and 4",
            "INVALID_ARGUMENT",
        )?;
        let root = root.canonicalize()?;
        let path = output_path(string(options, "state")?)?;
        fs::create_dir_all(
            path.parent()
                .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid state path"))?,
        )?;
        let lock_path = path.with_file_name(format!(
            "{}.lock",
            path.file_name().unwrap_or_default().to_string_lossy()
        ));
        let lock = fs::OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(&lock_path)?;
        private_file(&lock_path)?;
        lock.try_lock_exclusive().map_err(|_| {
            Error::new(
                "TRANSFER_IN_USE",
                "Another transfer is using this state file",
            )
        })?;
        let identity = hex::encode(Sha256::digest(
            format!("{endpoint}\0{project}\0{}", root.display()).as_bytes(),
        ));
        let mut state = if path.is_file() {
            load_json(&path)?
        } else {
            json!({"identity":identity,"uploads":{},"created":[],"staged":[],"bulk":[]})
        };
        require(
            state["identity"] == identity,
            "State file belongs to a different source or destination",
            "DATA_CONFLICT",
        )?;
        for key in ["created", "staged", "bulk"] {
            if state.get(key).is_none() {
                state[key] = json!([]);
            }
            require(
                state[key]
                    .as_array()
                    .is_some_and(|items| items.iter().all(Value::is_string)),
                "Invalid transfer state file",
                "INVALID_ARGUMENT",
            )?;
        }
        let uploads = state["uploads"]
            .as_object()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid transfer state file"))?;
        for (version, upload) in uploads {
            super::check_identifier(version, "Invalid state version")?;
            super::check_identifier(upload.as_str().unwrap_or(""), "Invalid state upload ID")?;
        }
        Ok(Self {
            call,
            root,
            path,
            state,
            concurrency,
            bulk_available,
            legacy: options["legacy"] == true,
            _lock: lock,
        })
    }
    fn save(&self) -> Result<()> {
        save_private(&self.path, &self.state)
    }
    fn contains(&self, list: &str, value: &str) -> bool {
        self.state[list]
            .as_array()
            .unwrap()
            .iter()
            .any(|item| item == value)
    }
    fn add(&mut self, list: &str, value: &str) {
        if !self.contains(list, value) {
            self.state[list].as_array_mut().unwrap().push(json!(value));
        }
    }
    fn unstage(&mut self, version: &str) -> Result<()> {
        self.state["staged"]
            .as_array_mut()
            .unwrap()
            .retain(|item| item != version);
        self.save()
    }
    fn uses_bulk(&self, version: &str) -> Result<bool> {
        if self.contains("bulk", version) {
            require(
                self.bulk_available,
                "gzip-json-v1 is required to resume this upload",
                "CAPABILITY_MISSING",
            )?;
            return Ok(true);
        }
        Ok(self.state["uploads"].get(version).is_none() && self.bulk_available && !self.legacy)
    }
    fn check_source(&self, reference: &Value) -> Result<()> {
        let (version, _) = super::reference(reference)?;
        let bulk = self.uses_bulk(version)?;
        for_batches(
            &self.root,
            reference,
            if bulk { BULK_ROWS } else { TRANSFER_ROWS },
            |_, rows| {
                let raw = json_bytes(&json!(rows))?;
                if bulk {
                    encode_bulk(&raw)?;
                } else {
                    require(
                        raw.len() <= super::TRANSFER_DECODED,
                        "A 250-row upload chunk exceeds 2 MiB; reduce source field size",
                        "INVALID_ARGUMENT",
                    )?;
                }
                Ok(())
            },
        )?;
        Ok(())
    }
    fn transfer(&mut self, reference: &Value, resume_staged: bool) -> Result<Value> {
        let (version, _) = super::reference(reference)?;
        let fresh = self.state["uploads"].get(version).is_none();
        require(
            !resume_staged || !fresh,
            "The staged version must already exist in the state file",
            "INVALID_ARGUMENT",
        )?;
        let bulk = self.uses_bulk(version)?;
        if fresh {
            if bulk {
                self.add("bulk", version);
            }
            self.state["uploads"][version] = json!(format!(
                "{}{}",
                uuid::Uuid::new_v4().simple(),
                uuid::Uuid::new_v4().simple()
            ));
        }
        self.save()?;
        let mut args = json!({"uploadId":self.state["uploads"][version],"ref":reference});
        if bulk {
            args["encoding"] = json!(BULK_ENCODING);
        }
        let started = Instant::now();
        let mut result = self.call.call("dataset_transfer_status", &args)?;
        let mut state = transfer_state(&result)?;
        if state == "failed"
            && result["code"] == "DATA_INCOMPLETE"
            && self.contains("staged", version)
        {
            self.unstage(version)?;
        }
        let mut upload_seconds = None;
        if !["complete", "running", "cleanup_required"].contains(&state) {
            if !self.contains("staged", version) && !resume_staged {
                let (mut block, mut block_bytes, mut sent, mut reused) =
                    (Vec::new(), 0usize, 0usize, 0usize);
                let mut send = |block: &mut Vec<(u64, Vec<Value>)>| -> Result<()> {
                    let (uploaded, skipped) =
                        self.upload_window(&args, std::mem::take(block), !fresh)?;
                    sent += uploaded;
                    reused += skipped;
                    emit(
                        json!({"version":version,"stage":"upload","uploadedParts":sent,"reusedParts":reused}),
                    );
                    Ok(())
                };
                for_batches(
                    &self.root,
                    reference,
                    if bulk { BULK_ROWS } else { TRANSFER_ROWS },
                    |part, rows| {
                        let bytes = json_bytes(&json!(rows))?.len();
                        if !block.is_empty() && block_bytes + bytes > 32 * 1024 * 1024 {
                            send(&mut block)?;
                            block_bytes = 0;
                        }
                        block.push((part, rows));
                        block_bytes += bytes;
                        if block.len() == if bulk { 4 } else { 128 } {
                            send(&mut block)?;
                            block_bytes = 0;
                        }
                        Ok(())
                    },
                )?;
                if !block.is_empty() {
                    send(&mut block)?;
                }
            }
            self.add("staged", version);
            self.save()?;
            upload_seconds = Some(seconds(started.elapsed()));
            result = self.call.call("dataset_transfer_finish", &args)?;
        }
        let finalize_start = Instant::now();
        let mut last_report = None;
        loop {
            state = transfer_state(&result)?;
            if state == "complete" {
                break;
            }
            if state == "failed" {
                if result["code"] == "DATA_INCOMPLETE" {
                    self.unstage(version)?;
                }
                return Err(Error::new(
                    "TRANSFER_FAILED",
                    format!(
                        "Dataset transfer failed: {}",
                        diagnostic_code(result["code"].as_str())
                    ),
                ));
            }
            if last_report.is_none_or(|at: Instant| at.elapsed() >= Duration::from_secs(20)) {
                emit(
                    json!({"version":version,"stage":"finalize","state":state,"phase":result["phase"],"completed":result["completed"],"total":result["total"]}),
                );
                last_report = Some(Instant::now());
            }
            result = self.call.call(
                if ["unknown", "cleanup_required"].contains(&state) {
                    "dataset_transfer_finish"
                } else {
                    "dataset_transfer_status"
                },
                &args,
            )?;
            if transfer_state(&result)? != "complete" {
                std::thread::sleep(Duration::from_secs(2));
            }
        }
        require(
            result["ref"] == *reference,
            "Completed transfer reference differs from the source",
            "DATA_CONFLICT",
        )?;
        emit(
            json!({"version":version,"stage":"finalize","state":"complete","rows":reference["rowCount"],"uploadSeconds":upload_seconds,"finalizeSeconds":seconds(finalize_start.elapsed())}),
        );
        Ok(reference.clone())
    }
    fn upload_window(
        &self,
        args: &Value,
        block: Vec<(u64, Vec<Value>)>,
        inspect: bool,
    ) -> Result<(usize, usize)> {
        let started = Instant::now();
        let bulk = args["encoding"] == BULK_ENCODING;
        let mut received = Map::new();
        if inspect {
            let mut request = args.clone();
            request["parts"] = json!(block.iter().map(|(part, _)| *part).collect::<Vec<_>>());
            let result = self.call.call("dataset_transfer_status", &request)?;
            if ["complete", "cleanup_required"].contains(&transfer_state(&result)?) {
                return Ok((0, block.len()));
            }
            received = result["receivedParts"]
                .as_object()
                .cloned()
                .ok_or_else(|| {
                    protocol_error("Missing receivedParts; update the target service")
                })?;
        }
        let checked = Instant::now();
        let mut pending = Vec::new();
        let (mut encoded_bytes, mut sent_bytes) = (0usize, 0usize);
        let total = block.len();
        for (part, rows) in block {
            let raw = json_bytes(&json!(rows))?;
            encoded_bytes += raw.len();
            let digest = hex::encode(Sha256::digest(&raw));
            if let Some(remote) = received.get(&part.to_string()) {
                require(
                    remote == &digest,
                    format!("Staged part {part} differs from the source"),
                    "DATA_CONFLICT",
                )?;
                continue;
            }
            let mut request = args.clone();
            request["part"] = json!(part);
            if bulk {
                let payload = encode_bulk(&raw)?;
                sent_bytes += payload.len();
                request["payload"] = json!(payload);
            } else {
                sent_bytes += raw.len();
                request["rows"] = json!(rows);
            }
            pending.push((part, request));
        }
        let encoded = Instant::now();
        for window in pending.chunks(self.concurrency) {
            let outcomes = std::thread::scope(|scope| {
                let workers = window
                    .iter()
                    .map(|(part, request)| {
                        let caller = &self.call;
                        scope.spawn(move || {
                            let result = caller.call("dataset_transfer_chunk", request)?;
                            require(
                                result["part"] == *part && result["complete"].is_boolean(),
                                "Invalid transfer chunk receipt",
                                "TRANSFER_PROTOCOL_ERROR",
                            )
                        })
                    })
                    .collect::<Vec<_>>();
                workers
                    .into_iter()
                    .map(|worker| {
                        worker
                            .join()
                            .map_err(|_| protocol_error("Upload request worker stopped"))
                            .and_then(|result| result)
                    })
                    .collect::<Vec<_>>()
            });
            for outcome in outcomes {
                outcome?;
            }
        }
        emit(
            json!({"stage":"upload-window","sentParts":pending.len(),"reusedParts":total-pending.len(),"encodedBytes":encoded_bytes,"sentPayloadBytes":sent_bytes,"receiptSeconds":seconds(checked.duration_since(started)),"encodeSeconds":seconds(encoded.duration_since(checked)),"requestSeconds":seconds(encoded.elapsed())}),
        );
        Ok((pending.len(), total - pending.len()))
    }
}
fn transfer_state(value: &Value) -> Result<&str> {
    value["state"]
        .as_str()
        .filter(|state| {
            [
                "unknown",
                "running",
                "cleanup_required",
                "complete",
                "failed",
            ]
            .contains(state)
        })
        .ok_or_else(|| {
            protocol_error("Missing or unsupported transfer state; update the target service")
        })
}
fn normalized(document: &Value) -> Value {
    let mut result = document.clone();
    if let Some(object) = result.as_object_mut() {
        for key in ["dataVersion", "computed", "progressive", "loading"] {
            object.remove(key);
        }
    }
    result["revision"] = json!(1);
    result
}
type ProjectTransfer = (PathBuf, BTreeMap<String, Value>, BTreeMap<String, Value>);

fn read_project(manifest: &Value) -> Result<ProjectTransfer> {
    let root = Path::new(string(manifest, "projectRoot")?).canonicalize()?;
    let mut db = Connection::open_with_flags(
        root.join("dashboards/dashboards.sqlite3"),
        OpenFlags::SQLITE_OPEN_READ_ONLY,
    )?;
    let transaction = db.transaction()?;
    let pages = manifest["pages"].as_array().ok_or_else(|| {
        Error::new(
            "INVALID_ARGUMENT",
            "Transfer manifest pages must be an array",
        )
    })?;
    let (mut documents, mut references) = (BTreeMap::new(), BTreeMap::new());
    for page in pages {
        let board = string(page, "dashboardId")?;
        model::check_identifier(board)?;
        require(
            !documents.contains_key(board),
            "Duplicate dashboard in transfer manifest",
            "INVALID_ARGUMENT",
        )?;
        let row: Option<(i64, String)> = transaction
            .query_row(
                "SELECT revision,document FROM boards WHERE id=?",
                [board],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        let (revision, raw) =
            row.ok_or_else(|| Error::new("NOT_FOUND", format!("{board}: dashboard is missing")))?;
        require(
            page["draftRevision"] == revision,
            format!("{board}: draft revision changed; rebuild the manifest"),
            "REVISION_CONFLICT",
        )?;
        let mut document: Value = serde_json::from_str(&raw)?;
        let components = document["manifest"]["components"]
            .as_object()
            .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Dashboard components are missing"))?;
        require(
            !components
                .values()
                .any(|component| component["kind"] == "chart"),
            format!("{board}: native chart components require an explicit import plan"),
            "UNSUPPORTED_OPERATION",
        )?;
        require(
            page["componentCount"] == components.len(),
            format!("{board}: component count changed"),
            "DATA_CONFLICT",
        )?;
        let used = components
            .values()
            .flat_map(|component| {
                [
                    component["datasetId"].as_str(),
                    component["binding"]["datasetId"].as_str(),
                ]
            })
            .flatten()
            .map(str::to_owned)
            .collect::<HashSet<_>>();
        let notes: Option<String> = transaction
            .query_row(
                "SELECT payload FROM annotations WHERE board_id=?",
                [board],
                |row| row.get(0),
            )
            .optional()?;
        document["manifest"]["annotations"] = notes
            .as_deref()
            .map(serde_json::from_str)
            .transpose()?
            .unwrap_or_else(|| json!([]));
        let selected = page["datasets"]
            .as_array()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Selected datasets must be an array"))?;
        let mut chosen = HashSet::new();
        require(
            document["snapshot"]["datasets"]
                .as_object()
                .is_none_or(Map::is_empty)
                && document["snapshot"]["componentDataRefs"]
                    .as_object()
                    .is_none_or(Map::is_empty),
            format!("{board}: inline or component datasets require an explicit import plan"),
            "UNSUPPORTED_OPERATION",
        )?;
        for item in selected {
            let id = string(item, "id")?;
            require(
                chosen.insert(id.to_owned()),
                format!("{board}: duplicate dataset in manifest"),
                "INVALID_ARGUMENT",
            )?;
            let value = &document["snapshot"]["datasetRefs"][id];
            let (version, _) = reference(value)?;
            require(
                ["version", "rowCount", "bytes"]
                    .iter()
                    .all(|key| value[*key] == item[*key]),
                format!("{board}/{id}: manifest data reference changed"),
                "DATA_CONFLICT",
            )?;
            if let Some(previous) = references.insert(version.to_owned(), value.clone()) {
                require(
                    previous == *value,
                    "Conflicting immutable reference metadata",
                    "DATA_CONFLICT",
                )?;
            }
        }
        require(
            used.is_subset(&chosen),
            format!("{board}: manifest omits a component dataset"),
            "INVALID_ARGUMENT",
        )?;
        if let Some(datasets) = document
            .get_mut("manifest")
            .and_then(|value| value.get_mut("datasets"))
            .and_then(Value::as_object_mut)
        {
            datasets.retain(|id, _| chosen.contains(id));
        }
        if let Some(metrics) = document
            .get_mut("manifest")
            .and_then(|value| value.get_mut("metrics"))
            .and_then(Value::as_object_mut)
        {
            metrics.retain(|_, metric| {
                metric["datasetId"]
                    .as_str()
                    .is_some_and(|id| chosen.contains(id))
            });
        }
        if let Some(refs) = document
            .get_mut("snapshot")
            .and_then(|value| value.get_mut("datasetRefs"))
            .and_then(Value::as_object_mut)
        {
            refs.retain(|id, _| chosen.contains(id));
        }
        if let Some(sources) = document
            .get_mut("manifest")
            .and_then(|value| value.get_mut("sources"))
            .and_then(Value::as_object_mut)
        {
            for source in sources.values_mut() {
                source["verification"] = json!("supplied");
            }
        }
        model::validate(&document)?;
        documents.insert(board.to_owned(), document);
    }
    Ok((root, documents, references))
}
pub fn command(options: &Value) -> Result<Value> {
    command_with(options, Remote::connect)
}
fn command_with(options: &Value, connect: impl Fn(&str) -> Result<Arc<Remote>>) -> Result<Value> {
    let manifest = load_json(Path::new(string(options, "manifest")?))?;
    let (root, documents, references) = read_project(&manifest)?;
    let project = string(options, "project")?;
    let remote = connect(project)?;
    let mut required = TRANSFER_TOOLS.to_vec();
    required.extend([
        ("dashboard_list", &[][..]),
        ("dashboard_get", &["dashboardId"][..]),
        ("runtime_result_chunk", &["requestId", "index"][..]),
        ("dashboard_create", &["dashboardId", "document"][..]),
    ]);
    let available = remote.require_tools(&required)?;
    let mut client = TransferClient::new(
        remote.clone(),
        &root,
        &remote.endpoint,
        project,
        options,
        supports_bulk(&available),
    )?;
    let resume = options["resume_staged"].as_str();
    require(
        resume.is_none_or(|version| references.contains_key(version)),
        "The staged version must exist in the manifest",
        "INVALID_ARGUMENT",
    )?;
    for reference in references.values() {
        client.check_source(reference)?;
    }
    let listed = remote.call("dashboard_list", &json!({}))?;
    let existing = listed["dashboards"]
        .as_array()
        .ok_or_else(|| protocol_error("Dashboard list is missing"))?
        .iter()
        .map(|item| {
            item["id"]
                .as_str()
                .map(str::to_owned)
                .ok_or_else(|| protocol_error("Dashboard ID is missing"))
        })
        .collect::<Result<HashSet<_>>>()?;
    for (board, document) in &documents {
        if existing.contains(board) {
            let actual = remote.call("dashboard_get", &json!({"dashboardId":board}))?;
            require(
                normalized(&actual["document"]) == normalized(document),
                format!("{board}: destination exists and differs; refusing to overwrite"),
                "DATA_CONFLICT",
            )?;
        }
    }
    if options["check_only"] == true {
        return Ok(json!({"checkedPages":documents.len(),"checkedDatasets":references.len()}));
    }
    for (version, reference) in &references {
        client.transfer(reference, resume == Some(version.as_str()))?;
    }
    for (board, document) in &documents {
        if !existing.contains(board) {
            remote.call(
                "dashboard_create",
                &json!({"dashboardId":board,"document":document}),
            )?;
        }
        client.add("created", board);
        client.save()?;
        emit(
            json!({"stage":"import","dashboardId":board,"state":"imported","nextAction":"dashboard_checkpoint"}),
        );
    }
    Ok(
        json!({"state":"complete","importedPages":documents.len(),"transferredDatasets":references.len(),"nextAction":"dashboard_checkpoint"}),
    )
}
fn source_reference(options: &Value) -> Result<Value> {
    require(
        options.get("ref").is_some() != options.get("rows").is_some(),
        "Specify exactly one of --ref or --rows",
        "INVALID_ARGUMENT",
    )?;
    if let Some(path) = options["ref"].as_str() {
        return load_json(Path::new(path));
    }
    let root = Path::new(string(options, "root")?);
    let fields = load_json(Path::new(string(options, "fields")?))?;
    let path = Path::new(string(options, "rows")?);
    let data = LocalData::new(Some(&root.join("data")))?;
    if path
        .extension()
        .is_some_and(|extension| extension == "jsonl")
    {
        let rows = BufReader::new(fs::File::open(path)?)
            .lines()
            .filter_map(|line| match line {
                Ok(line) if line.trim().is_empty() => None,
                value => Some(
                    value
                        .map_err(Error::from)
                        .and_then(|line| serde_json::from_str(&line).map_err(Error::from)),
                ),
            });
        data.import_iter(rows, &fields)
    } else {
        let rows = load_json(path)?;
        data.import_rows(
            rows.as_array().ok_or_else(|| {
                Error::new(
                    "INVALID_ARGUMENT",
                    "--rows must contain a JSON array or a .jsonl file",
                )
            })?,
            &fields,
        )
    }
}
pub fn remote_command(options: &Value) -> Result<Value> {
    remote_command_with(options, Remote::connect)
}
fn remote_command_with(
    options: &Value,
    connect: impl Fn(&str) -> Result<Arc<Remote>>,
) -> Result<Value> {
    let project = string(options, "project")?;
    let action = string(options, "action")?;
    let output = output_path(string(options, "output")?)?;
    if action == "read" {
        let remote = connect(project)?;
        remote.require_tools(&[
            ("dashboard_get", &["dashboardId"]),
            ("runtime_result_chunk", &["requestId", "index"]),
        ])?;
        let result = remote.call(
            "dashboard_get",
            &json!({"dashboardId":string(options,"dashboard")?}),
        )?;
        save_private(&output, &result)?;
        return Ok(
            json!({"output":output,"revision":result["document"]["revision"],"componentIds":result["document"]["manifest"]["components"].as_object().map(|components|components.keys().collect::<Vec<_>>()).unwrap_or_default()}),
        );
    }
    require(
        action == "upload",
        "Remote action must be read or upload",
        "INVALID_ARGUMENT",
    )?;
    let started = Instant::now();
    let reference = source_reference(options)?;
    emit(
        json!({"stage":"source","rows":reference["rowCount"],"bytes":reference["bytes"],"seconds":seconds(started.elapsed())}),
    );
    let remote = connect(project)?;
    let available = remote.require_tools(TRANSFER_TOOLS)?;
    let mut client = TransferClient::new(
        remote.clone(),
        Path::new(string(options, "root")?),
        &remote.endpoint,
        project,
        options,
        supports_bulk(&available),
    )?;
    client.check_source(&reference)?;
    if options["check_only"] == true {
        return Ok(json!({"checked":true,"rows":reference["rowCount"],"bytes":reference["bytes"]}));
    }
    let resume = options["resume_staged"]
        .as_str()
        .is_some_and(|version| reference["version"] == version);
    require(
        options.get("resume_staged").is_none() || resume,
        "The staged version must match the selected reference",
        "INVALID_ARGUMENT",
    )?;
    client.transfer(&reference, resume)?;
    save_private(&output, &reference)?;
    Ok(
        json!({"state":"complete","output":output,"version":reference["version"],"rowCount":reference["rowCount"]}),
    )
}

#[cfg(test)]
#[path = "../../tests/unit/transfer_client.rs"]
mod regression_tests;

#[cfg(test)]
#[path = "../../tests/unit/transfer_client_existing.rs"]
mod tests;
