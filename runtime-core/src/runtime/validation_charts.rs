//! Native business-shape checks for every existing chart and KPI preset.
//! The registry is data; validation algorithms execute entirely in Rust.
use serde_json::{json, Value};
use std::sync::OnceLock;
pub fn rules() -> &'static Value {
    static RULES: OnceLock<Value> = OnceLock::new();
    RULES.get_or_init(|| {
        serde_json::from_str(include_str!("../../resources/component-rules.json"))
            .expect("checked component registry")
    })
}
fn problem(out: &mut Vec<Value>, code: &str, path: impl AsRef<str>, message: impl AsRef<str>) {
    out.push(json!({"code":code,"path":path.as_ref(),"message":message.as_ref()}));
}
fn number(v: &Value) -> bool {
    v.as_f64().is_some_and(f64::is_finite)
}
fn text(v: &Value) -> bool {
    v.as_str().is_some_and(|s| !s.is_empty())
}
fn absent(v: &Value) -> bool {
    v.is_null() || v.as_str() == Some("")
}
fn repr(v: &Value) -> String {
    v.as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| v.to_string())
}
fn numeric_display(v: &Value) -> bool {
    static NUMBER: OnceLock<regex::Regex> = OnceLock::new();
    NUMBER
        .get_or_init(|| {
            regex::Regex::new(r"^\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)").expect("constant regex")
        })
        .is_match(&repr(v).replace(',', ""))
}
pub fn kpi_content(k: &Value, path: &str) -> Vec<Value> {
    let mut out = vec![];
    for field in [
        "desc",
        "description",
        "detail",
        "gaugeSub",
        "note",
        "rankSub",
        "subtitle",
        "trendLabel",
    ] {
        if !absent(&k[field]) {
            problem(&mut out,"KPI_DESCRIPTION_NOT_ALLOWED",format!("{path}.{field}"),"KPI descriptions are not allowed; put explanations in metric definitions or a separate text component");
        }
    }
    out
}
pub fn kpi_comparisons(k: &Value, path: &str) -> Vec<Value> {
    let mut out = vec![];
    static SIGNED: OnceLock<regex::Regex> = OnceLock::new();
    let re = SIGNED
        .get_or_init(|| regex::Regex::new(r"^[¥$€]?\s*([0-9][0-9.,]*)").expect("constant regex"));
    for field in ["yoy", "mom", "leftYoy", "rightYoy"] {
        let v = &k[field];
        if v.is_null() {
            continue;
        }
        let message = if v.is_number() {
            if number(v) {
                None
            } else {
                Some("Comparison must be finite or null")
            }
        } else if let Some(s) = v.as_str() {
            if re
                .captures(s.trim())
                .is_some_and(|c| c[1].replace(',', "").parse::<f64>() != Ok(0.))
            {
                Some("Nonzero comparison text needs an explicit + or - sign; use a numeric value when available")
            } else {
                None
            }
        } else {
            Some("Comparison must be a number, signed display text, or null")
        };
        if let Some(m) = message {
            problem(
                &mut out,
                "KPI_COMPARISON_INVALID",
                format!("{path}.{field}"),
                m,
            );
        }
    }
    out
}
pub fn kpi_presentation(k: &Value, path: &str) -> Vec<Value> {
    let mut out = kpi_comparisons(k, path);
    let kind = k["type"].as_str().unwrap_or("");
    let mut e = |field: &str, m: &str| {
        problem(
            &mut out,
            "KPI_PRESENTATION_INVALID",
            format!("{path}.{field}"),
            m,
        )
    };
    if ["mc04", "mc05"].contains(&kind) && !numeric_display(&k["value"]) {
        e(
            "value",
            "Progress and gauge cards need a numeric display value",
        );
    }
    if ["mc03", "mc12"].contains(&kind) {
        let months = k["sparkMonths"].as_array();
        let data = k["sparkData"].as_array();
        if !months.is_some_and(|v| !v.is_empty() && v.iter().all(Value::is_string)) {
            e("sparkMonths", "Declare non-empty sparkline period labels");
        }
        if !data.is_some_and(|v| !v.is_empty() && v.iter().all(number)) {
            e("sparkData", "Declare explicit finite sparkline values");
        } else if months.zip(data).is_some_and(|(a, b)| a.len() != b.len()) {
            e(
                "sparkData",
                "Sparkline periods and values must have equal lengths",
            );
        }
    }
    if kind == "mc06" {
        for f in ["leftTitle", "leftVal", "rightTitle", "rightVal"] {
            if absent(&k[f]) {
                e(f, "Declare both metrics and their labels");
            }
        }
    }
    if kind == "mc09" {
        let mut widths = vec![];
        for f in ["segLeftWidth", "segRightWidth"] {
            let v = repr(&k[f])
                .trim_end_matches('%')
                .parse::<f64>()
                .unwrap_or(f64::NAN);
            if !v.is_finite() || !(0.0..=100.0).contains(&v) {
                e(f, "Declare a segment percentage from 0 to 100");
            }
            widths.push(v);
        }
        let total: f64 = widths.iter().sum();
        if widths.iter().all(|v| v.is_finite())
            && (total - 100.).abs() > 1e-9 * total.abs().max(100.)
        {
            e("segLeftWidth", "Segment percentages must sum to 100");
        }
        for f in ["subLabel", "subVal"] {
            if absent(&k[f]) {
                e(f, "Declare the segment label and value");
            }
        }
    }
    if kind == "mc10" {
        let names = ["min", "p25", "median", "p75", "max"];
        let s = &k["stats"];
        if !s.is_object() || !names.iter().all(|n| number(&s[*n])) {
            e(
                "stats",
                "Declare finite min, p25, median, p75 and max from the observed distribution",
            );
        } else if !names
            .windows(2)
            .all(|n| s[n[0]].as_f64() <= s[n[1]].as_f64())
        {
            e(
                "stats",
                "Distribution statistics must satisfy min <= p25 <= median <= p75 <= max",
            );
        }
        if absent(&k["value"]) {
            e("value", "Declare the displayed median");
        }
    }
    if kind == "mc11" {
        if k["percent"].is_null() {
            if !numeric_display(&k["value"]) {
                e("percent","Ring progress needs a numeric percent (0-100 scale) or a numeric display value");
            }
        } else if !number(&k["percent"]) || k["percent"].as_f64().unwrap_or(-1.) < 0. {
            e(
                "percent",
                "Ring progress percent must be a finite number >= 0 (100 = target reached)",
            );
        }
    }
    if kind == "mc13" {
        for f in ["actual", "target"] {
            if !number(&k[f]) {
                e(
                    f,
                    "Bullet cards need finite numeric actual and target values",
                );
            }
        }
        if k.get("ranges").is_some_and(|v| {
            !v.as_array()
                .is_some_and(|v| v.len() <= 3 && v.iter().all(number))
        }) {
            e(
                "ranges",
                "Qualitative ranges are up to three finite numbers in the same unit as actual",
            );
        }
        if k.get("max")
            .is_some_and(|v| !number(v) || v.as_f64().unwrap_or(0.) <= 0.)
        {
            e("max", "Scale maximum must be a positive finite number");
        }
        if !["value", "target"].contains(
            &k.get("rangeBasis")
                .map_or("value", |v| v.as_str().unwrap_or("")),
        ) {
            e(
                "rangeBasis",
                "rangeBasis is value (absolute limits) or target (fractions of target)",
            );
        }
    }
    if kind == "mc14" {
        for f in ["currentValue", "priorValue"] {
            if !number(&k[f]) {
                e(
                    f,
                    "Period comparison needs finite numeric current and prior values",
                );
            }
        }
    }
    if kind == "mc15" {
        if let Some(items) = k["items"].as_array().filter(|a| (1..=4).contains(&a.len())) {
            for (i, item) in items.iter().enumerate() {
                if !item.is_object() || absent(&item["label"]) || absent(&item["value"]) {
                    e(&format!("items[{i}]"), "Each item needs label and value");
                }
            }
        } else {
            e("items", "Declare 1-4 list items");
        }
    }
    if kind == "mc16" && absent(&k["value"]) {
        e("value", "Declare the headline value");
    }
    if kind == "mc15" {
        if let Some(items) = k["items"].as_array().filter(|a| (1..=4).contains(&a.len())) {
            for (i, item) in items.iter().enumerate() {
                if item.is_object()
                    && !absent(&item["label"])
                    && !absent(&item["value"])
                    && !item["delta"].is_null()
                {
                    for mut p in kpi_comparisons(
                        &json!({"yoy":item["delta"]}),
                        &format!("{path}.items[{i}]"),
                    ) {
                        p["path"] = json!(format!("{path}.items[{i}].delta"));
                        out.push(p);
                    }
                }
            }
        }
    }
    out
}
pub fn chart_renderer(c: &Value, path: &str) -> Vec<Value> {
    let mut out = vec![];
    let mut e =
        |f: &str, m: &str| problem(&mut out, "CHART_RENDERER_INVALID", format!("{path}.{f}"), m);
    let renderer = c
        .get("renderer")
        .map_or("preset", |v| v.as_str().unwrap_or(""));
    if !["preset", "echarts", "html"].contains(&renderer) {
        e("renderer", "Choose preset, echarts or html");
        return out;
    }
    if c["code"].as_str().is_none_or(|s| s.trim().is_empty()) {
        e(
            "code",
            "Declare a non-empty chart code; custom renderers may use any business code",
        );
    } else if renderer == "preset"
        && !rules()["CHART_CODES"]
            .as_array()
            .is_some_and(|a| a.contains(&c["code"]))
    {
        e("code","Unknown preset code; use renderer=echarts with echarts options, or renderer=html with html content");
    }
    if renderer == "echarts" && c["echarts"].as_object().is_none_or(|o| o.is_empty()) {
        e(
            "echarts",
            "A native chart requires a non-empty ECharts option object",
        );
    }
    if renderer == "html" && c["html"].as_str().is_none_or(|s| s.trim().is_empty()) {
        e(
            "html",
            "A custom component requires HTML content, optionally including CSS and JavaScript",
        );
    }
    if renderer != "preset" {
        if c.get("encoding").is_some() {
            e(
                "encoding",
                "Preset encoding is not a custom renderer data transform",
            );
        }
        if c.get("data").is_some_and(|v| !v.is_object()) {
            e("data", "Custom component data must be an object");
        }
        let table = &c["table"];
        if !table.is_null() {
            let headers = table["headers"].as_array();
            if !table.is_object()
                || !headers.is_some_and(|a| !a.is_empty() && a.iter().all(Value::is_string))
            {
                e("table", "Supply table headers as a non-empty string array");
            } else if !table["rows"].as_array().is_some_and(|a| {
                a.iter().all(|r| {
                    r.as_array()
                        .is_some_and(|r| r.len() == headers.unwrap().len())
                })
            }) {
                e(
                    "table.rows",
                    "Each table row must have the same length as headers",
                );
            }
        }
    }
    out
}
fn required<'a>(d: &'a Value, key: &str, path: &str, e: &mut Vec<Value>) -> &'a Value {
    if d.get(key).is_none() {
        problem(
            e,
            "CHART_DATA_FIELD_MISSING",
            format!("{path}.{key}"),
            format!("Chart data {key} is required"),
        );
    }
    &d[key]
}
fn typed(v: &Value, kind: &str) -> bool {
    match kind {
        "number" => number(v),
        "nullable_number" => v.is_null() || number(v),
        "string" => text(v),
        "object" => v.is_object(),
        "array" => v.is_array(),
        _ => false,
    }
}
fn array<'a>(
    d: &'a Value,
    key: &str,
    path: &str,
    e: &mut Vec<Value>,
    kind: &str,
) -> Option<&'a Vec<Value>> {
    let value = required(d, key, path, e);
    if value.is_null() {
        return None;
    }
    let Some(a) = value.as_array() else {
        problem(
            e,
            "CHART_DATA_TYPE_INVALID",
            format!("{path}.{key}"),
            format!("Chart data {key} must be an array"),
        );
        return None;
    };
    if a.is_empty() {
        problem(
            e,
            "CHART_DATA_EMPTY",
            format!("{path}.{key}"),
            format!("Chart data {key} must contain at least one item"),
        );
    } else if !a.iter().all(|v| typed(v, kind)) {
        problem(
            e,
            "CHART_DATA_TYPE_INVALID",
            format!("{path}.{key}"),
            format!("Chart data {key} must contain only {kind} values"),
        );
    }
    Some(a)
}
fn lengths(arrays: &[(&str, Option<&Vec<Value>>)], path: &str, e: &mut Vec<Value>) {
    let sizes: Vec<_> = arrays
        .iter()
        .filter_map(|(name, v)| v.map(|v| (*name, v.len())))
        .collect();
    if sizes.len() > 1 && sizes.iter().any(|v| v.1 != sizes[0].1) {
        problem(
            e,
            "CHART_DATA_LENGTH_MISMATCH",
            path,
            format!(
                "Chart data arrays {} must have equal lengths",
                sizes.iter().map(|v| v.0).collect::<Vec<_>>().join(", ")
            ),
        );
    }
}
fn object_fields(d: &Value, key: &str, fields: &[(&str, &str)], path: &str, e: &mut Vec<Value>) {
    if let Some(a) = d[key].as_array() {
        for (i, item) in a.iter().enumerate().filter(|(_, v)| v.is_object()) {
            let p = format!("{path}.{key}[{i}]");
            for (field, kind) in fields {
                let v = required(item, field, &p, e);
                if !v.is_null() && !typed(v, kind) {
                    problem(
                        e,
                        "CHART_DATA_TYPE_INVALID",
                        format!("{p}.{field}"),
                        format!("{field} must be {kind}"),
                    );
                }
            }
        }
    }
}
fn strict_data(code: &str, d: &Value, path: &str, e: &mut Vec<Value>) {
    if code == "t06" {
        for grain in ["month", "quarter"] {
            let v = required(d, grain, path, e);
            if v.is_null() {
                continue;
            }
            let p = format!("{path}.{grain}");
            if !v.is_object() {
                problem(
                    e,
                    "CHART_DATA_TYPE_INVALID",
                    &p,
                    format!("{grain} data must be an object"),
                );
                continue;
            }
            let a = array(v, "categories", &p, e, "string");
            let b = array(v, "revenue", &p, e, "number");
            let c = array(v, "yieldGrowth", &p, e, "number");
            lengths(
                &[("categories", a), ("revenue", b), ("yieldGrowth", c)],
                &p,
                e,
            );
        }
        return;
    }
    let mut arrays = std::collections::HashMap::new();
    if let Some(fields) = rules()["CHART_ARRAY_FIELDS"][code].as_array() {
        for f in fields {
            let key = f[0].as_str().unwrap();
            arrays.insert(key, array(d, key, path, e, f[1].as_str().unwrap()));
        }
    }
    if let Some(groups) = rules()["CHART_EQUAL_LENGTH_GROUPS"][code].as_array() {
        for group in groups {
            let entries: Vec<_> = group
                .as_array()
                .unwrap()
                .iter()
                .filter_map(Value::as_str)
                .map(|k| (k, arrays.get(k).copied().flatten()))
                .collect();
            lengths(&entries, path, e);
        }
    }
    match code {
        "t05" => {
            if let Some(lines) = d["lines"].as_array() {
                for (i, line) in lines.iter().enumerate().filter(|(_, v)| v.is_object()) {
                    let p = format!("{path}.lines[{i}]");
                    let name = required(line, "name", &p, e);
                    if !name.is_null() && !text(name) {
                        problem(
                            e,
                            "CHART_DATA_TYPE_INVALID",
                            format!("{p}.name"),
                            "Line name must be a string",
                        );
                    }
                    let values = array(line, "data", &p, e, "number");
                    lengths(
                        &[("stages", d["stages"].as_array()), ("data", values)],
                        &p,
                        e,
                    );
                }
            }
        }
        "r01" | "r02" => {
            let key = if code == "r01" { "routes" } else { "clusters" };
            let n = if code == "r01" { 3 } else { 4 };
            if let Some(points) = d[key].as_array() {
                for (i, v) in points.iter().enumerate() {
                    let valid = v.as_array().is_some_and(|a| {
                        a.len() == n && a[..n - 1].iter().all(number) && text(&a[n - 1])
                    });
                    if !valid {
                        problem(
                            e,
                            "CHART_DATA_TYPE_INVALID",
                            format!("{path}.{key}[{i}]"),
                            if n == 3 {
                                "Each route must be [numeric x, numeric y, non-empty label]"
                            } else {
                                "Bubble points must be [numeric x, numeric y, numeric size, non-empty label]"
                            },
                        );
                    }
                }
            }
        }
        "d02" => {
            if let Some(a) = d["boxData"].as_array() {
                for (i, v) in a.iter().enumerate() {
                    if !v
                        .as_array()
                        .is_some_and(|v| v.len() == 5 && v.iter().all(number))
                    {
                        problem(
                            e,
                            "CHART_DATA_TYPE_INVALID",
                            format!("{path}.boxData[{i}]"),
                            "Box data must contain five numeric values",
                        );
                    }
                }
            }
        }
        "f01" | "k01" | "k03" | "k05" => {
            let key = match code {
                "f01" => "stages",
                "k01" => "demographics",
                "k03" => "assets",
                _ => "shares",
            };
            object_fields(d, key, &[("name", "string"), ("value", "number")], path, e);
        }
        "f02" | "r04" => {
            object_fields(d, "nodes", &[("name", "string")], path, e);
            let mut required = vec![("source", "string"), ("target", "string")];
            if code == "f02" {
                required.push(("value", "number"));
            }
            object_fields(d, "links", &required, path, e);
            let names: Vec<_> = d["nodes"]
                .as_array()
                .into_iter()
                .flatten()
                .filter(|v| v.is_object())
                .map(|v| &v["name"])
                .collect();
            if let Some(links) = d["links"].as_array() {
                for (i, link) in links.iter().enumerate() {
                    if link.is_object()
                        && (!names.contains(&&link["source"]) || !names.contains(&&link["target"]))
                    {
                        problem(
                            e,
                            "CHART_DATA_REFERENCE_INVALID",
                            format!("{path}.links[{i}]"),
                            "Link endpoints must reference declared nodes",
                        );
                    }
                }
            }
        }
        "d04" | "f03" | "r03" => {
            let key = if code == "d04" { "data" } else { "matrix" };
            let len = |k: &str| d[k].as_array().map_or(0, Vec::len);
            let expected = match code {
                "d04" => len("days") * len("hours"),
                "f03" => len("cohorts") * len("months"),
                _ => len("dimensions").pow(2),
            };
            if len(key) != expected {
                problem(
                    e,
                    "CHART_DATA_LENGTH_MISMATCH",
                    format!("{path}.{key}"),
                    format!("Matrix must contain {expected} cells"),
                );
            }
            if let Some(matrix) = d[key].as_array() {
                for (i, v) in matrix.iter().enumerate() {
                    if !v
                        .as_array()
                        .is_some_and(|a| a.len() == 3 && a.iter().all(number))
                    {
                        problem(
                            e,
                            "CHART_DATA_TYPE_INVALID",
                            format!("{path}.{key}[{i}]"),
                            "Matrix cells must be [numeric x, numeric y, numeric value]",
                        );
                    }
                }
            }
        }
        "k06" => {
            fn tree(nodes: &[Value], path: &str, e: &mut Vec<Value>) {
                for (i, n) in nodes.iter().enumerate().filter(|(_, n)| n.is_object()) {
                    let p = format!("{path}[{i}]");
                    if !text(&n["name"]) {
                        problem(
                            e,
                            "CHART_DATA_TYPE_INVALID",
                            format!("{p}.name"),
                            "Tree node name must be a string",
                        );
                    }
                    if let Some(children) = n["children"].as_array().filter(|a| !a.is_empty()) {
                        tree(children, &format!("{p}.children"), e);
                    } else if !number(&n["value"]) {
                        problem(
                            e,
                            "CHART_DATA_TYPE_INVALID",
                            format!("{p}.value"),
                            "Tree leaf value must be numeric",
                        );
                    }
                }
            }
            if let Some(nodes) = d["hierarchy"].as_array() {
                tree(nodes, &format!("{path}.hierarchy"), e);
            }
        }
        "r05" => {
            object_fields(
                d,
                "indicators",
                &[("name", "string"), ("max", "number")],
                path,
                e,
            );
            object_fields(
                d,
                "seriesData",
                &[("name", "string"), ("value", "array")],
                path,
                e,
            );
            let expected = d["indicators"].as_array().map_or(0, Vec::len);
            let series = d["seriesData"].as_array();
            if series.map_or(0, Vec::len) != 2 {
                problem(
                    e,
                    "CHART_DATA_LENGTH_MISMATCH",
                    format!("{path}.seriesData"),
                    "Radar data must contain two comparison series",
                );
            }
            if let Some(series) = series {
                for (i, s) in series.iter().enumerate() {
                    if !s["value"]
                        .as_array()
                        .is_some_and(|a| a.len() == expected && a.iter().all(number))
                    {
                        problem(
                            e,
                            "CHART_DATA_LENGTH_MISMATCH",
                            format!("{path}.seriesData[{i}].value"),
                            format!("Radar series must contain {expected} numeric values"),
                        );
                    }
                }
            }
        }
        _ => {}
    }
    if code == "m01" {
        let t = required(d, "target", path, e);
        if !t.is_null() && !number(t) {
            problem(
                e,
                "CHART_DATA_TYPE_INVALID",
                format!("{path}.target"),
                "Target must be numeric",
            );
        }
    }
    if code == "m04" {
        let rate = required(d, "rate", path, e);
        if !rate.is_null() && !number(rate) {
            problem(
                e,
                "CHART_DATA_TYPE_INVALID",
                format!("{path}.rate"),
                "Rate must be numeric",
            );
        }
        let target = required(d, "target", path, e);
        if !target.is_null() && !target.is_string() && !target.is_number() {
            problem(
                e,
                "CHART_DATA_TYPE_INVALID",
                format!("{path}.target"),
                "Target must be a display string or number",
            );
        }
    }
}
fn strict_presentation(code: &str, data: &Value, p: &Value, data_path: &str, e: &mut Vec<Value>) {
    let path = format!(
        "{}.presentation",
        data_path.rsplit_once(".data").map_or(data_path, |v| v.0)
    );
    if p.is_null() {
        problem(
            e,
            "CHART_PRESENTATION_MISSING",
            &path,
            "Strict chart generation requires presentation metadata",
        );
        return;
    }
    if !p.is_object() {
        problem(
            e,
            "CHART_PRESENTATION_TYPE_INVALID",
            &path,
            "Chart presentation must be an object",
        );
        return;
    }
    let c = &rules()["CHART_PRESENTATION_CONTRACTS"][code];
    let axis = c["axis"].as_array().expect("registry axis");
    if !axis.is_empty()
        && (!p["axisLabels"].is_object()
            || axis
                .iter()
                .any(|k| !text(&p["axisLabels"][k.as_str().unwrap()])))
    {
        problem(
            e,
            "CHART_PRESENTATION_FIELD_MISSING",
            format!("{path}.axisLabels"),
            format!(
                "axisLabels must declare {}",
                axis.iter()
                    .filter_map(Value::as_str)
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
        );
    }
    let series = if c["series"] == "lines" {
        data["lines"].as_array().map_or(0, Vec::len)
    } else {
        c["series"].as_u64().unwrap_or(0) as usize
    };
    let table = match rules()["CHART_TABLE_HEADER_COUNTS"][code].as_str() {
        Some("months+1") => data["months"].as_array().map_or(0, Vec::len) + 1,
        Some("stages+1") => data["stages"].as_array().map_or(0, Vec::len) + 1,
        _ => rules()["CHART_TABLE_HEADER_COUNTS"][code]
            .as_u64()
            .unwrap_or(0) as usize,
    };
    for (key, n) in [
        ("seriesLabels", series),
        (
            "tooltipValueLabels",
            c["tooltip"].as_u64().unwrap_or(0) as usize,
        ),
        ("units", c["units"].as_u64().unwrap_or(0) as usize),
        ("labels", c["labels"].as_u64().unwrap_or(0) as usize),
        ("tableHeaders", table),
    ] {
        if n == 0 && key != "tableHeaders" {
            continue;
        }
        if let Some(a) = p[key].as_array().filter(|a| a.iter().all(text)) {
            if a.len() != n {
                problem(
                    e,
                    "CHART_PRESENTATION_LENGTH_MISMATCH",
                    format!("{path}.{key}"),
                    format!("presentation {key} must contain {n} values"),
                );
            }
        } else {
            problem(
                e,
                "CHART_PRESENTATION_FIELD_MISSING",
                format!("{path}.{key}"),
                format!("presentation {key} must be a string array"),
            );
        }
    }
    if let Some(numeric) = c["numeric"].as_array() {
        for pair in numeric {
            let parent = pair[0].as_str().unwrap();
            let key = pair[1].as_str().unwrap();
            if !number(&p[parent][key]) {
                problem(
                    e,
                    "CHART_PRESENTATION_FIELD_MISSING",
                    format!("{path}.{parent}.{key}"),
                    format!("{parent}.{key} must be numeric"),
                );
            }
        }
    }
    if let Some(domains) = c["domain"].as_array() {
        for pair in domains {
            let parent = pair[0].as_str().unwrap();
            let key = pair[1].as_str().unwrap();
            let v = &p[parent][key];
            let pair_ok = |v: &Value| {
                v.as_array()
                    .is_some_and(|a| a.len() == 2 && a.iter().all(number))
            };
            let valid = if code == "r05" && key == "indicators" {
                v.as_array().is_some_and(|a| {
                    a.len() == data["indicators"].as_array().map_or(0, Vec::len)
                        && a.iter().all(pair_ok)
                })
            } else {
                pair_ok(v)
            };
            if !valid {
                problem(
                    e,
                    "CHART_PRESENTATION_FIELD_MISSING",
                    format!("{path}.{parent}.{key}"),
                    format!("{parent}.{key} must declare numeric domain pairs"),
                );
            }
        }
    }
}
pub fn chart_data(data: &Value, path: &str, code: &str, presentation: &Value) -> Vec<Value> {
    let mut out = vec![];
    if !data.is_object() {
        problem(
            &mut out,
            "CHART_DATA_INVALID",
            path,
            "Chart data must be an object",
        );
        return out;
    }
    if data.as_object().is_some_and(|v| v.is_empty()) {
        problem(
            &mut out,
            "CHART_DATA_EMPTY",
            path,
            "Chart data must contain explicit business values",
        );
    }
    for key in ["categories", "values", "x", "y", "nodes", "links", "series"] {
        if data.get(key).is_some_and(|v| !v.is_array()) {
            problem(
                &mut out,
                "CHART_DATA_ARRAY_REQUIRED",
                format!("{path}.{key}"),
                format!("Chart data {key} must be an array"),
            );
        }
    }
    for (left, right) in [("categories", "values"), ("x", "y")] {
        if data[left]
            .as_array()
            .zip(data[right].as_array())
            .is_some_and(|(a, b)| a.len() != b.len())
        {
            problem(
                &mut out,
                "CHART_DATA_LENGTH_MISMATCH",
                path,
                format!("Chart data {left} and {right} must have equal lengths"),
            );
        }
    }
    if rules()["CHART_CODES"]
        .as_array()
        .is_some_and(|a| a.contains(&json!(code)))
    {
        strict_data(code, data, path, &mut out);
        strict_presentation(code, data, presentation, path, &mut out);
    }
    out
}
