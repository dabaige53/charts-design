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
    1. Top Global Multi-Dimensional Filter Bar (Seasons, 4 Hubs, Fleets, Routes,
       and Search with real-time autocomplete suggestions & category tags)
    2. 4 Top-Tier KPI Metric Cards (Sparklines, Progress, Trend badges)
    3. Responsive Sectioned Chart Grid (5-action toolbar, chart/table views, CSV export, PNG copy,
       fullscreen focus, explanation dialogs)
    4. 14-Column Multi-Metric Interactive Pivot Table (Drag & Drop column reordering,
       visibility drawer, nowrap single-line layout, horizontal scroll, sorting, pagination, CSV)
    5. Native Explanation Dialog (Business overview, coordinates & series architecture,
       formula cards & governance rules)

Usage Examples:
    # 1. Generate preset dashboards
    python generate_dashboard.py --preset executive_report --output ./dist/executive_report.html --open
    python generate_dashboard.py --preset saas_product --output ./dist/saas_dashboard.html
    python generate_dashboard.py --preset financial_attribution --output ./dist/financial.html
    python generate_dashboard.py --preset strategic_matrix --output ./dist/strategic.html
    python generate_dashboard.py --preset comprehensive --output ./dist/comprehensive.html
    python generate_dashboard.py --preset executive_monthly --output ./dist/monthly.html

    # 2. Compose a custom dashboard with any chart codes
    python generate_dashboard.py --charts "c01,t06,k01,r01,fn01,m01,k04,c06" \
        --title "集团核心运营效能与财务战略研判看板" \
        --org "中国国际航空集团 · 战略财务部" \
        --output ./dist/custom_dashboard.html --open

    # 3. Batch generate all 6 standard dashboards
    python generate_dashboard.py --batch --outdir ./dist/dashboards/
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

from core.table_data import TABLE_COLUMNS, TABLE_ROWS
from core.chart_builders import CHARTS_JS_DEFINITIONS
from core.chart_catalog import ALL_CHARTS
from core.dashboard_template import generate_dashboard_html
from core.explanations import EXPLANATIONS_JSON_STRING

CHARTS_MAP = {**CHARTS_JS_DEFINITIONS, **ALL_CHARTS}

GLOBAL_FILTERS_CONFIG = {
    "seasons": [
        {"val": "2026S", "label": "2026夏秋航季"},
        {"val": "2025W", "label": "2025冬春航季"},
        {"val": "2025S", "label": "2025夏秋航季"},
        {"val": "2024FY", "label": "2024全航季基准"}
    ],
    "hubs": [
        {"val": "华东基地", "label": "华东基地 (虹桥 SHA / 浦东 PVG)", "desc": "长三角核心枢纽", "default": True},
        {"val": "北方基地", "label": "北方基地 (大兴 PKX / 首都 PEK)", "desc": "京津冀战略枢纽", "default": True},
        {"val": "华南基地", "label": "华南基地 (白云 CAN / 宝安 SZX)", "desc": "粤港澳大湾区", "default": True},
        {"val": "西南基地", "label": "西南基地 (天府 TFU / 双流 CTU)", "desc": "成渝双城经济圈", "default": True}
    ],
    "fleets": [
        {"val": "ALL", "label": "全部机型 (全机队)"},
        {"val": "WIDE", "label": "远程宽体客机 (A350 / B787 / B777)"},
        {"val": "NARROW", "label": "中短程窄体客机 (A321neo / B737)"},
        {"val": "DOMESTIC", "label": "国产商用客机 (C919 / ARJ21)"}
    ],
    "routes": [
        {"val": "ALL", "label": "全部航线网络 (全网)"},
        {"val": "TRUNK", "label": "国内核心商务干线 (京沪/京广/沪深)"},
        {"val": "REGIONAL", "label": "区域互联支线网络 (西部/海岛/旅游)"},
        {"val": "INTL", "label": "国际及地区航线 (洲际远程/一带一路)"}
    ]
}

PRESET_CONFIGS = {
    "executive_report": {
        "title": "民航核心航线与机队运营效能综合研判决算看板",
        "subtitle": "聚焦客运主营、座公里收益(RASK)、综合客座率(PLF)及核心航网收益贡献多维穿透",
        "orgName": "中国国际航空集团 · 商业智能与战略决算中心",
        "periodTag": "2026 夏秋航季 · 咨询级经营决算",
        "securityBadge": "内部战略研判 · 核心决算密级",
        "chartCodes": ["c01", "c02", "c08", "t06", "t01", "t04", "r01", "c06"],
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
    "saas_product": {
        "title": "SaaS 产品运营与用户全生命周期分析高管看板",
        "subtitle": "聚焦客户全生命周期价值 (LTV)、获客成本 (CAC)、留存率及各产品线 ARR 增长动能",
        "orgName": "企业级云计算与 SaaS 集团 · 战略运营决算部",
        "periodTag": "2026 财年 Q1 · 产品效能分析",
        "securityBadge": "内部研判 · 商用密级",
        "chartCodes": ["c02", "t04", "r02", "f01", "f03", "k01", "m02", "fn04"],
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
        "subtitle": "穿透客货运主营收入、航油及起降变动成本、资金流动桑基图与敏感性测算",
        "orgName": "民航航空集团 · 财务管理部与资金结算中心",
        "periodTag": "2025 全年度决算 · 财务归因审计",
        "securityBadge": "严格保密 · 财务核心决算",
        "chartCodes": ["fn01", "fn02", "fn03", "f02", "c04", "t05", "m03", "fn04"],
        "kpis": [
            {
                "id": "kpi-rev", "type": "mc01", "label": "集团客货运总营收", "value": "¥148.2 亿",
                "yoy": "+15.8% YoY", "isPositive": True, "statusBadge": "审计决算",
                "subLabel": "客运主营占比", "subVal": "84.2%", "explainKey": "mc01"
            },
            {
                "id": "kpi-cask", "type": "mc02", "label": "座公里成本 CASK", "value": "¥0.3820",
                "yoy": "-3.2% YoY", "mom": "-1.1% MoM", "isPositive": True,
                "subLabel": "航油单位成本", "subVal": "¥0.1180", "explainKey": "mc02"
            },
            {
                "id": "kpi-spark", "type": "mc03", "label": "经营性 EBITDA 利润率", "value": "24.6%",
                "yoy": "+4.2 pts", "isPositive": True, "subLabel": "净资产收益率",
                "subVal": "14.8%", "explainKey": "mc03", "sparkline": [18, 19, 21, 20, 22, 23, 25, 24, 26, 24, 25, 24.6]
            },
            {
                "id": "kpi-ask", "type": "mc04", "label": "年度降本增效推进达成率", "value": "94.5%",
                "percent": 94.5, "isPositive": True, "subLabel": "节支减亏目标", "subVal": "¥8.50 亿元",
                "explainKey": "mc04"
            }
        ]
    },
    "strategic_matrix": {
        "title": "战略业务组合四象限与运营风险矩阵看板",
        "subtitle": "BCG 战略四象限、相关性热力矩阵、全国航网拓扑关联与多维能力雷达对标",
        "orgName": "集团战略规划部 · 航网编排与投资决策委员会",
        "periodTag": "2026 ~ 2028 战略规划周期",
        "securityBadge": "战略机密 · 决策委员会专阅",
        "chartCodes": ["r01", "r03", "r04", "r05", "k03", "d04", "m01", "c03"],
        "kpis": [
            {
                "id": "kpi-rev", "type": "mc01", "label": "战略航网通航城市对", "value": "186 对",
                "yoy": "+14 对 YoY", "isPositive": True, "statusBadge": "干支结合",
                "subLabel": "国际远程航线", "subVal": "42 条", "explainKey": "mc01"
            },
            {
                "id": "kpi-rask", "type": "mc02", "label": "商务航线平均票价收益指数", "value": "128.5",
                "yoy": "+8.2% YoY", "mom": "+2.4% MoM", "isPositive": True,
                "subLabel": "两舱收益溢价", "subVal": "+38.5%", "explainKey": "mc02"
            },
            {
                "id": "kpi-spark", "type": "mc03", "label": "机队平均日利用率 (小时)", "value": "9.8 hr",
                "yoy": "+0.6 hr", "isPositive": True, "subLabel": "准点率 (OTP)",
                "subVal": "91.8%", "explainKey": "mc03", "sparkline": [8.8, 9.0, 9.2, 9.1, 9.5, 9.4, 9.7, 9.6, 9.9, 9.7, 9.8, 9.8]
            },
            {
                "id": "kpi-ask", "type": "mc04", "label": "新一代节能机队置换率", "value": "78.0%",
                "percent": 78.0, "isPositive": True, "subLabel": "十四五机队规划", "subVal": "目标 85.0%",
                "explainKey": "mc04"
            }
        ]
    },
    "comprehensive": {
        "title": "全要素咨询图表与业务指标体系大满贯全景看板",
        "subtitle": "涵盖对比、趋势、构成、分布、关系、流程、财务、监控八大类别精选图表与 14 列透视表",
        "orgName": "麦肯锡咨询团队 · 高级分析与商业智能实践群",
        "periodTag": "企业级商业智能标准参考体系",
        "securityBadge": "公开标准 · 生产级交付物",
        "chartCodes": ["c01", "t06", "k01", "d04", "r01", "f02", "fn01", "m01", "k04", "c06"],
        "kpis": [
            {
                "id": "kpi-rev", "type": "mc01", "label": "全网主营业务总营收", "value": "¥48.50 亿",
                "yoy": "+12.4% YoY", "isPositive": True, "statusBadge": "全要素核算",
                "subLabel": "客运贡献 82.4%", "subVal": "货邮辅营 17.6%", "explainKey": "mc01"
            },
            {
                "id": "kpi-rask", "type": "mc02", "label": "单位可用座公里收益 RASK", "value": "¥0.5420",
                "yoy": "+4.8% YoY", "mom": "+1.2% MoM", "isPositive": True,
                "subLabel": "单位座公里成本 CASK", "subVal": "¥0.3810", "explainKey": "mc02"
            },
            {
                "id": "kpi-spark", "type": "mc03", "label": "综合客座率 PLF (12M走势)", "value": "86.8%",
                "yoy": "+3.5 pts", "isPositive": True, "subLabel": "旅客净推荐值 (NPS)",
                "subVal": "+76.8", "explainKey": "mc03", "sparkline": [78, 80, 82, 79, 85, 84, 88, 86, 89, 85, 87, 86.8]
            },
            {
                "id": "kpi-ask", "type": "mc04", "label": "全年度总运力投放进度", "value": "86.5%",
                "percent": 86.5, "isPositive": True, "subLabel": "已投放可用座公里", "subVal": "525.0 亿座公里",
                "explainKey": "mc04"
            }
        ]
    },
    "executive_monthly": {
        "title": "月度民航运营与财务决算高管看板",
        "subtitle": "监控当月主营收入、客座率、RASK 与航班正常率执行进展",
        "orgName": "中国国际航空集团 · 运营指挥与收益管控中心",
        "periodTag": "2026 年 3 月 · 月度经营决算",
        "securityBadge": "内部研判 · 经营决算",
        "chartCodes": ["c01", "t01", "t06", "c08", "k01", "fn02", "r01", "m01"],
        "kpis": [
            {
                "id": "kpi-rev", "type": "mc01", "label": "月度客货运总营收", "value": "¥16.20 亿",
                "yoy": "+14.5% YoY", "isPositive": True, "statusBadge": "月度决算",
                "subLabel": "月度预算达成率", "subVal": "104.2%", "explainKey": "mc01"
            },
            {
                "id": "kpi-rask", "type": "mc02", "label": "当月座公里收益 RASK", "value": "¥0.5510",
                "yoy": "+3.8% YoY", "mom": "+0.9% MoM", "isPositive": True,
                "subLabel": "客座率调节边际", "subVal": "+¥0.0195", "explainKey": "mc02"
            },
            {
                "id": "kpi-spark", "type": "mc03", "label": "当月航班正常率 (OTP)", "value": "92.4%",
                "yoy": "+1.8 pts", "isPositive": True, "subLabel": "全月执行班次",
                "subVal": "14,850 架次", "explainKey": "mc03", "sparkline": [88, 89, 91, 90, 93, 92, 94, 91, 93, 92, 94, 92.4]
            },
            {
                "id": "kpi-ask", "type": "mc04", "label": "月度运力可用座公里完成", "value": "91.5%",
                "percent": 91.5, "isPositive": True, "subLabel": "月度运力供给", "subVal": "48.2 亿座公里",
                "explainKey": "mc04"
            }
        ]
    }
}

def generate_dashboard(preset_name="executive_report", chart_codes=None, title=None, org=None, output_path=None, auto_open=False):
    """Compiles a complete McKinsey-grade HTML executive dashboard."""
    preset = PRESET_CONFIGS.get(preset_name, PRESET_CONFIGS["executive_report"]).copy()

    page_title = title or preset["title"]
    org_name = org or preset["orgName"]
    subtitle = preset.get("subtitle", "经营管理决策支持与运行控制系统")
    period_tag = preset.get("periodTag", "2026 报告期")
    security_badge = preset.get("securityBadge", "内部研判 · 商业密级")

    selected_codes = chart_codes or preset.get("chartCodes", ["c01", "c02", "c08", "t06", "t01", "t04", "r01", "c06"])
    if isinstance(selected_codes, str):
        selected_codes = [c.strip().lower() for c in selected_codes.split(',') if c.strip()]

    charts_js_list = []
    for code in selected_codes:
        if code in CHARTS_MAP:
            charts_js_list.append(CHARTS_MAP[code])
        else:
            print(f"⚠️ Warning: Chart code '{code}' not recognized, skipping.")

    charts_combined_js = ",\n        ".join(charts_js_list)

    meta_dict = {
        "title": page_title,
        "subtitle": subtitle,
        "org": org_name,
        "system": period_tag,
        "statusText": security_badge
    }

    config_js = f"""        /**
         * =================================================================
         * 📊 DASHBOARD_CONFIG: 经营看板全局数据与配置中心
         * =================================================================
         */
        window.DASHBOARD_CONFIG = {{
            meta: {json.dumps(meta_dict, ensure_ascii=False, indent=16)},
            filters: {json.dumps(GLOBAL_FILTERS_CONFIG, ensure_ascii=False, indent=16)},
            kpis: {json.dumps(preset.get("kpis", []), ensure_ascii=False, indent=16)},
            charts: [
                {charts_combined_js}
            ],
            table: {{
                title: "民航核心航线与机队运营效能全要素透视表",
                explainKey: "table_airline_main",
                columns: {json.dumps(TABLE_COLUMNS, ensure_ascii=False, indent=16)},
                rows: {json.dumps(TABLE_ROWS, ensure_ascii=False, indent=16)}
            }},
            explanations: {EXPLANATIONS_JSON_STRING}
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
        auto_open=args.open
    )

if __name__ == "__main__":
    main()
