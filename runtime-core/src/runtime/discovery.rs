//! Immutable, packaged authoring knowledge with native selection and ranking.
use super::error::{require, Error, Result};
use serde_json::{json, Map, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    sync::OnceLock,
};

pub fn data() -> &'static Value {
    static DATA: OnceLock<Value> = OnceLock::new();
    DATA.get_or_init(|| {
        let mut data: Value = serde_json::from_str(include_str!("../../resources/discovery.json"))
            .expect("packaged chart declarations");
        for example in data["examples"]
            .as_object_mut()
            .expect("packaged examples")
            .values_mut()
        {
            if example["markdownSource"] == "academic-report.md" {
                example.as_object_mut().unwrap().remove("markdownSource");
                example["markdown"] = json!(include_str!("../../resources/academic-report.md"));
            }
            for operation in example["operations"]
                .as_array_mut()
                .expect("example operations")
            {
                if operation["op"] == "set_report_markdown"
                    && operation["source"] == "academic-report.md"
                {
                    operation.as_object_mut().unwrap().remove("source");
                    operation["value"] = json!(include_str!("../../resources/academic-report.md"));
                }
            }
        }
        data
    })
}
pub fn catalog() -> Value {
    let summary = &data()["summary"];
    json!({"statistical":super::statistics::statistical_declarations(),"charts":summary["legacy"]["chartCodes"].as_array().unwrap().iter().map(|v|json!({"code":v})).collect::<Vec<_>>(),"legacy":data()["catalog"],"originalKpis":summary["legacy"]["kpiTypes"],"kpiGuide":summary["kpiGuide"],"kpiPatterns":summary["kpiPatterns"],"policy":"Original components are preserved without automatic conversion; use explicit config and family."})
}
pub fn full_declarations() -> Value {
    let mut value = data()["declarations"].clone();
    value["statistical"] = super::statistics::statistical_declarations();
    value
}
pub fn declarations(args: &Value) -> Result<Value> {
    require(
        args.get("chartType").is_none(),
        "Only original chart codes are supported; select code, not chartType",
        "UNSUPPORTED_CHART_FAMILY",
    )?;
    require(
        args.get("code").is_none() || args.get("codes").is_none(),
        "Choose code or codes, not both",
        "INVALID_ARGUMENT",
    )?;
    let selected: Vec<String> = if let Some(code) = args.get("code") {
        vec![code
            .as_str()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Code must be a string"))?
            .into()]
    } else if let Some(codes) = args.get("codes") {
        let array = codes.as_array().ok_or_else(|| {
            Error::new(
                "INVALID_ARGUMENT",
                "codes must contain 1–8 chart/KPI code strings",
            )
        })?;
        require(
            !array.is_empty() && array.len() <= 8,
            "codes must contain 1–8 chart/KPI code strings",
            "INVALID_ARGUMENT",
        )?;
        let values: Vec<String> = array
            .iter()
            .map(|v| {
                v.as_str()
                    .map(String::from)
                    .ok_or_else(|| Error::new("INVALID_ARGUMENT", "codes must contain strings"))
            })
            .collect::<Result<_>>()?;
        require(
            values.iter().collect::<BTreeSet<_>>().len() == values.len(),
            "codes must be unique",
            "INVALID_ARGUMENT",
        )?;
        values
    } else {
        let mut value = data()["summary"].clone();
        value["statistical"] = super::statistics::statistical_declarations();
        return Ok(value);
    };
    let mut result = full_declarations();
    let original = &data()["declarations"]["legacy"];
    for code in &selected {
        require(
            original["chartCodes"].get(code).is_some() || original["kpiTypes"].get(code).is_some(),
            "No preset declaration for this code; custom codes use renderer=echarts/html",
            "INVALID_ARGUMENT",
        )?;
    }
    let selections:Vec<Value>=selected.iter().map(|code|json!({"code":code,"family":if original["chartCodes"].get(code).is_some(){"chart"}else{"kpi"}})).collect();
    if args.get("code").is_some() {
        result["selection"] = selections[0].clone();
    } else {
        result["selections"] = json!(selections);
    }
    for key in ["chartCodes", "kpiTypes"] {
        let values: Map<String, Value> = original[key]
            .as_object()
            .unwrap()
            .iter()
            .filter(|(code, _)| selected.contains(code))
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();
        result["legacy"][key] = values.into();
    }
    result["legacy"]["catalogEntries"] = json!(original["catalogEntries"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|entry| selected.iter().any(|id| entry["id"] == *id))
        .cloned()
        .collect::<Vec<_>>());
    let mut families = Map::new();
    for family in ["chart", "kpi"] {
        let codes: Vec<&String> = selected
            .iter()
            .filter(|id| {
                original[if family == "chart" {
                    "chartCodes"
                } else {
                    "kpiTypes"
                }]
                .get(*id)
                .is_some()
            })
            .collect();
        if codes.is_empty() {
            continue;
        }
        let mut entry = original["families"][family].clone();
        let schema = &mut entry["componentSchema"]["properties"]["config"];
        schema["properties"][if family == "chart" { "code" } else { "type" }] = if codes.len() == 1
        {
            json!({"const":codes[0]})
        } else {
            json!({"enum":codes})
        };
        if family == "kpi" {
            if let Some(required) = schema["required"].as_array_mut() {
                if !required.contains(&json!("type")) {
                    required.push(json!("type"));
                }
            }
        }
        entry["example"] = original[if family == "chart" {
            "chartCodes"
        } else {
            "kpiTypes"
        }][codes[0]]["example"]
            .clone();
        families.insert(family.into(), entry);
    }
    result["legacy"]["families"] = families.into();
    result["statistical"] = super::statistics::statistical_declarations();
    Ok(result)
}
pub fn examples(case: Option<&str>) -> Result<Value> {
    match case {
        None => Ok(data()["exampleIndex"].clone()),
        Some(id) => data()["examples"]
            .get(id)
            .cloned()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "Unknown generation case")),
    }
}
pub fn layouts() -> Value {
    data()["layouts"].clone()
}
fn contains(values: &Value, needle: &str) -> bool {
    values
        .as_array()
        .is_some_and(|a| a.iter().any(|v| v == needle))
}
pub fn recommend(args: &Value, doc: Option<&Value>) -> Result<Value> {
    let source = &data()["recommend"];
    let intent = args["intent"].as_str().unwrap_or_default();
    require(source["kpiByIntent"].get(intent).is_some(),"Choose comparison, ranking, trend, composition, distribution, relationship, flow, change, attribution, target or forecast","INVALID_INTENT")?;
    let categories = args["categories"].as_u64();
    let measures = args["measures"].as_u64();
    let mut has_time = args["hasTime"].as_bool();
    require(
        args["categories"].is_null() || categories.is_some_and(|v| v > 0),
        "categories must be a positive integer",
        "INVALID_ARGUMENT",
    )?;
    require(
        args["measures"].is_null() || measures.is_some_and(|v| v > 0),
        "measures must be a positive integer",
        "INVALID_ARGUMENT",
    )?;
    require(
        args["hasTime"].is_null() || has_time.is_some(),
        "hasTime must be boolean",
        "INVALID_ARGUMENT",
    )?;
    let requires_binding = args.get("requiresFilterBinding").map_or(Ok(false), |v| {
        v.as_bool()
            .ok_or_else(|| Error::new("INVALID_ARGUMENT", "requiresFilterBinding must be boolean"))
    })?;
    let mut used: BTreeMap<String, u64> = BTreeMap::new();
    if let Some(id) = args.get("datasetId") {
        let id = id
            .as_str()
            .ok_or_else(|| Error::new("DATASET_NOT_FOUND", "datasetId must identify a dataset"))?;
        require(
            doc.is_some_and(|d| d["manifest"]["datasets"].get(id).is_some()),
            "datasetId must identify a dataset in the supplied dashboard",
            "DATASET_NOT_FOUND",
        )?;
        if has_time.is_none()
            && doc.unwrap()["manifest"]["datasets"][id]["fields"]
                .as_object()
                .is_some_and(|f| f.values().any(|v| v["type"] == "date"))
        {
            has_time = Some(true);
        }
    }
    if let Some(doc) = doc {
        for component in doc["manifest"]["components"]
            .as_object()
            .into_iter()
            .flatten()
            .map(|(_, v)| v)
        {
            if component["kind"] == "legacy" && component.get("family").is_none_or(|v| v == "chart")
            {
                if let Some(code) = component["config"]["code"].as_str() {
                    *used.entry(code.into()).or_default() += 1;
                }
            }
        }
    }
    let mut ranked = Vec::new();
    let mut excluded = Vec::new();
    for (code, rule) in source["rules"].as_object().unwrap() {
        if !contains(&rule[0], intent) {
            continue;
        }
        let bindable = contains(&source["seriesTargets"], code)
            || contains(&source["dynamicCodes"], code) && code != "r03";
        if requires_binding && !bindable {
            excluded.push(json!({"code":code,"reason":"该分析形态没有已实现的筛选重算路径；不能用快照冒充联动。"}));
            continue;
        }
        let needs_time = rule[4].as_bool().unwrap();
        if needs_time && has_time == Some(false) {
            excluded.push(json!({"code":code,"reason":"该形态需要真实时间维度。"}));
            continue;
        }
        let mut score = if rule[0][0] == intent { 3 } else { 2 };
        let mut notes: Vec<String> = Vec::new();
        let mut mismatches = Vec::new();
        let low = rule[1].as_u64().unwrap();
        let high = rule[2].as_u64().unwrap();
        if let Some(n) = categories {
            if !(low..=high).contains(&n) {
                score -= 2;
                mismatches.push(json!({"field":"categories","kind":"readability","actual":n,"range":[low,high]}));
                notes.push(format!(
                    "当前 {n} 个类别超出建议阅读范围 {low}~{high}；需调整布局或明细呈现。"
                ));
            }
        }
        let mut binding = if contains(&source["seriesTargets"], code) {
            "preset"
        } else if bindable {
            "encoding"
        } else {
            "snapshot"
        };
        let mut fewest = rule[3][0].as_u64().unwrap();
        let mut most = rule[3][1].as_u64().unwrap();
        if code == "r02" && measures == Some(2) {
            fewest = 2;
            most = 2;
            binding = "encoding";
            notes.push("两个指标使用固定点大小的 encoding 散点；不虚构气泡规模。".into());
        }
        if code == "c03" && measures == Some(1) {
            fewest = 1;
            most = 1;
            binding = "encoding";
            notes.push("单指标分组图需另有 seriesField；未确认系列维度前不要提交。".into());
        }
        if let Some(n) = measures {
            if !(fewest..=most).contains(&n) {
                score -= 2;
                mismatches.push(
                    json!({"field":"measures","kind":"structure","actual":n,"range":[fewest,most]}),
                );
                notes.push(format!(
                    "当前 {n} 项指标与所需数值结构 {fewest}~{most} 项不匹配；先核对该预设声明。"
                ));
            }
        }
        if bindable {
            score += 1;
        }
        if let Some(n) = used.get(code) {
            notes.push(format!("本页已使用 {n} 次；相同分析问题优先保持一致形态。"));
        }
        let mut requirements = vec![source["requirements"][code]
            .as_str()
            .unwrap_or("明确类别、指标口径和单位；比较对象使用一致范围。")
            .to_owned()];
        if needs_time {
            requirements.push("时间顺序、粒度和缺失期处理已确认。".into());
        }
        if binding == "encoding" {
            requirements.push(
                "必须提供 config.encoding 和其专用 binding；普通预设数据路径不会自动启用此能力。"
                    .into(),
            );
        }
        let mut cautions = Vec::new();
        if mismatches.iter().any(|v| v["kind"] == "structure") {
            cautions.push("已知指标结构不匹配；不能直接填入当前数据，也不能编造缺少的系列。");
        }
        if mismatches.iter().any(|v| v["kind"] == "readability") {
            cautions.push("类别数量超出阅读建议；该范围不是验证器硬限制，应明确处理拥挤或空疏。");
        }
        if !bindable {
            cautions.push("此推荐为静态快照；筛选不重新计算其统计值。");
        }
        let incomplete =
            categories.is_none() || measures.is_none() || needs_time && has_time.is_none();
        if incomplete {
            cautions.push("输入形态尚不完整；当前排序是候选建议，不代表已验证适配。");
        }
        let fit = if !mismatches.is_empty() {
            "shape_mismatch"
        } else if incomplete || binding == "encoding" {
            "needs_confirmation"
        } else {
            "candidate"
        };
        let name = data()["catalog"]
            .as_array()
            .unwrap()
            .iter()
            .find(|v| v["id"] == *code)
            .and_then(|v| v["nameZh"].as_str())
            .unwrap_or(if code == "r05" {
                "多维雷达对标图"
            } else {
                code
            });
        ranked.push(json!({"code":code,"name":name,"why":rule[5],"score":score,"fit":fit,"shapeMismatches":mismatches,"filterBinding":if bindable{"supported"}else{"snapshotOnly"},"bindingMode":binding,"requirements":requirements,"cautions":cautions,"notes":notes,"declarationCall":{"tool":"chart_declarations","arguments":{"code":code}}}));
    }
    let structure = |v: &Value| {
        v["shapeMismatches"]
            .as_array()
            .unwrap()
            .iter()
            .any(|v| v["kind"] == "structure")
    };
    ranked.sort_by_key(|v| {
        (
            structure(v),
            -v["score"].as_i64().unwrap(),
            v["code"].as_str().unwrap().to_owned(),
        )
    });
    ranked.truncate(6);
    let kpis: Vec<Value> = source["kpiByIntent"][intent]
        .as_array()
        .unwrap()
        .iter()
        .filter(|v| !requires_binding || !contains(&source["snapshotKpis"], v.as_str().unwrap()))
        .cloned()
        .collect();
    let mut questions = Vec::new();
    if categories.is_none() {
        questions.push("图中实际需要展示多少个类别或时间点？");
    }
    if measures.is_none() {
        questions.push("要比较几个指标；它们的单位、聚合方式和基准是什么？");
    }
    if has_time.is_none() && matches!(intent, "trend" | "forecast") {
        questions.push("是否存在真实日期字段，采用什么时间粒度？");
    }
    let viable = ranked.iter().any(|v| !structure(v));
    Ok(
        json!({"intent":intent,"inputs":{"categories":categories,"measures":measures,"hasTime":has_time,"requiresFilterBinding":requires_binding},"charts":ranked,"kpiShapes":kpis,"usedOnPage":used,"excluded":excluded,"questions":questions,"designGuidance":source["designGuidance"],"status":if viable{"candidates"}else{"needs_input"},"next":if viable{"chart_declarations {\"codes\": [\"<chosen-chart>\", \"<chosen-kpi>\"]} returns shared schemas and synthetic working examples in one call."}else{"确认数据形态或筛选要求；不要用不支持该分析的预设替代。可另行评估原生 ECharts、HTML 或统计图快照。"}}),
    )
}
