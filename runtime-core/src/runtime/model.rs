//! Canonical document, atomic edit operations, report source and annotations.
use super::{
    error::{require, Error, Result},
    layouts, serialization, structure, validation,
};
use serde_json::{json, Map, Value};
use std::{collections::HashSet, sync::OnceLock};
pub const MAX_BYTES: usize = 16 * 1024 * 1024;
pub const MAX_ROWS: usize = 20_000;
pub const MAX_COMPONENTS: usize = 100;
pub const TYPES: [&str; 8] = [
    "bar",
    "line",
    "area",
    "pie",
    "scatter",
    "heatmap",
    "funnel",
    "waterfall",
];
pub const AGGREGATES: [&str; 7] = ["sum", "avg", "min", "max", "count", "ratio", "entity_ratio"];
pub const VIEW_MODES: [&str; 3] = ["dashboard", "report", "filtered-report"];
pub const SQL_SOURCE_ENGINES: [&str; 3] = ["sqlite", "postgresql", "duckdb"];
pub use serialization::{json_bytes, utcnow};
pub fn identifier(value: &Value, label: &str) -> Result<String> {
    let valid = value.as_str().is_some_and(|s| {
        let mut c = s.bytes();
        (1..=80).contains(&s.len())
            && c.next().is_some_and(|c| c.is_ascii_alphabetic())
            && c.all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
    });
    require(
        valid,
        format!("{label}: invalid identifier"),
        "INVALID_DOCUMENT",
    )?;
    Ok(value.as_str().unwrap().to_owned())
}
pub fn check_identifier(value: &str) -> Result<()> {
    identifier(&json!(value), "id").map(|_| ())
}
pub fn new_document(board: &str, title: &str) -> Result<Value> {
    check_identifier(board)?;
    Ok(
        json!({"schemaVersion":2,"id":board,"revision":0,"manifest":{"title":title,"theme":"light","components":{},"datasets":{},"metrics":{},"sources":{},"filters":[],"layout":{"desktop":[],"tablet":[],"mobile":[]}},"snapshot":{"status":"ready","updatedAt":utcnow(),"datasets":{}}}),
    )
}
pub fn field(meta: &Value, key: &Value, numeric: bool) -> Result<()> {
    let name = key.as_str().unwrap_or("");
    require(
        key.is_string() && meta["fields"].get(name).is_some(),
        format!("Unknown field: {key}"),
        "INVALID_DOCUMENT",
    )?;
    if numeric {
        require(
            meta["fields"][name]["type"] == "number",
            format!("Numeric field required: {name}"),
            "INVALID_DOCUMENT",
        )?;
    }
    Ok(())
}
pub fn validate(doc: &Value) -> Result<()> {
    validation::validate(doc)
}
pub fn live_datasets(doc: &Value) -> Value {
    Value::Object(
        doc["manifest"]["datasets"]
            .as_object()
            .into_iter()
            .flatten()
            .filter(|(_, v)| v["mode"] == "live")
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect(),
    )
}
pub fn inferred_fields(rows: &[Value]) -> Result<Value> {
    require(
        !rows.is_empty(),
        "Non-empty rows are needed to infer field types",
        "INVALID_DOCUMENT",
    )?;
    let mut keys = vec![];
    for row in rows {
        let row = row
            .as_object()
            .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Rows must be objects"))?;
        for key in row.keys() {
            if !keys.contains(key) {
                keys.push(key.clone());
            }
        }
    }
    let mut fields = Map::new();
    for key in keys {
        let values: Vec<_> = rows
            .iter()
            .filter_map(|r| r.get(&key))
            .filter(|v| !v.is_null())
            .collect();
        let kind = if !values.is_empty() && values.iter().all(|v| v.is_number()) {
            "number"
        } else if !values.is_empty() && values.iter().all(|v| v.is_boolean()) {
            "boolean"
        } else {
            "string"
        };
        fields.insert(key.clone(), json!({"type":kind,"label":key}));
    }
    Ok(Value::Object(fields))
}

// Unlike serde_json's default Value visitor, report fences reject duplicate keys.
struct Unique(Value);
impl<'de> serde::Deserialize<'de> for Unique {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> std::result::Result<Self, D::Error> {
        struct Visitor;
        impl<'de> serde::de::Visitor<'de> for Visitor {
            type Value = Unique;
            fn expecting(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                f.write_str("finite JSON with unique keys")
            }
            fn visit_bool<E: serde::de::Error>(self, v: bool) -> std::result::Result<Unique, E> {
                Ok(Unique(json!(v)))
            }
            fn visit_i64<E: serde::de::Error>(self, v: i64) -> std::result::Result<Unique, E> {
                Ok(Unique(json!(v)))
            }
            fn visit_u64<E: serde::de::Error>(self, v: u64) -> std::result::Result<Unique, E> {
                Ok(Unique(json!(v)))
            }
            fn visit_f64<E: serde::de::Error>(self, v: f64) -> std::result::Result<Unique, E> {
                serde_json::Number::from_f64(v)
                    .map(|v| Unique(Value::Number(v)))
                    .ok_or_else(|| E::custom("Non-finite number"))
            }
            fn visit_str<E: serde::de::Error>(self, v: &str) -> std::result::Result<Unique, E> {
                Ok(Unique(json!(v)))
            }
            fn visit_string<E: serde::de::Error>(
                self,
                v: String,
            ) -> std::result::Result<Unique, E> {
                Ok(Unique(json!(v)))
            }
            fn visit_unit<E: serde::de::Error>(self) -> std::result::Result<Unique, E> {
                Ok(Unique(Value::Null))
            }
            fn visit_none<E: serde::de::Error>(self) -> std::result::Result<Unique, E> {
                Ok(Unique(Value::Null))
            }
            fn visit_seq<A: serde::de::SeqAccess<'de>>(
                self,
                mut a: A,
            ) -> std::result::Result<Unique, A::Error> {
                let mut out = vec![];
                while let Some(v) = a.next_element::<Unique>()? {
                    out.push(v.0);
                }
                Ok(Unique(Value::Array(out)))
            }
            fn visit_map<A: serde::de::MapAccess<'de>>(
                self,
                mut a: A,
            ) -> std::result::Result<Unique, A::Error> {
                let mut out = Map::new();
                while let Some(k) = a.next_key::<String>()? {
                    if out.contains_key(&k) {
                        return Err(serde::de::Error::custom("Duplicate JSON key"));
                    }
                    let v = a.next_value::<Unique>()?;
                    out.insert(k, v.0);
                }
                Ok(Unique(Value::Object(out)))
            }
        }
        d.deserialize_any(Visitor)
    }
}
fn expand_tabs(line: &str) -> String {
    let mut out = String::new();
    let mut col = 0;
    for c in line.chars() {
        if c == '\t' {
            let count = 4 - col % 4;
            out.extend(std::iter::repeat_n(' ', count));
            col += count;
        } else {
            out.push(c);
            col += 1;
        }
    }
    out
}
pub fn report_chart_references(markdown: &str, components: Option<&Value>) -> Result<Vec<String>> {
    require(
        markdown.chars().count() <= 200_000,
        "Report markdown must contain 0-200000 characters",
        "INVALID_DOCUMENT",
    )?;
    static SYNTAX: OnceLock<(regex::Regex, regex::Regex, regex::Regex)> = OnceLock::new();
    let (fence, quote, item) = SYNTAX.get_or_init(|| {
        (
            regex::Regex::new(r"^ {0,3}(`{3,}|~{3,})(.*)$").unwrap(),
            regex::Regex::new(r"^ {0,3}> ?").unwrap(),
            regex::Regex::new(r"^( {0,3})([-+*]|[0-9]{1,9}[.)])( +)").unwrap(),
        )
    });
    let mut opened: Option<String> = None;
    let mut body: Vec<String> = vec![];
    let mut chart = false;
    let mut start = 0;
    // Zero denotes a blockquote; positive values are list indentation widths.
    let mut containers: Vec<usize> = vec![];
    let mut refs = vec![];
    for (line_number, original) in markdown.lines().enumerate() {
        let line = expand_tabs(original);
        let mut candidate = line.clone();
        if opened.is_some() && !containers.is_empty() {
            for prefix in &containers {
                let end = if *prefix == 0 {
                    quote.find(&candidate).map(|m| m.end())
                } else {
                    candidate
                        .bytes()
                        .take(*prefix)
                        .filter(|b| *b == b' ')
                        .count()
                        .eq(prefix)
                        .then_some(*prefix)
                };
                if let Some(end) = end {
                    candidate = candidate[end..].to_owned();
                } else {
                    opened = None;
                    body.clear();
                    chart = false;
                    break;
                }
            }
            if opened.is_none() {
                containers.clear();
            }
        }
        if let Some(token) = &opened {
            let indent = candidate.bytes().take_while(|b| *b == b' ').count();
            let tail = &candidate[indent..];
            let ticks = tail
                .bytes()
                .take_while(|b| *b == token.as_bytes()[0])
                .count();
            let closes = indent <= 3
                && ticks >= token.len()
                && tail[ticks..].bytes().all(|b| b == b' ' || b == b'\t');
            if !closes {
                if chart {
                    body.push(original.to_owned());
                }
                continue;
            }
            if chart {
                let value=serde_json::from_str::<Unique>(&body.join("\n")).map_err(|_|Error::new("INVALID_DOCUMENT",format!("Chart fence at line {start}: invalid JSON; use {{\"componentId\":\"trend\"}}")))?.0;
                require(value.as_object().is_some_and(|v|v.contains_key("componentId")&&v.keys().all(|k|["componentId","caption","source"].contains(&k.as_str()))),format!("Chart fence at line {start} requires componentId and permits only optional caption/source"),"INVALID_DOCUMENT")?;
                let target = identifier(&value["componentId"], "chart fence componentId")?;
                for (name, limit) in [("caption", 500), ("source", 1000)] {
                    if let Some(v) = value.get(name) {
                        require(v.as_str().is_some_and(|v|v.chars().count()<=limit),format!("Chart fence at line {start}: {name} must contain 0-{limit} characters"),"INVALID_DOCUMENT")?;
                    }
                }
                if let Some(c) = components {
                    require(c.get(&target).is_some(),format!("Chart fence refers to missing component \"{target}\"; insert an existing component ID"),"INVALID_DOCUMENT")?;
                    require(c[&target]["kind"]!="text",format!("Chart fence \"{target}\" must reference a non-text component; write narrative in Markdown"),"INVALID_DOCUMENT")?;
                }
                refs.push(target);
            }
            opened = None;
            body.clear();
            chart = false;
            containers.clear();
            continue;
        }
        candidate = line;
        let mut prefixes = vec![];
        loop {
            if let Some(q) = quote.find(&candidate) {
                prefixes.push(0);
                candidate = candidate[q.end()..].to_owned();
            } else if let Some(m) = item.captures(&candidate) {
                let padding = if m[3].len() <= 4 { m[3].len() } else { 1 };
                let width = m[1].len() + m[2].len() + padding;
                prefixes.push(width);
                candidate = candidate[width..].to_owned();
            } else {
                break;
            }
        }
        if let Some(m) = fence.captures(&candidate) {
            if m[1].starts_with('`') && m[2].contains('`') {
                continue;
            }
            opened = Some(m[1].to_owned());
            chart = m[2].trim() == "chart";
            start = line_number + 1;
            require(!chart||prefixes.is_empty(),format!("Chart fence at line {start} must be top-level; move it outside the list or blockquote"),"INVALID_DOCUMENT")?;
            containers = prefixes;
        }
    }
    require(
        opened.is_none() || !chart,
        format!("Chart fence at line {start} is not closed; add its closing fence before saving"),
        "INVALID_DOCUMENT",
    )?;
    Ok(refs)
}
pub fn validate_report(report: &Value, components: Option<&Value>) -> Result<()> {
    require(
        report.is_object(),
        "manifest.report must be an object",
        "INVALID_DOCUMENT",
    )?;
    let canonical = report.get("markdown").is_some();
    if canonical {
        let markdown = report["markdown"].as_str().ok_or_else(|| {
            Error::new(
                "INVALID_DOCUMENT",
                "Report markdown must contain 0-200000 characters",
            )
        })?;
        report_chart_references(markdown, components)?;
    }
    if canonical && report.get("subtitle").is_none() && report.get("blocks").is_none() {
        return Ok(());
    }
    require(
        report["subtitle"]
            .as_str()
            .is_some_and(|s| s.chars().count() <= 1000),
        "Report subtitle must contain 0-1000 characters",
        "INVALID_DOCUMENT",
    )?;
    let blocks = report["blocks"]
        .as_array()
        .filter(|a| a.len() <= 100)
        .ok_or_else(|| {
            Error::new(
                "INVALID_DOCUMENT",
                "Report blocks must be an array of at most 100 items",
            )
        })?;
    let mut ids = HashSet::new();
    let mut refs = HashSet::new();
    for block in blocks {
        require(
            block.is_object(),
            "Report block must be an object",
            "INVALID_DOCUMENT",
        )?;
        let key = identifier(&block["id"], "report block id")?;
        let target = identifier(&block["componentId"], "report component id")?;
        require(
            ids.insert(key),
            "Duplicate report block id",
            "INVALID_DOCUMENT",
        )?;
        require(
            refs.insert(target.clone()),
            "Duplicate report component reference",
            "INVALID_DOCUMENT",
        )?;
        if !canonical {
            if let Some(c) = components {
                require(
                    c.get(&target).is_some(),
                    "Report refers to a missing component",
                    "INVALID_DOCUMENT",
                )?;
            }
        }
    }
    Ok(())
}
pub fn report_markdown(manifest: &Value) -> Result<String> {
    let report = &manifest["report"];
    if let Some(markdown) = report.get("markdown") {
        return markdown
            .as_str()
            .map(str::to_owned)
            .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Report markdown must be text"));
    }
    fn literal(s: &str) -> String {
        s.chars()
            .flat_map(|c| {
                if c.is_ascii_punctuation() {
                    vec!['\\', c]
                } else {
                    vec![c]
                }
            })
            .collect()
    }
    let mut parts = vec![format!(
        "# {}",
        literal(
            &manifest["title"]
                .as_str()
                .unwrap_or("")
                .lines()
                .collect::<Vec<_>>()
                .join(" ")
        )
    )];
    if let Some(s) = report["subtitle"].as_str().filter(|s| !s.is_empty()) {
        parts.push(literal(s));
    }
    let blocks = if let Some(b) = report["blocks"].as_array() {
        b.clone()
    } else {
        let mut layout = manifest["layout"]["desktop"]
            .as_array()
            .cloned()
            .unwrap_or_default();
        layout.sort_by_key(|p| (p["y"].as_i64().unwrap_or(0), p["x"].as_i64().unwrap_or(0)));
        layout
            .iter()
            .map(|p| json!({"componentId":p["id"]}))
            .collect()
    };
    for block in blocks {
        let key = block["componentId"].as_str().unwrap_or("");
        let c = &manifest["components"][key];
        require(
            !c.is_null(),
            "Report refers to a missing component",
            "INVALID_DOCUMENT",
        )?;
        if c["kind"] == "text" {
            if let Some(t) = c["title"].as_str().filter(|s| !s.is_empty()) {
                parts.push(format!(
                    "## {}",
                    literal(&t.lines().collect::<Vec<_>>().join(" "))
                ));
            }
            if let Some(t) = c["subtitle"].as_str().filter(|s| !s.is_empty()) {
                parts.push(literal(t));
            }
            if let Some(t) = c["text"].as_str().filter(|s| !s.is_empty()) {
                parts.push(literal(t));
            }
        } else {
            parts.push(format!(
                "```chart\n{}\n```",
                serialization::python_json(&json!({"componentId":key}), false, false)?
            ));
        }
    }
    Ok(parts.join("\n\n") + "\n")
}
pub fn validate_annotations(notes: &Value, components: Option<&Value>) -> Result<()> {
    let notes = notes
        .as_array()
        .filter(|v| v.len() <= 100)
        .ok_or_else(|| Error::new("INVALID_DOCUMENT", "At most 100 annotations per document"))?;
    let mut ids = HashSet::new();
    for n in notes {
        require(
            n.is_object(),
            "Annotation must be an object",
            "INVALID_DOCUMENT",
        )?;
        let id = identifier(&n["id"], "annotation id")?;
        require(
            ids.insert(id),
            "Duplicate annotation id",
            "INVALID_DOCUMENT",
        )?;
        if !n["componentId"].is_null() {
            let c = identifier(&n["componentId"], "annotation component")?;
            require(
                components.is_none_or(|v| v.get(&c).is_some())
                    || n["anchor"].is_object()
                    || n["context"].is_object(),
                "Unknown annotation component",
                "INVALID_DOCUMENT",
            )?;
        }
        if let Some(a) = n.get("anchor") {
            require(
                a.is_object(),
                "Annotation anchor must be an object",
                "INVALID_DOCUMENT",
            )?;
            require(
                ["component", "text", "page"].contains(&a["scope"].as_str().unwrap_or("")),
                "Invalid annotation scope",
                "INVALID_DOCUMENT",
            )?;
            require(
                (a["scope"] == "component") != n["componentId"].is_null(),
                "Annotation scope must match component",
                "INVALID_DOCUMENT",
            )?;
            require(
                ["element", "area"].contains(&a["kind"].as_str().unwrap_or("")),
                "Invalid annotation selection",
                "INVALID_DOCUMENT",
            )?;
            require(
                a["quote"]
                    .as_str()
                    .is_some_and(|s| s.chars().count() <= 1000),
                "Invalid annotation quote",
                "INVALID_DOCUMENT",
            )?;
            if a["scope"] == "text" {
                require(
                    a["quote"].as_str().is_some_and(|s| !s.trim().is_empty()),
                    "Annotation text anchor requires quote",
                    "INVALID_DOCUMENT",
                )?;
                require(
                    a["occurrence"]
                        .as_i64()
                        .is_some_and(|n| (0..=10000).contains(&n)),
                    "Invalid annotation occurrence",
                    "INVALID_DOCUMENT",
                )?;
            }
            let r = &a["rect"];
            require(
                r.is_object(),
                "Annotation rectangle required",
                "INVALID_DOCUMENT",
            )?;
            for axis in ["x", "y", "width", "height"] {
                require(
                    r[axis]
                        .as_f64()
                        .is_some_and(|v| v.is_finite() && (0.0..=1.0).contains(&v)),
                    "Invalid annotation rectangle",
                    "INVALID_DOCUMENT",
                )?;
            }
            require(
                r["x"].as_f64().unwrap_or(0.) + r["width"].as_f64().unwrap_or(0.) <= 1.000001
                    && r["y"].as_f64().unwrap_or(0.) + r["height"].as_f64().unwrap_or(0.)
                        <= 1.000001,
                "Annotation rectangle exceeds target",
                "INVALID_DOCUMENT",
            )?;
        }
        require(
            n["text"]
                .as_str()
                .is_some_and(|s| !s.trim().is_empty() && s.chars().count() <= 4000),
            "Annotation text must contain 1-4000 characters",
            "INVALID_DOCUMENT",
        )?;
        require(
            n["createdAt"]
                .as_str()
                .is_some_and(|s| !s.is_empty() && s.chars().count() <= 100),
            "Annotation timestamp required",
            "INVALID_DOCUMENT",
        )?;
    }
    Ok(())
}
pub fn validate_component_content(value: &Value, key: &str) -> Result<()> {
    validation::validate_component_content(value, key)
}
pub fn compatibility(doc: &Value, c: &Value, kind: &str) -> Option<String> {
    let fail = |s: &str| Some(s.to_owned());
    if !TYPES.contains(&kind) {
        return fail("Unsupported chart type");
    }
    let x = c["x"].as_str().unwrap_or("");
    let series = c["series"].as_str().unwrap_or("");
    let measures = c["measures"].as_array().cloned().unwrap_or_default();
    if x.is_empty() {
        return fail("Choose an X/category field");
    }
    if ["pie", "funnel", "waterfall", "heatmap", "scatter"].contains(&kind) && measures.len() != 1 {
        return fail("This chart requires exactly one measure");
    }
    let metrics = &doc["manifest"]["metrics"];
    let units: HashSet<_> = measures
        .iter()
        .filter_map(Value::as_str)
        .map(|m| {
            (
                metrics[m]["unit"].as_str().unwrap_or(""),
                metrics[m]["format"].as_str().unwrap_or("number"),
            )
        })
        .collect();
    if units.len() > 1 {
        return fail("Mixed units require separate charts or an explicitly configured legacy dual-axis chart");
    }
    let metric = measures
        .first()
        .and_then(Value::as_str)
        .map(|id| &metrics[id])
        .unwrap_or(&Value::Null);
    if ["pie", "funnel"].contains(&kind)
        && !["sum", "count"].contains(&metric["aggregation"].as_str().unwrap_or(""))
    {
        return fail("Pie/funnel requires an additive sum or count measure");
    }
    let ds = c["datasetId"].as_str().unwrap_or("");
    if kind == "scatter" && doc["manifest"]["datasets"][ds]["fields"][x]["type"] != "number" {
        return fail("Scatter requires a numeric X field");
    }
    if kind == "heatmap" && series.is_empty() {
        return fail("Heatmap requires a second categorical field (series)");
    }
    if ["pie", "funnel", "waterfall"].contains(&kind) && !series.is_empty() {
        return fail("Remove the series grouping for this chart");
    }
    if kind == "waterfall" && (metric["semantic"] != "delta" || metric["aggregation"] != "sum") {
        return fail("Waterfall requires an additive delta metric; it is not a generic bar chart");
    }
    None
}
fn append_report_component(report: &mut Value, key: &str) -> Result<()> {
    let blocks = report["blocks"]
        .as_array_mut()
        .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Report blocks must be an array"))?;
    if blocks.iter().any(|b| b["componentId"] == key) {
        return Ok(());
    }
    let mut id = key.to_owned();
    let mut suffix = 2;
    while blocks.iter().any(|b| b["id"] == id) {
        let ending = format!("-{suffix}");
        id = format!("{}{}", &key[..key.len().min(80 - ending.len())], ending);
        suffix += 1;
    }
    blocks.push(json!({"id":id,"componentId":key}));
    Ok(())
}
pub fn apply_layout_template(m: &mut Value, template: &str, order: Option<&[Value]>) -> Result<()> {
    require(
        layouts::TEMPLATES.contains(&template),
        format!("Unknown layout template: {template}; read layout_templates for choices"),
        "UNKNOWN_LAYOUT",
    )?;
    if let Some(order) = order {
        let mut seen = HashSet::new();
        for k in order {
            let name = k.as_str().ok_or_else(|| {
                Error::new(
                    "INVALID_DOCUMENT",
                    "Layout order must be a list of unique component IDs",
                )
            })?;
            require(
                seen.insert(name),
                "Layout order must be a list of unique component IDs",
                "INVALID_DOCUMENT",
            )?;
            require(
                m["components"].get(name).is_some(),
                format!("Layout order refers to missing components: {name}"),
                "INVALID_DOCUMENT",
            )?;
        }
    }
    m["layout"] = layouts::compute_layout(m, template, order)?;
    m["layoutTemplate"] = json!({"id":template});
    if let Some(order) = order.filter(|o| !o.is_empty()) {
        m["layoutTemplate"]["order"] = json!(order);
    }
    Ok(())
}
pub fn apply_operations(doc: &Value, ops: &[Value]) -> Result<Value> {
    require(
        (1..=200).contains(&ops.len()),
        "Expected 1-200 operations",
        "INVALID_DOCUMENT",
    )?;
    let mut m = doc["manifest"].clone();
    let mut s = doc["snapshot"].clone();
    require(
        m.is_object() && s.is_object(),
        "manifest and snapshot are required",
        "INVALID_DOCUMENT",
    )?;
    let membership: HashSet<_> = m["components"]
        .as_object()
        .into_iter()
        .flatten()
        .map(|(k, _)| k.clone())
        .collect();
    let mut pending: Option<(String, Option<Vec<Value>>)> = None;
    let mut initialize_report = false;
    for op in ops {
        require(
            op.is_object(),
            "Operation must be an object",
            "INVALID_DOCUMENT",
        )?;
        let kind = op["op"].as_str().unwrap_or("");
        match kind {
            "put_source" | "put_metric" | "put_component" => {
                let key = identifier(&op["id"], "id")?;
                let collection = match kind {
                    "put_source" => "sources",
                    "put_metric" => "metrics",
                    _ => "components",
                };
                require(
                    op["value"].is_object(),
                    "Operation value must be an object",
                    "INVALID_DOCUMENT",
                )?;
                let previous = m["components"].get(&key).cloned();
                let mut value = op["value"].clone();
                if kind == "put_component" {
                    validate_component_content(&value, &key)?;
                    if previous.is_none() {
                        layouts::auto_place(&mut m, &key, &value)?;
                        if m.get("report").is_some() && m["report"].get("markdown").is_none() {
                            append_report_component(&mut m["report"], &key)?;
                        }
                    }
                    if !value["binding"].is_null() && value["binding"] != json!({}) {
                        let b = value["binding"].clone();
                        require(
                            b.is_object(),
                            "binding must be an object",
                            "INVALID_DOCUMENT",
                        )?;
                        value["datasetId"] = b["datasetId"].clone();
                        let empty = json!({});
                        let measures =
                            b.get("measures")
                                .unwrap_or(&empty)
                                .as_object()
                                .ok_or_else(|| {
                                    Error::new(
                                        "INVALID_DOCUMENT",
                                        "Binding measures must be an object",
                                    )
                                })?;
                        let mut distinct = vec![];
                        for v in measures.values() {
                            if !distinct.contains(v) {
                                distinct.push(v.clone());
                            }
                        }
                        value["measures"] = json!(distinct);
                    }
                    structure::update(previous.as_ref(), &mut value)?;
                }
                m[collection][key] = value;
            }
            "put_dataset" | "put_dataset_ref" | "put_live_dataset" => {
                let key = identifier(&op["id"], "id")?;
                m["datasets"][&key] = op["meta"].clone();
                if kind == "put_dataset" {
                    s["datasets"][&key] = op["rows"].clone();
                    if let Some(o) = s.get_mut("datasetRefs").and_then(Value::as_object_mut) {
                        o.remove(&key);
                    }
                } else {
                    if let Some(o) = s["datasets"].as_object_mut() {
                        o.remove(&key);
                    }
                    if kind == "put_dataset_ref" {
                        if s.get("datasetRefs").is_none() {
                            s["datasetRefs"] = json!({});
                        }
                        s["datasetRefs"][&key] = op["ref"].clone();
                    } else {
                        require(
                            m["datasets"][&key].is_object(),
                            "Dataset metadata must be an object",
                            "INVALID_DOCUMENT",
                        )?;
                        m["datasets"][&key]["mode"] = "live".into();
                        if let Some(o) = s.get_mut("datasetRefs").and_then(Value::as_object_mut) {
                            o.remove(&key);
                        }
                    }
                }
                s["updatedAt"] = utcnow().into();
            }
            "remove_component" => {
                let key = op["id"].as_str().unwrap_or("");
                require(
                    m["components"].get(key).is_some(),
                    "Component does not exist",
                    "INVALID_DOCUMENT",
                )?;
                if let Some(markdown) = m["report"]["markdown"].as_str() {
                    require(!report_chart_references(markdown,None)?.contains(&key.to_owned()),format!("Component \"{key}\" is referenced in report Markdown; remove its chart fence before deleting it"),"REPORT_COMPONENT_REFERENCED")?;
                }
                m["components"].as_object_mut().unwrap().remove(key);
                if let Some(a) = m.get_mut("annotations").and_then(Value::as_array_mut) {
                    a.retain(|n| n["componentId"] != key || n["anchor"].is_object());
                }
                for (bp, _) in layouts::COLS {
                    if let Some(a) = m["layout"][bp].as_array_mut() {
                        a.retain(|p| p["id"] != key);
                    }
                }
                if let Some(filters) = m["filters"].as_array_mut() {
                    for f in filters.iter_mut() {
                        if let Some(a) = f["componentIds"].as_array_mut() {
                            a.retain(|v| v != key);
                        }
                    }
                    filters.retain(|f| f["componentIds"].as_array().is_some_and(|a| !a.is_empty()));
                }
                if m["report"].get("markdown").is_none() {
                    if let Some(blocks) = m
                        .get_mut("report")
                        .and_then(|r| r.get_mut("blocks"))
                        .and_then(Value::as_array_mut)
                    {
                        blocks.retain(|b| b["componentId"] != key);
                    }
                }
            }
            "set_original_chart" => {
                let key = op["id"].as_str().unwrap_or("");
                let code = op["code"].as_str().unwrap_or("");
                require(
                    m["components"].get(key).is_some(),
                    "Chart not found",
                    "INVALID_DOCUMENT",
                )?;
                let c = &mut m["components"][key];
                require(
                    c["kind"] == "legacy" && c["family"] == "chart",
                    "Original chart required",
                    "INVALID_DOCUMENT",
                )?;
                require(
                    c["config"]["renderer"].as_str().unwrap_or("preset") == "preset",
                    "Custom renderers are edited through put_component, not preset switching",
                    "INCOMPATIBLE_CHART",
                )?;
                let current = c["config"]["code"].as_str().unwrap_or("").to_owned();
                require(
                    ["c01", "c02"].contains(&current.as_str()) && ["c01", "c02"].contains(&code),
                    "No reviewed conversion between these original codes",
                    "INCOMPATIBLE_CHART",
                )?;
                if current != code {
                    structure::invalidate(c);
                    c["config"]["code"] = json!(code);
                    let axes = &mut c["config"]["presentation"]["axisLabels"];
                    let x = axes["x"].clone();
                    axes["x"] = axes["y"].clone();
                    axes["y"] = x;
                }
            }
            "set_chart" => {
                let key = op["id"].as_str().unwrap_or("");
                require(
                    m["components"][key]["kind"] == "chart",
                    "Chart not found",
                    "INVALID_DOCUMENT",
                )?;
                let c = &mut m["components"][key];
                if c["chartType"] != op["chartType"] {
                    structure::invalidate(c);
                    c["chartType"] = op["chartType"].clone();
                }
            }
            "set_layout" => {
                let bp = op["breakpoint"].as_str().unwrap_or("desktop");
                require(
                    layouts::COLS.iter().any(|(b, _)| *b == bp),
                    "Unknown breakpoint",
                    "INVALID_DOCUMENT",
                )?;
                m["layout"][bp] = op["value"].clone();
                m.as_object_mut().unwrap().remove("layoutTemplate");
                pending = None;
            }
            "apply_layout_template" => {
                let template = op["template"].as_str().unwrap_or("").to_owned();
                let order = if let Some(v) = op.get("order") {
                    Some(
                        v.as_array()
                            .ok_or_else(|| {
                                Error::new(
                                    "INVALID_DOCUMENT",
                                    "Layout order must be a list of unique component IDs",
                                )
                            })?
                            .clone(),
                    )
                } else {
                    None
                };
                pending = Some((template, order));
            }
            "set_title" | "set_theme" | "set_filters" | "set_meta" | "set_annotations" => {
                m[&kind[4..]] = op["value"].clone();
            }
            "set_view_mode" => {
                let value = op["value"].as_str().unwrap_or("");
                require(
                    VIEW_MODES.contains(&value),
                    "Unknown view mode",
                    "INVALID_DOCUMENT",
                )?;
                m["viewMode"] = op["value"].clone();
                if ["report", "filtered-report"].contains(&value)
                    && m["report"].get("markdown").is_none()
                {
                    initialize_report = true;
                }
            }
            "set_report_markdown" => {
                let markdown = op["value"].as_str().ok_or_else(|| {
                    Error::new(
                        "INVALID_DOCUMENT",
                        "Report markdown must contain 0-200000 characters",
                    )
                })?;
                report_chart_references(markdown, None)?;
                if m.get("report").is_none() {
                    m["report"] = json!({});
                }
                m["report"]["markdown"] = op["value"].clone();
            }
            "set_report" => {
                validate_report(&op["value"], None)?;
                m["report"] = op["value"].clone();
            }
            "set_status" => s["status"] = op["value"].clone(),
            "set_data_mode" => {
                require(
                    ["local", "snapshot"].contains(&op["value"].as_str().unwrap_or("")),
                    "Data mode must be local or snapshot",
                    "INVALID_DOCUMENT",
                )?;
                s["localMode"] = json!(op["value"] == "local");
            }
            _ => {
                return Err(Error::new(
                    "UNKNOWN_OPERATION",
                    format!("Unsupported operation: {kind}"),
                ))
            }
        }
    }
    if let Some((template, order)) = pending {
        apply_layout_template(&mut m, &template, order.as_deref())?;
    } else if let Some(saved) = m.get("layoutTemplate").cloned() {
        let current: HashSet<_> = m["components"]
            .as_object()
            .into_iter()
            .flatten()
            .map(|(k, _)| k.clone())
            .collect();
        if current != membership {
            let order: Vec<_> = saved["order"]
                .as_array()
                .into_iter()
                .flatten()
                .filter(|v| v.as_str().is_some_and(|k| current.contains(k)))
                .cloned()
                .collect();
            apply_layout_template(
                &mut m,
                saved["id"].as_str().unwrap_or(""),
                if order.is_empty() { None } else { Some(&order) },
            )?;
        }
    }
    if initialize_report && m["report"].get("markdown").is_none() {
        if let Some(report) = m.get("report") {
            validate_report(report, Some(&m["components"]))?;
        }
        let markdown = report_markdown(&m)?;
        if m.get("report").is_none() {
            m["report"] = json!({});
        }
        m["report"]["markdown"] = json!(markdown);
    }
    let mut result = doc.clone();
    result["manifest"] = m;
    result["snapshot"] = s;
    validate(&result)?;
    Ok(result)
}

#[cfg(test)]
#[path = "../../tests/unit/model_existing.rs"]
mod tests;
