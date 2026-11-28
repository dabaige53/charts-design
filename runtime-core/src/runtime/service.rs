//! Native, transport-independent command service; all mutations are explicit.
use super::{
    assets, contract,
    data::LocalData,
    dataset_authoring, discovery, doctor,
    error::{require, Error, Result},
    exports, model,
    query::QueryRunner,
    statistics,
    store::Store,
    transport::Transport,
    versions::Versions,
    view::LocalView,
};
use serde_json::{json, Map, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Path, PathBuf},
    sync::Mutex,
    time::Instant,
};
use uuid::Uuid;

pub fn string<'a>(args: &'a Value, key: &str) -> Result<&'a str> {
    args[key]
        .as_str()
        .ok_or_else(|| Error::new("INVALID_ARGUMENT", format!("{key} must be a string")))
}
pub fn integer(args: &Value, key: &str) -> Result<i64> {
    args[key]
        .as_i64()
        .ok_or_else(|| Error::new("INVALID_ARGUMENT", format!("{key} must be an integer")))
}
pub fn unsigned(args: &Value, key: &str, default: u64) -> Result<u64> {
    args.get(key).map_or(Ok(default), |v| {
        v.as_u64().ok_or_else(|| {
            Error::new(
                "INVALID_ARGUMENT",
                format!("{key} must be a non-negative integer"),
            )
        })
    })
}
fn array<'a>(args: &'a Value, key: &str) -> Result<&'a [Value]> {
    args.get(key).map_or(Ok(&[][..]), |v| {
        v.as_array()
            .map(Vec::as_slice)
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", format!("{key} must be an array")))
    })
}
fn strings(value: Option<&Value>) -> Result<Option<Vec<String>>> {
    value
        .map(|v| {
            v.as_array()
                .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Expected an array of strings"))?
                .iter()
                .map(|v| {
                    v.as_str().map(String::from).ok_or_else(|| {
                        Error::new("INVALID_ARGUMENT", "Expected an array of strings")
                    })
                })
                .collect()
        })
        .transpose()
}
pub fn has_live(doc: &Value) -> bool {
    doc["manifest"]["datasets"]
        .as_object()
        .is_some_and(|m| m.values().any(|v| v["mode"] == "live"))
}
fn live_ids(doc: &Value) -> BTreeSet<String> {
    doc["manifest"]["datasets"]
        .as_object()
        .into_iter()
        .flatten()
        .filter(|(_, v)| v["mode"] == "live")
        .map(|(k, _)| k.clone())
        .collect()
}

pub struct Service {
    pub store: Store,
    pub queries: QueryRunner,
    pub views: LocalView,
    pub project_root: Option<PathBuf>,
    pub project_name: String,
    pub transport: Transport,
    doctor_reports: Mutex<BTreeMap<String, (String, Value)>>,
}
impl Service {
    pub fn new(root: &Path, sources: Option<&Path>, project: Option<&Path>) -> Result<Self> {
        let store = Store::new(root, project)?;
        let queries = QueryRunner::new(sources)?;
        let views = LocalView::new(store.data.clone(), Some(queries.clone()));
        let transport = Transport::new(&store.runtime_root)?;
        Ok(Self {
            project_root: store.project_root.clone(),
            project_name: store
                .project_root
                .as_ref()
                .and_then(|p| p.file_name())
                .map(|v| v.to_string_lossy().to_string())
                .unwrap_or_default(),
            store,
            queries,
            views,
            transport,
            doctor_reports: Mutex::new(BTreeMap::new()),
        })
    }
    pub fn call(&self, tool: &str, args: &Value) -> Result<Value> {
        let id = Uuid::new_v4().simple().to_string();
        let start = Instant::now();
        match self.execute(tool, args, None) {
            Ok(mut result) => {
                if matches!(tool, "dashboard_view" | "dashboard_filter_options") {
                    result["requestId"] = json!(id);
                    if args["compactRecords"] == true {
                        compact_records(&mut result);
                    }
                    self.transport.log(&id,tool,"query_complete","",0,&json!({"dashboardId":args["dashboardId"],"durationMs":start.elapsed().as_secs_f64()*1000.0,"revision":result["revision"],"cacheHits":result["computed"]["cacheHits"]}))?;
                }
                Ok(result)
            }
            Err(mut error) => {
                error.request_id = Some(id.clone());
                self.transport.log(&id,tool,"failed",&error.code,0,&json!({"dashboardId":args["dashboardId"],"durationMs":start.elapsed().as_secs_f64()*1000.0}))?;
                Err(error)
            }
        }
    }
    pub fn reading_document(
        &self,
        board: &str,
        args: &Value,
        pinned: Option<&Value>,
    ) -> Result<Value> {
        let mut doc = if let Some(value) = pinned {
            value.clone()
        } else {
            self.store.get(board, false)?
        };
        let expected = args
            .get("expectedRevision")
            .cloned()
            .unwrap_or_else(|| doc["revision"].clone());
        if pinned.is_none() && self.project_root.is_some() && expected != doc["revision"] {
            match self.store.readable(board) {
                Ok(saved) if saved["revision"] == expected => doc = saved,
                Ok(_) => {}
                Err(e) if e.code == "NO_SAVED_VERSION" => {}
                Err(e) => return Err(e),
            }
        }
        require(
            expected == doc["revision"],
            "Data changed; reload the dashboard",
            "REVISION_CONFLICT",
        )
        .map_err(|e| e.with_status(409))?;
        if let Some(version) = args.get("dataVersion") {
            require(
                *version == doctor::data_version(&doc)?,
                "Data version changed; reload",
                "REVISION_CONFLICT",
            )?;
        }
        Ok(doc)
    }
    pub fn live_dataset(&self, doc: &Value, id: &str) -> Result<(LocalData, Value)> {
        let meta = &doc["manifest"]["datasets"][id];
        require(
            meta["mode"] == "live",
            "Dataset is not live",
            "INVALID_ARGUMENT",
        )?;
        let source_id = string(meta, "sourceId")?;
        let query = &doc["manifest"]["sources"][source_id]["query"];
        let output = self.queries.execute(
            string(query, "connection")?,
            string(query, "sql")?,
            query.get("parameters"),
            30.0,
            Some(&meta["fields"]),
            query["engine"].as_str(),
        )?;
        let data = LocalData::new(None)?;
        let reference = data.import_rows(&output.rows, &output.fields)?;
        Ok((data, reference))
    }
    pub fn doctor(&self, doc: &Value, mode: &str, reuse: bool) -> Result<Value> {
        require(
            matches!(mode, "quick" | "full"),
            "Doctor mode must be quick or full",
            "INVALID_ARGUMENT",
        )?;
        let board = string(doc, "id")?;
        let fingerprint = doctor::document_fingerprint(doc)?;
        let previous = if reuse && !has_live(doc) {
            self.doctor_reports
                .lock()
                .map_err(|_| Error::new("INTERNAL_ERROR", "Doctor lock failed"))?
                .get(board)
                .filter(|(key, _)| *key == fingerprint)
                .map(|(_, v)| v.clone())
        } else {
            None
        };
        let report = doctor::diagnose(self, doc, mode, previous.as_ref())?;
        let mut reports = self
            .doctor_reports
            .lock()
            .map_err(|_| Error::new("INTERNAL_ERROR", "Doctor lock failed"))?;
        if report["passed"] != true {
            reports.remove(board);
        } else if mode == "full" {
            reports.insert(board.into(), (fingerprint, report.clone()));
        }
        drop(reports);
        let directory = self.store.runtime_root.join("doctor");
        fs::create_dir_all(&directory)?;
        let temporary = directory.join(format!("{board}.{}.tmp", Uuid::new_v4().simple()));
        fs::write(&temporary, serde_json::to_vec(&report)?)?;
        fs::rename(temporary, directory.join(format!("{board}.json")))?;
        Ok(report)
    }
    fn preload_filter_options(&self, doc: &Value, filter: &Value) -> Result<Value> {
        use sha2::{Digest, Sha256};
        let id = string(filter, "id")?;
        let versions: BTreeSet<&str> = array(filter, "componentIds")?
            .iter()
            .filter_map(Value::as_str)
            .filter_map(|key| doc["manifest"]["components"][key]["datasetId"].as_str())
            .filter_map(|dataset| doc["snapshot"]["datasetRefs"][dataset]["version"].as_str())
            .collect();
        let key = format!(
            "{:x}",
            Sha256::digest(serde_json::to_vec(&json!([
                assets::backend_build_id(),
                filter["field"],
                versions
            ]))?)
        );
        let directory = self.store.runtime_root.join("filter-options");
        exports::private_directory(&directory)?;
        let path = directory.join(format!("{key}.json"));
        if let Ok(bytes) = fs::read(&path) {
            if let Ok(page) = serde_json::from_slice::<Value>(&bytes) {
                if page["values"].is_array() && page["offset"] == 0 {
                    return Ok(page);
                }
            }
        }
        let page = self.views.filter_options(doc, id, "", 0, 100)?;
        let temporary = directory.join(format!("{key}.{}.tmp", Uuid::new_v4().simple()));
        fs::write(&temporary, serde_json::to_vec(&page)?)?;
        exports::private_file(&temporary)?;
        fs::rename(&temporary, path)?;
        Ok(page)
    }
    fn restore_export(&self, board: &str, id: &str, format: &str) -> Result<()> {
        if self.store.database.is_none() {
            return Ok(());
        }
        match exports::export_path(&self.store.root, board, id, format) {
            Ok(_) => return Ok(()),
            Err(error) if error.code == "NOT_FOUND" => {}
            Err(error) => return Err(error),
        }
        let target = exports::export_target(&self.store.root, board, id, format)?;
        let project = self
            .project_root
            .as_ref()
            .ok_or_else(|| Error::new("PROJECT_REQUIRED", "Cloud exports require a project"))?
            .canonicalize()?;
        let relative = target
            .strip_prefix(&project)
            .map_err(|_| Error::new("INVALID_PATH", "Export must remain in its project"))?;
        let relative = relative.to_string_lossy().replace('\\', "/");
        require(
            super::cloud::restore_file(&self.store.project, &relative, &target)?,
            "Export file not found",
            "NOT_FOUND",
        )
    }
    fn patch_operations(&self, current: &Value, operations: &[Value]) -> Result<Vec<Value>> {
        let mut result = operations.to_vec();
        let live_sources: BTreeSet<&str> = current["manifest"]["datasets"]
            .as_object()
            .into_iter()
            .flatten()
            .filter(|(_, v)| v["mode"] == "live")
            .filter_map(|(_, v)| v["sourceId"].as_str())
            .collect();
        for op in &mut result {
            let name = string(op, "op")?.to_owned();
            require(
                name != "put_live_dataset"
                    && !(name == "put_source"
                        && op["id"].as_str().is_some_and(|v| live_sources.contains(v))),
                "Use query_execute to configure live SQL",
                "INVALID_OPERATION",
            )?;
            require(
                name != "set_chart",
                "Use set_original_chart with an original code",
                "UNSUPPORTED_CHART_FAMILY",
            )?;
            if name == "put_component" && op["value"]["kind"] == "chart" {
                let id = string(op, "id")?;
                let previous = &current["manifest"]["components"][id];
                require(previous["kind"]=="chart" && previous["chartType"]==op["value"]["chartType"],"Use kind=legacy, family=chart with a preset code or config.renderer=echarts/html for custom charts","UNSUPPORTED_CHART_FAMILY")?;
            }
            if name == "put_source" && op["value"].is_object() {
                op["value"]["verification"] = json!("supplied");
            }
        }
        Ok(result)
    }
    pub fn execute(&self, tool: &str, args: &Value, pinned: Option<&Value>) -> Result<Value> {
        require(
            args.is_object(),
            "Tool arguments must be an object",
            "INVALID_ARGUMENT",
        )?;
        let start = Instant::now();
        let mut result = self.call_raw(tool, args, pinned)?;
        if self.store.database.is_some() {
            if let Some(exported) = result.get("export").and_then(Value::as_object) {
                let project = self
                    .project_root
                    .as_ref()
                    .ok_or_else(|| {
                        Error::new("PROJECT_REQUIRED", "Cloud exports require a project")
                    })?
                    .canonicalize()?;
                for key in ["path", "siteArchive"] {
                    if let Some(path) = exported.get(key).and_then(Value::as_str) {
                        let target = Path::new(path).canonicalize()?;
                        let relative = target.strip_prefix(&project).map_err(|_| {
                            Error::new("INVALID_PATH", "Export must remain in its project")
                        })?;
                        super::cloud::save_file(
                            &self.store.project,
                            &relative.to_string_lossy().replace('\\', "/"),
                            &target,
                        )?;
                    }
                }
            }
        }
        if result["document"].is_object() {
            let mut doc = result["document"].clone();
            if self.project_root.is_some() && tool != "dashboard_view" {
                doc["dataVersion"] = json!(doctor::data_version(&doc)?);
                doc["loading"] = self.store.config["loading"].clone();
                doc["progressive"] = json!(true);
                if !self.store.cos_enabled {
                    doc["computed"] = json!({"components":{},"tables":{},"grouped":{},"filterOptions":{},"filterPages":{}});
                }
                if !self.store.cos_enabled
                    && matches!(
                        tool,
                        "dashboard_preview" | "dashboard_refresh" | "dashboard_get"
                    )
                {
                    let preload = self.store.config["loading"]["preloadFilterIds"]
                        .as_array()
                        .cloned()
                        .unwrap_or_default();
                    for filter in doc["manifest"]["filters"]
                        .as_array()
                        .cloned()
                        .unwrap_or_default()
                    {
                        let id = string(&filter, "id")?;
                        if filter["op"] != "in" || !preload.iter().any(|v| v == id) {
                            continue;
                        }
                        let live = filter["componentIds"]
                            .as_array()
                            .into_iter()
                            .flatten()
                            .filter_map(Value::as_str)
                            .any(|key| {
                                doc["manifest"]["datasets"][doc["manifest"]["components"][key]
                                    ["datasetId"]
                                    .as_str()
                                    .unwrap_or("")]["mode"]
                                    == "live"
                            });
                        if live {
                            continue;
                        }
                        let page = self.preload_filter_options(&doc, &filter)?;
                        doc["computed"]["filterOptions"][id] = page["values"].clone();
                        doc["computed"]["filterPages"][id] = page;
                    }
                }
                result["document"] = doc;
                return Ok(result);
            }
            if matches!(
                tool,
                "dashboard_preview"
                    | "dashboard_view"
                    | "dashboard_refresh"
                    | "dashboard_migration_rollback"
            ) || args["dataMode"] == "local"
                || doc["snapshot"]["localMode"] == true
                || doc["snapshot"]["datasetRefs"]
                    .as_object()
                    .is_some_and(|v| !v.is_empty())
            {
                let mut tables = args.get("tableStates").cloned();
                let mut grains = args.get("granularities").cloned();
                if tool == "dashboard_refresh" {
                    for state in [&mut tables, &mut grains].into_iter().flatten() {
                        if let Some(state) = state.as_object_mut() {
                            state.retain(|key, _| doc["manifest"]["components"].get(key).is_some());
                        }
                    }
                }
                doc = self.views.prepare(
                    &self.store.compact(&doc)?,
                    if tool == "dashboard_refresh" {
                        None
                    } else {
                        args.get("filters")
                    },
                    tables.as_ref(),
                    grains.as_ref(),
                )?;
                if has_live(&doc) {
                    result["transient"] = json!(true);
                }
            }
            result["statisticalArtifacts"] =
                statistics::statistical_artifacts(&self.store.statistical_document(&doc)?);
            if doc["computed"].is_object() {
                doc["computed"]["totalDurationMs"] = json!(start.elapsed().as_secs_f64() * 1000.0);
            }
            result["document"] = doc;
        }
        if result["computed"].is_object() {
            result["computed"]["totalDurationMs"] = json!(start.elapsed().as_secs_f64() * 1000.0);
        }
        Ok(result)
    }
    fn document(&self, board: &str, pinned: Option<&Value>) -> Result<Value> {
        pinned.map_or_else(|| self.store.get(board, false), |v| Ok(v.clone()))
    }
    fn call_raw(&self, tool: &str, args: &Value, pinned: Option<&Value>) -> Result<Value> {
        let board = args["dashboardId"].as_str().unwrap_or("");
        match tool {
            "runtime_keepalive" => Ok(json!({"ok":true})),
            "runtime_result_chunk" => self.transport.chunk(args),
            "runtime_diagnostics" => self.transport.diagnostics(args),
            "runtime_report_error" => {
                let id = args["requestId"].as_str().unwrap_or("");
                let code = args["code"].as_str().unwrap_or("CLIENT_DECODE_FAILED");
                require(id.len() <= 64, "Invalid request ID", "INVALID_ARGUMENT")?;
                require(
                    [
                        "CLIENT_DECODE_FAILED",
                        "CHUNK_MISMATCH",
                        "RESULT_EXPIRED",
                        "CLIENT_RENDER_FAILED",
                        "CLIENT_DATA_APPLIED",
                        "CLIENT_DECODE_COMPLETE",
                        "CLIENT_FRAME_READY",
                    ]
                    .contains(&code),
                    "Invalid diagnostic code",
                    "INVALID_ARGUMENT",
                )?;
                if let Some(duration) = args.get("durationMs") {
                    require(
                        duration
                            .as_f64()
                            .is_some_and(|v| (0.0..=3_600_000.0).contains(&v)),
                        "Invalid duration",
                        "INVALID_ARGUMENT",
                    )?;
                }
                self.transport.log(id, "preview", "client", code, 0, args)?;
                Ok(json!({"ok":true}))
            }
            "dashboard_submit" => {
                self.project_required()?;
                let creating = args.get("createTitle").is_some();
                require(
                    creating != args.get("expectedRevision").is_some(),
                    "Supply either createTitle or expectedRevision",
                    "INVALID_ARGUMENT",
                )?;
                if creating {
                    require(
                        !string(args, "createTitle")?.is_empty()
                            && !array(args, "operations")?.is_empty(),
                        "Creating a dashboard requires a title and initial operations",
                        "INVALID_ARGUMENT",
                    )?;
                }
                let mut revision = if creating {
                    1
                } else {
                    integer(args, "expectedRevision")?
                };
                if args.get("operations").is_some() {
                    let mut ops = array(args, "operations")?.to_vec();
                    require(
                        !ops.iter().any(|v| v["op"] == "set_annotations"),
                        "Use dashboard_annotations_update for independent comment edits",
                        "INVALID_ARGUMENT",
                    )?;
                    if creating {
                        let initial = model::new_document(board, string(args, "createTitle")?)?;
                        ops = self.patch_operations(&initial, &ops)?;
                        self.store
                            .compact(&model::apply_operations(&initial, &ops)?)?;
                        self.store
                            .create(board, string(args, "createTitle")?, None)?;
                    }
                    revision = self.call_raw(
                        "dashboard_patch",
                        &json!({"dashboardId":board,"expectedRevision":revision,"operations":ops}),
                        None,
                    )?["document"]["revision"]
                        .as_i64()
                        .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Missing revision"))?;
                }
                let mut saved=self.call_raw("dashboard_checkpoint",&json!({"dashboardId":board,"expectedRevision":revision,"name":args["name"].as_str().unwrap_or("")}),None)?;
                saved["dashboardId"] = json!(board);
                saved["revision"] = json!(revision);
                Ok(saved)
            }
            "dashboard_publish" => {
                contract::validate_args(tool, args)?;
                self.project_required()?;
                let versions = Versions::new(&self.store)?;
                let status = versions.status(board)?;
                let expected = args
                    .get("expectedRevision")
                    .and_then(Value::as_i64)
                    .or(status["draftRevision"].as_i64())
                    .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Missing revision"))?;
                require(
                    status["draftRevision"] == expected,
                    "Reload before publishing",
                    "REVISION_CONFLICT",
                )?;
                let revision = integer(args, "revision")?;
                let report = self.doctor(&versions.read(board, revision)?, "full", true)?;
                if report["passed"] != true {
                    return Ok(
                        json!({"ok":false,"error":{"code":"DOCTOR_FAILED","message":"Version checks failed; the published version was not changed."},"doctor":report}),
                    );
                }
                Ok(
                    json!({"ok":true,"dashboardId":board,"publishedRevision":revision,"versionStatus":versions.publish(board,expected,revision)?}),
                )
            }
            "dashboard_annotations_update" => {
                self.project_required()?;
                if args.get("append").is_some() {
                    require(
                        !["expectedRevision", "expectedAnnotations", "annotations"]
                            .iter()
                            .any(|key| args.get(key).is_some()),
                        "Send append or a replacement list",
                        "INVALID_ARGUMENT",
                    )?;
                    self.store.append_annotation(board, &args["append"], None)
                } else {
                    require(
                        args["expectedAnnotations"].is_array(),
                        "expectedAnnotations must be an array",
                        "INVALID_ARGUMENT",
                    )?;
                    self.store.update_annotations(
                        board,
                        integer(args, "expectedRevision")?,
                        &args["expectedAnnotations"],
                        &args["annotations"],
                    )
                }
            }
            "dataset_storage_inventory"
            | "dataset_repartition"
            | "dataset_transfer_chunk"
            | "dataset_transfer_finish"
            | "dataset_transfer_status"
            | "dataset_transfer_cleanup"
            | "dashboard_share_publish"
            | "dashboard_share_status"
            | "dashboard_share_delete"
            | "dashboard_share_replace" => super::cloud::call(self, tool, args),
            "dashboard_version_status"
            | "dashboard_version_get"
            | "dashboard_version_publish"
            | "dashboard_version_delete"
            | "dashboard_version_delete_preview"
            | "dashboard_version_delete_status"
            | "dashboard_version_delete_retry"
            | "dashboard_version_query" => {
                self.project_required()?;
                let versions = Versions::new(&self.store)?;
                match tool {
                    "dashboard_version_status" => versions.status(board),
                    "dashboard_version_get" => {
                        Ok(json!({"version":versions.read(board,integer(args,"revision")?)?}))
                    }
                    "dashboard_version_query" => {
                        let operation = match string(args, "operation")? {
                            "view" => "dashboard_view",
                            "options" => "dashboard_filter_options",
                            "details" => "component_data",
                            "semantic" => "semantic_inspect",
                            "export" => "dataset_export",
                            _ => {
                                return Err(Error::new(
                                    "INVALID_ARGUMENT",
                                    "Unsupported historical operation",
                                ))
                            }
                        };
                        let doc = versions.read(board, integer(args, "revision")?)?;
                        let mut request = args.get("request").cloned().unwrap_or_else(|| json!({}));
                        require(
                            request.is_object(),
                            "request must be an object",
                            "INVALID_ARGUMENT",
                        )?;
                        request["dashboardId"] = json!(board);
                        request["expectedRevision"] = doc["revision"].clone();
                        self.execute(operation, &request, Some(&doc))
                    }
                    "dashboard_version_delete_preview" => versions.delete_preview(
                        board,
                        integer(args, "expectedRevision")?,
                        integer(args, "revision")?,
                    ),
                    "dashboard_version_delete_status" | "dashboard_version_delete_retry" => {
                        versions.delete_status(
                            board,
                            string(args, "jobId")?,
                            tool.ends_with("_retry"),
                        )
                    }
                    "dashboard_version_delete" => versions.delete_checkpoint(
                        board,
                        integer(args, "expectedRevision")?,
                        integer(args, "revision")?,
                        args["confirmation"].as_str(),
                    ),
                    _ => versions.publish(
                        board,
                        integer(args, "expectedRevision")?,
                        integer(args, "revision")?,
                    ),
                }
            }
            "dashboard_version_label" => {
                self.project_required()?;
                self.store.label_checkpoint(
                    board,
                    integer(args, "expectedRevision")?,
                    integer(args, "revision")?,
                    args["name"].as_str().unwrap_or(""),
                    args["published"].as_bool().unwrap_or(false),
                )
            }
            "dashboard_doctor" => self.doctor(
                &self.document(board, pinned)?,
                args["mode"].as_str().unwrap_or("full"),
                false,
            ),
            "dashboard_edit_begin"
            | "dashboard_edit_finish"
            | "dashboard_checkpoint"
            | "dashboard_history_diff" => {
                self.project_required()?;
                if tool == "dashboard_edit_begin" {
                    return self.store.begin(board, integer(args, "expectedRevision")?);
                }
                if tool == "dashboard_history_diff" {
                    return self.store.diff(
                        board,
                        integer(args, "fromRevision")?,
                        integer(args, "toRevision")?,
                    );
                }
                let draft = self.store.get(board, false)?;
                let expected = integer(args, "expectedRevision")?;
                require(
                    draft["revision"] == expected,
                    "Reload before checkpoint",
                    "REVISION_CONFLICT",
                )?;
                let report = self.doctor(&draft, "full", true)?;
                if report["passed"] != true {
                    return Ok(
                        json!({"ok":false,"error":{"code":"DOCTOR_FAILED","message":"Draft checks failed; no checkpoint was created. Read dashboard_get, fix the reported issues, then retry with the latest revision."},"doctor":report,"nextAction":"dashboard_get"}),
                    );
                }
                let previous = match self.store.readable(board) {
                    Ok(v) => v,
                    Err(e) if e.code == "NO_SAVED_VERSION" => draft.clone(),
                    Err(e) => return Err(e),
                };
                let checkpoint = self.store.checkpoint(
                    board,
                    expected,
                    args["name"].as_str().unwrap_or(""),
                    args["published"].as_bool().unwrap_or(false),
                    args["batchId"].as_str(),
                )?;
                Ok(
                    json!({"ok":true,"checkpoint":checkpoint,"doctor":report,"semanticChanges":semantic_diff(&previous,&draft),"nextAction":"dashboard_preview","displayPolicy":"saved-dashboard-ui"}),
                )
            }
            "runtime_info" => {
                let revision = if board.is_empty() {
                    None
                } else if self.project_root.is_some() {
                    self.store.display_revision(board)?
                } else {
                    Some(self.store.revision(board)?)
                };
                Ok(
                    json!({"version":env!("CARGO_PKG_VERSION"),"uiBuildId":assets::ui_build_id(),"backendBuildId":assets::backend_build_id(),"moduleRoot":assets::package_root(),"processId":std::process::id(),"projectRoot":self.project_root,"runtimeRoot":self.store.runtime_root,"dashboardRevision":revision,"runtimeLanguage":"rust"}),
                )
            }
            "dashboard_refresh" => {
                let mut doc = if let Some(v) = pinned {
                    v.clone()
                } else if self.project_root.is_some() {
                    self.store.readable(board)?
                } else {
                    self.store.get(board, false)?
                };
                if args.get("filters").is_some() {
                    let filters = array(args, "filters")?;
                    let mut values = Map::new();
                    for filter in filters {
                        let id = string(filter, "id")?;
                        require(
                            filter["values"].is_array(),
                            "Invalid filter override",
                            "INVALID_ARGUMENT",
                        )?;
                        values.insert(id.to_owned(), filter["values"].clone());
                    }
                    if let Some(filters) = doc["manifest"]
                        .get_mut("filters")
                        .and_then(Value::as_array_mut)
                    {
                        for filter in filters {
                            if let Some(value) = filter["id"].as_str().and_then(|id| values.get(id))
                            {
                                filter["values"] = value.clone();
                            }
                        }
                    }
                    for filter in filters {
                        if filter["id"] == "runtime-linkage" {
                            let mut filter = filter.clone();
                            filter["componentIds"] = json!(array(&filter, "componentIds")?
                                .iter()
                                .filter(|key| key
                                    .as_str()
                                    .is_some_and(|key| doc["manifest"]["components"]
                                        .get(key)
                                        .is_some()))
                                .cloned()
                                .collect::<Vec<_>>());
                            if !filter["componentIds"].as_array().unwrap().is_empty() {
                                doc["manifest"]["filters"]
                                    .as_array_mut()
                                    .unwrap()
                                    .push(filter);
                            }
                        }
                    }
                    model::validate(&doc)?;
                }
                Ok(json!({"document":doc}))
            }
            "statistical_render" => statistics::render_statistical(
                &self
                    .store
                    .statistical_document(&self.document(board, pinned)?)?,
                string(args, "componentId")?,
                args["format"].as_str().unwrap_or("svg"),
            ),
            "generation_examples" => discovery::examples(args["caseId"].as_str()),
            "chart_declarations" => discovery::declarations(args),
            "layout_templates" => Ok(discovery::layouts()),
            "chart_catalog" => Ok(discovery::catalog()),
            "chart_recommend" => {
                let doc = if board.is_empty() {
                    None
                } else {
                    Some(self.document(board, pinned)?)
                };
                discovery::recommend(args, doc.as_ref())
            }
            "dashboard_list" => Ok(json!({"dashboards":self.store.list()?})),
            "dashboard_export_open" | "dashboard_export_read" => {
                let id = string(args, "exportId")?;
                let format = string(args, "format")?;
                self.restore_export(board, id, format)?;
                if tool == "dashboard_export_open" {
                    exports::open_export(
                        &self.store.root,
                        board,
                        id,
                        format,
                        string(args, "action")?,
                    )
                } else {
                    exports::read_export(
                        &self.store.root,
                        board,
                        id,
                        format,
                        unsigned(args, "offset", 0)?,
                        unsigned(args, "limit", 262144)? as usize,
                    )
                }
            }
            "dashboard_export_site" => super::deployment::export_site(
                &self.store,
                board,
                None,
                None,
                args["dataFormat"].as_str().unwrap_or("auto"),
                false,
            ),
            "dashboard_export" => {
                let doc = self
                    .store
                    .compact(&self.reading_document(board, args, pinned)?)?;
                let format = string(args, "format")?;
                if has_live(&doc) {
                    require(
                        format == "json",
                        "实时 SQL 看板请从服务页面查看，支持导出 JSON 配置",
                        "LIVE_DATA_REQUIRES_RUNTIME",
                    )?;
                    return exports::export_dashboard(&self.store.root, &doc, "json");
                }
                let mut view = self.views.prepare(
                    &doc,
                    args.get("filters"),
                    args.get("tableStates"),
                    args.get("granularities"),
                )?;
                if format == "html" {
                    view["statisticalArtifacts"] =
                        statistics::statistical_artifacts(&self.store.statistical_document(&view)?);
                }
                exports::export_dashboard(&self.store.root, &view, format)
            }
            "dashboard_view" => {
                let doc = self.reading_document(board, args, pinned)?;
                let evidence = args.get("includeEvidence").map_or(Ok(false), |v| {
                    v.as_bool().ok_or_else(|| {
                        Error::new("INVALID_ARGUMENT", "includeEvidence must be boolean")
                    })
                })?;
                let mode = args["responseMode"].as_str().unwrap_or(if evidence {
                    "patch"
                } else {
                    "full"
                });
                require(
                    matches!(mode, "full" | "patch") && (!evidence || mode == "patch"),
                    "Component evidence requires patch response mode",
                    "INVALID_ARGUMENT",
                )?;
                if mode == "patch" {
                    let ids = strings(args.get("componentIds"))?.unwrap_or_else(|| {
                        doc["manifest"]["components"]
                            .as_object()
                            .unwrap()
                            .keys()
                            .cloned()
                            .collect()
                    });
                    let mut seen = BTreeSet::new();
                    let ids: Vec<String> =
                        ids.into_iter().filter(|v| seen.insert(v.clone())).collect();
                    let options = args.get("includeFilterOptions").map_or(Ok(false), |v| {
                        v.as_bool().ok_or_else(|| {
                            Error::new("INVALID_ARGUMENT", "includeFilterOptions must be boolean")
                        })
                    })?;
                    let mut states = args
                        .get("tableStates")
                        .cloned()
                        .unwrap_or_else(|| json!({}));
                    if self.project_root.is_some() {
                        let object = states.as_object_mut().ok_or_else(|| {
                            Error::new("INVALID_ARGUMENT", "tableStates must be an object")
                        })?;
                        for id in &ids {
                            object.entry(id.clone()).or_insert_with(
                                || json!({"pageSize":self.store.config["loading"]["pageSize"]}),
                            );
                        }
                    }
                    let doc = self.views.prepare_select(
                        &self.store.compact(&doc)?,
                        args.get("filters"),
                        Some(&states),
                        args.get("granularities"),
                        Some(&ids),
                        options,
                    )?;
                    let mut selected = doc.clone();
                    selected["manifest"]["components"] = Value::Object(
                        ids.iter()
                            .filter(|id| {
                                doc["manifest"]["components"][*id]["kind"] == "statistical"
                            })
                            .map(|id| (id.clone(), doc["manifest"]["components"][id].clone()))
                            .collect(),
                    );
                    let artifacts = statistics::statistical_artifacts(
                        &self.store.statistical_document(&selected)?,
                    );
                    let mut result = json!({"id":doc["id"],"revision":doc["revision"],"componentIds":ids,"computed":doc["computed"],"statisticalArtifacts":artifacts});
                    if has_live(&doc) {
                        result["transient"] = json!(true);
                    }
                    if evidence {
                        result["evidence"] = Value::Object(
                            ids.iter()
                                .map(|id| Ok((id.clone(), component_evidence(&doc, id)?)))
                                .collect::<Result<_>>()?,
                        );
                    }
                    result["computed"]["responseBytes"] = json!(serde_json::to_vec(&result)?.len());
                    Ok(result)
                } else {
                    Ok(json!({"document":doc}))
                }
            }
            "dashboard_filter_options" => {
                let doc = self
                    .store
                    .compact(&self.reading_document(board, args, pinned)?)?;
                let mut result = self.views.filter_options(
                    &doc,
                    string(args, "filterId")?,
                    args["search"].as_str().unwrap_or(""),
                    unsigned(args, "offset", 0)?,
                    unsigned(args, "limit", 100)? as usize,
                )?;
                if has_live(&doc) {
                    result["transient"] = json!(true);
                }
                Ok(result)
            }
            "dashboard_data_inspect" => {
                let doc = self.store.compact(&self.document(board, pinned)?)?;
                let refs = &doc["snapshot"]["datasetRefs"];
                let mut shared: BTreeMap<String, Vec<String>> = BTreeMap::new();
                for (key, reference) in refs.as_object().into_iter().flatten() {
                    shared
                        .entry(string(reference, "version")?.into())
                        .or_default()
                        .push(key.clone());
                }
                Ok(
                    json!({"datasets":refs,"componentData":doc["snapshot"]["componentDataRefs"],"sharedVersions":shared.values().filter(|v|v.len()>1).collect::<Vec<_>>(),"configBytes":super::serialization::python_json(&doc,false,true)?.len(),"dataFileBytes":self.store.data.path.as_ref().map(fs::metadata).transpose()?.map_or(0,|m|m.len())}),
                )
            }
            "dashboard_migrate" => {
                let migration = self
                    .store
                    .migrate(board, integer(args, "expectedRevision")?)?;
                Ok(json!({"document":self.store.get(board,false)?,"migration":migration}))
            }
            "dashboard_migration_rollback" => Ok(
                json!({"document":self.store.rollback_migration(board,integer(args,"expectedRevision")?,string(args,"backupId")?)?}),
            ),
            "dataset_attach" => {
                contract::validate_args(tool, args)?;
                let doc = self.store.get(board, false)?;
                let expected = integer(args, "expectedRevision")?;
                require(
                    doc["revision"] == expected,
                    "Reload before attaching data",
                    "REVISION_CONFLICT",
                )?;
                let started = Instant::now();
                let ds = string(args, "datasetId")?;
                let path = self.queries.sqlite_path(string(args, "connection")?)?;
                let reference = self.store.data.import_sqlite(
                    &path,
                    string(args, "table")?,
                    args.get("fields"),
                )?;
                let source = dataset_authoring::source_id("local", ds)?;
                let operations = vec![
                    json!({"op":"put_source","id":source,"value":{"kind":"file","name":format!("{}:{}",string(args,"connection")?,string(args,"table")?),"verification":"runtime-executed"}}),
                    json!({"op":"put_dataset_ref","id":ds,"meta":{"fields":reference["fields"],"sourceId":source},"ref":reference}),
                    json!({"op":"set_data_mode","value":"local"}),
                ];
                Ok(
                    json!({"document":self.store.mutate(board,expected,Some(&operations),None,false,None)?,"import":{"rowCount":reference["rowCount"],"logicalBytes":reference["bytes"],"durationMs":started.elapsed().as_secs_f64()*1000.0}}),
                )
            }
            "dataset_preview" => {
                contract::validate_args(tool, args)?;
                dataset_authoring::preview(self, args, pinned)
            }
            "component_data" => self.component_data(board, args, pinned),
            "dataset_export" => self.dataset_export(board, args, pinned),
            "dashboard_create" => {
                let mut document = args.get("document").cloned();
                if let Some(doc) = document.as_mut() {
                    require(!doc["manifest"]["components"].as_object().is_some_and(|v|v.values().any(|c|c["kind"]=="chart")),"Use kind=legacy, family=chart with a preset code or config.renderer=echarts/html","UNSUPPORTED_CHART_FAMILY")?;
                    if let Some(sources) = doc["manifest"]
                        .get_mut("sources")
                        .and_then(Value::as_object_mut)
                    {
                        for source in sources.values_mut() {
                            source["verification"] = json!("supplied");
                        }
                    }
                }
                Ok(
                    json!({"document":self.store.create(board,args["title"].as_str().unwrap_or("Dashboard"),document.as_ref())?}),
                )
            }
            "dashboard_annotations" => self.annotations(board, args),
            "dashboard_preview" => {
                assets::require_preview()?;
                Ok(
                    json!({"document":if let Some(doc)=pinned{doc.clone()}else if self.project_root.is_some(){self.store.readable(board)?}else{self.store.get(board,false)?}}),
                )
            }
            "dashboard_get" => Ok(
                json!({"document":if let Some(doc)=pinned{doc.clone()}else{self.store.get(board,args["dataMode"]!="local")?}}),
            ),
            "dashboard_validate" => {
                let doc = args
                    .get("document")
                    .cloned()
                    .map_or_else(|| self.document(board, pinned), Ok)?;
                model::validate(&doc)?;
                Ok(json!({"valid":true}))
            }
            "dashboard_patch" => {
                require(
                    args["operations"].is_array(),
                    "operations must be an array",
                    "INVALID_ARGUMENT",
                )?;
                let current = self.store.get(board, false)?;
                let operations = self.patch_operations(&current, array(args, "operations")?)?;
                if args.get("expectedAnnotations").is_some() {
                    self.project_required()?;
                    require(
                        args["expectedAnnotations"].is_array(),
                        "expectedAnnotations must be an array",
                        "INVALID_ARGUMENT",
                    )?;
                }
                let updated = self.store.mutate(
                    board,
                    integer(args, "expectedRevision")?,
                    Some(&operations),
                    None,
                    false,
                    args.get("expectedAnnotations"),
                )?;
                Ok(json!({"semanticChanges":semantic_diff(&current,&updated),"document":updated}))
            }
            "dashboard_history" => Ok(
                json!({"history":self.store.history(board,unsigned(args,"offset",0)? as usize,unsigned(args,"limit",50)? as usize)?}),
            ),
            "dashboard_restore" => Ok(
                json!({"document":self.store.mutate(board,integer(args,"expectedRevision")?,None,Some(integer(args,"revision")?),args["useCurrentData"].as_bool().unwrap_or(false),None)?}),
            ),
            "query_inspect" | "semantic_inspect" => {
                let doc = self.reading_document(board, args, pinned)?;
                let id = string(args, "componentId")?;
                let info = component_evidence(&doc, id)?;
                if tool == "query_inspect" {
                    Ok(
                        json!({"source":info["source"],"snapshotUpdatedAt":info["snapshotUpdatedAt"],"filters":info["filters"],"localVersion":info["localVersion"],"note":if info["dataset"]["mode"]=="live"{"The registered SQL runs on data reads. Interactive filters apply to its result."}else{"Interactive filters query the immutable local data version; upstream source SQL is not re-executed."}}),
                    )
                } else {
                    let c = &doc["manifest"]["components"][id];
                    Ok(
                        json!({"metrics":info["metrics"],"dataset":info["dataset"],"originalPresentation":c["config"]["presentation"],"originalExplanation":c["config"]["explanation"],"statisticalAnalysis":c["analysis"],"certified":false}),
                    )
                }
            }
            "legacy_render" => {
                let mut doc = self.document(board, pinned)?;
                let id = string(args, "componentId")?;
                let component = &doc["manifest"]["components"][id];
                require(
                    component["kind"] == "legacy",
                    "Original component not found",
                    "INVALID_DOCUMENT",
                )?;
                let live = live_ids(&doc);
                require(
                    !component["datasetId"]
                        .as_str()
                        .is_some_and(|v| live.contains(v)),
                    "实时 SQL 图表请从服务页面查看",
                    "LIVE_DATA_REQUIRES_RUNTIME",
                )?;
                if !live.is_empty() {
                    for ds in live {
                        doc["manifest"]["datasets"]
                            .as_object_mut()
                            .unwrap()
                            .remove(&ds);
                    }
                    doc = self.views.prepare_select(
                        &self.store.compact(&doc)?,
                        None,
                        None,
                        None,
                        Some(&[id.to_owned()]),
                        false,
                    )?;
                } else if doc["snapshot"]["datasetRefs"]
                    .as_object()
                    .is_some_and(|m| !m.is_empty())
                {
                    doc = self
                        .views
                        .prepare(&self.store.compact(&doc)?, None, None, None)?;
                }
                Ok(
                    json!({"html":assets::export_component(&doc,id)?,"scope":"component","componentId":id}),
                )
            }
            "dataset_import" | "query_execute" => self.import_dataset(tool, board, args),
            _ => Err(
                Error::new("UNKNOWN_TOOL", format!("Unsupported tool: {tool}")).with_status(404),
            ),
        }
    }
    fn project_required(&self) -> Result<()> {
        require(
            self.project_root.is_some(),
            "Project required",
            "PROJECT_REQUIRED",
        )
    }
    fn import_dataset(&self, tool: &str, board: &str, args: &Value) -> Result<Value> {
        contract::validate_args(tool, args)?;
        let ds = string(args, "datasetId")?;
        model::check_identifier(ds)?;
        let doc = self.store.get(board, false)?;
        let expected = integer(args, "expectedRevision")?;
        require(
            doc["revision"] == expected,
            "Reload before importing data",
            "REVISION_CONFLICT",
        )?;
        let live = tool == "query_execute" && args["mode"] == "live";
        let (rows, mut fields, source, source_id) = if tool == "dataset_import" {
            let (rows, fields) = dataset_authoring::parse_input(args)?;
            let id = dataset_authoring::source_id("import", ds)?;
            (
                rows,
                fields,
                json!({"kind":"file","name":args["name"].as_str().unwrap_or(ds),"verification":"supplied"}),
                id,
            )
        } else {
            require(
                live || args.get("fields").is_none(),
                "fields is only supported in live mode",
                "INVALID_ARGUMENT",
            )?;
            let declared = if live {
                args.get("fields")
                    .or_else(|| doc["manifest"]["datasets"][ds].get("fields"))
            } else {
                None
            };
            let output = self.queries.execute(
                string(args, "connection")?,
                string(args, "sql")?,
                args.get("parameters"),
                30.0,
                declared,
                None,
            )?;
            let id = format!("query-{}", string(&output.source["query"], "id")?);
            (output.rows, output.fields, output.source, id)
        };
        if rows.is_empty() && tool == "query_execute" {
            if let Some(previous) = doc["manifest"]["datasets"][ds]["fields"].as_object() {
                for (key, info) in fields.as_object_mut().unwrap() {
                    if let Some(old) = previous.get(key) {
                        *info = old.clone();
                    }
                }
            }
        }
        let mut operations = vec![json!({"op":"put_source","id":source_id,"value":source})];
        if live {
            let transient = LocalData::new(None)?;
            transient.import_rows(&rows, &fields)?;
            operations.push(json!({"op":"put_live_dataset","id":ds,"meta":{"fields":fields,"sourceId":source_id}}));
        } else {
            operations.push(json!({"op":"put_dataset","id":ds,"meta":{"fields":fields,"sourceId":source_id},"rows":rows}));
        }
        for (key, field) in fields.as_object().unwrap() {
            let identity = Uuid::new_v5(&Uuid::NAMESPACE_URL, format!("{ds}:{key}").as_bytes())
                .simple()
                .to_string();
            let id = format!("metric-{}", &identity[..20]);
            if field["type"] == "number" && doc["manifest"]["metrics"].get(&id).is_none() {
                operations.push(json!({"op":"put_metric","id":id,"value":{"datasetId":ds,"field":key,"aggregation":"sum","label":key,"unit":"","definition":format!("业务定义待确认：字段「{key}」的业务对象、记录粒度、纳入与排除条件尚未说明。当前配置仅对该字段求和。"),"status":"unverified"}}));
            }
        }
        let updated = self
            .store
            .mutate(board, expected, Some(&operations), None, false, None)?;
        if tool == "query_execute" {
            Ok(json!({"document":updated,"execution":source["query"]}))
        } else {
            Ok(json!({"semanticChanges":semantic_diff(&doc,&updated),"document":updated}))
        }
    }
    fn component_data(&self, board: &str, args: &Value, pinned: Option<&Value>) -> Result<Value> {
        let doc = self
            .store
            .compact(&self.reading_document(board, args, pinned)?)?;
        let key = string(args, "componentId")?;
        let component = doc["manifest"]["components"]
            .get(key)
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Component not found"))?;
        let ds = component["datasetId"]
            .as_str()
            .or(component["binding"]["datasetId"].as_str());
        let live = ds.is_some_and(|id| doc["manifest"]["datasets"][id]["mode"] == "live");
        let filters = active_filters(&doc, args, Some(key), ds)?;
        let offset = unsigned(args, "offset", 0)?;
        let limit = unsigned(args, "limit", 1000)?;
        require(
            (1..=1000).contains(&limit),
            "Invalid data range",
            "INVALID_ARGUMENT",
        )?;
        let search = args["search"].as_str().unwrap_or("");
        require(
            search.chars().count() <= 1000,
            "Table search must contain at most 1000 characters",
            "INVALID_ARGUMENT",
        )?;
        let (data, reference) = if live {
            self.live_dataset(&doc, ds.unwrap())?
        } else {
            let reference = ds
                .and_then(|id| doc["snapshot"]["datasetRefs"].get(id))
                .or_else(|| doc["snapshot"]["componentDataRefs"].get(key))
                .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Component has no row dataset"))?;
            (self.store.data.clone(), reference.clone())
        };
        let mut result = data.rows(
            &reference,
            &filters,
            None,
            array(args, "sort")?,
            offset,
            limit as usize,
            search,
        )?;
        if live {
            result["transient"] = json!(true);
        }
        Ok(result)
    }
    fn dataset_export(&self, board: &str, args: &Value, pinned: Option<&Value>) -> Result<Value> {
        let doc = self
            .store
            .compact(&self.reading_document(board, args, pinned)?)?;
        let key = args["componentId"].as_str();
        let component = key.and_then(|key| doc["manifest"]["components"].get(key));
        let ds = component
            .and_then(|c| c["datasetId"].as_str())
            .or(args["datasetId"].as_str());
        let live = ds.is_some_and(|id| doc["manifest"]["datasets"][id]["mode"] == "live");
        let filters = active_filters(&doc, args, key, ds)?;
        let mut presentation = component
            .map(|c| c["presentation"].clone())
            .filter(Value::is_object)
            .unwrap_or_else(|| json!({}));
        if let Some(config) = component.and_then(|c| c["config"].as_object()) {
            presentation.as_object_mut().unwrap().extend(config.clone());
        }
        let groups = strings(presentation.get("groupBy"))?;
        let sums = strings(presentation.get("sumFields"))?;
        let mut columns = strings(args.get("columns"))?;
        if groups.as_ref().is_some_and(|v| !v.is_empty()) && columns.is_none() {
            columns = Some(
                array(&presentation, "columns")?
                    .iter()
                    .map(|c| string(c, "key").map(String::from))
                    .collect::<Result<_>>()?,
            );
        }
        let (data, reference) = if live {
            self.live_dataset(&doc, ds.unwrap())?
        } else {
            let reference = ds
                .and_then(|id| doc["snapshot"]["datasetRefs"].get(id))
                .or_else(|| key.and_then(|k| doc["snapshot"]["componentDataRefs"].get(k)))
                .ok_or_else(|| {
                    Error::new(
                        "INVALID_ARGUMENT",
                        "Choose an existing dataset or table component",
                    )
                })?;
            (self.store.data.clone(), reference.clone())
        };
        let sort = array(args, "sort")?;
        let id = Uuid::new_v4().simple().to_string();
        let directory = (!live).then(|| self.store.root.join("exports").join(&id));
        let path = directory
            .as_ref()
            .map(|dir| dir.join(format!("{board}.csv")));
        let result = (|| -> Result<Value> {
            if let Some(directory) = &directory {
                exports::private_directory(directory)?;
            }
            let exported = data.export_csv(
                &reference,
                path.as_deref(),
                &filters,
                columns.as_deref(),
                sort,
                args["search"].as_str().unwrap_or(""),
                groups.as_deref(),
                sums.as_deref(),
                presentation.get("calculatedColumns"),
            )?;
            if let Some(path) = &path {
                exports::private_file(path)?;
            }
            Ok(exported)
        })();
        if result.is_err() {
            if let Some(directory) = &directory {
                let _ = fs::remove_dir_all(directory);
            }
        }
        let mut exported = result?;
        exported["filename"] = json!(format!("{board}.csv"));
        exported["format"] = json!("csv");
        exported["mimeType"] = json!("text/csv");
        if !live {
            exported["id"] = json!(id);
        }
        let mut result = json!({"export":exported});
        if live {
            result["transient"] = json!(true);
        }
        Ok(result)
    }
    fn annotations(&self, board: &str, args: &Value) -> Result<Value> {
        let targets = args.get("includeTargets").map_or(Ok(true), |v| {
            v.as_bool()
                .ok_or_else(|| Error::new("INVALID_ARGUMENT", "includeTargets must be a boolean"))
        })?;
        let state = if self.project_root.is_some() {
            self.store.annotation_state(board, targets)?
        } else {
            let doc = self.store.get(board, false)?;
            let mut state = doc["manifest"].clone();
            state["id"] = doc["id"].clone();
            state["revision"] = doc["revision"].clone();
            state
        };
        let notes = state["annotations"].as_array().cloned().unwrap_or_default();
        let mut result = json!({"dashboardId":state["id"],"title":state["title"],"revision":state["revision"],"annotations":notes,"count":notes.len(),"independentSave":self.project_root.is_some()});
        if !targets {
            return Ok(result);
        }
        let mut resolutions = Map::new();
        for note in notes {
            let component = note["componentId"].as_str();
            let scope = note["anchor"]["scope"]
                .as_str()
                .unwrap_or(if component.is_some() {
                    "component"
                } else {
                    "page"
                });
            let mut target = json!({"scope":scope});
            if let Some(id) = component {
                target["sourcePath"] = json!(format!("manifest.components.{id}"));
                if let Some(components) = state["components"].as_object() {
                    let c = components.get(id);
                    target["componentExists"] = json!(c.is_some());
                    if let Some(c) = c {
                        target["title"] = json!(c["title"].as_str().unwrap_or(""));
                        target["kind"] = c["kind"].clone();
                    }
                }
            } else {
                target["sourcePath"] = json!(if matches!(
                    state["viewMode"].as_str(),
                    Some("report" | "filtered-report")
                ) {
                    "manifest.report.markdown"
                } else {
                    "manifest"
                });
            }
            resolutions.insert(string(&note, "id")?.into(), target);
        }
        result["targets"] = resolutions.into();
        result["targetsResolved"] = json!(state["components"].is_object());
        Ok(result)
    }
}

pub fn component_evidence(doc: &Value, id: &str) -> Result<Value> {
    let manifest = &doc["manifest"];
    let snapshot = &doc["snapshot"];
    let component = manifest["components"]
        .get(id)
        .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Component not found"))?;
    let ds = component["datasetId"].as_str().unwrap_or("");
    let dataset = manifest["datasets"]
        .get(ds)
        .cloned()
        .unwrap_or_else(|| json!({}));
    let source = dataset["sourceId"]
        .as_str()
        .or(component["sourceId"].as_str())
        .unwrap_or("");
    let metrics: Map<String, Value> = array(component, "measures")?
        .iter()
        .filter_map(Value::as_str)
        .map(|id| (id.into(), manifest["metrics"][id].clone()))
        .collect();
    Ok(
        json!({"metrics":metrics,"source":manifest["sources"][source],"dataset":dataset,"snapshotUpdatedAt":snapshot["updatedAt"],"localVersion":snapshot["datasetRefs"].get(ds).or_else(||snapshot["componentDataRefs"].get(id)),"filters":array(manifest,"filters")?.iter().filter(|f|f["componentIds"].as_array().is_some_and(|v|v.iter().any(|v|v==id))).collect::<Vec<_>>(),"certified":false}),
    )
}
fn active_filters(
    doc: &Value,
    args: &Value,
    key: Option<&str>,
    dataset: Option<&str>,
) -> Result<Vec<Value>> {
    let filters = args.get("filters").unwrap_or(&doc["manifest"]["filters"]);
    let checked = model::apply_operations(doc, &[json!({"op":"set_filters","value":filters})])?;
    Ok(array(&checked["manifest"], "filters")?
        .iter()
        .filter(|f| {
            f["values"].as_array().is_some_and(|v| !v.is_empty())
                && f["componentIds"].as_array().is_some_and(|ids| {
                    ids.iter().filter_map(Value::as_str).any(|id| {
                        if let Some(key) = key {
                            id == key
                        } else {
                            doc["manifest"]["components"][id]["datasetId"].as_str() == dataset
                        }
                    })
                })
        })
        .cloned()
        .collect())
}
pub use super::store::semantic_diff;

fn compact_records(result: &mut Value) {
    let computed = if result.get("computed").is_some() {
        result.get_mut("computed")
    } else {
        result
            .get_mut("document")
            .and_then(|doc| doc.get_mut("computed"))
    };
    let Some(components) = computed
        .and_then(|value| value.get_mut("components"))
        .and_then(Value::as_object_mut)
    else {
        return;
    };
    for component in components.values_mut() {
        let Some(data) = component.get_mut("data") else {
            continue;
        };
        let Some(records) = data.get("records").and_then(Value::as_array) else {
            continue;
        };
        if records.len() < 20 {
            continue;
        }
        let Some(first) = records[0]["values"].as_object() else {
            continue;
        };
        let keys = first.keys().cloned().collect::<Vec<_>>();
        if !records.iter().all(|row| {
            row.as_object().is_some_and(|r| {
                r.len() == 3
                    && r.contains_key("category")
                    && r.contains_key("series")
                    && r.contains_key("values")
            }) && row["values"]
                .as_object()
                .is_some_and(|v| v.keys().eq(keys.iter()))
        }) {
            continue;
        }
        let rows: Vec<Vec<Value>> = records
            .iter()
            .map(|row| {
                let mut cells = vec![row["category"].clone(), row["series"].clone()];
                cells.extend(keys.iter().map(|key| row["values"][key].clone()));
                cells
            })
            .collect();
        data["packedRecords"] = json!({"keys":keys,"rows":rows});
        data.as_object_mut().unwrap().remove("records");
    }
}
