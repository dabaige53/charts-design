//! Read-only diagnostics preserve definition, immutable-data, and component checks.
use super::{
    assets,
    error::{Error, Result},
    model,
    service::Service,
    statistics,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::time::Instant;
use uuid::Uuid;
pub fn data_version(doc: &Value) -> Result<String> {
    Ok(format!(
        "{:x}",
        Sha256::digest(super::serialization::python_json(&doc["snapshot"], true, true)?.as_bytes())
    )[..20]
        .to_owned())
}
pub fn document_fingerprint(doc: &Value) -> Result<String> {
    Ok(format!(
        "{:x}",
        Sha256::digest(super::serialization::python_json(doc, true, true)?.as_bytes())
    ))
}
// Keep the diagnostic record's identity and measurement fields explicit at each check.
#[allow(clippy::too_many_arguments)]
fn checked<F: FnOnce() -> Result<()>>(
    checks: &mut Vec<Value>,
    events: &mut Vec<Value>,
    id: &str,
    board: &str,
    revision: &Value,
    name: &str,
    component: Option<&str>,
    work: F,
) {
    let start = Instant::now();
    let result = work();
    checks.push(match result{Ok(())=>json!({"check":name,"componentId":component,"status":"passed"}),Err(error)=>json!({"check":name,"componentId":component,"status":"failed","code":error.code,"message":error.message,"action":"检查该组件绑定和项目数据文件"})});
    events.push(json!({"requestId":id,"tool":"dashboard_doctor","stage":name,"code":"","bytes":0,"dashboardId":board,"durationMs":start.elapsed().as_secs_f64()*1000.0,"revision":revision}));
}
pub fn diagnose(
    service: &Service,
    doc: &Value,
    mode: &str,
    previous: Option<&Value>,
) -> Result<Value> {
    let board = super::service::string(doc, "id")?;
    let id = Uuid::new_v4().simple().to_string();
    let mut checks = Vec::new();
    let mut events = Vec::new();
    if let Some(previous) = previous {
        if let Some(check) = previous["checks"].as_array().and_then(|v| v.first()) {
            checks.push(check.clone());
        } else {
            checked(
                &mut checks,
                &mut events,
                &id,
                board,
                &doc["revision"],
                "definition",
                None,
                || model::validate(doc),
            );
        }
    } else {
        checked(
            &mut checks,
            &mut events,
            &id,
            board,
            &doc["revision"],
            "definition",
            None,
            || model::validate(doc),
        );
    }
    for (collection, prefix) in [
        ("datasetRefs", "dataset:"),
        ("componentDataRefs", "component-data:"),
    ] {
        for (key, reference) in doc["snapshot"][collection]
            .as_object()
            .into_iter()
            .flatten()
        {
            checked(
                &mut checks,
                &mut events,
                &id,
                board,
                &doc["revision"],
                &format!("{prefix}{key}"),
                None,
                || {
                    service
                        .store
                        .data
                        .describe(super::service::string(reference, "version")?)?;
                    Ok(())
                },
            );
        }
    }
    let mut ids: Vec<String> = if mode == "quick" {
        doc["manifest"]["layout"]["desktop"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|v| v["y"].as_f64().unwrap_or(0.0) < 8.0)
            .filter_map(|v| v["id"].as_str().map(String::from))
            .collect()
    } else {
        doc["manifest"]["components"]
            .as_object()
            .into_iter()
            .flatten()
            .map(|(key, _)| key.clone())
            .collect()
    };
    if let Some(previous) = previous {
        if checks.iter().all(|v| v["status"] == "passed") {
            checks.extend(
                previous["checks"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter(|v| v["check"] == "component")
                    .cloned(),
            );
            ids.clear();
        }
    }
    for key in ids {
        checked(
            &mut checks,
            &mut events,
            &id,
            board,
            &doc["revision"],
            "component",
            Some(&key),
            || {
                service.views.check_component(doc, &key)?;
                if doc["manifest"]["components"][&key]["kind"] == "statistical" {
                    let mut selected = doc.clone();
                    selected["manifest"]["components"] =
                        json!({&key:doc["manifest"]["components"][&key]});
                    let selected = service.store.statistical_document(&selected)?;
                    let artifact = statistics::render_statistical(&selected, &key, "svg")?;
                    if artifact.get("error").is_some() {
                        return Err(Error::new(
                            artifact["code"]
                                .as_str()
                                .unwrap_or("STATISTICAL_RENDER_FAILED"),
                            artifact["error"]
                                .as_str()
                                .unwrap_or("Statistical rendering failed"),
                        ));
                    }
                }
                Ok(())
            },
        );
    }
    let warnings: Vec<Value> = doc["manifest"]["annotations"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|note| {
            note["componentId"]
                .as_str()
                .is_some_and(|key| doc["manifest"]["components"].get(key).is_none())
        })
        .map(|note| json!({"code":"ANNOTATION_ANCHOR_UNAVAILABLE","annotationId":note["id"]}))
        .collect();
    let passed = checks.iter().all(|check| check["status"] == "passed");
    service.transport.log_many(&events)?;
    Ok(
        json!({"dashboardId":board,"requestId":id,"revision":doc["revision"],"dataVersion":data_version(doc)?,"uiBuildId":assets::ui_build_id(),"backendBuildId":assets::backend_build_id(),"mode":mode,"checks":checks,"warnings":warnings,"passed":passed}),
    )
}
