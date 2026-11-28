use super::*;
use std::sync::atomic::{AtomicUsize, Ordering};

// @wu-test type=boundary | scope=ordered cloud chunk restore | protects=concurrent fetching changes data hashes or a missing chunk becomes a silently truncated dataset
#[test]
fn chunk_restore_keeps_order_and_rejects_incomplete_results() {
    let progress = Arc::new(Mutex::new(Vec::new()));
    let recorded = progress.clone();
    let rows = ChunkRows::new(7, 2, |part| {
        Ok(json!((part * 2..(part * 2 + 2).min(7))
            .map(|n| json!({"n":n}))
            .collect::<Vec<_>>()))
    })
    .with_progress(move |part| recorded.lock().unwrap().push(part))
    .collect::<Result<Vec<_>>>()
    .unwrap();
    assert_eq!(rows, (0..7).map(|n| json!({"n":n})).collect::<Vec<_>>());
    assert_eq!(*progress.lock().unwrap(), vec![1, 2, 3, 4]);

    for invalid in [Value::Null, json!([]), json!([1, 2, 3])] {
        let finished = Arc::new(AtomicUsize::new(0));
        let calls = finished.clone();
        let mut chunks = ChunkRows::new(8, 2, move |part| {
            calls.fetch_add(1, Ordering::SeqCst);
            Ok(if part == 0 {
                invalid.clone()
            } else {
                json!([1, 2])
            })
        });
        assert_eq!(chunks.next().unwrap().unwrap_err().code, "DATA_INCOMPLETE");
        assert!(chunks.next().is_none());
        drop(chunks);
        assert_eq!(finished.load(Ordering::SeqCst), 4);
    }
    let mut panic = ChunkRows::new(1, 1, |_| panic!("simulated broken source"));
    assert_eq!(panic.next().unwrap().unwrap_err().code, "DATA_INCOMPLETE");
    let mut failed = ChunkRows::new(1, 1, |_| {
        Err(Error::new("SOURCE_UNAVAILABLE", "lost source"))
    });
    assert_eq!(
        failed.next().unwrap().unwrap_err().code,
        "SOURCE_UNAVAILABLE"
    );
}

// @wu-test type=boundary | scope=cloud dataset field metadata | protects=PostgreSQL JSONB ordering changes immutable dataset versions or malformed field order drops columns
#[test]
fn field_order_is_explicit_complete_and_unique() {
    let value =
        json!({"fields":{"b":{"type":"string"},"a":{"type":"number"}},"fieldOrder":["a","b"]});
    assert_eq!(
        ordered_fields(&value)
            .unwrap()
            .as_object()
            .unwrap()
            .keys()
            .collect::<Vec<_>>(),
        vec!["a", "b"]
    );
    assert_eq!(
        ordered_fields(&json!({"fields":value["fields"]})).unwrap(),
        value["fields"]
    );
    for invalid in [
        json!({"fields":null}),
        json!({"fields":value["fields"],"fieldOrder":"a"}),
        json!({"fields":value["fields"],"fieldOrder":["a"]}),
        json!({"fields":value["fields"],"fieldOrder":["a","a"]}),
        json!({"fields":value["fields"],"fieldOrder":["a","unknown"]}),
        json!({"fields":value["fields"],"fieldOrder":["a",1]}),
    ] {
        assert_eq!(ordered_fields(&invalid).unwrap_err().code, "DATA_CONFLICT");
    }
}
