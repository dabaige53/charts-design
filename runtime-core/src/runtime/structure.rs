//! Sanitized, data-independent diagrams shared by all component renderers.
use super::{
    error::{require, Error, Result},
    model::identifier,
};
use serde_json::{json, Value};
use std::sync::OnceLock;
const TAGS: &[&str] = &[
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text",
    "tspan", "title", "desc",
];
const ATTRS: &[&str] = &[
    "x",
    "y",
    "x1",
    "y1",
    "x2",
    "y2",
    "cx",
    "cy",
    "r",
    "rx",
    "ry",
    "width",
    "height",
    "d",
    "points",
    "fill",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-dasharray",
    "opacity",
    "fill-opacity",
    "stroke-opacity",
    "fill-rule",
    "transform",
    "font-size",
    "font-weight",
    "text-anchor",
    "dominant-baseline",
];
pub fn presentation(c: &Value) -> &Value {
    static EMPTY: OnceLock<Value> = OnceLock::new();
    let empty = EMPTY.get_or_init(|| json!({}));
    let owner = if c["kind"] == "legacy" {
        c.get("config").unwrap_or(empty)
    } else {
        c
    };
    owner.get("presentation").unwrap_or(empty)
}
fn presentation_mut(c: &mut Value) -> Result<&mut Value> {
    if c["kind"] == "legacy" {
        if c.get("config").is_none() {
            c["config"] = json!({});
        }
        require(
            c["config"].is_object(),
            "Component config must be an object",
            "INVALID_DOCUMENT",
        )?;
        if c["config"].get("presentation").is_none() {
            c["config"]["presentation"] = json!({});
        }
        Ok(&mut c["config"]["presentation"])
    } else {
        if c.get("presentation").is_none() {
            c["presentation"] = json!({});
        }
        Ok(&mut c["presentation"])
    }
}
fn escape(s: &str, attr: bool) -> String {
    let mut out = s
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;");
    if attr {
        out = out.replace('"', "&quot;");
    }
    out
}
pub fn sanitize_svg(svg: &str, view_box: &Value) -> Result<String> {
    require(
        !svg.is_empty() && svg.chars().count() <= 100000,
        "structureDiagram.svg must contain 1–100000 characters",
        "INVALID_DOCUMENT",
    )?;
    static DECLARATIONS: OnceLock<regex::Regex> = OnceLock::new();
    let declarations = DECLARATIONS
        .get_or_init(|| regex::Regex::new(r"(?i)<!\s*(DOCTYPE|ENTITY)").expect("constant regex"));
    require(
        !declarations.is_match(svg),
        "SVG declarations and entities are forbidden",
        "INVALID_DOCUMENT",
    )?;
    let doc = roxmltree::Document::parse(svg).map_err(|e| {
        Error::new(
            "INVALID_DOCUMENT",
            format!("Invalid structureDiagram SVG: {e}"),
        )
    })?;
    let root = doc.root_element();
    require(
        root.tag_name().name() == "svg"
            && root
                .tag_name()
                .namespace()
                .is_none_or(|n| n == "http://www.w3.org/2000/svg"),
        "structureDiagram.svg must have an SVG root",
        "INVALID_DOCUMENT",
    )?;
    require(
        root.descendants().filter(|n| n.is_element()).count() <= 2000,
        "Structure SVG allows at most 2000 elements",
        "INVALID_DOCUMENT",
    )?;
    fn write(node: roxmltree::Node<'_, '_>, root: bool, view_box: &Value, out: &mut String) {
        let tag = node.tag_name();
        if !root
            && (!TAGS.contains(&tag.name())
                || tag.name() == "svg"
                || tag
                    .namespace()
                    .is_some_and(|n| n != "http://www.w3.org/2000/svg"))
        {
            return;
        }
        out.push('<');
        out.push_str(tag.name());
        static URL_PAINT: OnceLock<regex::Regex> = OnceLock::new();
        let forbidden =
            URL_PAINT.get_or_init(|| regex::Regex::new(r"url\s*\(").expect("constant regex"));
        for a in node.attributes() {
            let lower = a.value().to_lowercase();
            if a.namespace().is_none()
                && ATTRS.contains(&a.name())
                && !forbidden.is_match(&lower)
                && !a.value().chars().any(|c| "<>&\\".contains(c))
                && !a.value().contains("://")
            {
                out.push(' ');
                out.push_str(a.name());
                out.push_str("=\"");
                out.push_str(&escape(a.value(), true));
                out.push('"');
            }
        }
        if root {
            out.push_str(" xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"");
            let s = view_box
                .as_array()
                .map(|a| a.iter().map(Value::to_string).collect::<Vec<_>>().join(" "))
                .unwrap_or_default();
            out.push_str(&s);
            out.push('"');
        }
        if !node.has_children() {
            out.push_str(" />");
            return;
        }
        out.push('>');
        for child in node.children() {
            if child.is_element() {
                write(child, false, view_box, out);
            } else if child.is_text() {
                out.push_str(&escape(child.text().unwrap_or(""), false));
            }
        }
        out.push_str("</");
        out.push_str(tag.name());
        out.push('>');
    }
    let mut out = String::new();
    write(root, true, view_box, &mut out);
    Ok(out)
}
pub fn normalize(diagram: &Value) -> Result<Value> {
    require(
        diagram.is_object(),
        "structureDiagram must be an object",
        "INVALID_DOCUMENT",
    )?;
    require(
        diagram["version"] == 1,
        "structureDiagram.version must be 1",
        "INVALID_DOCUMENT",
    )?;
    let box_ = diagram["viewBox"].as_array().ok_or_else(|| {
        Error::new(
            "INVALID_DOCUMENT",
            "structureDiagram.viewBox must contain four finite numbers",
        )
    })?;
    require(
        box_.len() == 4 && box_.iter().all(|v| v.as_f64().is_some_and(f64::is_finite)),
        "structureDiagram.viewBox must contain four finite numbers",
        "INVALID_DOCUMENT",
    )?;
    let nums: Vec<_> = box_.iter().map(|v| v.as_f64().unwrap_or(0.)).collect();
    require(
        nums[0] == 0.
            && nums[1] == 0.
            && nums[2] > 0.
            && nums[2] <= 10000.
            && nums[3] > 0.
            && nums[3] <= 10000.,
        "structureDiagram.viewBox must be [0, 0, width, height], dimensions 0–10000",
        "INVALID_DOCUMENT",
    )?;
    let annotations = diagram["annotations"].as_array().ok_or_else(|| {
        Error::new(
            "INVALID_DOCUMENT",
            "structureDiagram requires 1–32 annotations",
        )
    })?;
    require(
        (1..=32).contains(&annotations.len()),
        "structureDiagram requires 1–32 annotations",
        "INVALID_DOCUMENT",
    )?;
    let mut seen = std::collections::HashSet::new();
    for item in annotations {
        require(
            item.is_object(),
            "Structure annotation must be an object",
            "INVALID_DOCUMENT",
        )?;
        let key = identifier(&item["id"], "annotation id")?;
        require(
            seen.insert(key.clone()),
            "Structure annotation IDs must be unique",
            "INVALID_DOCUMENT",
        )?;
        for point in ["anchor", "label"] {
            let valid = item[point].as_array().is_some_and(|a| {
                a.len() == 2
                    && a.iter().enumerate().all(|(i, v)| {
                        v.as_f64()
                            .is_some_and(|v| v.is_finite() && v >= 0. && v <= nums[i + 2])
                    })
            });
            require(
                valid,
                format!("{key}.{point} must be inside viewBox"),
                "INVALID_DOCUMENT",
            )?;
        }
        require(
            ["left", "center", "right"].contains(
                &item
                    .get("align")
                    .map_or("center", |v| v.as_str().unwrap_or("")),
            ),
            format!("{key}: invalid label alignment"),
            "INVALID_DOCUMENT",
        )?;
        if let Some(metric) = item.get("metricId") {
            identifier(metric, "metric reference")?;
            require(
                item.get("name").is_none() && item.get("description").is_none(),
                format!("{key}: metric references must not duplicate name or description"),
                "INVALID_DOCUMENT",
            )?;
        } else {
            require(
                item["name"]
                    .as_str()
                    .is_some_and(|s| !s.trim().is_empty() && s.trim().chars().count() <= 120),
                format!("{key}: annotation name required (1–120 characters)"),
                "INVALID_DOCUMENT",
            )?;
        }
        require(
            item.get("description")
                .is_none_or(|v| v.as_str().is_some_and(|s| s.chars().count() <= 2000)),
            format!("{key}: description must be at most 2000 characters"),
            "INVALID_DOCUMENT",
        )?;
    }
    require(
        ["ready", "stale"].contains(
            &diagram
                .get("status")
                .map_or("ready", |v| v.as_str().unwrap_or("")),
        ),
        "Invalid structureDiagram status",
        "INVALID_DOCUMENT",
    )?;
    let svg = diagram["svg"]
        .as_str()
        .ok_or_else(|| Error::new("INVALID_DOCUMENT", "structureDiagram.svg must be a string"))?;
    let mut result = diagram.clone();
    result["svg"] = sanitize_svg(svg, &diagram["viewBox"])?.into();
    if result.get("status").is_none() {
        result["status"] = "ready".into();
    }
    Ok(result)
}
pub fn validate(c: &Value) -> Result<()> {
    require(
        c["kind"] != "legacy" || c.get("config").is_none_or(Value::is_object),
        "Component config must be an object",
        "INVALID_DOCUMENT",
    )?;
    let p = presentation(c);
    require(
        p.is_object(),
        "Presentation must be an object",
        "INVALID_DOCUMENT",
    )?;
    if let Some(d) = p.get("structureDiagram") {
        normalize(d)?;
    }
    Ok(())
}
pub fn normalize_component(c: &mut Value) -> Result<()> {
    require(
        c["kind"] != "legacy" || c.get("config").is_none_or(Value::is_object),
        "Component config must be an object",
        "INVALID_DOCUMENT",
    )?;
    require(
        presentation(c).is_object(),
        "Presentation must be an object",
        "INVALID_DOCUMENT",
    )?;
    if let Some(d) = presentation(c).get("structureDiagram") {
        let normalized = normalize(d)?;
        presentation_mut(c)?["structureDiagram"] = normalized;
    }
    Ok(())
}
pub fn update(previous: Option<&Value>, c: &mut Value) -> Result<()> {
    require(
        c["kind"] != "legacy" || c.get("config").is_none_or(Value::is_object),
        "Component config must be an object",
        "INVALID_DOCUMENT",
    )?;
    let p = presentation(c);
    require(
        p.is_object(),
        "Presentation must be an object",
        "INVALID_DOCUMENT",
    )?;
    if let Some(d) = p.get("structureDiagram") {
        let mut d = normalize(d)?;
        d["status"] = "ready".into();
        presentation_mut(c)?["structureDiagram"] = d;
    } else if let Some(old) = previous.and_then(|p| presentation(p).get("structureDiagram")) {
        let mut before = previous.expect("checked previous").clone();
        let mut after = c.clone();
        presentation_mut(&mut before)?
            .as_object_mut()
            .expect("validated presentation")
            .remove("structureDiagram");
        presentation_mut(&mut after)?
            .as_object_mut()
            .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Presentation must be an object"))?
            .remove("structureDiagram");
        let mut d = old.clone();
        d["status"] = if before == after {
            old.get("status").cloned().unwrap_or(json!("ready"))
        } else {
            json!("stale")
        };
        presentation_mut(c)?["structureDiagram"] = d;
    }
    Ok(())
}
pub fn invalidate(c: &mut Value) {
    if presentation(c).get("structureDiagram").is_some() {
        if let Ok(p) = presentation_mut(c) {
            p["structureDiagram"]["status"] = "stale".into();
        }
    }
}
pub fn schema() -> Value {
    super::discovery::data()["declarations"]["common"]["structureDiagramSchema"].clone()
}

#[cfg(test)]
#[path = "../../tests/unit/structure_existing.rs"]
mod tests;
