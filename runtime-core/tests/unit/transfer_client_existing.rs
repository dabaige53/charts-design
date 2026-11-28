use super::*;
use std::sync::atomic::AtomicUsize;

// @wu-test type=boundary | scope=MCP event decoding | protects=notifications or another request response cannot substitute for a transfer result
#[test]
fn event_decoder_selects_the_matching_response() {
    let body = concat!(
        ": ping\r\n\r\n",
        "data: {\"jsonrpc\":\"2.0\",\"method\":\"notifications/progress\"}\n\n",
        "data: {\"jsonrpc\":\"2.0\",\"id\":2,\n",
        "data: \"result\":{\"state\":\"complete\"}}\n\n"
    );
    assert_eq!(
        event_value(std::io::Cursor::new(body), 2).unwrap()["result"]["state"],
        "complete"
    );
    assert!(event_value(std::io::Cursor::new(body), 3).is_err());
    assert!(event_value(std::io::Cursor::new("data: nope\n\n"), 2).is_err());
}
struct Destination {
    local: LocalData,
    parts: Mutex<BTreeMap<u64, Vec<Value>>>,
    sent: Mutex<Vec<u64>>,
    saved: Mutex<Option<Value>>,
}
impl ToolCaller for Destination {
    fn call(&self, tool: &str, args: &Value) -> Result<Value> {
        if tool == "dataset_transfer_status" {
            if let Some(reference) = self.saved.lock().unwrap().as_ref() {
                return Ok(json!({"state":"complete","ref":reference}));
            }
            let mut received = Map::new();
            for part in args["parts"].as_array().into_iter().flatten() {
                if let Some(rows) = self.parts.lock().unwrap().get(&part.as_u64().unwrap()) {
                    received.insert(
                        part.to_string(),
                        json!(hex::encode(Sha256::digest(json_bytes(&json!(rows))?))),
                    );
                }
            }
            return Ok(json!({"state":"unknown","receivedParts":received}));
        }
        if tool == "dataset_transfer_chunk" {
            let part = args["part"].as_u64().unwrap();
            self.sent.lock().unwrap().push(part);
            self.parts
                .lock()
                .unwrap()
                .insert(part, args["rows"].as_array().unwrap().clone());
            return Ok(json!({"part":part,"complete":false}));
        }
        assert_eq!(tool, "dataset_transfer_finish");
        let rows = self
            .parts
            .lock()
            .unwrap()
            .values()
            .flatten()
            .cloned()
            .collect::<Vec<_>>();
        let value = self
            .local
            .import_rows(&rows, &ordered_fields(&args["ref"])?)?;
        require(value == args["ref"], "Transfer differs", "DATA_CONFLICT")?;
        *self.saved.lock().unwrap() = Some(value.clone());
        Ok(json!({"state":"complete","ref":value}))
    }
}
// @wu-test type=integration | scope=native resumable transfer client | protects=lost chunk acknowledgments cause receipt-based reuse and missing fields survive source streaming
#[test]
fn resumed_client_reuses_remote_chunks_and_verifies_content_hash() {
    let directory = tempfile::tempdir().unwrap();
    let root = directory.path();
    let source = LocalData::new(Some(&root.join("data"))).unwrap();
    let rows = (0..501)
        .map(|index| {
            if index % 3 == 0 {
                json!({"v":index})
            } else {
                json!({"v":index,"label":"华东","flag":true})
            }
        })
        .collect::<Vec<_>>();
    let value = source
        .import_rows(
            &rows,
            &json!({"v":{"type":"number"},"label":{"type":"string"},"flag":{"type":"boolean"}}),
        )
        .unwrap();
    let destination = Arc::new(Destination {
        local: LocalData::new(None).unwrap(),
        parts: Mutex::new(BTreeMap::from([(0, rows[..250].to_vec())])),
        sent: Mutex::new(Vec::new()),
        saved: Mutex::new(None),
    });
    let options = json!({"state":root.join("state.json"),"concurrency":4});
    let mut client = TransferClient::new(
        destination.clone(),
        root,
        "https://example.test/mcp",
        "project",
        &options,
        false,
    )
    .unwrap();
    let version = value["version"].as_str().unwrap();
    client.state["uploads"][version] = json!("a".repeat(64));
    client.save().unwrap();
    client.check_source(&value).unwrap();
    assert_eq!(client.transfer(&value, false).unwrap(), value);
    let mut sent = destination.sent.lock().unwrap().clone();
    sent.sort();
    assert_eq!(sent, vec![1, 2]);
    assert_eq!(destination.local.all_rows(&value).unwrap(), rows);
    assert_eq!(
        load_json(&root.join("state.json")).unwrap()["staged"],
        json!([version])
    );
    assert!(TransferClient::new(
        destination.clone(),
        root,
        "https://example.test/mcp",
        "project",
        &options,
        false
    )
    .is_err());
    drop(client);
    assert_eq!(
        TransferClient::new(
            destination,
            root,
            "https://other.test/mcp",
            "project",
            &options,
            false
        )
        .err()
        .unwrap()
        .code,
        "DATA_CONFLICT"
    );
}
struct Failure {
    started: AtomicUsize,
    active: AtomicUsize,
    completed: AtomicUsize,
}
impl ToolCaller for Failure {
    fn call(&self, _: &str, args: &Value) -> Result<Value> {
        self.started.fetch_add(1, Ordering::SeqCst);
        self.active.fetch_add(1, Ordering::SeqCst);
        let part = args["part"].as_u64().unwrap();
        std::thread::sleep(Duration::from_millis(if part == 0 { 5 } else { 40 }));
        self.active.fetch_sub(1, Ordering::SeqCst);
        self.completed.fetch_add(1, Ordering::SeqCst);
        if part == 0 {
            Err(Error::new("NETWORK_FAILURE", "test failure"))
        } else {
            Ok(json!({"part":part,"complete":false}))
        }
    }
}
// @wu-test type=boundary | scope=parallel transfer failure | protects=failed uploads wait for every inflight request and never continue into another window
#[test]
fn failed_upload_joins_all_inflight_requests() {
    let directory = tempfile::tempdir().unwrap();
    let caller = Arc::new(Failure {
        started: AtomicUsize::new(0),
        active: AtomicUsize::new(0),
        completed: AtomicUsize::new(0),
    });
    let options = json!({"state":directory.path().join("state.json"),"concurrency":4});
    let client = TransferClient::new(
        caller.clone(),
        directory.path(),
        "https://example.test/mcp",
        "project",
        &options,
        false,
    )
    .unwrap();
    let block = (0..8).map(|part| (part, vec![json!({"v":part})])).collect();
    assert_eq!(
        client
            .upload_window(&json!({}), block, false)
            .unwrap_err()
            .code,
        "NETWORK_FAILURE"
    );
    assert_eq!(caller.started.load(Ordering::SeqCst), 4);
    assert_eq!(caller.completed.load(Ordering::SeqCst), 4);
    assert_eq!(caller.active.load(Ordering::SeqCst), 0);
}
