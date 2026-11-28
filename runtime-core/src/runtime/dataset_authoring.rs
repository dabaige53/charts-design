//! Typed, bounded native author inputs and component-independent data previews.
use super::{
    error::{require, Error, Result},
    service::Service,
};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::{collections::BTreeSet, sync::OnceLock};
const MAX_ROWS: usize = 20_000;
const MAX_BYTES: usize = 16 * 1024 * 1024;
pub fn source_id(prefix: &str, id: &str) -> Result<String> {
    super::model::check_identifier(id)?;
    let value = format!("{prefix}-{id}");
    let value = if value.len() > 80 {
        format!("{prefix}-{:x}", Sha256::digest(id.as_bytes()))
    } else {
        value
    };
    super::model::check_identifier(&value)?;
    Ok(value)
}
fn fields(value: &Value) -> Result<Value> {
    let fields = value.as_object().filter(|v| !v.is_empty()).ok_or_else(|| {
        Error::new(
            "INVALID_ARGUMENT",
            "fields must be a non-empty field metadata object",
        )
    })?;
    for (key, field) in fields {
        require(
            !key.is_empty() && key.chars().count() < 200,
            "Field names must contain 1-199 characters",
            "INVALID_ARGUMENT",
        )?;
        require(
            matches!(
                field["type"].as_str(),
                Some("string" | "number" | "date" | "boolean")
            ),
            format!("{key}: declare type as string, number, date or boolean"),
            "INVALID_ARGUMENT",
        )?;
        require(
            field.get("label").is_none_or(Value::is_string),
            format!("{key}: label must be a string"),
            "INVALID_ARGUMENT",
        )?;
    }
    Ok(value.clone())
}
fn csv_number(text: &str, explicit: bool) -> bool {
    static INFER: OnceLock<regex::Regex> = OnceLock::new();
    static EXPLICIT: OnceLock<regex::Regex> = OnceLock::new();
    if explicit {
        EXPLICIT
            .get_or_init(|| {
                regex::Regex::new(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")
                    .unwrap()
            })
            .is_match(text)
    } else {
        INFER
            .get_or_init(|| regex::Regex::new(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$").unwrap())
            .is_match(text)
    }
}
fn csv_value(text: &str, kind: Option<&str>, row: u64, key: &str) -> Result<Value> {
    if text.is_empty() {
        return Ok(Value::Null);
    }
    if matches!(kind, Some("string" | "date")) {
        return Ok(json!(text));
    }
    if kind == Some("boolean") {
        return match text.trim().to_lowercase().as_str() {
            "true" | "1" => Ok(json!(true)),
            "false" | "0" => Ok(json!(false)),
            _ => Err(Error::new(
                "INVALID_ARGUMENT",
                format!("CSV row {row}, field {key}: expected true, false, 1 or 0"),
            )),
        };
    }
    let normalized = if kind == Some("number") {
        text.trim()
    } else {
        text
    };
    if kind == Some("number") {
        require(
            csv_number(normalized, true),
            format!("CSV row {row}, field {key}: expected a number"),
            "INVALID_ARGUMENT",
        )?;
    }
    if kind == Some("number") || csv_number(normalized, false) {
        if normalized.contains(['.', 'e', 'E']) {
            let n = normalized
                .parse::<f64>()
                .map_err(|_| Error::new("INVALID_ARGUMENT", "Number out of range"))?;
            require(n.is_finite(), "Number must be finite", "INVALID_ARGUMENT")?;
            Ok(json!(n))
        } else {
            normalized.parse::<i64>().map(|n|json!(n)).map_err(|_|Error::new("INVALID_ARGUMENT",format!("CSV row {row}, field {key}: number is out of range; use a string field for identifiers")))
        }
    } else {
        Ok(json!(text))
    }
}
// csv's parser deliberately tolerates unmatched quotes; retain the previous strict contract.
fn check_quotes(text: &str) -> Result<()> {
    let mut state = 0u8;
    for character in text.chars() {
        state = match (state, character) {
            (0, '"') => 2,
            (0, ',' | '\n' | '\r') => 0,
            (0, _) => 1,
            (1, ',' | '\n' | '\r') => 0,
            (1, _) => 1,
            (2, '"') => 3,
            (2, _) => 2,
            (3, '"') => 2,
            (3, ',' | '\n' | '\r') => 0,
            (3, _) => {
                return Err(Error::new(
                    "INVALID_ARGUMENT",
                    "Invalid CSV: unexpected character after closing quote",
                ))
            }
            _ => unreachable!(),
        };
    }
    require(
        state != 2,
        "Invalid CSV: unterminated quoted field",
        "INVALID_ARGUMENT",
    )
}
pub fn parse_input(args: &Value) -> Result<(Vec<Value>, Value)> {
    require(
        args.get("rows").is_some() != args.get("csvText").is_some(),
        "Supply exactly one of rows or csvText",
        "INVALID_ARGUMENT",
    )?;
    let declared = args.get("fields").map(fields).transpose()?;
    let rows: Vec<Value> = if let Some(text) = args.get("csvText") {
        let text = text
            .as_str()
            .ok_or_else(|| {
                Error::new(
                    "INVALID_ARGUMENT",
                    "csvText must contain CSV text, not a file reference",
                )
            })?
            .trim_start_matches('\u{feff}');
        require(
            text.len() <= MAX_BYTES,
            "CSV exceeds 16 MiB",
            "PAYLOAD_TOO_LARGE",
        )?;
        check_quotes(text)?;
        let mut reader = csv::ReaderBuilder::new()
            .flexible(false)
            .from_reader(text.as_bytes());
        let header = reader.headers()?.clone();
        require(
            !header.is_empty() && header.iter().all(|v| !v.trim().is_empty()),
            "CSV needs non-empty column headers",
            "INVALID_ARGUMENT",
        )?;
        require(
            header.iter().collect::<BTreeSet<_>>().len() == header.len(),
            "CSV column headers must be unique; duplicate columns would lose data",
            "INVALID_ARGUMENT",
        )?;
        require(
            header.iter().all(|v| v.chars().count() < 200),
            "CSV column headers must contain 1-199 characters",
            "INVALID_ARGUMENT",
        )?;
        if let Some(fields) = &declared {
            require(
                header.iter().all(|k| fields.get(k).is_some()),
                "CSV contains undeclared columns; include every header in fields",
                "INVALID_ARGUMENT",
            )?;
        }
        let mut rows = Vec::new();
        for record in reader.records() {
            let record = record?;
            require(
                rows.len() < MAX_ROWS,
                "Dataset exceeds 20000 rows",
                "PAYLOAD_TOO_LARGE",
            )?;
            let line = record
                .position()
                .map_or(rows.len() as u64 + 2, |v| v.line());
            let mut row = Map::new();
            for (key, value) in header.iter().zip(record.iter()) {
                row.insert(
                    key.into(),
                    csv_value(
                        value,
                        declared.as_ref().and_then(|v| v[key]["type"].as_str()),
                        line,
                        key,
                    )?,
                );
            }
            rows.push(row.into());
        }
        rows
    } else {
        args["rows"]
            .as_array()
            .ok_or_else(|| {
                Error::new("INVALID_ARGUMENT", "rows must be an array of field objects")
            })?
            .clone()
    };
    require(
        rows.len() <= MAX_ROWS,
        "Dataset exceeds 20000 rows",
        "PAYLOAD_TOO_LARGE",
    )?;
    require(
        !rows.is_empty() || declared.is_some(),
        "Empty rows need explicit fields to define the dataset schema",
        "INVALID_ARGUMENT",
    )?;
    require(
        rows.iter().all(Value::is_object),
        "Each row must be a field object",
        "INVALID_ARGUMENT",
    )?;
    let fields = match declared {
        Some(v) => v,
        None => fields(&super::model::inferred_fields(&rows)?)?,
    };
    for (index, row) in rows.iter().enumerate() {
        for (key, value) in row.as_object().unwrap() {
            let field = fields.get(key).ok_or_else(|| {
                Error::new(
                    "INVALID_ARGUMENT",
                    format!("Row {}: contains undeclared fields", index + 1),
                )
            })?;
            let kind = field["type"].as_str().unwrap();
            let valid = value.is_null()
                || match kind {
                    "string" | "date" => value.is_string(),
                    "boolean" => value.is_boolean(),
                    "number" => {
                        value.as_i64().is_some()
                            || value.is_f64() && value.as_f64().is_some_and(f64::is_finite)
                    }
                    _ => false,
                };
            require(valid,format!("Row {}, field {key}: value does not match {kind}; use explicit fields for mixed or ambiguous input",index+1),"INVALID_ARGUMENT")?;
        }
    }
    super::serialization::json_bytes(&json!({"fields":fields,"rows":rows}))?;
    Ok((rows, fields))
}
pub fn preview(service: &Service, args: &Value, pinned: Option<&Value>) -> Result<Value> {
    let board = super::service::string(args, "dashboardId")?;
    let id = super::service::string(args, "datasetId")?;
    super::model::check_identifier(board)?;
    super::model::check_identifier(id)?;
    let offset = super::service::unsigned(args, "offset", 0)?;
    let limit = super::service::unsigned(args, "limit", 20)?;
    require(
        offset <= 9_007_199_254_740_991,
        "offset must be a safe non-negative integer",
        "INVALID_ARGUMENT",
    )?;
    require(
        (1..=100).contains(&limit),
        "limit must be an integer from 1 to 100",
        "INVALID_ARGUMENT",
    )?;
    let doc = service.reading_document(board, args, pinned)?;
    let meta = doc["manifest"]["datasets"]
        .get(id)
        .ok_or_else(|| Error::new("NOT_FOUND", format!("Dataset not found: {id}")))?;
    let live = meta["mode"] == "live";
    let reference = doc["snapshot"]["datasetRefs"].get(id);
    let mut result = if live {
        let (data, reference) = service.live_dataset(&doc, id)?;
        data.rows(&reference, &[], None, &[], offset, limit as usize, "")?
    } else if let Some(reference) = reference {
        service
            .store
            .data
            .rows(reference, &[], None, &[], offset, limit as usize, "")?
    } else {
        let rows = doc["snapshot"]["datasets"][id]
            .as_array()
            .ok_or_else(|| Error::new("DATA_INCOMPLETE", "Dataset rows are unavailable"))?;
        let start = (offset as usize).min(rows.len());
        json!({"rows":rows[start..(start+limit as usize).min(rows.len())],"totalRows":rows.len()})
    };
    let next = offset + result["rows"].as_array().map_or(0, Vec::len) as u64;
    let more = next < result["totalRows"].as_u64().unwrap_or(0);
    let extra = json!({"dashboardId":board,"datasetId":id,"revision":doc["revision"],"dataVersion":super::doctor::data_version(&doc)?,"fields":meta["fields"],"sourceId":meta["sourceId"],"mode":if live{"live"}else{"snapshot"},"transient":live,"scope":"unfiltered-dataset","filtersApplied":false,"offset":offset,"limit":limit,"hasMore":more,"nextOffset":if more{json!(next)}else{Value::Null}});
    result
        .as_object_mut()
        .unwrap()
        .extend(extra.as_object().unwrap().clone());
    if !live {
        if let Some(reference) = reference {
            result["datasetVersion"] = reference["version"].clone();
        }
    }
    Ok(result)
}
