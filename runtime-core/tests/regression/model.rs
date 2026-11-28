use charts_design_core::runtime::{
    data::LocalData, dataset_authoring, discovery, layouts, model, service::Service, store::Store,
    validation, view::LocalView,
};
use serde_json::{json, Value};
use std::collections::HashSet;

fn base() -> Value {
    model::apply_operations(
        &model::new_document("board", "Business review").unwrap(),
        &[
            json!({"op":"put_source","id":"source","value":{"kind":"fixture","name":"Recorded observations"}}),
            json!({"op":"put_dataset","id":"data","meta":{"sourceId":"source","fields":{
                "region":{"type":"string"},"product":{"type":"string"},"month":{"type":"date"},
                "amount":{"type":"number"},"prior":{"type":"number"},"ratio":{"type":"number"},"unit":{"type":"string"}
            }},"rows":[
                {"region":"East","product":"A","month":"2026-01-01","amount":12,"prior":10,"unit":"%"},
                {"region":"East","product":"B","month":"2026-02-01","amount":18,"prior":15,"unit":"%"},
                {"region":"West","product":"A","month":"2026-01-01","amount":20,"prior":0,"unit":"%"}
            ]}),
            json!({"op":"put_metric","id":"total","value":{"datasetId":"data","field":"amount","aggregation":"sum","label":"Revenue","unit":"USD","definition":"Net revenue","status":"reviewed"}}),
            json!({"op":"put_metric","id":"baseline","value":{"datasetId":"data","field":"prior","aggregation":"sum","label":"Baseline","unit":"USD","definition":"Comparable baseline"}}),
        ],
    ).unwrap()
}

fn add(doc: &Value, id: &str, component: Value) -> Value {
    model::apply_operations(
        doc,
        &[json!({"op":"put_component","id":id,"value":component})],
    )
    .unwrap()
}

fn original(code: &str) -> Value {
    discovery::declarations(&json!({"code":code})).unwrap()["legacy"]["chartCodes"][code]["example"]
        ["operations"]
        .as_array()
        .unwrap()
        .iter()
        .find(|op| op["op"] == "put_component")
        .unwrap()["value"]["config"]
        .clone()
}

fn set(doc: &mut Value, pointer: &str, value: Value) {
    let (parent, key) = pointer.rsplit_once('/').unwrap();
    doc.pointer_mut(parent).unwrap()[key] = value;
}

fn dynamic() -> Value {
    json!({"kind":"legacy","family":"chart","title":"Sales by region and product","datasetId":"data",
        "config":{"code":"c03","data":{},"presentation":{},"encoding":{"stacked":true,"orientation":"horizontal","tooltip":["value","minimum","maximum","label"],"colors":{"A":"#123456"},"categoryOrder":["East","West"],"seriesOrder":["A","B"],"topSeries":2,"pinnedSeries":["A"],"visibleCount":2,"barWidth":16,"showLabels":true,"adjustableBarWidth":true,"seriesRanking":"category","emptyText":"No rows","otherSeriesLabel":"Others"}},
        "binding":{"datasetId":"data","categoryField":"region","seriesField":"product","measures":{"value":"total"},"attributes":{"minimum":{"field":"amount","aggregation":"min"},"maximum":{"field":"amount","aggregation":"max"},"label":{"field":"unit","aggregation":"unique"}},"orderBy":{"target":"value","direction":"desc"}}})
}

// @wu-test type=behavior | scope=responsive layout templates | protects=every component appears once, stays within each breakpoint and never overlaps after automatic layout changes
#[test]
fn layout_templates_preserve_membership_order_and_nonoverlapping_rectangles() {
    let mut doc = base();
    for (id, component) in [
        (
            "hero",
            json!({"kind":"legacy","family":"kpi","title":"Headline","layoutPriority":"primary","config":{"type":"mc06","label":"Comparison","leftVal":12,"rightVal":10}}),
        ),
        (
            "metric",
            json!({"kind":"kpi","title":"Revenue","datasetId":"data","measures":["total"]}),
        ),
        (
            "narrative",
            json!({"kind":"text","title":"Findings","text":"Explain the measured difference."}),
        ),
        (
            "chart",
            json!({"kind":"legacy","family":"chart","title":"Trend","config":original("c01")}),
        ),
        (
            "chartTwo",
            json!({"kind":"legacy","family":"chart","title":"Second chart","config":original("c02")}),
        ),
        (
            "chartThree",
            json!({"kind":"legacy","family":"chart","title":"Third chart","config":original("c01")}),
        ),
        (
            "detail",
            json!({"kind":"table","title":"Detail","datasetId":"data"}),
        ),
    ] {
        doc = add(&doc, id, component);
    }
    let ids: HashSet<_> = doc["manifest"]["components"]
        .as_object()
        .unwrap()
        .keys()
        .cloned()
        .collect();
    for template in layouts::TEMPLATES {
        let arranged = model::apply_operations(&doc, &[json!({"op":"apply_layout_template","template":template,"order":["hero","metric","narrative","chart","chartTwo","chartThree","detail"]})]).unwrap();
        for (bp, columns) in layouts::COLS {
            let cells = arranged["manifest"]["layout"][bp].as_array().unwrap();
            assert_eq!(
                cells
                    .iter()
                    .map(|c| c["id"].as_str().unwrap().to_string())
                    .collect::<HashSet<_>>(),
                ids
            );
            assert_eq!(cells.len(), ids.len());
            for (index, a) in cells.iter().enumerate() {
                let (ax, ay, aw, ah) = (
                    a["x"].as_i64().unwrap(),
                    a["y"].as_i64().unwrap(),
                    a["w"].as_i64().unwrap(),
                    a["h"].as_i64().unwrap(),
                );
                assert!(
                    ax >= 0 && ay >= 0 && aw > 0 && ah > 0 && ax + aw <= columns,
                    "{template}/{bp}: {a}"
                );
                for b in &cells[index + 1..] {
                    let (bx, by, bw, bh) = (
                        b["x"].as_i64().unwrap(),
                        b["y"].as_i64().unwrap(),
                        b["w"].as_i64().unwrap(),
                        b["h"].as_i64().unwrap(),
                    );
                    assert!(
                        ax + aw <= bx || bx + bw <= ax || ay + ah <= by || by + bh <= ay,
                        "{template}/{bp}: {a} overlaps {b}"
                    );
                }
            }
        }
        let changed = model::apply_operations(
            &arranged,
            &[json!({"op":"remove_component","id":"chartTwo"})],
        )
        .unwrap();
        assert!(changed["manifest"]["layoutTemplate"]["order"]
            .as_array()
            .unwrap()
            .iter()
            .all(|id| id != "chartTwo"));
        assert!(changed["manifest"]["layout"]["desktop"]
            .as_array()
            .unwrap()
            .iter()
            .all(|p| p["id"] != "chartTwo"));
    }
    for order in [
        json!(["hero", "hero"]),
        json!(["missing"]),
        json!([1]),
        json!({}),
    ] {
        assert!(model::apply_operations(
            &doc,
            &[json!({"op":"apply_layout_template","template":"executive","order":order})]
        )
        .is_err());
    }
    assert_eq!(
        model::apply_operations(
            &doc,
            &[json!({"op":"apply_layout_template","template":"unknown"})]
        )
        .unwrap_err()
        .code,
        "UNKNOWN_LAYOUT"
    );
    let mut explicit = model::apply_operations(
        &doc,
        &[json!({"op":"apply_layout_template","template":"executive"})],
    )
    .unwrap();
    explicit = model::apply_operations(&explicit, &[json!({"op":"set_layout","breakpoint":"desktop","value":explicit["manifest"]["layout"]["desktop"]})]).unwrap();
    assert!(explicit["manifest"].get("layoutTemplate").is_none());
}

// @wu-test type=behavior | scope=canonical report source | protects=legacy report conversion preserves prose, escapes Markdown and prevents dangling chart references
#[test]
fn report_conversion_and_component_removal_keep_markdown_authoritative() {
    let mut doc = base();
    doc = add(
        &doc,
        "intro",
        json!({"kind":"text","title":"Summary [1]","subtitle":"As *reported*","text":"Amount is [not a link](x)."}),
    );
    doc = add(
        &doc,
        "chart",
        json!({"kind":"legacy","family":"chart","title":"Sales","config":original("c01")}),
    );
    let legacy = json!({"subtitle":"Review *all* observations","blocks":[{"id":"summary","componentId":"intro"},{"id":"result","componentId":"chart"}]});
    let doc = model::apply_operations(
        &doc,
        &[
            json!({"op":"set_report","value":legacy}),
            json!({"op":"set_view_mode","value":"report"}),
        ],
    )
    .unwrap();
    let source = model::report_markdown(&doc["manifest"]).unwrap();
    assert!(source.contains("Summary \\[1\\]"));
    assert!(source.contains("Amount is \\[not a link\\]\\(x\\)\\."));
    assert_eq!(
        model::report_chart_references(&source, Some(&doc["manifest"]["components"])).unwrap(),
        vec!["chart"]
    );
    assert_eq!(
        model::apply_operations(&doc, &[json!({"op":"remove_component","id":"chart"})])
            .unwrap_err()
            .code,
        "REPORT_COMPONENT_REFERENCED"
    );
    let replaced = model::apply_operations(&doc, &[json!({"op":"set_report_markdown","value":"# Independent source\n\nMeasured conclusions."}),json!({"op":"remove_component","id":"chart"})]).unwrap();
    assert!(replaced["manifest"]["components"].get("chart").is_none());
    assert_eq!(
        model::report_markdown(&replaced["manifest"]).unwrap(),
        "# Independent source\n\nMeasured conclusions."
    );
    let automatic = model::apply_operations(&base(), &[json!({"op":"put_component","id":"intro","value":{"kind":"text","title":"Narrative","text":"Evidence"}}),json!({"op":"set_view_mode","value":"filtered-report"})]).unwrap();
    assert!(automatic["manifest"]["report"]["markdown"]
        .as_str()
        .unwrap()
        .contains("Evidence"));
    for invalid in [
        json!({"subtitle":"","blocks":[{"id":"one","componentId":"intro"},{"id":"one","componentId":"chart"}]}),
        json!({"subtitle":"","blocks":[{"id":"one","componentId":"intro"},{"id":"two","componentId":"intro"}]}),
        json!({"subtitle":false,"blocks":[]}),
        json!({"subtitle":"","blocks":[1]}),
    ] {
        assert!(model::validate_report(&invalid, Some(&doc["manifest"]["components"])).is_err());
    }
    assert!(model::report_markdown(&json!({"report":{"markdown":42}})).is_err());
}

// @wu-test type=boundary | scope=annotation geometry and target contracts | protects=invalid rectangles, ambiguous identifiers and text anchors cannot be persisted
#[test]
fn annotation_contract_rejects_outside_rectangles_and_ambiguous_targets() {
    let components = json!({"chart":{"kind":"legacy"}});
    let note = json!({"id":"note","componentId":"chart","text":"Review","createdAt":"2026-11-28","anchor":{"scope":"component","kind":"area","quote":"Revenue","rect":{"x":0.2,"y":0.2,"width":0.4,"height":0.4}}});
    model::validate_annotations(&json!([note]), Some(&components)).unwrap();
    let edits = [
        ("/id", json!("../bad")),
        ("/text", json!("  ")),
        ("/createdAt", json!("")),
        ("/anchor/scope", json!("text")),
        ("/anchor/kind", json!("unknown")),
        ("/anchor/quote", json!(0)),
        ("/anchor/rect/x", json!(-0.1)),
        ("/anchor/rect/width", json!(0.9)),
        ("/anchor/rect", json!([])),
    ];
    for (pointer, value) in edits {
        let mut invalid = note.clone();
        set(&mut invalid, pointer, value);
        assert!(
            model::validate_annotations(&json!([invalid]), Some(&components)).is_err(),
            "{pointer}"
        );
    }
    assert!(model::validate_annotations(&json!([note, note]), Some(&components)).is_err());
    let mut text = note.clone();
    text.as_object_mut().unwrap().remove("componentId");
    text["anchor"]["scope"] = json!("text");
    text["anchor"]["occurrence"] = json!(0);
    model::validate_annotations(&json!([text]), Some(&components)).unwrap();
    text["anchor"]["quote"] = json!("");
    assert!(model::validate_annotations(&json!([text]), Some(&components)).is_err());
    text["anchor"]["quote"] = json!("Revenue");
    text["anchor"]["occurrence"] = json!(10001);
    assert!(model::validate_annotations(&json!([text]), Some(&components)).is_err());
    let orphan =
        json!({"id":"orphan","componentId":"removed","text":"Historical","createdAt":"2026-11-28"});
    assert!(model::validate_annotations(&json!([orphan]), Some(&components)).is_err());
    let mut retained = orphan;
    retained["context"] = json!({"designRevision":1});
    model::validate_annotations(&json!([retained]), Some(&components)).unwrap();
}

// @wu-test type=integration | scope=dynamic bindings and compact transport | protects=aggregated series, attributes and compact record transport preserve exact field order and values
#[test]
fn dynamic_encoding_and_packed_records_preserve_category_series_and_attributes() {
    let root = tempfile::tempdir().unwrap();
    let service = Service::new(
        &root.path().join("cache"),
        None,
        Some(&root.path().join("project")),
    )
    .unwrap();
    let mut doc = base();
    doc["snapshot"]["datasets"]["data"] = json!((0..24).map(|i| json!({"region":format!("R{i:02}"),"product":"A","month":"2026-01-01","amount":i+1,"prior":i,"unit":"USD"})).collect::<Vec<_>>());
    doc = add(&doc, "chart", dynamic());
    service
        .store
        .create("board", "Encoding", Some(&doc))
        .unwrap();
    let ordinary = service
        .call(
            "dashboard_view",
            &json!({"dashboardId":"board","responseMode":"patch","componentIds":["chart"]}),
        )
        .unwrap();
    let records = ordinary["computed"]["components"]["chart"]["data"]["records"]
        .as_array()
        .unwrap();
    assert_eq!(records.len(), 24);
    assert_eq!(records[0]["category"], "R00");
    assert_eq!(records[0]["series"], "A");
    assert_eq!(records[0]["values"]["minimum"], 1);
    assert_eq!(records[23]["values"]["maximum"], 24);
    assert_eq!(records[0]["values"]["label"], "USD");
    let compact = service.call("dashboard_view", &json!({"dashboardId":"board","responseMode":"patch","componentIds":["chart"],"compactRecords":true})).unwrap();
    let packed = &compact["computed"]["components"]["chart"]["data"]["packedRecords"];
    assert!(compact["computed"]["components"]["chart"]["data"]
        .get("records")
        .is_none());
    for (row, expected) in packed["rows"].as_array().unwrap().iter().zip(records) {
        assert_eq!(row[0], expected["category"]);
        assert_eq!(row[1], expected["series"]);
        for (index, key) in packed["keys"].as_array().unwrap().iter().enumerate() {
            assert_eq!(row[index + 2], expected["values"][key.as_str().unwrap()]);
        }
    }
    assert_eq!(packed["rows"].as_array().unwrap().len(), records.len());
}

// @wu-test type=boundary | scope=dynamic encoding validation | protects=unknown fields, nonadditive stacks and unbound tooltip or size values cannot produce misleading charts
#[test]
fn encoding_contract_rejects_unbound_values_and_incompatible_aggregations() {
    let doc = add(&base(), "chart", dynamic());
    model::validate(&doc).unwrap();
    for (pointer, value) in [
        ("/config/encoding/orientation", json!("diagonal")),
        ("/config/encoding/stacked", json!(1)),
        ("/config/encoding/symbolSize", json!(101)),
        ("/config/encoding/topSeries", json!(0)),
        ("/config/encoding/categoryOrder", json!(["East", "East"])),
        ("/config/encoding/tooltip", json!(["unknown"])),
        ("/config/encoding/colors", json!({"A":3})),
        ("/config/encoding/colorBy", json!("value")),
        ("/config/encoding/seriesRanking", json!("unknown")),
        ("/binding/seriesField", json!("region")),
        ("/binding/categoryField", json!("missing")),
        ("/binding/orderBy/target", json!("missing")),
        ("/binding/orderBy/direction", json!("descending")),
        ("/binding/attributes/minimum/aggregation", json!("sum")),
        ("/binding/attributes/minimum/field", json!("region")),
    ] {
        let mut bad = doc.clone();
        set(&mut bad["manifest"]["components"]["chart"], pointer, value);
        assert!(model::validate(&bad).is_err(), "accepted {pointer}");
    }
    for (key, value) in [("unknown", json!(true)), ("sizeBy", json!("value"))] {
        let mut bad = doc.clone();
        bad["manifest"]["components"]["chart"]["config"]["encoding"][key] = value;
        assert!(model::validate(&bad).is_err());
    }
    let mut bad = doc.clone();
    bad["manifest"]["components"]["chart"]["binding"]["scale"] = json!({"value":100});
    assert!(model::validate(&bad).is_err());
    bad = doc.clone();
    bad["manifest"]["metrics"]["total"]["aggregation"] = json!("avg");
    assert!(model::validate(&bad).is_err());
    bad = doc.clone();
    bad["manifest"]["components"]["chart"]["binding"]["timeGrain"] = json!(true);
    assert!(model::validate(&bad).is_err());
    let mut scatter = dynamic();
    scatter["config"]["code"] = json!("r02");
    scatter["config"]["encoding"] =
        json!({"colorBy":"label","sizeBy":"x","symbolSize":12,"tooltip":["x","y","label"]});
    scatter["binding"]["measures"] = json!({"x":"total","y":"baseline"});
    scatter["binding"]
        .as_object_mut()
        .unwrap()
        .remove("orderBy");
    let valid = add(&base(), "scatter", scatter);
    model::validate(&valid).unwrap();
    let mut missing = valid;
    missing["manifest"]["components"]["scatter"]["config"]["encoding"]["sizeBy"] = json!("label");
    assert!(model::validate(&missing).is_err());
}

// @wu-test type=integration | scope=bound KPI comparisons and sparklines | protects=current and baseline sums are compared after filtering and chart series follow date order
#[test]
fn bound_kpi_comparisons_and_sparklines_use_filtered_aggregates() {
    let root = tempfile::tempdir().unwrap();
    let store = Store::new(root.path(), None).unwrap();
    let component = json!({"kind":"legacy","family":"kpi","title":"Revenue","datasetId":"data",
        "config":{"type":"mc03","label":"Revenue","value":0,"sparkData":[],"yoy":"stale","subVal":"stale"},
        "binding":{"datasetId":"data","measures":{"value":"total","mom":"baseline"},"comparisons":{"mom":{"current":"value","baseline":"mom","mode":"relative"}},"timeField":"month"}});
    let mut doc = add(&base(), "kpi", component);
    doc = model::apply_operations(&doc, &[json!({"op":"set_filters","value":[{"id":"region","field":"region","op":"in","values":["East"],"componentIds":["kpi"]}]})]).unwrap();
    let compact = store.compact(&doc).unwrap();
    let view = LocalView::new(store.data.clone(), None)
        .prepare(&compact, None, None, None)
        .unwrap();
    let kpi = &view["computed"]["components"]["kpi"];
    assert_eq!(kpi["value"], "30 USD");
    assert_eq!(kpi["mom"], "+20%");
    assert_eq!(kpi["yoy"], "—");
    assert_eq!(kpi["subVal"], "—");
    assert_eq!(kpi["sparkMonths"], json!(["2026-01-01", "2026-02-01"]));
    assert_eq!(
        kpi["sparkData"]
            .as_array()
            .unwrap()
            .iter()
            .map(Value::as_f64)
            .collect::<Vec<_>>(),
        vec![Some(12.0), Some(18.0)]
    );
    let filtered = json!([{"id":"region","field":"region","op":"in","values":["West"],"componentIds":["kpi"]}]);
    let view = LocalView::new(store.data.clone(), None)
        .prepare(&compact, Some(&filtered), None, None)
        .unwrap();
    assert_eq!(view["computed"]["components"]["kpi"]["mom"], "—");
    assert_eq!(view["computed"]["components"]["kpi"]["value"], "20 USD");
    let mut invalid = doc.clone();
    invalid["manifest"]["components"]["kpi"]["binding"]["comparisons"]["mom"]["baseline"] =
        json!("unbound");
    assert!(model::validate(&invalid).is_err());
    invalid = doc;
    invalid["manifest"]["components"]["kpi"]["binding"]["scale"] = json!({"value":0});
    assert!(model::validate(&invalid).is_err());
}

// @wu-test type=integration | scope=grouped table presentation | protects=ratio columns divide aggregated operands, zero denominators display missing and pagination cannot hide valid groups
#[test]
fn grouped_table_formats_ratios_and_keeps_exportable_numeric_results() {
    let root = tempfile::tempdir().unwrap();
    let store = Store::new(root.path(), None).unwrap();
    let component = json!({"kind":"table","title":"Regional efficiency","datasetId":"data","presentation":{
        "columns":[{"key":"region"},{"key":"unit"},{"key":"amount"},{"key":"prior"},{"key":"ratio"}],
        "groupBy":["region","unit"],"sumFields":["amount","prior","ratio"],
        "calculatedColumns":{"ratio":{"numerator":"amount","denominator":"prior","unitField":"unit","decimals":1}},
        "tableState":{"page":9,"pageSize":10,"sortCol":"amount","sortDir":"desc","columns":["region","unit","amount","prior","ratio"],"visible":["region","ratio"]}
    }});
    let doc = add(&base(), "table", component);
    let compact = store.compact(&doc).unwrap();
    let view = LocalView::new(store.data.clone(), None)
        .prepare(&compact, None, None, None)
        .unwrap();
    assert_eq!(view["computed"]["tables"]["table"]["page"], 1);
    assert_eq!(view["computed"]["tables"]["table"]["totalRows"], 2);
    let rows = &view["computed"]["components"]["table"]["rows"];
    assert_eq!(rows[0]["region"], "East");
    assert_eq!(rows[0]["ratio"], "120.0%");
    assert_eq!(rows[1]["ratio"], "—");
    let reference = &compact["snapshot"]["datasetRefs"]["data"];
    let numeric = store
        .data
        .grouped_rows(
            reference,
            &[],
            None,
            &[],
            0,
            10,
            "",
            &["region".into(), "unit".into()],
            &["amount".into(), "prior".into(), "ratio".into()],
            Some(&doc["manifest"]["components"]["table"]["presentation"]["calculatedColumns"]),
        )
        .unwrap();
    assert_eq!(numeric["rows"][0]["ratio"], 1.2);
    assert!(numeric["rows"][1]["ratio"].is_null());
    for state in [
        json!({"page":0}),
        json!({"pageSize":3}),
        json!({"keyword":3}),
        json!({"keyword":"x".repeat(1001)}),
    ] {
        assert!(LocalView::new(store.data.clone(), None)
            .prepare(&compact, None, Some(&json!({"table":state})), None)
            .is_err());
    }
    for (pointer, value) in [
        (
            "/presentation/calculatedColumns/ratio/unitField",
            json!("regionUnknown"),
        ),
        (
            "/presentation/calculatedColumns/ratio/numerator",
            json!("region"),
        ),
        ("/presentation/calculatedColumns/ratio/decimals", json!(7)),
        ("/presentation/tableState/columns", json!(["region"])),
        (
            "/presentation/tableState/visible",
            json!(["region", "region"]),
        ),
        ("/presentation/tableState/sortCol", json!("missing")),
    ] {
        let mut bad = doc.clone();
        set(&mut bad["manifest"]["components"]["table"], pointer, value);
        assert!(model::validate(&bad).is_err(), "{pointer}");
    }
}

// @wu-test type=integration | scope=unbound table persistence | protects=compact storage preserves row types and restores original table data without retaining stale references
#[test]
fn unbound_original_tables_round_trip_through_private_data_references() {
    let root = tempfile::tempdir().unwrap();
    let store = Store::new(root.path(), None).unwrap();
    let rows = json!([{"city":"East","value":1,"flag":true},{"city":"West","value":null}]);
    let doc = add(
        &base(),
        "table",
        json!({"kind":"legacy","family":"table","title":"Original rows","config":{"columns":[{"key":"city"},{"key":"value"},{"key":"flag"}],"rows":rows}}),
    );
    let compact = store.compact(&doc).unwrap();
    assert_eq!(
        compact["manifest"]["components"]["table"]["config"]["rows"],
        json!([])
    );
    assert_eq!(
        compact["snapshot"]["componentDataRefs"]["table"]["rowCount"],
        2
    );
    let hydrated = store.hydrate(&compact).unwrap();
    assert_eq!(
        hydrated["manifest"]["components"]["table"]["config"]["rows"],
        rows
    );
    assert!(hydrated["manifest"]["components"]["table"]["config"]
        .get("rowsRef")
        .is_none());
    assert!(hydrated["snapshot"].get("componentDataRefs").is_none());
    let mut cleared = compact.clone();
    cleared["manifest"]["components"]["table"]["config"]
        .as_object_mut()
        .unwrap()
        .remove("rowsRef");
    let cleared = store.compact(&cleared).unwrap();
    assert!(cleared["snapshot"]["componentDataRefs"]
        .get("table")
        .is_none());
    let mut wrong = compact.clone();
    wrong["snapshot"]["componentDataRefs"]["table"]["rowCount"] = json!(999);
    assert_eq!(store.compact(&wrong).unwrap_err().code, "INVALID_DOCUMENT");
    let mut large = compact;
    large["snapshot"]["componentDataRefs"]["table"]["rowCount"] = json!(20001);
    assert_eq!(
        store.hydrate(&large).unwrap_err().code,
        "LOCAL_DATA_REQUIRED"
    );
}

// @wu-test type=boundary | scope=chart comparability | protects=nonadditive pie charts, mixed units and unlabelled scatter or waterfall semantics are rejected
#[test]
fn legacy_chart_compatibility_and_preset_switching_preserve_semantics() {
    let doc = base();
    let c = json!({"kind":"chart","datasetId":"data","x":"region","measures":["total"]});
    assert!(model::compatibility(&doc, &c, "bar").is_none());
    assert!(model::compatibility(&doc, &c, "scatter")
        .unwrap()
        .contains("numeric"));
    assert!(model::compatibility(&doc, &c, "heatmap")
        .unwrap()
        .contains("second"));
    assert!(model::compatibility(&doc, &c, "waterfall")
        .unwrap()
        .contains("delta"));
    assert!(model::compatibility(&doc, &c, "unknown").is_some());
    let mut no_x = c.clone();
    no_x["x"] = json!("");
    assert!(model::compatibility(&doc, &no_x, "bar").is_some());
    let mut many = c.clone();
    many["measures"] = json!(["total", "baseline"]);
    assert!(model::compatibility(&doc, &many, "pie").is_some());
    let mut different = doc.clone();
    different["manifest"]["metrics"]["baseline"]["unit"] = json!("kg");
    assert!(model::compatibility(&different, &many, "bar")
        .unwrap()
        .contains("Mixed units"));
    different = doc.clone();
    different["manifest"]["metrics"]["total"]["aggregation"] = json!("avg");
    assert!(model::compatibility(&different, &c, "pie")
        .unwrap()
        .contains("additive"));
    let mut series = c;
    series["series"] = json!("product");
    assert!(model::compatibility(&doc, &series, "pie")
        .unwrap()
        .contains("series"));
    let chart =
        json!({"kind":"legacy","family":"chart","title":"Original","config":original("c01")});
    let one = add(&doc, "chart", chart);
    let before =
        one["manifest"]["components"]["chart"]["config"]["presentation"]["axisLabels"].clone();
    let two = model::apply_operations(
        &one,
        &[json!({"op":"set_original_chart","id":"chart","code":"c02"})],
    )
    .unwrap();
    assert_eq!(
        two["manifest"]["components"]["chart"]["config"]["code"],
        "c02"
    );
    assert_eq!(
        two["manifest"]["components"]["chart"]["config"]["presentation"]["axisLabels"]["x"],
        before["y"]
    );
    assert_eq!(
        model::apply_operations(
            &two,
            &[json!({"op":"set_original_chart","id":"chart","code":"r03"})]
        )
        .unwrap_err()
        .code,
        "INCOMPATIBLE_CHART"
    );
}

// @wu-test type=boundary | scope=document and import validation | protects=invalid business metadata and conflicting row sources are rejected without silently repairing them
#[test]
fn invalid_document_and_dataset_inputs_fail_before_mutating_assets() {
    let doc = base();
    for (pointer, value) in [
        ("/schemaVersion", json!(1)),
        ("/id", json!("bad/path")),
        ("/revision", json!(-1)),
        ("/manifest/title", json!("")),
        ("/manifest/theme", json!("unknown")),
        ("/snapshot/status", json!("unknown")),
        ("/snapshot/updatedAt", json!(false)),
        ("/manifest/datasets/data/sourceId", json!("missing")),
        (
            "/manifest/datasets/data/fields/amount/type",
            json!("object"),
        ),
        ("/snapshot/datasets/data/0/amount", json!("12")),
        ("/manifest/metrics/total/aggregation", json!("median")),
        ("/manifest/metrics/total/status", json!("certified")),
        ("/manifest/metrics/total/definition", json!("")),
        ("/manifest/metrics/total/unit", Value::Null),
    ] {
        let mut invalid = doc.clone();
        set(&mut invalid, pointer, value);
        assert!(model::validate(&invalid).is_err(), "{pointer}");
    }
    let mut invalid = doc.clone();
    invalid["manifest"]["meta"] = json!({"iconKey":"unknown"});
    assert!(model::validate(&invalid).is_err());
    invalid = doc.clone();
    invalid["manifest"]["meta"] = json!({"unrecognized":"value"});
    assert!(model::validate(&invalid).is_err());
    invalid = doc.clone();
    invalid["manifest"]["metrics"]["total"]["format"] = json!("percent");
    assert!(model::validate(&invalid).is_err());
    invalid = doc.clone();
    invalid["snapshot"]["datasets"]["data"][0]["extra"] = json!(true);
    assert!(model::validate(&invalid).is_err());
    assert!(model::apply_operations(&doc, &[]).is_err());
    assert_eq!(
        model::apply_operations(&doc, &[json!({"op":"arbitrary"})])
            .unwrap_err()
            .code,
        "UNKNOWN_OPERATION"
    );
    for request in [
        json!({"rows":[1]}),
        json!({"rows":[{}],"csvText":"x\n1"}),
        json!({"rows":[{"x":1}],"fields":{}}),
        json!({"csvText":"x\nNaN","fields":{"x":{"type":"number"}}}),
        json!({"csvText":"x\nmaybe","fields":{"x":{"type":"boolean"}}}),
        json!({"csvText":"x\n1","fields":{"missing":{"type":"string"}}}),
    ] {
        assert!(
            dataset_authoring::parse_input(&request).is_err(),
            "{request}"
        );
    }
    let inferred =
        model::inferred_fields(&[json!({"a":null,"b":true}), json!({"a":4,"c":"text"})]).unwrap();
    assert_eq!(inferred["a"]["type"], "number");
    assert_eq!(inferred["b"]["type"], "boolean");
    assert_eq!(inferred["c"]["type"], "string");
    assert!(model::inferred_fields(&[]).is_err());
    let dataset = LocalData::new(None).unwrap();
    assert!(dataset
        .import_rows(&[json!({"value":{}})], &json!({"value":{"type":"string"}}))
        .is_err());
}

// @wu-test type=boundary | scope=discovery selections | protects=ambiguous or unsupported declarations cannot masquerade as reviewed chart contracts
#[test]
fn discovery_rejects_ambiguous_selections_and_retains_original_catalog() {
    for invalid in [
        json!({"chartType":"bar"}),
        json!({"code":"c01","codes":["c01"]}),
        json!({"code":1}),
        json!({"codes":{}}),
        json!({"codes":[]}),
        json!({"codes":[1]}),
        json!({"codes":["c01","c01"]}),
        json!({"code":"missing"}),
    ] {
        assert!(discovery::declarations(&invalid).is_err(), "{invalid}");
    }
    let catalog = discovery::catalog();
    assert_eq!(catalog["charts"].as_array().unwrap().len(), 40);
    assert_eq!(catalog["originalKpis"].as_array().unwrap().len(), 16);
    assert!(!discovery::layouts().is_null());
    assert!(discovery::examples(Some("missing")).is_err());
    let declaration = discovery::declarations(&json!({"codes":["c01","mc01"]})).unwrap();
    assert_eq!(declaration["selections"].as_array().unwrap().len(), 2);
    assert_eq!(
        declaration["legacy"]["chartCodes"]
            .as_object()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(
        declaration["legacy"]["kpiTypes"].as_object().unwrap().len(),
        1
    );
    let c = json!({"kind":"legacy","family":"chart","title":"Unsafe binding","config":{"renderer":"echarts","code":"custom","echarts":{"series":[]}},"binding":{"datasetId":"data","measures":{"value":"total"}}});
    assert!(validation::validate_original(&c).is_err());
}
