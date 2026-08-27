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
WORKSPACE_SCRIPT="skills/executive-charts/scripts/dashboard_workspace.py"

python3 "$WORKSPACE_SCRIPT" init ./board --title "经营决策看板" --org "经营分析部"

python3 "$WORKSPACE_SCRIPT" import-csv ./board --csv ./data.csv --title "渠道经营看板"

python3 "$WORKSPACE_SCRIPT" meta set ./board --subtitle "2026 年 7 月" --system "月度经营复盘"

python3 "$WORKSPACE_SCRIPT" add filter ./board region \
  --label "大区" --type multi-select \
  --option east=华东 --option south=华南 \
  --default east --default south \
  --field region --consumer revenue --consumer regional-sales

python3 "$WORKSPACE_SCRIPT" add kpi ./board revenue \
  --label "营业收入" --value 224 --unit "万元" --yoy "+12.6% YoY"

python3 "$WORKSPACE_SCRIPT" add kpi ./board gross-margin --from ./gross-margin.json

python3 "$WORKSPACE_SCRIPT" add chart ./board regional-sales \
  --from ./regional-sales.chart.json

python3 "$WORKSPACE_SCRIPT" add chart ./board revenue-trend --from ./revenue-trend.json

python3 "$WORKSPACE_SCRIPT" table set ./board --from ./store-table.json

python3 "$WORKSPACE_SCRIPT" inspect ./board --json
python3 "$WORKSPACE_SCRIPT" validate ./board --strict --json
python3 "$WORKSPACE_SCRIPT" build ./board --output ./dist/board.html \
  --manifest ./preservation.json --json
```

When the skill is installed outside this repository, set `WORKSPACE_SCRIPT` to the `scripts/dashboard_workspace.py` beside the active `SKILL.md`.

Use `--replace` for an intentional replacement of an existing KPI or chart with the same id.

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

### Strict chart presentation

All 40 registered chart codes use an explicit `presentation` object in strict mode. This object supplies the renderer with the business-facing axes, series names, Tooltip fields, units, complete table-column names, and any domains, thresholds, totals, or classification labels required by that chart shape:

```json
{
  "id": "channel-mix",
  "code": "k02",
  "title": "区域渠道结构",
  "unit": "%",
  "data": {
    "hubs": ["华东", "华南"],
    "appDirect": [48, 42],
    "corpDirect": [28, 25],
    "ota": [24, 33]
  },
  "presentation": {
    "axisLabels": {"x": "销售占比", "y": "区域"},
    "seriesLabels": ["自营", "协议客户", "第三方"],
    "tooltipValueLabels": ["自营占比", "协议客户占比", "第三方占比"],
    "units": ["%", "%", "%"],
    "tableHeaders": ["区域", "自营占比", "协议客户占比", "第三方占比"]
  }
}
```

The exact per-code field counts live in `scripts/core/component_schemas.py` as `CHART_PRESENTATION_CONTRACTS` and `CHART_TABLE_HEADER_COUNTS`. Follow the selected code's contract, then run `validate --strict --json`. The renderer reads `data` for values and transformations and reads `presentation` for display semantics. Shared geometry and interaction live in the registered renderer.

### Filter

```json
{
  "id": "region",
  "key": "region",
  "label": "大区",
  "type": "multi-select",
  "fields": ["region"],
  "componentIds": ["revenue", "regional-sales"],
  "options": [
    {"value": "east", "label": "华东", "default": true},
    {"value": "south", "label": "华南", "default": true}
  ]
}
```

`fields` is the explicit table-data binding. `componentIds` lists consumers by stable component id; chart code remains the renderer selection. An empty `filters.json` renders the dashboard with an empty filter region.

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
- strict filters declare one or more data fields, and optional consumers are component-id arrays;
- chart codes exist and each chart provides explicit data;
- KPI and chart units are declared;
- table columns have stable keys and titles;
- the dashboard has at least one KPI or chart.

Warnings identify missing units or incomplete executive metadata. Resolve relevant warnings before final delivery.

## Complete supported component surface

The workspace contract covers all shipped component families:

- KPI cards: `mc01`–`mc09` (9 types);
- chart renderers: every code returned by `generate_chart.py --list` (currently 40 codes across `c`, `d`, `f`, `fn`, `k`, `m`, `r` and `t` families);
- dynamic filters: 0–N `select` or `multi-select` components with explicit fields and consumers;
- one structured table component with stable column keys and typed units;
- shared card shell capabilities: chart/table view, export, copy, fullscreen, explanation, resize and destroy lifecycle.

`component.id` is unique and preserved. `component.code` selects the visual renderer and may repeat.

## Generated HTML inspection and migration preservation

`build` always runs strict static inspection. Use the standalone commands for an existing page or CI:

```bash
python3 "$WORKSPACE_SCRIPT" inventory-html ./before.html --output ./preservation.json --json
python3 "$WORKSPACE_SCRIPT" inspect-html ./dist/board.html --strict --manifest ./preservation.json --json
python3 "$WORKSPACE_SCRIPT" inspect-html ./dist/board.html --runtime --strict --manifest ./preservation.json --json
python3 "$WORKSPACE_SCRIPT" compare-html ./before.html ./dist/board.html --manifest ./preservation.json --json
```

A Preservation Manifest may declare `requiredIds`, `requiredText`, `forbiddenText`, `requiredAssets` and `components`. Inspection checks document metadata, duplicate ids, broken DOM references, missing local assets and manifest requirements. Comparison additionally catches baseline ids, visible text and asset references lost during migration.

`--runtime` uses Playwright with the installed Chrome channel. It loads the generated file, waits for `DashboardRuntime`, checks every rendered KPI/chart/filter/table identity and chart-card actions, rejects browser errors or duplicate rendered ids, and verifies `destroy()` clears the mounted app.

When browser execution is unavailable, record that gate as unavailable and report strict validation, static inspection, generated inline-script syntax, and lifecycle unit-test evidence separately.
