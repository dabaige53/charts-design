"""Identify CSV fields and prepare reviewable workspace data."""

import csv
import os
import re
from typing import Any


def clean_num(value: str) -> float:
    """Extract a number from formatted CSV values."""
    if value is None or not str(value).strip():
        return 0.0
    cleaned = re.sub(r'[^\d.-]', '', str(value).strip())
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def profile_csv(file_path: str, custom_title: str | None = None) -> dict[str, Any]:
    """Infer column roles while retaining source cells for workspace import."""
    with open(file_path, 'r', encoding='utf-8-sig', errors='replace') as source:
        raw_rows = [
            [cell.strip() for cell in row]
            for row in csv.reader(source)
            if any(cell.strip() for cell in row)
        ]
    if len(raw_rows) < 2:
        raise ValueError("CSV must contain at least 1 header row and 1 data row.")

    headers, data_rows = raw_rows[0], raw_rows[1:]
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    time_match = re.search(r'(\d{4})[-_](\d{1,2})', base_name)
    period = ""
    if time_match:
        period = f"{time_match.group(1)}年{int(time_match.group(2))}月"
    elif '202' in base_name:
        year_match = re.search(r'202\d', base_name)
        if year_match:
            period = f"{year_match.group(0)}年度"

    name = re.sub(r'[\d_-]+', '', base_name).strip() or "业务运营"
    if name.endswith("明细"):
        name = name[:-2]
    suffix = "效能决算研判看板" if name.endswith("经营") else "经营效能决算研判看板"
    title = custom_title or f"{period}{name}{suffix}".strip()
    if not title.endswith(("看板", "报告")):
        title += "决策看板"

    columns = []
    for column_index, column_name in enumerate(headers):
        samples = [row[column_index] for row in data_rows if column_index < len(row) and row[column_index]]
        unit = ""
        unit_match = re.search(r'[\(（]([^\)）]+)[\)）]', column_name)
        if unit_match:
            unit = unit_match.group(1)
            column_name = re.sub(r'[\(（][^\)）]+[\)）]', '', column_name).strip()
        has_percent = (
            any('%' in value for value in samples)
            or '率' in column_name or '比' in column_name or unit == '%'
        )
        has_currency = (
            any(any(marker in value for marker in ('¥', '$', '元', '万', '亿')) for value in samples)
            or any(marker in column_name for marker in ('销售额', '收入', '成本', '毛利', 'GMV', 'ARR', '客单价', '坪效'))
        )
        has_days = (
            any(re.search(r'\d+(\.\d+)?\s*天', value) for value in samples)
            or any(marker in column_name for marker in ('天数', '周转天', '周期', 'DSI'))
        )
        numeric_count = 0
        for value in samples:
            try:
                float(re.sub(r'[^\d.-]', '', value))
            except ValueError:
                continue
            numeric_count += 1
        numeric = bool(samples) and numeric_count >= len(samples) * 0.7
        distinct = list(dict.fromkeys(samples))
        category = (
            any(column_name.startswith(marker) for marker in (
                '门店', '公司', '客户', '商品', '品类', '航线', '项目', '名称',
                '城市', '员工', '省份', '区域', '业态', '状态', '评级',
            ))
            and (not numeric or len(distinct) <= 15)
        )
        if category:
            kind = "category"
        elif has_percent:
            kind, unit = "percentage", unit or "%"
        elif has_currency:
            kind = "currency"
            if not unit:
                if any('万' in value for value in samples) or '万' in column_name:
                    unit = "万元"
                elif any('亿' in value for value in samples) or '亿' in column_name:
                    unit = "亿元"
                elif '坪效' in column_name:
                    unit = "元/㎡"
                else:
                    unit = "元"
        elif has_days:
            kind, unit = "duration", unit or "天"
        elif numeric and len(distinct) > 4 and column_name not in ('排名', '序号', 'ID', 'id'):
            kind = "numeric"
        else:
            kind = "category"
        columns.append({
            "index": column_index, "name": column_name, "type": kind,
            "unit": unit, "distinct": distinct,
        })

    dimensions = [
        column for column in columns
        if column["type"] == "category" and 2 <= len(column["distinct"]) <= 15
        and column["name"] not in ('排名', '序号', 'ID', 'id', '预算达成')
    ]
    filters = []
    if period:
        filters.append({
            "key": "period", "label": "统计周期", "type": "select",
            "options": [{"value": period, "label": f"{period} (当期决算)", "default": True}],
        })
    for dimension in dimensions[:3]:
        multiple = len(dimension["distinct"]) <= 6 and any(marker in dimension["name"] for marker in ('区', '地', '类'))
        options = [] if multiple else [{"value": "ALL", "label": f"全部{dimension['name']}", "default": True}]
        options.extend({"value": value, "label": value, "default": multiple} for value in dimension["distinct"])
        filters.append({
            "key": f"col_{dimension['index']}", "label": dimension["name"],
            "type": "multi-select" if multiple else "select", "options": options,
        })

    table_columns = []
    for column in columns:
        column_title = column["name"]
        unit = column["unit"]
        if unit and f"({unit})" not in column_title and f"（{unit}）" not in column_title:
            column_title = f"{column_title} ({unit})"
        table_columns.append({
            "key": f"col_{column['index']}", "title": column_title, "unit": unit,
        })
    table_rows = []
    for row in data_rows:
        values = {}
        for column in columns:
            column_index = column["index"]
            cell = row[column_index] if column_index < len(row) else ""
            values[f"col_{column_index}"] = cell
            if column["type"] in ("currency", "percentage", "numeric", "duration"):
                values[f"rawCol_{column_index}"] = clean_num(cell)
        table_rows.append(values)

    amount = next((column for column in columns if column["type"] == "currency"), None)
    if amount is None:
        amount = next((column for column in columns if column["type"] in ("numeric", "duration")), None)
    growth = next((
        column for column in columns if column["type"] == "percentage"
        and any(marker in column["name"] for marker in ('同比', '增长', '增速'))
    ), None)
    return {
        "meta": {"title": title},
        "filters": filters,
        "suggestedChartCount": int(amount is not None) + int(bool(dimensions) and amount is not None)
        + int(amount is not None and growth is not None) + int(growth is not None),
        "table": {
            "title": f"全要素{name}经营效能多维透视表",
            "columns": table_columns, "rows": table_rows,
        },
    }
