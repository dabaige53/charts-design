//! Ordered, content-aware layout on the established 12/8/4-column grids.
use super::error::{Error, Result};
use serde_json::{json, Value};

pub const COLS: [(&str, i64); 3] = [("desktop", 12), ("tablet", 8), ("mobile", 4)];
pub const TEMPLATES: [&str; 7] = [
    "executive",
    "focus",
    "bento",
    "sidebar",
    "grid3",
    "narrative",
    "scorecard",
];
const WIDE: [&str; 3] = ["mc06", "mc09", "mc14"];
const MOBILE: [&str; 8] = [
    "mc06", "mc09", "mc14", "mc10", "mc11", "mc13", "mc15", "mc16",
];
pub fn role(c: &Value) -> &str {
    match c["kind"].as_str().unwrap_or("") {
        "legacy" => match c["family"].as_str().unwrap_or("chart") {
            "kpi" => "kpi",
            "table" => "table",
            _ => "chart",
        },
        "kpi" => "kpi",
        "table" => "table",
        "text" => "text",
        _ => "chart",
    }
}
pub fn kpi_config(c: &Value) -> &Value {
    if c["kind"] == "legacy" {
        &c["config"]
    } else {
        &c["presentation"]
    }
}
pub fn kpi_type(c: &Value) -> &str {
    kpi_config(c)["type"].as_str().unwrap_or("mc01")
}
fn primary(c: &Value) -> bool {
    c["layoutPriority"] == "primary"
}
fn height(role: &str) -> i64 {
    match role {
        "kpi" => 4,
        "text" => 5,
        _ => 8,
    }
}
pub fn kpi_height(c: &Value) -> i64 {
    let cfg = kpi_config(c);
    let title = c
        .get("title")
        .or_else(|| cfg.get("label"))
        .and_then(Value::as_str)
        .unwrap_or("");
    let subtitle = c
        .get("subtitle")
        .or_else(|| cfg.get("subtitle"))
        .and_then(Value::as_str)
        .unwrap_or("");
    4 + i64::from(["mc15", "mc16"].contains(&kpi_type(c)) || primary(c))
        + i64::from(title.chars().count() > 32 || subtitle.chars().count() > 48)
}
pub fn split(cols: i64, count: usize) -> Vec<i64> {
    if count == 0 {
        return vec![];
    }
    (0..count)
        .map(|i| cols / count as i64 + i64::from((i as i64) < cols % count as i64))
        .collect()
}
fn balanced(keys: &[String], per: usize) -> Vec<Vec<String>> {
    if keys.is_empty() {
        return vec![];
    }
    let sizes = split(keys.len() as i64, keys.len().div_ceil(per));
    let mut at = 0;
    sizes
        .into_iter()
        .map(|size| {
            let end = at + size as usize;
            let r = keys[at..end].to_vec();
            at = end;
            r
        })
        .collect()
}
fn weighted(keys: &[String], weights: &[usize], capacity: usize) -> Vec<Vec<(String, usize)>> {
    let n = keys.len();
    let mut best = vec![(usize::MAX / 4, usize::MAX / 4); n + 1];
    let mut ends = vec![n; n];
    best[n] = (0, 0);
    for start in (0..n).rev() {
        let mut used = 0;
        for end in start..n {
            used += weights[end].clamp(1, capacity);
            if used > capacity {
                break;
            }
            let candidate = (1 + best[end + 1].0, used * used + best[end + 1].1);
            if candidate <= best[start] {
                best[start] = candidate;
                ends[start] = end + 1;
            }
        }
    }
    let mut result = Vec::new();
    let mut start = 0;
    while start < n {
        let end = ends[start];
        result.push(
            (start..end)
                .map(|i| (keys[i].clone(), weights[i].clamp(1, capacity)))
                .collect(),
        );
        start = end;
    }
    result
}
struct Flow {
    cols: i64,
    y: i64,
    placements: Vec<Value>,
}
impl Flow {
    fn new(cols: i64) -> Self {
        Self {
            cols,
            y: 0,
            placements: vec![],
        }
    }
    fn place(&mut self, key: &str, x: i64, y: i64, w: i64, h: i64) {
        self.placements
            .push(json!({"id":key,"x":x,"y":y,"w":w,"h":h}));
    }
    fn row(&mut self, keys: &[String], widths: &[i64], h: i64) {
        let mut x = 0;
        for (k, w) in keys.iter().zip(widths) {
            self.place(k, x, self.y, *w, h);
            x += w;
        }
        self.y += h;
    }
    fn grid(&mut self, keys: &[String], per: usize, h: i64) {
        for chunk in balanced(keys, per) {
            self.row(&chunk, &split(self.cols, chunk.len()), h);
        }
    }
    fn full(&mut self, keys: &[String], h: i64) {
        for k in keys {
            self.row(std::slice::from_ref(k), &[self.cols], h);
        }
    }
}
fn kpis(flow: &mut Flow, keys: &[String], per: usize, components: &Value, bp: &str) {
    let weights: Vec<_> = keys
        .iter()
        .map(|k| {
            let c = &components[k];
            if bp == "mobile" {
                if MOBILE.contains(&kpi_type(c)) || primary(c) {
                    per
                } else {
                    1
                }
            } else if per >= 3 && (WIDE.contains(&kpi_type(c)) || primary(c)) {
                2
            } else {
                1
            }
        })
        .collect();
    for row in weighted(keys, &weights, per) {
        let units: usize = row.iter().map(|v| v.1).sum();
        let unit_widths = split(flow.cols, units);
        let mut index = 0;
        let mut widths = vec![];
        let mut names = vec![];
        let mut h = 4;
        for (k, size) in row {
            widths.push(unit_widths[index..index + size].iter().sum());
            index += size;
            h = h.max(kpi_height(&components[&k]));
            names.push(k);
        }
        flow.row(&names, &widths, h);
    }
}
fn sequence(flow: &mut Flow, items: &[String], per: usize, h: i64, components: &Value) {
    let mut pending = vec![];
    for k in items {
        let r = role(&components[k]);
        if r == "chart" {
            pending.push(k.clone());
        } else {
            flow.grid(&pending, per, h);
            pending.clear();
            flow.full(std::slice::from_ref(k), height(r));
        }
    }
    flow.grid(&pending, per, h);
}
fn bento_flush(
    flow: &mut Flow,
    pending: &mut Vec<String>,
    patterns: &[Vec<i64>],
    pattern: &mut usize,
) {
    let mut i = 0;
    while i < pending.len() {
        let widths = &patterns[*pattern % patterns.len()];
        let end = (i + widths.len()).min(pending.len());
        let chunk = &pending[i..end];
        let fill = if chunk.len() < widths.len() {
            split(flow.cols, chunk.len())
        } else {
            widths.clone()
        };
        flow.row(chunk, &fill, 8);
        i = end;
        *pattern += 1;
    }
    pending.clear();
}

pub fn compute_layout(manifest: &Value, template: &str, order: Option<&[Value]>) -> Result<Value> {
    if !TEMPLATES.contains(&template) {
        return Err(Error::new(
            "UNKNOWN_LAYOUT",
            format!("Unknown layout template: {template}"),
        ));
    }
    let components = &manifest["components"];
    let map = components
        .as_object()
        .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Components must be an object"))?;
    let mut ordered = vec![];
    for key in order.unwrap_or(&[]).iter().filter_map(Value::as_str) {
        if map.contains_key(key) && !ordered.iter().any(|k| k == key) {
            ordered.push(key.to_owned());
        }
    }
    for key in map.keys() {
        if !ordered.contains(key) {
            ordered.push(key.clone());
        }
    }
    let kpi_keys: Vec<_> = ordered
        .iter()
        .filter(|k| role(&components[*k]) == "kpi")
        .cloned()
        .collect();
    let body: Vec<_> = ordered
        .iter()
        .filter(|k| ["chart", "text"].contains(&role(&components[*k])))
        .cloned()
        .collect();
    let tables: Vec<_> = ordered
        .iter()
        .filter(|k| role(&components[*k]) == "table")
        .cloned()
        .collect();
    let charts: Vec<_> = body
        .iter()
        .filter(|k| role(&components[*k]) == "chart")
        .cloned()
        .collect();
    let mut result = json!({});
    for (bp, cols) in COLS {
        let mut f = Flow::new(cols);
        let desktop = bp == "desktop";
        let tablet = bp == "tablet";
        let per = if desktop {
            4
        } else if tablet {
            2
        } else {
            1
        };
        if template == "sidebar" && desktop && !kpi_keys.is_empty() && !body.is_empty() {
            let mut top = 0;
            for k in &kpi_keys {
                let h = kpi_height(&components[k]);
                f.place(k, 0, top, 3, h);
                top += h;
            }
            let mut y = 0;
            for k in &body {
                let h = height(role(&components[k]));
                f.place(k, 3, y, 9, h);
                y += h;
            }
            f.y = top.max(y);
            f.full(&tables, 8);
            result[bp] = json!(f.placements);
            continue;
        }
        kpis(&mut f, &kpi_keys, per, components, bp);
        if template == "focus" && !charts.is_empty() {
            let hero = &charts[0];
            f.full(std::slice::from_ref(hero), if cols > 4 { 10 } else { 8 });
            let rest: Vec<_> = body.iter().filter(|k| *k != hero).cloned().collect();
            sequence(
                &mut f,
                &rest,
                if desktop {
                    3
                } else if tablet {
                    2
                } else {
                    1
                },
                8,
                components,
            );
        } else if template == "bento" && cols > 4 {
            let patterns = if desktop {
                vec![vec![8, 4], vec![4, 8], vec![6, 6], vec![4, 4, 4]]
            } else {
                vec![vec![8], vec![4, 4]]
            };
            let mut pattern = 0;
            let mut pending = vec![];
            for k in &body {
                if role(&components[k]) == "chart" {
                    pending.push(k.clone());
                } else {
                    bento_flush(&mut f, &mut pending, &patterns, &mut pattern);
                    f.full(std::slice::from_ref(k), height(role(&components[k])));
                }
            }
            bento_flush(&mut f, &mut pending, &patterns, &mut pattern);
        } else if template == "narrative" && cols > 4 {
            let mut i = 0;
            while i < body.len() {
                let k = &body[i];
                if role(&components[k]) == "chart"
                    && body
                        .get(i + 1)
                        .is_some_and(|n| role(&components[n]) == "text")
                {
                    let w = if desktop { 8 } else { 5 };
                    f.row(&body[i..i + 2], &[w, cols - w], 8);
                    i += 2;
                } else {
                    f.full(std::slice::from_ref(k), height(role(&components[k])));
                    i += 1;
                }
            }
        } else {
            let mut per = match template {
                "focus" | "grid3" | "scorecard" => 3,
                "narrative" => 1,
                _ => 2,
            };
            if tablet {
                per = if ["grid3", "scorecard"].contains(&template) {
                    2
                } else {
                    1
                };
            } else if !desktop {
                per = 1;
            }
            sequence(
                &mut f,
                &body,
                per,
                if template == "scorecard" && cols > 4 {
                    6
                } else {
                    8
                },
                components,
            );
        }
        f.full(&tables, 8);
        result[bp] = json!(f.placements);
    }
    Ok(result)
}
pub fn overlaps(a: &Value, b: &Value) -> bool {
    let n = |v: &Value, k: &str| v[k].as_i64().unwrap_or(0);
    n(a, "x") < n(b, "x") + n(b, "w")
        && n(b, "x") < n(a, "x") + n(a, "w")
        && n(a, "y") < n(b, "y") + n(b, "h")
        && n(b, "y") < n(a, "y") + n(a, "h")
}
pub fn auto_place(manifest: &mut Value, key: &str, c: &Value) -> Result<()> {
    let kind = role(c);
    let components = manifest["components"].clone();
    for (bp, cols) in COLS {
        let h = if kind == "kpi" {
            kpi_height(c)
        } else {
            height(kind)
        };
        let w = match kind {
            "kpi" => {
                if bp == "desktop" {
                    if WIDE.contains(&kpi_type(c)) || primary(c) {
                        6
                    } else {
                        3
                    }
                } else {
                    4
                }
            }
            "chart" => {
                if bp == "desktop" {
                    6
                } else {
                    cols
                }
            }
            _ => cols,
        };
        let arr = manifest["layout"][bp]
            .as_array_mut()
            .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Layout must be an array"))?;
        let bottom = arr
            .iter()
            .map(|p| p["y"].as_i64().unwrap_or(0) + p["h"].as_i64().unwrap_or(0))
            .max()
            .unwrap_or(0);
        let mut p = json!({"id":key,"x":0,"y":bottom,"w":w,"h":h});
        if !arr.is_empty() && w < cols {
            let top = arr
                .iter()
                .filter_map(|p| p["y"].as_i64())
                .max()
                .unwrap_or(0);
            let band: Vec<_> = arr.iter().filter(|p| p["y"] == top).collect();
            let same = band.iter().all(|p| {
                p["id"]
                    .as_str()
                    .is_some_and(|id| components.get(id).is_some_and(|c| role(c) == kind))
                    && p["h"] == h
            });
            let used = band
                .iter()
                .map(|p| p["x"].as_i64().unwrap_or(0) + p["w"].as_i64().unwrap_or(0))
                .max()
                .unwrap_or(0);
            let candidate = json!({"id":key,"x":used,"y":top,"w":w,"h":h});
            if same && used + w <= cols && !arr.iter().any(|p| overlaps(&candidate, p)) {
                p = candidate;
            }
        }
        arr.push(p);
    }
    Ok(())
}
pub fn templates_catalog() -> Value {
    let definitions=[
        ("executive","经典三段式","Executive three-tier","KPI row(s), charts in two balanced columns, detail tables full width.","Monthly reviews with 3-4 headline metrics and 2-6 evidence charts."),
        ("focus","主图聚焦","Hero focus","KPI strip, then the first chart full width and tall as the hero; supporting charts in three columns.","One decisive trend or comparison with several supporting views."),
        ("bento","便当格拼贴","Bento mosaic","Charts alternate wide/narrow rows (8+4, 4+8, 6+6, 4+4+4) for a varied, magazine-like rhythm.","Mixed evidence of different importance; 4-9 charts."),
        ("sidebar","侧栏指标","Sidebar metrics","KPIs stacked in a left column beside a wide chart column; tables full width below.","Monitoring pages where metrics stay visible next to long charts."),
        ("grid3","三列小多图","Small multiples","Compact charts three per row for side-by-side comparison of the same measure across segments.","Regional/product splits of one measure; 3, 6 or 9 similar charts."),
        ("narrative","图文叙事","Narrative briefing","Reading order top to bottom; a text component that follows a chart sits beside it as commentary (8+4).","Briefings where each chart carries a written takeaway."),
        ("scorecard","指标墙","KPI wall","Readable KPI grid (up to 4 per row on desktop, 2 on tablet, 1 on phones), then compact charts.","Operations scorecards with 6-20 or more metrics and few charts.")];
    json!({"templates":definitions.into_iter().map(|(id,name,en,description,best)|json!({"id":id,"name":name,"nameEn":en,"description":description,"bestFor":best})).collect::<Vec<_>>(),"usage":{"operation":{"op":"apply_layout_template","template":"bento","order":["optional component ids in reading order"]},"notes":["The template is applied after every other operation in the same patch, so components created in that patch are included.","The choice is saved as manifest.layoutTemplate; later put_component/remove_component patches re-flow the template automatically.","An explicit set_layout (including dragging cards in the editor) replaces the template with the manual layout.","Set component.layoutPriority to primary to give a headline KPI extra room; this never changes reading order or metric values.","Vary the composition with the content: do not default every dashboard to executive."]}})
}
