//! Bounded, read-only exports from immutable Charts Design dataset versions.

use std::{
    collections::{BTreeMap, HashMap, HashSet},
    fs::{self, File, OpenOptions},
    io::{BufReader, Read},
    path::Path,
    sync::Arc,
    time::Duration,
};

use arrow_array::{
    Array, ArrayRef, BinaryArray, BooleanArray, Float64Array, Int64Array, RecordBatch, StringArray,
};
use arrow_schema::{DataType, Field, Schema};
use parquet::{
    arrow::{arrow_reader::ParquetRecordBatchReaderBuilder, ArrowWriter},
    basic::{Compression, Encoding},
    file::{metadata::KeyValue, properties::WriterProperties},
    schema::types::ColumnPath,
};
use rusqlite::{types::ValueRef, Connection, OpenFlags, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

const MAX_BATCH_ROWS: usize = 8192;
const MAX_BATCH_BYTES: usize = 8 * 1024 * 1024;
const MAX_ROW_BYTES: usize = 16 * 1024 * 1024;
const MAX_FILE_BYTES: u64 = 24 * 1024 * 1024;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ExportReceipt {
    pub format: &'static str,
    pub version: String,
    pub row_count: u64,
    pub field_order: Vec<String>,
    pub missing_column: String,
    pub files: Vec<ExportFile>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ordinal_column: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub partition_index: Option<PartitionIndex>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub options: Option<BTreeMap<String, Vec<ExportFile>>>,
}

#[derive(Debug, Default)]
pub struct ExportOptions {
    pub partition_field: Option<String>,
    pub include_options: bool,
    pub single_file: bool,
}

#[derive(Debug, Serialize)]
pub struct PartitionIndex {
    pub field: String,
    pub entries: Vec<PartitionEntry>,
}

#[derive(Debug, Serialize)]
pub struct PartitionEntry {
    pub value: Option<String>,
    pub files: Vec<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InspectionReceipt {
    pub format: &'static str,
    pub row_count: u64,
    pub field_order: Vec<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ExportFile {
    pub path: String,
    pub row_count: usize,
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct DatasetMetadata {
    version: String,
    row_count: u64,
    fields: Map<String, Value>,
    field_order: Option<Vec<String>>,
}

#[derive(Clone, Copy)]
enum Kind {
    Text,
    Number,
    Boolean,
}

enum Cell {
    Null,
    Text(String),
    Integer(i64),
    Real(f64),
    Boolean(bool),
}

struct ExportRow {
    values: Vec<Cell>,
    missing: Vec<u8>,
    ordinal: i64,
}

struct Columns<'a> {
    fields: &'a [String],
    kinds: &'a [Kind],
    missing: &'a str,
    ordinal: Option<&'a str>,
}

/// Export one immutable version. The caller owns the empty output directory and
/// discards it after an error; no manifest or success receipt is written on failure.
pub fn export_parquet(database: &Path, version: &str, output: &Path) -> Result<ExportReceipt> {
    export_parquet_with_options(database, version, output, &ExportOptions::default())
}

pub fn export_parquet_with_options(
    database: &Path,
    version: &str,
    output: &Path,
    options: &ExportOptions,
) -> Result<ExportReceipt> {
    if options.single_file && (options.partition_field.is_some() || options.include_options) {
        return Err("Single-file export cannot include separate partitions or option files".into());
    }
    if version.len() != 64
        || !version
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err("Invalid data version: expected 64 lowercase hexadecimal characters".into());
    }
    let mut db = Connection::open_with_flags(
        database,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )?;
    db.busy_timeout(Duration::from_secs(30))?;
    // GROUP BY/ORDER BY can spill high-cardinality options to temporary files
    // instead of collecting every distinct value in application memory.
    db.pragma_update(None, "temp_store", "FILE")?;
    // Metadata and rows share one read snapshot, including when a local WAL writer is active.
    let transaction = db.transaction()?;
    let raw: String = transaction
        .query_row(
            "SELECT metadata FROM versions WHERE version = ?1",
            [version],
            |row| row.get(0),
        )
        .optional()?
        .ok_or("Unknown data version")?;
    let metadata: DatasetMetadata = serde_json::from_str(&raw)?;
    if metadata.version != version {
        return Err("Dataset metadata does not match the requested version".into());
    }
    let fields = metadata
        .field_order
        .unwrap_or_else(|| metadata.fields.keys().cloned().collect());
    let unique: HashSet<&str> = fields.iter().map(String::as_str).collect();
    if fields.is_empty()
        || unique.len() != fields.len()
        || fields.len() != metadata.fields.len()
        || fields
            .iter()
            .any(|name| !metadata.fields.contains_key(name))
    {
        return Err("Invalid dataset field order".into());
    }
    let kinds: Vec<Kind> = fields
        .iter()
        .map(
            |name| match metadata.fields[name].get("type").and_then(Value::as_str) {
                Some("string" | "date") => Ok(Kind::Text),
                Some("number") => Ok(Kind::Number),
                Some("boolean") => Ok(Kind::Boolean),
                _ => Err(format!("Unsupported field type for {name}").into()),
            },
        )
        .collect::<Result<_>>()?;
    let positions: HashMap<&str, usize> = fields
        .iter()
        .enumerate()
        .map(|(i, name)| (name.as_str(), i))
        .collect();
    let mut missing_column = "__charts_missing".to_string();
    while unique.contains(missing_column.as_str()) {
        missing_column.push('_');
    }
    let partition = options
        .partition_field
        .as_ref()
        .map(|field| -> Result<usize> {
            let index = *positions
                .get(field.as_str())
                .ok_or("Unknown partition field")?;
            if !matches!(kinds[index], Kind::Text) {
                return Err("Partition field must be declared as string or date".into());
            }
            Ok(index)
        })
        .transpose()?;
    let ordinal_column = partition.map(|_| {
        let mut name = "__charts_ordinal".to_string();
        while unique.contains(name.as_str()) || name == missing_column {
            name.push('_');
        }
        name
    });
    let schema = Columns {
        fields: &fields,
        kinds: &kinds,
        missing: &missing_column,
        ordinal: ordinal_column.as_deref(),
    };
    let mut partition_index = options
        .partition_field
        .as_ref()
        .map(|field| PartitionIndex {
            field: field.clone(),
            entries: Vec::new(),
        });
    if output.exists() {
        if !output.is_dir() || fs::read_dir(output)?.next().is_some() {
            return Err("Output must be a new or empty directory".into());
        }
    } else {
        fs::create_dir(output)?;
    }
    let selected = (0..fields.len())
        .map(|i| format!("c{i}"))
        .collect::<Vec<_>>()
        .join(",");
    let order = partition
        .map(|index| format!("c{index},"))
        .unwrap_or_default();
    let table = format!("d_{version}");
    let numeric_schema = options
        .single_file
        .then(|| floating_columns(&transaction, &table, &kinds))
        .transpose()?;
    let mut statement = transaction.prepare(&format!(
        "SELECT {selected}, _missing, rowid FROM {table} ORDER BY {order}rowid"
    ))?;
    let mut source = statement.query([])?;
    let mut batch = Vec::new();
    let mut batch_bytes = 0;
    let mut count = 0;
    let mut files = Vec::new();
    let mut single_writer = None;
    let single_name = format!("{version}-0.parquet");
    let single_path = output.join(&single_name);
    let mut flush = |batch: &mut Vec<ExportRow>,
                     files: &mut Vec<ExportFile>,
                     partition_index: &mut Option<PartitionIndex>|
     -> Result<()> {
        if let Some(floating) = &numeric_schema {
            let records = record_batch(&schema, batch, Some(floating))?;
            if single_writer.is_none() {
                single_writer = Some(parquet_writer(&single_path, &schema, records.schema())?);
            }
            let writer = single_writer.as_mut().unwrap();
            writer.write(&records)?;
            writer.flush()?;
            if writer.bytes_written() as u64 > MAX_FILE_BYTES {
                return Err("The Parquet file exceeds the 24 MiB static hosting limit".into());
            }
            batch.clear();
            Ok(())
        } else {
            flush_main(output, version, &schema, batch, files, partition_index)
        }
    };
    while let Some(row) = source.next()? {
        let (value, bytes) = read_row(row, &schema, &positions)?;
        let partition_value = partition.map(|index| match &value.values[index] {
            Cell::Null => None,
            Cell::Text(text) => Some(text.clone()),
            _ => unreachable!("Partition values have already been validated"),
        });
        let partition_changed = partition_index.as_ref().is_some_and(|index| {
            index
                .entries
                .last()
                .is_none_or(|entry| Some(&entry.value) != partition_value.as_ref())
        });
        if !batch.is_empty()
            && (partition_changed
                || batch.len() >= MAX_BATCH_ROWS
                || batch_bytes + bytes > MAX_BATCH_BYTES)
        {
            flush(&mut batch, &mut files, &mut partition_index)?;
            batch_bytes = 0;
        }
        if partition_changed {
            partition_index
                .as_mut()
                .unwrap()
                .entries
                .push(PartitionEntry {
                    value: partition_value.unwrap(),
                    files: Vec::new(),
                });
        }
        batch.push(value);
        batch_bytes += bytes;
        count += 1;
    }
    flush(&mut batch, &mut files, &mut partition_index)?;
    if count != metadata.row_count {
        return Err(format!(
            "Dataset row count mismatch: expected {}, read {count}",
            metadata.row_count
        )
        .into());
    }
    if let Some(writer) = single_writer {
        writer.close()?;
        files.push(file_receipt(
            &single_path,
            single_name,
            usize::try_from(count)?,
        )?);
    }
    let option_files = options
        .include_options
        .then(|| export_options(&transaction, version, output, &schema))
        .transpose()?;
    Ok(ExportReceipt {
        format: "parquet-v1",
        version: version.to_owned(),
        row_count: count,
        field_order: fields,
        missing_column,
        files,
        ordinal_column,
        partition_index,
        options: option_files,
    })
}

fn floating_columns(db: &Connection, table: &str, kinds: &[Kind]) -> Result<Vec<bool>> {
    let numeric: Vec<_> = kinds
        .iter()
        .enumerate()
        .filter_map(|(index, kind)| matches!(kind, Kind::Number).then_some(index))
        .collect();
    let mut result = vec![false; kinds.len()];
    if !numeric.is_empty() {
        // All row groups in a Parquet file must use the same physical schema.
        let selections = numeric
            .iter()
            .map(|index| format!("MAX(typeof(c{index})='real')"))
            .collect::<Vec<_>>()
            .join(",");
        db.query_row(&format!("SELECT {selections} FROM {table}"), [], |row| {
            for (offset, index) in numeric.into_iter().enumerate() {
                result[index] = row.get::<_, Option<bool>>(offset)?.unwrap_or(false);
            }
            Ok(())
        })?;
    }
    Ok(result)
}

fn flush_main(
    output: &Path,
    prefix: &str,
    schema: &Columns<'_>,
    batch: &mut Vec<ExportRow>,
    files: &mut Vec<ExportFile>,
    partition_index: &mut Option<PartitionIndex>,
) -> Result<()> {
    if !batch.is_empty() {
        let file = write_batch(output, prefix, files.len(), schema, batch)?;
        if let Some(index) = partition_index {
            index
                .entries
                .last_mut()
                .unwrap()
                .files
                .push(file.path.clone());
        }
        files.push(file);
        batch.clear();
    }
    Ok(())
}

fn export_options(
    db: &Connection,
    version: &str,
    output: &Path,
    source_schema: &Columns<'_>,
) -> Result<BTreeMap<String, Vec<ExportFile>>> {
    let mut options = BTreeMap::new();
    for (index, field) in source_schema.fields.iter().enumerate() {
        let schema = Columns {
            fields: std::slice::from_ref(field),
            kinds: &source_schema.kinds[index..=index],
            missing: source_schema.missing,
            ordinal: None,
        };
        let positions = HashMap::from([(field.as_str(), 0)]);
        // Missing values are stored as SQL NULL, so this intentionally collapses
        // them with explicit null for the option universe, while rows keep masks.
        let mut statement = db.prepare(&format!(
            "SELECT c{index}, NULL FROM d_{version} GROUP BY c{index} ORDER BY MIN(rowid)"
        ))?;
        let mut rows = statement.query([])?;
        let mut batch = Vec::new();
        let mut bytes = 0;
        let mut files = Vec::new();
        let prefix = format!("{version}-options-{index}");
        while let Some(row) = rows.next()? {
            let (value, size) = read_row(row, &schema, &positions)?;
            if !batch.is_empty()
                && (batch.len() >= MAX_BATCH_ROWS || bytes + size > MAX_BATCH_BYTES)
            {
                files.push(write_batch(output, &prefix, files.len(), &schema, &batch)?);
                batch.clear();
                bytes = 0;
            }
            batch.push(value);
            bytes += size;
        }
        if !batch.is_empty() {
            files.push(write_batch(output, &prefix, files.len(), &schema, &batch)?);
        }
        options.insert(field.clone(), files);
    }
    Ok(options)
}

fn read_row(
    row: &rusqlite::Row<'_>,
    schema: &Columns<'_>,
    positions: &HashMap<&str, usize>,
) -> Result<(ExportRow, usize)> {
    let fields = schema.fields;
    // Include cell/vector overhead in the estimate, not only UTF-8 payload bytes.
    let mut bytes = fields
        .len()
        .checked_mul(std::mem::size_of::<Cell>())
        .ok_or("Too many fields")?;
    bytes += fields.len().div_ceil(8) + std::mem::size_of::<ExportRow>();
    for index in 0..fields.len() {
        if let ValueRef::Text(value) | ValueRef::Blob(value) = row.get_ref(index)? {
            bytes = bytes
                .checked_add(value.len())
                .ok_or("Row exceeds export size limit")?;
        }
    }
    if bytes > MAX_ROW_BYTES {
        return Err("A single export row exceeds the 16 MiB limit".into());
    }
    let mut values = Vec::with_capacity(fields.len());
    for (index, kind) in schema.kinds.iter().enumerate() {
        let cell = match (kind, row.get_ref(index)?) {
            (_, ValueRef::Null) => Cell::Null,
            (Kind::Text, ValueRef::Text(value)) => {
                Cell::Text(std::str::from_utf8(value)?.to_owned())
            }
            (Kind::Number, ValueRef::Integer(value)) => Cell::Integer(value),
            (Kind::Number, ValueRef::Real(value)) if value.is_finite() => Cell::Real(value),
            (Kind::Boolean, ValueRef::Integer(value)) if value == 0 || value == 1 => {
                Cell::Boolean(value == 1)
            }
            _ => return Err(format!("Invalid stored value for field {}", fields[index]).into()),
        };
        values.push(cell);
    }
    let mut missing = vec![0; fields.len().div_ceil(8)];
    let missing_raw: Option<&str> = row.get_ref(fields.len())?.as_str_or_null()?;
    if let Some(raw) = missing_raw {
        if raw.len() > MAX_ROW_BYTES {
            return Err("Missing-field mask exceeds the 16 MiB limit".into());
        }
        let omitted: Vec<&str> = serde_json::from_str(raw)?;
        for field in omitted {
            let index = *positions
                .get(field)
                .ok_or("Missing-field mask refers to an undeclared field")?;
            if !matches!(values[index], Cell::Null) {
                return Err(format!("Missing field {field} contains a stored value").into());
            }
            missing[index / 8] |= 1 << (index % 8);
        }
    }
    let ordinal = if schema.ordinal.is_some() {
        row.get(fields.len() + 1)?
    } else {
        0
    };
    Ok((
        ExportRow {
            values,
            missing,
            ordinal,
        },
        bytes,
    ))
}

fn write_batch(
    output: &Path,
    prefix: &str,
    index: usize,
    columns: &Columns<'_>,
    rows: &[ExportRow],
) -> Result<ExportFile> {
    let batch = record_batch(columns, rows, None)?;
    let name = format!("{prefix}-{index}.parquet");
    let path = output.join(&name);
    let mut writer = parquet_writer(&path, columns, batch.schema())?;
    writer.write(&batch)?;
    writer.close()?;
    file_receipt(&path, name, rows.len())
}

fn record_batch(
    columns: &Columns<'_>,
    rows: &[ExportRow],
    floating: Option<&[bool]>,
) -> Result<RecordBatch> {
    let fields = columns.fields;
    let mut arrays: Vec<ArrayRef> = Vec::with_capacity(fields.len() + 1);
    let mut schema = Vec::with_capacity(fields.len() + 1);
    for (index, kind) in columns.kinds.iter().enumerate() {
        let (data_type, array): (DataType, ArrayRef) = match kind {
            Kind::Text => (
                DataType::Utf8,
                Arc::new(StringArray::from_iter(rows.iter().map(
                    |row| match &row.values[index] {
                        Cell::Text(text) => Some(text.as_str()),
                        _ => None,
                    },
                ))),
            ),
            Kind::Boolean => (
                DataType::Boolean,
                Arc::new(BooleanArray::from_iter(rows.iter().map(
                    |row| match row.values[index] {
                        Cell::Boolean(value) => Some(value),
                        _ => None,
                    },
                ))),
            ),
            Kind::Number
                if floating.map_or_else(
                    || {
                        rows.iter()
                            .any(|row| matches!(row.values[index], Cell::Real(_)))
                    },
                    |fields| fields[index],
                ) =>
            {
                let values = rows.iter().map(|row| match row.values[index] {
                    Cell::Null => Ok(None),
                    Cell::Real(value) => Ok(Some(value)),
                    Cell::Integer(value) if (value as f64) as i128 == i128::from(value) => Ok(Some(value as f64)),
                    Cell::Integer(_) => Err(format!("Field {} mixes floating-point values with an integer that cannot be represented exactly as Float64; use a string field for exact identifiers", fields[index]).into()),
                    _ => unreachable!("Stored scalar types are validated before batching"),
                }).collect::<Result<Vec<Option<f64>>>>()?;
                (DataType::Float64, Arc::new(Float64Array::from(values)))
            }
            Kind::Number => (
                DataType::Int64,
                Arc::new(Int64Array::from_iter(rows.iter().map(
                    |row| match row.values[index] {
                        Cell::Integer(value) => Some(value),
                        _ => None,
                    },
                ))),
            ),
        };
        schema.push(Field::new(&fields[index], data_type, true));
        arrays.push(array);
    }
    schema.push(Field::new(columns.missing, DataType::Binary, false));
    arrays.push(Arc::new(BinaryArray::from_iter_values(
        rows.iter().map(|row| row.missing.as_slice()),
    )));
    if let Some(name) = columns.ordinal {
        schema.push(Field::new(name, DataType::Int64, false));
        arrays.push(Arc::new(Int64Array::from_iter_values(
            rows.iter().map(|row| row.ordinal),
        )));
    }
    Ok(RecordBatch::try_new(Arc::new(Schema::new(schema)), arrays)?)
}

fn parquet_writer(
    path: &Path,
    columns: &Columns<'_>,
    schema: Arc<Schema>,
) -> Result<ArrowWriter<File>> {
    let mut metadata = vec![
        KeyValue::new("charts.format".to_owned(), "parquet-v1".to_owned()),
        KeyValue::new(
            "charts.fieldOrder".to_owned(),
            serde_json::to_string(columns.fields)?,
        ),
        KeyValue::new(
            "charts.missingColumn".to_owned(),
            columns.missing.to_owned(),
        ),
    ];
    if let Some(name) = columns.ordinal {
        metadata.push(KeyValue::new(
            "charts.ordinalColumn".to_owned(),
            name.to_owned(),
        ));
    }
    let mut properties = WriterProperties::builder()
        .set_compression(Compression::SNAPPY)
        .set_created_by(format!("charts-design-core {}", env!("CARGO_PKG_VERSION")))
        .set_max_row_group_row_count(Some(MAX_BATCH_ROWS))
        .set_key_value_metadata(Some(metadata));
    // Numeric dictionaries duplicate high-cardinality values and row indices.
    // Delta/byte-stream encodings let SNAPPY compress those columns directly.
    for field in schema.fields() {
        let encoding = match field.data_type() {
            DataType::Int64 => Encoding::DELTA_BINARY_PACKED,
            DataType::Float64 => Encoding::BYTE_STREAM_SPLIT,
            _ => continue,
        };
        let path = ColumnPath::new(vec![field.name().clone()]);
        properties = properties
            .set_column_dictionary_enabled(path.clone(), false)
            .set_column_encoding(path, encoding);
    }
    let props = properties.build();
    let file = OpenOptions::new().write(true).create_new(true).open(path)?;
    Ok(ArrowWriter::try_new(file, schema, Some(props))?)
}

fn file_receipt(path: &Path, name: String, count: usize) -> Result<ExportFile> {
    let bytes = path.metadata()?.len();
    if bytes > MAX_FILE_BYTES {
        fs::remove_file(path)?;
        return Err("A Parquet shard exceeds the 24 MiB static hosting limit; reduce the number or width of fields".into());
    }
    let mut file = BufReader::new(File::open(path)?);
    let mut hash = Sha256::new();
    let mut buffer = [0; 64 * 1024];
    loop {
        let read = file.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        hash.update(&buffer[..read]);
    }
    Ok(ExportFile {
        path: name,
        row_count: count,
        bytes,
        sha256: format!("{:x}", hash.finalize()),
    })
}

/// Read every data page and validate the Charts scalar/missing-value format.
/// Hash verification remains the caller's responsibility: decoding alone cannot
/// detect corruption that happens to produce another valid scalar value.
pub fn inspect_parquet(input: &Path) -> Result<InspectionReceipt> {
    let file = File::open(input)?;
    if file.metadata()?.len() > MAX_FILE_BYTES {
        return Err("A Parquet shard exceeds the 24 MiB static hosting limit".into());
    }
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)?;
    let mut metadata = HashMap::new();
    for item in builder
        .metadata()
        .file_metadata()
        .key_value_metadata()
        .into_iter()
        .flatten()
    {
        if item.key.starts_with("charts.") {
            let value = item
                .value
                .as_deref()
                .ok_or("Missing Charts metadata value")?;
            if metadata.insert(item.key.as_str(), value).is_some() {
                return Err("Duplicate Charts metadata key".into());
            }
        }
    }
    if metadata.get("charts.format") != Some(&"parquet-v1") {
        return Err("Unsupported Parquet format: expected charts.format=parquet-v1".into());
    }
    let field_order: Vec<String> = serde_json::from_str(
        metadata
            .get("charts.fieldOrder")
            .ok_or("Missing field order")?,
    )?;
    let missing = *metadata
        .get("charts.missingColumn")
        .ok_or("Missing mask column metadata")?;
    let ordinal = metadata.get("charts.ordinalColumn").copied();
    let names: HashSet<&str> = field_order.iter().map(String::as_str).collect();
    if field_order.is_empty()
        || names.len() != field_order.len()
        || names.contains(missing)
        || ordinal.is_some_and(|name| names.contains(name) || name == missing)
    {
        return Err("Invalid Charts field order or auxiliary column names".into());
    }
    let schema = builder.schema();
    if schema.fields().len() != field_order.len() + 1 + usize::from(ordinal.is_some()) {
        return Err("Parquet columns do not match the Charts field order".into());
    }
    for (index, name) in field_order.iter().enumerate() {
        let field = schema.field(index);
        if field.name() != name
            || !matches!(
                field.data_type(),
                DataType::Utf8 | DataType::Boolean | DataType::Int64 | DataType::Float64
            )
        {
            return Err("Invalid Charts business column".into());
        }
    }
    let mask_index = field_order.len();
    let mask_field = schema.field(mask_index);
    if mask_field.name() != missing
        || mask_field.data_type() != &DataType::Binary
        || mask_field.is_nullable()
    {
        return Err("Invalid Charts missing-mask column".into());
    }
    if let Some(name) = ordinal {
        let field = schema.field(mask_index + 1);
        if field.name() != name || field.data_type() != &DataType::Int64 || field.is_nullable() {
            return Err("Invalid Charts ordinal column".into());
        }
    }
    let has_ordinal = ordinal.is_some();
    let expected = builder.metadata().file_metadata().num_rows();
    if expected < 0
        || builder
            .metadata()
            .row_groups()
            .iter()
            .any(|group| !(0..=MAX_BATCH_ROWS as i64).contains(&group.num_rows()))
    {
        return Err("Parquet row group exceeds the Charts format limit".into());
    }
    let mut row_count = 0;
    for result in builder.with_batch_size(MAX_BATCH_ROWS).build()? {
        let batch = result?;
        let masks = batch
            .column(mask_index)
            .as_any()
            .downcast_ref::<BinaryArray>()
            .ok_or("Invalid decoded missing-mask column")?;
        if masks.null_count() != 0
            || (has_ordinal && batch.column(mask_index + 1).null_count() != 0)
        {
            return Err("Null Charts auxiliary value".into());
        }
        for row in 0..batch.num_rows() {
            let mask = masks.value(row);
            if mask.len() != field_order.len().div_ceil(8)
                || (!field_order.len().is_multiple_of(8)
                    && mask[mask.len() - 1] >> (field_order.len() % 8) != 0)
            {
                return Err("Invalid missing-mask width or padding".into());
            }
            for index in 0..field_order.len() {
                if mask[index / 8] & (1 << (index % 8)) != 0 && !batch.column(index).is_null(row) {
                    return Err("A missing business field contains a value".into());
                }
            }
        }
        for array in batch.columns().iter().take(field_order.len()) {
            if let Some(values) = array.as_any().downcast_ref::<Float64Array>() {
                if values.iter().flatten().any(|value| !value.is_finite()) {
                    return Err("Non-finite Charts numeric value".into());
                }
            }
        }
        row_count += batch.num_rows() as u64;
    }
    if row_count != expected as u64 {
        return Err("Decoded Parquet row count differs from its metadata".into());
    }
    Ok(InspectionReceipt {
        format: "parquet-v1",
        row_count,
        field_order,
    })
}
pub mod runtime;
