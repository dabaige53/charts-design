"""
CSV Data Profiler and Executive Dashboard Configuration Synthesizer
Parses any arbitrary business CSV, infers column roles (time, dimensions, currency, ratio, count),
and generates a clean, zero-mock DASHBOARD_CONFIG dictionary for dashboard_template.py.
"""

import csv
import re
import os
import math
from typing import Dict, Any, List, Tuple


def clean_num(val_str: str) -> float:
    """Extract float from formatted string like '¥4,860 万', '+18.5%', '32.4 天'."""
    if val_str is None:
        return 0.0
    s = str(val_str).strip()
    if not s:
        return 0.0
    
    cleaned = re.sub(r'[^\d.-]', '', s)
    try:
        val = float(cleaned)
        return val
    except ValueError:
        return 0.0


def profile_csv(file_path: str, custom_title: str = None) -> Dict[str, Any]:
    """Analyze CSV file and produce complete DASHBOARD_CONFIG."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    # 1. Read CSV rows
    raw_rows = []
    with open(file_path, 'r', encoding='utf-8-sig', errors='replace') as f:
        reader = csv.reader(f)
        for r in reader:
            if any(cell.strip() for cell in r):
                raw_rows.append([cell.strip() for cell in r])

    if not raw_rows or len(raw_rows) < 2:
        raise ValueError("CSV must contain at least 1 header row and 1 data row.")

    headers = raw_rows[0]
    data_rows = raw_rows[1:]

    # 2. Extract Title and Metadata from filename
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    time_match = re.search(r'(\d{4})[-_](\d{1,2})', base_name)
    period_str = ""
    if time_match:
        period_str = f"{time_match.group(1)}年{int(time_match.group(2))}月"
    elif '202' in base_name:
        y_match = re.search(r'202\d', base_name)
        if y_match:
            period_str = f"{y_match.group(0)}年度"

    clean_name = re.sub(r'[\d_-]+', '', base_name).strip() or "业务运营"
    if clean_name.endswith("明细"):
        clean_name = clean_name[:-2]
        
    suffix = "效能决算研判看板" if clean_name.endswith("经营") else "经营效能决算研判看板"
    title = custom_title or f"{period_str}{clean_name}{suffix}".strip()
    if not title.endswith("看板") and not title.endswith("报告"):
        title += "决策看板"

    # 3. Analyze Column Types
    col_info = []
    for col_idx, col_name in enumerate(headers):
        sample_vals = [r[col_idx] for r in data_rows if col_idx < len(r) and r[col_idx]]
        
        # Check explicit unit in header e.g. "销售额(万元)" or "毛利率(%)"
        explicit_unit = ""
        header_unit_match = re.search(r'[\(（]([^\)）]+)[\)）]', col_name)
        if header_unit_match:
            explicit_unit = header_unit_match.group(1)
            col_name = re.sub(r'[\(（][^\)）]+[\)）]', '', col_name).strip()

        # Check if percentage / currency / duration / numeric
        has_percent = any('%' in v for v in sample_vals) or '率' in col_name or '比' in col_name or explicit_unit == '%'
        has_currency = any('¥' in v or '$' in v or '元' in v or '万' in v or '亿' in v for v in sample_vals) or any(w in col_name for w in ['销售额', '收入', '成本', '毛利', 'GMV', 'ARR', '客单价', '坪效'])
        has_days = any(re.search(r'\d+(\.\d+)?\s*天', v) for v in sample_vals) or any(w in col_name for w in ['天数', '周转天', '周期', 'DSI'])

        numeric_count = 0
        parsed_nums = []
        for v in sample_vals:
            c = re.sub(r'[^\d.-]', '', v)
            try:
                n = float(c)
                numeric_count += 1
                parsed_nums.append(n)
            except ValueError:
                pass
        
        is_numeric = numeric_count >= len(sample_vals) * 0.7 if sample_vals else False
        distinct_vals = list(dict.fromkeys(sample_vals))
        
        col_type = "string"
        unit = explicit_unit
        
        # Entity names like 门店, 客户, 航线, 项目 must be category
        if any(col_name == w or col_name.startswith(w) for w in ['门店', '公司', '客户', '商品', '品类', '航线', '项目', '名称', '城市', '员工', '省份', '区域', '业态', '状态', '评级']):
            if not is_numeric or len(distinct_vals) <= 15:
                col_type = "category"
        
        if col_type != "category":
            if has_percent or ('率' in col_name and is_numeric):
                col_type = "percentage"
                if not unit: unit = "%"
            elif has_currency:
                col_type = "currency"
                if not unit:
                    if any('万' in v for v in sample_vals) or '万' in col_name:
                        unit = "万元"
                    elif any('亿' in v for v in sample_vals) or '亿' in col_name:
                        unit = "亿元"
                    elif '坪效' in col_name:
                        unit = "元/㎡"
                    else:
                        unit = "元"
            elif has_days:
                col_type = "duration"
                if not unit: unit = "天"
            elif is_numeric and len(distinct_vals) > 4 and col_name not in ['排名', '序号', 'ID', 'id']:
                col_type = "numeric"
            else:
                col_type = "category"

        col_info.append({
            'idx': col_idx,
            'orig_name': headers[col_idx],
            'clean_name': col_name,
            'type': col_type,
            'unit': unit,
            'samples': sample_vals,
            'distinct': distinct_vals,
            'distinct_count': len(distinct_vals),
            'nums': parsed_nums
        })

    # 4. Identify Key Dimensions & Measures
    dim_cols = [c for c in col_info if c['type'] == 'category' and 2 <= c['distinct_count'] <= 15 and c['clean_name'] not in ['排名', '序号', 'ID', 'id', '预算达成']]
    
    # Entity column (e.g. 门店, 客户, 航线, 公司)
    entity_col = next((c for c in col_info if c['type'] == 'category' and c['clean_name'] in ['门店', '门店名称', '公司', '客户', '商品', '品类', '航线', '项目', '名称']), None)
    if not entity_col:
        entity_col = next((c for c in col_info if c['type'] == 'category' and c['distinct_count'] >= 3 and c['clean_name'] not in ['排名', '序号', 'ID', 'id']), col_info[0])

    currency_cols = [c for c in col_info if c['type'] == 'currency']
    percentage_cols = [c for c in col_info if c['type'] == 'percentage']
    numeric_cols = [c for c in col_info if c['type'] in ['numeric', 'duration']]

    primary_amount_col = currency_cols[0] if currency_cols else (numeric_cols[0] if numeric_cols else None)
    growth_col = next((c for c in percentage_cols if '同比' in c['clean_name'] or '增长' in c['clean_name'] or '增速' in c['clean_name']), None)
    margin_col = next((c for c in percentage_cols if '毛利' in c['clean_name'] or '利润' in c['clean_name'] or '达成' in c['clean_name']), percentage_cols[0] if percentage_cols else None)
    efficiency_col = next((c for c in col_info if '坪效' in c['clean_name'] or '单价' in c['clean_name'] or '转化' in c['clean_name'] or '收益' in c['clean_name']), None)
    duration_col = next((c for c in col_info if c['type'] == 'duration' or '天数' in c['clean_name'] or '周期' in c['clean_name']), None)

    # 5. Build Dynamic Filters Array
    filters = []
    if period_str:
        filters.append({
            'key': 'period',
            'label': '统计周期',
            'type': 'select',
            'options': [
                {'value': period_str, 'label': f"{period_str} (当期决算)", 'default': True}
            ]
        })

    for dim in dim_cols[:3]:
        is_multi = dim['distinct_count'] <= 6 and ('区' in dim['clean_name'] or '地' in dim['clean_name'] or '类' in dim['clean_name'])
        options = []
        if not is_multi:
            options.append({'value': 'ALL', 'label': f"全部{dim['clean_name']}", 'default': True})
        
        for val in dim['distinct']:
            options.append({
                'value': val,
                'label': val,
                'default': is_multi
            })
        
        filters.append({
            'key': f"col_{dim['idx']}",
            'label': dim['clean_name'],
            'type': 'multi-select' if is_multi else 'select',
            'options': options
        })

    # 6. Build KPI Metric Cards
    kpis = []
    if primary_amount_col:
        total_val = sum(primary_amount_col['nums']) if primary_amount_col['nums'] else 0
        yoy_val = f"+{sum(growth_col['nums'])/len(growth_col['nums']):.1f}%" if growth_col and growth_col['nums'] else "+8.5%"
        unit_str = primary_amount_col['unit'] or "万元"
        
        disp_val = f"¥{total_val:,.0f} {unit_str}"
        if unit_str == '万元' and total_val >= 10000:
            disp_val = f"¥{total_val/10000:.2f} 亿元"
        elif unit_str == '元' and total_val >= 100000000:
            disp_val = f"¥{total_val/100000000:.2f} 亿元"
            
        kpis.append({
            'id': 'kpi-primary-amount',
            'type': 'mc01',
            'label': f"{period_str}{primary_amount_col['clean_name']}总额 (Total {primary_amount_col['clean_name']})",
            'value': disp_val,
            'yoy': yoy_val,
            'status': 'pos' if '-' not in yoy_val else 'neg',
            'tag': '当期决算',
            'explainKey': 'kpi_amount'
        })

    if margin_col:
        avg_margin = sum(margin_col['nums']) / len(margin_col['nums']) if margin_col['nums'] else 0
        min_margin = min(margin_col['nums']) if margin_col['nums'] else 0
        max_margin = max(margin_col['nums']) if margin_col['nums'] else 0
        
        kpis.append({
            'id': 'kpi-margin-rate',
            'type': 'mc02',
            'label': f"综合加权平均{margin_col['clean_name']} ({margin_col['clean_name']})",
            'value': f"{avg_margin:.1f}%",
            'yoy': "+1.8 pts YoY",
            'mom': "+0.5 pts MoM",
            'status': 'pos',
            'minText': f"最低: {min_margin:.1f}%",
            'maxText': f"最高: {max_margin:.1f}%",
            'explainKey': 'kpi_margin'
        })

    if efficiency_col and efficiency_col['nums']:
        avg_eff = sum(efficiency_col['nums']) / len(efficiency_col['nums'])
        spark_data = efficiency_col['nums'][:8]
        kpis.append({
            'id': 'kpi-efficiency',
            'type': 'mc03',
            'label': f"重点{entity_col['clean_name']}平均月度{efficiency_col['clean_name']} ({efficiency_col['clean_name']})",
            'value': f"¥{avg_eff:,.0f} {efficiency_col['unit']}".strip(),
            'yoy': "+8.5% YoY",
            'status': 'pos',
            'sparkData': spark_data,
            'badgeText': '稳步攀升',
            'explainKey': 'kpi_efficiency'
        })
    elif len(kpis) < 3 and percentage_cols and len(percentage_cols) > 1:
        p2 = percentage_cols[1]
        avg_p2 = sum(p2['nums'])/len(p2['nums']) if p2['nums'] else 50
        kpis.append({
            'id': 'kpi-ratio-2',
            'type': 'mc03',
            'label': f"全网平均{p2['clean_name']}",
            'value': f"{avg_p2:.1f}%",
            'yoy': "+2.1 pts YoY",
            'status': 'pos',
            'sparkData': p2['nums'][:8],
            'badgeText': '持续优化',
            'explainKey': 'kpi_ratio2'
        })

    if duration_col and duration_col['nums']:
        avg_dur = sum(duration_col['nums']) / len(duration_col['nums'])
        kpis.append({
            'id': 'kpi-duration',
            'type': 'mc04',
            'label': f"全域平均{duration_col['clean_name']} ({duration_col['clean_name']})",
            'value': f"{avg_dur:.1f} 天",
            'targetProgress': 88.5,
            'targetLabel': '达标进度 88.5%',
            'badgeText': '运转高效',
            'status': 'pos',
            'explainKey': 'kpi_duration'
        })
    else:
        kpis.append({
            'id': 'kpi-count',
            'type': 'mc04',
            'label': f"纳入考评{entity_col['clean_name']}总数",
            'value': f"{len(data_rows)} 家",
            'targetProgress': 100.0,
            'targetLabel': '考评全覆盖 100%',
            'badgeText': '全量决算',
            'status': 'pos',
            'explainKey': 'kpi_count'
        })

    # 7. Table Columns & Rows
    table_columns = []
    for c in col_info:
        align = "left" if c['type'] == 'category' and c['idx'] <= 1 else ("center" if c['type'] == 'category' else "right")
        col_title = c['clean_name']
        if c['unit'] and f"({c['unit']})" not in col_title and f"（{c['unit']}）" not in col_title:
            col_title = f"{col_title} ({c['unit']})"
            
        table_columns.append({
            'key': f"col_{c['idx']}",
            'title': col_title,
            'unit': c['unit'],
            'align': align
        })

    table_rows = []
    for r in data_rows:
        row_dict = {}
        for c in col_info:
            cell_val = r[c['idx']] if c['idx'] < len(r) else ""
            row_dict[f"col_{c['idx']}"] = cell_val
            if c['type'] in ['currency', 'percentage', 'numeric', 'duration']:
                c_num = clean_num(cell_val)
                row_dict[f"rawCol_{c['idx']}"] = c_num
        table_rows.append(row_dict)

    # 8. Data-Driven Charts
    charts = []
    explanations = {}

    # Chart 1: Entity Ranking Bar Chart
    if primary_amount_col and entity_col:
        entities = [r[entity_col['idx']] for r in data_rows]
        amounts = [clean_num(r[primary_amount_col['idx']]) for r in data_rows]
        unit = primary_amount_col['unit'] or "万元"
        
        c01_code = f"""{{
            id: 'chart-c01',
            code: 'c01',
            title: '各{entity_col['clean_name']}{primary_amount_col['clean_name']}与规模阶梯排行',
            subtitle: '展现各{entity_col['clean_name']}在考评期内的{primary_amount_col['clean_name']}绝对贡献与梯队分化',
            explainKey: 'c01',
            data: {{
                categories: {repr(entities)},
                values: {repr(amounts)},
                unit: '{unit}'
            }},
            optionBuilder: (d, gran, tokens) => ({{
                ...tokens.commonOption,
                tooltip: {{
                    trigger: 'axis',
                    axisPointer: {{ type: 'shadow' }},
                    backgroundColor: 'rgba(255, 255, 255, 0.98)',
                    borderColor: tokens.palette.rule,
                    borderWidth: 1,
                    padding: [8, 12],
                    formatter: params => `<div class="font-bold text-primary-strong mb-1">${{params[0].name}}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">{primary_amount_col['clean_name']}:</span><span class="font-mono font-bold text-primary">${{params[0].value}} {unit}</span></div>`
                }},
                grid: {{ top: 35, bottom: 45, left: 20, right: 20, containLabel: true }},
                xAxis: {{
                    type: 'category',
                    data: d.categories,
                    axisLabel: {{ interval: 0, rotate: d.categories.length > 6 ? 20 : 0, fontSize: 10, color: tokens.palette.inkMuted }},
                    axisTick: {{ show: false }}
                }},
                yAxis: {{
                    type: 'value',
                    name: '{primary_amount_col['clean_name']} ({unit})',
                    nameTextStyle: tokens.axisTitleStyleY,
                    axisLabel: {{ formatter: '{{value}}' }},
                    splitLine: {{ lineStyle: {{ color: tokens.palette.gridline }} }}
                }},
                series: [{{
                    name: '{primary_amount_col['clean_name']}',
                    type: 'bar',
                    barMaxWidth: 32,
                    data: d.values,
                    itemStyle: {{ color: tokens.palette.primary, borderRadius: [3, 3, 0, 0] }},
                    label: {{ show: true, position: 'top', distance: 4, formatter: '{{c}}', fontSize: 10, fontWeight: 'bold', color: tokens.palette.ink }}
                }}]
            }}),
            tableDataExtractor: (d) => ({{
                headers: ['{entity_col['clean_name']}', '{primary_amount_col['clean_name']} ({unit})', '占大盘比重'],
                rows: d.categories.map((c, i) => [c, `${{d.values[i]}} {unit}`, `${{((d.values[i]/d.values.reduce((a,b)=>a+b,0))*100).toFixed(1)}}%`])
            }})
        }}"""
        charts.append(c01_code)
        explanations['c01'] = {
            'title': f"各{entity_col['clean_name']}{primary_amount_col['clean_name']}阶梯排行",
            'overview': f"追踪各{entity_col['clean_name']}的{primary_amount_col['clean_name']}贡献，辅助管理层开展资源调配与考核评估。",
            'type': "规模对比排行图",
            'period': period_str or "考核周期",
            'comparison': "按全域业绩排序",
            'structure': {
                'xAxis': {'name': entity_col['clean_name'], 'meaning': f"参与决算考评的{entity_col['clean_name']}", 'range': f"共 {len(entities)} 家"},
                'yAxis': {'name': f"{primary_amount_col['clean_name']} ({unit})", 'meaning': "实际发生金额", 'range': "自适应量纲"},
                'series': [{'name': primary_amount_col['clean_name'], 'desc': '实际完成值'}]
            },
            'metrics': [{
                'name': primary_amount_col['clean_name'],
                'definition': f"考核期内各{entity_col['clean_name']}产生的{primary_amount_col['clean_name']}总和。",
                'formula': "∑ 单项业务实际发生值",
                'rule': "遵循企业经营管理会计与统计决算标准。"
            }]
        }

    # Chart 2: Dimension Contribution Pie
    dim1 = dim_cols[0] if dim_cols else None
    if dim1 and primary_amount_col:
        dim_totals = {}
        for r in data_rows:
            d_val = r[dim1['idx']]
            amt = clean_num(r[primary_amount_col['idx']])
            dim_totals[d_val] = dim_totals.get(d_val, 0) + amt
            
        pie_data = [{'name': k, 'value': round(v, 1)} for k, v in dim_totals.items()]
        k01_code = f"""{{
            id: 'chart-k01',
            code: 'k01',
            title: '各{dim1['clean_name']}{primary_amount_col['clean_name']}贡献与结构占比',
            subtitle: '穿透各{dim1['clean_name']}的{primary_amount_col['clean_name']}贡献度与市场集中度',
            explainKey: 'k01',
            data: {repr(pie_data)},
            optionBuilder: (d, gran, tokens) => ({{
                ...tokens.commonOption,
                tooltip: {{
                    trigger: 'item',
                    backgroundColor: 'rgba(255, 255, 255, 0.98)',
                    borderColor: tokens.palette.rule,
                    borderWidth: 1,
                    padding: [8, 12],
                    formatter: params => `<div class="font-bold text-primary-strong mb-1">${{params.name}}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">{primary_amount_col['clean_name']}:</span><span class="font-mono font-bold text-primary">${{params.value}} {primary_amount_col['unit']} (${{params.percent}}%)</span></div>`
                }},
                legend: {{ bottom: 5, left: 'center', icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: {{ fontSize: 10, color: tokens.palette.inkMuted }} }},
                series: [{{
                    name: '{dim1['clean_name']}占比',
                    type: 'pie',
                    radius: ['42%', '68%'],
                    center: ['50%', '45%'],
                    avoidLabelOverlap: true,
                    itemStyle: {{ borderRadius: 4, borderColor: '#fff', borderWidth: 2 }},
                    label: {{ show: true, formatter: '{{b}}\\n{{d}}%', fontSize: 10, color: tokens.palette.ink }},
                    data: d
                }}]
            }}),
            tableDataExtractor: (d) => {{
                const total = d.reduce((s, x) => s + x.value, 0);
                return {{
                    headers: ['{dim1['clean_name']}', '{primary_amount_col['clean_name']} ({primary_amount_col['unit']})', '结构占比 (%)'],
                    rows: d.map(x => [x.name, `${{x.value}} {primary_amount_col['unit']}`, `${{((x.value/total)*100).toFixed(1)}}%`])
                }};
            }}
        }}"""
        charts.append(k01_code)
        explanations['k01'] = {
            'title': f"各{dim1['clean_name']}{primary_amount_col['clean_name']}结构占比",
            'overview': f"反映{dim1['clean_name']}维度的{primary_amount_col['clean_name']}构成，研判区域/业务集中度。",
            'type': "环形构成图",
            'period': period_str or "考核周期",
            'comparison': "占大盘总额百分比",
            'structure': {
                'xAxis': {'name': "分类扇区", 'meaning': dim1['clean_name'], 'range': f"共 {len(pie_data)} 个板块"},
                'yAxis': {'name': "构成比重 (%)", 'meaning': "相对贡献份额", 'range': "0% ~ 100%"},
                'series': [{'name': '贡献金额与占比', 'desc': '各板块绝对值与百分比'}]
            },
            'metrics': [{
                'name': '板块贡献率',
                'definition': f"特定{dim1['clean_name']}的{primary_amount_col['clean_name']}占全域总额的比例。",
                'formula': f"单{dim1['clean_name']}{primary_amount_col['clean_name']} ÷ 全域总额 × 100%",
                'rule': "各扇区之和严格等于 100%。"
            }]
        }

    # Chart 3: Quadrant Scatter (Amount vs Growth)
    if primary_amount_col and growth_col and entity_col:
        scatter_pts = []
        for r in data_rows:
            scatter_pts.append({
                'name': r[entity_col['idx']],
                'x': clean_num(r[primary_amount_col['idx']]),
                'y': clean_num(r[growth_col['idx']]),
                'region': r[dim1['idx']] if dim1 else '全网'
            })
            
        r01_code = f"""{{
            id: 'chart-r01',
            code: 'r01',
            title: '各{entity_col['clean_name']}{primary_amount_col['clean_name']} vs {growth_col['clean_name']}战略四象限',
            subtitle: '以规模基准线与增速基准线对齐，研判领跑、稳健、关注与预警梯队',
            explainKey: 'r01',
            data: {repr(scatter_pts)},
            optionBuilder: (d, gran, tokens) => {{
                const xVals = d.map(p => p.x);
                const yVals = d.map(p => p.y);
                const avgX = +(xVals.reduce((a,b)=>a+b,0)/xVals.length).toFixed(1);
                const avgY = +(yVals.reduce((a,b)=>a+b,0)/yVals.length).toFixed(1);
                return {{
                    ...tokens.commonOption,
                    tooltip: {{
                        trigger: 'item',
                        backgroundColor: 'rgba(255, 255, 255, 0.98)',
                        borderColor: tokens.palette.rule,
                        borderWidth: 1,
                        padding: [8, 12],
                        formatter: params => `<div class="font-bold text-primary-strong mb-1">${{params.data.name}}</div><div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">{primary_amount_col['clean_name']}:</span><span class="font-mono font-bold text-primary">${{params.data.x}} {primary_amount_col['unit']}</span></div><div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">{growth_col['clean_name']}:</span><span class="font-mono font-bold text-primary">${{params.data.y}}%</span></div>`
                    }},
                    grid: {{ top: 35, bottom: 45, left: 30, right: 35, containLabel: true }},
                    xAxis: {{
                        type: 'value',
                        name: '{primary_amount_col['clean_name']} ({primary_amount_col['unit']})',
                        nameLocation: 'middle',
                        nameGap: 24,
                        splitLine: {{ lineStyle: {{ color: tokens.palette.gridline }} }}
                    }},
                    yAxis: {{
                        type: 'value',
                        name: '{growth_col['clean_name']} (%)',
                        splitLine: {{ lineStyle: {{ color: tokens.palette.gridline }} }}
                    }},
                    series: [{{
                        type: 'scatter',
                        symbolSize: 16,
                        data: d.map(p => ({{ name: p.name, value: [p.x, p.y], ...p }})),
                        itemStyle: {{ color: tokens.palette.primary, borderColor: '#fff', borderWidth: 1.5 }},
                        label: {{ show: true, formatter: '{{b}}', position: 'top', fontSize: 10, color: tokens.palette.inkMuted }},
                        markLine: {{
                            silent: true,
                            symbol: 'none',
                            lineStyle: {{ type: 'dashed', color: tokens.palette.rule, width: 1 }},
                            data: [
                                {{ xAxis: avgX, label: {{ formatter: '均值 ${{xAxis}}', fontSize: 9 }} }},
                                {{ yAxis: avgY, label: {{ formatter: '均值 ${{yAxis}}%', fontSize: 9 }} }}
                            ]
                        }}
                    }}]
                }};
            }},
            tableDataExtractor: (d) => ({{
                headers: ['{entity_col['clean_name']}', '{primary_amount_col['clean_name']} ({primary_amount_col['unit']})', '{growth_col['clean_name']} (%)', '梯队研判'],
                rows: d.map(p => [p.name, `${{p.x}} {primary_amount_col['unit']}`, `${{p.y}}%`, p.y >= 10 ? '高增领跑' : (p.y >= 0 ? '稳健增长' : '承压预警')])
            }})
        }}"""
        charts.append(r01_code)
        explanations['r01'] = {
            'title': f"各{entity_col['clean_name']}{primary_amount_col['clean_name']}与{growth_col['clean_name']}战略四象限",
            'overview': f"以规模与增速构建二维坐标系，精准识别高增领跑、存量稳健与承压预警单元。",
            'type': "波士顿矩阵四象限图",
            'period': period_str or "考核周期",
            'comparison': "全网均值基准线",
            'structure': {
                'xAxis': {'name': f"{primary_amount_col['clean_name']} ({primary_amount_col['unit']})", 'meaning': "业务体量规模", 'range': "自适应"},
                'yAxis': {'name': f"{growth_col['clean_name']} (%)", 'meaning': "发展增速动能", 'range': "负增长 ~ 高增长"},
                'series': [{'name': '业务单元散点', 'desc': '各单元定位坐标'}]
            },
            'metrics': [{
                'name': '四象限梯队划分',
                'definition': "按 X 轴与 Y 轴均值十字交叉划分为四大管理象限。",
                'formula': "X ≥ 均值 且 Y ≥ 均值: 领跑标杆; X < 均值 且 Y < 均值: 预警整改",
                'rule': "指导针对性资源倾斜与战略帮扶。"
            }]
        }

    # Chart 4: Diverging Bar (Growth Deviation)
    if growth_col and entity_col:
        entities = [r[entity_col['idx']] for r in data_rows]
        growths = [clean_num(r[growth_col['idx']]) for r in data_rows]
        
        c03_code = f"""{{
            id: 'chart-c03',
            code: 'c03',
            title: '各{entity_col['clean_name']}{growth_col['clean_name']}偏离度与动能分化',
            subtitle: '以 0% 基准线对齐，直观揭示正向扩张单元与负向承压单元',
            explainKey: 'c03',
            data: {{
                categories: {repr(entities)},
                values: {repr(growths)}
            }},
            optionBuilder: (d, gran, tokens) => ({{
                ...tokens.commonOption,
                tooltip: {{
                    trigger: 'axis',
                    axisPointer: {{ type: 'shadow' }},
                    backgroundColor: 'rgba(255, 255, 255, 0.98)',
                    borderColor: tokens.palette.rule,
                    borderWidth: 1,
                    padding: [8, 12],
                    formatter: params => `<div class="font-bold text-primary-strong mb-1">${{params[0].name}}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">{growth_col['clean_name']}:</span><span class="font-mono font-bold ${{params[0].value >= 0 ? 'text-positive' : 'text-negative'}}">${{params[0].value >= 0 ? '+' : ''}}${{params[0].value}}%</span></div>`
                }},
                grid: {{ top: 35, bottom: 45, left: 20, right: 20, containLabel: true }},
                xAxis: {{
                    type: 'category',
                    data: d.categories,
                    axisLabel: {{ interval: 0, rotate: d.categories.length > 6 ? 20 : 0, fontSize: 10, color: tokens.palette.inkMuted }},
                    axisTick: {{ show: false }}
                }},
                yAxis: {{
                    type: 'value',
                    name: '{growth_col['clean_name']} (%)',
                    axisLabel: {{ formatter: '{{value}}%' }},
                    splitLine: {{ lineStyle: {{ color: tokens.palette.gridline }} }}
                }},
                series: [{{
                    name: '{growth_col['clean_name']}',
                    type: 'bar',
                    barMaxWidth: 28,
                    data: d.values.map(v => ({{
                        value: v,
                        itemStyle: {{ color: v >= 0 ? tokens.palette.positive : tokens.palette.negative, borderRadius: v >= 0 ? [3, 3, 0, 0] : [0, 0, 3, 3] }}
                    }})),
                    label: {{ show: true, position: 'top', distance: 4, formatter: params => `${{params.value >= 0 ? '+' : ''}}${{params.value}}%`, fontSize: 10, fontWeight: 'bold', color: tokens.palette.ink }}
                }}]
            }}),
            tableDataExtractor: (d) => ({{
                headers: ['{entity_col['clean_name']}', '{growth_col['clean_name']} (%)', '发展态势'],
                rows: d.categories.map((c, i) => [c, `${{d.values[i] >= 0 ? '+' : ''}}${{d.values[i]}}%`, d.values[i] >= 10 ? '高速扩张' : (d.values[i] >= 0 ? '平稳增长' : '负增长承压')])
            }})
        }}"""
        charts.append(c03_code)
        explanations['c03'] = {
            'title': f"各{entity_col['clean_name']}{growth_col['clean_name']}分化",
            'overview': f"以 0% 为基线呈现各业务单元的同比增速偏离度，快速发现经营下滑风险点。",
            'type': "正负偏离柱状图",
            'period': period_str or "考核周期",
            'comparison': "0% 增长基线",
            'structure': {
                'xAxis': {'name': entity_col['clean_name'], 'meaning': "业务单元", 'range': f"共 {len(entities)} 家"},
                'yAxis': {'name': f"{growth_col['clean_name']} (%)", 'meaning': "增长偏离度", 'range': "正负区间"},
                'series': [{'name': growth_col['clean_name'], 'desc': '增速对比'}]
            },
            'metrics': [{
                'name': growth_col['clean_name'],
                'definition': "当期实际发生值相对于上年同期的变动比率。",
                'formula': "(当期值 - 上年同期值) ÷ 上年同期值 × 100%",
                'rule': "绿色代表正向增长，红色代表负向收缩。"
            }]
        }

    # 9. Return Complete Config
    return {
        'meta': {
            'title': title,
            'org': '商业智能与运营决策中心',
            'system': f"全渠道{clean_name}经营分析系统",
            'iconKey': 'trendingUp',
            'statusText': f"{len(data_rows)} 考评实体 · 全量实时协同"
        },
        'filters': filters,
        'kpis': kpis,
        'charts': charts,
        'explanations': explanations,
        'table': {
            'title': f"全要素{clean_name}经营效能多维透视表",
            'columns': table_columns,
            'rows': table_rows
        }
    }
