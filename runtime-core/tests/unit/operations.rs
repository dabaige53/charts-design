use super::*;

// @wu-test type=boundary | scope=database migration identity | protects=role text injects SQL or restores shared platform permissions
#[test]
fn database_migrations_keep_a_separate_runtime_identity() {
    for invalid in [
        "",
        "public",
        "anon",
        "authenticated",
        "service_role",
        "Owner",
        "0runtime",
        "runtime'; SELECT 1",
        "runtime-name",
    ] {
        assert!(adapt_migration("SELECT 1", invalid).is_err(), "{invalid}");
    }
    let directory = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .join("cloudbase/migrations");
    let mut source = String::new();
    for entry in fs::read_dir(directory).unwrap() {
        let path = entry.unwrap().path();
        if path.extension().is_some_and(|value| value == "sql") {
            source.push_str(&fs::read_to_string(path).unwrap());
        }
    }
    let migrated = adapt_migration(&source, "charts_runtime_test").unwrap();
    assert!(migrated.contains("session_user IS DISTINCT FROM 'charts_runtime_test'"));
    assert!(!migrated.contains("auth.role()"));
    assert!(!migrated.contains("service_role"));
    assert!(!migrated.contains(", anon, authenticated"));
}

// @wu-test type=boundary | scope=operator commands | protects=malformed maintenance arguments initiate storage or network operations
#[test]
fn invalid_maintenance_arguments_fail_before_side_effects() {
    for args in [
        vec!["cleanup", "extra"],
        vec!["cleanup-server", "extra"],
        vec!["migrate-neon", "extra"],
        vec!["migrate-cos"],
        vec!["healthcheck", "--wait-seconds", "NaN"],
    ] {
        let args: Vec<_> = args.into_iter().map(String::from).collect();
        assert_eq!(run(&args).unwrap().unwrap_err().code, "INVALID_ARGUMENT");
    }
    assert!(run(&["dashboard_get".into()]).is_none());
}
