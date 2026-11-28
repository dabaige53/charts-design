use charts_design_core::runtime::{
    data::{semantic_filters, time_grain, LocalData, QueryCache},
    error::Error,
    view::LocalView,
};
use serde_json::{json, Value};
use std::sync::atomic::{AtomicUsize, Ordering};

// @wu-test type=behavior | scope=bounded result cache | protects=least-recently-used entries are evicted, oversized results and failures never poison later requests
#[test]
fn cache_eviction_large_results_and_errors_preserve_computation_results() {
    let cache = QueryCache::new(1024, 2);
    for (key, value) in [("a", 1), ("b", 2)] {
        assert_eq!(
            cache.get(key.into(), || Ok(json!(value))).unwrap(),
            (json!(value), false)
        );
    }
    assert_eq!(
        cache.get("a".into(), || unreachable!()).unwrap(),
        (json!(1), true)
    );
    cache.get("c".into(), || Ok(json!(3))).unwrap();
    assert_eq!(
        cache.get("a".into(), || unreachable!()).unwrap(),
        (json!(1), true)
    );
    assert_eq!(
        cache.get("b".into(), || Ok(json!(22))).unwrap(),
        (json!(22), false)
    );
    let calls = AtomicUsize::new(0);
    for _ in 0..2 {
        let (value, hit) = cache
            .get("large".into(), || {
                calls.fetch_add(1, Ordering::SeqCst);
                Ok(json!("x".repeat(300)))
            })
            .unwrap();
        assert_eq!(value.as_str().unwrap().len(), 300);
        assert!(!hit);
    }
    assert_eq!(calls.load(Ordering::SeqCst), 2);
    assert_eq!(
        cache
            .get("error".into(), || Err(Error::new("RETRY", "Temporary")))
            .unwrap_err()
            .code,
        "RETRY"
    );
    assert_eq!(
        cache.get("error".into(), || Ok(json!(true))).unwrap(),
        (json!(true), false)
    );
}

// @wu-test type=behavior | scope=data search filters and formatted sorting | protects=private raw fields are not searchable, visible numeric strings sort numerically and scalar types survive filtering
#[test]
fn search_and_sort_use_visible_fields_and_keep_null_boolean_semantics() {
    let data = LocalData::new(None).unwrap();
    let fields = json!({"label":{"type":"string"},"display":{"type":"string"},"rawDisplay":{"type":"number"},"flag":{"type":"boolean"},"rawSecret":{"type":"string"},"_internal":{"type":"string"}});
    let reference = data.import_rows(&[
        json!({"label":"East","display":"$20.50","rawDisplay":20.5,"flag":true,"rawSecret":"private-token","_internal":"hidden"}),
        json!({"label":"West","display":"$3","rawDisplay":3,"flag":false}),
        json!({"label":"North","display":"Unavailable","rawDisplay":null,"flag":null}),
    ], &fields).unwrap();
    assert_eq!(
        data.rows(&reference, &[], None, &[], 0, 10, "private-token")
            .unwrap()["totalRows"],
        0
    );
    assert_eq!(
        data.rows(&reference, &[], None, &[], 0, 10, "hidden")
            .unwrap()["totalRows"],
        0
    );
    let filtered = data
        .rows(
            &reference,
            &[json!({"field":"label","op":"contains","values":["eAs"]})],
            None,
            &[],
            0,
            10,
            "",
        )
        .unwrap();
    assert_eq!(filtered["rows"][0]["label"], "East");
    assert_eq!(filtered["totalRows"], 1);
    let ranged = data
        .rows(
            &reference,
            &[json!({"field":"rawDisplay","op":"range","values":[2,21]})],
            None,
            &[json!({"field":"display","direction":"asc"})],
            0,
            10,
            "",
        )
        .unwrap();
    assert_eq!(ranged["rows"][0]["display"], "$3");
    assert_eq!(ranged["rows"][1]["display"], "$20.50");
    assert_eq!(
        data.distinct(&reference, "flag", &[]).unwrap(),
        vec![json!(true), json!(false), Value::Null]
    );
    let extra = [json!(false), json!(true), Value::Null];
    let page = data
        .option_page_extra(
            std::slice::from_ref(&reference),
            "flag",
            "",
            0,
            10,
            Some(("boolean", &extra)),
        )
        .unwrap();
    assert_eq!(page["values"], json!([null, false, true]));
    assert_eq!(page["totalValues"], 3);
    let beyond = data
        .option_page(std::slice::from_ref(&reference), "flag", "", 9, 10)
        .unwrap();
    assert!(beyond["values"].as_array().unwrap().is_empty());
    assert_eq!(beyond["totalValues"], 3);
    assert_eq!(beyond["hasMore"], false);
    let blank = data.option_page(&[], "unused", "", 0, 10).unwrap();
    assert_eq!(blank["totalValues"], 0);
    for filters in [
        vec![json!({"field":"flag","op":"unknown","values":[true]})],
        vec![json!({"field":"rawDisplay","op":"range","values":[1]})],
    ] {
        assert!(data
            .rows(&reference, &filters, None, &[], 0, 10, "")
            .is_err());
    }
    assert!(data
        .rows(
            &reference,
            &[],
            None,
            &[json!({"field":"label","direction":"backwards"})],
            0,
            10,
            ""
        )
        .is_err());
    assert!(data
        .rows(&reference, &[], Some(&[]), &[], 0, 10, "")
        .is_err());
    assert!(data
        .option_page(std::slice::from_ref(&reference), "flag", "", 0, 0)
        .is_err());
    assert!(data
        .option_page(std::slice::from_ref(&reference), "flag", "", u64::MAX, 10)
        .is_err());
    assert!(data
        .option_page(
            std::slice::from_ref(&reference),
            "flag",
            &"a".repeat(1001),
            0,
            10
        )
        .is_err());
    let formatted = data
        .import_rows(
            &[
                json!({"amount":"$20.5"}),
                json!({"amount":"3 USD"}),
                json!({"amount":"—"}),
                json!({"amount":"-2.1"}),
            ],
            &json!({"amount":{"type":"string"}}),
        )
        .unwrap();
    let sorted = data
        .rows(
            &formatted,
            &[],
            None,
            &[json!({"field":"amount","direction":"asc"})],
            0,
            10,
            "",
        )
        .unwrap();
    assert_eq!(
        sorted["rows"],
        json!([{"amount":"-2.1"},{"amount":"3 USD"},{"amount":"$20.5"},{"amount":"—"}])
    );
}

// @wu-test type=integration | scope=registered SQLite import | protects=quoted table names, booleans and failed scalar conversions cannot change the upstream database or leave staging tables
#[test]
fn sqlite_import_quotes_tables_and_recovers_after_failed_row_conversion() {
    let root = tempfile::tempdir().unwrap();
    let path = root.path().join("source.sqlite3");
    let db = rusqlite::Connection::open(&path).unwrap();
    db.execute_batch("CREATE TABLE \"sales\"\"data\" (flag BOOLEAN,amount NUMERIC);INSERT INTO \"sales\"\"data\" VALUES(1,12),(0,20);CREATE TABLE binary_data(value BLOB);INSERT INTO binary_data VALUES(x'01ff');").unwrap();
    let data = LocalData::new(Some(&root.path().join("data"))).unwrap();
    let fields = json!({"flag":{"type":"boolean"},"amount":{"type":"number"}});
    let reference = data
        .import_sqlite(&path, "sales\"data", Some(&fields))
        .unwrap();
    assert_eq!(
        data.all_rows(&reference).unwrap(),
        vec![
            json!({"flag":true,"amount":12}),
            json!({"flag":false,"amount":20})
        ]
    );
    assert!(data.import_sqlite(&path, "", None).is_err());
    assert!(data.import_sqlite(&path, "missing", None).is_err());
    assert!(data.import_sqlite(&path, "binary_data", None).is_err());
    assert_eq!(
        data.import_sqlite(&path, "sales\"data", Some(&fields))
            .unwrap(),
        reference
    );
    assert_eq!(
        db.query_row::<i64, _, _>("SELECT COUNT(*) FROM \"sales\"\"data\"", [], |r| r.get(0))
            .unwrap(),
        2
    );
    let count = data
        .with_connection(|db| {
            Ok(db.query_row::<i64, _, _>(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='staging'",
                [],
                |r| r.get(0),
            )?)
        })
        .unwrap();
    assert_eq!(count, 0);
    assert!(data.describe("not-a-hash").is_err());
    assert!(data.describe(&"0".repeat(64)).is_err());
    let mut false_reference = reference.clone();
    false_reference["rowCount"] = json!(3);
    assert_eq!(
        data.rows(&false_reference, &[], None, &[], 0, 10, "")
            .unwrap()["totalRows"],
        2,
        "Stored metadata remains authoritative over a caller-supplied row count"
    );
    assert_eq!(data.sqlite_source(&reference).unwrap().1, reference);
}

// @wu-test type=behavior | scope=aggregate semantic cache | protects=renamed display metrics reuse arithmetic without confusing grouped field names and filter order
#[test]
fn aggregate_cache_reuses_semantics_across_names_and_filter_order() {
    let data = LocalData::new(None).unwrap();
    let fields = json!({"__metric_0":{"type":"string"},"n":{"type":"number"},"flag":{"type":"boolean"},"day":{"type":"date"}});
    let reference = data
        .import_rows(
            &[
                json!({"__metric_0":"A","n":2,"flag":true,"day":"2026-01-01"}),
                json!({"__metric_0":"A","n":3,"flag":true,"day":"2026-02-01"}),
                json!({"__metric_0":"B","n":4,"flag":false,"day":"2026-04-01"}),
            ],
            &fields,
        )
        .unwrap();
    let view = LocalView::new(data.clone(), None);
    let filters = [
        json!({"id":"a","field":"flag","op":"in","values":[true,true]}),
        json!({"id":"b","field":"n","op":"range","values":[1,5]}),
    ];
    let (a, hit) = view
        .aggregate(
            &reference,
            &json!({"original":{"aggregation":"sum","field":"n"}}),
            &filters,
            &["__metric_0".into()],
            None,
        )
        .unwrap();
    assert!(!hit);
    assert_eq!(a, vec![json!({"__metric_0":"A","original":5})]);
    let equivalent = [
        filters[1].clone(),
        json!({"id":"renamed","field":"flag","op":"in","values":[true]}),
    ];
    let (b, hit) = view
        .aggregate(
            &reference,
            &json!({"renamed":{"aggregation":"sum","field":"n","label":"Changed text"}}),
            &equivalent,
            &["__metric_0".into()],
            None,
        )
        .unwrap();
    assert!(hit);
    assert_eq!(b, vec![json!({"__metric_0":"A","renamed":5})]);
    assert_eq!(
        semantic_filters(&filters).unwrap(),
        semantic_filters(&equivalent).unwrap()
    );
    assert_eq!(
        semantic_filters(&[json!({"field":"flag","op":"in","values":[]})]).unwrap(),
        json!([])
    );
    let grouped=data.aggregate(&reference,&json!({"count":{"aggregation":"count"},"min":{"aggregation":"min","field":"n"},"max":{"aggregation":"max","field":"n"},"avg":{"aggregation":"avg","field":"n"}}),&[],&["flag".into()],None).unwrap();
    assert_eq!(
        grouped[0],
        json!({"flag":true,"count":2,"min":2,"max":3,"avg":2.5})
    );
    assert!(data
        .aggregate(
            &reference,
            &json!({"median":{"aggregation":"median","field":"n"}}),
            &[],
            &[],
            None
        )
        .is_err());
    assert!(view
        .aggregate(&reference, &json!([]), &[], &[], None)
        .is_err());
    assert_eq!(time_grain(&Value::Null, "month").unwrap(), Value::Null);
    assert_eq!(
        time_grain(&json!("2026-11-04"), "month").unwrap(),
        "2026-11"
    );
    assert_eq!(time_grain(&json!("2026-11"), "quarter").unwrap(), "2026 Q4");
    for invalid in ["2026-13-01", "2026/11/01", "November", "2026-11bad"] {
        assert!(time_grain(&json!(invalid), "month").is_err());
    }
}
