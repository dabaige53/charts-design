//! Managed exports and bounded reads; tool parameters never select arbitrary paths.
use super::{
    error::{require, Error, Result},
    model,
};
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
use std::{
    fs,
    io::{Read, Seek, SeekFrom},
    path::{Path, PathBuf},
};
use uuid::Uuid;
pub fn private_directory(path: &Path) -> Result<()> {
    fs::create_dir_all(path)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    }
    Ok(())
}
pub fn private_file(path: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    }
    Ok(())
}
pub fn export_target(root: &Path, board: &str, id: &str, format: &str) -> Result<PathBuf> {
    model::check_identifier(board)?;
    require(
        id.len() == 32
            && id
                .bytes()
                .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v)),
        "Invalid export ID",
        "INVALID_ARGUMENT",
    )?;
    require(
        ["html", "json", "csv", "zip"].contains(&format),
        "Invalid export format",
        "INVALID_ARGUMENT",
    )?;
    let root = root.canonicalize()?;
    let target = root
        .join("exports")
        .join(id)
        .join(format!("{board}.{format}"));
    for parent in target.ancestors().take_while(|path| *path != root) {
        if fs::symlink_metadata(parent).is_ok() {
            require(
                parent.canonicalize()?.starts_with(&root),
                "Export path leaves its project",
                "INVALID_PATH",
            )?;
        }
    }
    Ok(target)
}
pub fn export_path(root: &Path, board: &str, id: &str, format: &str) -> Result<PathBuf> {
    let path = export_target(root, board, id, format)?
        .canonicalize()
        .map_err(|_| Error::new("NOT_FOUND", "Export file not found"))?;
    require(path.is_file(), "Export file not found", "NOT_FOUND")?;
    Ok(path)
}
pub fn export_dashboard(root: &Path, doc: &Value, format: &str) -> Result<Value> {
    require(
        ["html", "json"].contains(&format),
        "Choose HTML or JSON",
        "INVALID_ARGUMENT",
    )?;
    let id = Uuid::new_v4().simple().to_string();
    let board = super::service::string(doc, "id")?;
    model::check_identifier(board)?;
    let directory = root.join("exports").join(&id);
    private_directory(&directory)?;
    let name = format!("{board}.{format}");
    let path = directory.join(&name);
    let result = (|| -> Result<Value> {
        let text = if format == "html" {
            super::assets::export_document(doc)?
        } else {
            serde_json::to_string_pretty(doc)?
        };
        fs::write(&path, text)?;
        private_file(&path)?;
        Ok(
            json!({"export":{"id":id,"filename":name,"path":path.canonicalize()?,"mimeType":if format=="html"{"text/html"}else{"application/json"},"bytes":fs::metadata(&path)?.len(),"format":format,"scope":if format=="html"{"current-view-snapshot"}else{"configuration-and-local-references"}}}),
        )
    })();
    if result.is_err() {
        let _ = fs::remove_dir_all(&directory);
    }
    result
}
pub fn read_export(
    root: &Path,
    board: &str,
    id: &str,
    format: &str,
    offset: u64,
    limit: usize,
) -> Result<Value> {
    let path = export_path(root, board, id, format)?;
    let total = fs::metadata(&path)?.len();
    require(offset <= total, "Invalid export offset", "INVALID_ARGUMENT")?;
    require(
        (1..=262144).contains(&limit),
        "Invalid export chunk size",
        "INVALID_ARGUMENT",
    )?;
    let mut file = fs::File::open(&path)?;
    file.seek(SeekFrom::Start(offset))?;
    let mut raw = Vec::new();
    file.take(limit as u64).read_to_end(&mut raw)?;
    let next = offset + raw.len() as u64;
    Ok(
        json!({"id":id,"filename":path.file_name().unwrap().to_string_lossy(),"offset":offset,"bytes":total,"content":STANDARD.encode(raw),"encoding":"base64","nextOffset":next,"hasMore":next<total}),
    )
}
pub fn open_export(
    root: &Path,
    board: &str,
    id: &str,
    format: &str,
    action: &str,
) -> Result<Value> {
    let path = export_path(root, board, id, format)?;
    require(
        ["open", "reveal"].contains(&action),
        "Invalid file action",
        "INVALID_ARGUMENT",
    )?;
    require(
        cfg!(target_os = "macos"),
        "当前平台暂不支持打开文件，请按显示的路径访问文件",
        "INVALID_ARGUMENT",
    )?;
    #[cfg(target_os = "macos")]
    {
        let mut command = std::process::Command::new("/usr/bin/open");
        if action == "reveal" {
            command.arg("-R");
        }
        let status = command.arg(&path).status().map_err(|_| {
            Error::new(
                "EXPORT_OPEN_FAILED",
                format!("打开失败，文件仍保存在：{}", path.display()),
            )
        })?;
        require(
            status.success(),
            format!("打开失败，文件仍保存在：{}", path.display()),
            "EXPORT_OPEN_FAILED",
        )?;
    }
    Ok(json!({"ok":true,"action":action,"path":path}))
}

#[cfg(test)]
#[path = "../../tests/unit/exports.rs"]
mod tests;
