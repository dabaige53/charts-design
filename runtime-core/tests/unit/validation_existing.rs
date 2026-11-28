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
    let example =
        &super::super::discovery::data()["declarations"]["legacy"]["chartCodes"]["c01"]["example"];
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
