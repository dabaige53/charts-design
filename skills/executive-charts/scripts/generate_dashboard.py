#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
McKinsey-Grade Executive Dashboard Generator (高管看板与完整网页生成引擎)
=============================================================================
Author: Executive Charts Skill Suite
Description:
    Generates complete, enterprise-grade responsive HTML dashboards
    featuring:
    1. Top Global Filter Bar bound to table columns (options derived from the table rows)
    2. 4 Top-Tier KPI Metric Cards (Sparklines, Progress, Trend badges)
    3. Responsive Sectioned Chart Grid (5-action toolbar, chart/table views, CSV export, PNG copy,
       fullscreen focus, explanation dialogs)
    4. Multi-Metric Interactive Pivot Table (Drag & Drop column reordering,
       visibility drawer, nowrap single-line layout, horizontal scroll, sorting, pagination, CSV)
    5. Native Explanation Dialog (Business overview, coordinates & series architecture,
       formula cards & governance rules)

Usage Examples:
    # 1. Generate preset dashboards
    python generate_dashboard.py --preset retail_ecommerce --output ./dist/retail.html --open
    python generate_dashboard.py --preset saas_product --output ./dist/saas.html --open
    python generate_dashboard.py --preset financial_attribution --output ./dist/financial.html
    python generate_dashboard.py --preset executive_report --output ./dist/executive_report.html
    python generate_dashboard.py --preset strategic_matrix --output ./dist/strategic.html
    python generate_dashboard.py --preset comprehensive --output ./dist/comprehensive.html
    python generate_dashboard.py --preset executive_monthly --output ./dist/monthly.html

    # 2. Generate with custom configuration JSON (100% Custom Business Data)
    python generate_dashboard.py --config ./custom_retail.json --output ./dist/my_retail.html --open

    # 3. Compose a custom dashboard with any chart codes
    python generate_dashboard.py --charts "c01,t06,k01,r01,fn01,m01,k04,c06" \
        --title "集团核心运营效能研判看板" \
        --org "商业智能与运营决策中心" \
        --output ./dist/custom_dashboard.html --open
=============================================================================
"""

import os
import sys
import json
import argparse
import subprocess

# Add local path for modular imports
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from core.table_data import (
    TABLE_COLUMNS, TABLE_ROWS,
    AIRLINE_TABLE_COLUMNS, AIRLINE_TABLE_ROWS,
    RETAIL_TABLE_COLUMNS, RETAIL_TABLE_ROWS,
    SAAS_TABLE_COLUMNS, SAAS_TABLE_ROWS,
    FINANCIAL_TABLE_COLUMNS, FINANCIAL_TABLE_ROWS
)
from core.chart_builders import CHARTS_JS_DEFINITIONS
from core.chart_catalog import ALL_CHARTS
from core.dashboard_template import generate_dashboard_html
from core.explanations import EXPLANATIONS_JSON_STRING
from core.csv_profiler import profile_csv

CHARTS_MAP = {**CHARTS_JS_DEFINITIONS, **ALL_CHARTS}

# =============================================================================
# 行业筛选维度 (Industry Filter Dimensions)
# Each dimension binds one table column; options come from the resolved table rows.
# =============================================================================
AIRLINE_FILTER_DIMENSIONS = [
    ("hub", "multi-select", "枢纽基地"),
    ("routeType", "select", "航线网络"),
    ("rating", "select", "航线评级"),
]

RETAIL_FILTER_DIMENSIONS = [
    ("region", "multi-select", "所属大区"),
    ("format", "select", "门店业态"),
    ("rating", "select", "运营评级"),
]

SAAS_FILTER_DIMENSIONS = [
    ("segment", "multi-select", "客户梯队"),
    ("tier", "select", "订阅版本"),
    ("health", "select", "健康度评级"),
]

FINANCIAL_FILTER_DIMENSIONS = [
    ("segment", "multi-select", "业务板块"),
    ("auditRating", "select", "风控评级"),
]

# Legacy object filters: (group, label key, filter type).
LEGACY_FILTER_GROUPS = (
    ("seasons", "time", "select"),
    ("hubs", "hub", "multi-select"),
    ("fleets", "fleet", "select"),
    ("routes", "route", "select"),
)


def table_filters(table, dimensions):
    """Build array filters bound to table columns, taking options from the rows."""
    columns = {column["key"]: column.get("title", column["key"]) for column in table.get("columns", [])}
    rows = table.get("rows", [])
    filters = []
    for key, filter_type, label in dimensions:
        if key not in columns:
            continue
        label = label or columns[key]
        values = list(dict.fromkeys(row[key] for row in rows if row.get(key) not in (None, "")))
        options = [{"value": value, "label": value, "default": filter_type == "multi-select"} for value in values]
        if filter_type == "select":
            options.insert(0, {"value": "ALL", "label": f"全部{label}", "default": True})
        filters.append({"id": key, "key": key, "label": label, "type": filter_type,
                        "fields": [key], "componentIds": [], "options": options})
    return filters


def legacy_filters_to_array(legacy, table):
    """Bind each legacy filter group to the table column that holds its option values."""
    labels = legacy.get("labels", {})
    rows = table.get("rows", [])
    dimensions = []
    for group, label_key, filter_type in LEGACY_FILTER_GROUPS:
        values = {str(option.get("value", option.get("val"))) for option in legacy.get(group, [])} - {"ALL"}
        key = next((column["key"] for column in table.get("columns", [])
                    if values & {str(row.get(column["key"])) for row in rows}), None)
        if key and key not in {dimension[0] for dimension in dimensions}:
            dimensions.append((key, filter_type, labels.get(label_key)))
        elif values and not key:
            print(f"⚠️ Warning: legacy filter group '{group}' matches no table column, skipping.")
    return table_filters(table, dimensions)


PRESET_CONFIGS = {
    "retail_ecommerce": {
        "title": "零售连锁集团核心运营效能与商品战略研判看板",
        "subtitle": "聚焦全渠道 GMV、门店客流转化、品类坪效与会员生命周期价值多维穿透",
        "orgName": "商业集团 · 商业智能与运营决策中心",
        "periodTag": "2026 年 Q2 · 季度经营决算",
        "securityBadge": "内部战略研判 · 经营核心密级",
        "chartCodes": ["c01", "t06", "k01", "r01", "f01", "fn01", "m01", "k04"],
        "filterDimensions": RETAIL_FILTER_DIMENSIONS,
        "table": {
            "title": "全国连锁零售门店与全渠道运营效能透视表",
            "explainKey": "table_retail_main",
            "columns": RETAIL_TABLE_COLUMNS,
            "rows": RETAIL_TABLE_ROWS
        },
        "kpis": [
            {
                "id": "kpi-gmv", "type": "mc01", "label": "全渠道季度总 GMV", "value": "¥86.50 亿",
                "yoy": "+16.8% YoY", "isPositive": True, "statusBadge": "超额达成",
                "subLabel": "线下门店贡献 64.2%", "subVal": "线上即时零售 35.8%", "explainKey": "mc01"
            },
            {
                "id": "kpi-basket", "type": "mc02", "label": "全域平均客单价 (ATV)", "value": "¥168.50",
                "yoy": "+8.4% YoY", "mom": "+2.6% MoM", "isPositive": True,
                "subLabel": "连带率 (IPB)", "subVal": "3.42 件/单", "explainKey": "mc02"
            },
            {
                "id": "kpi-spark", "type": "mc03", "label": "会员活跃复购率 (Repurchase)", "value": "64.8%",
                "yoy": "+5.2 pts", "isPositive": True, "subLabel": "黑金会员留存率",
                "subVal": "88.6%", "explainKey": "mc03", "sparkline": [56, 58, 59, 61, 60, 62, 63, 62, 65, 64, 66, 64.8]
            },
            {
                "id": "kpi-sqm", "type": "mc04", "label": "重点门店日均坪效达成率", "value": "93.2%",
                "percent": 93.2, "isPositive": True, "subLabel": "综合日均坪效", "subVal": "¥158 / ㎡ / 天",
                "explainKey": "mc04"
            }
        ]
    },
    "saas_product": {
        "title": "SaaS 产品运营与用户全生命周期分析高管看板",
        "subtitle": "聚焦客户全生命周期价值 (LTV)、获客成本 (CAC)、留存率及各产品线 ARR 增长动能",
        "orgName": "企业级云计算与 SaaS 集团 · 战略运营决算部",
        "periodTag": "2026 财年 Q1 · 产品效能分析",
        "securityBadge": "内部研判 · 商用密级",
        "chartCodes": ["c02", "t04", "r02", "f01", "f03", "k01", "m02", "fn04"],
        "filterDimensions": SAAS_FILTER_DIMENSIONS,
        "table": {
            "title": "SaaS 全生命周期客户运营与续约健康度透视表",
            "explainKey": "table_saas_main",
            "columns": SAAS_TABLE_COLUMNS,
            "rows": SAAS_TABLE_ROWS
        },
        "kpis": [
            {
                "id": "kpi-arr", "type": "mc01", "label": "年度经常性收入 ARR", "value": "¥12.80 亿",
                "yoy": "+28.4% YoY", "isPositive": True, "statusBadge": "领跑行业",
                "subLabel": "净留存率 (NDR)", "subVal": "118.5%", "explainKey": "mc01"
            },
            {
                "id": "kpi-cac", "type": "mc02", "label": "获客成本回收周期 (CAC Payback)", "value": "8.5 个月",
                "yoy": "-2.1月 YoY", "mom": "-0.5月 MoM", "isPositive": True,
                "subLabel": "LTV / CAC 倍数", "subVal": "4.6x", "explainKey": "mc02"
            },
            {
                "id": "kpi-spark", "type": "mc03", "label": "月活跃企业租户 (MAU)", "value": "14,200 家",
                "yoy": "+18.2% YoY", "isPositive": True, "subLabel": "企业续约率",
                "subVal": "94.2%", "explainKey": "mc03", "sparkline": [10.2, 10.8, 11.5, 12.0, 12.4, 12.8, 13.1, 13.5, 13.8, 14.0, 14.1, 14.2]
            },
            {
                "id": "kpi-ask", "type": "mc04", "label": "年度战略营收预算推进率", "value": "88.2%",
                "percent": 88.2, "isPositive": True, "subLabel": "年度目标配额", "subVal": "¥14.50 亿元",
                "explainKey": "mc04"
            }
        ]
    },
    "financial_attribution": {
        "title": "财务边际贡献与成本费用多维穿透决算看板",
        "subtitle": "穿透主营业务收入、变动成本、资金流动桑基图与敏感性测算",
        "orgName": "集团总部 · 财务管理部与资金结算中心",
        "periodTag": "2025 全年度决算 · 财务归因审计",
        "securityBadge": "严格保密 · 财务核心决算",
        "chartCodes": ["fn01", "fn02", "fn03", "f02", "c04", "t05", "m03", "fn04"],
        "filterDimensions": FINANCIAL_FILTER_DIMENSIONS,
        "table": {
            "title": "集团各事业部经营效益与资金预算多维穿透表",
            "explainKey": "table_finance_main",
            "columns": FINANCIAL_TABLE_COLUMNS,
            "rows": FINANCIAL_TABLE_ROWS
        },
        "kpis": [
            {
                "id": "kpi-rev", "type": "mc01", "label": "集团主营业务总营收", "value": "¥148.2 亿",
                "yoy": "+15.8% YoY", "isPositive": True, "statusBadge": "审计决算",
                "subLabel": "主营业务占比", "subVal": "84.2%", "explainKey": "mc01"
            },
            {
                "id": "kpi-cask", "type": "mc02", "label": "综合运营费用率 (OPEX Ratio)", "value": "21.4%",
                "yoy": "-2.2 pts YoY", "mom": "-0.6 pts MoM", "isPositive": True,
                "subLabel": "研发资本化比例", "subVal": "38.5%", "explainKey": "mc02"
            },
            {
                "id": "kpi-spark", "type": "mc03", "label": "经营性 EBITDA 利润率", "value": "24.6%",
                "yoy": "+4.2 pts", "isPositive": True, "subLabel": "净资产收益率 (ROE)",
                "subVal": "14.8%", "explainKey": "mc03", "sparkline": [18, 19, 21, 20, 22, 23, 25, 24, 26, 24, 25, 24.6]
            },
            {
                "id": "kpi-ask", "type": "mc04", "label": "年度降本增效推进达成率", "value": "94.5%",
                "percent": 94.5, "isPositive": True, "subLabel": "节支减亏目标", "subVal": "¥8.50 亿元",
                "explainKey": "mc04"
            }
        ]
    },
    "executive_report": {
        "title": "民航核心航线与机队运营效能综合研判决算看板",
        "subtitle": "聚焦客运主营、座公里收益(RASK)、综合客座率(PLF)及核心航网收益贡献多维穿透",
        "orgName": "中国国际航空集团 · 商业智能与战略决算中心",
        "periodTag": "2026 夏秋航季 · 咨询级经营决算",
        "securityBadge": "内部战略研判 · 核心决算密级",
        "chartCodes": ["c01", "c02", "c08", "t06", "t01", "t04", "r01", "c06"],
        "filterDimensions": AIRLINE_FILTER_DIMENSIONS,
        "table": {
            "title": "民航核心航线与机队运营效能全要素透视表",
            "explainKey": "table_airline_main",
            "columns": AIRLINE_TABLE_COLUMNS,
            "rows": AIRLINE_TABLE_ROWS
        },
        "kpis": [
            {
                "id": "kpi-rev", "type": "mc01", "label": "民航客货运总营收", "value": "¥48.50 亿",
                "yoy": "+12.4% YoY", "isPositive": True, "statusBadge": "正常核算",
                "subLabel": "基期参考 ¥41.05亿", "subVal": "超额 +¥3.2亿", "explainKey": "mc01"
            },
            {
                "id": "kpi-rask", "type": "mc02", "label": "座公里收益 RASK", "value": "¥0.5420",
                "yoy": "+4.8% YoY", "mom": "+1.2% MoM", "isPositive": True,
                "subLabel": "同比增量贡献", "subVal": "+¥0.0248", "explainKey": "mc02"
            },
            {
                "id": "kpi-plf", "type": "mc03", "label": "综合客座率 PLF", "value": "86.8%",
                "yoy": "+3.5% YoY", "isPositive": True, "subLabel": "常旅客活跃度",
                "subVal": "78.5% (高粘性)", "explainKey": "mc03", "sparkline": [78, 80, 82, 79, 85, 84, 88, 86, 89, 85, 87, 86.8]
            },
            {
                "id": "kpi-ask", "type": "mc04", "label": "运力投入 ASK 年度规划达成", "value": "525.0 亿",
                "percent": 86.5, "isPositive": True, "subLabel": "年度规划目标", "subVal": "606.9 亿座公里",
                "explainKey": "mc04"
            }
        ]
    },
    "strategic_matrix": {
        "title": "战略业务组合四象限与运营风险矩阵看板",
        "subtitle": "BCG 战略四象限、相关性热力矩阵、业务拓扑关联与多维能力雷达对标",
        "orgName": "集团战略规划部 · 投资决策委员会",
        "periodTag": "2026 ~ 2028 战略规划周期",
        "securityBadge": "战略机密 · 决策委员会专阅",
        "chartCodes": ["r01", "r03", "r04", "r05", "k03", "d04", "m01", "c03"],
        "filterDimensions": AIRLINE_FILTER_DIMENSIONS,
        "table": {
            "title": "战略航网与重点业务单元效能矩阵表",
            "explainKey": "table_airline_main",
            "columns": AIRLINE_TABLE_COLUMNS,
            "rows": AIRLINE_TABLE_ROWS
        },
        "kpis": [
            {
                "id": "kpi-rev", "type": "mc01", "label": "战略通航城市对", "value": "186 对",
                "yoy": "+14 对 YoY", "isPositive": True, "statusBadge": "干支结合",
                "subLabel": "国际远程航线", "subVal": "42 条", "explainKey": "mc01"
            },
            {
                "id": "kpi-rask", "type": "mc02", "label": "商务干线平均票价指数", "value": "128.5",
                "yoy": "+8.2% YoY", "mom": "+2.4% MoM", "isPositive": True,
                "subLabel": "两舱收益溢价", "subVal": "+38.5%", "explainKey": "mc02"
            },
            {
                "id": "kpi-spark", "type": "mc03", "label": "平均资产日利用率", "value": "9.8 hr",
                "yoy": "+0.6 hr", "isPositive": True, "subLabel": "运营正点率",
                "subVal": "91.8%", "explainKey": "mc03", "sparkline": [8.8, 9.0, 9.2, 9.1, 9.5, 9.4, 9.7, 9.6, 9.9, 9.7, 9.8, 9.8]
            },
            {
                "id": "kpi-ask", "type": "mc04", "label": "战略新产品置换达成率", "value": "78.0%",
                "percent": 78.0, "isPositive": True, "subLabel": "五年规划目标", "subVal": "目标 85.0%",
                "explainKey": "mc04"
            }
        ]
    },
    "comprehensive": {
        "title": "全要素咨询图表与业务指标体系大满贯全景看板",
        "subtitle": "涵盖对比、趋势、构成、分布、关系、流程、财务、监控八大类别精选图表与多维透视表",
        "orgName": "商业咨询团队 · 高级分析与商业智能实践群",
        "periodTag": "企业级商业智能标准参考体系",
        "securityBadge": "公开标准 · 生产级交付物",
        "chartCodes": ["c01", "t06", "k01", "d04", "r01", "f02", "fn01", "m01", "k04", "c06"],
        "filterDimensions": AIRLINE_FILTER_DIMENSIONS,
        "table": {
            "title": "全要素运营效能综合透视表",
            "explainKey": "table_airline_main",
            "columns": AIRLINE_TABLE_COLUMNS,
            "rows": AIRLINE_TABLE_ROWS
        },
        "kpis": [
            {
                "id": "kpi-rev", "type": "mc01", "label": "主营业务总营收", "value": "¥48.50 亿",
                "yoy": "+12.4% YoY", "isPositive": True, "statusBadge": "全要素核算",
                "subLabel": "核心主营贡献 82.4%", "subVal": "增值业务 17.6%", "explainKey": "mc01"
            },
            {
                "id": "kpi-rask", "type": "mc02", "label": "单位可用产能收益 (RASK)", "value": "¥0.5420",
                "yoy": "+4.8% YoY", "mom": "+1.2% MoM", "isPositive": True,
                "subLabel": "单位产能成本 (CASK)", "subVal": "¥0.3810", "explainKey": "mc02"
            },
            {
                "id": "kpi-spark", "type": "mc03", "label": "综合利用率 (12M走势)", "value": "86.8%",
                "yoy": "+3.5 pts", "isPositive": True, "subLabel": "客户净推荐值 (NPS)",
                "subVal": "+76.8", "explainKey": "mc03", "sparkline": [78, 80, 82, 79, 85, 84, 88, 86, 89, 85, 87, 86.8]
            },
            {
                "id": "kpi-ask", "type": "mc04", "label": "全年度总产能投放进度", "value": "86.5%",
                "percent": 86.5, "isPositive": True, "subLabel": "已投放产能基数", "subVal": "525.0 亿单位",
                "explainKey": "mc04"
            }
        ]
    },
    "executive_monthly": {
        "title": "月度运营与财务决算高管看板",
        "subtitle": "监控当月主营收入、产能利用率、单位收益与正点率执行进展",
        "orgName": "集团总部 · 运营指挥与收益管控中心",
        "periodTag": "2026 年 3 月 · 月度经营决算",
        "securityBadge": "内部研判 · 经营决算",
        "chartCodes": ["c01", "t01", "t06", "c08", "k01", "fn02", "r01", "m01"],
        "filterDimensions": AIRLINE_FILTER_DIMENSIONS,
        "table": {
            "title": "月度核心业务单元运营决算透视表",
            "explainKey": "table_airline_main",
            "columns": AIRLINE_TABLE_COLUMNS,
            "rows": AIRLINE_TABLE_ROWS
        },
        "kpis": [
            {
                "id": "kpi-rev", "type": "mc01", "label": "月度主营总营收", "value": "¥16.20 亿",
                "yoy": "+14.5% YoY", "isPositive": True, "statusBadge": "月度决算",
                "subLabel": "月度预算达成率", "subVal": "104.2%", "explainKey": "mc01"
            },
            {
                "id": "kpi-rask", "type": "mc02", "label": "当月单位产出收益", "value": "¥0.5510",
                "yoy": "+3.8% YoY", "mom": "+0.9% MoM", "isPositive": True,
                "subLabel": "利用率调节边际", "subVal": "+¥0.0195", "explainKey": "mc02"
            },
            {
                "id": "kpi-spark", "type": "mc03", "label": "当月运营正常率", "value": "92.4%",
                "yoy": "+1.8 pts", "isPositive": True, "subLabel": "全月执行单量",
                "subVal": "14,850 次", "explainKey": "mc03", "sparkline": [88, 89, 91, 90, 93, 92, 94, 91, 93, 92, 94, 92.4]
            },
            {
                "id": "kpi-ask", "type": "mc04", "label": "月度产能供给完成率", "value": "91.5%",
                "percent": 91.5, "isPositive": True, "subLabel": "月度产能供给", "subVal": "48.2 亿单位",
                "explainKey": "mc04"
            }
        ]
    }
}

def serialize_chart_object(c):
    """Serializes a chart dict to JS object, unquoting JS functions."""
    if isinstance(c, str):
        return c
    code = str(c.get("code", "")).lower()
    uses_catalog_builder = code in CHARTS_MAP and "optionBuilder" not in c
    js_props = []
    for k, v in c.items():
        if k in ['optionBuilder', 'tableDataExtractor'] and isinstance(v, str) and (v.strip().startswith('(') or v.strip().startswith('function') or '=>' in v):
            js_props.append(f"{k}: {v}")
        else:
            js_props.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    overrides = "{\n            " + ",\n            ".join(js_props) + "\n        }"
    if uses_catalog_builder:
        # Keep chart components small: reuse the catalog renderer while replacing
        # its demo title/data/id with the explicit workspace component fields.
        return "{\n            ...(\n" + CHARTS_MAP[code] + "\n            ),\n            ..." + overrides + "\n        }"
    return overrides


def _chart_instance_id(code, index):
    """Return the stable, DOM-safe identity for one chart occurrence."""
    safe_code = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(code).lower()).strip("-")
    return f"chart-{safe_code or 'component'}-{index + 1}"

def generate_dashboard(
    preset_name="executive_report",
    chart_codes=None,
    title=None,
    org=None,
    output_path=None,
    auto_open=False,
    config_file=None,
    config_dict=None,
    from_csv=None,
    allow_preset_fallback=True
):
    """
    Compiles a complete McKinsey-grade HTML executive dashboard.
    
    Supports:
    1. Preset names: 'retail_ecommerce', 'saas_product', 'financial_attribution', 'executive_report', etc.
    2. Custom config file (JSON) or config dict with custom meta, filters, kpis, charts, table.
    3. Custom chart codes list.
    """
    # 1. Load from custom config or CSV if provided
    custom_cfg = {}
    if from_csv:
        custom_cfg = profile_csv(from_csv, custom_title=title)
    elif config_file:
        with open(config_file, 'r', encoding='utf-8') as f:
            custom_cfg = json.load(f)
    elif config_dict:
        custom_cfg = config_dict

    preset = PRESET_CONFIGS.get(preset_name, PRESET_CONFIGS["executive_report"]).copy() if allow_preset_fallback else {}

    # Merge meta
    custom_meta = custom_cfg.get("meta", {})
    page_title = title or custom_meta.get("title") or preset.get("title", "经营管理决策支持看板")
    org_name = org or custom_meta.get("org") or preset.get("orgName", "集团战略决策委员会")
    subtitle = custom_meta.get("subtitle") or preset.get("subtitle", "经营管理决策支持与运行控制系统")
    period_tag = custom_meta.get("system") or preset.get("periodTag", "2026 报告期")
    security_badge = custom_meta.get("statusText") or preset.get("securityBadge", "内部研判 · 商业密级")

    meta_dict = {
        "title": page_title,
        "subtitle": subtitle,
        "org": org_name,
        "system": period_tag,
        "statusText": security_badge
    }
    if custom_meta.get("iconKey"):
        meta_dict["iconKey"] = custom_meta["iconKey"]

    # KPIs
    kpis_config = custom_cfg["kpis"] if "kpis" in custom_cfg else preset.get("kpis", [])

    # Charts
    if "charts" in custom_cfg and isinstance(custom_cfg["charts"], list):
        if len(custom_cfg["charts"]) > 0 and isinstance(custom_cfg["charts"][0], str) and custom_cfg["charts"][0] in CHARTS_MAP:
            selected_codes = custom_cfg["charts"]
        elif len(custom_cfg["charts"]) > 0 and isinstance(custom_cfg["charts"][0], str) and custom_cfg["charts"][0].strip().startswith('{'):
            # Raw JS strings from csv_profiler or direct code
            charts_combined_js = ",\n        ".join(custom_cfg["charts"])
            selected_codes = None
        elif len(custom_cfg["charts"]) > 0 and isinstance(custom_cfg["charts"][0], dict):
            charts_combined_js = ",\n        ".join([serialize_chart_object(c) for c in custom_cfg["charts"]])
            selected_codes = None
        else:
            selected_codes = custom_cfg["charts"]
    else:
        selected_codes = chart_codes or preset.get("chartCodes", ["c01", "c02", "c08", "t06", "t01", "t04", "r01", "c06"])

    if selected_codes is not None:
        if isinstance(selected_codes, str):
            selected_codes = [c.strip().lower() for c in selected_codes.split(',') if c.strip()]

        charts_js_list = []
        for index, code in enumerate(selected_codes):
            if code in CHARTS_MAP:
                instance_id = _chart_instance_id(code, index)
                charts_js_list.append(
                    "{\n            ...(\n"
                    + CHARTS_MAP[code]
                    + f'\n            ),\n            instanceId: "{instance_id}",\n            id: "{instance_id}"\n        }}'
                )
            else:
                print(f"⚠️ Warning: Chart code '{code}' not recognized, skipping.")
        charts_combined_js = ",\n        ".join(charts_js_list)

    # Table
    if "table" in custom_cfg:
        table_config = custom_cfg["table"]
    elif preset.get("table"):
        table_config = preset["table"]
    elif allow_preset_fallback:
        table_config = {
            "title": "全要素业务运营效能透视表",
            "explainKey": "table_main",
            "columns": TABLE_COLUMNS,
            "rows": TABLE_ROWS
        }
    else:
        table_config = {"title": "数据明细", "columns": [], "rows": []}

    # Filters bind to columns of the resolved table.
    if "filters" in custom_cfg:
        filters_config = custom_cfg["filters"]
        if isinstance(filters_config, dict):
            filters_config = legacy_filters_to_array(filters_config, table_config)
    else:
        dimensions = preset.get("filterDimensions") or (AIRLINE_FILTER_DIMENSIONS if allow_preset_fallback else [])
        filters_config = table_filters(table_config, dimensions)

    # Explanations
    explanations_str = EXPLANATIONS_JSON_STRING if allow_preset_fallback else "{}"
    if "explanations" in custom_cfg:
        explanations_str = json.dumps(custom_cfg["explanations"], ensure_ascii=False)

    config_js = f"""        /**
         * =================================================================
         * 📊 DASHBOARD_CONFIG: 经营看板全局数据与配置中心
         * =================================================================
         */
        window.DASHBOARD_CONFIG = {{
            meta: {json.dumps(meta_dict, ensure_ascii=False, indent=16)},
            filters: {json.dumps(filters_config, ensure_ascii=False, indent=16)},
            kpis: {json.dumps(kpis_config, ensure_ascii=False, indent=16)},
            charts: [
                {charts_combined_js}
            ],
            table: {json.dumps(table_config, ensure_ascii=False, indent=16)},
            explanations: {explanations_str}
        }};"""

    html_content = generate_dashboard_html(config_js, page_title)

    if not output_path:
        output_path = f"./{preset_name}.html"

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as out_fp:
        out_fp.write(html_content)

    print(f"✅ Generated executive dashboard -> {output_path} ({len(html_content)} bytes)")

    if auto_open:
        subprocess.run(["open", output_path])

    return output_path

def main():
    parser = argparse.ArgumentParser(description="McKinsey-Grade Executive Dashboard Generator")
    parser.add_argument("--preset", "-p", type=str, choices=list(PRESET_CONFIGS.keys()), default="executive_report",
                        help=f"Preset dashboard style: {', '.join(PRESET_CONFIGS.keys())}")
    parser.add_argument("--from-csv", "--csv", type=str, help="Path to business CSV file to automatically profile and synthesize dashboard")
    parser.add_argument("--config", "-f", type=str, help="Path to custom JSON configuration file (Overrides meta, filters, kpis, table, charts)")
    parser.add_argument("--charts", "-c", type=str, help="Comma-separated chart codes (e.g. c01,t06,r01,fn01,m01,k04)")
    parser.add_argument("--title", "-t", type=str, help="Custom dashboard header title")
    parser.add_argument("--org", type=str, help="Custom organization/department name")
    parser.add_argument("--output", "-o", type=str, help="Target HTML output path")
    parser.add_argument("--open", action="store_true", help="Automatically open generated dashboard in default browser")

    args = parser.parse_args()

    generate_dashboard(
        preset_name=args.preset,
        chart_codes=args.charts,
        title=args.title,
        org=args.org,
        output_path=args.output,
        auto_open=args.open,
        config_file=args.config,
        from_csv=args.from_csv
    )

if __name__ == "__main__":
    main()
