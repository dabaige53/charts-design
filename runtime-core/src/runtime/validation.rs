//! Complete native document, renderer and binding invariants.
use super::{
    error::{require, Error, Result},
    layouts, model, structure,
};
use serde_json::{json, Value};
use std::collections::HashSet;
#[path = "validation_charts.rs"]
mod charts;
fn need(v: bool, message: impl Into<String>) -> Result<()> {
    require(v, message, "INVALID_DOCUMENT")
}
fn object<'a>(v: &'a Value, message: &str) -> Result<&'a serde_json::Map<String, Value>> {
    v.as_object()
        .ok_or_else(|| Error::new("INVALID_DOCUMENT", message))
}
fn optional<'a>(v: &'a Value, key: &str, default: &'a Value) -> &'a Value {
    v.get(key).unwrap_or(default)
}
fn choice(v: &Value, key: &str, default: &str, choices: &[&str]) -> bool {
    v.get(key).map_or(choices.contains(&default), |v| {
        v.as_str().is_some_and(|s| choices.contains(&s))
    })
}
fn num(v: &Value) -> bool {
    v.as_f64().is_some_and(f64::is_finite)
}
fn integer(v: &Value) -> bool {
    v.is_i64() || v.is_u64()
}
fn truth(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(v) => *v,
        Value::Number(n) => n.as_f64() != Some(0.),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}
fn string_len(v: &Value, min: usize, max: usize) -> bool {
    v.as_str()
        .is_some_and(|s| (min..=max).contains(&s.chars().count()))
}
pub fn validate_component_content(c: &Value, key: &str) -> Result<()> {
    if c["kind"] == "kpi" || (c["kind"] == "legacy" && c["family"] == "kpi") {
        let mut errors = charts::kpi_content(c, &format!("components.{key}"));
        for n in ["config", "presentation"] {
            if c[n].is_object() {
                errors.extend(charts::kpi_content(&c[n], &format!("components.{key}.{n}")));
            }
        }
        require(
            errors.is_empty(),
            json!(errors).to_string(),
            "KPI_DESCRIPTION_NOT_ALLOWED",
        )?;
    }
    Ok(())
}
pub fn validate_comparisons(c: &Value, path: &str) -> Result<()> {
    let errors = charts::kpi_comparisons(c, path);
    require(
        errors.is_empty(),
        format!("KPI comparison contract: {}", json!(errors)),
        "KPI_COMPARISON_INVALID",
    )
}
pub fn validate_original(c: &Value) -> Result<()> {
    let config = &c["config"];
    need(
        config.is_object(),
        "Original component requires a config object",
    )?;
    let family = c
        .get("family")
        .map_or("chart", |v| v.as_str().unwrap_or(""));
    need(
        ["chart", "kpi", "table"].contains(&family),
        "Unknown original component family",
    )?;
    match family {
        "chart" => {
            let errors = charts::chart_renderer(config, "config");
            require(
                errors.is_empty(),
                format!("Chart renderer contract: {}", json!(errors)),
                "CHART_RENDERER_INVALID",
            )?;
            need(
                config.get("echarts").is_none_or(Value::is_object),
                "config.echarts must be an ECharts option object",
            )?;
            if config["renderer"].as_str().unwrap_or("preset") != "preset" {
                require(
                    !truth(&c["binding"]),
                    "Custom renderers use explicit data; preset bindings require renderer=preset",
                    "CUSTOM_BINDING_UNSUPPORTED",
                )?;
                require(!truth(&c["datasetId"])&&!truth(&c["measures"]),"Custom renderers require explicit config.data and config.table; dataset computation is not inferred","CUSTOM_BINDING_UNSUPPORTED")?;
                return Ok(());
            }
            need(
                config["data"].is_object() && config["presentation"].is_object(),
                "Original charts need explicit data and presentation",
            )?;
            if config.get("encoding").is_some() {
                validate_encoding(c)?;
            } else {
                let errors = charts::chart_data(
                    &config["data"],
                    "config.data",
                    config["code"].as_str().unwrap_or(""),
                    &config["presentation"],
                );
                need(
                    errors.is_empty(),
                    format!("Original chart contract: {}", json!(errors)),
                )?;
            }
        }
        "kpi" => {
            validate_comparisons(config, "config")?;
            let kind = config
                .get("type")
                .map_or("mc01", |v| v.as_str().unwrap_or(""));
            need(
                (1..=16).any(|n| kind == format!("mc{n:02}")),
                "Unknown original KPI type",
            )?;
            need(config["label"].is_string(), "Original KPI requires a label")?;
            need(
                config.get("value").is_some()
                    || (kind == "mc06"
                        && config.get("leftVal").is_some()
                        && config.get("rightVal").is_some())
                    || (kind == "mc15" && config["items"].is_array()),
                "Original KPI requires explicit values",
            )?;
            if kind == "mc03" {
                need(
                    config
                        .get("sparkData")
                        .or_else(|| config.get("sparkline"))
                        .is_some_and(Value::is_array),
                    "Sparkline needs explicit sparkData, never preview defaults",
                )?;
            }
            if ["mc10", "mc11", "mc12", "mc13", "mc14", "mc15", "mc16"].contains(&kind) {
                let b = &c["binding"];
                let mut provided: HashSet<String> = b["measures"]
                    .as_object()
                    .into_iter()
                    .flatten()
                    .map(|(k, _)| k.clone())
                    .collect();
                if truth(&b["timeField"]) {
                    provided.extend(["sparkMonths".into(), "sparkData".into()]);
                }
                let errors: Vec<_> = charts::kpi_presentation(config, "config")
                    .into_iter()
                    .filter(|e| {
                        !e["path"]
                            .as_str()
                            .and_then(|s| s.split('.').nth(1))
                            .map(|s| s.split('[').next().unwrap_or(s))
                            .is_some_and(|f| provided.contains(f))
                    })
                    .collect();
                need(
                    errors.is_empty(),
                    format!("Original KPI contract: {}", json!(errors)),
                )?;
            }
        }
        "table" => {
            need(
                config["columns"].is_array() && config["rows"].is_array(),
                "Original table requires columns and rows",
            )?;
            let mut names = HashSet::new();
            need(
                config["columns"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .all(|v| v["key"].as_str().is_some_and(|k| names.insert(k))),
                "Table columns require unique keys",
            )?;
        }
        _ => unreachable!(),
    }
    Ok(())
}
pub fn validate_encoding(c: &Value) -> Result<()> {
    let e = &c["config"]["encoding"];
    let values = object(e, "encoding must be an object")?;
    let allowed = [
        "orientation",
        "stacked",
        "symbolSize",
        "colors",
        "tooltip",
        "colorBy",
        "sizeBy",
        "showLabels",
        "topSeries",
        "pinnedSeries",
        "visibleCount",
        "barWidth",
        "adjustableBarWidth",
        "emptyText",
        "otherSeriesLabel",
        "seriesRanking",
        "categoryOrder",
        "seriesOrder",
    ];
    need(
        values.keys().all(|k| allowed.contains(&k.as_str())),
        "Unknown encoding option; consult chart_declarations",
    )?;
    need(
        ["r02", "c03", "r03", "k01", "f02"].contains(&c["config"]["code"].as_str().unwrap_or("")),
        "Unsupported dynamic encoding code",
    )?;
    for key in ["categoryOrder", "seriesOrder"] {
        if let Some(v) = e.get(key) {
            let mut seen = HashSet::new();
            need(
                v.as_array()
                    .is_some_and(|a| a.iter().all(|v| v.as_str().is_some_and(|s| seen.insert(s)))),
                format!("{key} must contain unique strings"),
            )?;
        }
    }
    need(truth(&c["binding"]), "encoding requires a dataset binding")?;
    need(
        choice(e, "orientation", "vertical", &["horizontal", "vertical"]),
        "Invalid orientation",
    )?;
    for key in ["stacked", "adjustableBarWidth", "showLabels"] {
        need(
            e.get(key).is_none_or(Value::is_boolean),
            format!("{key} must be boolean"),
        )?;
    }
    need(
        e.get("symbolSize")
            .is_none_or(|v| v.as_f64().is_some_and(|n| (1.0..=100.0).contains(&n))),
        "symbolSize must be 1–100",
    )?;
    for key in ["tooltip", "pinnedSeries"] {
        need(
            e.get(key)
                .is_none_or(|v| v.as_array().is_some_and(|a| a.iter().all(Value::is_string))),
            format!("{key} must be an array of strings"),
        )?;
    }
    for (key, max) in [("topSeries", 100), ("visibleCount", 200), ("barWidth", 60)] {
        need(
            e.get(key)
                .is_none_or(|v| v.as_i64().is_some_and(|n| (1..=max).contains(&n))),
            format!("{key} must be 1–{max}"),
        )?;
    }
    for key in ["emptyText", "otherSeriesLabel"] {
        need(
            e.get(key).is_none_or(Value::is_string),
            format!("{key} must be text"),
        )?;
    }
    need(
        choice(e, "seriesRanking", "global", &["global", "category"]),
        "seriesRanking must be global or category",
    )?;
    need(
        e.get("colors").is_none_or(|v| {
            v.as_object()
                .is_some_and(|o| o.values().all(Value::is_string))
        }),
        "colors maps categories to CSS colors",
    )?;
    Ok(())
}
fn validate_encoding_binding(doc: &Value, c: &Value) -> Result<()> {
    let b = &c["binding"];
    let e = &c["config"]["encoding"];
    let ds = b["datasetId"].as_str().unwrap_or("");
    let meta = &doc["manifest"]["datasets"][ds];
    need(
        !truth(&b["scale"]),
        "Dynamic encoding uses metric units directly; remove binding.scale",
    )?;
    model::field(meta, &b["categoryField"], false)?;
    let measures = object(
        &b["measures"],
        "Binding measures must map target names to metric IDs",
    )?;
    let code = c["config"]["code"].as_str().unwrap_or("");
    let expected = if code == "r02" {
        vec!["x", "y"]
    } else {
        vec!["value"]
    };
    need(
        expected.iter().all(|k| measures.contains_key(*k)),
        format!("encoding requires measures: {}", expected.join(", ")),
    )?;
    if ["c03", "r03", "f02"].contains(&code) {
        model::field(meta, &b["seriesField"], false)?;
        need(
            b["categoryField"] != b["seriesField"],
            "Category and series must be different fields",
        )?;
        need(
            !truth(&e["colorBy"]) && !truth(&e["sizeBy"]),
            "c03 uses series colors and does not support sizeBy",
        )?;
        if truth(&e["stacked"]) {
            let id = b["measures"]["value"].as_str().unwrap_or("");
            need(
                ["sum", "count"].contains(
                    &doc["manifest"]["metrics"][id]["aggregation"]
                        .as_str()
                        .unwrap_or(""),
                ),
                "Stacked bars require an additive sum/count metric",
            )?;
        }
    }
    need(
        !truth(&b["timeGrain"]),
        "encoding does not yet support timeGrain; use date categories",
    )?;
    let empty = json!({});
    let attrs = object(
        optional(b, "attributes", &empty),
        "attributes must map names to field aggregation declarations",
    )?;
    for (key, spec) in attrs {
        need(
            !measures.contains_key(key) && spec.is_object(),
            "Attributes must have distinct names",
        )?;
        model::field(meta, &spec["field"], false)?;
        need(
            ["unique", "min", "max"].contains(&spec["aggregation"].as_str().unwrap_or("")),
            "Attribute aggregation must be unique/min/max",
        )?;
        if spec["aggregation"] != "unique" {
            model::field(meta, &spec["field"], true)?;
        }
    }
    let available = |k: &Value| {
        k.as_str()
            .is_some_and(|k| measures.contains_key(k) || attrs.contains_key(k))
    };
    need(
        e["tooltip"].as_array().into_iter().flatten().all(available),
        "Tooltip keys must be bound measures or attributes",
    )?;
    need(
        !truth(&e["colorBy"]) || available(&e["colorBy"]),
        "colorBy must be a bound key",
    )?;
    need(
        !truth(&e["sizeBy"])
            || e["sizeBy"]
                .as_str()
                .is_some_and(|k| measures.contains_key(k)),
        "sizeBy must be a bound measure",
    )?;
    if truth(&b["orderBy"]) {
        need(
            b["orderBy"]["target"]
                .as_str()
                .is_some_and(|s| measures.contains_key(s))
                && ["asc", "desc"].contains(&b["orderBy"]["direction"].as_str().unwrap_or("")),
            "Invalid binding orderBy",
        )?;
    }
    Ok(())
}
pub fn validate_binding(doc: &Value, c: &Value) -> Result<()> {
    let b = &c["binding"];
    need(b.is_object(), "binding must be an object")?;
    let m = &doc["manifest"];
    let ds = b["datasetId"].as_str().unwrap_or("");
    need(m["datasets"].get(ds).is_some(), "Binding dataset not found")?;
    need(
        c["datasetId"] == b["datasetId"],
        "Binding and component datasets must match",
    )?;
    let family = c["family"].as_str().unwrap_or("chart");
    let config = &c["config"];
    let empty = json!({});
    let measures = object(
        optional(b, "measures", &empty),
        "Binding measures must map target names to metric IDs",
    )?;
    for mid in measures.values() {
        let id = mid.as_str().unwrap_or("");
        need(
            mid.is_string() && m["metrics"].get(id).is_some(),
            "Binding references an unknown metric",
        )?;
        need(
            m["metrics"][id]["datasetId"] == ds,
            "Binding metrics must share its dataset",
        )?;
    }
    let scale = object(
        optional(b, "scale", &empty),
        "Binding scale targets must be measures",
    )?;
    need(
        scale.keys().all(|k| measures.contains_key(k)),
        "Binding scale targets must be measures",
    )?;
    need(
        scale
            .values()
            .all(|v| v.as_f64().is_some_and(|n| n.is_finite() && n > 0.)),
        "Binding scales must be positive finite numbers",
    )?;
    if family == "chart" && config.get("encoding").is_some() {
        return validate_encoding_binding(doc, c);
    }
    if family == "chart" {
        let code = config["code"].as_str().unwrap_or("");
        let (category, series): (&str, &[&str]) = match code {
            "c01" | "c02" => ("categories", &["values"]),
            "c03" => ("clusters", &["budget", "actual"]),
            "c04" => ("fleets", &["deviations"]),
            "c06" => ("hubs", &["offSeason", "peakSeason"]),
            "c07" => ("clusters", &["base2024", "curr2025"]),
            "c08" => ("categories", &["domestic", "intl"]),
            "d01" => ("brackets", &["counts"]),
            "t01" => ("months", &["rpk"]),
            "t02" => ("quarters", &["actual", "forecast"]),
            "t04" => ("quarters", &["premium", "economy", "cargo", "ancillary"]),
            "fn02" => ("quarters", &["revenue", "cost"]),
            "fn03" => ("variables", &["negative", "positive"]),
            "t06" => ("categories", &["revenue", "yieldGrowth"]),
            "r02" => ("clusters", &["x", "y", "size"]),
            _ => {
                return Err(Error::new(
                    "BINDING_TRANSFORM_REQUIRED",
                    "This original shape needs a dedicated reviewed data transform",
                ))
            }
        };
        need(
            b["categoryTarget"] == category,
            "Wrong category target for the original chart",
        )?;
        need(
            measures.len() == series.len() && series.iter().all(|k| measures.contains_key(*k)),
            "Bind every required series; stale snapshot series are not allowed",
        )?;
        model::field(&m["datasets"][ds], &b["categoryField"], false)?;
        let category = b["categoryField"].as_str().unwrap_or("");
        if code == "r02" {
            need(
                m["datasets"][ds]["fields"][category]["type"] == "string",
                "Bubble grouping field must be a string identifier",
            )?;
            need(
                !truth(&b["timeGrain"]),
                "Bubble grouping does not support time granularity",
            )?;
        }
        if truth(&b["orderBy"]) {
            need(
                b["orderBy"]["target"]
                    .as_str()
                    .is_some_and(|k| measures.contains_key(k)),
                "Binding sort target must be a bound measure",
            )?;
            need(
                ["asc", "desc"].contains(&b["orderBy"]["direction"].as_str().unwrap_or("")),
                "Binding sort direction must be asc or desc",
            )?;
        }
        if truth(&b["timeGrain"]) {
            need(
                m["datasets"][ds]["fields"][category]["type"] == "date",
                "Monthly/quarterly binding requires a date field",
            )?;
        }
    } else if family == "kpi" {
        let targets = [
            "value",
            "leftVal",
            "rightVal",
            "subVal",
            "yoy",
            "mom",
            "percent",
            "actual",
            "target",
            "currentValue",
            "priorValue",
        ];
        need(
            measures.keys().all(|k| targets.contains(&k.as_str())),
            "Unknown KPI binding target",
        )?;
        let required = if config["type"] == "mc06" {
            vec!["leftVal", "rightVal"]
        } else {
            vec!["value"]
        };
        need(
            required.iter().all(|k| measures.contains_key(*k)),
            "Bind each KPI headline value",
        )?;
        require(!["mc07","mc08","mc09","mc10","mc15"].contains(&config["type"].as_str().unwrap_or("mc01")),"Ranking/threshold/breakdown/distribution/list KPI requires a dedicated reviewed transform","BINDING_TRANSFORM_REQUIRED")?;
        if let Some(comparisons) = b.get("comparisons") {
            for (target, c) in object(comparisons, "Comparisons must be an object")? {
                need(
                    ["yoy", "mom"].contains(&target.as_str()) && c.is_object(),
                    "Comparisons target yoy/mom",
                )?;
                need(
                    c["current"]
                        .as_str()
                        .is_some_and(|s| measures.contains_key(s))
                        && c["baseline"]
                            .as_str()
                            .is_some_and(|s| measures.contains_key(s)),
                    "Comparison requires bound current and baseline values",
                )?;
                need(
                    choice(c, "mode", "relative", &["relative"]),
                    "Only relative comparison is supported",
                )?;
            }
        }
        if ["mc03", "mc12"].contains(&config["type"].as_str().unwrap_or("")) {
            model::field(&m["datasets"][ds], &b["timeField"], false)?;
        }
    } else if family == "table" {
        need(
            measures.is_empty(),
            "Table bindings consume rows, not aggregate measures",
        )?;
        for col in config["columns"].as_array().into_iter().flatten() {
            model::field(&m["datasets"][ds], &col["key"], false)?;
        }
    }
    Ok(())
}

pub fn validate(doc: &Value) -> Result<()> {
    model::json_bytes(doc)?;
    need(
        doc.is_object() && doc["schemaVersion"] == 2,
        "schemaVersion must be 2",
    )?;
    model::identifier(&doc["id"], "dashboard id")?;
    need(
        integer(&doc["revision"]) && doc["revision"].as_i64().is_some_and(|r| r >= 0),
        "Invalid revision",
    )?;
    let m = &doc["manifest"];
    let s = &doc["snapshot"];
    need(
        m.is_object() && s.is_object(),
        "manifest and snapshot are required",
    )?;
    need(
        string_len(&m["title"], 1, 240),
        "Title must contain 1-240 characters",
    )?;
    let empty = json!({});
    let empty_array = json!([]);
    let metadata = object(
        optional(m, "meta", &empty),
        "manifest.meta must be an object",
    )?;
    need(
        metadata
            .keys()
            .all(|k| ["subtitle", "org", "system", "statusText", "iconKey"].contains(&k.as_str())),
        "Unknown page metadata field",
    )?;
    for (k, v) in metadata {
        need(
            string_len(v, 0, 1000),
            format!("meta.{k} must contain 0-1000 characters"),
        )?;
    }
    need(
        choice(
            optional(m, "meta", &empty),
            "iconKey",
            "chart",
            &["chart", "plane"],
        ),
        "Page iconKey must be chart or plane",
    )?;
    need(
        ["light", "dark"].contains(&m["theme"].as_str().unwrap_or("")),
        "Unknown theme",
    )?;
    need(
        choice(m, "viewMode", "dashboard", &model::VIEW_MODES),
        "Unknown view mode",
    )?;
    for name in ["components", "datasets", "metrics", "sources", "layout"] {
        need(
            m[name].is_object(),
            format!("manifest.{name} must be an object"),
        )?;
    }
    let datasets = m["datasets"].as_object().unwrap();
    let components = m["components"].as_object().unwrap();
    let metrics = m["metrics"].as_object().unwrap();
    let sources = m["sources"].as_object().unwrap();
    let rows = object(&s["datasets"], "snapshot.datasets must be an object")?;
    need(
        ["ready", "partial", "blocked", "fixture"].contains(&s["status"].as_str().unwrap_or("")),
        "Unknown snapshot status",
    )?;
    need(s["updatedAt"].is_string(), "Snapshot timestamp is required")?;
    let refs = object(
        optional(s, "datasetRefs", &empty),
        "snapshot.datasetRefs must be an object",
    )?;
    let table_refs = object(
        optional(s, "componentDataRefs", &empty),
        "snapshot.componentDataRefs must be an object",
    )?;
    need(
        !refs.keys().any(|k| rows.contains_key(k)),
        "Dataset must have either rows or a local version, not both",
    )?;
    let live: HashSet<_> = datasets
        .iter()
        .filter(|(_, v)| v["mode"] == "live")
        .map(|(k, _)| k.as_str())
        .collect();
    need(
        !live
            .iter()
            .any(|k| rows.contains_key(*k) || refs.contains_key(*k)),
        "Live datasets cannot have snapshot rows or a local version",
    )?;
    let all: HashSet<_> = rows
        .keys()
        .chain(refs.keys())
        .map(String::as_str)
        .chain(live.iter().copied())
        .collect();
    need(
        all.len() == datasets.len() && datasets.keys().all(|k| all.contains(k.as_str())),
        "Dataset metadata and snapshot ids must match",
    )?;
    for key in table_refs.keys() {
        let c = &m["components"][key];
        need(
            c["kind"] == "legacy" && c["family"] == "table" && !truth(&c["binding"]),
            "Component data references belong to unbound original tables",
        )?;
    }
    for r in refs.values().chain(table_refs.values()) {
        need(
            r.is_object()
                && r["version"].as_str().is_some_and(|v| {
                    v.len() == 64
                        && v.bytes()
                            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
                }),
            "Local data version must be a content hash",
        )?;
        need(
            integer(&r["rowCount"]) && r["rowCount"].as_u64().is_some(),
            "Local data row count is required",
        )?;
    }
    need(
        components.len() <= model::MAX_COMPONENTS,
        "Too many components",
    )?;
    for (key, source) in sources {
        model::check_identifier(key)?;
        need(
            source.is_object()
                && ["query", "file", "fixture", "declared"]
                    .contains(&source["kind"].as_str().unwrap_or("")),
            "Source kind is required",
        )?;
        if source["kind"] == "query" {
            let q = &source["query"];
            need(
                q.is_object() && q["sql"].as_str().is_some_and(|s| !s.trim().is_empty()),
                "Query source needs actual SQL",
            )?;
            need(
                q["executedAt"].is_string() && truth(&q["engine"]) && truth(&q["id"]),
                "Query execution provenance is incomplete",
            )?;
        }
    }
    let mut total_rows = 0;
    for (key, meta) in datasets {
        model::check_identifier(key)?;
        need(
            meta.is_object() && meta["fields"].as_object().is_some_and(|o| !o.is_empty()),
            format!("{key}: field metadata required"),
        )?;
        let source_id = meta["sourceId"].as_str().unwrap_or("");
        need(
            sources.contains_key(source_id),
            format!("{key}: sourceId is required"),
        )?;
        let fields = meta["fields"].as_object().unwrap();
        for (name, info) in fields {
            need(
                (1..200).contains(&name.chars().count()),
                "Invalid field name",
            )?;
            need(
                info.is_object()
                    && ["string", "number", "boolean", "date"]
                        .contains(&info["type"].as_str().unwrap_or("")),
                format!("{name}: invalid field type"),
            )?;
        }
        if live.contains(key.as_str()) {
            let source = &m["sources"][source_id];
            need(
                source["kind"] == "query"
                    && source["verification"] == "runtime-executed"
                    && model::SQL_SOURCE_ENGINES
                        .contains(&source["query"]["engine"].as_str().unwrap_or(""))
                    && source["query"]["connection"].is_string(),
                format!("{key}: live data requires a registered SQL query"),
            )?;
            continue;
        }
        if let Some(r) = refs.get(key) {
            need(
                r["fields"] == meta["fields"],
                format!("{key}: local version fields must match dataset metadata"),
            )?;
            continue;
        }
        let rows = rows[key].as_array().ok_or_else(|| {
            Error::new("INVALID_DOCUMENT", format!("{key}: rows must be an array"))
        })?;
        total_rows += rows.len();
        for row in rows {
            let row = object(row, &format!("{key}: undeclared row field"))?;
            need(
                row.keys().all(|k| fields.contains_key(k)),
                format!("{key}: undeclared row field"),
            )?;
            for (name, v) in row {
                let kind = fields[name]["type"].as_str().unwrap_or("");
                let valid = v.is_null()
                    || match kind {
                        "number" => num(v),
                        "string" | "date" => v.is_string(),
                        "boolean" => v.is_boolean(),
                        _ => false,
                    };
                need(valid, format!("{key}.{name}: value does not match {kind}"))?;
            }
        }
    }
    require(
        total_rows <= model::MAX_ROWS,
        format!("Snapshot exceeds {} rows", model::MAX_ROWS),
        "PAYLOAD_TOO_LARGE",
    )?;
    for (key, metric) in metrics {
        model::check_identifier(key)?;
        need(
            metric.is_object(),
            format!("{key}: metric must be an object"),
        )?;
        let ds = metric["datasetId"].as_str().unwrap_or("");
        need(
            datasets.contains_key(ds),
            format!("{key}: unknown metric dataset"),
        )?;
        let agg = metric["aggregation"].as_str().unwrap_or("");
        need(
            model::AGGREGATES.contains(&agg),
            format!("{key}: unsupported aggregation"),
        )?;
        need(
            metric["label"].as_str().is_some_and(|s| !s.is_empty()),
            format!("{key}: label required"),
        )?;
        need(
            metric["definition"].as_str().is_some_and(|s| !s.is_empty()),
            format!("{key}: business definition required"),
        )?;
        need(
            metric["unit"].is_string(),
            format!("{key}: explicit unit required (empty string allowed)"),
        )?;
        need(
            choice(
                metric,
                "format",
                "number",
                &["number", "percent", "currency"],
            ),
            "Invalid metric format",
        )?;
        if metric["format"] == "percent" {
            need(
                metric["scale"] == "fraction",
                "Percent metrics must declare fractional scale",
            )?;
        }
        need(
            choice(metric, "status", "unverified", &["unverified", "reviewed"]),
            "Unsupported metric status",
        )?;
        need(
            metric
                .get("decimals")
                .is_none_or(|v| v.as_i64().is_some_and(|n| (0..=6).contains(&n))),
            format!("{key}: decimals must be an integer 0-6"),
        )?;
        if ["ratio", "entity_ratio"].contains(&agg) {
            model::field(&datasets[ds], &metric["numerator"], true)?;
            model::field(&datasets[ds], &metric["denominator"], true)?;
            if agg == "entity_ratio" {
                model::field(&datasets[ds], &metric["entityField"], false)?;
            }
        } else if agg != "count" {
            model::field(&datasets[ds], &metric["field"], true)?;
        }
    }
    need(
        components
            .values()
            .filter(|c| c["kind"] == "statistical")
            .count()
            <= 10,
        "At most 10 statistical components per document",
    )?;
    for (key, c) in components {
        model::check_identifier(key)?;
        let kind = c["kind"].as_str().unwrap_or("");
        need(
            c.is_object()
                && ["chart", "kpi", "table", "text", "legacy", "statistical"].contains(&kind),
            format!("{key}: invalid component kind"),
        )?;
        structure::validate(c)?;
        need(
            string_len(&c["title"], 0, 240),
            format!("{key}: title required"),
        )?;
        need(
            c.get("subtitle").is_none_or(|v| string_len(v, 0, 1000)),
            format!("{key}: subtitle must contain 0-1000 characters"),
        )?;
        let p = if kind == "legacy" {
            optional(c, "config", &empty)
        } else {
            optional(c, "presentation", &empty)
        };
        need(p.is_object(), "Presentation must be an object")?;
        let calculations = object(
            optional(p, "calculatedColumns", &empty),
            "calculatedColumns must be an object",
        )?;
        let ds = c["datasetId"].as_str().unwrap_or("");
        if !calculations.is_empty() {
            let fields = &m["datasets"][ds]["fields"];
            let sums = p["sumFields"].as_array().cloned().unwrap_or_default();
            let groups = p["groupBy"].as_array().cloned().unwrap_or_default();
            need(
                !groups.is_empty(),
                "Calculated columns require grouped rows",
            )?;
            for (target, spec) in calculations {
                need(
                    spec.as_object().is_some_and(|o| {
                        o.keys().all(|k| {
                            ["numerator", "denominator", "unitField", "decimals"]
                                .contains(&k.as_str())
                        })
                    }),
                    "Invalid calculated column",
                )?;
                need(
                    sums.contains(&json!(target)) && fields[target]["type"] == "number",
                    "Calculated target must be a numeric sum field",
                )?;
                need(
                    ["numerator", "denominator"].iter().all(|k| {
                        sums.contains(&spec[*k])
                            && spec[*k]
                                .as_str()
                                .is_some_and(|s| fields[s]["type"] == "number")
                    }),
                    "Calculated operands must be numeric sum fields",
                )?;
                need(
                    groups.contains(&spec["unitField"])
                        && spec["unitField"]
                            .as_str()
                            .is_some_and(|s| fields[s]["type"] == "string"),
                    "Calculated unit must be a grouped string field",
                )?;
                need(
                    spec.get("decimals")
                        .is_none_or(|v| v.as_i64().is_some_and(|n| (0..=6).contains(&n))),
                    "Calculated decimals must be 0–6",
                )?;
            }
        }
        if let Some(state) = p.get("tableState").filter(|v| !v.is_null()) {
            need(state.is_object(), "Table state must be an object")?;
            let names: HashSet<String> = if let Some(cols) = p["columns"].as_array() {
                cols.iter()
                    .filter_map(|c| c["key"].as_str())
                    .map(str::to_owned)
                    .collect()
            } else {
                m["datasets"][ds]["fields"]
                    .as_object()
                    .into_iter()
                    .flatten()
                    .map(|(k, _)| k.clone())
                    .collect()
            };
            for list in ["columns", "visible"] {
                let a = optional(state, list, &empty_array)
                    .as_array()
                    .ok_or_else(|| {
                        Error::new("INVALID_DOCUMENT", "Unknown or repeated table state column")
                    })?;
                let mut seen = HashSet::new();
                need(
                    a.iter().all(|v| {
                        v.as_str()
                            .is_some_and(|s| names.contains(s) && seen.insert(s))
                    }),
                    "Unknown or repeated table state column",
                )?;
                if list == "columns" && state.get(list).is_some() {
                    need(
                        a.len() == names.len(),
                        "Table order must preserve every column",
                    )?;
                }
            }
            need(
                state
                    .get("page")
                    .is_none_or(|v| v.as_i64().is_some_and(|n| n >= 1)),
                "Invalid table page",
            )?;
            need(
                state.get("pageSize").is_none_or(|v| {
                    v.as_i64()
                        .is_some_and(|n| [10, 20, 25, 50, 100, 9999].contains(&n))
                }),
                "Invalid table page size",
            )?;
            need(
                state["sortCol"].is_null()
                    || state["sortCol"].as_str().is_some_and(|n| names.contains(n)),
                "Invalid table sort column",
            )?;
            need(
                choice(state, "sortDir", "asc", &["asc", "desc"]),
                "Invalid table sort direction",
            )?;
        }
        if kind == "text" {
            need(c["text"].is_string(), "Text component requires text")?;
            continue;
        }
        if kind == "statistical" {
            need(
                !live.contains(ds),
                "Statistical plots require a static dataset",
            )?;
            super::statistics::validate_statistical(doc, c)?;
            continue;
        }
        if kind == "legacy" {
            validate_original(c)?;
            if !c["binding"].is_null() {
                validate_binding(doc, c)?;
            }
            continue;
        }
        need(
            datasets.contains_key(ds),
            format!("{key}: dataset not found"),
        )?;
        for dim in ["x", "series"] {
            if truth(&c[dim]) {
                model::field(&datasets[ds], &c[dim], false)?;
            }
        }
        if ["chart", "kpi"].contains(&kind) {
            let measures = c["measures"]
                .as_array()
                .filter(|a| !a.is_empty())
                .ok_or_else(|| {
                    Error::new("INVALID_DOCUMENT", format!("{key}: measures required"))
                })?;
            let mut seen = HashSet::new();
            for mid in measures {
                let id = mid.as_str().unwrap_or("");
                need(seen.insert(id), format!("{key}: repeated measure"))?;
                need(
                    metrics.contains_key(id) && metrics[id]["datasetId"] == ds,
                    format!("{key}: metric/dataset mismatch"),
                )?;
            }
            if kind == "kpi" {
                validate_comparisons(p, &format!("components.{key}.presentation"))?;
                need(measures.len() == 1, "KPI must have one headline measure")?;
                let card = p["type"].as_str().unwrap_or("mc01");
                need(
                    (1..=16).any(|n| card == format!("mc{n:02}")),
                    "Unknown KPI presentation type",
                )?;
                if ["mc03", "mc12"].contains(&card) {
                    if let Some(time) = p.get("timeField") {
                        model::field(&datasets[ds], time, false)?;
                    } else {
                        need(
                            p.get("sparkData")
                                .or_else(|| p.get("sparkline"))
                                .is_some_and(Value::is_array),
                            "mc03/mc12 require timeField or explicit sparkData",
                        )?;
                    }
                }
                if card == "mc06" {
                    need(
                        p.get("leftVal").is_some() && p.get("rightVal").is_some(),
                        "mc06 requires explicit leftVal and rightVal",
                    )?;
                }
            } else if let Some(problem) =
                model::compatibility(doc, c, c["chartType"].as_str().unwrap_or(""))
            {
                return Err(Error::new(
                    "INCOMPATIBLE_CHART",
                    format!("{key}: {problem}"),
                ));
            }
        }
    }
    model::validate_annotations(
        optional(m, "annotations", &empty_array),
        Some(&m["components"]),
    )?;
    if let Some(report) = m.get("report") {
        model::validate_report(report, Some(&m["components"]))?;
    }
    let filters = m["filters"]
        .as_array()
        .filter(|a| a.len() <= 30)
        .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Invalid filters"))?;
    let mut ids = HashSet::new();
    for f in filters {
        need(f.is_object(), "Invalid filter")?;
        let id = model::identifier(&f["id"], "filter id")?;
        need(ids.insert(id), "Duplicate filter id")?;
        let op = f["op"].as_str().unwrap_or("");
        need(
            ["in", "range", "contains"].contains(&op),
            "Unknown filter operation",
        )?;
        let values = f["values"]
            .as_array()
            .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Filter values must be an array"))?;
        need(
            choice(f, "selectionMode", "multiple", &["single", "multiple"]),
            "Unknown filter selection mode",
        )?;
        need(
            f.get("alwaysVisible").is_none_or(Value::is_boolean),
            "alwaysVisible must be a boolean",
        )?;
        if f["selectionMode"] == "single" {
            need(
                op == "in" && values.len() <= 1,
                "Single-select filter allows at most one value",
            )?;
        }
        need(
            values
                .iter()
                .all(|v| v.is_null() || v.is_string() || v.is_number() || v.is_boolean()),
            "Filter values must be scalar",
        )?;
        need(
            op != "range" || values.is_empty() || values.len() == 2,
            "Range filter needs two bounds",
        )?;
        if op == "contains" {
            need(
                values.len() <= 1 && values.iter().all(|v| string_len(v, 0, 1000)),
                "Search filter requires at most one text value (0-1000 characters)",
            )?;
        }
        let targets = f["componentIds"]
            .as_array()
            .filter(|a| !a.is_empty())
            .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Declare explicit filter consumers"))?;
        need(
            choice(f, "scope", "report", &["report", "table"]),
            "Unknown filter scope",
        )?;
        if f["scope"] == "table" {
            need(
                targets.len() == 1,
                "Table filter requires exactly one consumer",
            )?;
            let target = targets[0].as_str().unwrap_or("");
            let c = &m["components"][target];
            need(
                c["kind"] == "table" || (c["kind"] == "legacy" && c["family"] == "table"),
                "Table filter requires a table consumer",
            )?;
        }
        for target in targets {
            let target = target.as_str().unwrap_or("");
            need(
                components.contains_key(target),
                "Filter refers to a missing component",
            )?;
            let c = &components[target];
            need(c["kind"]!="statistical","Statistical components are static raw-observation plots; filters are not supported")?;
            need(
                c["kind"] != "text" && (c["kind"] != "legacy" || truth(&c["binding"])),
                "Original components need explicit bindings before filtering",
            )?;
            let ds = c["datasetId"].as_str().unwrap_or("");
            let meta = &m["datasets"][ds];
            model::field(meta, &f["field"], false)?;
            let name = f["field"].as_str().unwrap_or("");
            let kind = meta["fields"][name]["type"].as_str().unwrap_or("");
            if op == "contains" {
                need(kind == "string", "Search filter requires a string field")?;
            }
            need(
                values.iter().all(|v| {
                    v.is_null()
                        || match kind {
                            "number" => num(v),
                            "string" | "date" => v.is_string(),
                            "boolean" => v.is_boolean(),
                            _ => false,
                        }
                }),
                "Filter value type differs from its field",
            )?;
            if op == "range" && !values.is_empty() {
                let ordered = if kind == "number" {
                    values[0]
                        .as_f64()
                        .zip(values[1].as_f64())
                        .is_some_and(|(a, b)| a <= b)
                } else if kind == "boolean" {
                    values[0]
                        .as_bool()
                        .zip(values[1].as_bool())
                        .is_some_and(|(a, b)| !a || b)
                } else {
                    values[0]
                        .as_str()
                        .zip(values[1].as_str())
                        .is_some_and(|(a, b)| a <= b)
                };
                need(ordered, "Invalid filter range")?;
            }
        }
    }
    if let Some(saved) = m.get("layoutTemplate") {
        need(
            saved.as_object().is_some_and(|o| {
                layouts::TEMPLATES.contains(&saved["id"].as_str().unwrap_or(""))
                    && o.keys().all(|k| ["id", "order"].contains(&k.as_str()))
            }),
            "Invalid manifest.layoutTemplate",
        )?;
        need(
            saved["order"]
                .as_array()
                .into_iter()
                .flatten()
                .all(|k| k.as_str().is_some_and(|k| components.contains_key(k))),
            "manifest.layoutTemplate.order refers to a missing component",
        )?;
    }
    for (bp, cols) in layouts::COLS {
        let positions = m["layout"][bp].as_array().ok_or_else(|| {
            Error::new("INVALID_DOCUMENT", format!("{bp}: layout must be an array"))
        })?;
        let ids: HashSet<_> = positions.iter().filter_map(|p| p["id"].as_str()).collect();
        need(
            positions.len() == components.len()
                && ids.len() == components.len()
                && components.keys().all(|k| ids.contains(k.as_str())),
            format!("{bp}: every component needs exactly one placement"),
        )?;
        for (i, p) in positions.iter().enumerate() {
            need(
                ["x", "y", "w", "h"]
                    .iter()
                    .all(|k| p[*k].as_i64().is_some()),
                "Layout uses integer grid coordinates",
            )?;
            let x = p["x"].as_i64().unwrap();
            let y = p["y"].as_i64().unwrap();
            let w = p["w"].as_i64().unwrap();
            let h = p["h"].as_i64().unwrap();
            need(
                x >= 0
                    && (0..=10000).contains(&y)
                    && (1..=cols).contains(&w)
                    && (2..=100).contains(&h)
                    && x <= cols - w,
                format!("{bp}: layout out of bounds"),
            )?;
            for q in &positions[..i] {
                need(
                    !layouts::overlaps(p, q),
                    format!("{bp}: overlapping cards {} and {}", p["id"], q["id"]),
                )?;
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod runtime_validation_tests {
    use super::*;
    #[test]
    fn every_packaged_chart_and_kpi_uses_native_validation() {
        let declarations = &super::super::discovery::data()["declarations"]["legacy"];
        let document = model::new_document("fixture", "Native declaration compatibility").unwrap();
        let mut count = 0;
        for group in ["chartCodes", "kpiTypes"] {
            for (code, entry) in declarations[group].as_object().unwrap() {
                let ops = entry["example"]["operations"].as_array().unwrap();
                let saved = model::apply_operations(&document, ops)
                    .unwrap_or_else(|error| panic!("{code}: {} {}", error.code, error.message));
                validate(&saved).unwrap();
                count += 1;
            }
        }
        assert_eq!(count, 56);
        let table = &declarations["families"]["table"]["example"]["operations"];
        model::apply_operations(&document, table.as_array().unwrap()).unwrap();
        for (name, example) in super::super::discovery::data()["examples"]
            .as_object()
            .unwrap()
        {
            model::apply_operations(&document, example["operations"].as_array().unwrap())
                .unwrap_or_else(|error| panic!("{name}: {} {}", error.code, error.message));
        }
    }
    #[test]
    fn native_validation_rejects_malformed_business_data_and_renderer_types() {
        let example = &super::super::discovery::data()["declarations"]["legacy"]["chartCodes"]
            ["c01"]["example"];
        let doc = model::apply_operations(
            &model::new_document("fixture", "Validation boundaries").unwrap(),
            example["operations"].as_array().unwrap(),
        )
        .unwrap();
        let id = example["componentId"].as_str().unwrap();
        let mut broken = doc.clone();
        broken["manifest"]["components"][id]["config"]["data"]["values"] = json!([1]);
        assert!(validate(&broken).is_err());
        for renderer in [Value::Null, json!(false), json!(42), json!([])] {
            let mut broken = doc.clone();
            broken["manifest"]["components"][id]["config"]["renderer"] = renderer;
            assert_eq!(
                validate(&broken).unwrap_err().code,
                "CHART_RENDERER_INVALID"
            );
        }
        let kpi = json!({"kind":"legacy","family":"kpi","title":"Revenue","config":{"type":"mc01","label":"Revenue","value":"100","yoy":"2.5%"}});
        assert_eq!(
            validate_original(&kpi).unwrap_err().code,
            "KPI_COMPARISON_INVALID"
        );
        let described = json!({"kind":"kpi","description":"Misplaced narrative"});
        assert_eq!(
            validate_component_content(&described, "kpi")
                .unwrap_err()
                .code,
            "KPI_DESCRIPTION_NOT_ALLOWED"
        );
    }
}
