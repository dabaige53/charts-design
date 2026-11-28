//! MCP adapters share the service and project resolver with the HTTP application.
use super::{
    assets, contract, discovery,
    error::{require, Error, Result},
    service::Service,
    view::LocalView,
};
use rmcp::{model::*, service::RequestContext, ErrorData, RoleServer, ServerHandler, ServiceExt};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    path::PathBuf,
    sync::{Arc, Mutex, OnceLock},
    time::{Duration, Instant},
};

#[derive(Clone)]
pub struct Lifetime {
    state: Arc<Mutex<(Instant, usize)>>,
    timeout: Option<Duration>,
}
pub struct Activity(Lifetime);
impl Drop for Activity {
    fn drop(&mut self) {
        if let Ok(mut state) = self.0.state.lock() {
            state.0 = Instant::now();
            state.1 = state.1.saturating_sub(1);
        }
    }
}
impl Lifetime {
    pub fn new(seconds: f64) -> Result<Self> {
        require(
            seconds.is_finite() && seconds >= 0.0,
            "idle timeout must be non-negative",
            "INVALID_ARGUMENT",
        )?;
        Ok(Self {
            state: Arc::new(Mutex::new((Instant::now(), 0))),
            timeout: if seconds > 0.0 {
                Some(Duration::from_secs_f64(seconds))
            } else {
                None
            },
        })
    }
    pub fn activity(&self) -> Activity {
        if let Ok(mut state) = self.state.lock() {
            state.0 = Instant::now();
            state.1 += 1;
        }
        Activity(self.clone())
    }
    pub fn expired(&self) -> bool {
        self.timeout.is_some_and(|timeout| {
            self.state
                .lock()
                .is_ok_and(|state| state.1 == 0 && state.0.elapsed() >= timeout)
        })
    }
    pub fn seconds(&self) -> Option<f64> {
        self.timeout.map(|value| value.as_secs_f64())
    }
}

pub trait Gateway: Send + Sync {
    fn resolve(&self, args: Value) -> Result<(Arc<Service>, Value)>;
    fn remote(&self) -> bool {
        false
    }
    fn definitions(&self) -> Vec<Value> {
        contract::tool_definitions(self.remote(), true)
    }
    fn handle(
        &self,
        _name: &str,
        _request: &Value,
        _service: &Arc<Service>,
    ) -> Result<Option<Value>> {
        Ok(None)
    }
    fn decorate(
        &self,
        _name: &str,
        _request: &Value,
        mut result: Value,
        service: &Arc<Service>,
    ) -> Result<Value> {
        result["projectRoot"] = json!(service.project_root);
        Ok(result)
    }
}

pub struct LocalProjects {
    default: Arc<Service>,
    services: Mutex<BTreeMap<PathBuf, Arc<Service>>>,
    previews: Mutex<BTreeMap<PathBuf, super::server::LocalPreview>>,
    lifetime: Lifetime,
}
impl LocalProjects {
    pub fn new(default: Service, lifetime: Lifetime) -> Self {
        let default = Arc::new(default);
        let mut services = BTreeMap::new();
        if let Some(path) = &default.project_root {
            services.insert(path.clone(), default.clone());
        }
        Self {
            default,
            services: Mutex::new(services),
            previews: Mutex::new(BTreeMap::new()),
            lifetime,
        }
    }
}
impl Gateway for LocalProjects {
    fn resolve(&self, mut args: Value) -> Result<(Arc<Service>, Value)> {
        let selected = args
            .as_object_mut()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Arguments must be an object"))?
            .remove("projectRoot");
        let Some(selected) = selected else {
            return Ok((self.default.clone(), args));
        };
        let path = selected.as_str().filter(|s| !s.is_empty()).ok_or_else(|| {
            Error::new(
                "INVALID_PROJECT",
                "projectRoot must be an absolute project directory",
            )
        })?;
        let path = if let Some(rest) = path.strip_prefix("~/") {
            std::env::var_os("HOME")
                .map(PathBuf::from)
                .ok_or_else(|| Error::new("INVALID_PROJECT", "Home directory is unavailable"))?
                .join(rest)
        } else {
            PathBuf::from(path)
        };
        require(
            path.is_absolute(),
            "projectRoot must be an absolute project directory",
            "INVALID_PROJECT",
        )?;
        let path = super::server::absolute_path(&path)?;
        require(
            !path.exists() || path.is_dir(),
            "projectRoot must be a directory",
            "INVALID_PROJECT",
        )?;
        let mut services = self
            .services
            .lock()
            .map_err(|_| Error::new("INTERNAL_ERROR", "Project resolver unavailable"))?;
        let service = if let Some(service) = services.get(&path) {
            service.clone()
        } else {
            let key = hex::encode(Sha256::digest(path.to_string_lossy().as_bytes()));
            let mut service = Service::new(
                &self
                    .default
                    .store
                    .runtime_root
                    .join("projects")
                    .join(&key[..24]),
                None,
                Some(&path),
            )?;
            service.queries = self.default.queries.clone();
            service.views =
                LocalView::new(service.store.data.clone(), Some(service.queries.clone()));
            let service = Arc::new(service);
            services.insert(path, service.clone());
            service
        };
        Ok((service, args))
    }
    fn decorate(
        &self,
        name: &str,
        _request: &Value,
        mut result: Value,
        service: &Arc<Service>,
    ) -> Result<Value> {
        result["projectRoot"] = json!(service.project_root);
        if name == "dashboard_preview" && result["document"].is_object() {
            let board = result["document"]["id"]
                .as_str()
                .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Missing dashboard ID"))?
                .to_owned();
            let mut previews = self
                .previews
                .lock()
                .map_err(|_| Error::new("INTERNAL_ERROR", "Preview lock unavailable"))?;
            let key = service.store.root.clone();
            if !previews.contains_key(&key) {
                previews.insert(
                    key.clone(),
                    super::server::start_local(service.clone(), 0, self.lifetime.clone())?,
                );
            }
            let links = previews[&key].browser_links(&board)?;
            result["browserLinks"] = links.clone();
            result["document"]["browserLinks"] = links;
        }
        Ok(result)
    }
}

#[derive(Clone)]
pub struct Mcp {
    gateway: Arc<dyn Gateway>,
    lifetime: Lifetime,
    tools: Arc<Vec<Tool>>,
    validators: Arc<Vec<ValidatorCell>>,
}
type ValidatorCell = OnceLock<std::result::Result<jsonschema::Validator, String>>;
impl Mcp {
    pub fn new(gateway: Arc<dyn Gateway>, lifetime: Lifetime) -> Result<Self> {
        let tools = gateway
            .definitions()
            .into_iter()
            .map(serde_json::from_value)
            .collect::<std::result::Result<Vec<Tool>, _>>()?;
        let validators = Arc::new((0..tools.len()).map(|_| OnceLock::new()).collect());
        Ok(Self {
            gateway,
            lifetime,
            tools: Arc::new(tools),
            validators,
        })
    }
    fn public(&self) -> Vec<Tool> {
        self.tools
            .iter()
            .filter(|t| contract::author_tool(t.name.as_ref()))
            .cloned()
            .collect()
    }
    fn call(&self, name: &str, args: Value) -> Result<Value> {
        let index = self
            .tools
            .iter()
            .position(|tool| tool.name.as_ref() == name)
            .ok_or_else(|| {
                Error::new("UNKNOWN_TOOL", format!("Unsupported tool: {name}")).with_status(404)
            })?;
        let validator = self.validators[index]
            .get_or_init(|| {
                let schema = Value::Object((*self.tools[index].input_schema).clone());
                jsonschema::validator_for(&schema).map_err(|error| error.to_string())
            })
            .as_ref()
            .map_err(|_| Error::new("INVALID_CONTRACT", "Invalid tool schema"))?;
        if let Err(e) = validator.validate(&args) {
            return Err(Error::new("INVALID_ARGUMENT", e.to_string()));
        }
        let (service, mut request) = self.gateway.resolve(args)?;
        let response = if contract::DOCUMENT_WRITES.contains(&name) {
            request
                .as_object_mut()
                .unwrap()
                .remove("responseMode")
                .unwrap_or(json!("summary"))
        } else {
            json!("full")
        };
        require(
            response == "summary" || response == "full",
            "responseMode must be summary or full",
            "INVALID_ARGUMENT",
        )?;
        require(
            name != "dashboard_create" || service.project_root.is_some(),
            "Pass projectRoot for a new dashboard",
            "PROJECT_REQUIRED",
        )?;
        if contract::tool_schema(name).is_some_and(|s| s["properties"].get("dataMode").is_some()) {
            request
                .as_object_mut()
                .unwrap()
                .entry("dataMode")
                .or_insert(json!("local"));
        }
        let result = self
            .gateway
            .handle(name, &request, &service)?
            .map_or_else(|| service.call(name, &request), Ok)?;
        let mut result = self.gateway.decorate(name, &request, result, &service)?;
        if response == "summary" {
            result = contract::write_receipt(name, &request, &result)?;
        }
        if ![
            "runtime_result_chunk",
            "runtime_diagnostics",
            "runtime_report_error",
            "runtime_keepalive",
        ]
        .contains(&name)
        {
            let failed = result["ok"] == false;
            result = service.transport.encode(&result, name)?.0;
            if result["transport"]["requestId"].is_string() {
                // Transport envelopes must not turn a failed tool into an
                // apparent success. The stored complete result is unchanged.
                if failed {
                    result["ok"] = json!(false);
                }
                result =
                    self.gateway
                        .decorate("runtime_result_chunk", &request, result, &service)?;
                let mut uri = format!(
                    "charts://result/{}",
                    result["transport"]["requestId"].as_str().unwrap()
                );
                if let Some(project) = result["projectRoot"].as_str() {
                    uri.push('?');
                    uri.push_str(
                        &url::form_urlencoded::Serializer::new(String::new())
                            .append_pair("projectRoot", project)
                            .finish(),
                    );
                }
                result["transport"]["resourceUri"] = json!(uri);
            }
        }
        Ok(result)
    }
    fn resource(&self, uri: &str) -> Result<Value> {
        if uri.starts_with("charts://result/") {
            let parts = url::Url::parse(uri)
                .map_err(|_| Error::new("INVALID_RESOURCE", "Invalid result resource"))?;
            let id = parts.path().strip_prefix('/').unwrap_or_default();
            require(
                id.len() == 32
                    && id
                        .bytes()
                        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
                "Invalid result ID",
                "INVALID_RESOURCE",
            )?;
            let query: Vec<_> = parts.query_pairs().collect();
            require(
                query.is_empty()
                    || (query.len() == 1 && query[0].0 == "projectRoot" && !query[0].1.is_empty()),
                "Invalid result project",
                "INVALID_RESOURCE",
            )?;
            require(
                parts.fragment().is_none(),
                "Invalid result fragment",
                "INVALID_RESOURCE",
            )?;
            let request = if query.is_empty() {
                json!({})
            } else {
                json!({"projectRoot":query[0].1})
            };
            let (service, _) = self.gateway.resolve(request)?;
            return Ok(
                json!({"uri":uri,"mimeType":"application/json","text":service.transport.result_text(id)?}),
            );
        }
        if uri.starts_with("ui://charts-design/") {
            require(
                uri == assets::ui_resource_uri(),
                "请重新调用 dashboard_preview 打开当前组件构建。",
                "UI_BUILD_EXPIRED",
            )?;
            return Ok(
                json!({"uri":uri,"mimeType":"text/html;profile=mcp-app","text":assets::render_html("mcp",None,None,None)?,"_meta":{"ui":{"prefersBorder":true,"permissions":{"clipboardWrite":{}},"csp":{"connectDomains":[],"resourceDomains":[]}}}}),
            );
        }
        let value = match uri {
            "charts://catalog" => discovery::catalog(),
            "charts://contract" => {
                let mut contract = contract::discoverable_contract(self.gateway.remote());
                let definitions = self.gateway.definitions();
                contract["tools"] = Value::Object(
                    definitions
                        .iter()
                        .filter(|v| v["name"].as_str().is_some_and(contract::author_tool))
                        .map(|v| {
                            let mut v = v.clone();
                            let name = v
                                .as_object_mut()
                                .unwrap()
                                .remove("name")
                                .unwrap()
                                .as_str()
                                .unwrap()
                                .to_owned();
                            (name, v)
                        })
                        .collect(),
                );
                contract["clientTools"] = Value::Object(
                    definitions
                        .iter()
                        .filter(|v| !v["name"].as_str().is_some_and(contract::author_tool))
                        .map(|v| {
                            (
                                v["name"].as_str().unwrap().to_owned(),
                                v["inputSchema"].clone(),
                            )
                        })
                        .collect(),
                );
                contract
            }
            "charts://declarations" => discovery::full_declarations(),
            "charts://layouts" => discovery::layouts(),
            "charts://examples" => discovery::examples(None)?,
            uri if uri.starts_with("charts://examples/") => {
                discovery::examples(uri.strip_prefix("charts://examples/"))?
            }
            _ => return Err(Error::new("NOT_FOUND", "Unknown resource").with_status(404)),
        };
        Ok(json!({"uri":uri,"mimeType":"application/json","text":serde_json::to_string(&value)?}))
    }
}
fn protocol_error(error: Error) -> ErrorData {
    let mut data = json!({"code":error.code});
    if let Some(id) = error.request_id {
        data["requestId"] = json!(id);
    }
    ErrorData::invalid_params(error.message, Some(data))
}
fn tool_result(result: Value) -> std::result::Result<CallToolResult, ErrorData> {
    let text = serde_json::to_string(&result)
        .map_err(|error| ErrorData::internal_error(error.to_string(), None))?;
    serde_json::from_value(json!({"isError":result["ok"]==false,"content":[{"type":"text","text":text}],"structuredContent":result}))
        .map_err(|error| ErrorData::internal_error(error.to_string(), None))
}
impl ServerHandler for Mcp {
    fn get_info(&self) -> ServerConfig {
        ServerConfig::new(ServerCapabilities::builder().enable_tools().enable_resources().build()).with_server_info(Implementation::new("charts-design",env!("CARGO_PKG_VERSION"))).with_instructions("Use charts://contract for schemas and charts://examples for complete native authoring calls. Pass projectRoot on every project request.")
    }
    fn get_tool(&self, name: &str) -> Option<Tool> {
        self.tools
            .iter()
            .find(|tool| tool.name.as_ref() == name)
            .cloned()
    }
    async fn list_tools(
        &self,
        _request: Option<PaginatedRequestParams>,
        _context: RequestContext<RoleServer>,
    ) -> std::result::Result<ListToolsResult, ErrorData> {
        let _activity = self.lifetime.activity();
        serde_json::from_value(json!({"tools":self.public()}))
            .map_err(|e| ErrorData::internal_error(e.to_string(), None))
    }
    async fn call_tool(
        &self,
        request: CallToolRequestParams,
        _context: RequestContext<RoleServer>,
    ) -> std::result::Result<CallToolResponse, ErrorData> {
        let _activity = self.lifetime.activity();
        let me = self.clone();
        let result = tokio::task::spawn_blocking(move || {
            me.call(
                request.name.as_ref(),
                Value::Object(request.arguments.unwrap_or_default()),
            )
        })
        .await;
        let result = match result {
            Ok(Ok(v)) => v,
            Ok(Err(e)) => e.json(),
            Err(_) => Error::new("INTERNAL_ERROR", "Tool execution failed").json(),
        };
        Ok(tool_result(result)?.into())
    }
    async fn list_resources(
        &self,
        _request: Option<PaginatedRequestParams>,
        _context: RequestContext<RoleServer>,
    ) -> std::result::Result<ListResourcesResult, ErrorData> {
        let _activity = self.lifetime.activity();
        let mut resources = Vec::new();
        for (key, name) in [
            ("catalog", "Chart catalog"),
            ("contract", "Runtime tools and typed operations"),
            ("declarations", "Chart declaration requirements"),
            ("layouts", "Dashboard layout templates"),
            ("examples", "Dashboard and report reference cases"),
            ("examples/executive-dashboard", "Dashboard generation case"),
            ("examples/operations-scorecard", "Scorecard dashboard case"),
            ("examples/academic-report", "Academic report master"),
            ("examples/filtered-report", "Synthetic filtered report"),
        ] {
            resources.push(
                json!({"uri":format!("charts://{key}"),"name":name,"mimeType":"application/json"}),
            );
        }
        if assets::ui_build_id() != "unavailable" {
            resources.push(json!({"uri":assets::ui_resource_uri(),"name":"Charts Design React UI","mimeType":"text/html;profile=mcp-app"}));
        }
        serde_json::from_value(json!({"resources":resources}))
            .map_err(|e| ErrorData::internal_error(e.to_string(), None))
    }
    async fn read_resource(
        &self,
        request: ReadResourceRequestParams,
        _context: RequestContext<RoleServer>,
    ) -> std::result::Result<ReadResourceResponse, ErrorData> {
        let _activity = self.lifetime.activity();
        let me = self.clone();
        let value = tokio::task::spawn_blocking(move || me.resource(request.uri.as_ref()))
            .await
            .map_err(|_| ErrorData::internal_error("Resource read failed", None))?
            .map_err(protocol_error)?;
        let result: ReadResourceResult = serde_json::from_value(json!({"contents":[value]}))
            .map_err(|e| ErrorData::internal_error(e.to_string(), None))?;
        Ok(result.into())
    }
}
pub fn run(service: Service, idle: f64) -> Result<()> {
    let lifetime = Lifetime::new(idle)?;
    let gateway = Arc::new(LocalProjects::new(service, lifetime.clone()));
    let server = Mcp::new(gateway, lifetime.clone())?;
    let runtime = tokio::runtime::Runtime::new()?;
    let result = runtime.block_on(async move {
        let service = server
            .serve(rmcp::transport::stdio())
            .await
            .map_err(|e| Error::new("MCP_START_FAILED", e.to_string()))?;
        let cancel = service.cancellation_token();
        let watcher = tokio::spawn(async move {
            loop {
                tokio::time::sleep(Duration::from_millis(250)).await;
                if lifetime.expired() {
                    eprintln!("MCP closed after idle timeout");
                    cancel.cancel();
                    break;
                }
            }
        });
        let outcome = service
            .waiting()
            .await
            .map_err(|e| Error::new("MCP_FAILED", e.to_string()));
        watcher.abort();
        outcome.map(|_| ())
    });
    runtime.shutdown_timeout(Duration::from_millis(100));
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    struct FailedGateway {
        service: Arc<Service>,
        failure: Value,
    }
    impl Gateway for FailedGateway {
        fn resolve(&self, args: Value) -> Result<(Arc<Service>, Value)> {
            Ok((self.service.clone(), args))
        }
        fn handle(
            &self,
            _name: &str,
            _request: &Value,
            _service: &Arc<Service>,
        ) -> Result<Option<Value>> {
            Ok(Some(self.failure.clone()))
        }
    }

    // @wu-test type=integration | scope=MCP chunked failures | protects=large rejected writes retain isError and complete recoverable failure details
    #[test]
    fn chunked_failure_keeps_tool_error_and_complete_resource() {
        let directory = tempfile::tempdir().unwrap();
        let service = Arc::new(Service::new(directory.path(), None, None).unwrap());
        let failure = json!({
            "ok":false,
            "error":{"code":"DOCTOR_FAILED","message":"Draft checks failed"},
            "doctor":{"checks":[{"id":"chart","detail":"Validation evidence. ".repeat(5000)}]}
        });
        assert!(
            serde_json::to_vec(&failure).unwrap().len() > super::super::transport::INLINE_LIMIT
        );
        let gateway = Arc::new(FailedGateway {
            service,
            failure: failure.clone(),
        });
        let mcp = Mcp::new(gateway, Lifetime::new(0.0).unwrap()).unwrap();
        let result = tool_result(
            mcp.call(
                "dashboard_submit",
                json!({"dashboardId":"main","expectedRevision":1}),
            )
            .unwrap(),
        )
        .unwrap();
        assert_eq!(result.is_error, Some(true));
        let manifest = result.structured_content.unwrap();
        assert_eq!(manifest["ok"], false);
        assert_eq!(manifest["transport"]["encoding"], "base64-json-v1");
        let resource = mcp
            .resource(manifest["transport"]["resourceUri"].as_str().unwrap())
            .unwrap();
        let restored: Value = serde_json::from_str(resource["text"].as_str().unwrap()).unwrap();
        assert_eq!(restored["ok"], false);
        assert_eq!(restored["error"], failure["error"]);
        assert_eq!(restored["doctor"], failure["doctor"]);
    }
}
