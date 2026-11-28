use charts_design_core::runtime::{operations, service::Service};
use postgres::{Client, NoTls};
use std::{env, ffi::OsString, path::PathBuf, sync::Mutex};

pub static ENVIRONMENT: Mutex<()> = Mutex::new(());

pub struct Database {
    administrator: Client,
    name: String,
    pub role: String,
    pub owner_url: String,
    pub runtime_url: String,
    directory: tempfile::TempDir,
    environment: Vec<(&'static str, Option<OsString>)>,
}

impl Database {
    pub fn new() -> Self {
        let source = env::var("CHARTS_TEST_DATABASE_URL").expect(
            "Set CHARTS_TEST_DATABASE_URL to a disposable local PostgreSQL administrator connection",
        );
        let mut owner = url::Url::parse(&source).expect("PostgreSQL test URL");
        assert!(
            matches!(owner.host_str(), Some("127.0.0.1" | "localhost" | "[::1]")),
            "Cloud integration tests only run against loopback PostgreSQL"
        );
        let mut administrator = Client::connect(&source, NoTls).expect("local test PostgreSQL");
        let suffix = &uuid::Uuid::new_v4().simple().to_string()[..16];
        let name = format!("charts_ci_{suffix}");
        let role = format!("charts_app_{suffix}");
        administrator
            .batch_execute(&format!(
                "CREATE ROLE {role} LOGIN PASSWORD 'charts-test-only' NOSUPERUSER NOCREATEDB NOCREATEROLE;"
            ))
            .unwrap();
        administrator
            .batch_execute(&format!("CREATE DATABASE {name}"))
            .unwrap();
        owner.set_path(&format!("/{name}"));
        let owner_url = owner.to_string();
        owner.set_username(&role).unwrap();
        owner.set_password(Some("charts-test-only")).unwrap();
        let runtime_url = owner.to_string();
        let directory = tempfile::tempdir().unwrap();
        let environment = [
            "DATABASE_URL",
            "CHARTS_NEON_RUNTIME_ROLE",
            "CHARTS_STORAGE_BACKEND",
            "CHARTS_DATABASE_BACKEND",
            "CHARTS_RUNTIME_ROOT",
            "CHARTS_PUBLIC_URL",
            "CHARTS_TEST_QUERY_URL",
            "CLOUDBASE_ENV_ID",
            "CLOUDBASE_API_KEY",
            "CHARTS_PORT",
            "TENCENTCLOUD_RUNENV",
        ]
        .into_iter()
        .map(|key| (key, env::var_os(key)))
        .collect();
        let fixture = Self {
            administrator,
            name,
            role,
            owner_url,
            runtime_url,
            directory,
            environment,
        };
        env::set_var("DATABASE_URL", &fixture.owner_url);
        env::set_var("CHARTS_NEON_RUNTIME_ROLE", &fixture.role);
        let first = operations::migrate_neon().unwrap();
        assert!(first["applied"].as_u64().unwrap() > 0);
        assert_eq!(first["runtimeRole"], fixture.role);
        assert_eq!(operations::migrate_neon().unwrap()["applied"], 0);
        env::set_var("DATABASE_URL", &fixture.runtime_url);
        env::set_var("CHARTS_STORAGE_BACKEND", "neon");
        env::set_var("CHARTS_DATABASE_BACKEND", "neon");
        env::set_var("CHARTS_RUNTIME_ROOT", fixture.directory.path());
        env::set_var("CHARTS_PUBLIC_URL", "https://charts.test");
        fixture
    }

    pub fn path(&self, name: &str) -> PathBuf {
        self.directory.path().join(name)
    }

    pub fn legacy_project(&self, project: &str) {
        // An existing project from before the COS default has no asset-state
        // row until the runtime first ensures it. New projects use COS at once.
        let mut owner = Client::connect(&self.owner_url, NoTls).unwrap();
        owner
            .execute(
                "INSERT INTO charts.projects(name,config) VALUES($1,$2)",
                &[&project, &charts_design_core::runtime::store::defaults()],
            )
            .unwrap();
    }

    pub fn service(&self, project: &str, cache: &str) -> Service {
        Service::new(
            &self.path(cache),
            None,
            Some(&self.path("workspaces").join(project)),
        )
        .unwrap()
    }
}

impl Drop for Database {
    fn drop(&mut self) {
        for (key, value) in &self.environment {
            match value {
                Some(value) => env::set_var(key, value),
                None => env::remove_var(key),
            }
        }
        let _ = self.administrator.query(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=$1 AND pid<>pg_backend_pid()",
            &[&self.name],
        );
        let _ = self
            .administrator
            .batch_execute(&format!("DROP DATABASE IF EXISTS {}", self.name));
        let _ = self
            .administrator
            .batch_execute(&format!("DROP ROLE IF EXISTS {}", self.role));
    }
}
