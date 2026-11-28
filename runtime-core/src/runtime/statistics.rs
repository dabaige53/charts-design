//! Native bounded statistical rendering. Raw observations, SVG paths and PNG share one geometry.
use super::{
    data::QueryCache,
    error::{require, Error, Result},
    serialization::canonical_json,
};
use base64::Engine;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::{collections::HashSet, sync::OnceLock};
pub const MAX_STAT_ROWS: usize = 5000;
pub const PLOT_TYPES: [&str; 3] = ["histogram", "boxplot", "regression"];
pub fn validate_statistical(doc: &Value, component: &Value) -> Result<Vec<Value>> {
    let c = component.as_object().ok_or_else(|| {
        Error::new(
            "INVALID_DOCUMENT",
            "Statistical component must be an object",
        )
    })?;
    require(
        c.keys().all(|k| {
            [
                "kind",
                "title",
                "subtitle",
                "datasetId",
                "plot",
                "analysis",
                "presentation",
            ]
            .contains(&k.as_str())
        }),
        "Unknown statistical component field",
        "INVALID_DOCUMENT",
    )?;
    if let Some(sub) = c.get("subtitle") {
        require(
            sub.as_str().is_some_and(|s| s.chars().count() <= 1000),
            "Statistical subtitle must contain at most 1000 characters",
            "INVALID_DOCUMENT",
        )?;
    }
    let dataset = c.get("datasetId").and_then(Value::as_str).unwrap_or("");
    let meta = &doc["manifest"]["datasets"][dataset];
    require(
        meta.is_object(),
        "Statistical dataset not found",
        "INVALID_DOCUMENT",
    )?;
    let plot = c
        .get("plot")
        .and_then(Value::as_object)
        .ok_or_else(|| Error::new("INVALID_DOCUMENT", "Statistical plot must be an object"))?;
    let kind = plot.get("type").and_then(Value::as_str).unwrap_or("");
    require(
        PLOT_TYPES.contains(&kind),
        "Unsupported statistical plot type",
        "INVALID_DOCUMENT",
    )?;
    require(
        plot.keys().all(|k| {
            if kind == "histogram" {
                ["type", "x", "bins"].contains(&k.as_str())
            } else {
                ["type", "x", "y"].contains(&k.as_str())
            }
        }),
        "Unknown statistical plot option; executable code and arbitrary kwargs are forbidden",
        "INVALID_DOCUMENT",
    )?;
    let x = plot.get("x").and_then(Value::as_str).unwrap_or("");
    require(
        meta["fields"].get(x).is_some(),
        "Statistical field is not declared",
        "INVALID_DOCUMENT",
    )?;
    if kind == "boxplot" {
        require(
            ["string", "boolean"].contains(&meta["fields"][x]["type"].as_str().unwrap_or("")),
            "Boxplot x must be categorical string or boolean",
            "INVALID_DOCUMENT",
        )?;
    } else {
        require(
            meta["fields"][x]["type"] == "number",
            "Statistical x field must be numeric",
            "INVALID_DOCUMENT",
        )?;
    }
    let y = plot.get("y").and_then(Value::as_str);
    if kind == "histogram" {
        require(
            plot.get("bins")
                .unwrap_or(&json!(20))
                .as_u64()
                .is_some_and(|b| (1..=100).contains(&b)),
            "Histogram bins must be an integer from 1 to 100",
            "INVALID_DOCUMENT",
        )?;
    } else {
        require(
            y.is_some_and(|y| meta["fields"][y]["type"] == "number"),
            "Statistical y field must be numeric",
            "INVALID_DOCUMENT",
        )?;
    }
    let analysis = c
        .get("analysis")
        .and_then(Value::as_object)
        .ok_or_else(|| {
            Error::new(
                "INVALID_DOCUMENT",
                "Statistical analysis requires definition and unit",
            )
        })?;
    require(
        analysis.len() == 2 && analysis.contains_key("definition") && analysis.contains_key("unit"),
        "Statistical analysis requires exactly definition and unit",
        "INVALID_DOCUMENT",
    )?;
    require(
        analysis["definition"]
            .as_str()
            .is_some_and(|s| (1..=1000).contains(&s.chars().count())),
        "Supply the observation grain and measurement definition",
        "INVALID_DOCUMENT",
    )?;
    require(
        analysis["unit"]
            .as_str()
            .is_some_and(|s| s.chars().count() <= 100),
        "Unit must contain at most 100 characters",
        "INVALID_DOCUMENT",
    )?;
    let Some(rows) = doc["snapshot"]["datasets"]
        .get(dataset)
        .and_then(Value::as_array)
    else {
        require(
            doc["snapshot"]["datasetRefs"][dataset]["rowCount"]
                .as_u64()
                .is_some_and(|n| n <= MAX_STAT_ROWS as u64),
            "Statistical plots accept at most 5000 raw rows",
            "INVALID_DOCUMENT",
        )?;
        return Ok(Vec::new());
    };
    require(
        rows.len() <= MAX_STAT_ROWS,
        "Statistical plots accept at most 5000 raw rows",
        "INVALID_DOCUMENT",
    )?;
    let used = rows
        .iter()
        .filter(|r| !r[x].is_null() && y.is_none_or(|y| !r[y].is_null()))
        .cloned()
        .collect::<Vec<_>>();
    require(
        !used.is_empty(),
        "Statistical plot requires at least one complete observation",
        "INVALID_DOCUMENT",
    )?;
    for row in &used {
        for key in std::iter::once(x).chain(y) {
            let value = &row[key];
            if let Some(s) = value.as_str() {
                require(
                    s.chars().count() <= 100,
                    "Statistical category labels are limited to 100 characters",
                    "INVALID_DOCUMENT",
                )?;
            }
            if let Some(n) = value.as_f64() {
                require(
                    n.is_finite() && n.abs() <= 1e12,
                    "Statistical numeric values must be within ±1e12",
                    "INVALID_DOCUMENT",
                )?;
            }
            if key != x || kind != "boxplot" {
                require(
                    value.is_number(),
                    "Statistical observations require numeric values",
                    "INVALID_DOCUMENT",
                )?;
            } else {
                require(
                    value.is_string() || value.is_boolean(),
                    "Boxplot category values must match declared type",
                    "INVALID_DOCUMENT",
                )?;
            }
        }
    }
    let distinct = used
        .iter()
        .map(|r| r[x].to_string())
        .collect::<HashSet<_>>()
        .len();
    if kind == "boxplot" {
        require(
            distinct <= 20,
            "Boxplot accepts at most 20 categories",
            "INVALID_DOCUMENT",
        )?;
    }
    if kind == "regression" {
        require(
            used.len() >= 3 && distinct >= 2,
            "Regression needs at least 3 complete observations and distinct x values",
            "INVALID_DOCUMENT",
        )?;
    }
    Ok(used)
}
pub fn render_statistical(doc: &Value, component_id: &str, format: &str) -> Result<Value> {
    require(
        ["svg", "png"].contains(&format),
        "Statistical format must be svg or png",
        "INVALID_ARGUMENT",
    )?;
    let c = &doc["manifest"]["components"][component_id];
    require(
        c["kind"] == "statistical",
        "Statistical component not found",
        "INVALID_ARGUMENT",
    )?;
    let used = validate_statistical(doc, c)?;
    let dataset = c["datasetId"].as_str().unwrap_or("");
    let meta = &doc["manifest"]["datasets"][dataset];
    let source_id = meta["sourceId"].as_str().unwrap_or("");
    let source = &doc["manifest"]["sources"][source_id];
    let columns = std::iter::once(c["plot"]["x"].as_str().unwrap_or(""))
        .chain(c["plot"]["y"].as_str())
        .collect::<Vec<_>>();
    let payload = json!({"component":c,"rows":used.iter().map(|r|Value::Object(columns.iter().map(|k|((*k).into(),r[*k].clone())).collect())).collect::<Vec<_>>(),"fields":columns.iter().map(|k|((*k).into(),json!({"label":meta["fields"][*k]["label"].as_str().unwrap_or(k).chars().take(200).collect::<String>()}))).collect::<Map<_,_>>(),"renderer":"charts-native-statistics-v1"});
    let raw = canonical_json(&payload)?;
    static CACHE: OnceLock<QueryCache> = OnceLock::new();
    let key = format!("{format}:{:x}", Sha256::digest(raw.as_bytes()));
    let (encoded, _) = CACHE
        .get_or_init(|| QueryCache::new(32 * 1024 * 1024, 24))
        .get(key, || Ok(json!(draw(&payload, format)?)))?;
    let dropped = doc["snapshot"]["datasets"][dataset]
        .as_array()
        .map(Vec::len)
        .unwrap_or(0)
        .saturating_sub(used.len());
    let kind = c["plot"]["type"].as_str().unwrap_or("");
    let method=match kind{"histogram"=>format!("Counts; {} equal-width bins",c["plot"]["bins"].as_u64().unwrap_or(20)),"boxplot"=>"Median, quartiles, 1.5×IQR whiskers; outliers shown".into(),_=>"Ordinary least-squares line; confidence interval not computed; association does not establish causation".into()};
    let unit = c["analysis"]["unit"].as_str().unwrap_or("");
    let caption=format!("{method}. Raw observations; n={}; missing observations omitted={dropped}. Definition: {}. Unit: {}. Source: {} ({}; {}, not certified). Snapshot: {}.",used.len(),c["analysis"]["definition"].as_str().unwrap_or(""),if unit.is_empty(){"unitless"}else{unit},source["name"].as_str().unwrap_or(source_id),source["kind"].as_str().unwrap_or(""),source["verification"].as_str().unwrap_or("supplied"),doc["snapshot"]["updatedAt"].as_str().unwrap_or(""));
    let mime = if format == "svg" {
        "image/svg+xml"
    } else {
        "image/png"
    };
    Ok(
        json!({"dataUri":format!("data:{mime};base64,{}",encoded.as_str().unwrap_or("")),"mimeType":mime,"caption":caption,"provenance":{"datasetId":dataset,"sourceId":source_id,"source":source,"snapshotUpdatedAt":doc["snapshot"]["updatedAt"],"inputSha256":format!("{:x}",Sha256::digest(raw.as_bytes())),"rowsUsed":used.len(),"rowsDropped":dropped,"versions":{"charts-native-statistics":"1","resvg":"0.50.0"},"aggregation":"none; raw observations"}}),
    )
}
pub fn statistical_artifacts(doc: &Value) -> Value {
    let mut out = Map::new();
    if let Some(components) = doc["manifest"]["components"].as_object() {
        for (id, c) in components {
            if c["kind"] == "statistical" {
                out.insert(
                    id.clone(),
                    match render_statistical(doc, id, "svg") {
                        Ok(v) => v,
                        Err(e) => json!({"error":e.message,"code":e.code}),
                    },
                );
            }
        }
    }
    Value::Object(out)
}
pub fn regression_line(x: &[f64], y: &[f64]) -> Result<([f64; 2], [f64; 2])> {
    require(
        x.len() == y.len() && !x.is_empty(),
        "Regression requires paired values",
        "INVALID_ARGUMENT",
    )?;
    let dx = x.iter().map(|v| v - x[0]).collect::<Vec<_>>();
    let dy = y.iter().map(|v| v - y[0]).collect::<Vec<_>>();
    let cx = dx.iter().sum::<f64>() / x.len() as f64;
    let cy = dy.iter().sum::<f64>() / x.len() as f64;
    let scale = dx.iter().map(|v| (v - cx).abs()).fold(0f64, f64::max);
    require(
        scale > 0.0,
        "Regression requires distinct x values",
        "INVALID_ARGUMENT",
    )?;
    let z = dx.iter().map(|v| (v - cx) / scale).collect::<Vec<_>>();
    let slope = z.iter().zip(&dy).map(|(z, dy)| z * (dy - cy)).sum::<f64>()
        / z.iter().map(|z| z * z).sum::<f64>();
    let lo = dx.iter().copied().fold(f64::INFINITY, f64::min);
    let hi = dx.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let line_y = [
        y[0] + cy + slope * (lo - cx) / scale,
        y[0] + cy + slope * (hi - cx) / scale,
    ];
    require(
        line_y.iter().all(|v| v.is_finite()),
        "Regression produced non-finite predictions",
        "INVALID_ARGUMENT",
    )?;
    Ok((
        [
            x.iter().copied().fold(f64::INFINITY, f64::min),
            x.iter().copied().fold(f64::NEG_INFINITY, f64::max),
        ],
        line_y,
    ))
}
pub fn histogram(values: &[f64], bins: usize) -> Result<(Vec<f64>, Vec<usize>)> {
    require(
        !values.is_empty() && (1..=100).contains(&bins) && values.iter().all(|n| n.is_finite()),
        "Invalid histogram input",
        "INVALID_ARGUMENT",
    )?;
    let mut low = values.iter().copied().fold(f64::INFINITY, f64::min);
    let mut high = values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    if low == high {
        low -= 0.5;
        high += 0.5;
    }
    let width = (high - low) / bins as f64;
    let edges = (0..=bins)
        .map(|i| {
            if i == bins {
                high
            } else {
                low + i as f64 * width
            }
        })
        .collect::<Vec<_>>();
    let mut counts = vec![0; bins];
    for value in values {
        let mut bin = ((value - low) / width).floor().max(0.0) as usize;
        bin = bin.min(bins - 1);
        while bin > 0 && *value < edges[bin] {
            bin -= 1;
        }
        while bin < bins - 1 && *value >= edges[bin + 1] {
            bin += 1;
        }
        counts[bin] += 1;
    }
    Ok((edges, counts))
}
pub fn box_summary(values: &[f64]) -> Result<Value> {
    require(
        !values.is_empty() && values.iter().all(|v| v.is_finite()),
        "Invalid boxplot values",
        "INVALID_ARGUMENT",
    )?;
    let mut v = values.to_vec();
    v.sort_by(f64::total_cmp);
    let percentile = |q: f64| {
        let pos = (v.len() - 1) as f64 * q;
        let lo = pos.floor() as usize;
        let hi = pos.ceil() as usize;
        v[lo] + (v[hi] - v[lo]) * (pos - lo as f64)
    };
    let q1 = percentile(0.25);
    let median = percentile(0.5);
    let q3 = percentile(0.75);
    let iqr = q3 - q1;
    let lower = v
        .iter()
        .copied()
        .find(|x| *x >= q1 - 1.5 * iqr)
        .unwrap_or(q1);
    let upper = v
        .iter()
        .copied()
        .rev()
        .find(|x| *x <= q3 + 1.5 * iqr)
        .unwrap_or(q3);
    Ok(
        json!({"q1":q1,"median":median,"q3":q3,"lower":lower.min(q1),"upper":upper.max(q3),"outliers":v.into_iter().filter(|x|*x<lower||*x>upper).collect::<Vec<_>>()}),
    )
}
fn escaped(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}
fn label(value: &Value) -> String {
    if let Some(s) = value.as_str() {
        s.to_string()
    } else {
        value.to_string()
    }
}
fn range(values: &[f64]) -> (f64, f64) {
    let low = values.iter().copied().fold(f64::INFINITY, f64::min);
    let high = values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let pad = if low == high {
        low.abs().max(1.0) * 0.05
    } else {
        (high - low) * 0.05
    };
    (low - pad, high + pad)
}
fn number(n: f64) -> String {
    if n.abs() >= 1e6 || (n != 0.0 && n.abs() < 0.001) {
        format!("{n:.2e}")
    } else {
        let s = format!("{n:.3}");
        s.trim_end_matches('0').trim_end_matches('.').to_string()
    }
}
fn draw(payload: &Value, format: &str) -> Result<String> {
    let c = &payload["component"];
    let plot = &c["plot"];
    let rows = payload["rows"]
        .as_array()
        .ok_or_else(|| Error::new("STATISTICAL_RENDER_FAILED", "Missing observations"))?;
    let x = plot["x"].as_str().unwrap_or("");
    let y = plot["y"].as_str().unwrap_or("");
    let kind = plot["type"].as_str().unwrap_or("");
    let mut svg=String::from("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1152\" height=\"648\" viewBox=\"0 0 1152 648\"><rect width=\"1152\" height=\"648\" fill=\"white\"/><g font-family=\"Noto Serif CJK SC,DejaVu Sans,sans-serif\" font-size=\"18\" fill=\"#444444\">");
    let (left, right, top, bottom) = (
        110.0,
        1108.0,
        34.0,
        if kind == "boxplot" { 492.0 } else { 558.0 },
    );
    let mut geometry = String::new();
    let mut categories = Vec::new();
    let (xr, yr) = if kind == "histogram" {
        let values = rows
            .iter()
            .map(|r| r[x].as_f64().unwrap())
            .collect::<Vec<_>>();
        let (edges, counts) = histogram(&values, plot["bins"].as_u64().unwrap_or(20) as usize)?;
        let ymax = counts.iter().copied().max().unwrap_or(1).max(1) as f64 * 1.08;
        let xr = (*edges.first().unwrap(), *edges.last().unwrap());
        let px = |v: f64| left + (v - xr.0) / (xr.1 - xr.0) * (right - left);
        let py = |v: f64| bottom - v / ymax * (bottom - top);
        for (i, count) in counts.iter().enumerate() {
            geometry.push_str(&format!("<rect x=\"{:.5}\" y=\"{:.5}\" width=\"{:.5}\" height=\"{:.5}\" fill=\"#555555\" stroke=\"white\" stroke-width=\"1\"/>",px(edges[i]),py(*count as f64),px(edges[i+1])-px(edges[i]),bottom-py(*count as f64)));
        }
        (xr, (0.0, ymax))
    } else if kind == "boxplot" {
        let mut groups: Vec<(Value, Vec<f64>)> = Vec::new();
        for row in rows {
            if let Some((_, v)) = groups.iter_mut().find(|(k, _)| k == &row[x]) {
                v.push(row[y].as_f64().unwrap());
            } else {
                groups.push((row[x].clone(), vec![row[y].as_f64().unwrap()]));
            }
        }
        let values = groups
            .iter()
            .flat_map(|(_, v)| v.iter().copied())
            .collect::<Vec<_>>();
        let yr = range(&values);
        let py = |v: f64| bottom - (v - yr.0) / (yr.1 - yr.0) * (bottom - top);
        let step = (right - left) / groups.len() as f64;
        for (i, (name, values)) in groups.iter().enumerate() {
            let summary = box_summary(values)?;
            let center = left + (i as f64 + 0.5) * step;
            let half = step * 0.30;
            categories.push((center, label(name)));
            let q1 = summary["q1"].as_f64().unwrap();
            let median = summary["median"].as_f64().unwrap();
            let q3 = summary["q3"].as_f64().unwrap();
            let lo = summary["lower"].as_f64().unwrap();
            let hi = summary["upper"].as_f64().unwrap();
            geometry.push_str(&format!("<path d=\"M{center} {}V{} M{} {}H{} M{} {}H{}\" stroke=\"#555555\" stroke-width=\"2\" fill=\"none\"/><rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#aaaaaa\" stroke=\"#555555\" stroke-width=\"2\"/><path d=\"M{} {}H{}\" stroke=\"#444444\" stroke-width=\"2.5\"/>",py(lo),py(hi),center-half*0.5,py(lo),center+half*0.5,center-half*0.5,py(hi),center+half*0.5,center-half,py(q3),half*2.0,(py(q1)-py(q3)).max(0.1),center-half,py(median),center+half));
            for value in summary["outliers"].as_array().unwrap() {
                geometry.push_str(&format!(
                    "<circle cx=\"{center}\" cy=\"{}\" r=\"3\" fill=\"none\" stroke=\"#555555\"/>",
                    py(value.as_f64().unwrap())
                ));
            }
        }
        ((0.0, groups.len() as f64), yr)
    } else {
        let xs = rows
            .iter()
            .map(|r| r[x].as_f64().unwrap())
            .collect::<Vec<_>>();
        let ys = rows
            .iter()
            .map(|r| r[y].as_f64().unwrap())
            .collect::<Vec<_>>();
        let xr = range(&xs);
        let yr = range(&ys);
        let px = |v: f64| left + (v - xr.0) / (xr.1 - xr.0) * (right - left);
        let py = |v: f64| bottom - (v - yr.0) / (yr.1 - yr.0) * (bottom - top);
        for (x, y) in xs.iter().zip(&ys) {
            geometry.push_str(&format!("<circle cx=\"{:.5}\" cy=\"{:.5}\" r=\"3.9\" fill=\"#444444\" fill-opacity=\"0.65\"/>",px(*x),py(*y)));
        }
        let (lx, ly) = regression_line(&xs, &ys)?;
        geometry.push_str(&format!(
            "<path d=\"M{} {}L{} {}\" stroke=\"#444444\" stroke-width=\"2.2\" fill=\"none\"/>",
            px(lx[0]),
            py(ly[0]),
            px(lx[1]),
            py(ly[1])
        ));
        (xr, yr)
    };
    for i in 0..=5 {
        let fraction = i as f64 / 5.0;
        let pos = bottom - fraction * (bottom - top);
        let value = yr.0 + fraction * (yr.1 - yr.0);
        svg.push_str(&format!("<path d=\"M{left} {pos}H{right}\" stroke=\"#777777\" stroke-opacity=\"0.2\"/><text x=\"{}\" y=\"{}\" text-anchor=\"end\">{}</text>",left-14.0,pos+6.0,escaped(&number(value))));
        if kind != "boxplot" {
            let pos = left + fraction * (right - left);
            svg.push_str(&format!(
                "<text x=\"{pos}\" y=\"{}\" text-anchor=\"middle\">{}</text>",
                bottom + 31.0,
                escaped(&number(xr.0 + fraction * (xr.1 - xr.0)))
            ));
        }
    }
    svg.push_str(&geometry);
    for (pos, name) in categories {
        let text = name.chars().take(100).collect::<String>();
        svg.push_str(&format!("<text transform=\"translate({pos},{}) rotate(-35)\" text-anchor=\"end\" font-size=\"15\">{}</text>",bottom+25.0,escaped(&text)));
    }
    svg.push_str(&format!("<path d=\"M{left} {top}V{bottom}H{right}\" stroke=\"#555555\" fill=\"none\" stroke-width=\"1.5\"/>"));
    let unit = c["analysis"]["unit"].as_str().unwrap_or("");
    let suffix = if unit.is_empty() {
        String::new()
    } else {
        format!(" ({unit})")
    };
    let x_label = format!(
        "{}{}",
        payload["fields"][x]["label"].as_str().unwrap_or(x),
        if kind == "histogram" {
            suffix.as_str()
        } else {
            ""
        }
    );
    let y_label = if kind == "histogram" {
        "Count".into()
    } else {
        format!(
            "{}{}",
            payload["fields"][y]["label"].as_str().unwrap_or(y),
            suffix
        )
    };
    svg.push_str(&format!("<text x=\"{}\" y=\"627\" text-anchor=\"middle\" font-size=\"21\">{}</text><text transform=\"translate(29,{}) rotate(-90)\" text-anchor=\"middle\" font-size=\"21\">{}</text></g></svg>",(left+right)/2.0,escaped(&x_label),(top+bottom)/2.0,escaped(&y_label)));
    static OPTIONS: OnceLock<resvg::usvg::Options<'static>> = OnceLock::new();
    let opts = OPTIONS.get_or_init(|| {
        let mut o = resvg::usvg::Options::default();
        o.fontdb_mut().load_system_fonts();
        o.font_family = "DejaVu Sans".into();
        o
    });
    require(opts.fontdb.faces().next().is_some(),"Install fonts for native statistical rendering (DejaVu Sans and Noto Serif CJK recommended)","STATISTICAL_FONT_UNAVAILABLE")?;
    let tree = resvg::usvg::Tree::from_str(&svg, opts)
        .map_err(|e| Error::new("STATISTICAL_RENDER_FAILED", e.to_string()))?;
    let bytes = if format == "svg" {
        tree.to_string(&resvg::usvg::WriteOptions::default())
            .into_bytes()
    } else {
        let size = tree.size().to_int_size();
        let mut pixmap =
            resvg::tiny_skia::Pixmap::new(size.width(), size.height()).ok_or_else(|| {
                Error::new(
                    "STATISTICAL_RENDER_FAILED",
                    "Could not allocate statistical image",
                )
            })?;
        resvg::render(
            &tree,
            resvg::tiny_skia::Transform::default(),
            &mut pixmap.as_mut(),
        );
        pixmap
            .encode_png()
            .map_err(|e| Error::new("STATISTICAL_RENDER_FAILED", e.to_string()))?
    };
    Ok(base64::engine::general_purpose::STANDARD.encode(bytes))
}
pub fn statistical_schema() -> Value {
    let name = json!({"type":"string","minLength":1,"maxLength":199});
    let variants = PLOT_TYPES
        .iter()
        .map(|kind| {
            let mut p = json!({"type":{"const":kind},"x":name});
            let required = if *kind == "histogram" {
                p["bins"] = json!({"type":"integer","minimum":1,"maximum":100,"default":20});
                json!(["type", "x"])
            } else {
                p["y"] = name.clone();
                json!(["type", "x", "y"])
            };
            json!({"type":"object","additionalProperties":false,"properties":p,"required":required})
        })
        .collect::<Vec<_>>();
    json!({"type":"object","additionalProperties":false,"required":["kind","title","datasetId","plot","analysis"],"properties":{"kind":{"const":"statistical"},"title":{"type":"string","maxLength":240},"subtitle":{"type":"string","maxLength":1000},"datasetId":{"type":"string"},"plot":{"oneOf":variants},"presentation":{"type":"object","properties":{"structureDiagram":super::structure::schema()}},"analysis":{"type":"object","additionalProperties":false,"required":["definition","unit"],"properties":{"definition":{"type":"string","minLength":1,"maxLength":1000},"unit":{"type":"string","maxLength":100}}}}})
}
pub fn statistical_declarations() -> Value {
    json!({"componentSchema":statistical_schema(),"backend":"charts-native-statistics","types":PLOT_TYPES,"component":{"kind":"statistical","title":"Measurement distribution","datasetId":"observations","plot":{"type":"histogram","x":"value","bins":20},"analysis":{"definition":"One row per observed item; value is its measured quantity.","unit":"units"}},"rules":["Native Rust rendering converts SVG text to font paths for portable display. Install DejaVu Sans and Noto Serif CJK for multilingual labels.","Histogram requires numeric x and integer bins 1–100; boxplot requires categorical x and numeric y; regression requires numeric x and y, at least 3 complete rows and distinct x values.","Use raw observations. analysis.definition describes grain and meaning; analysis.unit labels the measured axis. Include x units in dataset field labels for regression.","At most 5000 rows and 20 boxplot categories. Null/missing observations are omitted and counted. Statistical components use a fixed dataset without interactive filters.","SVG in preview and offline export; statistical_render also supports PNG. Plot inputs exclude paths, URLs, executable code and arbitrary kwargs. Regression uses OLS without a confidence interval.","Use ordinary Markdown chart fences. Derived artifacts are generated from the canonical document; rendering keys include data, specification and native renderer version.","Histograms count equal-width bins. Boxplots use linear quartiles, 1.5 IQR whiskers and individual outliers. Regression uses centered least squares for numerical stability."]})
}
