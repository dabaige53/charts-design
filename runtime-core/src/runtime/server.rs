//! Author and publication HTTP hosts. All data work goes through the shared service.
use super::{
    assets,
    cloud::{self, CloudDatabase},
    error::{require, Error, Result},
    mcp::{Gateway, Lifetime},
    model,
    query::QueryRunner,
    service::{string, Service},
    versions::Versions,
    view::LocalView,
};
use axum::{
    body::Body,
    extract::{ConnectInfo, State},
    http::{HeaderMap, Method, Request, StatusCode},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    Router,
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use hmac::{Hmac, Mac};
use http_body_util::BodyExt;
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    future::Future,
    io::Write,
    net::{SocketAddr, TcpListener},
    path::{Component, Path, PathBuf},
    sync::{Arc, Mutex},
    time::Duration,
};
use subtle::ConstantTimeEq;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;
const MAX_BODY: usize = 16 * 1024 * 1024;
const READING: &[&str] = &[
    "dashboard_view",
    "dashboard_filter_options",
    "component_data",
    "query_inspect",
    "semantic_inspect",
    "dashboard_export",
    "dataset_export",
];
const PREVIEW: &[&str] = &[
    "dashboard_get",
    "dashboard_preview",
    "dashboard_list",
    "dashboard_refresh",
    "dashboard_view",
    "dashboard_filter_options",
    "component_data",
    "query_inspect",
    "semantic_inspect",
    "runtime_info",
    "runtime_keepalive",
    "runtime_report_error",
    "dashboard_export",
    "dashboard_export_read",
    "dataset_export",
];
const VIEW: &[&str] = &[
    "dashboard_get",
    "dashboard_view",
    "dashboard_refresh",
    "dashboard_filter_options",
    "component_data",
    "query_inspect",
    "semantic_inspect",
    "statistical_render",
    "dashboard_annotations",
    "dashboard_list",
    "dashboard_preview",
    "runtime_info",
    "runtime_keepalive",
    "runtime_report_error",
    "dashboard_export",
    "dashboard_export_read",
    "dataset_export",
    "legacy_render",
];
const EDIT: &[&str] = &[
    "dashboard_submit",
    "dashboard_publish",
    "dashboard_annotations_update",
    "dashboard_patch",
    "dashboard_edit_begin",
    "dashboard_edit_finish",
    "dashboard_checkpoint",
    "dashboard_validate",
    "dashboard_doctor",
    "dashboard_history",
    "dashboard_history_diff",
    "dashboard_restore",
    "dashboard_version_label",
    "runtime_diagnostics",
    "dashboard_export_site",
    "dashboard_version_status",
    "dashboard_version_get",
    "dashboard_version_publish",
    "dashboard_version_delete",
    "dashboard_version_delete_preview",
    "dashboard_version_delete_status",
    "dashboard_version_delete_retry",
    "dashboard_version_query",
    "dashboard_share_status",
    "dashboard_share_publish",
    "dashboard_share_delete",
    "dashboard_share_replace",
];
fn now() -> i64 {
    chrono::Utc::now().timestamp()
}
fn equal(a: &str, b: &str) -> bool {
    a.as_bytes().ct_eq(b.as_bytes()).into()
}
fn random() -> String {
    format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple())
}
fn encoded(value: &str) -> String {
    url::form_urlencoded::byte_serialize(value.as_bytes()).collect()
}
fn valid_project(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 64
        && name
            .bytes()
            .next()
            .is_some_and(|b| b.is_ascii_alphanumeric())
        && name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
}
pub fn absolute_path(path: &Path) -> Result<PathBuf> {
    let path = if path.is_absolute() {
        path.to_owned()
    } else {
        std::env::current_dir()?.join(path)
    };
    let mut normalized = PathBuf::new();
    for part in path.components() {
        match part {
            Component::ParentDir => {
                normalized.pop();
            }
            Component::CurDir => {}
            part => normalized.push(part.as_os_str()),
        }
    }
    let mut ancestor = normalized.clone();
    let mut missing = Vec::new();
    while !ancestor.exists() {
        missing.push(
            ancestor
                .file_name()
                .ok_or_else(|| Error::new("INVALID_PATH", "Invalid path"))?
                .to_os_string(),
        );
        require(ancestor.pop(), "Invalid path", "INVALID_PATH")?;
    }
    let mut result = ancestor.canonicalize()?;
    for part in missing.into_iter().rev() {
        result.push(part);
    }
    Ok(result)
}
fn load_secret(path: &Path) -> Result<Vec<u8>> {
    if let Ok(secret) = fs::read(path) {
        return Ok(secret);
    }
    fs::create_dir_all(path.parent().unwrap())?;
    let mut temp = tempfile::NamedTempFile::new_in(path.parent().unwrap())?;
    temp.write_all(random().as_bytes())?;
    temp.as_file().sync_all()?;
    match fs::hard_link(temp.path(), path) {
        Ok(()) => {}
        Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {}
        Err(e) => return Err(e.into()),
    }
    Ok(fs::read(path)?)
}
#[derive(Clone)]
pub struct Signer(Vec<u8>);
impl Signer {
    pub fn new(secret: Vec<u8>) -> Result<Self> {
        require(
            secret.len() >= 32,
            "The signing secret needs at least 32 bytes",
            "INVALID_CONFIG",
        )?;
        Ok(Self(secret))
    }
    fn mac(&self, body: &str) -> Vec<u8> {
        let mut mac = Hmac::<Sha256>::new_from_slice(&self.0).expect("HMAC accepts any key length");
        mac.update(b"charts-design.v1.");
        mac.update(body.as_bytes());
        mac.finalize().into_bytes().to_vec()
    }
    pub fn sign(&self, payload: &Value) -> Result<String> {
        let canonical = super::serialization::canonical_json(payload)?;
        let mut ascii = String::new();
        for c in canonical.chars() {
            if c.is_ascii() {
                ascii.push(c)
            } else {
                for unit in c.encode_utf16(&mut [0; 2]) {
                    ascii.push_str(&format!("\\u{unit:04x}"));
                }
            }
        }
        let body = URL_SAFE_NO_PAD.encode(ascii.as_bytes());
        Ok(format!(
            "{}.{}",
            body,
            URL_SAFE_NO_PAD.encode(self.mac(&body))
        ))
    }
    pub fn verify(&self, token: &str, kind: &str) -> Option<Value> {
        if token.len() > 4096 {
            return None;
        }
        let (body, mac) = token.split_once('.')?;
        let bytes = URL_SAFE_NO_PAD.decode(mac).ok()?;
        if !bool::from(self.mac(body).ct_eq(&bytes)) {
            return None;
        }
        let value: Value = serde_json::from_slice(&URL_SAFE_NO_PAD.decode(body).ok()?).ok()?;
        if value["k"] != kind || value["exp"].as_i64()? < now() {
            return None;
        }
        Some(value)
    }
}
#[derive(Clone)]
pub struct Settings {
    pub workspace: PathBuf,
    pub runtime: PathBuf,
    pub host: String,
    pub port: u16,
    pub public_url: String,
    pub base: String,
    pub tokens: Vec<String>,
    pub secret: Vec<u8>,
    pub share_hours: f64,
    pub default_project: String,
    pub sources: Option<PathBuf>,
    pub stateless: bool,
    pub allowed_hosts: Vec<String>,
    pub insecure: bool,
    pub role: String,
    pub guard_hosts: bool,
    pub forwarded_allow_ips: String,
}
impl Settings {
    pub fn from_options(args: &Value) -> Result<Self> {
        let get = |key: &str, env: &str, default: &str| {
            args[key]
                .as_str()
                .filter(|v| !v.is_empty())
                .map(String::from)
                .or_else(|| std::env::var(env).ok().filter(|v| !v.is_empty()))
                .unwrap_or_else(|| default.into())
        };
        let workspace = get("workspace", "CHARTS_WORKSPACE", "");
        require(
            !workspace.is_empty(),
            "Choose --workspace or CHARTS_WORKSPACE",
            "INVALID_CONFIG",
        )?;
        let workspace = absolute_path(Path::new(&workspace))?;
        let runtime = get(
            "runtime_root",
            "CHARTS_RUNTIME_ROOT",
            &workspace.join(".runtime").to_string_lossy(),
        );
        let runtime = absolute_path(Path::new(&runtime))?;
        let host = get("host", "CHARTS_HOST", "127.0.0.1");
        let port = args["port"]
            .as_u64()
            .map(|v| v.to_string())
            .unwrap_or_else(|| get("port", "CHARTS_PORT", "8000"))
            .parse::<u16>()
            .map_err(|_| Error::new("INVALID_CONFIG", "Invalid port"))?;
        let public = get("public_url", "CHARTS_PUBLIC_URL", "");
        let explicit = !public.is_empty();
        let public_url = if explicit {
            public.trim_end_matches('/').to_owned()
        } else {
            format!(
                "http://{}:{port}",
                if ["0.0.0.0", "::", ""].contains(&host.as_str()) {
                    "127.0.0.1"
                } else {
                    &host
                }
            )
        };
        let url = url::Url::parse(&public_url)
            .map_err(|_| Error::new("INVALID_CONFIG", "public URL must be absolute http(s)"))?;
        require(
            ["http", "https"].contains(&url.scheme())
                && url.host_str().is_some()
                && url.username().is_empty()
                && url.password().is_none()
                && url.query().is_none()
                && url.fragment().is_none(),
            "Invalid public URL",
            "INVALID_CONFIG",
        )?;
        let mut tokens: Vec<String> = args["token"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(Value::as_str)
            .map(String::from)
            .collect();
        tokens.extend(
            std::env::var("CHARTS_SERVER_TOKENS")
                .unwrap_or_default()
                .split(',')
                .map(str::trim)
                .filter(|v| !v.is_empty())
                .map(String::from),
        );
        let token_file = get("token_file", "CHARTS_SERVER_TOKEN_FILE", "");
        if !token_file.is_empty() {
            tokens.extend(
                fs::read_to_string(token_file)?
                    .lines()
                    .map(str::trim)
                    .filter(|v| !v.is_empty() && !v.starts_with('#'))
                    .map(String::from),
            );
        }
        tokens.sort();
        tokens.dedup();
        for token in &tokens {
            require(
                token.len() >= 16 && !token.contains(['\r', '\n']),
                "Bearer tokens need at least 16 characters",
                "INVALID_CONFIG",
            )?;
        }
        let insecure = args["insecure_no_auth"] == true;
        require(
            !insecure || ["127.0.0.1", "localhost", "::1"].contains(&host.as_str()),
            "--insecure-no-auth requires loopback",
            "INVALID_CONFIG",
        )?;
        require(
            !tokens.is_empty() || insecure,
            "Configure CHARTS_SERVER_TOKENS or --token",
            "INVALID_CONFIG",
        )?;
        let backend = std::env::var("CHARTS_STORAGE_BACKEND").unwrap_or_default();
        let role = get(
            "role",
            "CHARTS_SERVER_ROLE",
            if ["cloudbase", "cloudflare"].contains(&backend.as_str()) {
                "sharing"
            } else {
                "workspace"
            },
        );
        require(
            ["workspace", "sharing"].contains(&role.as_str())
                && !(role == "workspace"
                    && ["cloudbase", "cloudflare"].contains(&backend.as_str())),
            "CloudBase and Cloudflare run in the sharing role",
            "INVALID_CONFIG",
        )?;
        let supplied_secret = get("secret", "CHARTS_SERVER_SECRET", "");
        require(
            !cloud::cloud_enabled()? || !supplied_secret.is_empty(),
            "Cloud storage requires CHARTS_SERVER_SECRET",
            "INVALID_CONFIG",
        )?;
        let secret = if supplied_secret.is_empty() {
            load_secret(&runtime.join("server-secret"))?
        } else {
            supplied_secret.into_bytes()
        };
        require(
            secret.len() >= 32,
            "Signing secret requires 32 bytes",
            "INVALID_CONFIG",
        )?;
        let share_hours = args["share_ttl_hours"].as_f64().unwrap_or(
            get("share_ttl_hours", "CHARTS_SHARE_TTL_HOURS", "168")
                .parse()
                .map_err(|_| Error::new("INVALID_CONFIG", "Invalid share lifetime"))?,
        );
        require(
            share_hours.is_finite() && share_hours > 0.0 && share_hours <= 8784.0,
            "Share lifetime must be at most one year",
            "INVALID_CONFIG",
        )?;
        let default_project = get("default_project", "CHARTS_DEFAULT_PROJECT", "default");
        require(
            valid_project(&default_project),
            "Invalid default project",
            "INVALID_CONFIG",
        )?;
        let allowed_hosts: Vec<String> = if let Some(hosts) = args["allowed_host"].as_array() {
            hosts
                .iter()
                .filter_map(Value::as_str)
                .map(String::from)
                .collect()
        } else {
            get("allowed_host", "CHARTS_ALLOWED_HOSTS", "")
                .split(',')
                .map(str::trim)
                .filter(|v| !v.is_empty())
                .map(String::from)
                .collect()
        };
        let guard_hosts = explicit || !allowed_hosts.is_empty() || insecure;
        let sources = get("sources", "CHARTS_SOURCES", "");
        let base = url.path().trim_end_matches('/').to_owned();
        Ok(Self {
            workspace,
            runtime,
            host,
            port,
            public_url,
            base,
            tokens,
            secret,
            share_hours,
            default_project,
            sources: if sources.is_empty() {
                None
            } else {
                Some(PathBuf::from(sources))
            },
            stateless: args["stateless"] == true
                || !get("stateless", "CHARTS_STATELESS", "").is_empty()
                || cloud::cloud_enabled()?,
            allowed_hosts,
            insecure,
            role,
            guard_hosts,
            forwarded_allow_ips: get(
                "forwarded_allow_ips",
                "CHARTS_FORWARDED_ALLOW_IPS",
                "127.0.0.1",
            ),
        })
    }
    fn trusted_peer(&self, peer: &str) -> bool {
        self.forwarded_allow_ips
            .split(',')
            .map(str::trim)
            .any(|entry| {
                entry == "*"
                    || entry == peer
                    || entry.parse::<ipnet::IpNet>().is_ok_and(|network| {
                        peer.parse::<std::net::IpAddr>()
                            .is_ok_and(|address| network.contains(&address))
                    })
            })
    }
    fn client_ip(&self, peer: &str, headers: &HeaderMap) -> String {
        if self.trusted_peer(peer) {
            if let Some(value) = headers
                .get("x-forwarded-for")
                .and_then(|value| value.to_str().ok())
            {
                let chain: Vec<_> = value.split(',').map(str::trim).collect();
                if chain.len() <= 32
                    && chain
                        .iter()
                        .all(|value| value.parse::<std::net::IpAddr>().is_ok())
                {
                    if let Some(client) = chain
                        .iter()
                        .rev()
                        .find(|value| !self.trusted_peer(value))
                        .or(chain.first())
                    {
                        return client.to_string();
                    }
                }
            }
        }
        peer.to_owned()
    }
    fn host_guard(&self, headers: &HeaderMap) -> Result<()> {
        if !self.guard_hosts {
            return Ok(());
        }
        let url = url::Url::parse(&self.public_url).unwrap();
        let authority = &url[url::Position::BeforeHost..url::Position::AfterPort];
        let mut hosts = self.allowed_hosts.clone();
        hosts.extend([
            authority.into(),
            format!("127.0.0.1:{}", self.port),
            format!("localhost:{}", self.port),
            format!("{}:{}", self.host, self.port),
        ]);
        let host = header(headers, "host");
        require(
            hosts.iter().any(|h| h == host),
            "Unexpected Host header",
            "INVALID_HOST",
        )
        .map_err(|e| e.with_status(403))?;
        let origin = header(headers, "origin");
        let mut origins = vec![
            url.origin().ascii_serialization(),
            format!("http://127.0.0.1:{}", self.port),
            format!("http://localhost:{}", self.port),
        ];
        origins.extend(
            self.allowed_hosts
                .iter()
                .map(|host| format!("https://{host}")),
        );
        require(
            origin.is_empty() || origins.iter().any(|allowed| allowed == origin),
            "Cross-origin access is disabled",
            "INVALID_ORIGIN",
        )
        .map_err(|e| e.with_status(403))
    }
}
#[derive(Clone)]
struct Principal {
    admin: bool,
    edit: bool,
    primary: Option<String>,
    boards: Option<BTreeSet<String>>,
    can_annotate: bool,
}
#[derive(Clone)]
struct ProjectPrincipal {
    project: String,
    principal: Principal,
}
impl Principal {
    fn board(&self, board: &str) -> Result<()> {
        model::check_identifier(board)?;
        require(
            self.boards.as_ref().is_none_or(|set| set.contains(board)),
            "This link is limited to another dashboard",
            "FORBIDDEN",
        )
        .map_err(|e| e.with_status(403))
    }
}
pub struct RemoteServer {
    pub settings: Settings,
    pub signer: Signer,
    services: Mutex<BTreeMap<String, Arc<Service>>>,
    queries: Option<QueryRunner>,
    database: Option<CloudDatabase>,
    pub shares: Option<super::shares::CloudShares>,
    attempts: Mutex<BTreeMap<(String, String), (usize, i64)>>,
}
impl RemoteServer {
    pub fn new(settings: Settings) -> Result<Self> {
        fs::create_dir_all(&settings.runtime)?;
        let signer = Signer::new(settings.secret.clone())?;
        let shares = if settings.role == "sharing" {
            Some(super::shares::CloudShares::from_environment(Some(
                &settings.public_url,
            ))?)
        } else {
            None
        };
        let database = if settings.role == "workspace" && cloud::cloud_enabled()? {
            Some(CloudDatabase::new()?)
        } else {
            None
        };
        let queries = if settings.role == "workspace" {
            fs::create_dir_all(&settings.workspace)?;
            Some(QueryRunner::new(settings.sources.as_deref())?)
        } else {
            None
        };
        if database.is_none() && settings.role == "workspace" {
            Connection::open(settings.runtime.join("server-state.sqlite3"))?.execute_batch("CREATE TABLE IF NOT EXISTS share_generations(project TEXT,dashboard TEXT,generation INTEGER,PRIMARY KEY(project,dashboard));")?;
        }
        Ok(Self {
            settings,
            signer,
            services: Mutex::new(BTreeMap::new()),
            queries,
            database,
            shares,
            attempts: Mutex::new(BTreeMap::new()),
        })
    }
    fn admin(&self, token: &str) -> bool {
        let mut yes = false;
        for candidate in &self.settings.tokens {
            yes |= equal(token, candidate);
        }
        yes
    }
    fn author(&self, headers: &HeaderMap) -> Result<()> {
        require(
            self.settings.insecure || self.admin(bearer(headers)),
            "Send Authorization: Bearer <server token>",
            "UNAUTHORIZED",
        )
        .map_err(|e| e.with_status(401))
    }
    fn project_name(&self, value: Option<&str>) -> Result<String> {
        let value = value.unwrap_or(&self.settings.default_project);
        let name = if Path::new(value).is_absolute() {
            let path = absolute_path(Path::new(value))?;
            require(
                path.parent() == Some(self.settings.workspace.as_path()),
                "Project is outside server workspace",
                "PROJECT_OUTSIDE_WORKSPACE",
            )?;
            path.file_name().unwrap().to_string_lossy().to_string()
        } else {
            value.into()
        };
        require(
            valid_project(&name),
            "projectRoot must be a project name",
            "INVALID_PROJECT",
        )?;
        Ok(name)
    }
    fn exists(&self, name: &str) -> Result<bool> {
        if !valid_project(name) {
            return Ok(false);
        }
        if let Some(db) = &self.database {
            return Ok(db
                .call("projects", "", &json!({}))?
                .as_array()
                .is_some_and(|v| v.iter().any(|v| v == name)));
        }
        let path = absolute_path(&self.settings.workspace.join(name))?;
        Ok(path.parent() == Some(self.settings.workspace.as_path())
            && path.join("charts-project.json").is_file())
    }
    fn names(&self) -> Result<Vec<String>> {
        if let Some(db) = &self.database {
            return db
                .call("projects", "", &json!({}))?
                .as_array()
                .ok_or_else(|| Error::new("CLOUD_DATABASE_ERROR", "Invalid project listing"))?
                .iter()
                .map(|v| {
                    v.as_str()
                        .map(String::from)
                        .ok_or_else(|| Error::new("CLOUD_DATABASE_ERROR", "Invalid project name"))
                })
                .collect();
        }
        let mut names = Vec::new();
        for entry in fs::read_dir(&self.settings.workspace)? {
            let name = entry?.file_name().to_string_lossy().into_owned();
            if self.exists(&name)? {
                names.push(name);
            }
        }
        names.sort();
        Ok(names)
    }
    pub fn service(&self, name: &str) -> Result<Arc<Service>> {
        let name = self.project_name(Some(name))?;
        let path = absolute_path(&self.settings.workspace.join(&name))?;
        require(
            path.parent() == Some(self.settings.workspace.as_path()),
            "Project is outside workspace",
            "PROJECT_OUTSIDE_WORKSPACE",
        )?;
        let mut services = self
            .services
            .lock()
            .map_err(|_| Error::new("INTERNAL_ERROR", "Project lock unavailable"))?;
        if let Some(service) = services.get(&name) {
            return Ok(service.clone());
        }
        let mut service = Service::new(
            &self.settings.runtime.join("projects").join(&name),
            None,
            Some(&path),
        )?;
        service.project_name = name.clone();
        service.queries = self
            .queries
            .as_ref()
            .ok_or_else(|| Error::new("FORBIDDEN", "Sharing hosts have no author workspace"))?
            .clone();
        service.views = LocalView::new(service.store.data.clone(), Some(service.queries.clone()));
        let service = Arc::new(service);
        services.insert(name, service.clone());
        Ok(service)
    }
    fn generation(&self, project: &str, board: &str, revoke: bool) -> Result<i64> {
        if let Some(db) = &self.database {
            return db
                .call(
                    if revoke { "revoke" } else { "generation" },
                    project,
                    &json!({"board":board}),
                )?
                .as_i64()
                .ok_or_else(|| Error::new("CLOUD_DATABASE_ERROR", "Invalid generation"));
        }
        let db = Connection::open(self.settings.runtime.join("server-state.sqlite3"))?;
        db.busy_timeout(Duration::from_secs(10))?;
        if revoke {
            return Ok(db.query_row("INSERT INTO share_generations VALUES(?,?,1) ON CONFLICT(project,dashboard) DO UPDATE SET generation=generation+1 RETURNING generation",params![project,board],|r|r.get(0))?);
        }
        let value = db
            .query_row(
                "SELECT generation FROM share_generations WHERE project=? AND dashboard=?",
                params![project, board],
                |r| r.get(0),
            )
            .optional()?
            .unwrap_or(0);
        Ok(value)
    }
    fn principal(&self, token: &str, project: &str) -> Result<Principal> {
        if self.admin(token) || (self.settings.insecure && token.is_empty()) {
            return Ok(Principal {
                admin: true,
                edit: true,
                primary: None,
                boards: None,
                can_annotate: true,
            });
        }
        let value = self.signer.verify(token, "share").ok_or_else(|| {
            Error::new(
                "UNAUTHORIZED",
                "链接已失效或缺少访问令牌，请重新打开分享链接",
            )
            .with_status(401)
        })?;
        require(value["p"] == project, "访问令牌失效", "UNAUTHORIZED")
            .map_err(|e| e.with_status(401))?;
        let board = string(&value, "d")?;
        let fallback = json!({board:value["g"]});
        let pages = value
            .get("pages")
            .unwrap_or(&fallback)
            .as_object()
            .ok_or_else(|| Error::new("UNAUTHORIZED", "Invalid page scope").with_status(401))?;
        require(
            pages.get(board) == Some(&value["g"]),
            "Invalid page scope",
            "UNAUTHORIZED",
        )
        .map_err(|e| e.with_status(401))?;
        for (page, generation) in pages {
            require(
                generation.as_i64() == Some(self.generation(project, page, false)?),
                "Share link has been revoked",
                "UNAUTHORIZED",
            )
            .map_err(|e| e.with_status(401))?;
        }
        let edit = value["a"] == "edit";
        Ok(Principal {
            admin: false,
            edit,
            primary: Some(board.into()),
            boards: Some(pages.keys().cloned().collect()),
            can_annotate: edit || value["annotationMode"] == "annotate",
        })
    }
    fn request_principal(&self, input: &HttpInput, project: &str) -> Result<Principal> {
        if let Some(verified) = input.verified.as_ref().filter(|v| v.project == project) {
            return Ok(verified.principal.clone());
        }
        self.principal(bearer(&input.headers), project)
    }
    pub fn share(&self, project: &str, args: &Value) -> Result<Value> {
        let service = self.service(project)?;
        let board = string(args, "dashboardId")?;
        service.store.revision(board)?;
        let access = args["access"].as_str().unwrap_or("view");
        let mode = args["annotationMode"].as_str().unwrap_or("view");
        require(
            ["view", "edit"].contains(&access) && ["view", "annotate"].contains(&mode),
            "Invalid share access",
            "INVALID_ARGUMENT",
        )?;
        let hours = args["expiresInHours"]
            .as_f64()
            .unwrap_or(self.settings.share_hours);
        require(
            hours.is_finite() && hours > 0.0 && hours <= 8784.0,
            "Invalid share lifetime",
            "INVALID_ARGUMENT",
        )?;
        let exp = now() + (hours * 3600.0) as i64;
        let mut pages = serde_json::Map::new();
        pages.insert(board.into(), json!(self.generation(project, board, false)?));
        if let Some(additional) = args.get("dashboardIds") {
            for value in additional
                .as_array()
                .ok_or_else(|| Error::new("INVALID_ARGUMENT", "dashboardIds must be an array"))?
            {
                let page = value
                    .as_str()
                    .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid page ID"))?;
                require(
                    !pages.contains_key(page),
                    "Duplicate page",
                    "INVALID_ARGUMENT",
                )?;
                service.store.revision(page)?;
                pages.insert(page.into(), json!(self.generation(project, page, false)?));
            }
        }
        let token=self.signer.sign(&json!({"k":"share","p":project,"d":board,"a":access,"exp":exp,"g":pages[board],"pages":pages,"annotationMode":mode,"n":&random()[..8]}))?;
        Ok(
            json!({"dashboardId":board,"url":format!("{}/{}/{}/{}#token={token}",self.settings.public_url,access,encoded(project),encoded(board)),"access":access,"annotationMode":mode,"expiresAt":chrono::DateTime::from_timestamp(exp,0).unwrap().to_rfc3339_opts(chrono::SecondsFormat::Secs,false)}),
        )
    }
    fn file_link(&self, project: &str, path: &str) -> Result<Value> {
        let root = absolute_path(&self.settings.workspace.join(project))?;
        let target = absolute_path(Path::new(path))?;
        if !target.starts_with(&root) || !target.is_file() {
            return Ok(Value::Null);
        }
        let token=self.signer.sign(&json!({"k":"file","p":project,"f":target.strip_prefix(root).unwrap().to_string_lossy().replace('\\',"/"),"exp":now()+86400}))?;
        Ok(json!(format!("{}/files/{token}", self.settings.public_url)))
    }
    fn decorate_result(
        &self,
        name: &str,
        mut result: Value,
        service: &Arc<Service>,
        browser: bool,
    ) -> Result<Value> {
        let project = &service.project_name;
        result["projectRoot"] = json!(project);
        if browser && name == "dashboard_preview" && result["document"].is_object() {
            let board = &result["document"]["id"];
            let links = json!({"editUrl":self.share(project,&json!({"dashboardId":board,"access":"edit"}))?["url"],"viewUrl":self.share(project,&json!({"dashboardId":board,"annotationMode":"annotate"}))?["url"]});
            result["browserLinks"] = links.clone();
            result["document"]["browserLinks"] = links;
        }
        if let Some(path) = result["export"]["path"].as_str().map(String::from) {
            result["export"]["downloadUrl"] = self.file_link(project, &path)?;
            if let Some(path) = result["export"]["siteArchive"].as_str().map(String::from) {
                result["export"]["siteDownloadUrl"] = self.file_link(project, &path)?;
            }
        }
        Ok(result)
    }
    fn call_viewer(
        &self,
        project: &str,
        name: &str,
        mut args: Value,
        principal: &Principal,
    ) -> Result<Value> {
        require(
            VIEW.contains(&name) || (principal.edit && EDIT.contains(&name)),
            "This link does not allow that operation",
            "FORBIDDEN",
        )
        .map_err(|e| e.with_status(403))?;
        require(
            args.is_object(),
            "Tool arguments must be an object",
            "INVALID_REQUEST",
        )?;
        args.as_object_mut().unwrap().remove("projectRoot");
        let service = self.service(project)?;
        if let Some(boards) = &principal.boards {
            if name == "dashboard_list" {
                let mut result = service.call(name, &json!({}))?;
                result["dashboards"]
                    .as_array_mut()
                    .unwrap()
                    .retain(|v| v["id"].as_str().is_some_and(|id| boards.contains(id)));
                result["projectRoot"] = json!(project);
                return Ok(result);
            }
            if args.get("dashboardId").is_some()
                || super::contract::tool_schema(name)
                    .is_some_and(|s| s["properties"].get("dashboardId").is_some())
            {
                let board = args["dashboardId"]
                    .as_str()
                    .or(principal.primary.as_deref())
                    .ok_or_else(|| Error::new("FORBIDDEN", "Missing page scope"))?;
                principal.board(board)?;
                args["dashboardId"] = json!(board);
            }
        }
        if !principal.edit && READING.contains(&name) {
            pin_reader_revision(&service, &mut args)?;
        }
        let actual = if name == "dashboard_get" && !principal.edit {
            "dashboard_preview"
        } else {
            name
        };
        let mut result =
            self.decorate_result(name, service.call(actual, &args)?, &service, false)?;
        if service.store.cos_enabled {
            for field in ["document", "version"] {
                if result[field].is_object() {
                    let doc = result[field].clone();
                    let prefix = format!(
                        "{}/api/v1/p/{}/content/{}/{}/",
                        self.settings.base,
                        encoded(project),
                        encoded(string(&doc, "id")?),
                        doc["revision"]
                    );
                    result[field] = super::shares::web_document(
                        &service.store,
                        &doc,
                        |object, file| format!("{prefix}{object}/{file}"),
                        principal.edit && field != "version",
                        true,
                    )?;
                }
            }
        }
        if !principal.admin {
            if name == "runtime_info" {
                result.as_object_mut().unwrap().retain(|key, _| {
                    [
                        "version",
                        "uiBuildId",
                        "backendBuildId",
                        "dashboardRevision",
                        "projectRoot",
                    ]
                    .contains(&key.as_str())
                });
            }
            if let Some(export) = result["export"].as_object_mut() {
                for key in ["path", "directory", "siteArchive", "publishDirectory"] {
                    export.remove(key);
                }
            }
        }
        Ok(result)
    }
}
impl Gateway for RemoteServer {
    fn remote(&self) -> bool {
        true
    }
    fn resolve(&self, mut args: Value) -> Result<(Arc<Service>, Value)> {
        let project = args
            .as_object_mut()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Arguments must be an object"))?
            .remove("projectRoot");
        let name = self.project_name(
            project
                .as_ref()
                .map(|v| {
                    v.as_str().ok_or_else(|| {
                        Error::new("INVALID_PROJECT", "projectRoot must be a project name")
                    })
                })
                .transpose()?,
        )?;
        Ok((self.service(&name)?, args))
    }
    fn definitions(&self) -> Vec<Value> {
        let mut tools = super::contract::tool_definitions(true, true);
        tools.retain(|v| v["name"] != "dashboard_export_open");
        for(name,description,properties)in[("dashboard_share","Create an expiring browser link to a saved dashboard. Share only when requested; use dashboard_share_publish for independent keyed copies.",json!({"dashboardId":{"type":"string"},"dashboardIds":{"type":"array","items":{"type":"string"},"uniqueItems":true},"access":{"enum":["view","edit"]},"annotationMode":{"enum":["view","annotate"]},"expiresInHours":{"type":"number","minimum":1,"maximum":8784},"projectRoot":{"type":"string"}})),("dashboard_share_revoke","Revoke previously issued browser links to a dashboard without deleting content.",json!({"dashboardId":{"type":"string"},"projectRoot":{"type":"string"}}))]{tools.push(json!({"name":name,"description":description,"inputSchema":{"type":"object","properties":properties,"required":["dashboardId"],"additionalProperties":false},"annotations":{"readOnlyHint":false,"destructiveHint":name.ends_with("revoke"),"idempotentHint":false,"openWorldHint":false},"_meta":{"ui":{"visibility":["app"]}}}));}
        tools
    }
    fn handle(&self, name: &str, args: &Value, service: &Arc<Service>) -> Result<Option<Value>> {
        match name {
            "dashboard_share" => Ok(Some(self.share(&service.project_name, args)?)),
            "dashboard_share_revoke" => {
                let board = string(args, "dashboardId")?;
                service.store.revision(board)?;
                Ok(Some(
                    json!({"dashboardId":board,"revoked":true,"generation":self.generation(&service.project_name,board,true)?}),
                ))
            }
            _ => Ok(None),
        }
    }
    fn decorate(
        &self,
        name: &str,
        _args: &Value,
        result: Value,
        service: &Arc<Service>,
    ) -> Result<Value> {
        self.decorate_result(name, result, service, true)
    }
}
fn header<'a>(headers: &'a HeaderMap, name: &str) -> &'a str {
    headers
        .get(name)
        .and_then(|h| h.to_str().ok())
        .unwrap_or("")
}
fn bearer(headers: &HeaderMap) -> &str {
    let value = header(headers, "authorization");
    if value
        .get(..7)
        .is_some_and(|v| v.eq_ignore_ascii_case("bearer "))
    {
        value[7..].trim()
    } else {
        ""
    }
}
fn pin_reader_revision(service: &Service, args: &mut Value) -> Result<()> {
    let revision = service
        .store
        .display_revision(string(args, "dashboardId")?)?
        .ok_or_else(|| Error::new("NO_SAVED_VERSION", "暂无已保存版本"))?;
    require(
        args.get("expectedRevision").is_none_or(|v| v == revision),
        "请刷新已保存的看板版本",
        "REVISION_CONFLICT",
    )
    .map_err(|e| e.with_status(409))?;
    args["expectedRevision"] = json!(revision);
    Ok(())
}
pub fn annotation_response(
    service: &Service,
    board: &str,
    revision: Option<i64>,
    can_annotate: bool,
    can_manage: bool,
    payload: Option<&Value>,
) -> Result<Value> {
    model::check_identifier(board)?;
    require(
        service.project_root.is_some(),
        "Independent annotations require a project",
        "PROJECT_REQUIRED",
    )?;
    let doc = if let Some(revision) = revision {
        require(
            revision > 0,
            "revision must be a positive integer",
            "INVALID_ARGUMENT",
        )?;
        let draft = if can_manage {
            Some(service.store.get(board, false)?)
        } else {
            None
        };
        if draft.as_ref().is_some_and(|v| v["revision"] == revision) {
            draft.unwrap()
        } else {
            Versions::new(&service.store)?.read(board, revision)?
        }
    } else if can_manage {
        service.store.get(board, false)?
    } else {
        service.store.readable(board)?
    };
    if let Some(payload) = payload {
        require(
            can_annotate,
            "This page does not allow annotations",
            "FORBIDDEN",
        )
        .map_err(|e| e.with_status(403))?;
        let mut result = if let Some(note) = payload.get("append") {
            require(
                note.is_object()
                    && payload.get("expectedAnnotations").is_none()
                    && payload.get("annotations").is_none(),
                "Send append or a replacement list",
                "INVALID_ARGUMENT",
            )?;
            let name = payload
                .get("authorName")
                .map(|v| {
                    v.as_str()
                        .ok_or_else(|| Error::new("INVALID_ARGUMENT", "authorName must be text"))
                })
                .transpose()?
                .unwrap_or("");
            require(
                name.chars().count() <= 80,
                "authorName must contain at most 80 characters",
                "INVALID_ARGUMENT",
            )?;
            let mut note = note.clone();
            note["author"] = json!({"name":if name.trim().is_empty(){if can_manage{"作者"}else{"访客"}}else{name.trim()},"verified":false});
            service.store.append_annotation(board, &note, Some(&doc))?
        } else {
            require(
                can_manage,
                "This preview can add annotations but cannot manage them",
                "FORBIDDEN",
            )
            .map_err(|e| e.with_status(403))?;
            require(
                payload["expectedAnnotations"].is_array(),
                "expectedAnnotations must be an array",
                "INVALID_ARGUMENT",
            )?;
            let expected = if let Some(value) = payload.get("expectedRevision") {
                value.as_i64().filter(|v| *v > 0).ok_or_else(|| {
                    Error::new("INVALID_ARGUMENT", "expectedRevision must be positive")
                })?
            } else {
                service.store.revision(board)?
            };
            service.store.update_annotations(
                board,
                expected,
                &payload["expectedAnnotations"],
                &payload["annotations"],
            )?
        };
        result["targetRevision"] = doc["revision"].clone();
        return Ok(result);
    }
    let mut result = service.call(
        "dashboard_annotations",
        &json!({"dashboardId":board,"includeTargets":false}),
    )?;
    let mut targets = serde_json::Map::new();
    for note in result["annotations"].as_array().into_iter().flatten() {
        let component = note["componentId"].as_str();
        let mut target = json!({"scope":note["anchor"]["scope"].as_str().unwrap_or(if component.is_some(){"component"}else{"page"})});
        if let Some(id) = component {
            let item = doc["manifest"]["components"].get(id);
            target["sourcePath"] = json!(format!("manifest.components.{id}"));
            target["componentExists"] = json!(item.is_some());
            if let Some(item) = item {
                target["title"] = item.get("title").cloned().unwrap_or(json!(""));
                target["kind"] = item["kind"].clone();
            }
        } else {
            target["sourcePath"] = json!(if matches!(
                doc["manifest"]["viewMode"].as_str(),
                Some("report" | "filtered-report")
            ) {
                "manifest.report.markdown"
            } else {
                "manifest"
            });
        }
        targets.insert(string(note, "id")?.into(), target);
    }
    result["targetRevision"] = doc["revision"].clone();
    result["targets"] = Value::Object(targets);
    result["targetsResolved"] = json!(true);
    result["canRead"] = json!(true);
    result["canAnnotate"] = json!(can_annotate);
    result["canManageAnnotations"] = json!(can_manage);
    result["author"] = json!({"name":if can_manage{"作者"}else{"访客"},"verified":false});
    Ok(result)
}
struct HttpInput {
    method: Method,
    path: String,
    query: BTreeMap<String, String>,
    headers: HeaderMap,
    body: Vec<u8>,
    archive: Option<tempfile::NamedTempFile>,
    peer: String,
    verified: Option<ProjectPrincipal>,
}
impl HttpInput {
    fn json(&self) -> Result<Value> {
        require(
            header(&self.headers, "content-type")
                .split(';')
                .next()
                .unwrap_or("")
                .trim()
                == "application/json",
            "Use application/json",
            "CONTENT_TYPE",
        )
        .map_err(|e| e.with_status(415))?;
        let value: Value = serde_json::from_slice(&self.body)
            .map_err(|_| Error::new("INVALID_REQUEST", "Body must contain valid JSON"))?;
        require(
            value.is_object(),
            "Body must be an object",
            "INVALID_REQUEST",
        )?;
        Ok(value)
    }
    fn revision(&self, payload: Option<&Value>) -> Result<Option<i64>> {
        if let Some(value) = payload.and_then(|p| p.get("revision")) {
            return value.as_i64().filter(|v| *v > 0).map(Some).ok_or_else(|| {
                Error::new("INVALID_ARGUMENT", "revision must be a positive integer")
            });
        }
        self.query
            .get("revision")
            .map(|v| {
                v.parse::<i64>()
                    .ok()
                    .filter(|v| *v > 0)
                    .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Invalid revision"))
            })
            .transpose()
    }
    fn cookie(&self, name: &str) -> &str {
        header(&self.headers, "cookie")
            .split(';')
            .find_map(|part| {
                part.trim()
                    .split_once('=')
                    .filter(|(key, _)| *key == name)
                    .map(|(_, v)| v)
            })
            .unwrap_or("")
    }
}
enum Payload {
    Bytes(Vec<u8>),
    File(fs::File),
}
struct HttpOutput {
    status: u16,
    kind: String,
    headers: Vec<(String, String)>,
    payload: Payload,
}
impl HttpOutput {
    fn raw(raw: Vec<u8>, kind: &str) -> Self {
        Self {
            status: 200,
            kind: kind.into(),
            headers: Vec::new(),
            payload: Payload::Bytes(raw),
        }
    }
    fn json(value: &Value) -> Result<Self> {
        Ok(Self::raw(serde_json::to_vec(value)?, "application/json"))
    }
    fn html(value: String) -> Self {
        Self::raw(value.into_bytes(), "text/html; charset=utf-8")
    }
    fn with_header(mut self, key: &str, value: impl Into<String>) -> Self {
        self.headers.push((key.into(), value.into()));
        self
    }
    fn status(mut self, status: u16) -> Self {
        self.status = status;
        self
    }
    fn failure(error: Error) -> Self {
        let status = if error.status != 400 {
            error.status
        } else {
            match error.code.as_str() {
                "FORBIDDEN" => 403,
                "UNAUTHORIZED" | "INVALID_ACCESS_KEY" => 401,
                "NOT_FOUND" | "LINK_EXPIRED" => 404,
                "SHARE_EXPIRED" | "SHARE_UNAVAILABLE" => 410,
                "REVISION_CONFLICT" | "ANNOTATION_CONFLICT" | "ANNOTATION_LIMIT" => 409,
                "SHARE_RATE_LIMITED" => 429,
                _ => 400,
            }
        };
        Self::json(&error.json()).unwrap().status(status)
    }
    fn response(self, gzip: bool, head: bool) -> Response {
        let encoded = self
            .headers
            .iter()
            .any(|(key, _)| key == "Content-Encoding");
        let mut builder = axum::http::Response::builder()
            .status(self.status)
            .header("Content-Type", self.kind)
            .header("Cache-Control", "private, no-store")
            .header("X-Content-Type-Options", "nosniff")
            .header("Referrer-Policy", "no-referrer")
            .header("X-Frame-Options", "DENY")
            .header("Cross-Origin-Opener-Policy", "same-origin");
        for (k, v) in self.headers {
            if let (Ok(name), Ok(value), Some(headers)) = (
                axum::http::HeaderName::from_bytes(k.as_bytes()),
                axum::http::HeaderValue::from_str(&v),
                builder.headers_mut(),
            ) {
                headers.insert(name, value);
            }
        }
        let body = match self.payload {
            Payload::Bytes(mut bytes) => {
                if gzip && !encoded && bytes.len() > 1024 {
                    let mut encoder =
                        flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::new(5));
                    if encoder.write_all(&bytes).is_ok() {
                        if let Ok(compressed) = encoder.finish() {
                            bytes = compressed;
                            builder = builder
                                .header("Content-Encoding", "gzip")
                                .header("Vary", "Accept-Encoding");
                        }
                    }
                }
                builder = builder.header("Content-Length", bytes.len());
                if head {
                    Body::empty()
                } else {
                    Body::from(bytes)
                }
            }
            Payload::File(file) => {
                if let Ok(metadata) = file.metadata() {
                    builder = builder.header("Content-Length", metadata.len());
                }
                if head {
                    Body::empty()
                } else {
                    Body::from_stream(tokio_util::io::ReaderStream::new(
                        tokio::fs::File::from_std(file),
                    ))
                }
            }
        };
        builder
            .body(body)
            .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response())
    }
}

fn encoding_quality(headers: &HeaderMap, encoding: &str) -> f32 {
    header(headers, "accept-encoding")
        .split(',')
        .find_map(|entry| {
            let mut parts = entry.trim().split(';');
            if !parts.next()?.trim().eq_ignore_ascii_case(encoding) {
                return None;
            }
            Some(
                parts
                    .find_map(|part| part.trim().strip_prefix("q="))
                    .map_or(1.0, |quality| quality.parse::<f32>().unwrap_or(0.0)),
            )
        })
        .unwrap_or(0.0)
}

fn versioned_asset(input: &HttpInput, build: &str, name: &str) -> Result<HttpOutput> {
    let (path, kind) = assets::web_asset(build, name)?;
    let br = encoding_quality(&input.headers, "br");
    let gzip = encoding_quality(&input.headers, "gzip");
    let order = if br >= gzip {
        [(br, "br", "br"), (gzip, "gzip", "gz")]
    } else {
        [(gzip, "gzip", "gz"), (br, "br", "br")]
    };
    let output = |bytes| {
        HttpOutput::raw(bytes, kind)
            .with_header("Cache-Control", "public, max-age=31536000, immutable")
            .with_header("Vary", "Accept-Encoding")
    };
    for (quality, encoding, extension) in order {
        if quality > 0.0 {
            let compressed = path.with_extension(format!(
                "{}.{extension}",
                path.extension().unwrap().to_string_lossy()
            ));
            match fs::read(compressed) {
                Ok(bytes) => return Ok(output(bytes).with_header("Content-Encoding", encoding)),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
                Err(error) => return Err(error.into()),
            }
        }
    }
    Ok(output(fs::read(path)?))
}
async fn read_input(request: Request<Body>, upload: bool) -> Result<HttpInput> {
    let verified = request.extensions().get::<ProjectPrincipal>().cloned();
    let (peer, method, path, query, headers) = {
        let peer = request
            .extensions()
            .get::<ConnectInfo<SocketAddr>>()
            .map(|p| p.0.ip().to_string())
            .unwrap_or_else(|| "unknown".into());
        let query = url::form_urlencoded::parse(request.uri().query().unwrap_or("").as_bytes())
            .into_owned()
            .collect();
        (
            peer,
            request.method().clone(),
            request.uri().path().to_owned(),
            query,
            request.headers().clone(),
        )
    };
    let limit = if upload {
        256 * 1024 * 1024
    } else if path.starts_with("/s/") {
        if path.ends_with("/api/annotations") {
            40 * 1024
        } else {
            4096
        }
    } else {
        MAX_BODY
    };
    if let Some(value) = headers.get("content-length") {
        require(
            value
                .to_str()
                .ok()
                .and_then(|v| v.parse::<usize>().ok())
                .is_some_and(|v| v <= limit),
            "Request body is too large",
            "PAYLOAD_TOO_LARGE",
        )
        .map_err(|e| e.with_status(413))?;
    }
    let mut body = request.into_body();
    let mut bytes = Vec::new();
    let archive = if upload {
        Some(tempfile::NamedTempFile::new()?)
    } else {
        None
    };
    let mut file = archive
        .as_ref()
        .map(|temp| temp.reopen())
        .transpose()?
        .map(tokio::fs::File::from_std);
    let mut size = 0;
    while let Some(frame) = body.frame().await {
        let frame =
            frame.map_err(|_| Error::new("INVALID_REQUEST", "Failed to read request body"))?;
        if let Ok(data) = frame.into_data() {
            size += data.len();
            require(
                size <= limit,
                "Request body is too large",
                "PAYLOAD_TOO_LARGE",
            )
            .map_err(|e| e.with_status(413))?;
            if let Some(file) = &mut file {
                use tokio::io::AsyncWriteExt;
                file.write_all(&data).await?;
            } else {
                bytes.extend_from_slice(&data);
            }
        }
    }
    if let Some(file) = &mut file {
        use tokio::io::AsyncWriteExt;
        file.flush().await?;
    }
    Ok(HttpInput {
        method,
        path,
        query,
        headers,
        body: bytes,
        archive,
        peer,
        verified,
    })
}
struct LocalState {
    service: Arc<Service>,
    token: String,
    port: u16,
    lifetime: Lifetime,
}
impl LocalState {
    fn preview_token(&self, board: &str) -> Result<String> {
        model::check_identifier(board)?;
        let encoded = URL_SAFE_NO_PAD.encode(board.as_bytes());
        let mut mac = Hmac::<Sha256>::new_from_slice(self.token.as_bytes()).unwrap();
        mac.update(encoded.as_bytes());
        Ok(format!(
            "view.{encoded}.{}",
            hex::encode(mac.finalize().into_bytes())
        ))
    }
    fn browser_links(&self, board: &str) -> Result<Value> {
        self.service.store.revision(board)?;
        Ok(
            json!({"editUrl":format!("http://127.0.0.1:{}/edit/{}#token={}",self.port,encoded(board),self.token),"viewUrl":format!("http://127.0.0.1:{}/view/{}#token={}",self.port,encoded(board),self.preview_token(board)?)}),
        )
    }
    fn principal(&self, token: &str) -> Result<Principal> {
        if equal(token, &self.token) {
            return Ok(Principal {
                admin: true,
                edit: true,
                primary: None,
                boards: None,
                can_annotate: true,
            });
        }
        let parts: Vec<_> = token.split('.').collect();
        if parts.len() == 3 && parts[0] == "view" {
            if let Ok(raw) = URL_SAFE_NO_PAD.decode(parts[1]) {
                if let Ok(board) = String::from_utf8(raw) {
                    if self
                        .preview_token(&board)
                        .is_ok_and(|expected| equal(&expected, token))
                    {
                        return Ok(Principal {
                            admin: false,
                            edit: false,
                            primary: Some(board.clone()),
                            boards: Some(BTreeSet::from([board])),
                            can_annotate: true,
                        });
                    }
                }
            }
        }
        Err(Error::new(
            "UNAUTHORIZED",
            "Open the token-bearing URL printed by the local server",
        )
        .with_status(401))
    }
    fn handle(&self, input: &HttpInput) -> Result<HttpOutput> {
        let _activity = self.lifetime.activity();
        let allowed = [
            format!("127.0.0.1:{}", self.port),
            format!("localhost:{}", self.port),
        ];
        require(
            allowed.iter().any(|h| h == header(&input.headers, "host")),
            "Unexpected Host header",
            "INVALID_HOST",
        )
        .map_err(|e| e.with_status(403))?;
        let origin = header(&input.headers, "origin");
        require(
            origin.is_empty() || allowed.iter().any(|h| origin == format!("http://{h}")),
            "Cross-origin access is disabled",
            "INVALID_ORIGIN",
        )
        .map_err(|e| e.with_status(403))?;
        let path = input.path.as_str();
        let principal = if path.starts_with("/api/") {
            Some(self.principal(bearer(&input.headers))?)
        } else {
            None
        };
        if input.method == Method::GET || input.method == Method::HEAD {
            if path == "/health" {
                return HttpOutput::json(&json!({"ok":true}));
            }
            if let Some((build, name)) = path
                .strip_prefix("/assets/")
                .and_then(|path| path.split_once('/'))
            {
                return versioned_asset(input, build, name);
            }
            if path == "/" || path.starts_with("/edit/") || path.starts_with("/view/") {
                let board = path
                    .strip_prefix("/edit/")
                    .or_else(|| path.strip_prefix("/view/"));
                if let Some(board) = board {
                    self.service.store.revision(board)?;
                }
                let read_only = path.starts_with("/view/");
                let project = &self.service.project_root;
                let boot = json!({"projectRoot":project,"dashboardId":board,"readOnly":read_only,"annotationAccess":{"endpoint":"/api/annotations/{dashboardId}","canRead":project.is_some(),"canAnnotate":project.is_some(),"canManageAnnotations":project.is_some()&&!read_only,"scope":project.as_ref().map(|p|p.to_string_lossy().into_owned()).unwrap_or_else(||"legacy".into())},"browserLinksEndpoint":"/api/browser-links/{dashboardId}","publicationApiBase":"/api/publications/"});
                return Ok(HttpOutput::html(assets::render_web_html(
                    "",
                    self.lifetime.seconds(),
                    &boot,
                )?));
            }
            if let Some(board) = path.strip_prefix("/api/browser-links/") {
                let principal = principal.as_ref().unwrap();
                principal.board(board)?;
                let mut links = self.browser_links(board)?;
                if !principal.edit {
                    links.as_object_mut().unwrap().remove("editUrl");
                }
                return HttpOutput::json(&links);
            }
            if let Some(board) = path.strip_prefix("/api/annotations/") {
                let principal = principal.as_ref().unwrap();
                principal.board(board)?;
                return HttpOutput::json(&annotation_response(
                    &self.service,
                    board,
                    input.revision(None)?,
                    true,
                    principal.edit,
                    None,
                )?);
            }
            if let Some(board) = path.strip_prefix("/api/export/") {
                let principal = principal.as_ref().unwrap();
                principal.board(board)?;
                let doc = if !principal.edit && self.service.project_root.is_some() {
                    self.service.store.readable(board)?
                } else {
                    self.service.store.get(board, false)?
                };
                return Ok(HttpOutput::html(assets::export_document(
                    &self.service.store.hydrate(&doc)?,
                )?));
            }
            if let Some(id) = path
                .strip_prefix("/api/publications/")
                .and_then(|p| p.strip_suffix("/feedback"))
            {
                let principal = principal.as_ref().unwrap();
                require(principal.edit, "Author access is required", "FORBIDDEN")?;
                let board = input
                    .query
                    .get("dashboardId")
                    .ok_or_else(|| Error::new("INVALID_ARGUMENT", "dashboardId is required"))?;
                principal.board(board)?;
                return HttpOutput::json(
                    &super::local_shares::LocalShares::new(&self.service)?.feedback(board, id)?,
                );
            }
        }
        if input.method == Method::POST {
            let principal = principal
                .as_ref()
                .ok_or_else(|| Error::new("NOT_FOUND", "Unknown endpoint"))?;
            let mut args = input.json()?;
            if let Some(board) = path.strip_prefix("/api/annotations/") {
                principal.board(board)?;
                require(
                    args.get("dashboardId").is_none_or(|v| v == board),
                    "Dashboard does not match endpoint",
                    "FORBIDDEN",
                )?;
                return HttpOutput::json(&annotation_response(
                    &self.service,
                    board,
                    input.revision(Some(&args))?,
                    true,
                    principal.edit,
                    Some(&args),
                )?);
            }
            if let Some(mut name) = path.strip_prefix("/api/tools/") {
                args.as_object_mut().unwrap().remove("projectRoot");
                if !principal.edit {
                    require(
                        PREVIEW.contains(&name),
                        "This preview cannot change content or versions",
                        "FORBIDDEN",
                    )
                    .map_err(|e| e.with_status(403))?;
                    if let Some(board) = args["dashboardId"].as_str() {
                        principal.board(board)?;
                    } else if ![
                        "dashboard_list",
                        "runtime_info",
                        "runtime_keepalive",
                        "runtime_report_error",
                    ]
                    .contains(&name)
                    {
                        args["dashboardId"] = json!(principal.primary);
                    }
                    if name == "dashboard_get" {
                        name = "dashboard_preview";
                    }
                    if READING.contains(&name) && self.service.project_root.is_some() {
                        pin_reader_revision(&self.service, &mut args)?;
                    }
                }
                let mut result = self.service.call(name, &args)?;
                if !principal.edit && name == "dashboard_list" {
                    result["dashboards"].as_array_mut().unwrap().retain(|v| {
                        v["id"]
                            .as_str()
                            .is_some_and(|id| principal.boards.as_ref().unwrap().contains(id))
                    });
                }
                if ["dashboard_get", "dashboard_preview"].contains(&name) {
                    result["projectRoot"] = json!(self.service.project_root);
                }
                return HttpOutput::json(&result);
            }
        }
        Err(Error::new("NOT_FOUND", "Unknown endpoint").with_status(404))
    }
}
pub struct LocalPreview {
    state: Arc<LocalState>,
    cancel: CancellationToken,
    thread: Option<std::thread::JoinHandle<()>>,
}
impl LocalPreview {
    pub fn browser_links(&self, board: &str) -> Result<Value> {
        self.state.browser_links(board)
    }
}
impl Drop for LocalPreview {
    fn drop(&mut self) {
        self.cancel.cancel();
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}
async fn local_http(State(state): State<Arc<LocalState>>, request: Request<Body>) -> Response {
    let head = request.method() == Method::HEAD;
    let gzip = encoding_quality(request.headers(), "gzip") > 0.0;
    let result = match read_input(request, false).await {
        Ok(input) => tokio::task::spawn_blocking(move || state.handle(&input))
            .await
            .unwrap_or_else(|_| {
                Err(Error::new("INTERNAL_ERROR", "Request failed").with_status(500))
            }),
        Err(e) => Err(e),
    };
    result
        .unwrap_or_else(HttpOutput::failure)
        .response(gzip, head)
}
pub fn start_local(service: Arc<Service>, port: u16, lifetime: Lifetime) -> Result<LocalPreview> {
    let listener = TcpListener::bind(("127.0.0.1", port))?;
    let port = listener.local_addr()?.port();
    listener.set_nonblocking(true)?;
    let state = Arc::new(LocalState {
        service,
        token: random(),
        port,
        lifetime,
    });
    let cancel = CancellationToken::new();
    let shared = state.clone();
    let shutdown = cancel.clone();
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()?;
    let thread = std::thread::spawn(move || {
        let _ = runtime.block_on(async move {
            let listener = tokio::net::TcpListener::from_std(listener)?;
            let life = shared.lifetime.clone();
            let watcher_cancel = shutdown.clone();
            let watcher = tokio::spawn(async move {
                loop {
                    tokio::time::sleep(Duration::from_millis(250)).await;
                    if life.expired() {
                        watcher_cancel.cancel();
                        break;
                    }
                    if watcher_cancel.is_cancelled() {
                        break;
                    }
                }
            });
            let app = Router::new().fallback(local_http).with_state(shared);
            let result = axum::serve(listener, app)
                .with_graceful_shutdown(shutdown.cancelled_owned())
                .await;
            watcher.abort();
            result
        });
        runtime.shutdown_timeout(Duration::from_secs(2));
    });
    Ok(LocalPreview {
        state,
        cancel,
        thread: Some(thread),
    })
}
fn shutdown_signal() -> std::io::Result<impl Future<Output = ()>> {
    #[cfg(unix)]
    let (mut interrupt, mut terminate) = {
        use tokio::signal::unix::{signal, SignalKind};
        (
            signal(SignalKind::interrupt())?,
            signal(SignalKind::terminate())?,
        )
    };
    #[cfg(windows)]
    let mut interrupt = tokio::signal::windows::ctrl_c()?;
    Ok(async move {
        #[cfg(unix)]
        tokio::select! {
            _ = interrupt.recv() => {},
            _ = terminate.recv() => {},
        }
        #[cfg(windows)]
        interrupt.recv().await;
    })
}

pub fn serve_local(
    service: Service,
    port: u16,
    idle: f64,
    dashboard: Option<&str>,
    view: bool,
) -> Result<()> {
    assets::require_preview()?;
    let preview = start_local(Arc::new(service), port, Lifetime::new(idle)?)?;
    let url = if let Some(board) = dashboard {
        preview.browser_links(board)?[if view { "viewUrl" } else { "editUrl" }]
            .as_str()
            .unwrap()
            .to_owned()
    } else {
        format!(
            "http://127.0.0.1:{}/#token={}",
            preview.state.port, preview.state.token
        )
    };
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_io()
        .build()?;
    runtime.block_on(async {
        let signal = shutdown_signal()?;
        println!("{}", json!({"url":url,"port":preview.state.port}));
        tokio::select! {
            _ = preview.cancel.cancelled() => {},
            _ = signal => preview.cancel.cancel(),
        }
        Ok(())
    })
}
fn html_escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}
fn access_form(path: &str, message: &str, status: u16) -> HttpOutput {
    let nonce = random();
    let path = html_escape(path);
    let error = if message.is_empty() {
        String::new()
    } else {
        format!(
            "<p id=\"key-error\" class=\"error\" role=\"alert\">{}</p>",
            html_escape(message)
        )
    };
    let page = include_str!("../../resources/share-access.html")
        .replace("{{favicon}}", &assets::favicon_link())
        .replace("{{nonce}}", &nonce)
        .replace("{{path}}", &path)
        .replace("{{error}}", &error)
        .replace(
            "{{description}}",
            if error.is_empty() {
                "key-hint"
            } else {
                "key-hint key-error"
            },
        )
        .replace(
            "{{invalid}}",
            if status == 401 {
                " aria-invalid=\"true\""
            } else {
                ""
            },
        )
        .replace(
            "{{retry}}",
            &if status == 403 {
                format!("<a class=\"retry\" href=\"{path}\">重新打开分享</a>")
            } else {
                String::new()
            },
        );
    let mut response=HttpOutput::html(page).status(status).with_header("Referrer-Policy","same-origin").with_header("Content-Security-Policy",format!("default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; img-src data:; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"));
    if status == 429 {
        response = response.with_header("Retry-After", "900");
    }
    response
}
impl RemoteServer {
    fn publication_source(&self, project: Option<&str>, source: Option<&str>) -> Result<String> {
        let project = project.filter(|p| valid_project(p)).ok_or_else(|| {
            Error::new(
                "INVALID_PROJECT",
                "A valid publication project name is required",
            )
        })?;
        let source = source.ok_or_else(|| {
            Error::new(
                "INVALID_ARGUMENT",
                "A stable local project UUID is required",
            )
        })?;
        let uuid = Uuid::parse_str(source)
            .map_err(|_| Error::new("INVALID_ARGUMENT", "Invalid local project UUID"))?;
        require(
            uuid.get_version_num() == 4 && uuid.to_string() == source,
            "A stable local project UUID is required",
            "INVALID_ARGUMENT",
        )?;
        Ok(hex::encode(Sha256::digest(
            format!("local-publication:{project}:{source}").as_bytes(),
        )))
    }
    fn feedback(
        &self,
        shares: &super::shares::CloudShares,
        share: &str,
        board: Option<&str>,
    ) -> Result<Value> {
        let control = shares.control(share)?;
        let board = board.unwrap_or(string(&control, "dashboardId")?);
        let expiry = control["expiresAt"]
            .as_i64()
            .unwrap_or(now() + 900)
            .min(now() + 900);
        let token = self.signer.sign(
            &json!({"k":"share-feedback","shareId":share,"dashboardId":board,"exp":expiry}),
        )?;
        let mut result = shares.annotations(share, Some(board))?;
        result["url"] = json!(format!(
            "{}/s/{share}/?dashboardId={}#feedback={token}",
            shares.public_url,
            encoded(board)
        ));
        result["canAnnotate"] = json!(false);
        result["expiresAt"] = json!(expiry);
        Ok(result)
    }
    fn key_attempt(&self, share: &str, peer: &str) -> Result<()> {
        let now = now();
        let mut attempts = self
            .attempts
            .lock()
            .map_err(|_| Error::new("INTERNAL_ERROR", "Rate limiter unavailable"))?;
        attempts.retain(|_, (_, until)| *until > now);
        for (key, limit) in [
            ((share.to_owned(), peer.to_owned()), 5),
            ((share.to_owned(), "*".into()), 100),
        ] {
            require(
                attempts.get(&key).is_none_or(|(count, _)| *count < limit),
                "尝试次数过多，请 15 分钟后重试",
                "SHARE_RATE_LIMITED",
            )?;
        }
        for key in [
            (share.to_owned(), peer.to_owned()),
            (share.to_owned(), "*".into()),
        ] {
            let entry = attempts.entry(key).or_insert((0, now + 900));
            entry.0 += 1;
        }
        Ok(())
    }
    fn same_origin(&self, input: &HttpInput) -> Result<()> {
        let origin = header(&input.headers, "origin");
        let url = url::Url::parse(&self.settings.public_url).unwrap();
        require(
            origin.is_empty() || origin == url.origin().ascii_serialization(),
            "Invalid request origin",
            "FORBIDDEN",
        )
        .map_err(|e| e.with_status(403))
    }
    fn publication(&self, input: &HttpInput, share: &str, name: &str) -> Result<HttpOutput> {
        let shares = self
            .shares
            .as_ref()
            .ok_or_else(|| Error::new("CLOUD_SHARE_NOT_CONFIGURED", "云端分享未配置"))?;
        super::shares::checked_id(share)?;
        let control = shares.control(share)?;
        let path = format!("{}/s/{share}/", self.settings.base);
        let cookie = format!("charts-share-{share}");
        if input.method == Method::POST {
            self.same_origin(input)?;
            let fields: Vec<_> = url::form_urlencoded::parse(&input.body)
                .into_owned()
                .collect();
            require(fields.len() <= 4, "Invalid form", "INVALID_ARGUMENT")?;
            let value = |key: &str| {
                fields
                    .iter()
                    .find(|(k, _)| k == key)
                    .map(|(_, v)| v.as_str())
                    .unwrap_or("")
            };
            let token = value("feedbackToken");
            let feedback = if token.is_empty() {
                self.key_attempt(share, &self.settings.client_ip(&input.peer, &input.headers))?;
                shares.authenticate(share, value("accessKey"))?;
                None
            } else {
                let payload = self
                    .signer
                    .verify(token, "share-feedback")
                    .filter(|v| v["shareId"] == share)
                    .ok_or_else(|| Error::new("INVALID_ACCESS_KEY", "反馈访问链接已失效"))?;
                shares.publication_page(share, payload["dashboardId"].as_str(), Some(&control))?;
                Some(payload)
            };
            let mut expiry = control["expiresAt"]
                .as_i64()
                .unwrap_or(now() + 43200)
                .min(now() + 43200);
            if let Some(feedback) = &feedback {
                expiry = expiry.min(feedback["exp"].as_i64().unwrap());
            }
            let session=self.signer.sign(&json!({"k":"cloud-share","shareId":share,"exp":expiry,"feedback":feedback.is_some()}))?;
            let redirect = if let Some(feedback) = &feedback {
                format!(
                    "{path}?dashboardId={}",
                    encoded(string(feedback, "dashboardId")?)
                )
            } else {
                path.clone()
            };
            return Ok(HttpOutput::raw(Vec::new(),"text/plain").status(303).with_header("Location",redirect).with_header("Set-Cookie",format!("{cookie}={session}; Max-Age={}; Path={path}; Secure; HttpOnly; SameSite=Strict",(expiry-now()).max(0))));
        }
        let session = self
            .signer
            .verify(input.cookie(&cookie), "cloud-share")
            .filter(|v| v["shareId"] == share);
        if session.is_none() {
            require(
                name == "index.html",
                "请先输入访问密钥",
                "INVALID_ACCESS_KEY",
            )?;
            return Ok(access_form(&path, "", 200));
        }
        let session = session.unwrap();
        let mut raw = shares.content(share, name, Some(&control))?;
        if name == "index.html" {
            let access = serde_json::to_string(&path)?.replace('<', "\\u003c");
            let entry = format!(
                r#"<script id="charts-share-entry">(()=>{{const params=new URLSearchParams(location.hash.slice(1));const field=params.has('feedback')?'feedbackToken':params.has('key')?'accessKey':null;if(field){{const value=params.get(field==='feedbackToken'?'feedback':'key');history.replaceState(null,'',location.pathname+location.search);const form=document.createElement('form');form.method='post';form.action={access};const input=document.createElement('input');input.type='hidden';input.name=field;input.value=value;form.appendChild(input);document.body.appendChild(form);form.submit();return;}}const app=document.createElement('script');app.src='app.js';document.body.appendChild(app);}})();</script>"#
            );
            raw = String::from_utf8(raw)
                .map_err(|_| Error::new("SHARE_UNAVAILABLE", "Invalid publication HTML"))?
                .replace("<script src=\"app.js\"></script>", &entry)
                .into_bytes();
        }
        if session["feedback"] == true
            && control["pages"]
                .as_array()
                .is_some_and(|pages| pages.iter().any(|p| p["path"] == name))
        {
            let mut document: Value = serde_json::from_slice(&raw)?;
            if document["annotationAccess"].is_object() {
                document["annotationAccess"]["canAnnotate"] = json!(false);
            }
            document["annotationsOpen"] = json!(true);
            raw = serde_json::to_vec(&document)?;
        }
        let kind = if name.ends_with(".gz") {
            String::from("application/gzip")
        } else {
            mime_guess::from_path(name)
                .first_or_octet_stream()
                .to_string()
        };
        Ok(HttpOutput::raw(raw, &kind)
            .with_header("Cache-Control", "private, no-store, max-age=0")
            .with_header(
                "Referrer-Policy",
                if name == "index.html" {
                    "same-origin"
                } else {
                    "no-referrer"
                },
            )
            .with_header(
                "Content-Security-Policy",
                "frame-ancestors 'none'; base-uri 'self'; object-src 'none'",
            ))
    }
    fn publication_annotations(&self, input: &HttpInput, share: &str) -> Result<HttpOutput> {
        let shares = self
            .shares
            .as_ref()
            .ok_or_else(|| Error::new("CLOUD_SHARE_NOT_CONFIGURED", "分享服务尚未配置"))?;
        super::shares::checked_id(share)?;
        let control = shares.control(share)?;
        let session = self
            .signer
            .verify(
                input.cookie(&format!("charts-share-{share}")),
                "cloud-share",
            )
            .filter(|v| v["shareId"] == share)
            .ok_or_else(|| Error::new("INVALID_ACCESS_KEY", "请先输入访问密钥"))?;
        let result = if input.method == Method::GET {
            let mut result =
                shares.annotations(share, input.query.get("dashboardId").map(String::as_str))?;
            require(
                input
                    .revision(None)?
                    .is_none_or(|revision| result["revision"] == revision),
                "批注读取版本不匹配",
                "REVISION_CONFLICT",
            )?;
            if session["feedback"] == true {
                result["canAnnotate"] = json!(false);
            }
            result
        } else {
            require(
                session["feedback"] != true,
                "反馈查看链接仅允许读取",
                "FORBIDDEN",
            )?;
            self.same_origin(input)?;
            let body = input.json()?;
            require(
                body.as_object().unwrap().keys().all(|k| {
                    ["dashboardId", "append", "authorName", "revision"].contains(&k.as_str())
                }),
                "Invalid annotation request",
                "INVALID_ARGUMENT",
            )?;
            let board = body["dashboardId"].as_str();
            let page = shares.publication_page(share, board, Some(&control))?;
            require(
                input
                    .revision(Some(&body))?
                    .is_none_or(|r| page["revision"] == r),
                "批注提交版本不匹配",
                "REVISION_CONFLICT",
            )?;
            shares.append_annotation(share, board, &body["append"], body["authorName"].as_str())?
        };
        HttpOutput::json(&result)
    }
    fn handle(&self, input: &HttpInput) -> Result<HttpOutput> {
        let path = input.path.as_str();
        if path == "/health" && (input.method == Method::GET || input.method == Method::HEAD) {
            let mut value =
                json!({"ok":true,"version":env!("CARGO_PKG_VERSION"),"role":self.settings.role});
            if self.settings.role == "workspace" {
                value["storage"] = json!(self
                    .database
                    .as_ref()
                    .map_or("sqlite", |db| db.backend.as_str()));
            }
            if let Some(commit) = std::env::var("CHARTS_IMAGE_COMMIT")
                .ok()
                .filter(|value| !value.is_empty())
            {
                value["release"] = json!({"version":env!("CARGO_PKG_VERSION"),"commit":commit});
            } else if let Ok(version) = std::env::var("CHARTS_RELEASE_VERSION") {
                value["release"] = json!({"version":version,"commit":std::env::var("CHARTS_RELEASE_COMMIT").unwrap_or_default()});
            }
            return HttpOutput::json(&value);
        }
        let decoded = decoded_path(path)?;
        let parts: Vec<&str> = decoded.iter().map(String::as_str).collect();
        if self.settings.role == "sharing" {
            match parts.as_slice() {
                ["api", "v1", "publications"] if input.method == Method::POST => {
                    self.author(&input.headers)?;
                    require(
                        header(&input.headers, "content-type").split(';').next()
                            == Some("application/zip"),
                        "Use application/zip",
                        "CONTENT_TYPE",
                    )
                    .map_err(|e| e.with_status(415))?;
                    let source = self.publication_source(
                        Some(header(&input.headers, "x-charts-project")),
                        Some(header(&input.headers, "x-charts-source")),
                    )?;
                    let archive = input.archive.as_ref().ok_or_else(|| {
                        Error::new("INVALID_REQUEST", "Missing publication archive")
                    })?;
                    let mode = header(&input.headers, "x-charts-annotation-mode");
                    let expiration = header(&input.headers, "x-charts-expiration");
                    return HttpOutput::json(&self.shares.as_ref().unwrap().import_site_path(
                        archive.path(),
                        &source,
                        header(&input.headers, "x-charts-request"),
                        &self.settings.secret,
                        if mode.is_empty() { "view" } else { mode },
                        if expiration.is_empty() {
                            "7d"
                        } else {
                            expiration
                        },
                        None,
                    )?);
                }
                ["api", "v1", "publications", share]
                    if input.method == Method::GET || input.method == Method::DELETE =>
                {
                    self.author(&input.headers)?;
                    let source = self.publication_source(
                        input.query.get("project").map(String::as_str),
                        input.query.get("source").map(String::as_str),
                    )?;
                    let shares = self.shares.as_ref().unwrap();
                    shares.owner_control(share, &source)?;
                    return HttpOutput::json(&if input.method == Method::DELETE {
                        shares.revoke_owner(share, &source)?
                    } else {
                        self.feedback(
                            shares,
                            share,
                            input.query.get("dashboardId").map(String::as_str),
                        )?
                    });
                }
                ["s", share, "api", "annotations"]
                    if input.method == Method::GET || input.method == Method::POST =>
                {
                    return self.publication_annotations(input, share)
                }
                ["s", share, tail @ ..]
                    if input.method == Method::GET || input.method == Method::POST =>
                {
                    let name = tail.join("/");
                    let name = if name.is_empty() { "index.html" } else { &name };
                    require(
                        input.method != Method::POST || name == "index.html",
                        "Unknown endpoint",
                        "NOT_FOUND",
                    )?;
                    return match self.publication(input, share, name) {
                        Err(error)
                            if input.method == Method::POST
                                && ["INVALID_ACCESS_KEY", "SHARE_RATE_LIMITED", "FORBIDDEN"]
                                    .contains(&error.code.as_str()) =>
                        {
                            Ok(access_form(
                                &format!("{}/s/{share}/", self.settings.base),
                                if error.code == "FORBIDDEN" {
                                    "无法验证本次访问来源。请重新打开分享后输入密钥。"
                                } else {
                                    &error.message
                                },
                                if error.code == "FORBIDDEN" {
                                    403
                                } else if error.code == "SHARE_RATE_LIMITED" {
                                    429
                                } else {
                                    401
                                },
                            ))
                        }
                        result => result,
                    };
                }
                _ => return Err(Error::new("NOT_FOUND", "Unknown endpoint").with_status(404)),
            }
        }
        match parts.as_slice() {
            [""] | ["view", _, _] | ["edit", _, _]
                if matches!(input.method, Method::GET | Method::HEAD) =>
            {
                let project = if parts.len() == 3 {
                    parts[1]
                } else {
                    &self.settings.default_project
                };
                require(
                    valid_project(project),
                    "Invalid project name",
                    "INVALID_PROJECT",
                )?;
                let board = if parts.len() == 3 {
                    model::check_identifier(parts[2])?;
                    Some(parts[2])
                } else {
                    None
                };
                let boot = json!({"mode":"web","projectRoot":project,"dashboardId":board,"apiBase":format!("{}/api/v1/p/{}/tools/",self.settings.base,encoded(project)),"readOnly":parts.first()==Some(&"view"),"idleTimeout":null,"annotationAccess":{"endpoint":format!("{}/api/v1/p/{}/annotations/{{dashboardId}}",self.settings.base,encoded(project)),"canRead":true,"canAnnotate":false,"canManageAnnotations":false,"scope":format!("workspace:{project}")},"publicationApiBase":format!("{}/api/v1/p/{}/publications/",self.settings.base,encoded(project))});
                Ok(HttpOutput::html(assets::render_web_html(
                    &self.settings.base,
                    None,
                    &boot,
                )?))
            }
            ["assets", build, name] if matches!(input.method, Method::GET | Method::HEAD) => {
                versioned_asset(input, build, name)
            }
            ["assets", build, "fonts", name]
                if matches!(input.method, Method::GET | Method::HEAD) =>
            {
                versioned_asset(input, build, &format!("fonts/{name}"))
            }
            ["assets", name] if input.method == Method::GET => {
                require(
                    assets::UI_RESOURCES.contains(name),
                    "Unknown asset",
                    "NOT_FOUND",
                )?;
                let bytes = fs::read(assets::dist().join(name))?;
                Ok(HttpOutput::raw(
                    bytes,
                    if name.ends_with(".js") {
                        "text/javascript"
                    } else {
                        "text/css"
                    },
                )
                .with_header("Cache-Control", "no-cache"))
            }
            ["api", "v1", "p", project, "tools", name] if input.method == Method::POST => {
                let principal = self.request_principal(input, project)?;
                let args = input.json()?;
                require(self.exists(project)?, "Project not found", "NOT_FOUND")
                    .map_err(|e| e.with_status(404))?;
                HttpOutput::json(&self.call_viewer(project, name, args, &principal)?)
            }
            ["api", "v1", "p", project, "annotations", board]
                if input.method == Method::GET || input.method == Method::POST =>
            {
                let principal = self.request_principal(input, project)?;
                principal.board(board)?;
                let body = if input.method == Method::POST {
                    Some(input.json()?)
                } else {
                    None
                };
                require(
                    body.as_ref()
                        .is_none_or(|p| p.get("dashboardId").is_none_or(|v| v == *board)),
                    "Dashboard does not match endpoint",
                    "FORBIDDEN",
                )?;
                require(self.exists(project)?, "Project not found", "NOT_FOUND")?;
                let mut result = annotation_response(
                    self.service(project)?.as_ref(),
                    board,
                    input.revision(body.as_ref())?,
                    principal.can_annotate,
                    principal.edit,
                    body.as_ref(),
                )?;
                result["canAnnotate"] = json!(principal.can_annotate);
                result["canManageAnnotations"] = json!(principal.edit);
                result["independentSave"] = json!(true);
                result["author"] =
                    json!({"name":if principal.edit{"作者"}else{"访客"},"verified":false});
                HttpOutput::json(&result)
            }
            ["api", "v1", "p", project, "publications", share, "feedback"]
                if input.method == Method::GET =>
            {
                let principal = self.request_principal(input, project)?;
                require(
                    principal.edit,
                    "Only the author can open share feedback",
                    "FORBIDDEN",
                )?;
                let board = input
                    .query
                    .get("dashboardId")
                    .map(String::as_str)
                    .or(principal.primary.as_deref())
                    .ok_or_else(|| Error::new("INVALID_ARGUMENT", "dashboardId is required"))?;
                principal.board(board)?;
                HttpOutput::json(
                    &super::local_shares::LocalShares::new(self.service(project)?.as_ref())?
                        .feedback(board, share)?,
                )
            }
            ["api", "v1", "p", project, "content", board, revision, object, name]
                if input.method == Method::GET =>
            {
                let principal = self.request_principal(input, project)?;
                principal.board(board)?;
                let revision = revision
                    .parse::<i64>()
                    .map_err(|_| Error::new("INVALID_ARGUMENT", "Invalid revision"))?;
                let service = self.service(project)?;
                require(
                    service.store.cos_enabled,
                    "Project has no cloud assets",
                    "NOT_FOUND",
                )?;
                let doc = if principal.edit {
                    let draft = service.store.get(board, false)?;
                    if draft["revision"] == revision {
                        draft
                    } else {
                        Versions::new(&service.store)?.read(board, revision)?
                    }
                } else {
                    require(
                        service.store.display_revision(board)? == Some(revision),
                        "Version no longer available",
                        "REVISION_CONFLICT",
                    )?;
                    Versions::new(&service.store)?.read(board, revision)?
                };
                Ok(HttpOutput::raw(
                    super::shares::authorized_file(&service.store, &doc, object, name)?,
                    if name.ends_with(".gz") {
                        "application/gzip"
                    } else {
                        "application/octet-stream"
                    },
                ))
            }
            ["api", "v1", "catalog"] if input.method == Method::POST => {
                self.author(&input.headers)?;
                let projects = self
                    .names()?
                    .iter()
                    .map(|name| {
                        Ok(json!({"name":name,"dashboards":self.service(name)?.store.list()?}))
                    })
                    .collect::<Result<Vec<_>>>()?;
                HttpOutput::json(&json!({"projects":projects}))
            }
            ["api", "v1", "share"] if input.method == Method::POST => {
                self.author(&input.headers)?;
                let args = input.json()?;
                let project = self.project_name(args["project"].as_str())?;
                require(self.exists(&project)?, "Project not found", "NOT_FOUND")?;
                HttpOutput::json(&self.share(&project, &args)?)
            }
            ["files", token] if input.method == Method::GET => {
                let payload = self.signer.verify(token, "file").ok_or_else(|| {
                    Error::new("LINK_EXPIRED", "Download link is invalid or expired")
                        .with_status(404)
                })?;
                let project = string(&payload, "p")?;
                require(
                    self.exists(project)?,
                    "Download link is invalid or expired",
                    "LINK_EXPIRED",
                )?;
                let root = absolute_path(&self.settings.workspace.join(project))?;
                let target = absolute_path(&root.join(string(&payload, "f")?))?;
                require(
                    [root.join("dashboards/exports"), root.join("deployments")]
                        .iter()
                        .any(|base| target.starts_with(base)),
                    "Download path is outside project",
                    "FORBIDDEN",
                )?;
                if !target.is_file() && cloud::cloud_enabled()? {
                    cloud::restore_file(project, string(&payload, "f")?, &target)?;
                }
                let file = fs::File::open(&target).map_err(|_| {
                    Error::new("LINK_EXPIRED", "Download is unavailable").with_status(404)
                })?;
                Ok(HttpOutput {
                    status: 200,
                    kind: mime_guess::from_path(&target)
                        .first_or_octet_stream()
                        .to_string(),
                    headers: vec![(
                        "Content-Disposition".into(),
                        format!(
                            "attachment; filename*=UTF-8''{}",
                            encoded(&target.file_name().unwrap().to_string_lossy())
                        ),
                    )],
                    payload: Payload::File(file),
                })
            }
            _ => Err(Error::new("NOT_FOUND", "Unknown endpoint").with_status(404)),
        }
    }
}
fn decoded_path(path: &str) -> Result<Vec<String>> {
    path.trim_start_matches('/')
        .split('/')
        .map(|part| {
            percent_encoding::percent_decode_str(part)
                .decode_utf8()
                .map(|part| part.into_owned())
                .map_err(|_| Error::new("INVALID_REQUEST", "Invalid URL encoding"))
        })
        .collect()
}
async fn guard(
    State(server): State<Arc<RemoteServer>>,
    mut request: Request<Body>,
    next: Next,
) -> Response {
    let check = (|| -> Result<Option<String>> {
        let path = request.uri().path();
        if path != "/health" {
            server.settings.host_guard(request.headers())?;
            if server.settings.role == "sharing" {
                if let Ok(expected) = std::env::var("CHARTS_ORIGIN_TOKEN") {
                    if !expected.is_empty() {
                        require(
                            equal(&expected, header(request.headers(), "x-origin-token")),
                            "Invalid origin token",
                            "FORBIDDEN",
                        )
                        .map_err(|e| e.with_status(403))?;
                    }
                }
            }
        }
        // MCP is one exact endpoint. Reject descendants before body parsing;
        // the SDK's generic service does not enforce an HTTP path itself.
        require(!path.starts_with("/mcp/"), "Unknown endpoint", "NOT_FOUND")
            .map_err(|error| error.with_status(404))?;
        if path == "/mcp" || path.starts_with("/api/v1/publications") {
            server.author(request.headers())?;
        }
        if server.settings.role == "workspace" {
            let parts = decoded_path(path)?;
            if parts.len() == 3
                && parts[0] == "api"
                && parts[1] == "v1"
                && ["catalog", "share"].contains(&parts[2].as_str())
            {
                server.author(request.headers())?;
            }
            if parts.len() >= 4 && parts[0] == "api" && parts[1] == "v1" && parts[2] == "p" {
                return Ok(Some(parts[3].clone()));
            }
        }
        Ok(None)
    })();
    let project = match check {
        Ok(project) => project,
        Err(error) => return HttpOutput::failure(error).response(false, false),
    };
    if let Some(project) = project {
        let auth = server.clone();
        let token = bearer(request.headers()).to_owned();
        // Generation checks may query the cloud. Perform them once, off the
        // async worker, before consuming any untrusted request body.
        let verified = tokio::task::spawn_blocking(move || {
            auth.principal(&token, &project)
                .map(|principal| ProjectPrincipal { project, principal })
        })
        .await;
        match verified {
            Ok(Ok(principal)) => {
                request.extensions_mut().insert(principal);
            }
            Ok(Err(error)) => return HttpOutput::failure(error).response(false, false),
            Err(_) => {
                return HttpOutput::failure(
                    Error::new("INTERNAL_ERROR", "Authentication failed").with_status(500),
                )
                .response(false, false)
            }
        }
    }
    let method = request.method().clone();
    let start = std::time::Instant::now();
    let response = next.run(request).await;
    eprintln!(
        "HTTP {method} {} {}ms",
        response.status().as_u16(),
        start.elapsed().as_millis()
    );
    response
}
async fn remote_http(State(server): State<Arc<RemoteServer>>, request: Request<Body>) -> Response {
    let gzip = encoding_quality(request.headers(), "gzip") > 0.0;
    let head = request.method() == Method::HEAD;
    let upload = server.settings.role == "sharing"
        && request.method() == Method::POST
        && request.uri().path() == "/api/v1/publications";
    let result = match read_input(request, upload).await {
        Ok(input) => tokio::task::spawn_blocking(move || server.handle(&input))
            .await
            .unwrap_or_else(|_| {
                Err(
                    Error::new("INTERNAL_ERROR", "Request failed; inspect server logs")
                        .with_status(500),
                )
            }),
        Err(e) => Err(e),
    };
    result
        .unwrap_or_else(HttpOutput::failure)
        .response(gzip, head)
}
pub fn router(server: Arc<RemoteServer>, cancel: CancellationToken) -> Result<Router> {
    let mut app = Router::new()
        .fallback(remote_http)
        .with_state(server.clone());
    if server.settings.role == "workspace" {
        use rmcp::transport::streamable_http_server::{
            session::local::LocalSessionManager, StreamableHttpServerConfig, StreamableHttpService,
        };
        let lifetime = Lifetime::new(0.0)?;
        let mcp = super::mcp::Mcp::new(server.clone(), lifetime)?;
        let mut config = StreamableHttpServerConfig::default()
            .with_legacy_session_mode(!server.settings.stateless)
            .with_json_response(server.settings.stateless)
            .with_max_request_body_bytes(MAX_BODY + 1024 * 1024)
            .with_cancellation_token(cancel);
        if !server.settings.guard_hosts {
            config = config.disable_allowed_hosts();
        } else {
            let url = url::Url::parse(&server.settings.public_url).unwrap();
            config.allowed_hosts = server.settings.allowed_hosts.clone();
            config.allowed_hosts.extend([
                url[url::Position::BeforeHost..url::Position::AfterPort].into(),
                format!("127.0.0.1:{}", server.settings.port),
                format!("localhost:{}", server.settings.port),
                format!("{}:{}", server.settings.host, server.settings.port),
            ]);
        }
        let service = StreamableHttpService::new(
            move || Ok(mcp.clone()),
            LocalSessionManager::default().into(),
            config,
        );
        app = app.route_service("/mcp", service);
    }
    Ok(app.layer(middleware::from_fn_with_state(server, guard)))
}
pub fn command(options: &Value) -> Result<Option<Value>> {
    let settings = Settings::from_options(options)?;
    let server = Arc::new(RemoteServer::new(settings)?);
    if options["command"] == "share" {
        let project = server.project_name(options["project"].as_str())?;
        let args = json!({"dashboardId":options["dashboard"],"access":options["access"].as_str().unwrap_or("view"),"expiresInHours":options["hours"].as_f64().unwrap_or(server.settings.share_hours)});
        return Ok(Some(server.share(&project, &args)?));
    }
    let runtime = tokio::runtime::Runtime::new()?;
    let host = server.settings.host.clone();
    let port = server.settings.port;
    let cancel = CancellationToken::new();
    let app = router(server, cancel.clone())?;
    let result = runtime.block_on(async move {
        let signal = shutdown_signal()?;
        let listener = tokio::net::TcpListener::bind((host.as_str(), port)).await?;
        eprintln!(
            "Charts Design Rust HTTP listening on {}",
            listener.local_addr()?
        );
        axum::serve(
            listener,
            app.into_make_service_with_connect_info::<SocketAddr>(),
        )
        .with_graceful_shutdown(async move {
            signal.await;
            cancel.cancel();
        })
        .await
        .map_err(Error::from)
    });
    runtime.shutdown_timeout(Duration::from_secs(2));
    result.map(|_| None)
}

#[cfg(test)]
#[path = "../../tests/unit/server_http.rs"]
mod regression_tests;

#[cfg(test)]
#[path = "../../tests/unit/server_existing.rs"]
mod tests;
