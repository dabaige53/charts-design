//! Stable errors shared by CLI, MCP, HTTP, and the native service.
use serde_json::{json, Value};
use std::fmt;

#[derive(Debug, Clone)]
pub struct Error {
    pub code: String,
    pub message: String,
    pub status: u16,
    pub request_id: Option<String>,
}

pub type Result<T> = std::result::Result<T, Error>;

impl Error {
    pub fn new(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
            status: 400,
            request_id: None,
        }
    }
    pub fn with_status(mut self, status: u16) -> Self {
        self.status = status;
        self
    }
    pub fn json(&self) -> Value {
        let mut value = json!({"ok": false, "error": {"code": self.code, "message": self.message}});
        if let Some(id) = &self.request_id {
            value["error"]["requestId"] = json!(id);
        }
        value
    }
}

impl fmt::Display for Error {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}
impl std::error::Error for Error {}
impl From<std::io::Error> for Error {
    fn from(error: std::io::Error) -> Self {
        Self::new("IO_ERROR", error.to_string()).with_status(500)
    }
}
impl From<serde_json::Error> for Error {
    fn from(error: serde_json::Error) -> Self {
        Self::new("INVALID_ARGUMENT", error.to_string())
    }
}
impl From<rusqlite::Error> for Error {
    fn from(error: rusqlite::Error) -> Self {
        Self::new("DATABASE_ERROR", error.to_string()).with_status(500)
    }
}
impl From<csv::Error> for Error {
    fn from(error: csv::Error) -> Self {
        Self::new("INVALID_ARGUMENT", error.to_string())
    }
}
pub fn require(condition: bool, message: impl Into<String>, code: impl Into<String>) -> Result<()> {
    if condition {
        Ok(())
    } else {
        Err(Error::new(code, message))
    }
}
