//! Native command-line entry points. JSON files remain optional author inputs.
use super::{
    assets, contract, discovery,
    error::{require, Error, Result},
    model,
    service::{integer, string, Service},
    store,
};
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
use std::{
    collections::BTreeSet,
    fs,
    io::{self, Read},
    path::{Path, PathBuf},
};
const COMMANDS: &[&str] = &[
    "init",
    "migrate-project",
    "list",
    "get",
    "validate",
    "history",
    "patch",
    "restore",
    "serve",
    "export",
    "import",
    "import-workspace",
    "call",
    "catalog",
    "contract",
    "mcp",
    "server",
    "share",
    "transfer",
    "remote",
];
pub fn help() {
    println!(
        r#"Charts Design native runtime

Usage: charts-design-core [--project-root PATH] [--runtime-root PATH] [--sources FILE] COMMAND

Authoring:
  init ID [--title TITLE] [--mode dashboard|report] [--demo]
  list | get ID | validate ID | history ID
  validate --file DOCUMENT.json
  patch ID --expected REVISION --file OPERATIONS.json
  restore ID --expected REVISION --revision SAVED_REVISION
  call TOOL [--json-file FILE|-]
  import ID --file DOCUMENT.json
  import-workspace ID --path DIRECTORY
  migrate-project --source-root PATH --board ID [--board ID] [--apply]
  export ID --output PATH [--format html|json|csv] [--dataset ID|--component ID]
  catalog | contract

Services and transfer:
  serve [--port 8765] [--dashboard ID] [--view] [--idle-timeout 60]
  mcp [--idle-timeout 60]
  server [--workspace PATH] [--host 127.0.0.1] [--port 8000] [--token TOKEN]
  share PROJECT DASHBOARD [--access view|edit] [--hours HOURS]
  remote read --project NAME --dashboard ID --output FILE
  remote upload --project NAME --root PATH --ref FILE --state FILE --output FILE
  transfer --manifest FILE --project NAME --state FILE [--check-only]

Operator commands:
  cleanup                                      Process configured cloud cleanup jobs
  cleanup-server                               Serve scheduled cleanup events using CHARTS_PORT
  healthcheck [--wait-seconds 60]               Check the local CHARTS_PORT endpoint
  migrate-neon                                 Apply migrations using DATABASE_URL and CHARTS_NEON_RUNTIME_ROLE
  migrate-cos --project NAME --workspace PATH [--partition-field FIELD] [--apply]
  export-parquet --database PATH --version SHA256 --output DIRECTORY [--single-file | --partition-field FIELD --include-options]
  inspect-parquet --input FILE

Use --help with any command. --idle-timeout 0 keeps a local service running.
Project paths and source aliases are operator inputs. MCP tools do not receive arbitrary SQL file paths."#
    );
}
pub fn parse(args: &[String]) -> Result<Value> {
    let mut options = json!({"root":".charts-runtime"});
    let mut positionals = Vec::new();
    let mut command = None;
    let mut iterator = args.iter();
    while let Some(argument) = iterator.next() {
        if argument == "--" {
            positionals.extend(iterator.cloned());
            break;
        }
        if let Some(option) = argument.strip_prefix("--") {
            let (name, inline) = option
                .split_once('=')
                .map_or((option, None), |(a, b)| (a, Some(b)));
            let key = name.replace('-', "_");
            if [
                "demo",
                "apply",
                "view",
                "stateless",
                "insecure-no-auth",
                "legacy",
                "check-only",
            ]
            .contains(&name)
            {
                require(
                    inline.is_none(),
                    format!("--{name} does not accept a value"),
                    "INVALID_ARGUMENT",
                )?;
                options[&key] = json!(true);
            } else {
                let raw = inline
                    .map(String::from)
                    .or_else(|| iterator.next().cloned())
                    .ok_or_else(|| {
                        Error::new("INVALID_ARGUMENT", format!("--{name} requires a value"))
                    })?;
                let value = if ["port", "expected", "revision", "concurrency"].contains(&name) {
                    let number = raw.parse::<i64>().map_err(|_| {
                        Error::new("INVALID_ARGUMENT", format!("--{name} must be an integer"))
                    })?;
                    require(
                        if name == "concurrency" {
                            (1..=4).contains(&number)
                        } else if name == "port" {
                            (0..=65535).contains(&number)
                        } else {
                            number > 0
                        },
                        format!("--{name} is outside the allowed range"),
                        "INVALID_ARGUMENT",
                    )?;
                    json!(number)
                } else if ["idle-timeout", "share-ttl-hours", "hours"].contains(&name) {
                    let number = raw.parse::<f64>().map_err(|_| {
                        Error::new("INVALID_ARGUMENT", format!("--{name} must be numeric"))
                    })?;
                    require(
                        number.is_finite()
                            && if name == "idle-timeout" {
                                number >= 0.0
                            } else {
                                number > 0.0
                            },
                        format!(
                            "--{name} must be {}",
                            if name == "idle-timeout" {
                                "non-negative"
                            } else {
                                "positive"
                            }
                        ),
                        "INVALID_ARGUMENT",
                    )?;
                    json!(number)
                } else {
                    json!(raw)
                };
                if ["board", "token", "allowed-host"].contains(&name) {
                    if options.get(&key).is_none() {
                        options[&key] = json!([]);
                    }
                    options[&key].as_array_mut().unwrap().push(value);
                } else {
                    options[&key] = value;
                }
            }
        } else if command.is_none() {
            require(
                COMMANDS.contains(&argument.as_str()),
                format!("Unsupported command: {argument}"),
                "INVALID_ARGUMENT",
            )?;
            command = Some(argument.clone());
        } else {
            positionals.push(argument.clone());
        }
    }
    let command = command
        .ok_or_else(|| Error::new("INVALID_ARGUMENT", "A command is required; use --help"))?;
    let mut allowed: BTreeSet<&str> = ["root", "project_root", "runtime_root", "sources"]
        .into_iter()
        .collect();
    let specifics: &[&str] = match command.as_str() {
        "init" => &["title", "demo", "mode"],
        "migrate-project" => &["source_root", "board", "apply"],
        "patch" => &["expected", "file"],
        "restore" => &["expected", "revision"],
        "serve" => &["port", "dashboard", "view", "idle_timeout"],
        "export" => &["output", "format", "dataset", "component"],
        "import" => &["file"],
        "validate" => &["file"],
        "import-workspace" => &["path"],
        "call" => &["json_file"],
        "mcp" => &["idle_timeout"],
        "transfer" => &[
            "manifest",
            "project",
            "state",
            "concurrency",
            "legacy",
            "check_only",
            "resume_staged",
        ],
        "remote" => &[
            "project",
            "dashboard",
            "output",
            "ref",
            "rows",
            "fields",
            "state",
            "concurrency",
            "check_only",
            "legacy",
            "resume_staged",
        ],
        "server" | "share" => &[
            "workspace",
            "public_url",
            "token",
            "token_file",
            "share_ttl_hours",
            "default_project",
            "host",
            "port",
            "stateless",
            "allowed_host",
            "forwarded_allow_ips",
            "insecure_no_auth",
            "access",
            "hours",
        ],
        _ => &[],
    };
    allowed.extend(specifics.iter().copied());
    for key in options.as_object().unwrap().keys() {
        require(
            allowed.contains(key.as_str()),
            format!("Unknown option --{} for {command}", key.replace('_', "-")),
            "INVALID_ARGUMENT",
        )?;
    }
    let count = match command.as_str() {
        "init" | "get" | "validate" | "history" | "patch" | "restore" | "export" | "import"
        | "import-workspace" | "call" | "remote" => 1,
        "share" => 2,
        _ => 0,
    };
    let file_validation = command == "validate" && options.get("file").is_some();
    require(
        positionals.len() == count || file_validation && positionals.is_empty(),
        format!("{command} expects {count} positional arguments"),
        "INVALID_ARGUMENT",
    )?;
    options["command"] = json!(command);
    if count == 1 && !positionals.is_empty() {
        options[match command.as_str() {
            "call" => "tool",
            "remote" => "action",
            _ => "id",
        }] = json!(positionals[0]);
    }
    if command == "remote" {
        require(
            ["read", "upload"].contains(&options["action"].as_str().unwrap_or("")),
            "remote expects read or upload",
            "INVALID_ARGUMENT",
        )?;
    }
    if count == 2 {
        options["project"] = json!(positionals[0]);
        options["dashboard"] = json!(positionals[1]);
    }
    Ok(options)
}
fn path(value: &str) -> Result<PathBuf> {
    let expanded = if value == "~" || value.starts_with("~/") {
        let home = std::env::var_os("HOME")
            .ok_or_else(|| Error::new("INVALID_PATH", "Home directory is unavailable"))?;
        PathBuf::from(home).join(value.strip_prefix("~/").unwrap_or(""))
    } else {
        PathBuf::from(value)
    };
    Ok(if expanded.is_absolute() {
        expanded
    } else {
        std::env::current_dir()?.join(expanded)
    })
}
fn json_input(name: &str) -> Result<Value> {
    let mut bytes = Vec::new();
    if name == "-" {
        io::stdin()
            .lock()
            .take(17 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)?;
    } else {
        fs::File::open(path(name)?)?
            .take(17 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)?;
    }
    require(
        bytes.len() <= 17 * 1024 * 1024,
        "JSON input exceeds the document limit",
        "PAYLOAD_TOO_LARGE",
    )?;
    Ok(serde_json::from_slice(&bytes)?)
}
pub fn run(args: &[String]) -> Result<()> {
    if args.iter().any(|v| v == "--help" || v == "-h") {
        help();
        return Ok(());
    }
    if args == ["--version"] {
        println!("charts-design-core {}", env!("CARGO_PKG_VERSION"));
        return Ok(());
    }
    let options = parse(args)?;
    let command = string(&options, "command")?;
    if command == "validate" && options.get("file").is_some() {
        let value = json_input(string(&options, "file")?)?;
        model::validate(value.get("document").unwrap_or(&value))?;
        println!("{}", json!({"valid":true}));
        return Ok(());
    }
    if command == "transfer" {
        println!(
            "{}",
            serde_json::to_string(&super::transfer::command(&options)?)?
        );
        return Ok(());
    }
    if command == "remote" {
        println!(
            "{}",
            serde_json::to_string(&super::transfer::remote_command(&options)?)?
        );
        return Ok(());
    }
    if matches!(command, "server" | "share") {
        if let Some(result) = super::server::command(&options)? {
            println!("{}", serde_json::to_string(&result)?);
        }
        return Ok(());
    }
    let root = path(
        options["runtime_root"]
            .as_str()
            .unwrap_or(options["root"].as_str().unwrap_or(".charts-runtime")),
    )?;
    let project = options["project_root"].as_str().map(path).transpose()?;
    let sources = options["sources"].as_str().map(path).transpose()?;
    let service = Service::new(&root, sources.as_deref(), project.as_deref())?;
    if project.is_none() && command != "mcp" {
        require(
            !["init", "import", "import-workspace"].contains(&command),
            "Specify --project-root for new dashboards",
            "PROJECT_REQUIRED",
        )?;
    }
    let id = options["id"].as_str().unwrap_or("");
    let result = match command {
        "init" => {
            let mode = options["mode"].as_str().unwrap_or("dashboard");
            require(["dashboard", "report"].contains(&mode), "mode must be dashboard or report", "INVALID_ARGUMENT")?;
            let title = options["title"].as_str().unwrap_or(if mode == "report" {"Analysis report"} else {"Dashboard"});
            let mut doc = model::new_document(id, title)?;
            if options["demo"] == true {
                let example = discovery::examples(Some(if mode == "report" {"academic-report"} else {"executive-dashboard"}))?;
                doc = model::apply_operations(&doc, example["operations"].as_array().unwrap())?;
            }
            if let Some(title) = options.get("title") { doc["manifest"]["title"] = title.clone(); }
            if mode == "report" && doc["manifest"]["viewMode"] != "report" {
                doc = model::apply_operations(&doc, &[json!({"op":"set_view_mode","value":"report"})])?;
            }
            service.call("dashboard_create", &json!({"dashboardId":id,"document":doc}))?
        }
        "list" => service.call("dashboard_list", &json!({}))?,
        "get" | "validate" | "history" => service.call(&format!("dashboard_{command}"), &json!({"dashboardId":id}))?,
        "patch" => service.call("dashboard_patch", &json!({"dashboardId":id,"expectedRevision":integer(&options,"expected")?,"operations":json_input(string(&options,"file")?)?}))?,
        "restore" => service.call("dashboard_restore", &json!({"dashboardId":id,"expectedRevision":integer(&options,"expected")?,"revision":integer(&options,"revision")?}))?,
        "call" => {
            let tool = string(&options, "tool")?;
            require(contract::tool_schema(tool).is_some(), format!("Unsupported tool: {tool}"), "UNKNOWN_TOOL")?;
            service.call(tool, &json_input(options["json_file"].as_str().unwrap_or("-"))?)?
        }
        "catalog" => discovery::catalog(),
        "contract" => contract::discoverable_contract(false),
        "import" => service.call("dashboard_create", &json!({"dashboardId":id,"document":json_input(string(&options,"file")?)?}))?,
        "import-workspace" => {
            let (doc, notes) = import_workspace(&path(string(&options, "path")?)?, id)?;
            let mut result = service.call("dashboard_create", &json!({"dashboardId":id,"document":doc}))?;
            result["migrationNotes"] = notes;
            result
        }
        "migrate-project" => {
            let project = project.as_ref().ok_or_else(|| Error::new("PROJECT_REQUIRED", "Migration requires --project-root"))?;
            let boards = options["board"].as_array().filter(|v| !v.is_empty())
                .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Migration requires --board"))?
                .iter().map(|v| v.as_str().map(String::from).ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid board")))
                .collect::<Result<Vec<_>>>()?;
            store::migrate_project(&path(string(&options, "source_root")?)?, project, &root, &boards, options["apply"] == true)?
        }
        "export" => {
            let doc = service.store.get(id, false)?;
            let output = path(string(&options, "output")?)?;
            if let Some(parent) = output.parent() { fs::create_dir_all(parent)?; }
            let format = options["format"].as_str().unwrap_or("html");
            require(["html", "json", "csv"].contains(&format), "format must be html, json or csv", "INVALID_ARGUMENT")?;
            let mut result = json!({"output":output,"revision":doc["revision"],"format":format});
            if format == "csv" {
                let mut request = json!({"dashboardId":id});
                if let Some(dataset) = options.get("dataset") { request["datasetId"] = dataset.clone(); }
                if let Some(component) = options.get("component") { request["componentId"] = component.clone(); }
                let mut exported = service.call("dataset_export", &request)?["export"].clone();
                if let Some(content) = exported.as_object_mut().unwrap().remove("content") {
                    fs::write(&output, STANDARD.decode(content.as_str().unwrap_or("")).map_err(|e| Error::new("INVALID_RESULT", e.to_string()))?)?;
                } else {
                    let source = exported.as_object_mut().unwrap().remove("path").ok_or_else(|| Error::new("INVALID_RESULT", "Export has no data"))?;
                    fs::copy(path(source.as_str().unwrap_or(""))?, &output)?;
                }
                result.as_object_mut().unwrap().extend(exported.as_object().unwrap().clone());
            } else if format == "html" {
                let exported = service.call("dashboard_export", &json!({"dashboardId":id,"format":"html"}))?;
                fs::copy(path(string(&exported["export"], "path")?)?, &output)?;
            } else {
                fs::write(&output, serde_json::to_vec_pretty(&service.store.hydrate(&doc)?)?)?;
            }
            super::exports::private_file(&output)?;
            result
        }
        "serve" => {
            let dashboard = options["dashboard"].as_str();
            require(options["view"] != true || dashboard.is_some(), "Choose --dashboard when opening a saved-version --view", "INVALID_ARGUMENT")?;
            if let Some(id) = dashboard { service.store.revision(id)?; }
            assets::require_preview()?;
            let port = options["port"].as_u64().unwrap_or(8765);
            require(port <= u16::MAX as u64, "Port must be from 0 to 65535", "INVALID_ARGUMENT")?;
            super::server::serve_local(service, port as u16, options["idle_timeout"].as_f64().unwrap_or(60.0), dashboard, options["view"] == true)?;
            return Ok(());
        }
        "mcp" => {
            super::mcp::run(service, options["idle_timeout"].as_f64().unwrap_or(60.0))?;
            return Ok(());
        }
        _ => return Err(Error::new("INVALID_ARGUMENT", format!("Unsupported command: {command}"))),
    };
    println!("{}", serde_json::to_string(&result)?);
    Ok(())
}

pub fn import_workspace(root: &Path, board: &str) -> Result<(Value, Value)> {
    let root = root.canonicalize()?;
    let read = |relative: &str| -> Result<Value> {
        let target = root.join(relative).canonicalize()?;
        require(
            target.starts_with(&root),
            "Workspace reference escapes its root",
            "PATH_OUTSIDE_WORKSPACE",
        )?;
        Ok(serde_json::from_slice(&fs::read(target)?)?)
    };
    let old = read("dashboard.json")?;
    require(
        old["schemaVersion"] == 1,
        "Expected workspace schemaVersion 1",
        "INVALID_ARGUMENT",
    )?;
    let doc = model::new_document(
        board,
        old["meta"]["title"]
            .as_str()
            .unwrap_or("Imported dashboard"),
    )?;
    let mut ops = vec![
        json!({"op":"put_source","id":"workspace-import","value":{"kind":"file","name":root.file_name().unwrap_or_default().to_string_lossy(),"verification":"supplied"}}),
    ];
    let refs = &old["components"];
    for (collection, family, label) in [("charts", "chart", "title"), ("kpis", "kpi", "label")] {
        for (index, relative) in refs[collection]
            .as_array()
            .into_iter()
            .flatten()
            .enumerate()
        {
            let item =
                read(relative.as_str().ok_or_else(|| {
                    Error::new("INVALID_ARGUMENT", "Invalid workspace reference")
                })?)?;
            let id = item["id"]
                .as_str()
                .map(String::from)
                .unwrap_or_else(|| format!("{family}-{index}"));
            model::check_identifier(&id)?;
            ops.push(json!({"op":"put_component","id":id,"value":{"kind":"legacy","family":family,"title":item[label].as_str().unwrap_or(&id),"config":item,"sourceId":"workspace-import"}}));
        }
    }
    if let Some(relative) = refs["table"].as_str() {
        let table = read(relative)?;
        if table["columns"].as_array().is_some_and(|v| !v.is_empty()) {
            let id = table["id"].as_str().unwrap_or("import-table");
            model::check_identifier(id)?;
            ops.push(json!({"op":"put_component","id":id,"value":{"kind":"legacy","family":"table","title":table["title"].as_str().unwrap_or("Details"),"config":table,"sourceId":"workspace-import"}}));
        }
    }
    let mut result = model::apply_operations(&doc, &ops)?;
    result["manifest"]["originalWorkspace"] = json!({"meta":old.get("meta").unwrap_or(&json!({})),"manifest":old,"filters":if let Some(path)=refs["filters"].as_str(){read(path)?}else{json!([])}});
    let mut order = result["manifest"]["components"]
        .as_object()
        .unwrap()
        .keys()
        .cloned()
        .collect::<Vec<_>>();
    order.sort_by_key(
        |id| match result["manifest"]["components"][id]["family"].as_str() {
            Some("kpi") => 0,
            Some("chart") => 1,
            _ => 2,
        },
    );
    for (breakpoint, columns) in [("desktop", 12), ("tablet", 8), ("mobile", 4)] {
        let (mut x, mut y, mut height) = (0, 0, 0);
        let mut positions = Vec::new();
        for id in &order {
            let component = &result["manifest"]["components"][id];
            let kpi = component["family"] == "kpi";
            let table = component["family"] == "table";
            let width = if breakpoint == "mobile" || table || component["config"]["colSpan"] == 2 {
                columns
            } else if kpi && breakpoint == "desktop" {
                columns / 4
            } else {
                columns / 2
            };
            let h = if kpi {
                4
            } else if table {
                12
            } else {
                8
            };
            if x + width > columns {
                y += height;
                x = 0;
                height = 0;
            }
            positions.push(json!({"id":id,"x":x,"y":y,"w":width,"h":h}));
            x += width;
            height = height.max(h);
        }
        result["manifest"]["layout"][breakpoint] = json!(positions);
    }
    model::validate(&result)?;
    Ok((result,json!(["Original chart, KPI and table configurations are preserved; bind verified data paths before enabling cross-component filters."])))
}
