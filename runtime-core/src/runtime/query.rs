//! Operator-configured, bounded, read-only SQL sources. No source credentials are tool arguments.
use super::{
    data::{json_sql, sql_value, LocalData},
    error::{require, Error, Result},
    model::inferred_fields,
    serialization::utcnow,
};
use rusqlite::{
    hooks::{AuthAction, AuthContext, Authorization},
    OpenFlags,
};
use serde_json::{json, Map, Value};
use std::{
    collections::{HashMap, HashSet},
    fs,
    path::{Path, PathBuf},
    sync::mpsc,
    thread,
    time::{Duration, Instant},
};
pub const MAX_QUERY_ROWS: usize = 10_000;
const SAFE_FUNCTIONS:&str="abs avg coalesce count date datetime dense_rank first_value hex ifnull instr julianday lag last_value lead length like likelihood lower ltrim max min nullif nth_value ntile percent_rank printf rank replace round row_number rtrim strftime substr substring sum time total trim typeof unicode unixepoch upper";
#[derive(Clone, Debug)]
pub struct Source {
    pub engine: String,
    pub target: String,
}
#[derive(Clone, Default)]
pub struct QueryRunner {
    pub sources: HashMap<String, Source>,
}
pub struct QueryResult {
    pub rows: Vec<Value>,
    pub fields: Value,
    pub source: Value,
}
impl QueryRunner {
    pub fn new(file: Option<&Path>) -> Result<Self> {
        let mut this = Self::default();
        if let Some(file) = file {
            let cfg: Value = serde_json::from_slice(&fs::read(file)?)?;
            let cfg = cfg.as_object().ok_or_else(|| {
                Error::new("INVALID_CONFIG", "Source configuration must be an object")
            })?;
            for (alias, source) in cfg {
                let engine = source["engine"].as_str().unwrap_or("");
                require(
                    ["sqlite", "postgresql", "duckdb"].contains(&engine),
                    "Source engine must be sqlite, postgresql, or duckdb",
                    "INVALID_CONFIG",
                )?;
                let target = if engine == "postgresql" {
                    let name = source["dsnEnv"].as_str().unwrap_or("");
                    let mut chars = name.chars();
                    require(
                        chars
                            .next()
                            .is_some_and(|c| c.is_ascii_alphabetic() || c == '_')
                            && chars.all(|c| c.is_ascii_alphanumeric() || c == '_'),
                        "PostgreSQL source requires dsnEnv with an environment variable name",
                        "INVALID_CONFIG",
                    )?;
                    name.into()
                } else {
                    let name = source["path"]
                        .as_str()
                        .filter(|s| !s.trim().is_empty())
                        .ok_or_else(|| {
                            Error::new("INVALID_CONFIG", "File SQL source requires a path")
                        })?;
                    let path = expand_path(name)?.canonicalize()?;
                    require(
                        path.is_file(),
                        "SQL source must be an existing database file",
                        "INVALID_CONFIG",
                    )?;
                    path.to_string_lossy().into_owned()
                };
                this.sources.insert(
                    alias.clone(),
                    Source {
                        engine: engine.into(),
                        target,
                    },
                );
            }
        }
        Ok(this)
    }
    pub fn source(&self, alias: &str) -> Result<&Source> {
        self.sources.get(alias).ok_or_else(|| {
            Error::new(
                "SOURCE_NOT_ALLOWED",
                "Unknown source alias; configure it on the server, not in the tool call",
            )
        })
    }
    pub fn sqlite_path(&self, alias: &str) -> Result<PathBuf> {
        let s = self.source(alias)?;
        require(
            s.engine == "sqlite",
            "dataset_attach requires SQLite; use query_execute for other engines",
            "SOURCE_NOT_ALLOWED",
        )?;
        Ok(PathBuf::from(&s.target))
    }
    pub fn execute(
        &self,
        alias: &str,
        sql: &str,
        params: Option<&Value>,
        timeout: f64,
        fields: Option<&Value>,
        expected_engine: Option<&str>,
    ) -> Result<QueryResult> {
        let source = self.source(alias)?;
        require(
            expected_engine.is_none_or(|e| e == source.engine),
            "Source engine changed; register SQL again for the configured engine",
            "SOURCE_ENGINE_CHANGED",
        )?;
        require(
            !sql.is_empty() && sql.chars().count() < 100000,
            "SQL must contain 1-99999 characters",
            "INVALID_ARGUMENT",
        )?;
        require(
            params.is_none_or(|p| p.is_array() || p.is_object()),
            "Parameters must be an object or array",
            "INVALID_ARGUMENT",
        )?;
        require(
            timeout.is_finite() && timeout > 0.0 && timeout <= 3600.0,
            "Invalid query timeout",
            "INVALID_ARGUMENT",
        )?;
        let started = Instant::now();
        let (columns, mut rows, dates) = match source.engine.as_str() {
            "sqlite" => sqlite(&source.target, sql, params, timeout)?,
            "postgresql" => postgres_query(&source.target, sql, params, timeout)?,
            _ => duck_query(&source.target, sql, params, timeout)?,
        };
        require(
            columns.iter().collect::<HashSet<_>>().len() == columns.len(),
            "Duplicate SQL column names; add unique aliases",
            "INVALID_ARGUMENT",
        )?;
        require(rows.len()<=MAX_QUERY_ROWS,"Query exceeds 10000 rows. Aggregate or narrow the query; rows are not silently truncated.","INVALID_ARGUMENT")?;
        let mut metadata = if let Some(fields) = fields {
            let keys = fields.as_object().ok_or_else(|| {
                Error::new("QUERY_SCHEMA_CHANGED", "Declared fields must be a mapping")
            })?;
            require(
                columns.iter().all(|c| keys.contains_key(c)) && keys.len() == columns.len(),
                "SQL result columns must match declared fields",
                "QUERY_SCHEMA_CHANGED",
            )?;
            for (k, m) in keys {
                if m["type"] == "boolean" {
                    for row in &mut rows {
                        if matches!(row[k].as_i64(), Some(0 | 1)) {
                            row[k] = json!(row[k].as_i64() == Some(1));
                        }
                    }
                }
            }
            fields.clone()
        } else if rows.is_empty() {
            Value::Object(
                columns
                    .iter()
                    .map(|c| (c.clone(), json!({"type":"string","label":c})))
                    .collect(),
            )
        } else {
            inferred_fields(&rows)?
        };
        if fields.is_none() {
            for key in dates {
                metadata[&key]["type"] = json!("date");
            }
        }
        let source = json!({"kind":"query","verification":"runtime-executed","query":{"id":uuid::Uuid::new_v4().simple().to_string(),"engine":source.engine,"connection":alias,"sql":sql,"parameters":params.cloned().filter(|p|p.as_array().is_none_or(|a|!a.is_empty())).unwrap_or(json!({})),"executedAt":utcnow(),"durationMs":(started.elapsed().as_secs_f64()*1000.0).round(),"rowCount":rows.len()}});
        Ok(QueryResult {
            rows,
            fields: metadata,
            source,
        })
    }
}
type RawResult = (Vec<String>, Vec<Value>, Vec<String>);
fn expand_path(path: &str) -> Result<PathBuf> {
    if let Some(rest) = path.strip_prefix("~/") {
        let home = std::env::var_os("HOME")
            .ok_or_else(|| Error::new("INVALID_CONFIG", "Home directory is not available"))?;
        Ok(PathBuf::from(home).join(rest))
    } else {
        Ok(PathBuf::from(path))
    }
}
fn sqlite(path: &str, sql: &str, params: Option<&Value>, timeout: f64) -> Result<RawResult> {
    let run = || -> Result<RawResult> {
        let mut db = rusqlite::Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
        db.busy_timeout(Duration::from_secs_f64(timeout))?;
        db.execute_batch("PRAGMA query_only=ON")?;
        db.authorizer(Some(|context: AuthContext<'_>| match context.action {
            AuthAction::Select | AuthAction::Read { .. } | AuthAction::Recursive => {
                Authorization::Allow
            }
            AuthAction::Function { function_name }
                if SAFE_FUNCTIONS
                    .split_whitespace()
                    .any(|f| f.eq_ignore_ascii_case(function_name)) =>
            {
                Authorization::Allow
            }
            _ => Authorization::Deny,
        }))?;
        let start = Instant::now();
        db.progress_handler(1000, Some(move || start.elapsed().as_secs_f64() > timeout))?;
        let mut stmt = db.prepare(sql)?;
        require(
            stmt.column_count() > 0,
            "Only queries returning rows are allowed",
            "QUERY_REJECTED",
        )?;
        let columns = stmt
            .column_names()
            .map(|c| c.to_string())
            .collect::<Vec<_>>();
        require(
            columns.iter().collect::<HashSet<_>>().len() == columns.len(),
            "Duplicate SQL column names; add unique aliases",
            "QUERY_REJECTED",
        )?;
        match params {
            Some(Value::Object(map)) => {
                for i in 1..=stmt.parameter_count() {
                    let name = stmt.parameter_name(i).ok_or_else(|| {
                        Error::new(
                            "QUERY_REJECTED",
                            "Named parameters cannot bind anonymous placeholders",
                        )
                    })?;
                    let key = name.trim_start_matches([':', '@', '$']);
                    let v = map.get(key).ok_or_else(|| {
                        Error::new("QUERY_REJECTED", format!("Missing parameter: {key}"))
                    })?;
                    stmt.raw_bind_parameter(i, sql_value(v)?)?;
                }
            }
            Some(Value::Array(values)) => {
                require(
                    values.len() == stmt.parameter_count(),
                    "Incorrect number of query parameters",
                    "QUERY_REJECTED",
                )?;
                for (i, v) in values.iter().enumerate() {
                    stmt.raw_bind_parameter(i + 1, sql_value(v)?)?;
                }
            }
            _ => require(
                stmt.parameter_count() == 0,
                "Query parameters are required",
                "QUERY_REJECTED",
            )?,
        };
        let mut cursor = stmt.raw_query();
        let mut rows = Vec::new();
        while rows.len() <= MAX_QUERY_ROWS {
            let Some(r) = cursor.next()? else { break };
            let mut row = Map::new();
            for (i, c) in columns.iter().enumerate() {
                let v = json_sql(r.get_ref(i)?).map_err(|_| {
                    Error::new(
                        "QUERY_SCHEMA_CHANGED",
                        "SQL result contains a non-scalar, non-finite, or invalid UTF-8 value",
                    )
                })?;
                require(
                    !v.is_number() || v.as_f64().is_some_and(f64::is_finite),
                    "SQL result contains a non-finite number",
                    "QUERY_SCHEMA_CHANGED",
                )?;
                row.insert(c.clone(), v);
            }
            rows.push(Value::Object(row));
        }
        Ok((columns, rows, Vec::new()))
    };
    run().map_err(|e| {
        if e.code == "QUERY_SCHEMA_CHANGED" {
            e
        } else {
            Error::new("QUERY_REJECTED", e.message)
        }
    })
}

#[derive(Debug)]
struct PgParam(Value);
impl postgres::types::ToSql for PgParam {
    fn to_sql(
        &self,
        ty: &postgres::types::Type,
        out: &mut bytes::BytesMut,
    ) -> std::result::Result<postgres::types::IsNull, Box<dyn std::error::Error + Sync + Send>>
    {
        use postgres::types::{IsNull, Type};
        let v = &self.0;
        if v.is_null() {
            return Ok(IsNull::Yes);
        }
        match *ty {
            Type::BOOL => v
                .as_bool()
                .ok_or("Expected boolean parameter")?
                .to_sql(ty, out),
            Type::INT2 => {
                i16::try_from(v.as_i64().ok_or("Expected integer parameter")?)?.to_sql(ty, out)
            }
            Type::INT4 => {
                i32::try_from(v.as_i64().ok_or("Expected integer parameter")?)?.to_sql(ty, out)
            }
            Type::INT8 => v
                .as_i64()
                .ok_or("Expected integer parameter")?
                .to_sql(ty, out),
            Type::FLOAT4 => (v.as_f64().ok_or("Expected number parameter")? as f32).to_sql(ty, out),
            Type::FLOAT8 => v
                .as_f64()
                .ok_or("Expected number parameter")?
                .to_sql(ty, out),
            Type::NUMERIC => {
                let d = rust_decimal::Decimal::from_str_exact(&v.to_string())?;
                d.to_sql(ty, out)
            }
            Type::JSON | Type::JSONB => v.to_sql(ty, out),
            _ => v.as_str().ok_or("Expected text parameter")?.to_sql(ty, out),
        }
    }
    fn accepts(_: &postgres::types::Type) -> bool {
        true
    }
    fn encode_format(&self, ty: &postgres::types::Type) -> postgres::types::Format {
        use postgres::types::{Format, Type};
        match *ty {
            // These scalars arrive as JSON strings, not PostgreSQL's binary
            // temporal/UUID representation. Let the server parse their text.
            Type::DATE | Type::TIME | Type::TIMESTAMP | Type::TIMESTAMPTZ | Type::UUID => {
                Format::Text
            }
            _ => Format::Binary,
        }
    }
    postgres::types::to_sql_checked!();
}
fn postgres_query(env: &str, sql: &str, params: Option<&Value>, timeout: f64) -> Result<RawResult> {
    use postgres::types::Type;
    let dsn = std::env::var(env).map_err(|_| {
        Error::new(
            "INVALID_CONFIG",
            format!("Configure PostgreSQL connection in the {env} environment variable"),
        )
    })?;
    let mut config: postgres::Config = dsn.parse().map_err(|_| {
        Error::new(
            "INVALID_CONFIG",
            "Invalid PostgreSQL connection configuration",
        )
    })?;
    config.connect_timeout(Duration::from_secs_f64(timeout.ceil().max(2.0)));
    let connector = native_tls::TlsConnector::builder()
        .build()
        .map_err(|_| Error::new("SOURCE_UNAVAILABLE", "TLS initialization failed"))?;
    let tls = postgres_native_tls::MakeTlsConnector::new(connector);
    let mut db = config.connect(tls).map_err(|_| {
        Error::new(
            "SOURCE_UNAVAILABLE",
            "Could not connect to configured PostgreSQL source",
        )
        .with_status(503)
    })?;
    let (query, bindings) = pg_placeholders(sql, params)?;
    let args = bindings
        .iter()
        .map(|v| v as &(dyn postgres::types::ToSql + Sync))
        .collect::<Vec<_>>();
    let mut run = || -> std::result::Result<RawResult, postgres::Error> {
        let mut tx = db.transaction()?;
        tx.batch_execute("SET TRANSACTION READ ONLY")?;
        tx.query_one(
            "SELECT set_config('statement_timeout',$1,true)",
            &[&format!("{}ms", (timeout * 1000.0).round() as u64)],
        )?;
        tx.execute(&format!("DECLARE charts_query CURSOR FOR {query}"), &args)?;
        let values = tx.query(
            &format!("FETCH {} FROM charts_query", MAX_QUERY_ROWS + 1),
            &[],
        )?;
        let statement = tx.prepare("FETCH 0 FROM charts_query")?;
        let columns = statement
            .columns()
            .iter()
            .map(|c| c.name().to_string())
            .collect::<Vec<_>>();
        let mut dates = Vec::new();
        for c in statement.columns() {
            if matches!(*c.type_(), Type::DATE | Type::TIMESTAMP | Type::TIMESTAMPTZ) {
                dates.push(c.name().to_string());
            }
        }
        let mut rows = Vec::new();
        for r in values {
            let mut row = Map::new();
            for (i, c) in r.columns().iter().enumerate() {
                let v = r
                    .try_get::<_, Option<PgScalar>>(i)?
                    .map(|v| v.0)
                    .unwrap_or(Value::Null);
                row.insert(c.name().to_string(), v);
            }
            rows.push(Value::Object(row));
        }
        tx.rollback()?;
        Ok((columns, rows, dates))
    };
    run().map_err(|e| {
        if e.code() == Some(&postgres::error::SqlState::QUERY_CANCELED) {
            Error::new("QUERY_TIMEOUT", "PostgreSQL query timed out")
        } else {
            Error::new(
                "QUERY_REJECTED",
                format!(
                    "PostgreSQL query failed ({})",
                    e.code().map(|c| c.code()).unwrap_or("unknown")
                ),
            )
        }
    })
}
struct PgScalar(Value);
impl<'a> postgres::types::FromSql<'a> for PgScalar {
    fn from_sql(
        ty: &postgres::types::Type,
        raw: &'a [u8],
    ) -> std::result::Result<Self, Box<dyn std::error::Error + Sync + Send>> {
        use postgres::types::Type;
        let value = match *ty {
            Type::BOOL => json!(bool::from_sql(ty, raw)?),
            Type::INT2 => json!(i16::from_sql(ty, raw)?),
            Type::INT4 => json!(i32::from_sql(ty, raw)?),
            Type::INT8 => json!(i64::from_sql(ty, raw)?),
            Type::FLOAT4 => {
                let n = f32::from_sql(ty, raw)?;
                if !n.is_finite() {
                    return Err("Non-finite SQL number".into());
                }
                json!(n)
            }
            Type::FLOAT8 => {
                let n = f64::from_sql(ty, raw)?;
                if !n.is_finite() {
                    return Err("Non-finite SQL number".into());
                }
                json!(n)
            }
            Type::NUMERIC => {
                let d = rust_decimal::Decimal::from_sql(ty, raw)?;
                json!(d.to_string().parse::<f64>()?)
            }
            Type::DATE => json!(chrono::NaiveDate::from_sql(ty, raw)?.to_string()),
            Type::TIME => json!(chrono::NaiveTime::from_sql(ty, raw)?
                .format("%H:%M:%S%.f")
                .to_string()),
            Type::TIMESTAMP => json!(chrono::NaiveDateTime::from_sql(ty, raw)?
                .format("%Y-%m-%dT%H:%M:%S%.f")
                .to_string()),
            Type::TIMESTAMPTZ => json!(chrono::DateTime::<chrono::Utc>::from_sql(ty, raw)?
                .to_rfc3339_opts(chrono::SecondsFormat::AutoSi, false)),
            Type::UUID => json!(uuid::Uuid::from_slice(raw)?.to_string()),
            Type::JSON | Type::JSONB => {
                let value = Value::from_sql(ty, raw)?;
                if value.is_array() || value.is_object() {
                    return Err(
                        "SQL result must contain scalar fields; extract JSON scalar values".into(),
                    );
                }
                value
            }
            Type::VARCHAR | Type::TEXT | Type::BPCHAR | Type::NAME | Type::UNKNOWN => {
                json!(std::str::from_utf8(raw)?)
            }
            _ => {
                return Err("SQL result must contain scalar fields; cast unsupported values".into())
            }
        };
        Ok(Self(value))
    }
    fn accepts(_: &postgres::types::Type) -> bool {
        true
    }
}
fn pg_placeholders(sql: &str, params: Option<&Value>) -> Result<(String, Vec<PgParam>)> {
    if params.is_none() {
        return Ok((sql.into(), Vec::new()));
    }
    let mut out = String::new();
    let mut bound = Vec::new();
    let chars = sql.chars().collect::<Vec<_>>();
    let mut i = 0;
    let mut position = 0;
    while i < chars.len() {
        if chars[i] != '%' {
            out.push(chars[i]);
            i += 1;
            continue;
        }
        if chars.get(i + 1) == Some(&'%') {
            out.push('%');
            i += 2;
            continue;
        }
        let value;
        if chars.get(i + 1) == Some(&'(') {
            let close = (i + 2..chars.len())
                .find(|j| chars[*j] == ')')
                .ok_or_else(|| Error::new("QUERY_REJECTED", "Malformed PostgreSQL placeholder"))?;
            require(
                chars
                    .get(close + 1)
                    .is_some_and(|c| ['s', 'b', 't'].contains(c)),
                "Malformed PostgreSQL placeholder",
                "QUERY_REJECTED",
            )?;
            let name = chars[i + 2..close].iter().collect::<String>();
            value = params
                .and_then(Value::as_object)
                .and_then(|m| m.get(&name))
                .ok_or_else(|| {
                    Error::new("QUERY_REJECTED", format!("Missing query parameter: {name}"))
                })?
                .clone();
            i = close + 2;
        } else {
            require(
                chars
                    .get(i + 1)
                    .is_some_and(|c| ['s', 'b', 't'].contains(c)),
                "Malformed PostgreSQL placeholder; use %% for percent",
                "QUERY_REJECTED",
            )?;
            value = params
                .and_then(Value::as_array)
                .and_then(|a| a.get(position))
                .ok_or_else(|| Error::new("QUERY_REJECTED", "Missing positional query parameter"))?
                .clone();
            position += 1;
            i += 2;
        }
        require(
            value.is_null() || value.is_string() || value.is_number() || value.is_boolean(),
            "Query parameter must be scalar",
            "INVALID_ARGUMENT",
        )?;
        bound.push(PgParam(value));
        out.push_str(&format!("${}", bound.len()));
    }
    if let Some(a) = params.and_then(Value::as_array) {
        require(
            position == a.len(),
            "Incorrect number of query parameters",
            "QUERY_REJECTED",
        )?;
    }
    Ok((out, bound))
}

fn duck_error(e: duckdb::Error) -> Error {
    let text = e.to_string();
    if text.to_lowercase().contains("interrupt") {
        Error::new("QUERY_TIMEOUT", "DuckDB query timed out")
    } else {
        Error::new("QUERY_REJECTED", text)
    }
}
fn duck_config() -> std::result::Result<duckdb::Config, duckdb::Error> {
    duckdb::Config::default()
        .access_mode(duckdb::AccessMode::ReadOnly)?
        // DuckDB applies C API options in order. Disable its spill directory
        // before external access blocks further directory configuration.
        .with("temp_directory", "")?
        .enable_autoload_extension(false)?
        .with("autoinstall_known_extensions", "false")?
        .enable_external_access(false)?
        .with("lock_configuration", "true")
}
struct QueryTimer {
    stop: Option<mpsc::Sender<()>>,
    thread: Option<thread::JoinHandle<()>>,
}
impl Drop for QueryTimer {
    fn drop(&mut self) {
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}
fn duck_query(path: &str, sql: &str, params: Option<&Value>, timeout: f64) -> Result<RawResult> {
    validate_duckdb_select(path, sql)?;
    let db = duckdb::Connection::open_with_flags(path, duck_config().map_err(duck_error)?)
        .map_err(duck_error)?;
    let interrupt = db.interrupt_handle();
    let (sender, receiver) = mpsc::channel();
    let timer = QueryTimer {
        stop: Some(sender),
        thread: Some(thread::spawn(move || {
            if receiver
                .recv_timeout(Duration::from_secs_f64(timeout))
                .is_err()
            {
                interrupt.interrupt();
            }
        })),
    };
    let mut stmt = db.prepare(sql).map_err(duck_error)?;
    let mut bindings = Vec::new();
    for i in 1..=stmt.parameter_count() {
        let value = match params {
            Some(Value::Array(a)) => a.get(i - 1),
            Some(Value::Object(m)) => m.get(&stmt.parameter_name(i).map_err(duck_error)?),
            _ => None,
        }
        .ok_or_else(|| Error::new("QUERY_REJECTED", "Missing query parameter"))?;
        bindings.push(duck_param(value)?);
    }
    if let Some(p) = params {
        let len = p
            .as_array()
            .map(Vec::len)
            .or_else(|| p.as_object().map(Map::len))
            .unwrap_or(0);
        require(
            len == stmt.parameter_count(),
            "Incorrect number of query parameters",
            "QUERY_REJECTED",
        )?;
    }
    // Start a streaming result, then use the driver's fallible row cursor.
    // query() materializes every row before our result limit can stop it;
    // iterating ArrowStream directly would panic on a later fetch error.
    {
        let _stream = stmt
            .stream_arrow(duckdb::params_from_iter(bindings.iter()))
            .map_err(duck_error)?;
    }
    let schema = stmt.schema();
    let mut cursor = stmt.raw_query();
    let mut columns = Vec::new();
    let mut rows = Vec::new();
    let mut dates = HashSet::new();
    while rows.len() <= MAX_QUERY_ROWS {
        let Some(row) = cursor.next().map_err(duck_error)? else {
            break;
        };
        if columns.is_empty() {
            columns = row.as_ref().column_names().to_vec();
        }
        let mut result = Map::new();
        for (i, name) in columns.iter().enumerate() {
            let scalar = row.get_ref(i).map_err(duck_error)?;
            if matches!(
                scalar,
                duckdb::types::ValueRef::Date32(_) | duckdb::types::ValueRef::Timestamp(_, _)
            ) {
                dates.insert(name.clone());
            }
            let value = match (scalar, schema.field(i).data_type()) {
                // DuckDB exposes UUID as its fixed-width binary Arrow carrier;
                // ordinary SQL BLOB values remain unsupported scalar fields.
                (
                    duckdb::types::ValueRef::Blob(bytes),
                    duckdb::arrow::datatypes::DataType::FixedSizeBinary(16),
                ) => {
                    json!(uuid::Uuid::from_slice(bytes)
                        .map_err(|_| Error::new("QUERY_SCHEMA_CHANGED", "Invalid UUID result"))?
                        .to_string())
                }
                (
                    duckdb::types::ValueRef::Timestamp(unit, value),
                    duckdb::arrow::datatypes::DataType::Timestamp(_, Some(_)),
                ) => {
                    json!(duck_timestamp(unit, value)?
                        .to_rfc3339_opts(chrono::SecondsFormat::AutoSi, false))
                }
                (value, _) => duck_scalar(value)?,
            };
            result.insert(name.clone(), value);
        }
        rows.push(Value::Object(result));
    }
    drop(cursor);
    if columns.is_empty() {
        columns = stmt.column_names();
    }
    drop(timer);
    Ok((columns, rows, dates.into_iter().collect()))
}
fn duck_param(v: &Value) -> Result<duckdb::types::Value> {
    use duckdb::types::Value as D;
    Ok(match v {
        Value::Null => D::Null,
        Value::Bool(b) => D::Boolean(*b),
        Value::String(s) => D::Text(s.clone()),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                D::BigInt(i)
            } else {
                D::Double(n.as_f64().ok_or_else(|| {
                    Error::new("INVALID_ARGUMENT", "Invalid numeric query parameter")
                })?)
            }
        }
        _ => {
            return Err(Error::new(
                "INVALID_ARGUMENT",
                "Query parameters must be scalar",
            ))
        }
    })
}
fn duck_scalar(v: duckdb::types::ValueRef<'_>) -> Result<Value> {
    use duckdb::types::ValueRef as D;
    let out = match v {
        D::Null => Value::Null,
        D::Boolean(b) => json!(b),
        D::TinyInt(n) => json!(n),
        D::SmallInt(n) => json!(n),
        D::Int(n) => json!(n),
        D::BigInt(n) => json!(n),
        D::HugeInt(n) => {
            let i = i64::try_from(n).map_err(|_| {
                Error::new(
                    "QUERY_SCHEMA_CHANGED",
                    "SQL integer exceeds signed 64-bit range",
                )
            })?;
            json!(i)
        }
        D::UHugeInt(n) => {
            let value = i64::try_from(n).map_err(|_| {
                Error::new(
                    "QUERY_SCHEMA_CHANGED",
                    "SQL integer exceeds signed 64-bit range",
                )
            })?;
            json!(value)
        }
        D::UTinyInt(n) => json!(n),
        D::USmallInt(n) => json!(n),
        D::UInt(n) => json!(n),
        D::UBigInt(n) => {
            require(
                n <= i64::MAX as u64,
                "SQL integer exceeds signed 64-bit range",
                "QUERY_SCHEMA_CHANGED",
            )?;
            json!(n)
        }
        D::Float(n) => {
            require(
                n.is_finite(),
                "SQL result contains a non-finite number",
                "QUERY_SCHEMA_CHANGED",
            )?;
            json!(n)
        }
        D::Double(n) => {
            require(
                n.is_finite(),
                "SQL result contains a non-finite number",
                "QUERY_SCHEMA_CHANGED",
            )?;
            json!(n)
        }
        D::Decimal(n) => json!(n
            .to_string()
            .parse::<f64>()
            .map_err(|_| Error::new("QUERY_SCHEMA_CHANGED", "Invalid decimal result"))?),
        D::Text(_) | D::Enum(..) => json!(v
            .as_str()
            .map_err(|_| Error::new("QUERY_SCHEMA_CHANGED", "Invalid text or enum result"))?),
        D::Date32(days) => {
            let date = chrono::NaiveDate::from_ymd_opt(1970, 1, 1)
                .unwrap()
                .checked_add_signed(chrono::Duration::days(days as i64))
                .ok_or_else(|| {
                    Error::new("QUERY_SCHEMA_CHANGED", "Date is outside supported range")
                })?;
            json!(date.to_string())
        }
        D::Timestamp(unit, n) => {
            let t = duck_timestamp(unit, n)?;
            json!(t.naive_utc().format("%Y-%m-%dT%H:%M:%S%.f").to_string())
        }
        D::Time64(unit, n) => {
            let us = duck_microseconds(unit, n)?;
            require(
                (0..86_400_000_000).contains(&us),
                "Invalid time result",
                "QUERY_SCHEMA_CHANGED",
            )?;
            let t = chrono::NaiveTime::from_num_seconds_from_midnight_opt(
                (us / 1_000_000) as u32,
                ((us % 1_000_000) * 1000) as u32,
            )
            .unwrap();
            json!(t.format("%H:%M:%S%.f").to_string())
        }
        _ => {
            return Err(Error::new(
                "QUERY_SCHEMA_CHANGED",
                "SQL result must contain scalar fields; cast unsupported values in the query",
            ))
        }
    };
    Ok(out)
}

fn duck_microseconds(unit: duckdb::types::TimeUnit, value: i64) -> Result<i64> {
    use duckdb::types::TimeUnit;
    let microseconds = match unit {
        TimeUnit::Second => value.checked_mul(1_000_000),
        TimeUnit::Millisecond => value.checked_mul(1_000),
        TimeUnit::Microsecond => Some(value),
        TimeUnit::Nanosecond => Some(value / 1_000),
    };
    microseconds.ok_or_else(|| {
        Error::new(
            "QUERY_SCHEMA_CHANGED",
            "Time value is outside supported range",
        )
    })
}

fn duck_timestamp(
    unit: duckdb::types::TimeUnit,
    value: i64,
) -> Result<chrono::DateTime<chrono::Utc>> {
    require(
        value != i64::MAX && value != i64::MIN,
        "Infinite timestamps are not supported",
        "QUERY_SCHEMA_CHANGED",
    )?;
    chrono::DateTime::from_timestamp_micros(duck_microseconds(unit, value)?).ok_or_else(|| {
        Error::new(
            "QUERY_SCHEMA_CHANGED",
            "Timestamp is outside supported range",
        )
    })
}

/// Validate with DuckDB's parser before using the high-level driver's prepare(),
/// which otherwise executes intermediate statements in a multi-statement input.
fn validate_duckdb_select(path: &str, sql: &str) -> Result<()> {
    use duckdb::ffi as f;
    use std::{
        ffi::{CStr, CString},
        ptr,
    };
    // DuckDB's preprocessor rewrites PRAGMA into SELECT before the C API
    // exposes its prepared statement type. Check the original command first;
    // all other syntax, including SELECT variants and CTEs, is still checked
    // by DuckDB's parser below.
    require(
        !first_sql_keyword(sql).is_some_and(|word| word.eq_ignore_ascii_case("pragma")),
        "DuckDB source requires a single SELECT query",
        "QUERY_REJECTED",
    )?;
    struct Handles {
        config: f::duckdb_config,
        db: f::duckdb_database,
        con: f::duckdb_connection,
        extracted: f::duckdb_extracted_statements,
        prepared: f::duckdb_prepared_statement,
    }
    impl Drop for Handles {
        fn drop(&mut self) {
            unsafe {
                if !self.prepared.is_null() {
                    f::duckdb_destroy_prepare(&mut self.prepared);
                }
                if !self.extracted.is_null() {
                    f::duckdb_destroy_extracted(&mut self.extracted);
                }
                if !self.con.is_null() {
                    f::duckdb_disconnect(&mut self.con);
                }
                if !self.db.is_null() {
                    f::duckdb_close(&mut self.db);
                }
                if !self.config.is_null() {
                    f::duckdb_destroy_config(&mut self.config);
                }
            }
        }
    }
    let mut h = Handles {
        config: ptr::null_mut(),
        db: ptr::null_mut(),
        con: ptr::null_mut(),
        extracted: ptr::null_mut(),
        prepared: ptr::null_mut(),
    };
    let path =
        CString::new(path).map_err(|_| Error::new("INVALID_CONFIG", "Invalid source path"))?;
    let sql =
        CString::new(sql).map_err(|_| Error::new("QUERY_REJECTED", "SQL contains a null byte"))?;
    unsafe {
        require(
            f::duckdb_create_config(&mut h.config) == f::DuckDBSuccess,
            "DuckDB configuration failed",
            "SOURCE_UNAVAILABLE",
        )?;
        for (k, v) in [
            ("access_mode", "READ_ONLY"),
            ("temp_directory", ""),
            ("autoinstall_known_extensions", "false"),
            ("autoload_known_extensions", "false"),
            ("enable_external_access", "false"),
            ("lock_configuration", "true"),
        ] {
            let setting = k;
            let k = CString::new(k).unwrap();
            let v = CString::new(v).unwrap();
            require(
                f::duckdb_set_config(h.config, k.as_ptr(), v.as_ptr()) == f::DuckDBSuccess,
                format!("DuckDB read-only configuration failed: {setting}"),
                "SOURCE_UNAVAILABLE",
            )?;
        }
        let mut error = ptr::null_mut();
        let status = f::duckdb_open_ext(path.as_ptr(), &mut h.db, h.config, &mut error);
        if !error.is_null() {
            f::duckdb_free(error.cast());
        }
        require(
            status == f::DuckDBSuccess,
            "Could not open configured DuckDB source",
            "SOURCE_UNAVAILABLE",
        )?;
        require(
            f::duckdb_connect(h.db, &mut h.con) == f::DuckDBSuccess,
            "Could not connect to configured DuckDB source",
            "SOURCE_UNAVAILABLE",
        )?;
        let count = f::duckdb_extract_statements(h.con, sql.as_ptr(), &mut h.extracted);
        require(
            count == 1,
            "DuckDB source requires a single SELECT query",
            "QUERY_REJECTED",
        )?;
        let prepared =
            f::duckdb_prepare_extracted_statement(h.con, h.extracted, 0, &mut h.prepared);
        if prepared != f::DuckDBSuccess {
            let msg = f::duckdb_prepare_error(h.prepared);
            let text = if msg.is_null() {
                "DuckDB query preparation failed".into()
            } else {
                CStr::from_ptr(msg).to_string_lossy().into_owned()
            };
            return Err(Error::new("QUERY_REJECTED", text));
        }
        require(
            f::duckdb_prepared_statement_type(h.prepared)
                == f::duckdb_statement_type_DUCKDB_STATEMENT_TYPE_SELECT,
            "DuckDB source requires a single SELECT query",
            "QUERY_REJECTED",
        )?;
    }
    Ok(())
}

fn first_sql_keyword(mut sql: &str) -> Option<&str> {
    loop {
        sql = sql.trim_start_matches(|c: char| c.is_whitespace() || c == '\u{feff}');
        if let Some(rest) = sql.strip_prefix(';') {
            sql = rest;
        } else if let Some(rest) = sql.strip_prefix("--") {
            sql = &rest[rest.find(['\r', '\n'])?..];
        } else if let Some(rest) = sql.strip_prefix("/*") {
            let bytes = rest.as_bytes();
            let mut depth = 1usize;
            let mut at = 0;
            while at + 1 < bytes.len() && depth != 0 {
                match &bytes[at..at + 2] {
                    b"/*" => {
                        depth += 1;
                        at += 2;
                    }
                    b"*/" => {
                        depth -= 1;
                        at += 2;
                    }
                    _ => at += 1,
                }
            }
            if depth != 0 {
                return None;
            }
            sql = &rest[at..];
        } else {
            let end = sql
                .bytes()
                .position(|b| !b.is_ascii_alphanumeric() && b != b'_')
                .unwrap_or(sql.len());
            return (end != 0).then_some(&sql[..end]);
        }
    }
}

pub struct LiveQueryRequest {
    pub queries: Option<QueryRunner>,
    pub manifest: Value,
    pub data: LocalData,
    pub refs: HashMap<String, Value>,
}
impl LiveQueryRequest {
    pub fn new(queries: Option<QueryRunner>, manifest: &Value) -> Result<Self> {
        Ok(Self {
            queries,
            manifest: manifest.clone(),
            data: LocalData::new(None)?,
            refs: HashMap::new(),
        })
    }
    pub fn reference(&mut self, dataset: &str) -> Result<Value> {
        if let Some(r) = self.refs.get(dataset) {
            return Ok(r.clone());
        }
        let meta = &self.manifest["datasets"][dataset];
        let q = &self.manifest["sources"][meta["sourceId"].as_str().unwrap_or("")]["query"];
        let queries = self.queries.as_ref().ok_or_else(|| {
            Error::new(
                "SOURCE_NOT_ALLOWED",
                "Live SQL source configuration is unavailable",
            )
        })?;
        let result = queries.execute(
            q["connection"].as_str().unwrap_or(""),
            q["sql"].as_str().unwrap_or(""),
            q.get("parameters"),
            5.0,
            Some(&meta["fields"]),
            q["engine"].as_str(),
        )?;
        self.add(dataset, &result.rows, &result.fields)
    }
    pub fn add(&mut self, dataset: &str, rows: &[Value], fields: &Value) -> Result<Value> {
        let reference = self.data.import_rows(rows, fields)?;
        self.refs.insert(dataset.into(), reference.clone());
        Ok(reference)
    }
}

#[cfg(test)]
#[path = "../../tests/unit/query.rs"]
mod tests;
