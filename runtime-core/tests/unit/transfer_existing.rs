use super::*;
use crate::runtime::data::LocalData;
use std::time::{Duration, Instant};

fn setup(path: &std::path::Path) -> (Transfers, Arc<LocalBackend>, Value, Vec<Value>) {
    let rows = (0..501)
        .map(|index| {
            if index % 5 == 0 {
                json!({"label":"华东","value":index})
            } else {
                json!({"label":null,"value":index,"enabled":index%2==0})
            }
        })
        .collect::<Vec<_>>();
    let source = LocalData::new(None).unwrap();
    let reference = source.import_rows(&rows, &json!({"label":{"type":"string"},"value":{"type":"number"},"enabled":{"type":"boolean"}})).unwrap();
    let backend = Arc::new(LocalBackend {
        data: LocalData::new(Some(&path.join("data"))).unwrap(),
        staging: path.join("objects"),
    });
    let manager = Transfers {
        backend: backend.clone(),
        registry: Arc::new(Registry::default()),
        project: "test".into(),
    };
    (manager, backend, reference, rows)
}
fn completed(manager: &Transfers, upload: &str, reference: &Value, bulk: bool) -> Value {
    let start = Instant::now();
    loop {
        let result = manager.status(upload, reference, None, bulk).unwrap();
        if result["state"] != "running" {
            return result;
        }
        assert!(
            start.elapsed() < Duration::from_secs(5),
            "transfer did not finish"
        );
        std::thread::sleep(Duration::from_millis(5));
    }
}

// @wu-test type=boundary | scope=compressed transfer payload | protects=oversized decompression, appended gzip members and noncanonical JSON cannot enter a dataset
#[test]
fn bulk_payload_is_bounded_and_exact() {
    let rows = json!([{"value":1.0,"label":"华东"},{"value":null}]);
    let raw = json_bytes(&rows).unwrap();
    let encoded = encode_bulk(&raw).unwrap();
    let compressed = bulk_binary(&encoded).unwrap();
    assert_eq!(bulk_rows(&bulk_raw(&compressed).unwrap(), 2).unwrap(), rows);
    let mut trailing = compressed.clone();
    trailing.extend_from_slice(&compressed);
    assert!(bulk_raw(&trailing).is_err());
    assert!(bulk_binary("not base64!").is_err());
    assert!(bulk_rows(b"[ {\"value\":1} ]", 1).is_err());
    assert!(bulk_rows(b"[1]", 1).is_err());
    let bomb = gzip(&vec![b' '; BULK_DECODED + 1]).unwrap();
    assert!(bulk_raw(&bomb).is_err());
    assert!(reference(&json!({"version":"a".repeat(64),"rowCount":1,"fields":{"v":{"type":"number"}},"fieldOrder":["v","v"]})).is_err());
}

// @wu-test type=integration | scope=resumable native transfer | protects=duplicate chunks stay idempotent, receipts match canonical hashes and completed references retain source data
#[test]
fn native_transfer_validates_receipts_and_commits_once() {
    let directory = tempfile::tempdir().unwrap();
    let (manager, backend, reference, rows) = setup(directory.path());
    let upload = "a".repeat(64);
    let first = json!(&rows[..250]);
    assert_eq!(
        manager
            .chunk(&upload, &reference, 0, Some(&first), false, None)
            .unwrap(),
        json!({"complete":false,"part":0})
    );
    manager
        .chunk(&upload, &reference, 0, Some(&first), false, None)
        .unwrap();
    let mut changed = first.clone();
    changed[0]["value"] = json!(9999);
    assert_eq!(
        manager
            .chunk(&upload, &reference, 0, Some(&changed), false, None)
            .unwrap_err()
            .code,
        "DATA_CONFLICT"
    );
    let status = manager
        .status(&upload, &reference, Some(&json!([0, 1, 2])), false)
        .unwrap();
    assert_eq!(
        status["receivedParts"]["0"],
        hex::encode(Sha256::digest(json_bytes(&first).unwrap()))
    );
    assert!(status["receivedParts"].get("1").is_none());
    manager
        .chunk(
            &upload,
            &reference,
            1,
            Some(&json!(&rows[250..500])),
            false,
            None,
        )
        .unwrap();
    manager
        .chunk(
            &upload,
            &reference,
            2,
            Some(&json!(&rows[500..])),
            false,
            None,
        )
        .unwrap();
    assert_eq!(
        manager.finish(&upload, &reference, false).unwrap()["state"],
        "running"
    );
    let result = completed(&manager, &upload, &reference, false);
    assert_eq!(result, json!({"state":"complete","ref":reference}));
    assert_eq!(backend.data.all_rows(&reference).unwrap(), rows);
    assert!(backend
        .storage()
        .unwrap()
        .list(&manager.prefix(&upload, false))
        .unwrap()
        .is_empty());
    assert_eq!(manager.finish(&upload, &reference, false).unwrap(), result);
    assert_eq!(
        manager
            .chunk(&upload, &reference, 0, Some(&first), false, None)
            .unwrap()["complete"],
        true
    );
}

// @wu-test type=integration | scope=transfer integrity failures | protects=missing chunks and mismatched content hashes never publish remote metadata
#[test]
fn incomplete_and_conflicting_transfers_never_publish() {
    let directory = tempfile::tempdir().unwrap();
    let (manager, backend, reference, rows) = setup(directory.path());
    let upload = "b".repeat(64);
    manager.finish(&upload, &reference, false).unwrap();
    assert_eq!(
        completed(&manager, &upload, &reference, false)["code"],
        "DATA_INCOMPLETE"
    );
    let mut wrong = reference.clone();
    wrong["version"] = json!("f".repeat(64));
    let payload = json!(encode_bulk(&json_bytes(&json!(rows)).unwrap()).unwrap());
    manager
        .chunk(&upload, &wrong, 0, None, true, Some(&payload))
        .unwrap();
    manager.finish(&upload, &wrong, true).unwrap();
    assert_eq!(
        completed(&manager, &upload, &wrong, true)["code"],
        "DATA_CONFLICT"
    );
    let version = reference["version"].as_str().unwrap();
    assert!(backend
        .data
        .find_local_reference(version)
        .unwrap()
        .is_none());
    let wrong_version = wrong["version"].as_str().unwrap();
    assert!(backend
        .data
        .find_local_reference(wrong_version)
        .unwrap()
        .is_none());
    assert!(manager
        .status(&upload, &wrong, Some(&json!([0, 0])), true)
        .is_err());
}
