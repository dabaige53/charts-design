//! Packaged declarations are data; native validators and services execute them.
use super::error::{require, Error, Result};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    sync::OnceLock,
};

pub const DOCUMENT_WRITES: &[&str] = &[
    "dashboard_create",
    "dashboard_patch",
    "dashboard_restore",
    "dataset_import",
    "dataset_attach",
    "query_execute",
    "dashboard_migrate",
    "dashboard_migration_rollback",
];
pub const WRITE_RESPONSE_HELP: &str = " MCP defaults to a summary without document: dashboardId, revision, affectedComponentIds, counts and operation metadata. Use top-level revision for the next expectedRevision. Request responseMode=full or dashboard_get when the document is needed. Data-write summaries also return dataset fields/sourceId/metrics and read-only nextCalls; reuse the returned metric IDs rather than deriving them. A draft write is not a checked checkpoint; use dashboard_submit to check and save it.";

pub fn data() -> &'static Value {
    static DATA: OnceLock<Value> = OnceLock::new();
    DATA.get_or_init(|| {
        serde_json::from_str(include_str!("../../resources/contract.json"))
            .expect("packaged tool declarations")
    })
}
pub fn member(collection: &str, name: &str) -> bool {
    data()[collection]
        .as_array()
        .is_some_and(|a| a.iter().any(|v| v.as_str() == Some(name)))
}
pub fn author_tool(name: &str) -> bool {
    member("authorTools", name)
}
pub fn maintenance_tool(name: &str) -> bool {
    member("maintenanceTools", name)
}
pub fn read_only(name: &str) -> bool {
    member("readOnly", name)
}
pub fn tool_schema(name: &str) -> Option<&'static Value> {
    data()["tools"].get(name).map(|v| &v["inputSchema"])
}
pub fn validate_args(name: &str, args: &Value) -> Result<()> {
    static VALIDATORS: OnceLock<
        std::result::Result<BTreeMap<String, jsonschema::Validator>, String>,
    > = OnceLock::new();
    let validators = VALIDATORS
        .get_or_init(|| {
            data()["tools"]
                .as_object()
                .expect("tools object")
                .iter()
                .map(|(name, tool)| {
                    jsonschema::validator_for(&tool["inputSchema"])
                        .map(|validator| (name.clone(), validator))
                        .map_err(|e| format!("{name}: {e}"))
                })
                .collect()
        })
        .as_ref()
        .map_err(|error| Error::new("INVALID_SCHEMA", error))?;
    let validator = validators.get(name).ok_or_else(|| {
        Error::new("UNKNOWN_TOOL", format!("Unsupported tool: {name}")).with_status(404)
    })?;
    validator
        .validate(args)
        .map_err(|e| Error::new("INVALID_ARGUMENT", e.to_string()))
}
pub fn tool_definitions(remote: bool, include_clients: bool) -> Vec<Value> {
    data()["tools"].as_object().expect("tools object").iter().filter_map(|(name, value)| {
        if maintenance_tool(name) || remote && name == "dashboard_export_open" || !include_clients && !author_tool(name) { return None; }
        let mut definition = value.clone();
        definition["name"] = json!(name);
        definition["inputSchema"]["properties"]["projectRoot"] = json!({"type":"string", "description": if remote { "Project name inside the server workspace. Pass it on every call; omission uses the startup default, never the last project." } else { "Absolute project asset directory. Pass it on every project request; omission uses only the startup default, never the last project." }});
        if DOCUMENT_WRITES.contains(&name.as_str()) {
            definition["description"] = json!(format!("{}{}", definition["description"].as_str().unwrap_or_default(), WRITE_RESPONSE_HELP));
            definition["inputSchema"]["properties"]["responseMode"] = json!({"type":"string","enum":["summary","full"],"default":"summary","description":"summary returns a compact write receipt; full retains the complete document for editors. MCP only."});
        }
        definition["annotations"] = json!({"readOnlyHint":read_only(name),"destructiveHint":member("destructive",name),"idempotentHint":name=="dashboard_share_publish" || read_only(name) && name!="runtime_keepalive","openWorldHint":(["dashboard_share_publish","dashboard_share_replace","dashboard_share_delete"].contains(&name.as_str()))});
        if !author_tool(name) { definition["_meta"] = json!({"ui":{"visibility":["app"]}}); }
        if name == "dashboard_preview" && super::assets::ui_build_id() != "unavailable" { definition["_meta"] = json!({"ui":{"resourceUri":super::assets::ui_resource_uri()}}); }
        Some(definition)
    }).collect()
}
pub fn discoverable_contract(remote: bool) -> Value {
    let mut contract = data()["contract"].clone();
    let definitions = tool_definitions(remote, true);
    let mut tools = serde_json::Map::new();
    let mut clients = serde_json::Map::new();
    for mut item in definitions {
        let name = item["name"].as_str().unwrap().to_owned();
        item.as_object_mut().unwrap().remove("name");
        if author_tool(&name) {
            tools.insert(name, item);
        } else {
            clients.insert(name, item["inputSchema"].clone());
        }
    }
    contract["tools"] = tools.into();
    contract["clientTools"] = clients.into();
    contract["operationSchemas"] = data()["operationSchemas"].clone();
    contract["projectRouting"] = json!({"selector":"projectRoot","scope":"request","description":if remote {"Workspace project name"} else {"Absolute project asset directory"},"omitted":"startup project default or legacy store; never the last selected project","preview":"bind once from result.projectRoot; include it in all subsequent calls, including chunks"});
    contract["statistical"] = super::statistics::statistical_declarations();
    contract
}
pub fn write_receipt(name: &str, args: &Value, result: &Value) -> Result<Value> {
    if !DOCUMENT_WRITES.contains(&name) || !result["document"].is_object() || result["ok"] == false
    {
        return Ok(result.clone());
    }
    let doc = &result["document"];
    let manifest = &doc["manifest"];
    let components = manifest["components"]
        .as_object()
        .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Missing components"))?;
    let mut receipt = result.clone();
    let output = receipt.as_object_mut().unwrap();
    output.remove("document");
    output.remove("statisticalArtifacts");
    let mut affected = BTreeSet::new();
    match name {
        "dashboard_patch" => {
            for operation in args["operations"].as_array().into_iter().flatten() {
                match operation["op"].as_str().unwrap_or_default() {
                    "put_component" | "remove_component" | "set_original_chart" => {
                        if let Some(id) = operation["id"].as_str() {
                            affected.insert(id.to_owned());
                        }
                    }
                    "put_metric"
                    | "put_dataset"
                    | "put_dataset_ref"
                    | "set_filters"
                    | "set_layout"
                    | "apply_layout_template" => affected.extend(components.keys().cloned()),
                    _ => {}
                }
            }
        }
        "dataset_import" | "dataset_attach" | "query_execute" => {
            let id = args["datasetId"]
                .as_str()
                .ok_or_else(|| Error::new("INVALID_ARGUMENT", "datasetId required"))?;
            let meta = &manifest["datasets"][id];
            let reference = &doc["snapshot"]["datasetRefs"][id];
            let metrics: serde_json::Map<String, Value> = manifest["metrics"]
                .as_object()
                .into_iter()
                .flatten()
                .filter(|(_, m)| m["datasetId"] == id)
                .map(|(k, v)| (k.clone(), v.clone()))
                .collect();
            let mut dataset = json!({"id":id,"mode":meta.get("mode").unwrap_or(&json!("snapshot")),"fields":meta["fields"],"sourceId":meta["sourceId"],"metrics":metrics});
            if reference.is_object() {
                dataset["rowCount"] = reference["rowCount"].clone();
                dataset["version"] = reference["version"].clone();
            } else if dataset["mode"] != "live" {
                dataset["rowCount"] = json!(doc["snapshot"]["datasets"][id]
                    .as_array()
                    .map_or(0, Vec::len));
            }
            receipt["dataset"] = dataset;
            let mut context = json!({"dashboardId":doc["id"]});
            if !result["projectRoot"].is_null() {
                context["projectRoot"] = result["projectRoot"].clone();
            }
            let mut preview = context.clone();
            preview["datasetId"] = json!(id);
            preview["expectedRevision"] = doc["revision"].clone();
            preview["limit"] = json!(20);
            if !doc["dataVersion"].is_null() {
                preview["dataVersion"] = doc["dataVersion"].clone();
            }
            receipt["nextCalls"] = json!([{"tool":"dataset_preview","arguments":preview},{"tool":"dashboard_get","arguments":context}]);
            affected.extend(
                components
                    .iter()
                    .filter(|(_, c)| c["datasetId"] == id || c["binding"]["datasetId"] == id)
                    .map(|(k, _)| k.clone()),
            );
        }
        _ => affected.extend(components.keys().cloned()),
    }
    receipt["ok"] = json!(true);
    receipt["dashboardId"] = doc["id"].clone();
    receipt["revision"] = doc["revision"].clone();
    receipt["affectedComponentIds"] = json!(affected);
    receipt["counts"] = json!({"components":components.len(),"datasets":manifest["datasets"].as_object().map_or(0,|v|v.len()),"metrics":manifest["metrics"].as_object().map_or(0,|v|v.len())});
    receipt["readTool"] = json!("dashboard_get");
    Ok(receipt)
}
pub fn operation_schema(name: &str) -> Result<&'static Value> {
    let schemas = data()["operationSchemas"].as_array();
    if let Some(found) =
        schemas.and_then(|a| a.iter().find(|s| s["properties"]["op"]["const"] == name))
    {
        return Ok(found);
    }
    if let Some(found) = data()["operationSchemas"].get(name) {
        return Ok(found);
    }
    require(
        false,
        format!("Unknown operation: {name}"),
        "INVALID_OPERATION",
    )?;
    unreachable!()
}
