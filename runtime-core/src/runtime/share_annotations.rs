//! Append-only publication feedback, isolated from author documents and revisions.
use super::{
    cloud::CloudDatabase,
    error::{require, Error, Result},
    object_storage::Storage,
};
use fs2::FileExt;
use rusqlite::{params, Connection, OpenFlags, OptionalExtension};
use serde_json::{json, Value};
use std::{
    fs::{self, OpenOptions},
    path::{Path, PathBuf},
    time::Duration,
};

pub enum ShareAnnotations {
    Local(PathBuf),
    Remote(CloudDatabase),
}
impl ShareAnnotations {
    pub fn for_storage(storage: &Storage) -> Result<Self> {
        if let Some(root) = storage.root() {
            return Ok(Self::Local(root.canonicalize()?));
        }
        CloudDatabase::new()
            .and_then(|db| db.with_function("charts_share_annotations"))
            .map(Self::Remote)
            .map_err(|_| {
                Error::new(
                    "ANNOTATIONS_NOT_CONFIGURED",
                    "分享服务尚未配置持久批注数据库",
                )
                .with_status(503)
            })
    }
    pub fn kind(&self) -> &'static str {
        match self {
            Self::Local(_) => "sqlite-v1",
            Self::Remote(_) => "postgres-v1",
        }
    }
    pub fn call(&self, action: &str, payload: &Value) -> Result<Value> {
        let share = payload["shareId"]
            .as_str()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Share ID is required"))?;
        super::shares::checked_id(share)?;
        match self {
            Self::Remote(database) => database.call(action, "", payload),
            Self::Local(root) => {
                let locks = root.join("share-locks");
                fs::create_dir_all(&locks)?;
                let lock = OpenOptions::new()
                    .read(true)
                    .write(true)
                    .create(true)
                    .truncate(false)
                    .open(locks.join(format!("{share}.lock")))?;
                lock.lock_exclusive()?;
                let result = Self::local_call(root, action, share, payload);
                FileExt::unlock(&lock)?;
                result
            }
        }
    }
    fn retire(path: &Path) -> Result<()> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(false)
            .open(path)?;
        Ok(())
    }
    fn local_call(root: &Path, action: &str, share: &str, payload: &Value) -> Result<Value> {
        let path = root.join("shares").join(share).join("annotations.sqlite3");
        let retired = root.join("retired").join(share);
        if matches!(action, "delete" | "cleanup_claim") && (retired.exists() || !path.is_file()) {
            Self::retire(&retired)?;
            return Ok(json!({"claimed":true,"deleted":true}));
        }
        require(!retired.exists(), "分享已过期或撤销", "SHARE_EXPIRED")?;
        if action == "ready" {
            return Ok(json!({"ready":true}));
        }
        let flags = if action == "configure" {
            fs::create_dir_all(path.parent().unwrap())?;
            OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_CREATE
        } else {
            require(path.is_file(), "分享批注存储不可用", "SHARE_UNAVAILABLE")?;
            OpenFlags::SQLITE_OPEN_READ_WRITE
        };
        let mut db = Connection::open_with_flags(&path, flags)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(path.parent().unwrap(), fs::Permissions::from_mode(0o700))?;
            fs::set_permissions(&path, fs::Permissions::from_mode(0o600))?;
        }
        db.busy_timeout(Duration::from_secs(30))?;
        let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        if matches!(action, "delete" | "cleanup_claim") {
            let scope: bool = tx.query_row(
                "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name='scope')",
                [],
                |r| r.get(0),
            )?;
            if !scope {
                Self::retire(&retired)?;
                tx.commit()?;
                return Ok(json!({"claimed":true,"deleted":true}));
            }
        }
        if action == "configure" {
            tx.execute_batch("CREATE TABLE IF NOT EXISTS scope (id INTEGER PRIMARY KEY CHECK(id=1), state TEXT, payload TEXT); CREATE TABLE IF NOT EXISTS notes (board TEXT, id TEXT, fingerprint TEXT, payload TEXT, PRIMARY KEY(board,id));")?;
            let mut definition = json!({"owner":payload["owner"],"pages":payload["pages"],"expiresAt":payload["expiresAt"],"annotationMode":payload["annotationMode"],"sourceDigest":payload["sourceDigest"],"stagingUntil":payload.get("stagingUntil").cloned().unwrap_or_else(||json!(super::shares::now()+3600))});
            let previous: Option<(String, String)> = tx
                .query_row("SELECT state,payload FROM scope WHERE id=1", [], |r| {
                    Ok((r.get(0)?, r.get(1)?))
                })
                .optional()?;
            if let Some((state, raw)) = previous {
                require(
                    matches!(state.as_str(), "uploading" | "active"),
                    "分享已撤销",
                    "SHARE_EXPIRED",
                )?;
                let previous: Value = serde_json::from_str(&raw)?;
                require(
                    alive(&previous, "expiresAt")
                        && (state == "active" || alive(&previous, "stagingUntil")),
                    "分享发布暂存已过期",
                    "SHARE_EXPIRED",
                )?;
                let mut compared = definition.clone();
                compared["stagingUntil"] = previous["stagingUntil"].clone();
                if !definition["sourceDigest"].is_null() {
                    compared["expiresAt"] = previous["expiresAt"].clone();
                }
                require(
                    previous == compared,
                    "分享请求已用于其他版本或权限",
                    "REVISION_CONFLICT",
                )?;
                definition = previous;
            } else {
                tx.execute(
                    "INSERT INTO scope VALUES(1,?,?)",
                    params!["uploading", serde_json::to_string(&definition)?],
                )?;
            }
            tx.commit()?;
            return Ok(
                json!({"ready":true,"expiresAt":definition["expiresAt"],"stagingUntil":definition["stagingUntil"]}),
            );
        }
        let row: Option<(String, String)> = tx
            .query_row("SELECT state,payload FROM scope WHERE id=1", [], |r| {
                Ok((r.get(0)?, r.get(1)?))
            })
            .optional()?;
        let (state, raw) = row.ok_or_else(|| Error::new("SHARE_UNAVAILABLE", "分享不存在"))?;
        let scope: Value = serde_json::from_str(&raw)?;
        let result = if matches!(action, "delete" | "cleanup_claim") {
            let now = payload["now"].as_i64().unwrap_or_else(super::shares::now);
            let due = matches!(state.as_str(), "revoked" | "retired")
                || payload["revoked"] == true
                || state == "uploading" && scope["stagingUntil"].as_i64().is_some_and(|v| v <= now)
                || state == "active" && scope["expiresAt"].as_i64().is_some_and(|v| v <= now);
            if action == "cleanup_claim" && !due {
                json!({"claimed":false,"state":state,"stagingUntil":scope["stagingUntil"]})
            } else {
                Self::retire(&retired)?;
                tx.execute("DELETE FROM notes", [])?;
                tx.execute(
                    "UPDATE scope SET state='retired',payload='{}' WHERE id=1",
                    [],
                )?;
                json!({"claimed":true,"deleted":true})
            }
        } else if action == "revoke" {
            tx.execute("UPDATE scope SET state='revoked' WHERE id=1", [])?;
            json!({"revoked":true})
        } else if action == "activate" {
            require(
                matches!(state.as_str(), "uploading" | "active")
                    && alive(&scope, "expiresAt")
                    && (state == "active" || alive(&scope, "stagingUntil")),
                "分享已过期或撤销",
                "SHARE_EXPIRED",
            )?;
            tx.execute("UPDATE scope SET state='active' WHERE id=1", [])?;
            json!({"active":true})
        } else {
            require(
                state == "active" && alive(&scope, "expiresAt"),
                "分享已过期或撤销",
                "SHARE_EXPIRED",
            )?;
            let board = payload["dashboardId"]
                .as_str()
                .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Dashboard ID is required"))?;
            let page = scope["pages"]
                .as_array()
                .into_iter()
                .flatten()
                .find(|p| p["id"] == board)
                .ok_or_else(|| Error::new("FORBIDDEN", "此分享不包含该页面"))?;
            if action == "read" {
                let mut stmt =
                    tx.prepare("SELECT payload FROM notes WHERE board=? ORDER BY rowid")?;
                let raw = stmt
                    .query_map([board], |r| r.get::<_, String>(0))?
                    .collect::<std::result::Result<Vec<_>, _>>()?;
                Value::Array(
                    raw.iter()
                        .map(|s| serde_json::from_str(s))
                        .collect::<std::result::Result<Vec<_>, _>>()?,
                )
            } else {
                require(
                    action == "append",
                    "Unknown annotation operation",
                    "INVALID_ARGUMENT",
                )?;
                require(
                    scope["annotationMode"] == "annotate",
                    "此分享仅允许查看",
                    "FORBIDDEN",
                )?;
                let note = &payload["annotation"];
                require(
                    note["context"]["designRevision"] == page["revision"],
                    "批注版本不匹配",
                    "REVISION_CONFLICT",
                )?;
                let note_id = note["id"]
                    .as_str()
                    .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Annotation ID is required"))?;
                let fingerprint = payload["fingerprint"].as_str().ok_or_else(|| {
                    Error::new("INVALID_ARGUMENT", "Annotation fingerprint is required")
                })?;
                let existing: Option<(String, String)> = tx
                    .query_row(
                        "SELECT fingerprint,payload FROM notes WHERE board=? AND id=?",
                        params![board, note_id],
                        |r| Ok((r.get(0)?, r.get(1)?)),
                    )
                    .optional()?;
                if let Some((previous, raw)) = existing {
                    require(
                        previous == fingerprint,
                        "此批注编号已用于其他内容",
                        "ANNOTATION_CONFLICT",
                    )?;
                    serde_json::from_str(&raw)?
                } else {
                    let count: i64 =
                        tx.query_row("SELECT count(*) FROM notes WHERE board=?", [board], |r| {
                            r.get(0)
                        })?;
                    require(count < 100, "此页面最多保存 100 条批注", "ANNOTATION_LIMIT")?;
                    tx.execute(
                        "INSERT INTO notes VALUES(?,?,?,?)",
                        params![board, note_id, fingerprint, serde_json::to_string(note)?],
                    )?;
                    note.clone()
                }
            }
        };
        tx.commit()?;
        Ok(result)
    }
}
fn alive(scope: &Value, key: &str) -> bool {
    scope[key].is_null()
        || scope[key]
            .as_i64()
            .is_some_and(|v| super::shares::now() < v)
}

#[cfg(test)]
#[path = "../../tests/unit/share_annotations.rs"]
mod tests;
