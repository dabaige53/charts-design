PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS publications (
  id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  board TEXT NOT NULL,
  revision INTEGER NOT NULL,
  mode TEXT NOT NULL,
  expires_at INTEGER,
  revoked INTEGER NOT NULL DEFAULT 0,
  document TEXT,
  files TEXT
);
CREATE INDEX IF NOT EXISTS publications_due ON publications(expires_at) WHERE document IS NOT NULL;

CREATE TABLE IF NOT EXISTS publication_chunks (
  share_id TEXT NOT NULL REFERENCES publications(id),
  part INTEGER NOT NULL,
  contents BLOB NOT NULL,
  PRIMARY KEY (share_id, part)
);

CREATE TABLE IF NOT EXISTS pages_snapshots (
  share_id TEXT PRIMARY KEY REFERENCES publications(id),
  assets TEXT NOT NULL,
  title TEXT NOT NULL,
  deployment_id TEXT
);

CREATE TABLE IF NOT EXISTS pages_deployment_lock (
  id INTEGER PRIMARY KEY CHECK(id=1),
  token TEXT NOT NULL,
  expires_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS annotations (
  share_id TEXT NOT NULL REFERENCES publications(id),
  id TEXT NOT NULL,
  received_at INTEGER NOT NULL,
  fingerprint TEXT NOT NULL,
  payload TEXT NOT NULL,
  PRIMARY KEY (share_id, id)
);

CREATE TABLE IF NOT EXISTS access_attempts (
  share_id TEXT NOT NULL,
  client TEXT NOT NULL,
  window INTEGER NOT NULL,
  attempts INTEGER NOT NULL,
  PRIMARY KEY (share_id, client, window)
);
