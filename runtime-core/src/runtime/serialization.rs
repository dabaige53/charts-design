//! Stable JSON and timestamps shared by persistence and content addressing.
use super::error::{require, Result};
use serde_json::Value;

pub fn utcnow() -> String {
    chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Micros, false)
}

/// Match Python's finite float representation used by existing dataset hashes.
/// serde's shortest digits are retained; only fixed/exponent notation is changed.
fn float_text(value: &serde_json::Number) -> String {
    let raw = value.to_string();
    if !value.is_f64() {
        return raw;
    }
    let (negative, body) = raw
        .strip_prefix('-')
        .map_or((false, raw.as_str()), |v| (true, v));
    let (mantissa, power) = body
        .split_once(['e', 'E'])
        .map_or((body, 0_i32), |(m, e)| (m, e.parse().unwrap_or(0)));
    let decimal = mantissa.find('.').unwrap_or(mantissa.len()) as i32;
    let mut digits: String = mantissa.chars().filter(|c| *c != '.').collect();
    let leading = digits.bytes().take_while(|b| *b == b'0').count();
    if leading == digits.len() {
        return if negative { "-0.0" } else { "0.0" }.into();
    }
    let exponent = decimal + power - leading as i32 - 1;
    digits.drain(..leading);
    while digits.len() > 1 && digits.ends_with('0') {
        digits.pop();
    }
    let mut out = if negative {
        "-".to_owned()
    } else {
        String::new()
    };
    if !(-4..16).contains(&exponent) {
        out.push(digits.as_bytes()[0] as char);
        if digits.len() > 1 {
            out.push('.');
            out.push_str(&digits[1..]);
        }
        out.push('e');
        out.push(if exponent < 0 { '-' } else { '+' });
        out.push_str(&format!("{:02}", exponent.unsigned_abs()));
    } else {
        let position = exponent + 1;
        if position <= 0 {
            out.push_str("0.");
            out.extend(std::iter::repeat_n('0', (-position) as usize));
            out.push_str(&digits);
        } else if position as usize >= digits.len() {
            out.push_str(&digits);
            out.extend(std::iter::repeat_n('0', position as usize - digits.len()));
            out.push_str(".0");
        } else {
            out.push_str(&digits[..position as usize]);
            out.push('.');
            out.push_str(&digits[position as usize..]);
        }
    }
    out
}

/// `spaced` selects Python json.dumps' default separators, not indentation.
pub fn python_json(value: &Value, sort_keys: bool, spaced: bool) -> Result<String> {
    fn write(value: &Value, sort: bool, spaced: bool, out: &mut String) {
        let comma = if spaced { ", " } else { "," };
        match value {
            Value::Null => out.push_str("null"),
            Value::Bool(v) => out.push_str(if *v { "true" } else { "false" }),
            Value::Number(n) => out.push_str(&float_text(n)),
            Value::String(v) => {
                out.push_str(&serde_json::to_string(v).expect("JSON string serialization"))
            }
            Value::Array(values) => {
                out.push('[');
                for (i, v) in values.iter().enumerate() {
                    if i > 0 {
                        out.push_str(comma);
                    }
                    write(v, sort, spaced, out);
                }
                out.push(']');
            }
            Value::Object(values) => {
                out.push('{');
                let mut keys: Vec<_> = values.keys().collect();
                if sort {
                    keys.sort();
                }
                for (i, key) in keys.iter().enumerate() {
                    if i > 0 {
                        out.push_str(comma);
                    }
                    out.push_str(&serde_json::to_string(key).expect("JSON key serialization"));
                    out.push_str(if spaced { ": " } else { ":" });
                    write(&values[*key], sort, spaced, out);
                }
                out.push('}');
            }
        }
    }
    let mut out = String::new();
    write(value, sort_keys, spaced, &mut out);
    Ok(out)
}

pub fn canonical_json(value: &Value) -> Result<String> {
    python_json(value, true, false)
}
pub fn json_bytes(value: &Value) -> Result<Vec<u8>> {
    let bytes = python_json(value, false, false)?.into_bytes();
    require(
        bytes.len() <= 16 * 1024 * 1024,
        "Artifact exceeds 16 MiB",
        "PAYLOAD_TOO_LARGE",
    )?;
    Ok(bytes)
}

/// Compare JSON values across browser round trips without conflating booleans
/// with numbers or rounding large integers through f64. Content hashes still
/// use the exact original number representation in `json_bytes`.
pub fn equivalent_json(left: &Value, right: &Value) -> bool {
    fn integer(number: &serde_json::Number) -> Option<i128> {
        number
            .as_i64()
            .map(i128::from)
            .or_else(|| number.as_u64().map(i128::from))
    }
    fn integer_float(value: i128, float: f64) -> bool {
        float.is_finite()
            && float.fract() == 0.0
            && (i64::MIN as f64..u64::MAX as f64).contains(&float)
            && float as i128 == value
    }
    match (left, right) {
        (Value::Number(a), Value::Number(b)) => match (integer(a), integer(b)) {
            (Some(a), Some(b)) => a == b,
            (Some(a), None) => b.as_f64().is_some_and(|b| integer_float(a, b)),
            (None, Some(b)) => a.as_f64().is_some_and(|a| integer_float(b, a)),
            (None, None) => a == b,
        },
        (Value::Array(a), Value::Array(b)) => {
            a.len() == b.len() && a.iter().zip(b).all(|(a, b)| equivalent_json(a, b))
        }
        (Value::Object(a), Value::Object(b)) => {
            a.len() == b.len()
                && a.iter()
                    .all(|(key, a)| b.get(key).is_some_and(|b| equivalent_json(a, b)))
        }
        _ => left == right,
    }
}

#[cfg(test)]
#[path = "../../tests/unit/serialization.rs"]
mod tests;
