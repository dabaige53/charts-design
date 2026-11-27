use std::{
    fs,
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

use arrow_array::{Array, BinaryArray, BooleanArray, Float64Array, Int64Array, StringArray};
use charts_design_core::{
    export_parquet, export_parquet_with_options, inspect_parquet, ExportOptions, ExportReceipt,
};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use rusqlite::{params, params_from_iter, types::Value as SqlValue, Connection};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

struct Fixture {
    root: PathBuf,
    database: PathBuf,
    connection: Connection,
    version: String,
    fields: Vec<(String, String)>,
    count: u64,
}

impl Fixture {
    fn new(fields: &[(&str, &str)]) -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "charts-core-{}-{nonce}-{}",
            std::process::id(),
            NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        let database = root.join("data.sqlite3");
        let connection = Connection::open(&database).unwrap();
        let version = "a".repeat(64);
        let columns = (0..fields.len())
            .map(|i| format!("c{i}"))
            .collect::<Vec<_>>()
            .join(",");
        connection.execute_batch(&format!("CREATE TABLE versions (version TEXT PRIMARY KEY, metadata TEXT NOT NULL); CREATE TABLE d_{version} ({columns}, _missing TEXT); BEGIN" )).unwrap();
        Self {
            root,
            database,
            connection,
            version,
            fields: fields
                .iter()
                .map(|(a, b)| (a.to_string(), b.to_string()))
                .collect(),
            count: 0,
        }
    }

    fn insert(&mut self, mut values: Vec<SqlValue>, missing: Option<&str>) {
        values.push(
            missing
                .map(|s| SqlValue::Text(s.to_owned()))
                .unwrap_or(SqlValue::Null),
        );
        let marks = vec!["?"; values.len()].join(",");
        self.connection
            .execute(
                &format!("INSERT INTO d_{} VALUES ({marks})", self.version),
                params_from_iter(values),
            )
            .unwrap();
        self.count += 1;
    }

    fn seal(&self, include_order: bool) {
        let fields: Map<String, Value> = self
            .fields
            .iter()
            .map(|(key, kind)| (key.clone(), json!({"type":kind})))
            .collect();
        let mut metadata =
            json!({"version": self.version, "rowCount": self.count, "fields": fields});
        if include_order {
            metadata["fieldOrder"] =
                json!(self.fields.iter().map(|(name, _)| name).collect::<Vec<_>>());
        }
        self.connection
            .execute(
                "INSERT INTO versions VALUES (?1,?2)",
                params![self.version, metadata.to_string()],
            )
            .unwrap();
        self.connection.execute_batch("COMMIT").unwrap();
    }

    fn export(&self) -> Result<ExportReceipt, Box<dyn std::error::Error>> {
        export_parquet(&self.database, &self.version, &self.root.join("out"))
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

// @wu-test type=integration | scope=runtime-core export-parquet | protects=Parquet preserves scalar types, explicit null, missing fields, original field order, and source bytes
#[test]
fn round_trip_types_and_missing_mask_without_modifying_source() {
    let mut fixture = Fixture::new(&[
        ("label", "string"),
        ("day", "date"),
        ("amount", "number"),
        ("integer", "number"),
        ("ok", "boolean"),
        ("__charts_missing", "string"),
    ]);
    fixture.insert(
        vec![
            "航线\0含\"".to_owned().into(),
            "2026-11-26".to_owned().into(),
            12.5.into(),
            i64::MAX.into(),
            1.into(),
            "business".to_owned().into(),
        ],
        None,
    );
    fixture.insert(
        vec![
            "".to_owned().into(),
            SqlValue::Null,
            SqlValue::Null,
            (-2).into(),
            0.into(),
            SqlValue::Null,
        ],
        Some("[\"day\"]"),
    );
    fixture.seal(false); // Historical metadata without fieldOrder must keep JSON insertion order.
    let before = fs::read(&fixture.database).unwrap();
    let receipt = fixture.export().unwrap();
    assert_eq!(receipt.row_count, 2);
    assert_eq!(receipt.missing_column, "__charts_missing_");
    assert_eq!(
        receipt.field_order,
        fixture
            .fields
            .iter()
            .map(|(name, _)| name.clone())
            .collect::<Vec<_>>()
    );
    assert_eq!(receipt.files.len(), 1);
    let bytes = fs::read(fixture.root.join("out").join(&receipt.files[0].path)).unwrap();
    assert_eq!(
        receipt.files[0].sha256,
        format!("{:x}", Sha256::digest(&bytes))
    );
    assert_eq!(receipt.files[0].bytes, bytes.len() as u64);
    let builder = ParquetRecordBatchReaderBuilder::try_new(
        fs::File::open(fixture.root.join("out").join(&receipt.files[0].path)).unwrap(),
    )
    .unwrap();
    let metadata = builder
        .metadata()
        .file_metadata()
        .key_value_metadata()
        .unwrap();
    assert!(metadata
        .iter()
        .any(|v| v.key == "charts.format" && v.value.as_deref() == Some("parquet-v1")));
    assert!(metadata.iter().any(
        |v| v.key == "charts.missingColumn" && v.value.as_deref() == Some("__charts_missing_")
    ));
    let batch = builder.build().unwrap().next().unwrap().unwrap();
    let texts = batch
        .column(0)
        .as_any()
        .downcast_ref::<StringArray>()
        .unwrap();
    assert_eq!(texts.value(0), "航线\0含\"");
    assert_eq!(texts.value(1), "");
    let dates = batch
        .column(1)
        .as_any()
        .downcast_ref::<StringArray>()
        .unwrap();
    assert_eq!(dates.value(0), "2026-11-26");
    assert!(dates.is_null(1));
    let amounts = batch
        .column(2)
        .as_any()
        .downcast_ref::<Float64Array>()
        .unwrap();
    assert_eq!(amounts.value(0), 12.5);
    assert!(amounts.is_null(1));
    let integers = batch
        .column(3)
        .as_any()
        .downcast_ref::<Int64Array>()
        .unwrap();
    assert_eq!(integers.value(0), i64::MAX);
    assert_eq!(integers.value(1), -2);
    let booleans = batch
        .column(4)
        .as_any()
        .downcast_ref::<BooleanArray>()
        .unwrap();
    assert!(booleans.value(0));
    assert!(!booleans.value(1));
    let masks = batch
        .column(6)
        .as_any()
        .downcast_ref::<BinaryArray>()
        .unwrap();
    assert_eq!(masks.value(0), [0]);
    assert_eq!(masks.value(1), [2]);
    assert_eq!(fs::read(&fixture.database).unwrap(), before);
}

// @wu-test type=integration | scope=runtime-core numeric export | protects=Mixed numeric columns cannot silently round an int64 when promoted to Float64
#[test]
fn rejects_lossy_mixed_numeric_columns() {
    let mut fixture = Fixture::new(&[("amount", "number")]);
    fixture.insert(vec![9_007_199_254_740_993_i64.into()], None);
    fixture.insert(vec![1.5.into()], None);
    fixture.seal(true);
    assert!(fixture
        .export()
        .unwrap_err()
        .to_string()
        .contains("cannot be represented exactly"));
    assert!(fs::read_dir(fixture.root.join("out"))
        .unwrap()
        .next()
        .is_none());
}

// @wu-test type=integration | scope=runtime-core bounded export | protects=Crossing a shard boundary neither drops rows nor reorders them and permits each shard's exact numeric schema
#[test]
fn shards_preserve_every_row_in_order() {
    let mut fixture = Fixture::new(&[("position", "number")]);
    for value in 0..8192 {
        fixture.insert(vec![SqlValue::Integer(value)], None);
    }
    fixture.insert(vec![8192.5.into()], None);
    fixture.seal(true);
    let receipt = fixture.export().unwrap();
    assert_eq!(receipt.row_count, 8193);
    assert_eq!(
        receipt
            .files
            .iter()
            .map(|f| f.row_count)
            .collect::<Vec<_>>(),
        [8192, 1]
    );
    let first = ParquetRecordBatchReaderBuilder::try_new(
        fs::File::open(fixture.root.join("out").join(&receipt.files[0].path)).unwrap(),
    )
    .unwrap()
    .with_batch_size(8192)
    .build()
    .unwrap()
    .next()
    .unwrap()
    .unwrap();
    let values = first
        .column(0)
        .as_any()
        .downcast_ref::<Int64Array>()
        .unwrap();
    assert_eq!(values.values().as_ref(), &(0_i64..8192).collect::<Vec<_>>());
    let last = ParquetRecordBatchReaderBuilder::try_new(
        fs::File::open(fixture.root.join("out").join(&receipt.files[1].path)).unwrap(),
    )
    .unwrap()
    .build()
    .unwrap()
    .next()
    .unwrap()
    .unwrap();
    assert_eq!(
        last.column(0)
            .as_any()
            .downcast_ref::<Float64Array>()
            .unwrap()
            .value(0),
        8192.5
    );
}

// @wu-test type=integration | scope=runtime-core single Parquet | protects=跨行组导出产生多个文件或改变数字和原始行序
#[test]
fn single_file_keeps_multiple_row_groups_and_shared_schema() {
    let mut fixture = Fixture::new(&[("position", "number"), ("id", "number")]);
    for index in 0..8193_i64 {
        let position = if index == 8192 {
            SqlValue::Real(8192.5)
        } else {
            SqlValue::Integer(index)
        };
        fixture.insert(
            vec![position, SqlValue::Integer(9007199254740993 + index)],
            None,
        );
    }
    fixture.seal(true);
    let output = fixture.root.join("single");
    let receipt = export_parquet_with_options(
        &fixture.database,
        &fixture.version,
        &output,
        &ExportOptions {
            single_file: true,
            ..Default::default()
        },
    )
    .unwrap();
    assert_eq!(receipt.files.len(), 1);
    assert_eq!(receipt.files[0].row_count, 8193);
    let path = output.join(&receipt.files[0].path);
    assert_eq!(inspect_parquet(&path).unwrap().row_count, 8193);
    let reader = ParquetRecordBatchReaderBuilder::try_new(fs::File::open(path).unwrap()).unwrap();
    assert_eq!(reader.metadata().num_row_groups(), 2);
    let mut batches = reader.with_batch_size(8192).build().unwrap();
    let first = batches.next().unwrap().unwrap();
    let last = batches.next().unwrap().unwrap();
    let first_position = first
        .column(0)
        .as_any()
        .downcast_ref::<Float64Array>()
        .unwrap();
    let first_id = first
        .column(1)
        .as_any()
        .downcast_ref::<Int64Array>()
        .unwrap();
    let last_position = last
        .column(0)
        .as_any()
        .downcast_ref::<Float64Array>()
        .unwrap();
    assert_eq!(first_position.value(8191), 8191.0);
    assert_eq!(first_id.value(0), 9007199254740993);
    assert_eq!(last_position.value(0), 8192.5);
}

// @wu-test type=integration | scope=runtime-core version validation | protects=Unknown or malformed versions cannot read other tables or produce a successful export
#[test]
fn rejects_unknown_versions_and_nonempty_destinations() {
    let fixture = Fixture::new(&[("id", "number")]);
    fixture.seal(true);
    let unknown = export_parquet(
        &fixture.database,
        &"b".repeat(64),
        &fixture.root.join("unknown"),
    )
    .unwrap_err();
    assert!(unknown.to_string().contains("Unknown data version"));
    assert!(!fixture.root.join("unknown").exists());
    assert!(export_parquet(
        &fixture.database,
        "x';DROP TABLE versions;--",
        &fixture.root.join("invalid")
    )
    .is_err());
    fs::create_dir(fixture.root.join("out")).unwrap();
    fs::write(fixture.root.join("out/keep"), "keep").unwrap();
    assert!(fixture
        .export()
        .unwrap_err()
        .to_string()
        .contains("empty directory"));
    assert_eq!(
        fs::read_to_string(fixture.root.join("out/keep")).unwrap(),
        "keep"
    );
}

// @wu-test type=integration | scope=runtime-core byte-limited batching | protects=Wide rows trigger the memory bound before the row-count bound without losing records
#[test]
fn wide_rows_split_before_the_row_limit() {
    let mut fixture = Fixture::new(&[("text", "string")]);
    for _ in 0..5 {
        fixture.insert(vec![SqlValue::Text("x".repeat(2 * 1024 * 1024))], None);
    }
    fixture.seal(true);
    let receipt = fixture.export().unwrap();
    assert_eq!(receipt.row_count, 5);
    assert_eq!(
        receipt
            .files
            .iter()
            .map(|file| file.row_count)
            .collect::<Vec<_>>(),
        [3, 2]
    );
}

// @wu-test type=integration | scope=runtime-core empty and bounded export | protects=Empty datasets retain metadata and an oversized row fails without emitting a success artifact
#[test]
fn empty_dataset_and_oversized_row() {
    let empty = Fixture::new(&[("text", "string")]);
    empty.seal(true);
    let receipt = empty.export().unwrap();
    assert_eq!(receipt.row_count, 0);
    assert!(receipt.files.is_empty());
    let mut large = Fixture::new(&[("text", "string")]);
    large.insert(vec![SqlValue::Text("x".repeat(16 * 1024 * 1024 + 1))], None);
    large.seal(true);
    assert!(large.export().unwrap_err().to_string().contains("16 MiB"));
    assert!(fs::read_dir(large.root.join("out"))
        .unwrap()
        .next()
        .is_none());
}

// @wu-test type=integration | scope=partitioned Parquet | protects=Partition pruning preserves nulls, missing values and original row order even with auxiliary-name collisions
#[test]
fn partitions_keep_original_ordinals_and_null_missing_masks() {
    let mut fixture = Fixture::new(&[
        ("月份", "date"),
        ("amount", "number"),
        ("__charts_ordinal", "string"),
    ]);
    for (month, value, missing) in [
        (Some("2026-02"), 10, false),
        (Some("2026-01"), 20, false),
        (None, 30, false),
        (None, 40, true),
        (Some("2026-02"), 50, false),
    ] {
        fixture.insert(
            vec![
                month
                    .map(|value| value.to_owned().into())
                    .unwrap_or(SqlValue::Null),
                value.into(),
                "business".to_owned().into(),
            ],
            missing.then_some("[\"月份\"]"),
        );
    }
    fixture.seal(true);
    fixture
        .connection
        .execute(
            &format!("UPDATE d_{} SET rowid=55 WHERE rowid=5", fixture.version),
            [],
        )
        .unwrap();
    let options = ExportOptions {
        partition_field: Some("月份".to_owned()),
        ..Default::default()
    };
    let receipt = export_parquet_with_options(
        &fixture.database,
        &fixture.version,
        &fixture.root.join("out"),
        &options,
    )
    .unwrap();
    assert_eq!(receipt.ordinal_column.as_deref(), Some("__charts_ordinal_"));
    assert!(receipt.options.is_none());
    let partitions = receipt.partition_index.as_ref().unwrap();
    assert_eq!(partitions.field, "月份");
    assert_eq!(
        partitions
            .entries
            .iter()
            .map(|entry| entry.value.as_deref())
            .collect::<Vec<_>>(),
        [None, Some("2026-01"), Some("2026-02")]
    );
    assert_eq!(
        partitions
            .entries
            .iter()
            .flat_map(|entry| &entry.files)
            .collect::<Vec<_>>(),
        receipt
            .files
            .iter()
            .map(|file| &file.path)
            .collect::<Vec<_>>()
    );
    let mut restored = Vec::new();
    for file in &receipt.files {
        let path = fixture.root.join("out").join(&file.path);
        let inspected = inspect_parquet(&path).unwrap();
        assert_eq!(inspected.field_order, receipt.field_order);
        assert_eq!(inspected.row_count as usize, file.row_count);
        for batch in ParquetRecordBatchReaderBuilder::try_new(fs::File::open(path).unwrap())
            .unwrap()
            .build()
            .unwrap()
        {
            let batch = batch.unwrap();
            let values = batch
                .column(1)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap();
            let masks = batch
                .column(3)
                .as_any()
                .downcast_ref::<BinaryArray>()
                .unwrap();
            let ordinals = batch
                .column(4)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap();
            for index in 0..batch.num_rows() {
                restored.push((
                    ordinals.value(index),
                    values.value(index),
                    masks.value(index)[0],
                ));
            }
        }
    }
    assert_eq!(
        restored.iter().map(|row| row.0).collect::<Vec<_>>(),
        [3, 4, 2, 1, 55]
    );
    restored.sort_by_key(|row| row.0);
    assert_eq!(
        restored,
        [(1, 10, 0), (2, 20, 0), (3, 30, 0), (4, 40, 1), (55, 50, 0)]
    );
    for field in ["amount", "unknown", "c0; DROP TABLE versions"] {
        let invalid = ExportOptions {
            partition_field: Some(field.to_owned()),
            ..Default::default()
        };
        assert!(export_parquet_with_options(
            &fixture.database,
            &fixture.version,
            &fixture.root.join("invalid"),
            &invalid
        )
        .is_err());
        assert!(!fixture.root.join("invalid").exists());
    }
}

// @wu-test type=integration | scope=Parquet option universe | protects=High-cardinality options cannot overflow one shard and null/missing or Boolean choices retain their existing meaning
#[test]
fn options_stream_distinct_values_with_independent_bounds() {
    let mut fixture = Fixture::new(&[("id", "number"), ("分区", "string"), ("active", "boolean")]);
    for index in 0..8193 {
        fixture.insert(
            vec![
                index.into(),
                "same".to_owned().into(),
                if index < 2 {
                    index.into()
                } else {
                    SqlValue::Null
                },
            ],
            (index >= 3).then_some("[\"active\"]"),
        );
    }
    fixture.seal(true);
    let options = ExportOptions {
        partition_field: Some("分区".to_owned()),
        include_options: true,
        ..Default::default()
    };
    let receipt = export_parquet_with_options(
        &fixture.database,
        &fixture.version,
        &fixture.root.join("out"),
        &options,
    )
    .unwrap();
    assert_eq!(receipt.row_count, 8193);
    assert_eq!(
        receipt
            .files
            .iter()
            .map(|file| file.row_count)
            .collect::<Vec<_>>(),
        [8192, 1]
    );
    assert_eq!(
        receipt.partition_index.as_ref().unwrap().entries[0]
            .files
            .len(),
        2
    );
    let choices = receipt.options.as_ref().unwrap();
    assert_eq!(
        choices["id"]
            .iter()
            .map(|file| file.row_count)
            .collect::<Vec<_>>(),
        [8192, 1]
    );
    assert_eq!(choices["分区"][0].row_count, 1);
    assert_eq!(choices["active"][0].row_count, 3);
    let names: std::collections::HashSet<_> = receipt
        .files
        .iter()
        .chain(choices.values().flatten())
        .map(|file| &file.path)
        .collect();
    assert_eq!(
        names.len(),
        receipt.files.len() + choices.values().map(Vec::len).sum::<usize>()
    );
    for (field, files) in choices {
        for file in files {
            let path = fixture.root.join("out").join(&file.path);
            assert!(file
                .path
                .starts_with(&format!("{}-options-", fixture.version)));
            assert_eq!(
                inspect_parquet(&path).unwrap().field_order,
                [field.to_owned()]
            );
            let builder =
                ParquetRecordBatchReaderBuilder::try_new(fs::File::open(path).unwrap()).unwrap();
            assert!(!builder
                .metadata()
                .file_metadata()
                .key_value_metadata()
                .unwrap()
                .iter()
                .any(|item| item.key == "charts.ordinalColumn"));
            for batch in builder.build().unwrap() {
                let batch = batch.unwrap();
                let masks = batch
                    .column(1)
                    .as_any()
                    .downcast_ref::<BinaryArray>()
                    .unwrap();
                assert!(masks.iter().all(|mask| mask == Some(&[0][..])));
                if field == "active" {
                    let values = batch
                        .column(0)
                        .as_any()
                        .downcast_ref::<BooleanArray>()
                        .unwrap();
                    assert_eq!(
                        values.iter().collect::<Vec<_>>(),
                        [Some(false), Some(true), None]
                    );
                }
            }
        }
    }
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_charts-design-core"))
        .arg("export-parquet")
        .arg("--database")
        .arg(&fixture.database)
        .args([
            "--version",
            &fixture.version,
            "--partition-field",
            "分区",
            "--include-options",
            "--output",
        ])
        .arg(fixture.root.join("cli"))
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let cli: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(cli["options"]["id"].as_array().unwrap().len(), 2);
    assert_eq!(cli["ordinalColumn"], "__charts_ordinal");
    assert_eq!(cli["partitionIndex"]["field"], "分区");
}

// @wu-test type=boundary | scope=Parquet read-back validation | protects=A valid footer cannot conceal corrupted data pages and foreign Parquet must not pass format validation
#[test]
fn inspection_decodes_data_pages_and_checks_format() {
    let mut fixture = Fixture::new(&[("value", "number")]);
    fixture.insert(vec![10.into()], None);
    fixture.insert(vec![20.into()], None);
    fixture.seal(true);
    let receipt = fixture.export().unwrap();
    let path = fixture.root.join("out").join(&receipt.files[0].path);
    let inspected = inspect_parquet(&path).unwrap();
    assert_eq!(inspected.row_count, 2);
    assert_eq!(inspected.field_order, ["value"]);
    let old_receipt = serde_json::to_value(&receipt).unwrap();
    assert!(old_receipt.get("ordinalColumn").is_none());
    assert!(old_receipt.get("partitionIndex").is_none());
    assert!(old_receipt.get("options").is_none());
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_charts-design-core"))
        .args(["inspect-parquet", "--input"])
        .arg(&path)
        .output()
        .unwrap();
    assert!(output.status.success());
    assert_eq!(
        serde_json::from_slice::<Value>(&output.stdout).unwrap(),
        json!({"format":"parquet-v1","rowCount":2,"fieldOrder":["value"]})
    );
    let builder = ParquetRecordBatchReaderBuilder::try_new(fs::File::open(&path).unwrap()).unwrap();
    let page_offset = builder.metadata().row_group(0).column(0).data_page_offset() as usize;
    let original = fs::read(&path).unwrap();
    let mut corrupted = original.clone();
    corrupted[page_offset..page_offset + 10].fill(0xff);
    let damaged = fixture.root.join("damaged.parquet");
    fs::write(&damaged, corrupted).unwrap();
    assert!(ParquetRecordBatchReaderBuilder::try_new(fs::File::open(&damaged).unwrap()).is_ok());
    assert!(inspect_parquet(&damaged).is_err());
    let mut foreign = original;
    let marker = foreign
        .windows(b"parquet-v1".len())
        .position(|bytes| bytes == b"parquet-v1")
        .unwrap();
    foreign[marker..marker + b"parquet-v1".len()].copy_from_slice(b"parquet-x1");
    fs::write(&damaged, foreign).unwrap();
    assert!(inspect_parquet(&damaged)
        .unwrap_err()
        .to_string()
        .contains("Unsupported Parquet format"));
}
