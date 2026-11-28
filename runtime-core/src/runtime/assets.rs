//! Shared, compiled UI assets; HTML bootstrap never includes executable JSON.
use super::error::{require, Error, Result};
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
use std::{collections::BTreeMap, fs, path::PathBuf};

pub const MIME_TYPE: &str = "text/html;profile=mcp-app";
pub const UI_RESOURCES: [&str; 3] = ["app.js", "app.css", "static-worker.js"];
pub fn package_root() -> PathBuf {
    if let Some(path) = std::env::var_os("CHARTS_PACKAGE_ROOT") {
        return PathBuf::from(path);
    }
    if let Ok(executable) = std::env::current_exe() {
        for path in executable.ancestors().skip(1).take(6) {
            if path.join("package.json").is_file() && path.join("runtime-ui").is_dir() {
                return path.to_path_buf();
            }
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .to_path_buf()
}
pub fn dist() -> PathBuf {
    std::env::var_os("CHARTS_UI_DIST")
        .map(PathBuf::from)
        .unwrap_or_else(|| package_root().join("runtime-ui/dist"))
}
pub fn ui_build_id() -> String {
    build_manifest()["id"]
        .as_str()
        .map(String::from)
        .unwrap_or_else(|| "unavailable".into())
}
fn build_manifest() -> Value {
    fs::read(dist().join("build.json"))
        .ok()
        .and_then(|raw| serde_json::from_slice(&raw).ok())
        .unwrap_or(Value::Null)
}
pub fn ui_resource_uri() -> String {
    format!("ui://charts-design/dashboard-{}.html", ui_build_id())
}
pub fn backend_build_id() -> &'static str {
    env!("CHARTS_BACKEND_BUILD_ID")
}
pub fn require_preview() -> Result<()> {
    require(
        ui_build_id() != "unavailable",
        "UI 尚未打包；请运行 bun run ui:prepare。",
        "UI_UNAVAILABLE",
    )
    .map_err(|e| e.with_status(503))
}
pub fn favicon_link() -> String {
    let svg = r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="2" y="2" width="60" height="60" rx="14" fill="#1016bf"/><path d="M15 45 32 34 49 19" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><g fill="#fff"><circle cx="15" cy="45" r="5"/><circle cx="32" cy="34" r="5"/><circle cx="49" cy="19" r="5"/></g></svg>"##;
    format!(
        "<link rel=\"icon\" type=\"image/svg+xml\" href=\"data:image/svg+xml;base64,{}\">",
        STANDARD.encode(svg)
    )
}
fn boot_json(
    mode: &str,
    document: Option<&Value>,
    idle_timeout: Option<f64>,
    boot_state: Option<&Value>,
) -> Result<String> {
    require_preview()?;
    let mut boot = json!({"mode":mode,"document":document,"idleTimeout":idle_timeout,"uiBuildId":ui_build_id()});
    if let Some(state) = boot_state {
        let state = state
            .as_object()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Boot state must be an object"))?;
        boot.as_object_mut().unwrap().extend(state.clone());
    }
    Ok(serde_json::to_string(&boot)?.replace('<', "\\u003c"))
}
pub fn render_html(
    mode: &str,
    document: Option<&Value>,
    idle_timeout: Option<f64>,
    boot_state: Option<&Value>,
) -> Result<String> {
    let boot = boot_json(mode, document, idle_timeout, boot_state)?;
    let css = fs::read_to_string(dist().join("app.css"))?.replace("</style", "<\\/style");
    let js = fs::read_to_string(dist().join("app.js"))?.replace("</script", "<\\/script");
    Ok(format!("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Charts Design</title>{}<style>{css}</style></head><body><div id=\"root\"></div><script>window.__chartsBoot={boot};</script><script>{js}</script></body></html>",favicon_link()))
}
pub fn render_web_html(base: &str, idle_timeout: Option<f64>, state: &Value) -> Result<String> {
    let boot = boot_json("web", None, idle_timeout, Some(state))?;
    let manifest = build_manifest();
    let id = manifest["webId"]
        .as_str()
        .or(manifest["id"].as_str())
        .ok_or_else(|| Error::new("UI_UNAVAILABLE", "Missing UI build"))?;
    let prefix = format!("{base}/assets/{id}")
        .replace('&', "&amp;")
        .replace('"', "&quot;")
        .replace('<', "&lt;");
    let preload = r#"(()=>{const b=window.__chartsBoot;const token=new URLSearchParams(location.hash.slice(1)).get('token');if(!token||!b.readOnly||!b.dashboardId)return;window.__chartsInitialPreview=fetch((b.apiBase||'/api/tools/')+'dashboard_preview',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({dashboardId:b.dashboardId})}).then(r=>r.ok?r.json():null).catch(()=>null);})();"#;
    Ok(format!("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Charts Design</title>{}<link rel=\"stylesheet\" href=\"{prefix}/app.css\"><script defer src=\"{prefix}/app.js\"></script></head><body><div id=\"root\"></div><script>window.__chartsBoot={boot};</script><script>{preload}</script></body></html>", favicon_link()))
}

pub fn web_asset(build: &str, name: &str) -> Result<(PathBuf, &'static str)> {
    let manifest = build_manifest();
    let web = manifest["webId"].as_str();
    require(
        web.or(manifest["id"].as_str()) == Some(build),
        "Unknown asset build",
        "NOT_FOUND",
    )?;
    let registered_font = web.is_some()
        && manifest["fonts"]
            .as_array()
            .is_some_and(|fonts| fonts.iter().any(|font| font.as_str() == Some(name)));
    let mime = match name {
        "app.css" => "text/css; charset=utf-8",
        "app.js" | "static-worker.js" => "text/javascript; charset=utf-8",
        name if registered_font && name.ends_with(".woff2") => "font/woff2",
        name if registered_font && name.ends_with(".woff") => "font/woff",
        name if registered_font && name.ends_with(".ttf") => "font/ttf",
        _ => return Err(Error::new("NOT_FOUND", "Unknown asset")),
    };
    let root = if web.is_some() {
        dist().join("web")
    } else {
        dist()
    };
    Ok((root.join(name), mime))
}
pub fn bundle_assets() -> Result<BTreeMap<String, Vec<u8>>> {
    require_preview()?;
    let build = build_manifest();
    UI_RESOURCES
        .into_iter()
        .map(|name| {
            let path = if name == "app.js" && build["webId"].is_string() {
                dist().join("web/app.js")
            } else {
                dist().join(name)
            };
            Ok((name.to_owned(), fs::read(path)?))
        })
        .collect()
}
pub fn export_document(document: &Value) -> Result<String> {
    require(
        !super::service::has_live(document),
        "实时 SQL 看板请通过运行服务查看",
        "LIVE_DATA_REQUIRES_RUNTIME",
    )?;
    let mut doc = document.clone();
    doc["snapshot"] = json!({"datasets":{}});
    if let Some(root) = doc.as_object_mut() {
        for key in [
            "loading",
            "progressive",
            "browserLinks",
            "annotationAccess",
            "publicationApiBase",
            "publication",
            "annotationsOpen",
        ] {
            root.remove(key);
        }
    }
    if let Some(manifest) = doc.get_mut("manifest").and_then(Value::as_object_mut) {
        for key in ["sources", "queries", "annotations"] {
            manifest.remove(key);
        }
    }
    if let Some(artifacts) = doc
        .get_mut("statisticalArtifacts")
        .and_then(Value::as_object_mut)
    {
        for artifact in artifacts.values_mut() {
            if let Some(a) = artifact.as_object_mut() {
                a.remove("provenance");
            }
        }
    }
    render_html("snapshot", Some(&doc), Some(60.0), None)
}
pub fn export_component(document: &Value, id: &str) -> Result<String> {
    let component = document["manifest"]["components"]
        .get(id)
        .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Unknown component"))?;
    let mut doc = document.clone();
    doc["manifest"]["components"] = json!({id:component});
    doc["manifest"]["filters"] = json!([]);
    doc["manifest"]["viewMode"] = json!("dashboard");
    for (breakpoint, columns) in [("desktop", 12), ("tablet", 8), ("mobile", 4)] {
        doc["manifest"]["layout"][breakpoint] = json!([{"id":id,"x":0,"y":0,"w":columns,"h":10}]);
    }
    export_document(&doc)
}
