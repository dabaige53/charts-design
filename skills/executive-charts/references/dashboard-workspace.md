# Composable Dashboard Workspace

Read this reference when assembling or editing a dashboard. The workspace keeps the manifest small and stores each evidence block separately.

## Layout

```text
board/
├── dashboard.json
├── filters.json
├── kpis/
│   └── revenue.json
├── charts/
│   └── regional-sales.json
└── table.json
```

`dashboard.json` contains metadata and component paths. The CLI resolves those paths only during validation and build.

## Commands

```bash
charts-design dashboard init ./board --title "经营决策看板" --org "经营分析部"

charts-design dashboard import-csv ./board --csv ./data.csv --title "渠道经营看板"

charts-design dashboard meta set ./board --subtitle "2026 年 7 月" --system "月度经营复盘"

charts-design dashboard add filter ./board region \
  --label "大区" --type multi-select \
  --option east=华东 --option south=华南 \
  --default east --default south

charts-design dashboard add kpi ./board revenue \
  --label "营业收入" --value 224 --unit "万元" --yoy "+12.6% YoY"

charts-design dashboard add kpi ./board gross-margin --from ./gross-margin.json

charts-design dashboard add chart ./board regional-sales \
  --code c01 --title "各区域营业收入" --unit "万元" \
  --data-file ./regional-sales-data.json

charts-design dashboard add chart ./board revenue-trend --from ./revenue-trend.json

charts-design dashboard table set ./board --from ./store-table.json

charts-design dashboard inspect ./board --json
charts-design dashboard validate ./board --strict --json
charts-design dashboard build ./board --output ./dist/board.html --json
```

Use `--replace` only when intentionally replacing an existing KPI or chart with the same id.

## Component schemas

### KPI

```json
{
  "id": "gross-margin",
  "type": "mc02",
  "label": "综合毛利率",
  "value": "32.3%",
  "unit": "%",
  "yoy": "+1.8 pts YoY",
  "status": "positive"
}
```

Keep the display value and unit consistent. For complex cards, add only fields used by that `mc` card type.

### Chart

```json
{
  "id": "regional-sales",
  "code": "c01",
  "title": "各区域营业收入",
  "subtitle": "华东贡献领先，华南增速更快",
  "unit": "万元",
  "data": {
    "categories": ["华东", "华南"],
    "values": [128, 96],
    "unit": "万元"
  }
}
```

The `code` selects the catalog renderer and supplies the visible Badge. The component's `title`, `subtitle`, `data` and `unit` replace catalog preview content during workspace builds.

Use a focused component file when a chart needs multiple series. Keep data values in the component; keep formatter and renderer behavior in the chart system.

### Filter

```json
{
  "id": "region",
  "key": "region",
  "label": "大区",
  "type": "multi-select",
  "options": [
    {"value": "east", "label": "华东", "default": true},
    {"value": "south", "label": "华南", "default": true}
  ]
}
```

An empty `filters.json` is valid and means the dashboard has no filters.

### Table

```json
{
  "title": "门店经营明细",
  "columns": [
    {"key": "store", "title": "门店", "align": "left"},
    {"key": "sales", "title": "销售额 (万元)", "unit": "万元", "align": "right"}
  ],
  "rows": [
    {"store": "华东一店", "sales": 128}
  ]
}
```

For large tables, generate `table.json` from source data with a deterministic script and use `dashboard table set`; keep those rows out of the manifest and ordinary `inspect` output.

## Validation contract

`dashboard validate --strict --json` returns one JSON envelope. It checks:

- workspace references stay inside the workspace and resolve to valid JSON;
- component ids are unique;
- filter definitions use the array schema;
- chart codes exist and each chart provides explicit data;
- KPI and chart units are declared;
- table columns have stable keys and titles;
- the dashboard has at least one KPI or chart.

Warnings identify missing units or incomplete executive metadata. Resolve relevant warnings before final delivery.
