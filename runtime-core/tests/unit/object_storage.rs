use super::*;
use std::{
    net::{TcpListener, TcpStream},
    sync::atomic::{AtomicBool, Ordering},
    thread::JoinHandle,
};

#[derive(Clone, Debug)]
struct RecordedRequest {
    method: String,
    target: String,
    headers: BTreeMap<String, String>,
    body: Vec<u8>,
}

type HttpReply = (u16, Vec<u8>);

struct CosFixture {
    url: String,
    requests: Arc<Mutex<Vec<RecordedRequest>>>,
    replies: Arc<Mutex<VecDeque<HttpReply>>>,
    stopped: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
}

fn read_request(stream: &mut TcpStream) -> RecordedRequest {
    stream
        .set_read_timeout(Some(Duration::from_secs(10)))
        .unwrap();
    let mut raw = Vec::new();
    let mut buffer = [0u8; 4096];
    let header_end = loop {
        let count = stream.read(&mut buffer).unwrap();
        assert!(count > 0);
        raw.extend_from_slice(&buffer[..count]);
        if let Some(index) = raw.windows(4).position(|part| part == b"\r\n\r\n") {
            break index + 4;
        }
        assert!(raw.len() < 64 * 1024);
    };
    let text = std::str::from_utf8(&raw[..header_end]).unwrap();
    let mut lines = text.split("\r\n");
    let mut first = lines.next().unwrap().split_whitespace();
    let method = first.next().unwrap().to_owned();
    let target = first.next().unwrap().to_owned();
    let headers = lines
        .filter_map(|line| line.split_once(':'))
        .map(|(name, value)| (name.to_ascii_lowercase(), value.trim().to_owned()))
        .collect::<BTreeMap<_, _>>();
    let length = headers
        .get("content-length")
        .map_or(0, |n| n.parse::<usize>().unwrap());
    while raw.len() < header_end + length {
        let count = stream.read(&mut buffer).unwrap();
        assert!(count > 0);
        raw.extend_from_slice(&buffer[..count]);
    }
    RecordedRequest {
        method,
        target,
        headers,
        body: raw[header_end..header_end + length].to_vec(),
    }
}

impl CosFixture {
    fn new() -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let requests = Arc::new(Mutex::new(Vec::new()));
        let replies = Arc::new(Mutex::new(VecDeque::<(u16, Vec<u8>)>::new()));
        let stopped = Arc::new(AtomicBool::new(false));
        let captured = requests.clone();
        let responses = replies.clone();
        let done = stopped.clone();
        let thread = std::thread::spawn(move || {
            while !done.load(Ordering::Relaxed) {
                match listener.accept() {
                    Ok((mut stream, _)) => {
                        captured.lock().unwrap().push(read_request(&mut stream));
                        let (status, body) = responses
                            .lock()
                            .unwrap()
                            .pop_front()
                            .expect("unexpected COS request");
                        write!(stream,"HTTP/1.1 {status} Test\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",body.len()).unwrap();
                        stream.write_all(&body).unwrap();
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        std::thread::sleep(Duration::from_millis(2))
                    }
                    Err(error) => panic!("COS fixture accept: {error}"),
                }
            }
        });
        Self {
            url,
            requests,
            replies,
            stopped,
            thread: Some(thread),
        }
    }
    fn reply(&self, status: u16, body: impl AsRef<[u8]>) {
        self.replies
            .lock()
            .unwrap()
            .push_back((status, body.as_ref().to_vec()));
    }
    fn storage(&self) -> Storage {
        Storage::Cos(CosStorage {
            region: "test-region".into(),
            bucket: "private-bucket".into(),
            prefix: "shares/".into(),
            credentials: Arc::new(Mutex::new(None)),
            connection: Some(Arc::new(CosConnection {
                client: Client::builder()
                    .no_proxy()
                    .redirect(reqwest::redirect::Policy::none())
                    .timeout(Duration::from_secs(5))
                    .build()
                    .unwrap(),
                credentials: Credentials {
                    id: "test-key-id".into(),
                    key: "test-secret".into(),
                    token: "test-session".into(),
                },
                host: "private-bucket.cos.test-region.myqcloud.com".into(),
                endpoint: self.url.clone(),
            })),
        })
    }
    fn recorded(&self) -> Vec<RecordedRequest> {
        self.requests.lock().unwrap().clone()
    }
}
impl Drop for CosFixture {
    fn drop(&mut self) {
        self.stopped.store(true, Ordering::Relaxed);
        if let Some(thread) = self.thread.take() {
            if !std::thread::panicking() {
                thread.join().unwrap();
            } else {
                let _ = thread.join();
            }
        }
    }
}

// @wu-test type=integration | scope=COS HTTP signing, streaming and pagination | protects=private object headers, encoded keys, bounded reads and complete paginated listings survive native transport changes
#[test]
fn cos_transport_preserves_private_headers_streams_and_paginated_objects() {
    let fixture = CosFixture::new();
    let storage = fixture.storage();
    fixture.reply(
        200,
        b"<AccessControlPolicy><AccessControlList/></AccessControlPolicy>",
    );
    fixture.reply(404, b"<Error><Code>NoSuchBucketPolicy</Code></Error>");
    storage.check_private().unwrap();
    assert_eq!(storage.executor(), "tencent-scf");
    assert!(storage.root().is_none());
    fixture.reply(200, b"");
    storage
        .put("data/中文 a+%.json", b"business rows", "application/json")
        .unwrap();
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("upload.parquet");
    fs::write(&path, b"PAR1payloadPAR1").unwrap();
    fixture.reply(200, b"");
    storage
        .put_file("data/rows.parquet", &path, "application/vnd.apache.parquet")
        .unwrap();
    fixture.reply(200, b"PAR1payloadPAR1");
    let target = temp.path().join("download.parquet");
    let hash = hex::encode(sha2::Sha256::digest(b"PAR1payloadPAR1"));
    assert!(storage
        .download_file("data/rows.parquet", &target, Some(15), &hash)
        .unwrap());
    assert_eq!(fs::read(target).unwrap(), b"PAR1payloadPAR1");
    fixture.reply(404, b"<Error><Code>NoSuchKey</Code></Error>");
    assert!(storage.get("data/missing").unwrap().is_none());
    fixture.reply(404, b"<Error><Code>NoSuchVersion</Code></Error>");
    assert!(storage.get("data/retired").unwrap().is_none());
    fixture.reply(403, b"<Error><Code>AccessDenied</Code></Error>");
    assert_eq!(
        storage.get("data/forbidden").unwrap_err().code,
        "AccessDenied"
    );
    fixture.reply(503, b"<Error><Code>unsafe&lt;script&gt;</Code></Error>");
    assert_eq!(
        storage.get("data/failed").unwrap_err().code,
        "COS_REQUEST_FAILED"
    );
    fixture.reply(200, b"too much data");
    assert_eq!(
        storage.get_bounded("data/large", 2).unwrap_err().code,
        "CLOUD_FILE_CORRUPT"
    );
    let first=b"<ListBucketResult><IsTruncated>true</IsTruncated><NextMarker>shares/data/a</NextMarker><Contents><Key>shares/data/a</Key><Size>4</Size></Contents></ListBucketResult>";
    let second=b"<ListBucketResult><IsTruncated>false</IsTruncated><Contents><Key>shares/data/b</Key><Size>8</Size></Contents></ListBucketResult>";
    fixture.reply(200, first);
    fixture.reply(200, second);
    assert_eq!(storage.list("data/").unwrap(), vec!["data/a", "data/b"]);
    fixture.reply(200, first);
    fixture.reply(200, second);
    assert_eq!(storage.size_prefix("data/").unwrap(), 12);
    let requests = fixture.recorded();
    let put = &requests[2];
    assert_eq!(put.method, "PUT");
    assert_eq!(put.target, "/shares/data/%E4%B8%AD%E6%96%87%20a%2B%25.json");
    assert_eq!(put.body, b"business rows");
    assert_eq!(put.headers["x-cos-acl"], "private");
    assert_eq!(put.headers["x-cos-server-side-encryption"], "AES256");
    assert_eq!(put.headers["cache-control"], "private, no-store, max-age=0");
    assert_eq!(
        put.headers["host"],
        "private-bucket.cos.test-region.myqcloud.com"
    );
    assert_eq!(put.headers["x-cos-security-token"], "test-session");
    assert!(put.headers["authorization"].contains("q-ak=test-key-id"));
    assert!(put.headers["authorization"].contains("q-header-list=cache-control;content-type;host;x-cos-acl;x-cos-security-token;x-cos-server-side-encryption"));
    assert_eq!(requests[3].body, b"PAR1payloadPAR1");
    assert_eq!(requests[3].headers["content-length"], "15");
    let pages = requests
        .iter()
        .filter(|r| r.target.contains("marker=shares%2Fdata%2Fa"))
        .count();
    assert_eq!(pages, 2);
    assert!(fixture.replies.lock().unwrap().is_empty());
}

// @wu-test type=boundary | scope=COS privacy and deletion protocol | protects=public bucket ACLs or policies are rejected and physical deletion cannot silently stall or partially fail
#[test]
fn cos_privacy_and_physical_deletion_fail_closed() {
    let fixture = CosFixture::new();
    let storage = fixture.storage();
    for acl in ["not xml","<Wrong/>","<AccessControlPolicy><AccessControlList><Grant><URI>http://acs.amazonaws.com/groups/global/AllUsers</URI></Grant></AccessControlList></AccessControlPolicy>"] {
        fixture.reply(200,acl);assert_eq!(storage.check_private().unwrap_err().code,"COS_BUCKET_NOT_PRIVATE");
    }
    let private = b"<AccessControlPolicy><AccessControlList/></AccessControlPolicy>";
    for policy in [
        json!({}),
        json!({"Statement":[false]}),
        json!({"Statement":{"Effect":"Allow","Principal":"*"}}),
        json!({"statement":[{"effect":"allow","principal":{"qcs":["*"]}}]}),
    ] {
        fixture.reply(200, private);
        fixture.reply(200, serde_json::to_vec(&policy).unwrap());
        assert_eq!(
            storage.check_private().unwrap_err().code,
            "COS_BUCKET_NOT_PRIVATE"
        );
    }
    fixture.reply(200, private);
    fixture.reply(200,br#"{"Statement":[{"Effect":"Deny","Principal":"*"},{"Effect":"Allow","Principal":{"qcs":["qcs::cam::uin/1:uin/1"]}}]}"#);
    storage.check_private().unwrap();
    let versions=b"<ListVersionsResult><IsTruncated>false</IsTruncated><Version><Key>shares/site/a</Key><VersionId>old</VersionId><Size>4</Size></Version><DeleteMarker><Key>shares/site/a</Key><VersionId>removed</VersionId></DeleteMarker></ListVersionsResult>";
    let no_versions = b"<ListVersionsResult><IsTruncated>false</IsTruncated></ListVersionsResult>";
    let objects=b"<ListBucketResult><IsTruncated>false</IsTruncated><Contents><Key>shares/site/b</Key><Size>3</Size></Contents></ListBucketResult>";
    let no_objects = b"<ListBucketResult><IsTruncated>false</IsTruncated></ListBucketResult>";
    fixture.reply(200, versions);
    fixture.reply(200, b"<DeleteResult/>");
    fixture.reply(200, no_versions);
    fixture.reply(200, objects);
    fixture.reply(200, b"<DeleteResult/>");
    fixture.reply(200, no_objects);
    fixture.reply(200, no_versions);
    storage.delete_prefix("site/").unwrap();
    let deletes = fixture
        .recorded()
        .into_iter()
        .filter(|r| r.method == "POST")
        .collect::<Vec<_>>();
    assert_eq!(deletes.len(), 2);
    assert!(String::from_utf8_lossy(&deletes[0].body).contains("<VersionId>old</VersionId>"));
    assert!(String::from_utf8_lossy(&deletes[0].body).contains("<VersionId>removed</VersionId>"));
    assert_eq!(
        deletes[0].headers["content-md5"],
        STANDARD.encode(<md5::Md5 as md5::Digest>::digest(&deletes[0].body))
    );
    fixture.reply(200, versions);
    fixture.reply(200, b"<DeleteResult/>");
    fixture.reply(200, versions);
    assert_eq!(
        storage.delete_prefix("site/").unwrap_err().code,
        "COS_DELETE_FAILED"
    );
    for response in [
        "invalid",
        "<Wrong/>",
        "<DeleteResult><Error><Code>AccessDenied</Code></Error></DeleteResult>",
    ] {
        fixture.reply(200, versions);
        fixture.reply(200, response);
        assert_eq!(
            storage.delete_prefix("site/").unwrap_err().code,
            "COS_DELETE_FAILED"
        );
    }
    assert!(fixture.replies.lock().unwrap().is_empty());
}

// @wu-test type=boundary | scope=temporary storage credentials | protects=malformed or expired credentials cannot be cached and all supported expiry representations keep the safety margin
#[test]
fn temporary_credentials_validate_content_and_expiration_before_caching() {
    let epoch = 1_800_000_000;
    let credentials = json!({"code":0,"data":{"TmpSecretId":"temporary-id","TmpSecretKey":"temporary-key","Token":"temporary-token"}});
    let (parsed, lifetime) =
        parse_credentials(&serde_json::to_vec(&credentials).unwrap(), epoch).unwrap();
    assert_eq!(parsed.id, "temporary-id");
    assert_eq!(parsed.key, "temporary-key");
    assert_eq!(parsed.token, "temporary-token");
    assert_eq!(lifetime, Duration::from_secs(1200));
    for (key, value) in [
        ("ExpiredTime", json!(epoch + 300)),
        ("expiredTime", json!((epoch + 300).to_string())),
        (
            "Expiration",
            json!(chrono::DateTime::from_timestamp(epoch + 300, 0)
                .unwrap()
                .to_rfc3339()),
        ),
        ("expiration", json!(epoch + 300)),
    ] {
        let mut response = credentials.clone();
        response["data"][key] = value;
        assert_eq!(
            parse_credentials(&serde_json::to_vec(&response).unwrap(), epoch)
                .unwrap()
                .1,
            Duration::from_secs(240)
        );
    }
    let mut expired = credentials.clone();
    expired["data"]["ExpiredTime"] = json!(epoch + 60);
    assert_eq!(
        parse_credentials(&serde_json::to_vec(&expired).unwrap(), epoch)
            .err()
            .unwrap()
            .code,
        "CLOUD_CREDENTIAL_UNAVAILABLE"
    );
    for invalid in [
        json!({"code":403}),
        json!({"code":0,"data":{}}),
        json!({"code":0,"data":{"TmpSecretId":"id","TmpSecretKey":"key","Token":""}}),
    ] {
        assert_eq!(
            parse_credentials(&serde_json::to_vec(&invalid).unwrap(), epoch)
                .err()
                .unwrap()
                .code,
            "CLOUD_CREDENTIAL_UNAVAILABLE"
        );
    }
    assert_eq!(
        parse_credentials(b"invalid-json", epoch)
            .err()
            .unwrap()
            .code,
        "CLOUD_CREDENTIAL_UNAVAILABLE"
    );
}

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
