use std::{env, path::PathBuf, process::ExitCode};

use charts_design_core::{export_parquet_with_options, inspect_parquet, ExportOptions};

const USAGE: &str =
    "Usage: charts-design-core export-parquet --database PATH --version SHA256 --output DIRECTORY [--partition-field FIELD] [--include-options]\n       charts-design-core inspect-parquet --input FILE";

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args_os().skip(1);
    let command = args.next().ok_or(USAGE)?;
    if command == "--version" {
        println!("charts-design-core {}", env!("CARGO_PKG_VERSION"));
        return Ok(());
    }
    if command == "--help" || command == "-h" {
        println!("{USAGE}");
        return Ok(());
    }
    if command == "inspect-parquet" {
        if args.next().as_deref() != Some(std::ffi::OsStr::new("--input")) {
            return Err(USAGE.into());
        }
        let input = PathBuf::from(args.next().ok_or(USAGE)?);
        if args.next().is_some() {
            return Err(USAGE.into());
        }
        println!("{}", serde_json::to_string(&inspect_parquet(&input)?)?);
        return Ok(());
    }
    if command != "export-parquet" {
        return Err(USAGE.into());
    }
    let (mut database, mut version, mut output) = (None, None, None);
    let mut partition_field = None;
    let mut include_options = false;
    while let Some(flag) = args.next() {
        if flag == "--include-options" {
            if include_options {
                return Err("Duplicate argument: --include-options".into());
            }
            include_options = true;
            continue;
        }
        let slot = if flag == "--database" {
            &mut database
        } else if flag == "--version" {
            &mut version
        } else if flag == "--output" {
            &mut output
        } else if flag == "--partition-field" {
            &mut partition_field
        } else {
            return Err(format!("Unknown argument: {}. {USAGE}", flag.to_string_lossy()).into());
        };
        if slot.is_some() {
            return Err(format!("Duplicate argument: {}", flag.to_string_lossy()).into());
        }
        *slot = Some(args.next().ok_or(USAGE)?);
    }
    let database = PathBuf::from(database.ok_or(USAGE)?);
    let output = PathBuf::from(output.ok_or(USAGE)?);
    let version = version
        .ok_or(USAGE)?
        .into_string()
        .map_err(|_| "Invalid data version")?;
    let options = ExportOptions {
        partition_field: partition_field
            .map(|value| value.into_string())
            .transpose()
            .map_err(|_| "Invalid partition field")?,
        include_options,
    };
    let receipt = export_parquet_with_options(&database, &version, &output, &options)?;
    println!("{}", serde_json::to_string(&receipt)?);
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("charts-design-core: {error}");
            ExitCode::FAILURE
        }
    }
}
