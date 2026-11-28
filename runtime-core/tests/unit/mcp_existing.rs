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
    assert!(serde_json::to_vec(&failure).unwrap().len() > super::super::transport::INLINE_LIMIT);
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
