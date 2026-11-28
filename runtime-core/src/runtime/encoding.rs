//! Dynamic original-chart bindings retain their declared metric and grouping semantics.
use super::{
    error::{Error, Result},
    view::LocalView,
};
use serde_json::{json, Map, Value};
pub fn resolve_encoding(
    view: &LocalView,
    reference: &Value,
    manifest: &Value,
    component: &Value,
    active: &[Value],
) -> Result<Vec<Value>> {
    let binding = &component["binding"];
    let measures = binding["measures"]
        .as_object()
        .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Encoding requires bound measures"))?;
    let mut definitions = Map::new();
    for (key, mid) in measures {
        definitions.insert(
            key.clone(),
            manifest["metrics"][mid.as_str().unwrap_or("")].clone(),
        );
    }
    if let Some(attributes) = binding["attributes"].as_object() {
        definitions.extend(attributes.iter().map(|(k, v)| (k.clone(), v.clone())));
    }
    let mut groups = vec![binding["categoryField"].as_str().unwrap_or("").to_string()];
    if let Some(series) = binding["seriesField"].as_str().filter(|s| !s.is_empty()) {
        groups.push(series.into());
    }
    let (rows, _) = view.aggregate(
        reference,
        &Value::Object(definitions.clone()),
        active,
        &groups,
        None,
    )?;
    Ok(rows.iter().map(|r|json!({"category":r[&groups[0]],"series":groups.get(1).map(|g|r[g].clone()),"values":definitions.keys().map(|k|(k.clone(),r[k].clone())).collect::<Map<_,_>>()})).collect())
}
