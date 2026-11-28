//! Component resolution over immutable datasets, without sending observations to chart clients.
use super::{
    data::{semantic_filters, LocalData, QueryCache},
    error::{require, Error, Result},
    model::apply_operations,
    query::{LiveQueryRequest, QueryRunner},
    serialization::{canonical_json, json_bytes},
};
use rust_decimal::{prelude::ToPrimitive, Decimal, RoundingStrategy};
use serde_json::{json, Map, Value};
use std::{
    collections::{BTreeMap, HashSet},
    time::Instant,
};

fn decimal(v: &Value) -> Result<Decimal> {
    let s = v
        .as_number()
        .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Expected numeric metric result"))?
        .to_string();
    Decimal::from_str_exact(&s)
        .or_else(|_| Decimal::from_scientific(&s))
        .map_err(|_| {
            Error::new(
                "INVALID_ARGUMENT",
                "Metric value exceeds decimal formatting range",
            )
        })
}
pub fn formatted(value: &Value, metric: &Value, signed: bool) -> Result<String> {
    if value.is_null() {
        return Ok("—".into());
    }
    let mut n = decimal(value)?;
    if metric["format"] == "percent" {
        n = n.checked_mul(Decimal::from(100)).ok_or_else(|| {
            Error::new(
                "INVALID_ARGUMENT",
                "Percent value exceeds decimal formatting range",
            )
        })?;
    }
    let places = metric["decimals"].as_u64().unwrap_or(2).min(28) as u32;
    n = n.round_dp_with_strategy(places, RoundingStrategy::MidpointAwayFromZero);
    if n.is_zero() {
        n = Decimal::ZERO;
    }
    let s = n.normalize().to_string();
    let (integer, fraction) = s.split_once('.').unwrap_or((&s, ""));
    let negative = integer.starts_with('-');
    let digits = integer.trim_start_matches('-');
    let mut text = String::new();
    if negative {
        text.push('-');
    }
    for (i, c) in digits.chars().enumerate() {
        if i > 0 && (digits.len() - i) % 3 == 0 {
            text.push(',');
        }
        text.push(c);
    }
    if !fraction.is_empty() {
        text.push('.');
        text.push_str(fraction);
    }
    if metric["format"] == "percent" {
        text.push('%');
    } else if let Some(unit) = metric["unit"].as_str().filter(|u| !u.is_empty()) {
        text.push(' ');
        text.push_str(unit);
    }
    if signed && n > Decimal::ZERO {
        text.insert(0, '+');
    }
    Ok(text)
}
fn rounded(value: f64, places: u64) -> Result<Value> {
    if !value.is_finite() {
        return Err(Error::new(
            "INVALID_ARGUMENT",
            "Metric calculation produced a non-finite value",
        ));
    }
    let v = decimal(&json!(value))?.round_dp_with_strategy(
        places.min(28) as u32,
        RoundingStrategy::MidpointAwayFromZero,
    );
    Ok(json!(v.to_f64().ok_or_else(|| Error::new(
        "INVALID_ARGUMENT",
        "Metric formatting failed"
    ))?))
}
fn string_key(v: &Value) -> String {
    v.as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| v.to_string())
}
fn array_strings(value: Option<&Value>) -> Result<Vec<String>> {
    match value {
        None => Ok(Vec::new()),
        Some(v) => v
            .as_array()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Expected an array"))?
            .iter()
            .map(|v| {
                v.as_str()
                    .map(str::to_owned)
                    .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Expected a string field"))
            })
            .collect(),
    }
}
fn object(value: Option<&Value>) -> Map<String, Value> {
    value
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default()
}

#[derive(Clone)]
pub struct LocalView {
    pub data: LocalData,
    pub queries: Option<QueryRunner>,
    pub query_cache: QueryCache,
}
impl LocalView {
    pub fn new(data: LocalData, queries: Option<QueryRunner>) -> Self {
        Self {
            data,
            queries,
            query_cache: QueryCache::default(),
        }
    }
    pub fn aggregate(
        &self,
        reference: &Value,
        metrics: &Value,
        filters: &[Value],
        groups: &[String],
        grain: Option<&str>,
    ) -> Result<(Vec<Value>, bool)> {
        self.data.validate_reference(reference)?;
        let metrics = metrics.as_object().ok_or_else(|| {
            Error::new("INVALID_ARGUMENT", "Metric definitions must be a mapping")
        })?;
        let names = metrics.keys().cloned().collect::<Vec<_>>();
        let definitions = metrics
            .values()
            .map(|m| {
                Value::Object(
                    m.as_object()
                        .into_iter()
                        .flatten()
                        .filter(|(k, _)| {
                            [
                                "aggregation",
                                "field",
                                "numerator",
                                "denominator",
                                "entityField",
                            ]
                            .contains(&k.as_str())
                        })
                        .map(|(k, v)| (k.clone(), v.clone()))
                        .collect(),
                )
            })
            .collect::<Vec<_>>();
        let mut canonical = BTreeMap::new();
        for d in &definitions {
            canonical.insert(canonical_json(d)?, d.clone());
        }
        let canonical = canonical.into_values().collect::<Vec<_>>();
        let mut prefix = "__metric_".to_string();
        while (0..canonical.len()).any(|i| groups.contains(&format!("{prefix}{i}"))) {
            prefix.insert(0, '_');
        }
        let aliases = canonical
            .iter()
            .enumerate()
            .map(|(i, d)| (format!("{prefix}{i}"), d.clone()))
            .collect::<Map<_, _>>();
        let alias_names = aliases.keys().cloned().collect::<Vec<_>>();
        let key = canonical_json(&json!([
            reference["version"],
            canonical,
            semantic_filters(filters)?,
            groups,
            grain
        ]))?;
        let (result, hit) = self.query_cache.get(key, || {
            Ok(json!(self.data.aggregate(
                reference,
                &Value::Object(aliases),
                filters,
                groups,
                grain
            )?))
        })?;
        let mut translated = Vec::new();
        for row in result
            .as_array()
            .ok_or_else(|| Error::new("INTERNAL_ERROR", "Invalid aggregate result"))?
        {
            let mut out = Map::new();
            for g in groups {
                out.insert(g.clone(), row[g].clone());
            }
            for (name, def) in names.iter().zip(&definitions) {
                let index = canonical.iter().position(|d| d == def).unwrap();
                out.insert(name.clone(), row[&alias_names[index]].clone());
            }
            translated.push(Value::Object(out));
        }
        Ok((translated, hit))
    }
    pub fn prepare(
        &self,
        doc: &Value,
        filters: Option<&Value>,
        table_states: Option<&Value>,
        granularities: Option<&Value>,
    ) -> Result<Value> {
        self.prepare_select(doc, filters, table_states, granularities, None, true)
    }
    pub fn check_component(&self, doc: &Value, key: &str) -> Result<()> {
        self.prepare_select(doc, None, None, None, Some(&[key.into()]), false)
            .map(|_| ())
    }
    pub fn prepare_select(
        &self,
        document: &Value,
        filters: Option<&Value>,
        table_states: Option<&Value>,
        granularities: Option<&Value>,
        component_ids: Option<&[String]>,
        include_filter_options: bool,
    ) -> Result<Value> {
        let started = Instant::now();
        let mut doc = if let Some(filters) = filters {
            apply_operations(document, &[json!({"op":"set_filters","value":filters})])?
        } else {
            document.clone()
        };
        let m = doc["manifest"].clone();
        let snapshot = doc["snapshot"].clone();
        require(
            snapshot["datasets"].as_object().is_some_and(Map::is_empty),
            "Local preview requires versioned datasets",
            "INVALID_ARGUMENT",
        )?;
        let components = m["components"]
            .as_object()
            .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Components are missing"))?;
        let refs = object(snapshot.get("datasetRefs"));
        let table_states = object(table_states);
        let granularities = object(granularities);
        require(
            table_states.keys().all(|k| components.contains_key(k)),
            "Unknown table view component",
            "INVALID_ARGUMENT",
        )?;
        require(
            granularities.iter().all(|(k, v)| {
                components.contains_key(k) && [Some("month"), Some("quarter")].contains(&v.as_str())
            }),
            "Invalid chart granularity",
            "INVALID_ARGUMENT",
        )?;
        let selected = component_ids
            .map(<[String]>::to_vec)
            .unwrap_or_else(|| components.keys().cloned().collect());
        require(
            selected.iter().all(|k| components.contains_key(k)),
            "Unknown view component",
            "INVALID_ARGUMENT",
        )?;
        let declared_filters = m["filters"].as_array().cloned().unwrap_or_default();
        if component_ids.is_none() {
            for (ds, reference) in &refs {
                let mut keys = HashSet::new();
                for f in &declared_filters {
                    if f["componentIds"].as_array().is_some_and(|a| {
                        a.iter().any(|id| {
                            id.as_str()
                                .is_some_and(|id| components[id]["datasetId"] == *ds)
                        })
                    }) {
                        if let Some(field) = f["field"].as_str() {
                            keys.insert(field.to_string());
                        }
                    }
                }
                for c in components.values() {
                    if c["datasetId"] == *ds && (c["family"] == "table" || c["kind"] == "table") {
                        if let Some(fields) = reference["fields"].as_object() {
                            for (k, v) in fields {
                                if v["type"] == "number" {
                                    keys.insert(k.clone());
                                }
                            }
                        }
                    }
                }
                self.data
                    .prepare_indexes(reference, &keys.into_iter().collect::<Vec<_>>())?;
            }
        }
        let mut live = LiveQueryRequest::new(self.queries.clone(), &m)?;
        let live_view = LocalView::new(live.data.clone(), None);
        let mut computed = json!({"components":{},"tables":{},"grouped":{},"filterOptions":{},"filterPages":{},"cacheHits":0});
        let mut hits = 0u64;
        for key in selected {
            let c = &components[&key];
            let kind = c["kind"].as_str().unwrap_or("");
            let family = if kind == "legacy" {
                c["family"].as_str().unwrap_or("chart")
            } else {
                kind
            };
            if ["text", "statistical"].contains(&family) {
                continue;
            }
            let mut raw = Value::Object(if kind == "legacy" {
                object(c.get("config"))
            } else {
                let mut r = object(c.get("presentation"));
                r.extend(object(c.get("config")));
                r
            });
            let binding = c.get("binding").filter(|b| b.is_object());
            let ds = c["datasetId"].as_str();
            let is_live = ds.is_some_and(|ds| m["datasets"][ds]["mode"] == "live");
            let reference = if is_live {
                Some(live.reference(ds.unwrap())?)
            } else if let Some(ds) = ds {
                refs.get(ds).cloned()
            } else {
                snapshot["componentDataRefs"].get(&key).cloned()
            };
            let view = if is_live { &live_view } else { self };
            let active = declared_filters
                .iter()
                .filter(|f| {
                    f["componentIds"]
                        .as_array()
                        .is_some_and(|ids| ids.iter().any(|id| id == &key))
                        && f["values"].as_array().is_some_and(|v| !v.is_empty())
                })
                .cloned()
                .collect::<Vec<_>>();
            let Some(reference) = reference else {
                computed["components"][&key] = raw;
                continue;
            };
            if family == "table" {
                let mut state = object(raw.get("tableState"));
                state.extend(object(table_states.get(&key)));
                let mut page = state
                    .get("page")
                    .unwrap_or(&json!(1))
                    .as_u64()
                    .filter(|p| *p >= 1)
                    .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid table pagination"))?;
                let size = state
                    .get("pageSize")
                    .unwrap_or(&json!(10))
                    .as_u64()
                    .filter(|s| [10, 20, 25, 50, 100, 9999].contains(s))
                    .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid table pagination"))?
                    as usize;
                let fields = if let Some(ds) = ds {
                    &m["datasets"][ds]["fields"]
                } else {
                    &reference["fields"]
                };
                let columns=raw.get("columns").filter(|v|v.as_array().is_some_and(|a|!a.is_empty())).or_else(||c["presentation"].get("columns").filter(|v|v.as_array().is_some_and(|a|!a.is_empty()))).cloned().unwrap_or_else(||Value::Array(fields.as_object().into_iter().flatten().map(|(k,v)|json!({"key":k,"title":v["label"].as_str().unwrap_or(k),"align":if v["type"]=="number"{"right"}else{"left"}})).collect()));
                let selected_fields = columns
                    .as_array()
                    .ok_or_else(|| {
                        Error::new("INVALID_ARGUMENT", "Table columns must be an array")
                    })?
                    .iter()
                    .map(|v| {
                        v["key"]
                            .as_str()
                            .map(str::to_owned)
                            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid table column"))
                    })
                    .collect::<Result<Vec<_>>>()?;
                require(
                    selected_fields
                        .iter()
                        .all(|f| reference["fields"].get(f).is_some()),
                    "Unknown table column",
                    "INVALID_ARGUMENT",
                )?;
                let sort=state.get("sortCol").and_then(Value::as_str).filter(|s|!s.is_empty()).map(|s|vec![json!({"field":s,"direction":state.get("sortDir").cloned().unwrap_or(json!("asc"))})]).unwrap_or_default();
                let search = state
                    .get("keyword")
                    .unwrap_or(&Value::Null)
                    .as_str()
                    .unwrap_or("");
                require(
                    !state.contains_key("keyword") || state["keyword"].is_string(),
                    "Table search must be a string",
                    "INVALID_ARGUMENT",
                )?;
                require(
                    search.chars().count() <= 1000,
                    "Table search must contain at most 1000 characters",
                    "INVALID_ARGUMENT",
                )?;
                let groups = array_strings(raw.get("groupBy"))?;
                let sums = array_strings(raw.get("sumFields"))?;
                let request = |page: u64| -> Result<Value> {
                    let offset = page
                        .checked_sub(1)
                        .and_then(|p| p.checked_mul(size as u64))
                        .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid table page"))?;
                    if groups.is_empty() {
                        view.data.rows(
                            &reference,
                            &active,
                            Some(&selected_fields),
                            &sort,
                            offset,
                            size,
                            search,
                        )
                    } else {
                        view.data.grouped_rows(
                            &reference,
                            &active,
                            Some(&selected_fields),
                            &sort,
                            offset,
                            size,
                            search,
                            &groups,
                            &sums,
                            raw.get("calculatedColumns"),
                        )
                    }
                };
                let mut result = request(page)?;
                let total = result["totalRows"].as_u64().unwrap_or(0);
                let last = total.div_ceil(size as u64).max(1);
                if page > last {
                    page = last;
                    result = request(page)?;
                }
                if let Some(calculated) = raw["calculatedColumns"].as_object() {
                    for row in result["rows"].as_array_mut().into_iter().flatten() {
                        for (target, spec) in calculated {
                            let value = row[target].as_f64();
                            let unit = row[spec["unitField"].as_str().unwrap_or("")]
                                .as_str()
                                .unwrap_or("");
                            let places = spec["decimals"].as_u64().unwrap_or(1).min(20) as usize;
                            row[target] = json!(match value {
                                None => "—".into(),
                                Some(v) =>
                                    if unit == "%" {
                                        format!("{:.*}%", places, v * 100.0)
                                    } else {
                                        format!("{:.*} {}", places, v, unit).trim_end().to_string()
                                    },
                            });
                        }
                    }
                }
                raw["rows"] = result["rows"].clone();
                raw["columns"] = columns;
                computed["tables"][&key] = json!({"page":page,"pageSize":size,"totalRows":total,"sortCol":state.get("sortCol"),"sortDir":state.get("sortDir").cloned().unwrap_or(json!("asc")),"keyword":search,"durationMs":result["durationMs"]});
                computed["components"][&key] = raw;
                continue;
            }
            if binding.is_some() && raw.get("encoding").is_some() {
                raw["data"] = json!({"records":super::encoding::resolve_encoding(view,&reference,&m,c,&active)?});
                computed["components"][&key] = raw;
                continue;
            }
            let mids = if let Some(b) = binding {
                object(b.get("measures"))
            } else {
                c["measures"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(Value::as_str)
                    .map(|mid| (mid.to_string(), json!(mid)))
                    .collect()
            };
            let definitions = mids
                .values()
                .filter_map(Value::as_str)
                .map(|mid| (mid.to_string(), m["metrics"][mid].clone()))
                .collect::<Map<_, _>>();
            let definitions_value = Value::Object(definitions.clone());
            if family == "kpi" {
                let (result, hit) =
                    view.aggregate(&reference, &definitions_value, &active, &[], None)?;
                hits += u64::from(hit);
                let values = result.first().cloned().unwrap_or(json!({}));
                if let Some(b) = binding {
                    for name in ["yoy", "mom", "subVal", "leftVal", "rightVal"] {
                        if raw.get(name).is_some() && !mids.contains_key(name) {
                            raw[name] = json!("—");
                        }
                    }
                    for (target, mid) in &mids {
                        let mid = mid.as_str().unwrap_or("");
                        let value = values[mid]
                            .as_f64()
                            .map(|v| json!(v * b["scale"][target].as_f64().unwrap_or(1.0)))
                            .unwrap_or(Value::Null);
                        raw[target] =
                            if ["percent", "actual", "target", "currentValue", "priorValue"]
                                .contains(&target.as_str())
                            {
                                value
                            } else {
                                json!(formatted(
                                    &value,
                                    &m["metrics"][mid],
                                    ["yoy", "mom"].contains(&target.as_str())
                                )?)
                            };
                    }
                } else {
                    let mid = c["measures"][0].as_str().unwrap_or("");
                    let metric = &m["metrics"][mid];
                    if raw.get("type").is_none() {
                        raw["type"] = json!("mc01");
                    }
                    raw["label"] = c["title"].clone();
                    raw["value"] = json!(formatted(&values[mid], metric, false)?);
                    raw["statusBadge"] = json!(if metric["status"] == "reviewed" {
                        "已复核"
                    } else {
                        "待复核"
                    });
                    if raw.get("subLabel").is_none() {
                        raw["subLabel"] = json!("统计口径");
                    }
                    if raw.get("subVal").is_none() {
                        let aggregation = metric["aggregation"].as_str().unwrap_or("");
                        raw["subVal"] = json!(match aggregation {
                            "sum" => "合计",
                            "ratio" => "分子 / 分母",
                            "avg" => "平均",
                            "count" => "计数",
                            _ => aggregation,
                        });
                    }
                    if !active.is_empty() {
                        for name in [
                            "yoy",
                            "mom",
                            "subVal",
                            "leftVal",
                            "rightVal",
                            "trendLabel",
                            "gaugeSub",
                        ] {
                            if raw.get(name).is_some() {
                                raw[name] = json!("—");
                            }
                        }
                        if let Some(r) = raw.as_object_mut() {
                            for name in [
                                "percent",
                                "actual",
                                "target",
                                "currentValue",
                                "priorValue",
                                "stats",
                                "items",
                            ] {
                                r.remove(name);
                            }
                        }
                        raw["subLabel"] = json!("当前筛选范围");
                    }
                }
                if let Some(b) = binding {
                    for (target, comparison) in object(b.get("comparisons")) {
                        let current = values[mids[comparison["current"].as_str().unwrap_or("")]
                            .as_str()
                            .unwrap_or("")]
                        .as_f64();
                        let baseline = values[mids[comparison["baseline"].as_str().unwrap_or("")]
                            .as_str()
                            .unwrap_or("")]
                        .as_f64();
                        let delta = match (current, baseline) {
                            (Some(c), Some(b)) if b != 0.0 => json!((c - b) / b),
                            _ => Value::Null,
                        };
                        raw[&target] = json!(formatted(
                            &delta,
                            &json!({"format":"percent","scale":"fraction","decimals":1,"unit":""}),
                            true
                        )?);
                    }
                }
                let time_field = binding
                    .and_then(|b| b["timeField"].as_str())
                    .or_else(|| {
                        if binding.is_none() {
                            raw["timeField"].as_str()
                        } else {
                            None
                        }
                    })
                    .map(str::to_owned);
                if [Some("mc03"), Some("mc12")].contains(&raw["type"].as_str()) {
                    if let Some(field) = time_field {
                        let mid = if binding.is_some() {
                            mids.get("value").and_then(Value::as_str).unwrap_or("")
                        } else {
                            c["measures"][0].as_str().unwrap_or("")
                        };
                        let (spark, hit) = view.aggregate(
                            &reference,
                            &json!({mid:definitions[mid]}),
                            &active,
                            std::slice::from_ref(&field),
                            None,
                        )?;
                        hits += u64::from(hit);
                        let mut spark = spark;
                        spark.sort_by_cached_key(|r| string_key(&r[&field]));
                        raw["sparkMonths"] =
                            json!(spark.iter().map(|r| r[&field].clone()).collect::<Vec<_>>());
                        let multiplier =
                            if binding.is_none() && definitions[mid]["format"] == "percent" {
                                100.0
                            } else {
                                1.0
                            };
                        raw["sparkData"] = json!(spark
                            .iter()
                            .map(|r| r[mid]
                                .as_f64()
                                .map(|v| json!(v * multiplier))
                                .unwrap_or(Value::Null))
                            .collect::<Vec<_>>());
                    }
                }
                computed["components"][&key] = raw;
                continue;
            }
            if let Some(b) = binding {
                let category = b["categoryField"].as_str().unwrap_or("");
                let grain = if b["timeGrain"].as_bool().unwrap_or(false) {
                    Some(
                        granularities
                            .get(&key)
                            .and_then(Value::as_str)
                            .or_else(|| raw["defaultGranularity"].as_str())
                            .unwrap_or("month")
                            .to_string(),
                    )
                } else {
                    None
                };
                if let Some(g) = &grain {
                    raw["defaultGranularity"] = json!(g);
                }
                let (mut grouped, hit) = view.aggregate(
                    &reference,
                    &definitions_value,
                    &active,
                    &[category.into()],
                    grain.as_deref(),
                )?;
                hits += u64::from(hit);
                if grain.is_some() {
                    grouped.sort_by_cached_key(|r| string_key(&r[category]));
                }
                if let Some(order) = b.get("orderBy") {
                    let mid = mids[order["target"].as_str().unwrap_or("")]
                        .as_str()
                        .unwrap_or("");
                    let direction = if order["direction"] == "desc" {
                        -1.0
                    } else {
                        1.0
                    };
                    grouped.sort_by(|a, z| {
                        a[mid]
                            .is_null()
                            .cmp(&z[mid].is_null())
                            .then_with(|| {
                                (direction * a[mid].as_f64().unwrap_or(0.0))
                                    .total_cmp(&(direction * z[mid].as_f64().unwrap_or(0.0)))
                            })
                            .then_with(|| string_key(&a[category]).cmp(&string_key(&z[category])))
                    });
                }
                let code = raw["code"].as_str().unwrap_or("").to_string();
                let mut data = if code == "t06" {
                    json!({})
                } else {
                    raw.get("data")
                        .filter(|v| v.is_object())
                        .cloned()
                        .unwrap_or(json!({}))
                };
                let displayed = |row: &Value, target: &str, mid: &str| -> Result<Value> {
                    if let Some(value) = row[mid].as_f64() {
                        rounded(
                            value * b["scale"][target].as_f64().unwrap_or(1.0),
                            m["metrics"][mid]["decimals"].as_u64().unwrap_or(2),
                        )
                    } else {
                        Ok(Value::Null)
                    }
                };
                if code == "r02" {
                    let mut points = Vec::new();
                    for row in &grouped {
                        let mut values = ["x", "y", "size"]
                            .iter()
                            .map(|target| {
                                displayed(row, target, mids[*target].as_str().unwrap_or(""))
                            })
                            .collect::<Result<Vec<_>>>()?;
                        if !row[category].is_null()
                            && row[category] != ""
                            && values.iter().all(|v| !v.is_null())
                            && values[2].as_f64().is_some_and(|n| n >= 0.0)
                        {
                            values.push(row[category].clone());
                            points.push(Value::Array(values));
                        }
                    }
                    data["clusters"] = json!(points);
                } else {
                    let target = b["categoryTarget"].as_str().unwrap_or("");
                    data[target] = json!(grouped
                        .iter()
                        .filter(|r| !r[category].is_null())
                        .map(|r| r[category].clone())
                        .collect::<Vec<_>>());
                    for (target, mid) in &mids {
                        data[target] = json!(grouped
                            .iter()
                            .filter(|r| !r[category].is_null())
                            .map(|r| displayed(r, target, mid.as_str().unwrap_or("")))
                            .collect::<Result<Vec<_>>>()?);
                    }
                }
                raw["data"] = if code == "t06" {
                    json!({"month":data,"quarter":data})
                } else {
                    data
                };
                raw["hasGranularity"] = json!(b["timeGrain"].as_bool().unwrap_or(false));
                computed["components"][&key] = raw;
            } else {
                let mut groups = vec![c["x"].as_str().unwrap_or("").to_string()];
                if let Some(s) = c["series"].as_str().filter(|s| !s.is_empty()) {
                    groups.push(s.into());
                }
                let (grouped, hit) =
                    view.aggregate(&reference, &definitions_value, &active, &groups, None)?;
                hits += u64::from(hit);
                computed["grouped"][&key]=json!(grouped.iter().map(|r|json!({"x":r[&groups[0]],"group":groups.get(1).map(|k|r[k].clone()),"values":definitions.keys().map(|k|(k.clone(),r[k].clone())).collect::<Map<_,_>>()})).collect::<Vec<_>>());
            }
        }
        if include_filter_options {
            for f in &declared_filters {
                if f["op"] == "in" {
                    let id = f["id"].as_str().unwrap_or("");
                    let options = self.filter_options_with(&doc, id, "", 0, 100, &mut live)?;
                    computed["filterOptions"][id] = options["values"].clone();
                    computed["filterPages"][id] = options;
                }
            }
        }
        doc["snapshot"]["localMode"] = json!(true);
        computed["cacheHits"] = json!(hits);
        computed["durationMs"] = json!(started.elapsed().as_secs_f64() * 1000.0);
        computed["sourceRows"] = Value::Object(
            refs.iter()
                .map(|(k, v)| (k.clone(), v["rowCount"].clone()))
                .collect(),
        );
        computed["sourceBytes"] = json!(refs
            .values()
            .map(|r| r["bytes"].as_u64().unwrap_or(0))
            .sum::<u64>());
        doc["computed"] = computed;
        let size = json_bytes(&doc)?.len();
        require(
            size <= 16 * 1024 * 1024,
            "Artifact exceeds 16 MiB",
            "PAYLOAD_TOO_LARGE",
        )?;
        doc["computed"]["responseBytes"] = json!(size);
        Ok(doc)
    }
    pub fn filter_options(
        &self,
        document: &Value,
        id: &str,
        search: &str,
        offset: u64,
        limit: usize,
    ) -> Result<Value> {
        let mut live = LiveQueryRequest::new(self.queries.clone(), &document["manifest"])?;
        self.filter_options_with(document, id, search, offset, limit, &mut live)
    }
    fn filter_options_with(
        &self,
        document: &Value,
        id: &str,
        search: &str,
        offset: u64,
        limit: usize,
        live: &mut LiveQueryRequest,
    ) -> Result<Value> {
        let m = &document["manifest"];
        let filter = m["filters"]
            .as_array()
            .and_then(|a| a.iter().find(|f| f["id"] == id && f["op"] == "in"))
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Unknown selection filter"))?;
        let ids = filter["componentIds"]
            .as_array()
            .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Filter consumers must be declared"))?;
        let refs = &document["snapshot"]["datasetRefs"];
        let mut consumers = Vec::new();
        let mut live_ids = Vec::new();
        for id in ids {
            let c = &m["components"][id.as_str().unwrap_or("")];
            if let Some(ds) = c["datasetId"].as_str() {
                if let Some(r) = refs.get(ds) {
                    consumers.push(r.clone());
                }
                if m["datasets"][ds]["mode"] == "live" && !live_ids.contains(&ds.to_string()) {
                    live_ids.push(ds.to_string());
                }
            }
        }
        let field = filter["field"].as_str().unwrap_or("");
        if live_ids.is_empty() {
            return self
                .data
                .option_page(&consumers, field, search, offset, limit);
        }
        let kind = m["datasets"][&live_ids[0]]["fields"][field]["type"]
            .as_str()
            .unwrap_or("");
        let mut unique = BTreeMap::new();
        for ds in live_ids {
            let reference = live.reference(&ds)?;
            for v in live.data.distinct(&reference, field, &[])? {
                unique.insert(canonical_json(&v)?, v);
            }
        }
        self.data.option_page_extra(
            &consumers,
            field,
            search,
            offset,
            limit,
            Some((kind, &unique.into_values().collect::<Vec<_>>())),
        )
    }
}
