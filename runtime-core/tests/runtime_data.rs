use charts_design_core::runtime::{
    data::LocalData,
    query::QueryRunner,
    statistics,
    view::{formatted, LocalView},
};
use serde_json::{json, Value};
use std::{
    fs,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, Barrier,
    },
    thread,
    time::Duration,
};

// @wu-test type=unit | scope=native immutable data | protects=Python data versions, field order and missing/null remain readable
#[test]
fn immutable_version_matches_existing_python_bytes() {
    let data = LocalData::new(None).unwrap();
    let fields = json!({"z":{"type":"boolean"},"a":{"type":"number"},"d":{"type":"date"}});
    let rows = vec![
        json!({"z":true,"a":1.0,"d":"2026-11"}),
        json!({"a":2,"d":null}),
        json!({"z":null,"a":-0.0}),
    ];
    let reference = data.import_rows(&rows, &fields).unwrap();
    assert_eq!(
        reference["version"],
        "41a1f9bfed808745b837d8fac7ebd366024e869aa7a5ac7a12dcf4daec2c9b77"
    );
    assert_eq!(reference["fieldOrder"], json!(["z", "a", "d"]));
    assert_eq!(reference["hasMissingFields"], true);
    assert_eq!(data.all_rows(&reference).unwrap(), rows);
    assert_eq!(data.import_rows(&rows, &fields).unwrap(), reference);
    assert!(data.import_rows(&[json!({"z":1})], &fields).is_err());
    assert_eq!(data.import_rows(&rows, &fields).unwrap(), reference);
}

// @wu-test type=behavior | scope=native filters and paging | protects=missing keys stay distinct from null and mixed-case sort directions cannot skip or repeat rows
#[test]
fn filters_null_missing_and_seek_pages() {
    let data = LocalData::new(None).unwrap();
    let fields = json!({"label":{"type":"string"},"n":{"type":"number"},"flag":{"type":"boolean"}});
    let reference = data
        .import_rows(
            &[
                json!({"label":"Alpha","n":1,"flag":true}),
                json!({"label":"Bravo","n":null,"flag":false}),
                json!({"label":"Charlie","flag":null}),
                json!({"label":"Delta","n":2,"flag":true}),
                json!({"label":"Echo","n":1,"flag":false}),
            ],
            &fields,
        )
        .unwrap();
    let result = data
        .rows(
            &reference,
            &[json!({"field":"n","op":"in","values":[null]})],
            None,
            &[],
            0,
            100,
            "",
        )
        .unwrap();
    assert_eq!(result["totalRows"], 1);
    assert_eq!(result["rows"][0]["label"], "Bravo");
    let result = data
        .rows(&reference, &[], None, &[], 0, 100, "null")
        .unwrap();
    assert_eq!(result["totalRows"], 2);
    for (direction, expected) in [
        ("desc", ["Delta", "Alpha", "Echo", "Bravo", "Charlie"]),
        ("DESC", ["Delta", "Alpha", "Echo", "Bravo", "Charlie"]),
        ("ASC", ["Bravo", "Charlie", "Alpha", "Echo", "Delta"]),
    ] {
        let sort = [json!({"field":"n","direction":direction})];
        let mut pages = Vec::new();
        for offset in [0, 2, 4] {
            let page = data
                .rows(&reference, &[], None, &sort, offset, 2, "")
                .unwrap();
            assert_eq!(page["totalRows"], 5);
            pages.extend(page["rows"].as_array().unwrap().clone());
        }
        let labels = pages
            .iter()
            .map(|row| row["label"].as_str().unwrap())
            .collect::<Vec<_>>();
        assert_eq!(
            labels, expected,
            "{direction} must keep the same order on every page"
        );
    }
    assert_eq!(
        data.rows(&reference, &[], None, &[], 0, 100, "true")
            .unwrap()["totalRows"],
        2
    );
}

// @wu-test type=unit | scope=native aggregates | protects=entity net amounts and ratio-of-sums are not replaced by row averages
#[test]
fn ratio_and_entity_ratio_preserve_business_semantics() {
    let d = LocalData::new(None).unwrap();
    let fields = json!({"entity":{"type":"string"},"group":{"type":"string"},"a":{"type":"number"},"b":{"type":"number"},"date":{"type":"date"}});
    let r = d
        .import_rows(
            &[
                json!({"entity":"e1","group":"g","a":10,"b":20,"date":"2026-10-01"}),
                json!({"entity":"e1","group":"g","a":-10,"b":0,"date":"2026-10-03"}),
                json!({"entity":"e2","group":"g","a":3,"b":6,"date":"2026-11-01"}),
                json!({"entity":null,"group":"g","a":9,"b":18,"date":"2026-11-02"}),
            ],
            &fields,
        )
        .unwrap();
    let ratio = d
        .aggregate(
            &r,
            &json!({"r":{"aggregation":"ratio","numerator":"a","denominator":"b"}}),
            &[],
            &[],
            None,
        )
        .unwrap();
    assert!((ratio[0]["r"].as_f64().unwrap() - 12.0 / 44.0).abs() < 1e-12);
    let entity=d.aggregate(&r,&json!({"r":{"aggregation":"entity_ratio","numerator":"a","denominator":"b","entityField":"entity"}}),&[],&[],None).unwrap();
    assert_eq!(entity[0]["r"], 0.5);
    let grouped = d
        .aggregate(
            &r,
            &json!({"total":{"aggregation":"sum","field":"a"}}),
            &[],
            &["date".into()],
            Some("quarter"),
        )
        .unwrap();
    assert_eq!(grouped[0]["date"], "2026 Q4");
    assert_eq!(grouped[0]["total"], 12);
}

// @wu-test type=unit | scope=native grouping | protects=one grouped page contains exact group count and calculated ratio
#[test]
fn grouped_page_and_calculated_columns() {
    let d = LocalData::new(None).unwrap();
    let fields = json!({"group":{"type":"string"},"a":{"type":"number"},"b":{"type":"number"},"ratio":{"type":"number"}});
    let r = d
        .import_rows(
            &[
                json!({"group":"A","a":2,"b":4}),
                json!({"group":"A","a":3,"b":6}),
                json!({"group":"B","a":7,"b":0}),
            ],
            &fields,
        )
        .unwrap();
    let columns = vec!["group".into(), "a".into(), "ratio".into()];
    let groups = vec!["group".into()];
    let sums = vec!["a".into(), "b".into(), "ratio".into()];
    let calculated = json!({"ratio":{"numerator":"a","denominator":"b"}});
    let result = d
        .grouped_rows(
            &r,
            &[],
            Some(&columns),
            &[],
            0,
            1,
            "",
            &groups,
            &sums,
            Some(&calculated),
        )
        .unwrap();
    assert_eq!(result["totalRows"], 2);
    assert_eq!(result["rows"][0], json!({"group":"A","a":5,"ratio":0.5}));
    let empty = d
        .grouped_rows(
            &r,
            &[],
            Some(&columns),
            &[],
            8,
            1,
            "",
            &groups,
            &sums,
            Some(&calculated),
        )
        .unwrap();
    assert_eq!(empty["totalRows"], 2);
    assert!(empty["rows"].as_array().unwrap().is_empty());
}

// @wu-test type=integration | scope=native multi-file options | protects=more than ten immutable cloud query files can be searched without truncation
#[test]
fn options_span_twelve_readonly_query_files() {
    let temp = tempfile::tempdir().unwrap();
    let d = LocalData::new(Some(&temp.path().join("merged"))).unwrap();
    let mut refs = Vec::new();
    for i in 0..12 {
        let source = LocalData::new(Some(&temp.path().join(format!("source-{i}")))).unwrap();
        let r = source
            .import_rows(
                &[
                    json!({"value":format!("label-{i:02}")}),
                    json!({"value":null}),
                ],
                &json!({"value":{"type":"string"}}),
            )
            .unwrap();
        d.mount_version(
            r["version"].as_str().unwrap(),
            source.path.as_ref().unwrap(),
        )
        .unwrap();
        refs.push(r);
    }
    let result = d.option_page(&refs, "value", "label-", 10, 3).unwrap();
    assert_eq!(result["totalValues"], 12);
    assert_eq!(result["values"], json!(["label-10", "label-11"]));
    assert_eq!(result["hasMore"], false);
    let all = d.option_page(&refs, "value", "", 0, 100).unwrap();
    assert_eq!(all["totalValues"], 13);
    assert_eq!(all["values"][0], Value::Null);
}

// @wu-test type=unit | scope=native bounded cache | protects=parallel requests share one calculation and returned values cannot poison cache
#[test]
fn cache_singleflight_and_copy_isolation() {
    use charts_design_core::runtime::data::QueryCache;
    let cache = QueryCache::default();
    let barrier = Arc::new(Barrier::new(6));
    let calls = Arc::new(AtomicUsize::new(0));
    let mut threads = Vec::new();
    for _ in 0..6 {
        let (c, b, n) = (cache.clone(), barrier.clone(), calls.clone());
        threads.push(thread::spawn(move || {
            b.wait();
            c.get("same".into(), || {
                n.fetch_add(1, Ordering::SeqCst);
                thread::sleep(Duration::from_millis(20));
                Ok(json!({"rows":[1,2]}))
            })
            .unwrap()
        }));
    }
    for t in threads {
        assert_eq!(t.join().unwrap().0["rows"], json!([1, 2]));
    }
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    let (mut changed, _) = cache.get("same".into(), || unreachable!()).unwrap();
    changed["rows"] = json!([99]);
    assert_eq!(
        cache.get("same".into(), || unreachable!()).unwrap().0["rows"],
        json!([1, 2])
    );
}

// @wu-test type=unit | scope=native cache recovery | protects=a failed calculation cannot leave later requests waiting forever
#[test]
fn cache_retries_after_calculation_panics() {
    use charts_design_core::runtime::data::QueryCache;
    let cache = QueryCache::default();
    let failed = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        cache.get("retry".into(), || panic!("interrupted calculation"))
    }));
    assert!(failed.is_err());
    let (sender, receiver) = std::sync::mpsc::channel();
    let worker = thread::spawn(move || {
        sender
            .send(cache.get("retry".into(), || Ok(json!({"ready":true}))))
            .unwrap();
    });
    let result = receiver
        .recv_timeout(Duration::from_secs(2))
        .expect("A cancelled singleflight owner must release its key")
        .unwrap();
    assert_eq!(result.0, json!({"ready":true}));
    assert!(!result.1);
    worker.join().unwrap();
}

// @wu-test type=unit | scope=native CSV export | protects=complete streamed rows, spreadsheet formula escaping, and immutable database
#[test]
fn csv_is_complete_safe_and_cannot_overwrite_database() {
    use base64::Engine;
    let temp = tempfile::tempdir().unwrap();
    let d = LocalData::new(Some(temp.path())).unwrap();
    let r = d
        .import_rows(
            &[
                json!({"value":"=1+1","flag":true}),
                json!({"value":"plain","flag":false}),
            ],
            &json!({"value":{"type":"string"},"flag":{"type":"boolean"}}),
        )
        .unwrap();
    let receipt = d
        .export_csv(&r, None, &[], None, &[], "", None, None, None)
        .unwrap();
    let raw = base64::engine::general_purpose::STANDARD
        .decode(receipt["content"].as_str().unwrap())
        .unwrap();
    assert!(raw.starts_with(&[0xef, 0xbb, 0xbf]));
    assert_eq!(
        String::from_utf8(raw[3..].to_vec()).unwrap(),
        "value,flag\r\n'=1+1,true\r\nplain,false\r\n"
    );
    assert!(d
        .export_csv(&r, d.path.as_deref(), &[], None, &[], "", None, None, None)
        .is_err());
    assert_eq!(d.all_rows(&r).unwrap().len(), 2);
}

// @wu-test type=integration | scope=native SQLite source | protects=source SQL remains bounded read-only and uses declared scalar types
#[test]
fn sqlite_sources_reject_side_effects_and_multiple_statements() {
    let temp = tempfile::tempdir().unwrap();
    let file = temp.path().join("source.sqlite3");
    let db = rusqlite::Connection::open(&file).unwrap();
    db.execute_batch(
        "CREATE TABLE sample(n INTEGER,flag BOOLEAN);INSERT INTO sample VALUES(1,1),(2,0)",
    )
    .unwrap();
    drop(db);
    let cfg = temp.path().join("sources.json");
    fs::write(
        &cfg,
        serde_json::to_vec(&json!({"source":{"engine":"sqlite","path":file}})).unwrap(),
    )
    .unwrap();
    let q = QueryRunner::new(Some(&cfg)).unwrap();
    let fields = json!({"n":{"type":"number"},"flag":{"type":"boolean"}});
    let r = q
        .execute(
            "source",
            "SELECT n,flag FROM sample WHERE n>=:minimum",
            Some(&json!({"minimum":1})),
            5.0,
            Some(&fields),
            Some("sqlite"),
        )
        .unwrap();
    assert_eq!(r.rows[0], json!({"n":1,"flag":true}));
    for sql in [
        "DELETE FROM sample RETURNING n",
        "SELECT load_extension('no')",
        "SELECT 1;SELECT 2",
        "ATTACH ':memory:' AS other",
        "SELECT n,n FROM sample",
    ] {
        assert!(
            q.execute("source", sql, None, 5.0, None, None).is_err(),
            "{sql}"
        );
    }
    assert!(q
        .execute("missing", "SELECT 1", None, 5.0, None, None)
        .is_err());
    assert_eq!(
        q.execute(
            "source",
            "SELECT COUNT(*) AS n FROM sample",
            None,
            5.0,
            None,
            None
        )
        .unwrap()
        .rows[0]["n"],
        2
    );
}

// @wu-test type=integration | scope=native DuckDB source | protects=single SELECT boundaries, bounded results and supported scalar types
#[test]
fn duckdb_native_parser_enforces_one_readonly_select() {
    let temp = tempfile::tempdir().unwrap();
    let file = temp.path().join("source.duckdb");
    let db = duckdb::Connection::open(&file).unwrap();
    db.execute_batch("CREATE TABLE sample(n INTEGER);INSERT INTO sample VALUES(1),(2)")
        .unwrap();
    drop(db);
    let cfg = temp.path().join("sources.json");
    fs::write(
        &cfg,
        serde_json::to_vec(&json!({"source":{"engine":"duckdb","path":file}})).unwrap(),
    )
    .unwrap();
    let q = QueryRunner::new(Some(&cfg)).unwrap();
    let result = q
        .execute(
            "source",
            "SELECT n FROM sample WHERE n >= $minimum",
            Some(&json!({"minimum":2})),
            5.0,
            None,
            None,
        )
        .unwrap();
    assert_eq!(result.rows, json!([{"n":2}]).as_array().unwrap().clone());
    for sql in [
        "-- query\n/* outer /* nested */ end */ SELECT n FROM sample",
        "WITH selected AS (SELECT n FROM sample) SELECT n FROM selected",
        "(SELECT n FROM sample)",
        "VALUES (1), (2)",
        "FROM sample SELECT n",
        "TABLE sample",
    ] {
        assert_eq!(
            q.execute("source", sql, None, 5.0, None, None)
                .unwrap_or_else(|error| panic!("{sql}: {error:?}"))
                .rows
                .len(),
            2,
            "{sql}"
        );
    }
    for sql in [
        "SELECT 1;DELETE FROM sample",
        "SELECT 1;SELECT 2",
        "PRAGMA version",
        "; -- command\r\n /* outer /* nested */ end */ pRaGmA version;",
        "CALL pragma_version()",
        "SET threads = 2",
        "EXPLAIN SELECT n FROM sample",
        "COPY sample TO '/tmp/charts-should-not-exist.csv'",
        "SELECT * FROM read_csv('/etc/passwd')",
    ] {
        assert!(
            q.execute("source", sql, None, 5.0, None, None).is_err(),
            "{sql}"
        );
    }
    // This result cannot be materialized within the query budget. Fetching the
    // first 10001 rows must reach the explicit result limit instead of timing
    // out or allocating memory for the full source relation.
    let oversized = q
        .execute(
            "source",
            "SELECT i FROM range(1000000000) AS numbers(i)",
            None,
            2.0,
            None,
            None,
        )
        .err()
        .expect("Oversized source queries must be rejected");
    assert_eq!(oversized.code, "INVALID_ARGUMENT");
    assert!(oversized.message.contains("10000"));
    let scalars = q.execute(
        "source",
        "SELECT '550e8400-e29b-41d4-a716-446655440000'::UUID AS id, 'active'::ENUM('active','closed') AS state, 7::UHUGEINT AS unsigned, TIMESTAMPTZ '2026-11-28 12:34:56+08' AS moment",
        None, 5.0, None, None,
    ).unwrap();
    assert_eq!(
        scalars.rows[0],
        json!({
            "id":"550e8400-e29b-41d4-a716-446655440000",
            "state":"active","unsigned":7,"moment":"2026-11-28T04:34:56+00:00"
        })
    );
    assert!(q
        .execute(
            "source",
            "SELECT TIMESTAMP_S 'infinity' AS moment",
            None,
            5.0,
            None,
            None
        )
        .is_err());
    assert_eq!(
        q.execute(
            "source",
            "SELECT COUNT(*) AS n FROM sample",
            None,
            5.0,
            None,
            None
        )
        .unwrap()
        .rows[0]["n"],
        2
    );
}

// @wu-test type=unit | scope=native statistical mathematics | protects=equal-width counts, linear quartiles and stable large-offset OLS remain unchanged
#[test]
fn statistical_math_matches_declared_methods() {
    let (edges, counts) = statistics::histogram(&[1.0, 1.0, 1.0], 2).unwrap();
    assert_eq!(edges, vec![0.5, 1.0, 1.5]);
    assert_eq!(counts, vec![0, 3]);
    let s = statistics::box_summary(&[1., 2., 3., 4., 5., 6., 7., 8., 9., 10., 100.]).unwrap();
    assert_eq!(s["median"], 6.0);
    assert_eq!(s["q1"], 3.5);
    assert_eq!(s["q3"], 8.5);
    assert_eq!(s["outliers"], json!([100.]));
    let (x, y) = statistics::regression_line(&[1e12, 1e12 + 1., 1e12 + 2.], &[3., 5., 7.]).unwrap();
    assert_eq!(x, [1e12, 1e12 + 2.]);
    assert!((y[0] - 3.0).abs() < 1e-12 && (y[1] - 7.0).abs() < 1e-12);
}

// @wu-test type=unit | scope=native display formatting | protects=half-up rounding, signed percentages and negative zero match business cards
#[test]
fn formatting_preserves_decimal_half_up() {
    let m = json!({"decimals":2,"unit":"元"});
    assert_eq!(
        formatted(&json!(1234.565), &m, false).unwrap(),
        "1,234.57 元"
    );
    assert_eq!(formatted(&json!(-0.0001), &m, false).unwrap(), "0 元");
    assert_eq!(
        formatted(
            &json!(0.1255),
            &json!({"format":"percent","decimals":1}),
            true
        )
        .unwrap(),
        "+12.6%"
    );
    assert_eq!(formatted(&Value::Null, &m, true).unwrap(), "—");
}

fn simple_document(data: &LocalData) -> Value {
    let fields =
        json!({"region":{"type":"string"},"value":{"type":"number"},"date":{"type":"date"}});
    let reference = data
        .import_rows(
            &[
                json!({"region":"North","value":10,"date":"2026-10-01"}),
                json!({"region":"South","value":20,"date":"2026-11-01"}),
            ],
            &fields,
        )
        .unwrap();
    json!({"schemaVersion":1,"id":"test","revision":1,"manifest":{"title":"Test","sources":{"src":{"kind":"supplied","name":"Synthetic","verification":"supplied"}},"datasets":{"sales":{"fields":fields,"sourceId":"src"}},"metrics":{"sales":{"datasetId":"sales","field":"value","aggregation":"sum","unit":"元","decimals":0,"status":"unverified"}},"components":{"kpi":{"kind":"legacy","family":"kpi","title":"Revenue","datasetId":"sales","config":{"type":"mc01"},"binding":{"datasetId":"sales","measures":{"value":"sales"}}}},"filters":[]},"snapshot":{"datasets":{},"datasetRefs":{"sales":reference},"updatedAt":"2026-11-28T00:00:00Z"}})
}
// @wu-test type=integration | scope=native local view | protects=resolved KPI values are calculated from immutable data with reusable semantic cache
#[test]
fn local_view_resolves_kpi_without_shipping_source_rows() {
    let data = LocalData::new(None).unwrap();
    let doc = simple_document(&data);
    let view = LocalView::new(data, None);
    let first = view.prepare(&doc, None, None, None).unwrap();
    assert_eq!(first["computed"]["components"]["kpi"]["value"], "30 元");
    assert!(first["snapshot"]["datasets"]
        .as_object()
        .unwrap()
        .is_empty());
    let second = view.prepare(&doc, None, None, None).unwrap();
    assert_eq!(second["computed"]["cacheHits"], 1);
    assert!(doc.get("computed").is_none());
}

// @wu-test type=integration | scope=native statistical artifacts | protects=SVG and PNG have the same native backend and omit missing observations explicitly
#[test]
fn statistical_svg_and_png_report_native_backend() {
    use base64::Engine;
    let data = LocalData::new(None).unwrap();
    let mut doc = simple_document(&data);
    doc["snapshot"]["datasets"] = json!({"sales":[{"region":"N","value":1},{"region":"N","value":2},{"region":"N","value":null}]});
    doc["manifest"]["components"] = json!({"stat":{"kind":"statistical","title":"Distribution","datasetId":"sales","plot":{"type":"histogram","x":"value","bins":2},"analysis":{"definition":"One raw measurement per row","unit":"元"}}});
    for format in ["svg", "png"] {
        let output = statistics::render_statistical(&doc, "stat", format).unwrap();
        assert_eq!(output["provenance"]["rowsUsed"], 2);
        assert_eq!(output["provenance"]["rowsDropped"], 1);
        assert_eq!(
            output["provenance"]["versions"]["charts-native-statistics"],
            "1"
        );
        assert!(output["provenance"]["versions"].get("seaborn").is_none());
        let bytes = base64::engine::general_purpose::STANDARD
            .decode(
                output["dataUri"]
                    .as_str()
                    .unwrap()
                    .split_once(',')
                    .unwrap()
                    .1,
            )
            .unwrap();
        if format == "png" {
            assert!(bytes.starts_with(b"\x89PNG\r\n\x1a\n"));
        } else {
            let text = String::from_utf8(bytes).unwrap();
            assert!(text.contains("<svg") && text.contains("<path"));
            assert!(!text.contains("<text"));
        }
    }
}
