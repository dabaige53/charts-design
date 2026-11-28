//! Saved checkpoints, immutable release archives and reviewed deletion plans.
use super::{
    cloud::{self, CloudDatabase},
    error::{require, Error, Result},
    serialization::{json_bytes, utcnow},
    store::Store,
};
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
pub struct Versions<'a> {
    pub store: &'a Store,
    remote: Option<CloudDatabase>,
}
impl<'a> Versions<'a> {
    pub fn new(store: &'a Store) -> Result<Self> {
        let remote = store
            .database
            .as_ref()
            .map(|d| d.with_function("charts_release"))
            .transpose()?;
        if remote.is_none() && store.versions_initialized.get().is_none() {
            let mut db = store.connect()?;
            let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
            tx.execute_batch("CREATE TABLE IF NOT EXISTS releases(id INTEGER PRIMARY KEY AUTOINCREMENT,board_id TEXT NOT NULL,revision INTEGER NOT NULL,created_at TEXT NOT NULL,document TEXT NOT NULL);CREATE INDEX IF NOT EXISTS releases_board ON releases(board_id,id);CREATE INDEX IF NOT EXISTS releases_revision ON releases(board_id,revision,id);CREATE TABLE IF NOT EXISTS version_heads(board_id TEXT PRIMARY KEY,published INTEGER);INSERT OR IGNORE INTO version_heads SELECT board_id,revision FROM releases WHERE id IN (SELECT max(id) FROM releases GROUP BY board_id);CREATE TABLE IF NOT EXISTS version_delete_plans(token TEXT PRIMARY KEY,board_id TEXT,revision INTEGER,fingerprint TEXT,plan TEXT);")?;
            tx.commit()?;
            let _ = store.versions_initialized.set(());
        }
        Ok(Self { store, remote })
    }
    pub fn status(&self, board: &str) -> Result<Value> {
        if let Some(db) = &self.remote {
            return db.call("status", &self.store.project, &json!({"board":board}));
        }
        let mut db = self.store.connect()?;
        let tx = db.transaction()?;
        let current: Option<i64> = tx
            .query_row("SELECT revision FROM boards WHERE id=?", [board], |r| {
                r.get(0)
            })
            .optional()?;
        let current = current.ok_or_else(|| Error::new("NOT_FOUND", "Dashboard not found"))?;
        let saved: Option<i64> = tx.query_row(
            "SELECT max(revision) FROM revisions WHERE board_id=?",
            [board],
            |r| r.get(0),
        )?;
        let mut stmt=tx.prepare("SELECT id,revision,created_at FROM releases WHERE board_id=? ORDER BY id DESC LIMIT 100")?;
        let releases=stmt.query_map([board],|r|Ok(json!({"id":r.get::<_,i64>(0)?,"revision":r.get::<_,i64>(1)?,"created_at":r.get::<_,String>(2)?})))?.collect::<std::result::Result<Vec<_>,_>>()?;
        let published: Option<Option<i64>> = tx
            .query_row(
                "SELECT published FROM version_heads WHERE board_id=?",
                [board],
                |r| r.get(0),
            )
            .optional()?;
        Ok(
            json!({"draftRevision":current,"savedRevision":saved,"frozen":true,"publishedRevision":published.flatten(),"releases":releases,"deletionJobs":[]}),
        )
    }
    fn read_db(db: &Connection, board: &str, revision: i64) -> Result<Value> {
        let mut row: Option<String> = db
            .query_row(
                "SELECT document FROM revisions WHERE board_id=? AND revision=?",
                params![board, revision],
                |r| r.get(0),
            )
            .optional()?;
        if row.is_none() {
            row=db.query_row("SELECT document FROM releases WHERE board_id=? AND revision=? ORDER BY id DESC LIMIT 1",params![board,revision],|r|r.get(0)).optional()?;
        }
        let raw = row.ok_or_else(|| Error::new("NOT_FOUND", "Saved version not found"))?;
        Ok(serde_json::from_str(&raw)?)
    }
    pub fn read(&self, board: &str, revision: i64) -> Result<Value> {
        if let Some(db) = &self.remote {
            return self.store.decode(&db.call(
                "read",
                &self.store.project,
                &json!({"board":board,"revision":revision}),
            )?);
        }
        let mut db = self.store.connect()?;
        let tx = db.transaction()?;
        Self::read_db(&tx, board, revision)
    }
    pub fn publish(&self, board: &str, expected: i64, revision: i64) -> Result<Value> {
        require(
            expected > 0 && revision > 0,
            "Expected draft and saved revision are required",
            "INVALID_DOCUMENT",
        )?;
        if let Some(db) = &self.remote {
            return db.call(
                "publish",
                &self.store.project,
                &json!({"board":board,"expected":expected,"revision":revision,"at":utcnow()}),
            );
        }
        let mut db = self.store.connect()?;
        let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        let current: Option<i64> = tx
            .query_row("SELECT revision FROM boards WHERE id=?", [board], |r| {
                r.get(0)
            })
            .optional()?;
        require(
            current == Some(expected),
            "Reload before publishing",
            "REVISION_CONFLICT",
        )?;
        let doc = Self::read_db(&tx, board, revision)?;
        let last: Option<i64> = tx
            .query_row(
                "SELECT revision FROM releases WHERE board_id=? ORDER BY id DESC LIMIT 1",
                [board],
                |r| r.get(0),
            )
            .optional()?;
        if last != Some(revision) {
            tx.execute(
                "INSERT INTO releases(board_id,revision,created_at,document) VALUES(?,?,?,?)",
                params![
                    board,
                    revision,
                    utcnow(),
                    String::from_utf8_lossy(&json_bytes(&doc)?).as_ref()
                ],
            )?;
        }
        tx.execute(
            "INSERT OR REPLACE INTO version_heads VALUES(?,?)",
            params![board, revision],
        )?;
        tx.commit()?;
        self.status(board)
    }
    fn fingerprint(db: &Connection, board: &str) -> Result<String> {
        let mut parts = vec![];
        for (table, field) in [
            ("boards", "id"),
            ("revisions", "board_id"),
            ("releases", "board_id"),
            ("version_heads", "board_id"),
            ("checkpoint_meta", "board_id"),
            ("annotations", "board_id"),
            ("annotation_events", "board_id"),
        ] {
            let mut stmt = db.prepare(&format!("SELECT * FROM {table} WHERE {field}=?"))?;
            let count = stmt.column_count();
            let mut rows = stmt.query([board])?;
            while let Some(row) = rows.next()? {
                let mut values = vec![];
                for index in 0..count {
                    use rusqlite::types::ValueRef;
                    values.push(match row.get_ref(index)? {
                        ValueRef::Null => Value::Null,
                        ValueRef::Integer(n) => json!(n),
                        ValueRef::Real(n) => json!(n),
                        ValueRef::Text(s) => json!(String::from_utf8_lossy(s)),
                        ValueRef::Blob(_) => {
                            return Err(Error::new(
                                "INVALID_DOCUMENT",
                                "Unexpected binary version state",
                            ))
                        }
                    });
                }
                parts.push(Value::Array(values));
            }
        }
        Ok(format!("{:x}", Sha256::digest(json_bytes(&json!(parts))?)))
    }
    pub fn delete_preview(&self, board: &str, expected: i64, revision: i64) -> Result<Value> {
        if self.remote.is_some() {
            return cloud::version_delete_preview(self.store, board, expected, revision);
        }
        let mut db = self.store.connect()?;
        let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        let current: Option<i64> = tx
            .query_row("SELECT revision FROM boards WHERE id=?", [board], |r| {
                r.get(0)
            })
            .optional()?;
        require(
            current == Some(expected),
            "Reload before deleting",
            "REVISION_CONFLICT",
        )?;
        let doc = Self::read_db(&tx, board, revision)?;
        let fingerprint = Self::fingerprint(&tx, board)?;
        let next_saved: Option<i64> = tx.query_row(
            "SELECT max(revision) FROM revisions WHERE board_id=? AND revision<>?",
            params![board, revision],
            |r| r.get(0),
        )?;
        let head: Option<Option<i64>> = tx
            .query_row(
                "SELECT published FROM version_heads WHERE board_id=?",
                [board],
                |r| r.get(0),
            )
            .optional()?;
        let token = uuid::Uuid::new_v4().simple().to_string();
        let retained = doc["snapshot"]["datasetRefs"]
            .as_object()
            .into_iter()
            .flatten()
            .map(|(_, r)| json!({"version":r["version"],"references":[{"source":"local-data"}]}))
            .collect::<Vec<_>>();
        let plan = json!({"token":token,"revision":revision,"shares":[],"objects":[],"datasets":[],"retained":retained,"cosBytes":0,"postgresBytes":0,"nextSavedRevision":next_saved,"clearsPublication":head.flatten()==Some(revision),"checkedAt":utcnow()});
        tx.execute(
            "INSERT INTO version_delete_plans VALUES(?,?,?,?,?)",
            params![token, board, revision, fingerprint, plan.to_string()],
        )?;
        tx.commit()?;
        Ok(plan)
    }
    pub fn delete_status(&self, board: &str, job_id: &str, retry: bool) -> Result<Value> {
        require(
            self.remote.is_some(),
            "Cloud deletion task required",
            "UNSUPPORTED_OPERATION",
        )?;
        cloud::version_delete_status(self.store, board, job_id, retry)
    }
    pub fn delete_checkpoint(
        &self,
        board: &str,
        expected: i64,
        revision: i64,
        confirmation: Option<&str>,
    ) -> Result<Value> {
        require(
            expected > 0 && revision > 0,
            "Expected draft and checkpoint revision are required",
            "INVALID_DOCUMENT",
        )?;
        if self.remote.is_some() {
            require(
                confirmation.is_some_and(|s| !s.is_empty()),
                "Review deletion impact first",
                "CONFIRMATION_REQUIRED",
            )?;
            return cloud::version_delete_checkpoint(
                self.store,
                board,
                expected,
                revision,
                confirmation.unwrap_or(""),
            );
        }
        let mut db = self.store.connect()?;
        let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        let current: Option<i64> = tx
            .query_row("SELECT revision FROM boards WHERE id=?", [board], |r| {
                r.get(0)
            })
            .optional()?;
        require(
            current == Some(expected),
            "Reload before deleting",
            "REVISION_CONFLICT",
        )?;
        let plan:Option<String>=tx.query_row("SELECT fingerprint FROM version_delete_plans WHERE token=? AND board_id=? AND revision=?",params![confirmation,board,revision],|r|r.get(0)).optional()?;
        let fingerprint = plan
            .ok_or_else(|| Error::new("CONFIRMATION_REQUIRED", "Review deletion impact first"))?;
        require(
            fingerprint == Self::fingerprint(&tx, board)?,
            "删除影响已变化，请重新确认",
            "PLAN_CHANGED",
        )?;
        tx.execute(
            "DELETE FROM revisions WHERE board_id=? AND revision=?",
            params![board, revision],
        )?;
        tx.execute(
            "DELETE FROM releases WHERE board_id=? AND revision=?",
            params![board, revision],
        )?;
        tx.execute(
            "UPDATE version_heads SET published=NULL WHERE board_id=? AND published=?",
            params![board, revision],
        )?;
        tx.execute(
            "DELETE FROM checkpoint_meta WHERE board_id=? AND revision=?",
            params![board, revision],
        )?;
        if current == Some(revision) {
            let raw: String =
                tx.query_row("SELECT document FROM boards WHERE id=?", [board], |r| {
                    r.get(0)
                })?;
            let mut doc: Value = serde_json::from_str(&raw)?;
            doc["revision"] = json!(revision + 1);
            tx.execute(
                "UPDATE boards SET revision=?,document=? WHERE id=?",
                params![
                    revision + 1,
                    String::from_utf8_lossy(&json_bytes(&doc)?).as_ref(),
                    board
                ],
            )?;
        }
        tx.execute("DELETE FROM batches WHERE board_id=?", [board])?;
        tx.execute(
            "DELETE FROM version_delete_plans WHERE token=?",
            [confirmation],
        )?;
        tx.commit()?;
        self.store.sync_mirrors(
            board,
            current == Some(revision),
            false,
            true,
            Some(&[revision]),
            false,
        )?;
        Ok(json!({"deleted":true,"revision":revision,"state":"complete"}))
    }
}
