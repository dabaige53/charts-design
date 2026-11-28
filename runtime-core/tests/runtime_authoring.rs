use charts_design_core::runtime::{
    contract, dataset_authoring, discovery, model, service::Service, transport::Transport,
};
use serde_json::{json, Value};
use tempfile::TempDir;

fn service(temp: &TempDir) -> Service {
    Service::new(
        &temp.path().join("runtime"),
        None,
        Some(&temp.path().join("project")),
    )
    .unwrap()
}

// @wu-test type=boundary | scope=CSV initialization | protects=missing values, identifiers and invalid structure are silently reinterpreted
#[test]
fn csv_initialization_preserves_types_and_rejects_lossy_input() {
    let (rows, fields) = dataset_authoring::parse_input(
        &json!({"csvText":"\u{feff}region,amount,postcode\r\nEast,12,00123\r\nSouth,,00234\r\n"}),
    )
    .unwrap();
    assert_eq!(
        rows,
        vec![
            json!({"region":"East","amount":12,"postcode":"00123"}),
            json!({"region":"South","amount":null,"postcode":"00234"})
        ]
    );
    assert_eq!(fields["postcode"]["type"], "string");
    assert_eq!(fields["amount"]["type"], "number");
    for invalid in [
        "amount,amount\n1,2\n",
        "region,amount\nEast\n",
        "region,amount\nEast,1,extra\n",
        "region,amount\n\"East,1\n",
        "region, \nEast,1\n",
    ] {
        assert_eq!(
            dataset_authoring::parse_input(&json!({"csvText":invalid}))
                .unwrap_err()
                .code,
            "INVALID_ARGUMENT",
            "{invalid}"
        );
    }
    let fields =
        json!({"id":{"type":"string"},"amount":{"type":"number"},"active":{"type":"boolean"}});
    let (rows, _) = dataset_authoring::parse_input(
        &json!({"csvText":"id,amount,active\n001,1.5e2,TRUE\n002,,0\n", "fields":fields}),
    )
    .unwrap();
    assert_eq!(
        rows,
        vec![
            json!({"id":"001","amount":150.0,"active":true}),
            json!({"id":"002","amount":null,"active":false})
        ]
    );
    assert!(dataset_authoring::parse_input(
        &json!({"rows":[{"amount":"12"}],"fields":{"amount":{"type":"number"}}})
    )
    .is_err());
    assert!(dataset_authoring::parse_input(&json!({"rows":[]})).is_err());
    assert!(
        dataset_authoring::parse_input(&json!({"rows":[],"fields":fields}))
            .unwrap()
            .0
            .is_empty()
    );
}

// @wu-test type=integration | scope=data to chart authoring | protects=agents must reconstruct metric IDs or create components before inspecting data
#[test]
fn data_receipt_continues_to_preview_and_saved_computed_view() {
    let temp = TempDir::new().unwrap();
    let service = service(&temp);
    service
        .call(
            "dashboard_create",
            &json!({"dashboardId":"fresh","title":"Revenue"}),
        )
        .unwrap();
    let request = json!({"dashboardId":"fresh","datasetId":"sales","expectedRevision":1,"csvText":"region,amount\nEast,10\nWest,20\n"});
    let imported = service.call("dataset_import", &request).unwrap();
    let receipt = contract::write_receipt("dataset_import", &request, &imported).unwrap();
    assert!(receipt.get("document").is_none());
    assert_eq!(receipt["revision"], 2);
    assert_eq!(receipt["dataset"]["rowCount"], 2);
    let preview_call = &receipt["nextCalls"][0];
    assert_eq!(preview_call["tool"], "dataset_preview");
    let preview = service
        .call("dataset_preview", &preview_call["arguments"])
        .unwrap();
    assert_eq!(preview["totalRows"], 2);
    assert_eq!(preview["scope"], "unfiltered-dataset");
    assert_eq!(preview["filtersApplied"], false);
    assert_eq!(preview["rows"][1]["amount"], 20);
    assert_eq!(
        service.store.get("fresh", false).unwrap()["manifest"]["components"],
        json!({})
    );
    let metrics = receipt["dataset"]["metrics"].as_object().unwrap();
    let metric = metrics
        .iter()
        .find(|(_, value)| value["field"] == "amount")
        .unwrap();
    assert_eq!(metric.1["status"], "unverified");
    let submitted = service.call("dashboard_submit", &json!({"dashboardId":"fresh","expectedRevision":2,"operations":[{"op":"put_component","id":"total","value":{"kind":"kpi","title":"Revenue","datasetId":"sales","measures":[metric.0]}}]})).unwrap();
    assert_eq!(submitted["ok"], true);
    assert_eq!(submitted["doctor"]["passed"], true);
    let view = service.call("dashboard_view", &json!({"dashboardId":"fresh","expectedRevision":submitted["revision"],"componentIds":["total"],"responseMode":"patch","includeEvidence":true})).unwrap();
    assert_eq!(view["computed"]["components"]["total"]["value"], "30");
    assert_eq!(
        view["evidence"]["total"]["metrics"][metric.0]["field"],
        "amount"
    );
    let raw = service.call("component_data", &json!({"dashboardId":"fresh","componentId":"total","expectedRevision":submitted["revision"]})).unwrap();
    assert_eq!(
        raw["rows"]
            .as_array()
            .unwrap()
            .iter()
            .map(|row| row["amount"].as_f64().unwrap())
            .sum::<f64>(),
        30.0
    );
    assert!(service
        .call(
            "dataset_preview",
            &json!({"dashboardId":"fresh","datasetId":"sales","expectedRevision":999})
        )
        .is_err());
}

// @wu-test type=integration | scope=SQLite 明细 CSV 导出 | protects=筛选结果导出错误、文件权限过宽或失败后留下半成品
#[test]
fn csv_export_is_private_and_failed_exports_leave_no_file() {
    use base64::{engine::general_purpose::STANDARD, Engine};
    let temp = TempDir::new().unwrap();
    let service = service(&temp);
    let saved = service
        .call("dashboard_submit", &json!({
            "dashboardId":"sales", "createTitle":"Sales", "operations":[
                {"op":"put_source","id":"fixture","value":{"kind":"fixture","name":"Sales"}},
                {"op":"put_dataset","id":"sales","meta":{"sourceId":"fixture","fields":{
                    "region":{"type":"string"},"amount":{"type":"number"}
                }},"rows":[{"region":"East","amount":10},{"region":"West","amount":20},{"region":"East","amount":30}]},
                {"op":"put_component","id":"detail","value":{"kind":"table","title":"Sales","datasetId":"sales"}},
                {"op":"set_filters","value":[{"id":"region","field":"region","op":"in","values":["East"],"componentIds":["detail"]}]}
            ]
        }))
        .unwrap();
    assert_eq!(saved["ok"], true);
    let args = json!({"dashboardId":"sales","componentId":"detail","expectedRevision":saved["revision"],
        "sort":[{"field":"amount","direction":"desc"}],"columns":["region","amount"]});
    let result = service.call("dataset_export", &args).unwrap();
    let export = &result["export"];
    assert_eq!(export["rowCount"], 2);
    let path = std::path::Path::new(export["path"].as_str().unwrap());
    assert_eq!(
        std::fs::read(path).unwrap(),
        "\u{feff}region,amount\r\nEast,30\r\nEast,10\r\n".as_bytes()
    );
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            std::fs::metadata(path).unwrap().permissions().mode() & 0o777,
            0o600
        );
        assert_eq!(
            std::fs::metadata(path.parent().unwrap())
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o700
        );
    }
    let mut offset = 0;
    let mut reconstructed = Vec::new();
    loop {
        let chunk = service
            .call(
                "dashboard_export_read",
                &json!({"dashboardId":"sales",
            "exportId":export["id"],"format":"csv","offset":offset,"limit":9}),
            )
            .unwrap();
        reconstructed.extend(STANDARD.decode(chunk["content"].as_str().unwrap()).unwrap());
        if chunk["hasMore"] == false {
            break;
        }
        offset = chunk["nextOffset"].as_u64().unwrap();
    }
    assert_eq!(reconstructed, std::fs::read(path).unwrap());

    let mut invalid = args;
    invalid["columns"] = json!(["does-not-exist"]);
    assert!(service.call("dataset_export", &invalid).is_err());
    let exports = std::fs::read_dir(path.parent().unwrap().parent().unwrap()).unwrap();
    assert_eq!(exports.count(), 1);
}

// @wu-test type=integration | scope=initial submission | protects=failed initialization leaves an empty dashboard that blocks a corrected request
#[test]
fn invalid_initial_submission_is_correctable_without_cleanup() {
    let temp = TempDir::new().unwrap();
    let service = service(&temp);
    let bad = json!({"dashboardId":"new-board","createTitle":"Revenue","operations":[{"op":"put_component","id":"missing-source","value":{"kind":"kpi","title":"Invalid","datasetId":"absent","measures":["missing"]}}]});
    assert!(service.call("dashboard_submit", &bad).is_err());
    assert_eq!(
        service.store.get("new-board", false).unwrap_err().code,
        "NOT_FOUND"
    );
    let good = json!({"dashboardId":"new-board","createTitle":"Revenue","operations":[{"op":"set_title","value":"Ready"}]});
    let saved = service.call("dashboard_submit", &good).unwrap();
    assert_eq!(saved["ok"], true);
    assert_eq!(saved["doctor"]["passed"], true);
    assert_eq!(
        service.store.readable("new-board").unwrap()["manifest"]["title"],
        "Ready"
    );
    assert!(service.call("dashboard_submit", &good).is_err());
}

// @wu-test type=behavior | scope=declaration discovery | protects=published preset examples fail native validation or lose report source
#[test]
fn declarations_and_examples_remain_executable() {
    let definitions = contract::tool_definitions(false, false);
    assert_eq!(definitions.len(), 24);
    for name in ["dashboard_submit", "dataset_import", "dataset_preview"] {
        assert!(definitions.iter().any(|tool| tool["name"] == name));
    }
    let selected = discovery::declarations(&json!({"codes":["c01","t01","mc03"]})).unwrap();
    assert_eq!(selected["selections"].as_array().unwrap().len(), 3);
    assert!(discovery::declarations(&json!({"codes":["c01","c01"]})).is_err());
    let full = discovery::full_declarations();
    for kind in ["chartCodes", "kpiTypes"] {
        for (code, item) in full["legacy"][kind].as_object().unwrap() {
            let doc = model::new_document("declaration-example", code).unwrap();
            let operations = item["example"]["operations"].as_array().unwrap();
            model::apply_operations(&doc, operations).unwrap_or_else(|e| panic!("{code}: {e}"));
        }
    }
    for (id, _) in discovery::data()["examples"].as_object().unwrap() {
        let example = discovery::examples(Some(id)).unwrap();
        let doc = model::new_document("page-example", id).unwrap();
        let built =
            model::apply_operations(&doc, example["operations"].as_array().unwrap()).unwrap();
        if id == "academic-report" {
            assert_eq!(
                built["manifest"]["report"]["markdown"],
                include_str!("../resources/academic-report.md")
            );
        }
    }
    contract::validate_args(
        "dataset_preview",
        &json!({"dashboardId":"fresh","datasetId":"sales","limit":20}),
    )
    .unwrap();
    assert!(contract::validate_args(
        "dataset_preview",
        &json!({"dashboardId":"fresh","datasetId":"sales","limit":101})
    )
    .is_err());
}

// @wu-test type=boundary | scope=chart recommendations | protects=unknown data shape is represented as verified and non-recomputable correlation is recommended for filtering
#[test]
fn recommendations_expose_unknowns_and_real_binding_requirements() {
    let unknown = discovery::recommend(&json!({"intent":"comparison"}), None).unwrap();
    assert_eq!(unknown["inputs"]["measures"], Value::Null);
    assert!(!unknown["questions"].as_array().unwrap().is_empty());
    let relation = discovery::recommend(
        &json!({"intent":"relationship","measures":2,"requiresFilterBinding":true}),
        None,
    )
    .unwrap();
    let charts = relation["charts"].as_array().unwrap();
    assert!(charts.iter().all(|c| c["filterBinding"] == "supported"));
    assert!(!charts.iter().any(|c| c["code"] == "r03"));
    assert_eq!(
        charts.iter().find(|c| c["code"] == "r02").unwrap()["bindingMode"],
        "encoding"
    );
    let mismatch = discovery::recommend(
        &json!({"intent":"target","measures":9,"categories":4}),
        None,
    )
    .unwrap();
    assert_eq!(mismatch["status"], "needs_input");
}

// @wu-test type=behavior | scope=complete recommendation guidance | protects=an intent loses its guidance or a snapshot-only shape is offered as interactive
#[test]
fn every_recommendation_intent_preserves_requirements_and_filter_capabilities() {
    let known = &discovery::data()["declarations"]["legacy"]["chartCodes"];
    let snapshot_kpis = discovery::data()["recommend"]["snapshotKpis"]
        .as_array()
        .unwrap();
    for intent in [
        "comparison",
        "ranking",
        "trend",
        "composition",
        "distribution",
        "relationship",
        "flow",
        "change",
        "attribution",
        "target",
        "forecast",
    ] {
        let result = discovery::recommend(&json!({"intent":intent}), None).unwrap();
        assert!(!result["charts"].as_array().unwrap().is_empty(), "{intent}");
        for chart in result["charts"].as_array().unwrap() {
            assert!(known.get(chart["code"].as_str().unwrap()).is_some());
            assert!(!chart["requirements"].as_array().unwrap().is_empty());
            assert!(!chart["cautions"].as_array().unwrap().is_empty());
        }
        let interactive =
            discovery::recommend(&json!({"intent":intent,"requiresFilterBinding":true}), None)
                .unwrap();
        assert!(interactive["charts"]
            .as_array()
            .unwrap()
            .iter()
            .all(|chart| chart["filterBinding"] == "supported"));
        assert!(interactive["kpiShapes"]
            .as_array()
            .unwrap()
            .iter()
            .all(|kpi| !snapshot_kpis.contains(kpi)));
    }
    for invalid in [
        json!({}),
        json!({"intent":"pie"}),
        json!({"intent":"trend","categories":0}),
        json!({"intent":"trend","hasTime":"yes"}),
        json!({"intent":"trend","requiresFilterBinding":"yes"}),
    ] {
        assert!(discovery::recommend(&invalid, None).is_err(), "{invalid}");
    }
}

// @wu-test type=behavior | scope=chart choice and comparability | protects=crowded or incompatible charts outrank usable shapes and string periods are falsely ruled out
#[test]
fn recommendation_ranking_preserves_comparability_and_unknown_time_roles() {
    let many = discovery::recommend(
        &json!({"intent":"comparison","categories":25,"measures":1}),
        None,
    )
    .unwrap();
    assert!(["c02", "c05"].contains(&many["charts"][0]["code"].as_str().unwrap()));
    let example = discovery::examples(Some("executive-dashboard")).unwrap();
    let mut doc = model::apply_operations(
        &model::new_document("guide", "Guide").unwrap(),
        example["operations"].as_array().unwrap(),
    )
    .unwrap();
    let request = json!({"intent":"comparison","categories":4,"measures":1});
    let page = discovery::recommend(&request, Some(&doc)).unwrap();
    let blank = discovery::recommend(&request, None).unwrap();
    assert_eq!(page["charts"][0]["code"], blank["charts"][0]["code"]);
    assert_eq!(page["usedOnPage"]["c01"], 1);
    let repeated = page["charts"]
        .as_array()
        .unwrap()
        .iter()
        .find(|chart| chart["code"] == "c01")
        .unwrap();
    assert!(repeated["notes"]
        .as_array()
        .unwrap()
        .iter()
        .any(|note| note.as_str().unwrap().contains("已使用")));
    let crowded = discovery::recommend(
        &json!({"intent":"comparison","categories":30,"measures":3,"hasTime":false}),
        None,
    )
    .unwrap();
    assert_eq!(crowded["status"], "candidates");
    assert_eq!(crowded["charts"][0]["code"], "r05");
    assert!(!crowded["charts"][0]["shapeMismatches"]
        .as_array()
        .unwrap()
        .iter()
        .any(|issue| issue["kind"] == "structure"));
    let dataset = doc["manifest"]["datasets"]
        .as_object()
        .unwrap()
        .keys()
        .next()
        .unwrap()
        .clone();
    for field in doc["manifest"]["datasets"][&dataset]["fields"]
        .as_object_mut()
        .unwrap()
        .values_mut()
    {
        if field["type"] == "date" {
            field["type"] = json!("string");
        }
    }
    let mut request =
        json!({"intent":"trend","datasetId":dataset,"requiresFilterBinding":true,"measures":1});
    let unknown = discovery::recommend(&request, Some(&doc)).unwrap();
    assert_eq!(unknown["inputs"]["hasTime"], Value::Null);
    assert!(unknown["charts"]
        .as_array()
        .unwrap()
        .iter()
        .any(|chart| chart["code"] == "t01"));
    request["hasTime"] = json!(false);
    let denied = discovery::recommend(&request, Some(&doc)).unwrap();
    assert!(!denied["charts"]
        .as_array()
        .unwrap()
        .iter()
        .any(|chart| chart["code"] == "t01"));
    assert!(denied["excluded"]
        .as_array()
        .unwrap()
        .iter()
        .any(|chart| chart["code"] == "t01"));
    request["datasetId"] = json!("missing");
    assert_eq!(
        discovery::recommend(&request, Some(&doc)).unwrap_err().code,
        "DATASET_NOT_FOUND"
    );
}

// @wu-test type=integration | scope=MCP result transport | protects=large responses are truncated or live SQL rows persist to disk
#[test]
fn chunked_results_are_complete_and_live_results_are_ephemeral() {
    let temp = TempDir::new().unwrap();
    let transport = Transport::new(temp.path()).unwrap();
    let value = json!({"requestId":"saved-response","rows":["x".repeat(90_000)]});
    let (encoded, text) = transport.encode(&value, "dashboard_get").unwrap();
    assert!(text.is_none());
    assert!(encoded["transport"]["chunks"].as_u64().unwrap() > 1);
    assert_eq!(
        serde_json::from_str::<Value>(&transport.result_text("saved-response").unwrap()).unwrap(),
        value
    );
    let mut base64 = String::new();
    for index in 0..encoded["transport"]["chunks"].as_u64().unwrap() {
        base64.push_str(
            transport
                .chunk(&json!({"requestId":"saved-response","index":index}))
                .unwrap()["data"]
                .as_str()
                .unwrap(),
        );
    }
    use base64::{engine::general_purpose::STANDARD, Engine};
    assert_eq!(
        serde_json::from_slice::<Value>(&STANDARD.decode(base64).unwrap()).unwrap(),
        value
    );
    let live = json!({"requestId":"live-response","transient":true,"rows":["y".repeat(90_000)]});
    transport.encode(&live, "dataset_preview").unwrap();
    assert!(transport.result_text("live-response").is_ok());
    drop(transport);
    let reopened = Transport::new(temp.path()).unwrap();
    assert!(reopened.result_text("saved-response").is_ok());
    assert_eq!(
        reopened.result_text("live-response").unwrap_err().code,
        "RESULT_EXPIRED"
    );
}

// @wu-test type=integration | scope=MCP 大响应过期诊断 | protects=无法用原响应编号查出过期原因或诊断暴露业务内容
#[test]
fn expired_result_is_diagnosable_by_its_response_id() {
    let temp = TempDir::new().unwrap();
    let service = service(&temp);
    let data = json!({"rows":["只用于合成测试的业务内容".repeat(5000)]});
    let (encoded, _) = service.transport.encode(&data, "dashboard_get").unwrap();
    let request_id = encoded["transport"]["requestId"].as_str().unwrap();
    let db = rusqlite::Connection::open(&service.transport.cache_path).unwrap();
    db.execute(
        "UPDATE results SET expires = 0 WHERE request_id = ?",
        [request_id],
    )
    .unwrap();

    let error = service
        .call(
            "runtime_result_chunk",
            &json!({"requestId":request_id,"index":0}),
        )
        .unwrap_err();
    assert_eq!(error.code, "RESULT_EXPIRED");
    assert_eq!(error.request_id.as_deref(), Some(request_id));

    let error = service.transport.result_text(request_id).unwrap_err();
    assert_eq!(error.code, "RESULT_EXPIRED");
    assert_eq!(error.request_id.as_deref(), Some(request_id));

    let diagnostics = service
        .call("runtime_diagnostics", &json!({"requestId":request_id}))
        .unwrap();
    for tool in ["runtime_result_chunk", "resources/read"] {
        assert!(diagnostics["events"]
            .as_array()
            .unwrap()
            .iter()
            .any(|event| event["tool"] == tool && event["code"] == "RESULT_EXPIRED"));
    }
    assert!(!diagnostics.to_string().contains("合成测试的业务内容"));
}
