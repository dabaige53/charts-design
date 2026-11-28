use super::*;
// @wu-test type=unit | scope=serialization | protects=existing Python data hashes and null/number distinctions
#[test]
fn python_json_vectors() {
    for (input, expected) in [
        ("1.0", "1.0"),
        ("-0.0", "-0.0"),
        ("1e-7", "1e-07"),
        ("1e16", "1e+16"),
        ("1.2e20", "1.2e+20"),
        ("0.0001", "0.0001"),
        ("1000000000000000.0", "1000000000000000.0"),
        ("1.2345e-8", "1.2345e-08"),
        ("1234567890123456789", "1234567890123456789"),
    ] {
        assert_eq!(
            canonical_json(&serde_json::from_str(input).unwrap()).unwrap(),
            expected
        );
    }
    let value: Value = serde_json::from_str(r#"{"乙":null,"a":[true,1,1.0],"甲":"值"}"#).unwrap();
    assert_eq!(
        canonical_json(&value).unwrap(),
        r#"{"a":[true,1,1.0],"乙":null,"甲":"值"}"#
    );
    assert_eq!(
        python_json(&value, true, true).unwrap(),
        r#"{"a": [true, 1, 1.0], "乙": null, "甲": "值"}"#
    );
}
#[test]
fn browser_number_equality_preserves_large_integer_and_hash_boundaries() {
    for (left, right, expected) in [
        ("0", "-0.0", true),
        ("1", "1.0", true),
        ("1", "1.1", false),
        ("9007199254740992", "9007199254740992.0", true),
        ("9007199254740993", "9007199254740992.0", false),
        ("18446744073709551615", "18446744073709551616.0", false),
        ("-9223372036854775808", "-9223372036854775808.0", true),
        ("true", "1", false),
        ("null", "0", false),
        (r#"{"a":[0,1]}"#, r#"{"a":[-0.0,1.0]}"#, true),
    ] {
        let left: Value = serde_json::from_str(left).unwrap();
        let right: Value = serde_json::from_str(right).unwrap();
        assert_eq!(equivalent_json(&left, &right), expected);
        assert_eq!(equivalent_json(&right, &left), expected);
        assert_ne!(json_bytes(&left).unwrap(), json_bytes(&right).unwrap());
    }
}
