//! PostgreSQL cloud contracts share one serialized environment fixture.
#[path = "support/postgres.rs"]
mod database;
#[path = "cloud/shares.rs"]
mod shares;
#[path = "cloud/workspace.rs"]
mod workspace;
