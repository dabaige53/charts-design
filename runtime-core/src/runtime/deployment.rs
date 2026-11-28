//! Atomic static exports with immutable native Parquet and public-UI ZIP caches.
use super::{
    assets,
    data::LocalData,
    error::{require, Error, Result},
    exports::{private_directory, private_file},
    serialization::{json_bytes, python_json},
    store::Store,
};
use flate2::{write::GzEncoder, Compression};
use fs2::FileExt;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
};
use uuid::Uuid;
fn digest(path: &Path) -> Result<String> {
    let mut input = File::open(path)?;
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 1024 * 1024];
    loop {
        let count = input.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        hash.update(&buffer[..count]);
    }
    Ok(format!("{:x}", hash.finalize()))
}
fn package_files(receipt: &Value) -> Vec<&Value> {
    let mut files = receipt["files"]
        .as_array()
        .into_iter()
        .flatten()
        .collect::<Vec<_>>();
    for options in receipt["options"]
        .as_object()
        .into_iter()
        .flatten()
        .map(|(_, v)| v)
    {
        files.extend(options.as_array().into_iter().flatten());
    }
    files
}
fn valid_receipt(
    directory: &Path,
    reference: &Value,
    partition: Option<&str>,
    options: bool,
    single: bool,
) -> Option<Value> {
    (|| -> Result<Value> {
        let receipt: Value = serde_json::from_slice(&fs::read(directory.join("receipt.json"))?)?;
        let order = reference.get("fieldOrder").cloned().unwrap_or_else(|| {
            json!(reference["fields"]
                .as_object()
                .unwrap()
                .keys()
                .collect::<Vec<_>>())
        });
        let version = super::service::string(reference, "version")?;
        require(
            receipt["format"] == "parquet-v1"
                && receipt["version"] == version
                && receipt["rowCount"] == reference["rowCount"]
                && receipt["fieldOrder"] == order,
            "Incomplete Parquet metadata",
            "PARQUET_EXPORT_FAILED",
        )?;
        let files = receipt["files"]
            .as_array()
            .ok_or_else(|| Error::new("PARQUET_EXPORT_FAILED", "Missing files"))?;
        require(
            !single || files.len() == 1,
            "Single-file Parquet required",
            "PARQUET_EXPORT_FAILED",
        )?;
        let mut total = 0u64;
        for (index, item) in files.iter().enumerate() {
            require(
                item["path"] == format!("{version}-{index}.parquet"),
                "Invalid Parquet path",
                "PARQUET_EXPORT_FAILED",
            )?;
            total = total
                .checked_add(
                    item["rowCount"]
                        .as_u64()
                        .ok_or_else(|| Error::new("PARQUET_EXPORT_FAILED", "Invalid row count"))?,
                )
                .ok_or_else(|| Error::new("PARQUET_EXPORT_FAILED", "Invalid row count"))?;
        }
        require(
            reference["rowCount"] == total,
            "Incomplete Parquet rows",
            "PARQUET_EXPORT_FAILED",
        )?;
        let empty = Map::new();
        let option_files = receipt["options"].as_object().unwrap_or(&empty);
        let expected = if options {
            reference["fields"]
                .as_object()
                .unwrap()
                .keys()
                .collect::<BTreeSet<_>>()
        } else {
            BTreeSet::new()
        };
        require(
            option_files.keys().collect::<BTreeSet<_>>() == expected,
            "Invalid option fields",
            "PARQUET_EXPORT_FAILED",
        )?;
        for (index, field) in order
            .as_array()
            .ok_or_else(|| Error::new("PARQUET_EXPORT_FAILED", "Invalid field order"))?
            .iter()
            .enumerate()
        {
            let key = field
                .as_str()
                .ok_or_else(|| Error::new("PARQUET_EXPORT_FAILED", "Invalid field name"))?;
            let mut total = 0u64;
            for (part, item) in option_files
                .get(key)
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .enumerate()
            {
                require(
                    item["path"] == format!("{version}-options-{index}-{part}.parquet"),
                    "Invalid option path",
                    "PARQUET_EXPORT_FAILED",
                )?;
                total += item["rowCount"]
                    .as_u64()
                    .ok_or_else(|| Error::new("PARQUET_EXPORT_FAILED", "Invalid option rows"))?;
            }
            require(
                total <= reference["rowCount"].as_u64().unwrap_or(0),
                "Invalid option count",
                "PARQUET_EXPORT_FAILED",
            )?;
        }
        let missing = receipt["missingColumn"]
            .as_str()
            .ok_or_else(|| Error::new("PARQUET_EXPORT_FAILED", "Missing presence column"))?;
        require(
            reference["fields"].get(missing).is_none(),
            "Invalid presence column",
            "PARQUET_EXPORT_FAILED",
        )?;
        if let Some(field) = partition {
            let ordinal = receipt["ordinalColumn"]
                .as_str()
                .ok_or_else(|| Error::new("PARQUET_EXPORT_FAILED", "Missing ordinal column"))?;
            require(
                ordinal != missing
                    && reference["fields"].get(ordinal).is_none()
                    && receipt["partitionIndex"]["field"] == field,
                "Invalid partition index",
                "PARQUET_EXPORT_FAILED",
            )?;
            let entries = receipt["partitionIndex"]["entries"]
                .as_array()
                .ok_or_else(|| Error::new("PARQUET_EXPORT_FAILED", "Missing partition entries"))?;
            let mut values = BTreeSet::new();
            let mut partitions = Vec::new();
            for entry in entries {
                require(
                    entry["value"].is_null() || entry["value"].is_string(),
                    "Invalid partition value",
                    "PARQUET_EXPORT_FAILED",
                )?;
                require(
                    values.insert(entry["value"].to_string()),
                    "Duplicate partition value",
                    "PARQUET_EXPORT_FAILED",
                )?;
                for path in entry["files"]
                    .as_array()
                    .ok_or_else(|| Error::new("PARQUET_EXPORT_FAILED", "Invalid partition files"))?
                {
                    partitions.push(path.as_str().unwrap_or("").to_owned());
                }
            }
            partitions.sort();
            let mut paths = files
                .iter()
                .map(|v| v["path"].as_str().unwrap_or("").to_owned())
                .collect::<Vec<_>>();
            paths.sort();
            require(
                partitions == paths,
                "Incomplete partition index",
                "PARQUET_EXPORT_FAILED",
            )?;
        } else {
            require(
                receipt["partitionIndex"].is_null() && receipt["ordinalColumn"].is_null(),
                "Unexpected partition metadata",
                "PARQUET_EXPORT_FAILED",
            )?;
        }
        for item in package_files(&receipt) {
            let bytes = item["bytes"]
                .as_u64()
                .ok_or_else(|| Error::new("PARQUET_EXPORT_FAILED", "Invalid file size"))?;
            let hash = item["sha256"].as_str().unwrap_or("");
            require(
                bytes > 0
                    && bytes <= 24 * 1024 * 1024
                    && hash.len() == 64
                    && hash
                        .bytes()
                        .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)),
                "Invalid Parquet checksum or size",
                "PARQUET_EXPORT_FAILED",
            )?;
            require(
                fs::metadata(directory.join(super::service::string(item, "path")?))?.len() == bytes,
                "Truncated Parquet file",
                "PARQUET_EXPORT_FAILED",
            )?;
        }
        Ok(receipt)
    })()
    .ok()
}

pub fn copy_parquet_package(
    target: &Path,
    data: &LocalData,
    reference: &Value,
    cache_root: &Path,
    partition: Option<&str>,
    options: bool,
    single: bool,
) -> Result<Value> {
    let version = super::service::string(reference, "version")?;
    require(
        version.len() == 64
            && version
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)),
        "Invalid data version",
        "INVALID_ARGUMENT",
    )?;
    require(
        partition.is_none_or(|p| {
            matches!(
                reference["fields"][p]["type"].as_str(),
                Some("string" | "date")
            )
        }),
        "Partition field must be a declared string or date",
        "INVALID_ARGUMENT",
    )?;
    private_directory(target)?;
    let cache = cache_root.join("parquet-v1");
    private_directory(&cache)?;
    let mut key = version.to_owned();
    if partition.is_some() || options {
        let layout = python_json(&json!([partition, options]), false, true)?;
        key.push_str(&format!(
            "-{}",
            &format!("{:x}", Sha256::digest(layout.as_bytes()))[..24]
        ));
    }
    if single {
        key.push_str("-single");
    }
    let directory = cache.join(&key);
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(cache.join(format!("{key}.lock")))?;
    lock.lock_exclusive()?;
    let mut receipt = valid_receipt(&directory, reference, partition, options, single);
    let mut reused = receipt.is_some();
    for _ in 0..2 {
        if receipt.is_none() {
            let (source, metadata) = data.sqlite_source(reference)?;
            require(
                metadata == *reference,
                "Immutable dataset metadata changed",
                "DATA_CONFLICT",
            )?;
            let staged = tempfile::Builder::new()
                .prefix("parquet-")
                .tempdir_in(&cache)?;
            let output = staged.path().join("data");
            let native = crate::export_parquet_with_options(
                &source,
                version,
                &output,
                &crate::ExportOptions {
                    partition_field: partition.map(String::from),
                    include_options: options,
                    single_file: single,
                },
            )
            .map_err(|e| Error::new("PARQUET_EXPORT_FAILED", e.to_string()))?;
            let native = serde_json::to_value(native)?;
            fs::write(output.join("receipt.json"), serde_json::to_vec(&native)?)?;
            let checked = valid_receipt(&output, reference, partition, options, single)
                .ok_or_else(|| Error::new("PARQUET_EXPORT_FAILED", "Incomplete native export"))?;
            if directory.exists() {
                fs::remove_dir_all(&directory)?;
            }
            fs::rename(output, &directory)?;
            receipt = Some(checked);
        }
        let mut complete = true;
        for item in package_files(receipt.as_ref().unwrap()) {
            let name = super::service::string(item, "path")?;
            let destination = target.join(name);
            fs::copy(directory.join(name), &destination)?;
            if digest(&destination)? != super::service::string(item, "sha256")? {
                fs::remove_file(destination)?;
                complete = false;
                break;
            }
        }
        if complete {
            let mut result = receipt.unwrap();
            result["cacheHit"] = json!(reused);
            return Ok(result);
        }
        receipt = None;
        reused = false;
    }
    Err(Error::new(
        "PARQUET_EXPORT_FAILED",
        "Native export checksum mismatch",
    ))
}
pub fn inspect_parquet(path: &Path) -> Result<Value> {
    serde_json::to_value(
        crate::inspect_parquet(path)
            .map_err(|e| Error::new("PARQUET_EXPORT_FAILED", e.to_string()))?,
    )
    .map_err(Into::into)
}

fn zip_error(e: zip::result::ZipError) -> Error {
    Error::new("EXPORT_FAILED", e.to_string())
}
fn write_zip_file(writer: &mut zip::ZipWriter<File>, path: &Path, name: &str) -> Result<()> {
    writer
        .start_file(
            name,
            zip::write::SimpleFileOptions::default()
                .compression_method(zip::CompressionMethod::Deflated),
        )
        .map_err(zip_error)?;
    let mut file = File::open(path)?;
    std::io::copy(&mut file, writer)?;
    Ok(())
}
fn prepare_archive(site: &Path, archive: &Path, cache_root: &Path) -> Result<()> {
    let signatures: Map<String, Value> = assets::UI_RESOURCES
        .into_iter()
        .map(|name| Ok((name.into(), json!(digest(&site.join(name))?))))
        .collect::<Result<_>>()?;
    let key = format!("{:x}", Sha256::digest(json_bytes(&signatures.into())?));
    private_directory(cache_root)?;
    let directory = cache_root.join(&key);
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(cache_root.join(format!("{key}.lock")))?;
    lock.lock_exclusive()?;
    if let Ok(expected) = fs::read_to_string(directory.join("sha256")) {
        if directory.join("ui.zip").is_file() {
            fs::copy(directory.join("ui.zip"), archive)?;
            if digest(archive)? == expected.trim() {
                return Ok(());
            }
        }
    }
    let temporary = tempfile::Builder::new()
        .prefix("ui-")
        .tempdir_in(cache_root)?;
    let staged = temporary.path().join("template");
    private_directory(&staged)?;
    let file = File::create(staged.join("ui.zip"))?;
    let mut writer = zip::ZipWriter::new(file);
    for name in assets::UI_RESOURCES {
        write_zip_file(&mut writer, &site.join(name), name)?;
    }
    writer.finish().map_err(zip_error)?;
    fs::write(staged.join("sha256"), digest(&staged.join("ui.zip"))?)?;
    if directory.exists() {
        fs::remove_dir_all(&directory)?;
    }
    fs::rename(staged, &directory)?;
    fs::copy(directory.join("ui.zip"), archive)?;
    Ok(())
}
fn recursive_files(root: &Path) -> Result<Vec<PathBuf>> {
    let mut result = Vec::new();
    for entry in fs::read_dir(root)? {
        let entry = entry?;
        if entry.file_type()?.is_dir() {
            result.extend(recursive_files(&entry.path())?);
        } else if entry.file_type()?.is_file() {
            result.push(entry.path());
        }
    }
    result.sort();
    Ok(result)
}
fn write_json_shards(
    site: &Path,
    key: &str,
    data: &LocalData,
    reference: Option<&Value>,
    rows: &[Value],
) -> Result<(Vec<String>, u64)> {
    let mut files = Vec::new();
    let mut batch = Vec::<Vec<u8>>::new();
    let (mut count, mut size) = (0u64, 2usize);
    fn flush(
        site: &Path,
        key: &str,
        files: &mut Vec<String>,
        batch: &mut Vec<Vec<u8>>,
    ) -> Result<()> {
        if batch.is_empty() {
            return Ok(());
        }
        let name = format!("data/{key}-{}.json.gz", files.len());
        let output = File::create(site.join(&name))?;
        let mut gz = GzEncoder::new(output, Compression::default());
        gz.write_all(b"[")?;
        for (index, row) in batch.iter().enumerate() {
            if index > 0 {
                gz.write_all(b",")?;
            }
            gz.write_all(row)?;
        }
        gz.write_all(b"]")?;
        gz.finish()?;
        files.push(name);
        batch.clear();
        Ok(())
    }
    let mut visit = |row: Value| -> Result<()> {
        let raw = json_bytes(&row)?;
        require(
            raw.len() + 2 <= 16 * 1024 * 1024,
            "A single export row exceeds the 16 MiB limit",
            "PAYLOAD_TOO_LARGE",
        )?;
        if !batch.is_empty() && (batch.len() == 5000 || size + 1 + raw.len() > 16 * 1024 * 1024) {
            flush(site, key, &mut files, &mut batch)?;
            size = 2;
        }
        size += raw.len() + usize::from(!batch.is_empty());
        batch.push(raw);
        count += 1;
        Ok(())
    };
    if let Some(reference) = reference {
        data.for_each_row(reference, &[], None, &[], "", &mut visit)?;
    } else {
        for row in rows {
            visit(row.clone())?;
        }
    }
    flush(site, key, &mut files, &mut batch)?;
    Ok((files, count))
}
fn static_options(data: &LocalData, manifest: &Value, refs: &Value) -> Result<Value> {
    let mut output = Map::new();
    for filter in manifest["filters"].as_array().into_iter().flatten() {
        if filter["op"] != "in" {
            continue;
        }
        let datasets: BTreeSet<String> = filter["componentIds"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(Value::as_str)
            .filter_map(|key| {
                manifest["components"][key]["datasetId"]
                    .as_str()
                    .map(String::from)
            })
            .collect();
        if !datasets.iter().all(|id| refs.get(id).is_some()) {
            continue;
        }
        let field = super::service::string(filter, "field")?;
        let sources: Vec<Value> = datasets.iter().map(|id| refs[id].clone()).collect();
        let kinds: BTreeSet<String> = sources
            .iter()
            .map(|s| s["fields"][field]["type"].to_string())
            .collect();
        if kinds.len() != 1 {
            continue;
        }
        let page = data.option_page(&sources, field, "", 0, 100)?;
        if page["hasMore"] == false && json_bytes(&page["values"])?.len() <= 16 * 1024 {
            output.insert(
                super::service::string(filter, "id")?.into(),
                page["values"].clone(),
            );
        }
    }
    Ok(output.into())
}

pub fn export_site(
    store: &Store,
    board: &str,
    output_root: Option<&Path>,
    document: Option<&Value>,
    requested: &str,
    single_parquet: bool,
) -> Result<Value> {
    assets::require_preview()?;
    super::model::check_identifier(board)?;
    require(
        ["auto", "parquet", "json"].contains(&requested),
        "dataFormat must be auto, parquet or json",
        "INVALID_ARGUMENT",
    )?;
    let build: Value = serde_json::from_slice(&fs::read(assets::dist().join("build.json"))?)?;
    let supported = build["staticDataFormats"]
        .as_array()
        .is_some_and(|v| v.iter().any(|v| v == "parquet-v1"));
    if requested == "parquet" {
        require(
            supported,
            "The UI bundle needs Parquet support; prepare matching UI resources.",
            "UI_UNAVAILABLE",
        )?;
    }
    let format = if requested == "parquet" || requested == "auto" && supported {
        "parquet"
    } else {
        "json"
    };
    let original = document.cloned().map_or_else(
        || {
            if store.project_root.is_some() {
                store.readable(board)
            } else {
                store.get(board, false)
            }
        },
        Ok,
    )?;
    let mut doc = store.compact(&original)?;
    require(
        !super::service::has_live(&doc),
        "实时 SQL 看板请通过运行服务查看",
        "LIVE_DATA_REQUIRES_RUNTIME",
    )?;
    let mut artifacts =
        super::statistics::statistical_artifacts(&store.statistical_document(&doc)?);
    if let Some(values) = artifacts.as_object_mut() {
        for value in values.values_mut() {
            if let Some(value) = value.as_object_mut() {
                value.remove("provenance");
            }
        }
    }
    doc["statisticalArtifacts"] = artifacts;
    let id = Uuid::new_v4().simple().to_string();
    let root = output_root
        .map(Path::to_path_buf)
        .unwrap_or_else(|| store.root.join("exports"));
    private_directory(&root)?;
    let directory = root.join(&id);
    let staged = tempfile::Builder::new()
        .prefix("export-")
        .tempdir_in(&root)?;
    let site = staged.path().join("site");
    private_directory(&site.join("data"))?;
    let used: BTreeSet<String> = doc["manifest"]["components"]
        .as_object()
        .into_iter()
        .flatten()
        .filter_map(|(_, c)| {
            c["datasetId"]
                .as_str()
                .or(c["binding"]["datasetId"].as_str())
                .map(String::from)
        })
        .collect();
    let refs = doc["snapshot"]["datasetRefs"].clone();
    let mut static_files = Map::new();
    let mut counts = Map::new();
    let mut encodings = Map::new();
    let mut write_dataset = |key: &str,
                             reference: Option<&Value>,
                             rows: &[Value],
                             fields: &Value|
     -> Result<()> {
        let (files, count) = if format == "parquet" {
            let imported;
            let reference = match reference {
                Some(v) => v,
                None => {
                    imported = store.data.import_rows(rows, fields)?;
                    &imported
                }
            };
            let receipt = copy_parquet_package(
                &site.join("data"),
                &store.data,
                reference,
                &store.runtime_root.join("parquet-cache"),
                None,
                false,
                single_parquet,
            )?;
            let files = receipt["files"].as_array().unwrap();
            encodings.insert(key.into(),json!({"format":"parquet-v1","cacheHit":receipt["cacheHit"],"bytes":files.iter().map(|f|f["bytes"].as_u64().unwrap_or(0)).sum::<u64>()}));
            (
                files
                    .iter()
                    .map(|f| format!("data/{}", f["path"].as_str().unwrap()))
                    .collect::<Vec<_>>(),
                receipt["rowCount"].as_u64().unwrap_or(0),
            )
        } else {
            write_json_shards(&site, key, &store.data, reference, rows)?
        };
        static_files.insert(key.into(), json!(files));
        counts.insert(key.into(), json!(count));
        Ok(())
    };
    for key in used {
        write_dataset(
            &key,
            refs.get(&key),
            doc["snapshot"]["datasets"][&key]
                .as_array()
                .map_or(&[], Vec::as_slice),
            &doc["manifest"]["datasets"][&key]["fields"],
        )?;
    }
    for (key, reference) in doc["snapshot"]["componentDataRefs"]
        .as_object()
        .cloned()
        .unwrap_or_default()
    {
        if doc["manifest"]["components"].get(&key).is_none() {
            continue;
        }
        let dataset = format!("component-{key}");
        write_dataset(&dataset, Some(&reference), &[], &reference["fields"])?;
        doc["manifest"]["components"][&key]["datasetId"] = json!(dataset);
        doc["manifest"]["datasets"][&dataset] = json!({"fields":reference["fields"]});
        if let Some(config) = doc["manifest"]["components"][&key]
            .get_mut("config")
            .and_then(Value::as_object_mut)
        {
            config.remove("rowsRef");
        }
    }
    doc["staticFiles"] = static_files.into();
    doc["staticFilterOptions"] = static_options(&store.data, &doc["manifest"], &refs)?;
    doc["snapshot"] = json!({"datasets":{}});
    for key in ["sources", "queries", "annotations"] {
        doc["manifest"].as_object_mut().unwrap().remove(key);
    }
    for key in [
        "browserLinks",
        "annotationAccess",
        "publicationApiBase",
        "publication",
        "annotationsOpen",
        "computed",
        "progressive",
        "loading",
    ] {
        doc.as_object_mut().unwrap().remove(key);
    }
    for (name, content) in assets::bundle_assets()? {
        fs::write(site.join(name), content)?;
    }
    fs::write(site.join("document.json"), json_bytes(&doc)?)?;
    fs::write(site.join("index.html"),format!("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Charts Design</title>{}<link rel=\"stylesheet\" href=\"app.css\"></head><body><div id=\"root\"></div><script>window.__chartsBoot={{mode:\"static\"}};</script><script src=\"app.js\"></script></body></html>",assets::favicon_link()))?;
    let manifest = json!({"dashboardId":board,"revision":doc["revision"],"uiBuildId":assets::ui_build_id(),"backendBuildId":assets::backend_build_id(),"dataFormat":format,"datasets":counts,"encodings":encodings});
    fs::write(site.join("export-manifest.json"), json_bytes(&manifest)?)?;
    fs::write(site.join("README.txt"),"将此目录放入普通静态 HTTP 服务。网页按组件加载 data/ 分片，在浏览器本地筛选，不连接 MCP。数据包含使用中的数据集全部记录。\n")?;
    let archive = staged.path().join(format!("{board}.zip"));
    prepare_archive(
        &site,
        &archive,
        &store.runtime_root.join("ui-archive-cache"),
    )?;
    let mut writer =
        zip::ZipWriter::new_append(OpenOptions::new().read(true).write(true).open(&archive)?)
            .map_err(zip_error)?;
    for path in recursive_files(&site)? {
        let name = path
            .strip_prefix(&site)
            .unwrap()
            .to_string_lossy()
            .replace('\\', "/");
        if !assets::UI_RESOURCES.contains(&name.as_str()) {
            write_zip_file(&mut writer, &path, &name)?;
        }
    }
    writer.finish().map_err(zip_error)?;
    private_file(&archive)?;
    fs::rename(staged.path(), &directory)?;
    let site = directory.join("site");
    let archive = directory.join(format!("{board}.zip"));
    Ok(
        json!({"export":{"id":id,"filename":format!("{board}.zip"),"path":archive.canonicalize()?,"directory":site.canonicalize()?,"format":"zip","mimeType":"application/zip","bytes":fs::metadata(&archive)?.len(),"scope":"static-site-with-used-datasets","manifest":manifest}}),
    )
}

#[cfg(test)]
#[path = "../../tests/unit/deployment.rs"]
mod tests;
