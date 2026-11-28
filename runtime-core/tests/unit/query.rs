use super::*;
use postgres::types::{Format, IsNull, ToSql, Type};

// @wu-test type=boundary | scope=PostgreSQL DATE 参数绑定 | protects=日期文本以二进制日期发送，导致真实查询被拒绝
#[test]
fn postgres_date_parameter_uses_postgresql_text_format() {
    let date = PgParam(json!("2026-11-01"));
    let mut encoded = bytes::BytesMut::new();
    assert!(matches!(
        date.to_sql_checked(&Type::DATE, &mut encoded).unwrap(),
        IsNull::No
    ));
    assert!(matches!(date.encode_format(&Type::DATE), Format::Text));
    assert_eq!(&encoded[..], b"2026-11-01");
}

// @wu-test type=integration | scope=DuckDB scalar conversion | protects=column types, temporal units or named bindings change values when data reaches a dashboard
#[test]
fn duckdb_queries_preserve_scalar_types_and_parameter_identity() {
    let temporary = tempfile::tempdir().unwrap();
    let path = temporary.path().join("source.duckdb");
    {
        let db = duckdb::Connection::open(&path).unwrap();
        db.execute_batch("CREATE TYPE region AS ENUM ('east','west')")
            .unwrap();
    }
    let runner = QueryRunner {
        sources: HashMap::from([(
            "test".into(),
            Source {
                engine: "duckdb".into(),
                target: path.to_string_lossy().into_owned(),
            },
        )]),
    };
    let values = runner.execute("test", "SELECT NULL AS absent,true AS flag,1::TINYINT AS i8,2::SMALLINT AS i16,3::INTEGER AS i32,4::BIGINT AS i64,5::HUGEINT AS i128,6::UTINYINT AS u8,7::USMALLINT AS u16,8::UINTEGER AS u32,9::UBIGINT AS u64,10::UHUGEINT AS u128,1.5::FLOAT AS single,2.5::DOUBLE AS double,12.25::DECIMAL(10,2) AS decimal,'east'::region AS region,DATE '2026-11-28' AS day,TIME '12:34:56' AS clock,TIMESTAMP '2026-11-28 12:34:56' AS local,TIMESTAMPTZ '2026-11-28 12:34:56+00' AS instant,'550e8400-e29b-41d4-a716-446655440000'::UUID AS uuid", None, 10.0, None, None).unwrap();
    for (name, expected) in [
        ("i8", 1),
        ("i16", 2),
        ("i32", 3),
        ("i64", 4),
        ("i128", 5),
        ("u8", 6),
        ("u16", 7),
        ("u32", 8),
        ("u64", 9),
        ("u128", 10),
    ] {
        assert_eq!(values.rows[0][name], expected);
    }
    for (name, expected) in [("single", 1.5), ("double", 2.5), ("decimal", 12.25)] {
        assert_eq!(values.rows[0][name], expected);
    }
    for (name, expected) in [
        ("region", "east"),
        ("day", "2026-11-28"),
        ("clock", "12:34:56"),
        ("local", "2026-11-28T12:34:56"),
        ("instant", "2026-11-28T12:34:56+00:00"),
        ("uuid", "550e8400-e29b-41d4-a716-446655440000"),
    ] {
        assert_eq!(values.rows[0][name], expected);
    }
    assert_eq!(values.rows[0]["absent"], Value::Null);
    assert_eq!(values.rows[0]["flag"], true);
    assert_eq!(values.fields["day"]["type"], "date");
    let named = runner.execute("test", "SELECT $label::VARCHAR AS label,$flag::BOOLEAN AS flag,$n::BIGINT AS n,$fraction::DOUBLE AS fraction,$empty::VARCHAR AS empty", Some(&json!({"label":"quoted ' text","flag":true,"n":42,"fraction":1.5,"empty":null})),10.0,None,None).unwrap();
    assert_eq!(
        named.rows[0],
        json!({"label":"quoted ' text","flag":true,"n":42,"fraction":1.5,"empty":null})
    );
    let empty = runner
        .execute("test", "SELECT 1 AS n WHERE false", None, 10.0, None, None)
        .unwrap();
    assert!(empty.rows.is_empty());
    assert!(empty.fields.get("n").is_some());
    for params in [json!([]), json!([1, 2]), json!([{}])] {
        assert!(runner
            .execute("test", "SELECT ? AS n", Some(&params), 10.0, None, None)
            .is_err());
    }
}

// @wu-test type=boundary | scope=native scalar range and time conversion | protects=overflow, infinity, invalid UTF-8 or unsupported binary data silently becomes a different business value
#[test]
fn duckdb_rejects_values_outside_the_dashboard_scalar_contract() {
    use duckdb::types::{TimeUnit as U, ValueRef as D};
    for invalid in [
        D::HugeInt(i128::MAX),
        D::UHugeInt(u128::MAX),
        D::UBigInt(u64::MAX),
        D::Float(f32::NAN),
        D::Double(f64::INFINITY),
        D::Text(&[0xff]),
        D::Date32(i32::MAX),
        D::Blob(b"binary"),
        D::Timestamp(U::Microsecond, i64::MAX),
        D::Timestamp(U::Microsecond, i64::MIN),
        D::Timestamp(U::Second, i64::MAX - 1),
        D::Time64(U::Second, -1),
        D::Time64(U::Second, 86400),
        D::Time64(U::Second, i64::MAX),
    ] {
        assert_eq!(
            duck_scalar(invalid).unwrap_err().code,
            "QUERY_SCHEMA_CHANGED"
        );
    }
    for (unit, value) in [
        (U::Second, 1),
        (U::Millisecond, 1000),
        (U::Microsecond, 1_000_000),
        (U::Nanosecond, 1_000_000_000),
    ] {
        assert_eq!(duck_scalar(D::Time64(unit, value)).unwrap(), "00:00:01");
        assert_eq!(
            duck_scalar(D::Timestamp(unit, value)).unwrap(),
            "1970-01-01T00:00:01"
        );
    }
    assert_eq!(duck_scalar(D::Date32(-1)).unwrap(), "1969-12-31");
    assert_eq!(
        duck_scalar(D::Timestamp(U::Nanosecond, -1_000_000_000)).unwrap(),
        "1969-12-31T23:59:59"
    );
}
