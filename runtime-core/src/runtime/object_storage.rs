//! Private object storage used by cloud assets and disposable publications.
use super::error::{require, Error, Result};
use base64::{engine::general_purpose::STANDARD, Engine};
use hmac::{Hmac, Mac};
use reqwest::blocking::{Body, Client, Response};
use serde_json::{json, Value};
use sha1::{Digest, Sha1};
use std::{
    collections::{BTreeMap, VecDeque},
    env, fs,
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    sync::{Arc, Mutex, OnceLock},
    time::{Duration, Instant},
};

type CredentialCache = Arc<Mutex<Option<(Credentials, Instant)>>>;
fn http_client() -> Result<&'static Client> {
    static CLIENT: OnceLock<Result<Client>> = OnceLock::new();
    CLIENT
        .get_or_init(|| {
            Client::builder()
                .connect_timeout(Duration::from_secs(20))
                .timeout(Duration::from_secs(60))
                .pool_max_idle_per_host(8)
                .redirect(reqwest::redirect::Policy::none())
                .build()
                .map_err(|_| {
                    Error::new("COS_UNAVAILABLE", "COS HTTP client initialization failed")
                        .with_status(503)
                })
        })
        .as_ref()
        .map_err(Clone::clone)
}
fn credential_cache(identity: String) -> Result<CredentialCache> {
    static CACHES: OnceLock<Mutex<VecDeque<(String, CredentialCache)>>> = OnceLock::new();
    let mut caches = CACHES.get_or_init(Mutex::default).lock().map_err(|_| {
        Error::new(
            "CLOUD_CREDENTIAL_UNAVAILABLE",
            "Credential cache unavailable",
        )
    })?;
    if let Some(position) = caches.iter().position(|(key, _)| key == &identity) {
        let entry = caches.remove(position).unwrap();
        let cache = entry.1.clone();
        caches.push_back(entry);
        return Ok(cache);
    }
    let cache = Arc::new(Mutex::new(None));
    caches.push_back((identity, cache.clone()));
    while caches.len() > 8 {
        caches.pop_front();
    }
    Ok(cache)
}

#[derive(Clone)]
struct Credentials {
    id: String,
    key: String,
    token: String,
}
#[derive(Clone)]
pub struct CosStorage {
    region: String,
    bucket: String,
    pub prefix: String,
    credentials: CredentialCache,
}
#[derive(Clone)]
pub enum Storage {
    Private { root: PathBuf, executor: String },
    Cos(CosStorage),
}

pub fn private_path(root: &Path, key: &str) -> Result<PathBuf> {
    let relative = Path::new(key);
    require(
        !key.is_empty()
            && !relative.is_absolute()
            && relative
                .components()
                .all(|c| matches!(c, Component::Normal(_))),
        "Invalid private object key",
        "INVALID_ARGUMENT",
    )?;
    let canonical_root = root.canonicalize()?;
    let target = canonical_root.join(relative);
    let mut existing = target.as_path();
    while !existing.exists() {
        existing = existing
            .parent()
            .ok_or_else(|| Error::new("INVALID_PATH", "Invalid private object key"))?;
    }
    require(
        existing.canonicalize()?.starts_with(&canonical_root),
        "Invalid private object key",
        "INVALID_ARGUMENT",
    )?;
    Ok(target)
}

pub fn atomic_write(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| Error::new("INVALID_PATH", "Path has no parent"))?;
    fs::create_dir_all(parent)?;
    let mut staged = tempfile::NamedTempFile::new_in(parent)?;
    staged.write_all(bytes)?;
    staged.as_file().sync_all()?;
    staged.persist(path).map_err(|e| Error::from(e.error))?;
    Ok(())
}

pub fn file_digest(path: &Path) -> Result<(u64, String)> {
    let mut file = fs::File::open(path)?;
    let mut digest = sha2::Sha256::new();
    let mut size = 0u64;
    let mut buffer = [0u8; 128 * 1024];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
        size += count as u64;
    }
    Ok((size, hex::encode(digest.finalize())))
}
fn copy_verified(
    mut reader: impl Read,
    target: &Path,
    expected_bytes: Option<u64>,
    expected_hash: &str,
) -> Result<()> {
    require(
        expected_hash.len() == 64
            && expected_hash
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "Invalid object checksum",
        "DATA_CONFLICT",
    )?;
    let parent = target
        .parent()
        .ok_or_else(|| Error::new("INVALID_PATH", "Path has no parent"))?;
    fs::create_dir_all(parent)?;
    let mut staged = tempfile::NamedTempFile::new_in(parent)?;
    let mut digest = sha2::Sha256::new();
    let mut size = 0u64;
    let mut buffer = [0u8; 128 * 1024];
    loop {
        let count = reader.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        size = size
            .checked_add(count as u64)
            .ok_or_else(|| Error::new("CLOUD_FILE_CORRUPT", "Object size overflow"))?;
        require(
            expected_bytes.is_none_or(|expected| size <= expected),
            "Cloud object byte count mismatch",
            "CLOUD_FILE_CORRUPT",
        )?;
        digest.update(&buffer[..count]);
        staged.write_all(&buffer[..count])?;
    }
    require(
        expected_bytes.is_none_or(|expected| size == expected)
            && hex::encode(digest.finalize()) == expected_hash,
        "Cloud object checksum mismatch",
        "CLOUD_FILE_CORRUPT",
    )?;
    staged.as_file().sync_all()?;
    staged
        .persist(target)
        .map_err(|error| Error::from(error.error))?;
    Ok(())
}
fn private_headers(content_type: &str) -> BTreeMap<String, String> {
    BTreeMap::from([
        ("content-type".into(), content_type.into()),
        (
            "cache-control".into(),
            "private, no-store, max-age=0".into(),
        ),
        ("x-cos-acl".into(), "private".into()),
        ("x-cos-server-side-encryption".into(), "AES256".into()),
    ])
}

impl Storage {
    pub fn private(root: PathBuf, executor: &str) -> Result<Self> {
        fs::create_dir_all(&root)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&root, fs::Permissions::from_mode(0o700))?;
        }
        Ok(Self::Private {
            root: root.canonicalize()?,
            executor: executor.into(),
        })
    }
    pub fn publication() -> Result<Self> {
        let backend = env::var("CHARTS_STORAGE_BACKEND").unwrap_or_default();
        if matches!(backend.as_str(), "cloudflare" | "neon") {
            let root = env::var("CHARTS_RUNTIME_ROOT")
                .map_err(|_| Error::new("INVALID_CONFIG", "Configure CHARTS_RUNTIME_ROOT"))?;
            Self::private(
                PathBuf::from(root).join("private-shares"),
                if backend == "neon" {
                    "server-timer"
                } else {
                    "cloudflare-cron"
                },
            )
        } else {
            Ok(Self::Cos(CosStorage::from_environment()?))
        }
    }
    pub fn assets() -> Result<Self> {
        if env::var("CHARTS_STORAGE_BACKEND").as_deref() == Ok("neon") {
            let root = env::var("CHARTS_RUNTIME_ROOT")
                .map_err(|_| Error::new("INVALID_CONFIG", "Configure CHARTS_RUNTIME_ROOT"))?;
            return Self::private(PathBuf::from(root).join("private-assets"), "server-timer");
        }
        let mut storage = CosStorage::from_environment()?;
        let prefix =
            env::var("CHARTS_COS_ASSET_PREFIX").unwrap_or_else(|_| "charts-assets/".into());
        let prefix = format!("{}/", prefix.trim_end_matches('/'));
        require(
            !prefix.starts_with(&storage.prefix) && !storage.prefix.starts_with(&prefix),
            "Asset and disposable share prefixes must be separate",
            "INVALID_CONFIG",
        )?;
        storage.prefix = checked_prefix(&prefix)?;
        let result = Self::Cos(storage);
        result.check_private()?;
        Ok(result)
    }
    pub fn executor(&self) -> &str {
        match self {
            Self::Private { executor, .. } => executor,
            Self::Cos(_) => "tencent-scf",
        }
    }
    pub fn root(&self) -> Option<&Path> {
        match self {
            Self::Private { root, .. } => Some(root),
            _ => None,
        }
    }
    pub fn check_private(&self) -> Result<()> {
        match self {
            Self::Private { root, .. } => {
                #[cfg(unix)]
                {
                    use std::os::unix::fs::PermissionsExt;
                    require(
                        fs::metadata(root)?.permissions().mode() & 0o077 == 0,
                        "Share directory must be private",
                        "INVALID_CONFIG",
                    )?;
                }
                Ok(())
            }
            Self::Cos(cos) => cos.check_private(),
        }
    }
    pub fn put(&self, key: &str, bytes: &[u8], content_type: &str) -> Result<()> {
        match self {
            Self::Private { root, .. } => atomic_write(&private_path(root, key)?, bytes),
            Self::Cos(cos) => {
                cos.request(
                    "PUT",
                    &cos.key(key)?,
                    &BTreeMap::new(),
                    private_headers(content_type),
                    bytes.to_vec(),
                )?;
                Ok(())
            }
        }
    }
    pub fn put_file(&self, key: &str, path: &Path, content_type: &str) -> Result<()> {
        let file = fs::File::open(path)?;
        let bytes = file.metadata()?.len();
        match self {
            Self::Private { root, .. } => {
                let target = private_path(root, key)?;
                let parent = target
                    .parent()
                    .ok_or_else(|| Error::new("INVALID_PATH", "Object path has no parent"))?;
                fs::create_dir_all(parent)?;
                let mut staged = tempfile::NamedTempFile::new_in(parent)?;
                let copied = std::io::copy(&mut file.take(bytes + 1), &mut staged)?;
                require(
                    copied == bytes,
                    "Upload source changed while reading",
                    "DATA_CONFLICT",
                )?;
                staged.as_file().sync_all()?;
                staged
                    .persist(target)
                    .map_err(|error| Error::from(error.error))?;
                Ok(())
            }
            Self::Cos(cos) => {
                let mut headers = private_headers(content_type);
                headers.insert("content-length".into(), bytes.to_string());
                let mut response = cos.request_response(
                    "PUT",
                    &cos.key(key)?,
                    &BTreeMap::new(),
                    headers,
                    Body::sized(file, bytes),
                )?;
                std::io::copy(&mut response, &mut std::io::sink()).map_err(|_| {
                    Error::new("COS_UNAVAILABLE", "COS response failed").with_status(503)
                })?;
                Ok(())
            }
        }
    }
    fn reader(&self, key: &str) -> Result<Option<Box<dyn Read>>> {
        let source: Box<dyn Read> = match self {
            Self::Private { root, .. } => match fs::File::open(private_path(root, key)?) {
                Ok(file) => Box::new(file),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
                Err(error) => return Err(error.into()),
            },
            Self::Cos(cos) => match cos.request_response(
                "GET",
                &cos.key(key)?,
                &BTreeMap::new(),
                BTreeMap::new(),
                Body::from(Vec::<u8>::new()),
            ) {
                Ok(response) => Box::new(response),
                Err(error) if matches!(error.code.as_str(), "NoSuchKey" | "NoSuchVersion") => {
                    return Ok(None)
                }
                Err(error) => return Err(error),
            },
        };
        Ok(Some(source))
    }
    pub fn download_file(
        &self,
        key: &str,
        target: &Path,
        expected_bytes: Option<u64>,
        expected_hash: &str,
    ) -> Result<bool> {
        let Some(source) = self.reader(key)? else {
            return Ok(false);
        };
        copy_verified(source, target, expected_bytes, expected_hash)?;
        Ok(true)
    }
    pub fn get_bounded(&self, key: &str, maximum: u64) -> Result<Option<Vec<u8>>> {
        let Some(source) = self.reader(key)? else {
            return Ok(None);
        };
        let mut raw = Vec::new();
        source
            .take(maximum.saturating_add(1))
            .read_to_end(&mut raw)?;
        require(
            raw.len() as u64 <= maximum,
            "Cloud object exceeds its declared byte count",
            "CLOUD_FILE_CORRUPT",
        )?;
        Ok(Some(raw))
    }
    pub fn get(&self, key: &str) -> Result<Option<Vec<u8>>> {
        self.get_bounded(key, u64::MAX)
    }
    pub fn list(&self, prefix: &str) -> Result<Vec<String>> {
        match self {
            Self::Private { root, .. } => {
                let start = private_path(root, prefix)?;
                let mut out = Vec::new();
                let mut pending = vec![start];
                while let Some(path) = pending.pop() {
                    if !path.exists() {
                        continue;
                    }
                    let metadata = fs::symlink_metadata(&path)?;
                    require(
                        !metadata.file_type().is_symlink(),
                        "Symbolic object paths are not allowed",
                        "INVALID_PATH",
                    )?;
                    if metadata.is_dir() {
                        for entry in fs::read_dir(path)? {
                            pending.push(entry?.path());
                        }
                    } else if metadata.is_file() {
                        out.push(
                            path.strip_prefix(root)
                                .unwrap()
                                .to_string_lossy()
                                .replace('\\', "/"),
                        );
                    }
                }
                out.sort();
                Ok(out)
            }
            Self::Cos(cos) => Ok(cos
                .entries(prefix, false)?
                .into_iter()
                .filter_map(|e| e.key.strip_prefix(&cos.prefix).map(str::to_owned))
                .collect()),
        }
    }
    pub fn delete_prefix(&self, prefix: &str) -> Result<()> {
        match self {
            Self::Private { root, .. } => {
                let path = private_path(root, prefix)?;
                if path.is_dir() {
                    fs::remove_dir_all(path)?;
                } else if path.exists() {
                    fs::remove_file(path)?;
                }
                Ok(())
            }
            Self::Cos(cos) => {
                // Version IDs must be physically removed before deleting visible objects.
                for versions in [true, false, true] {
                    let mut previous = None;
                    loop {
                        let (entries, _) = cos.entries_page(prefix, versions, "", "")?;
                        if entries.is_empty() {
                            break;
                        }
                        let current = entries
                            .iter()
                            .map(|entry| (entry.key.clone(), entry.version.clone()))
                            .collect::<Vec<_>>();
                        require(
                            previous.as_ref() != Some(&current),
                            "COS deletion did not advance; cleanup will retry",
                            "COS_DELETE_FAILED",
                        )?;
                        cos.delete_entries(&entries)?;
                        previous = Some(current);
                    }
                }
                Ok(())
            }
        }
    }
    pub fn size_prefix(&self, prefix: &str) -> Result<u64> {
        match self {
            Self::Private { root, .. } => self.list(prefix)?.iter().try_fold(0, |sum, key| {
                Ok(sum + fs::metadata(private_path(root, key)?)?.len())
            }),
            Self::Cos(cos) => {
                let (mut marker, mut version_marker, mut total) =
                    (String::new(), String::new(), 0u64);
                loop {
                    let (entries, next) =
                        cos.entries_page(prefix, false, &marker, &version_marker)?;
                    for entry in entries {
                        total = total.checked_add(entry.size).ok_or_else(|| {
                            Error::new("COS_REQUEST_FAILED", "Object size overflow")
                        })?;
                    }
                    let Some((key, version)) = next else {
                        break;
                    };
                    marker = key;
                    version_marker = version;
                }
                Ok(total)
            }
        }
    }
}

fn checked_prefix(prefix: &str) -> Result<String> {
    require(
        !prefix.trim_matches('/').is_empty()
            && !prefix.starts_with('/')
            && !prefix.contains('\\')
            && !prefix.chars().any(char::is_control)
            && !prefix.split('/').any(|p| p == ".." || p == "."),
        "Configure a dedicated non-empty COS share prefix",
        "INVALID_CONFIG",
    )?;
    Ok(format!("{}/", prefix.trim_end_matches('/')))
}
fn encode(value: &str) -> String {
    value
        .as_bytes()
        .iter()
        .map(|b| {
            if b.is_ascii_alphanumeric() || b"-_.~".contains(b) {
                (*b as char).to_string()
            } else {
                format!("%{b:02X}")
            }
        })
        .collect()
}
fn sha1_hmac(key: &[u8], value: &str) -> String {
    let mut mac = Hmac::<Sha1>::new_from_slice(key).expect("HMAC accepts arbitrary keys");
    mac.update(value.as_bytes());
    hex::encode(mac.finalize().into_bytes())
}
struct Entry {
    key: String,
    version: Option<String>,
    size: u64,
}
type ObjectPage = (Vec<Entry>, Option<(String, String)>);

impl CosStorage {
    fn from_environment() -> Result<Self> {
        let region = env::var("CHARTS_COS_REGION").unwrap_or_default();
        let bucket = env::var("CHARTS_COS_BUCKET").unwrap_or_default();
        require(
            !region.is_empty()
                && !bucket.is_empty()
                && region
                    .bytes()
                    .chain(bucket.bytes())
                    .all(|b| b.is_ascii_alphanumeric() || b == b'-'),
            "Configure CHARTS_COS_REGION and CHARTS_COS_BUCKET",
            "CLOUD_SHARE_NOT_CONFIGURED",
        )?;
        let prefix = checked_prefix(
            &env::var("CHARTS_COS_SHARE_PREFIX").unwrap_or_else(|_| "charts-shares/".into()),
        )?;
        let identity = hex::encode(sha2::Sha256::digest(
            json!([
                region,
                bucket,
                env::var("CLOUDBASE_ENV_ID").unwrap_or_default(),
                env::var("CLOUDBASE_REGION").unwrap_or_else(|_| region.clone()),
                env::var("CLOUDBASE_API_KEY").unwrap_or_default()
            ])
            .to_string()
            .as_bytes(),
        ));
        Ok(Self {
            region,
            bucket,
            prefix,
            credentials: credential_cache(identity)?,
        })
    }
    fn key(&self, key: &str) -> Result<String> {
        require(
            !key.is_empty()
                && !key.starts_with('/')
                && !key.contains('\\')
                && !key.chars().any(char::is_control)
                && !key.split('/').any(|p| p == ".." || p == "."),
            "Invalid private object key",
            "INVALID_ARGUMENT",
        )?;
        Ok(format!("{}{key}", self.prefix))
    }
    fn credentials(&self) -> Result<Credentials> {
        let api_key = env::var("CLOUDBASE_API_KEY").unwrap_or_default();
        let id = env::var("TENCENTCLOUD_SECRETID").unwrap_or_default();
        if api_key.is_empty()
            || (!id.is_empty() && env::var("CHARTS_COS_AUTH").as_deref() != Ok("cloudbase"))
        {
            let key = env::var("TENCENTCLOUD_SECRETKEY").unwrap_or_default();
            require(
                !id.is_empty() && !key.is_empty(),
                "Configure Tencent runtime credentials or CloudBase service credentials",
                "CLOUD_SHARE_NOT_CONFIGURED",
            )?;
            return Ok(Credentials {
                id,
                key,
                token: env::var("TENCENTCLOUD_SESSIONTOKEN").unwrap_or_default(),
            });
        }
        let mut cached = self.credentials.lock().map_err(|_| {
            Error::new(
                "CLOUD_CREDENTIAL_UNAVAILABLE",
                "Credential lock unavailable",
            )
        })?;
        if let Some((credentials, expires)) = cached.as_ref() {
            if Instant::now() < *expires {
                return Ok(credentials.clone());
            }
        }
        let environment = env::var("CLOUDBASE_ENV_ID").unwrap_or_default();
        let region = env::var("CLOUDBASE_REGION").unwrap_or_else(|_| self.region.clone());
        require(
            !environment.is_empty()
                && environment
                    .bytes()
                    .chain(region.bytes())
                    .all(|b| b.is_ascii_alphanumeric() || b == b'-'),
            "Configure CloudBase environment and region",
            "INVALID_CONFIG",
        )?;
        let response = http_client()?
            .post(format!(
                "https://{environment}.{region}.tcb-api.tencentcloudapi.com/capi/credential"
            ))
            .bearer_auth(api_key)
            .timeout(Duration::from_secs(20))
            .json(&json!({"env":environment}))
            .send()
            .and_then(|r| r.error_for_status())
            .map_err(|_| {
                Error::new(
                    "CLOUD_CREDENTIAL_UNAVAILABLE",
                    "CloudBase credential exchange failed",
                )
                .with_status(503)
            })?;
        let mut raw = Vec::new();
        response
            .take(1024 * 1024 + 1)
            .read_to_end(&mut raw)
            .map_err(|_| {
                Error::new(
                    "CLOUD_CREDENTIAL_UNAVAILABLE",
                    "CloudBase credential exchange failed",
                )
                .with_status(503)
            })?;
        require(
            raw.len() <= 1024 * 1024,
            "CloudBase credential response is too large",
            "CLOUD_CREDENTIAL_UNAVAILABLE",
        )?;
        let response: Value = serde_json::from_slice(&raw).map_err(|_| {
            Error::new(
                "CLOUD_CREDENTIAL_UNAVAILABLE",
                "CloudBase credential exchange returned invalid JSON",
            )
        })?;
        require(
            response["code"] == 0,
            "CloudBase credential exchange was rejected",
            "CLOUD_CREDENTIAL_UNAVAILABLE",
        )?;
        let c = &response["data"];
        let credentials = Credentials {
            id: c["TmpSecretId"].as_str().unwrap_or("").into(),
            key: c["TmpSecretKey"].as_str().unwrap_or("").into(),
            token: c["Token"].as_str().unwrap_or("").into(),
        };
        require(
            !credentials.id.is_empty()
                && !credentials.key.is_empty()
                && !credentials.token.is_empty(),
            "CloudBase credential exchange returned incomplete credentials",
            "CLOUD_CREDENTIAL_UNAVAILABLE",
        )?;
        let expires = ["ExpiredTime", "expiredTime", "Expiration", "expiration"]
            .into_iter()
            .find_map(|key| {
                c.get(key).and_then(|value| {
                    value.as_i64().or_else(|| {
                        value.as_str().and_then(|value| {
                            value.parse::<i64>().ok().or_else(|| {
                                chrono::DateTime::parse_from_rfc3339(value)
                                    .ok()
                                    .map(|time| time.timestamp())
                            })
                        })
                    })
                })
            });
        let lifetime = expires
            .map(|expiry| expiry - chrono::Utc::now().timestamp() - 60)
            .unwrap_or(1200);
        require(
            lifetime > 0,
            "CloudBase returned expired credentials",
            "CLOUD_CREDENTIAL_UNAVAILABLE",
        )?;
        *cached = Some((
            credentials.clone(),
            Instant::now() + Duration::from_secs((lifetime as u64).min(1200)),
        ));
        Ok(credentials)
    }
    fn request(
        &self,
        method: &str,
        key: &str,
        params: &BTreeMap<String, String>,
        headers: BTreeMap<String, String>,
        body: Vec<u8>,
    ) -> Result<Vec<u8>> {
        let response = self.request_response(method, key, params, headers, Body::from(body))?;
        let mut raw = Vec::new();
        response
            .take(8 * 1024 * 1024 + 1)
            .read_to_end(&mut raw)
            .map_err(|_| Error::new("COS_UNAVAILABLE", "COS response failed").with_status(503))?;
        require(
            raw.len() <= 8 * 1024 * 1024,
            "COS control response is too large",
            "COS_REQUEST_FAILED",
        )?;
        Ok(raw)
    }
    fn request_response(
        &self,
        method: &str,
        key: &str,
        params: &BTreeMap<String, String>,
        mut headers: BTreeMap<String, String>,
        body: Body,
    ) -> Result<Response> {
        let credentials = self.credentials()?;
        let host = format!("{}.cos.{}.myqcloud.com", self.bucket, self.region);
        headers.insert("host".into(), host.clone());
        if !credentials.token.is_empty() {
            headers.insert("x-cos-security-token".into(), credentials.token);
        }
        let now = chrono::Utc::now().timestamp();
        let times = format!("{};{}", now - 60, now + 900);
        let canonical = |values: &BTreeMap<String, String>| {
            let mut pairs = values
                .iter()
                .map(|(k, v)| (encode(k).to_lowercase(), encode(v)))
                .collect::<Vec<_>>();
            pairs.sort();
            pairs
        };
        let query = canonical(params);
        let hs = canonical(&headers);
        let uri = format!("/{key}");
        let http = format!(
            "{}\n{uri}\n{}\n{}\n",
            method.to_lowercase(),
            query
                .iter()
                .map(|(k, v)| format!("{k}={v}"))
                .collect::<Vec<_>>()
                .join("&"),
            hs.iter()
                .map(|(k, v)| format!("{k}={v}"))
                .collect::<Vec<_>>()
                .join("&")
        );
        let sign_key = sha1_hmac(credentials.key.as_bytes(), &times);
        let text = format!(
            "sha1\n{times}\n{}\n",
            hex::encode(Sha1::digest(http.as_bytes()))
        );
        let signature = sha1_hmac(sign_key.as_bytes(), &text);
        let authorization=format!("q-sign-algorithm=sha1&q-ak={}&q-sign-time={times}&q-key-time={times}&q-header-list={}&q-url-param-list={}&q-signature={signature}",credentials.id,hs.iter().map(|(k,_)|k.as_str()).collect::<Vec<_>>().join(";"),query.iter().map(|(k,_)|k.as_str()).collect::<Vec<_>>().join(";"));
        let path = key.split('/').map(encode).collect::<Vec<_>>().join("/");
        let query = params
            .iter()
            .map(|(k, v)| format!("{}={}", encode(k), encode(v)))
            .collect::<Vec<_>>()
            .join("&");
        let url = format!(
            "https://{host}/{path}{}",
            if query.is_empty() {
                String::new()
            } else {
                format!("?{query}")
            }
        );
        let mut request = http_client()?
            .request(
                method
                    .parse()
                    .map_err(|_| Error::new("INVALID_ARGUMENT", "Invalid COS method"))?,
                url,
            )
            .header("authorization", authorization)
            .body(body);
        for (key, value) in headers {
            request = request.header(key, value);
        }
        let response = request
            .send()
            .map_err(|_| Error::new("COS_UNAVAILABLE", "COS request failed").with_status(503))?;
        let status = response.status();
        if !status.is_success() {
            let mut raw = Vec::new();
            response
                .take(1024 * 1024)
                .read_to_end(&mut raw)
                .map_err(|_| {
                    Error::new("COS_UNAVAILABLE", "COS response failed").with_status(503)
                })?;
            let text = String::from_utf8_lossy(&raw);
            let code = roxmltree::Document::parse(&text)
                .ok()
                .and_then(|d| {
                    d.descendants()
                        .find(|n| n.has_tag_name("Code"))
                        .and_then(|n| n.text())
                        .filter(|code| {
                            code.len() <= 128
                                && code
                                    .bytes()
                                    .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
                        })
                        .map(str::to_owned)
                })
                .unwrap_or_else(|| "COS_REQUEST_FAILED".into());
            return Err(Error::new(code, "COS object request failed").with_status(status.as_u16()));
        }
        Ok(response)
    }
    fn check_private(&self) -> Result<()> {
        let raw = self.request(
            "GET",
            "",
            &BTreeMap::from([("acl".into(), "".into())]),
            BTreeMap::new(),
            vec![],
        )?;
        let text = String::from_utf8(raw)
            .map_err(|_| Error::new("COS_BUCKET_NOT_PRIVATE", "Invalid COS ACL"))?;
        let doc = roxmltree::Document::parse(&text)
            .map_err(|_| Error::new("COS_BUCKET_NOT_PRIVATE", "Invalid COS ACL"))?;
        require(
            doc.root_element().has_tag_name("AccessControlPolicy")
                && doc
                    .descendants()
                    .any(|node| node.has_tag_name("AccessControlList")),
            "Invalid COS ACL",
            "COS_BUCKET_NOT_PRIVATE",
        )?;
        require(
            !doc.descendants().any(|n| {
                n.has_tag_name("URI")
                    && n.text()
                        .is_some_and(|v| v.contains("AllUsers") || v.contains("AuthenticatedUsers"))
            }),
            "Cloud shares require a private COS bucket",
            "COS_BUCKET_NOT_PRIVATE",
        )?;
        match self.request(
            "GET",
            "",
            &BTreeMap::from([("policy".into(), "".into())]),
            BTreeMap::new(),
            vec![],
        ) {
            Err(e) if e.code == "NoSuchBucketPolicy" => Ok(()),
            Err(e) => Err(e),
            Ok(raw) => {
                let policy: Value = serde_json::from_slice(&raw)?;
                let statements = policy.get("Statement").or_else(|| policy.get("statement"));
                let statements: Vec<&Value> = match statements {
                    Some(Value::Array(values)) => values.iter().collect(),
                    Some(Value::Object(_)) => vec![statements.unwrap()],
                    _ => {
                        return Err(Error::new(
                            "COS_BUCKET_NOT_PRIVATE",
                            "Invalid COS bucket policy",
                        ))
                    }
                };
                for statement in statements {
                    require(
                        statement.is_object(),
                        "Invalid COS bucket policy",
                        "COS_BUCKET_NOT_PRIVATE",
                    )?;
                    if statement
                        .get("Effect")
                        .or_else(|| statement.get("effect"))
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .eq_ignore_ascii_case("allow")
                    {
                        let principal = statement
                            .get("Principal")
                            .or_else(|| statement.get("principal"))
                            .unwrap_or(&Value::Null);
                        let values = principal
                            .as_object()
                            .map(|o| o.values().collect::<Vec<_>>())
                            .unwrap_or_else(|| vec![principal]);
                        require(
                            !values.iter().any(|v| {
                                **v == "*"
                                    || v.as_array().is_some_and(|a| a.iter().any(|s| s == "*"))
                            }),
                            "Remove public allow policies from the share bucket",
                            "COS_BUCKET_NOT_PRIVATE",
                        )?;
                    }
                }
                Ok(())
            }
        }
    }
    fn entries(&self, prefix: &str, versions: bool) -> Result<Vec<Entry>> {
        let mut marker = String::new();
        let mut version_marker = String::new();
        let mut out = Vec::new();
        loop {
            let (entries, next) = self.entries_page(prefix, versions, &marker, &version_marker)?;
            out.extend(entries);
            let Some((key, version)) = next else {
                break;
            };
            marker = key;
            version_marker = version;
        }
        Ok(out)
    }
    fn entries_page(
        &self,
        prefix: &str,
        versions: bool,
        marker: &str,
        version_marker: &str,
    ) -> Result<ObjectPage> {
        let full = self.key(prefix)?;
        let mut params = BTreeMap::from([
            ("prefix".into(), full.clone()),
            ("max-keys".into(), "1000".into()),
        ]);
        if versions {
            params.insert("versions".into(), String::new());
            params.insert("key-marker".into(), marker.into());
            params.insert("version-id-marker".into(), version_marker.into());
        } else {
            params.insert("marker".into(), marker.into());
        }
        let raw = self.request("GET", "", &params, BTreeMap::new(), vec![])?;
        parse_listing(&raw, &full, versions, marker, version_marker)
    }
    fn delete_entries(&self, entries: &[Entry]) -> Result<()> {
        let body = delete_body(entries)?;
        let digest = <md5::Md5 as md5::Digest>::digest(&body);
        let headers = BTreeMap::from([
            ("content-type".into(), "application/xml".into()),
            ("content-length".into(), body.len().to_string()),
            ("content-md5".into(), STANDARD.encode(digest)),
        ]);
        let raw = self.request(
            "POST",
            "",
            &BTreeMap::from([("delete".into(), String::new())]),
            headers,
            body,
        )?;
        let text = std::str::from_utf8(&raw)
            .map_err(|_| Error::new("COS_DELETE_FAILED", "Invalid COS deletion response"))?;
        let document = roxmltree::Document::parse(text)
            .map_err(|_| Error::new("COS_DELETE_FAILED", "Invalid COS deletion response"))?;
        require(
            document.root_element().has_tag_name("DeleteResult")
                && !document
                    .descendants()
                    .any(|node| node.has_tag_name("Error")),
            "COS object deletion failed; cleanup will retry",
            "COS_DELETE_FAILED",
        )
    }
}

fn parse_listing(
    raw: &[u8],
    prefix: &str,
    versions: bool,
    marker: &str,
    version_marker: &str,
) -> Result<ObjectPage> {
    let text = std::str::from_utf8(raw)
        .map_err(|_| Error::new("COS_REQUEST_FAILED", "Invalid COS listing"))?;
    let document = roxmltree::Document::parse(text)
        .map_err(|_| Error::new("COS_REQUEST_FAILED", "Invalid COS listing"))?;
    let root = document.root_element();
    require(
        root.has_tag_name(if versions {
            "ListVersionsResult"
        } else {
            "ListBucketResult"
        }),
        "Unexpected COS listing response",
        "COS_REQUEST_FAILED",
    )?;
    let field = |node: roxmltree::Node<'_, '_>, name: &str| {
        node.children()
            .find(|child| child.has_tag_name(name))
            .and_then(|child| child.text())
            .unwrap_or("")
            .to_owned()
    };
    let mut entries = Vec::new();
    for node in root.children().filter(|node| {
        node.is_element()
            && if versions {
                matches!(node.tag_name().name(), "Version" | "DeleteMarker")
            } else {
                node.has_tag_name("Contents")
            }
    }) {
        let key = field(node, "Key");
        require(
            key.starts_with(prefix),
            "COS listing escaped its publication prefix",
            "COS_REQUEST_FAILED",
        )?;
        let version = if versions {
            let version = field(node, "VersionId");
            require(
                !version.is_empty(),
                "COS version listing omitted a version ID",
                "COS_REQUEST_FAILED",
            )?;
            Some(version)
        } else {
            None
        };
        let size = field(node, "Size");
        let size = if node.has_tag_name("DeleteMarker") {
            0
        } else {
            size.parse()
                .map_err(|_| Error::new("COS_REQUEST_FAILED", "Invalid COS object size"))?
        };
        entries.push(Entry { key, version, size });
    }
    require(
        entries.len() <= 1000,
        "COS listing exceeds its requested page size",
        "COS_REQUEST_FAILED",
    )?;
    let truncated = field(root, "IsTruncated");
    require(
        truncated.eq_ignore_ascii_case("true") || truncated.eq_ignore_ascii_case("false"),
        "COS listing omitted pagination state",
        "COS_REQUEST_FAILED",
    )?;
    if truncated.eq_ignore_ascii_case("false") {
        return Ok((entries, None));
    }
    let next = field(
        root,
        if versions {
            "NextKeyMarker"
        } else {
            "NextMarker"
        },
    );
    let next_version = field(root, "NextVersionIdMarker");
    require(
        !next.is_empty()
            && next.starts_with(prefix)
            && (next != marker || next_version != version_marker),
        "COS pagination did not advance",
        "COS_REQUEST_FAILED",
    )?;
    Ok((entries, Some((next, next_version))))
}
fn delete_body(entries: &[Entry]) -> Result<Vec<u8>> {
    require(
        !entries.is_empty() && entries.len() <= 1000,
        "Invalid COS deletion batch",
        "INVALID_ARGUMENT",
    )?;
    let mut xml = String::from("<Delete><Quiet>true</Quiet>");
    for entry in entries {
        xml.push_str("<Object><Key>");
        xml.push_str(&quick_xml::escape::escape(&entry.key));
        xml.push_str("</Key>");
        if let Some(version) = &entry.version {
            require(
                !version.is_empty(),
                "COS version ID is missing",
                "COS_DELETE_FAILED",
            )?;
            xml.push_str("<VersionId>");
            xml.push_str(&quick_xml::escape::escape(version));
            xml.push_str("</VersionId>");
        }
        xml.push_str("</Object>");
    }
    xml.push_str("</Delete>");
    Ok(xml.into_bytes())
}

#[cfg(test)]
mod tests {
    use super::*;

    // @wu-test type=integration | scope=streamed private object files | protects=large query files keep bounded memory and failed checksum or byte-count validation cannot replace valid cached data
    #[test]
    fn streamed_files_commit_only_after_integrity_verification() {
        let directory = tempfile::tempdir().unwrap();
        let storage = Storage::private(directory.path().join("objects"), "test").unwrap();
        let source = directory.path().join("source.sqlite3");
        let mut file = fs::File::create(&source).unwrap();
        let buffer = vec![b'x'; 128 * 1024];
        for _ in 0..65 {
            file.write_all(&buffer).unwrap();
        }
        drop(file);
        let (bytes, hash) = file_digest(&source).unwrap();
        storage
            .put_file("dataset/query.sqlite3", &source, "application/octet-stream")
            .unwrap();
        let target = directory.path().join("download.sqlite3");
        assert!(storage
            .download_file("dataset/query.sqlite3", &target, Some(bytes), &hash)
            .unwrap());
        assert_eq!(file_digest(&target).unwrap(), (bytes, hash.clone()));
        fs::write(&target, b"existing valid cache").unwrap();
        assert!(storage
            .download_file("dataset/query.sqlite3", &target, Some(bytes - 1), &hash)
            .is_err());
        assert_eq!(fs::read(&target).unwrap(), b"existing valid cache");
        assert!(storage
            .download_file(
                "dataset/query.sqlite3",
                &target,
                Some(bytes),
                &"f".repeat(64)
            )
            .is_err());
        assert_eq!(fs::read(&target).unwrap(), b"existing valid cache");
        assert!(storage.get_bounded("dataset/query.sqlite3", 1024).is_err());
        assert!(!storage
            .download_file("missing/query.sqlite3", &target, None, &hash)
            .unwrap());
        assert!(storage
            .put_file("../outside", &source, "application/octet-stream")
            .is_err());
        storage.delete_prefix("dataset/").unwrap();
        assert!(storage.list("dataset/").unwrap().is_empty());
    }

    // @wu-test type=boundary | scope=COS physical deletion | protects=object versions and delete markers remain explicit, batches are escaped and pagination never escapes a publication prefix
    #[test]
    fn cos_pages_preserve_version_ids_and_reject_stalled_or_escaped_markers() {
        let xml = br#"<ListVersionsResult xmlns="http://cos.example.test/"><IsTruncated>true</IsTruncated><NextKeyMarker>shares/one/object</NextKeyMarker><NextVersionIdMarker>next</NextVersionIdMarker><Version><Key>shares/one/a&amp;b</Key><VersionId>v&lt;1</VersionId><Size>42</Size></Version><DeleteMarker><Key>shares/one/object</Key><VersionId>marker</VersionId></DeleteMarker></ListVersionsResult>"#;
        let (entries, marker) = parse_listing(xml, "shares/one/", true, "", "").unwrap();
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].size, 42);
        assert_eq!(entries[1].version.as_deref(), Some("marker"));
        assert_eq!(marker, Some(("shares/one/object".into(), "next".into())));
        assert!(parse_listing(xml, "shares/one/", true, "shares/one/object", "next").is_err());
        assert!(parse_listing(xml, "shares/two/", true, "", "").is_err());
        let body = String::from_utf8(delete_body(&entries).unwrap()).unwrap();
        let parsed = roxmltree::Document::parse(&body).unwrap();
        let versions = parsed
            .descendants()
            .filter(|node| node.has_tag_name("VersionId"))
            .filter_map(|node| node.text())
            .collect::<Vec<_>>();
        assert_eq!(versions, vec!["v<1", "marker"]);
        assert!(body.contains("<Key>shares/one/a&amp;b</Key>"));
        let missing = br#"<ListVersionsResult><IsTruncated>false</IsTruncated><Version><Key>shares/one/a</Key><Size>1</Size></Version></ListVersionsResult>"#;
        assert!(parse_listing(missing, "shares/one/", true, "", "").is_err());
        assert!(delete_body(&[]).is_err());
    }

    // @wu-test type=unit | scope=COS signing and credential cache | protects=canonical escaping and HMAC primitives stay stable while credential caches remain isolated by configuration
    #[test]
    fn signing_primitives_and_shared_credentials_are_stable() {
        assert_eq!(
            sha1_hmac(&[0x0b; 20], "Hi There"),
            "b617318655057264e28bc0b6fb378c8ef146be00"
        );
        assert_eq!(encode("中文 /%+"), "%E4%B8%AD%E6%96%87%20%2F%25%2B");
        let first = credential_cache("test-identity-one".into()).unwrap();
        let same = credential_cache("test-identity-one".into()).unwrap();
        let other = credential_cache("test-identity-two".into()).unwrap();
        assert!(Arc::ptr_eq(&first, &same));
        assert!(!Arc::ptr_eq(&first, &other));
        assert!(checked_prefix("../outside/").is_err());
        assert!(checked_prefix("a\\..\\outside").is_err());
        assert!(checked_prefix("path\ninvalid").is_err());
    }
}
