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

`dashboard.json` contains metadata and component paths. The CLI resolves those paths only during validation.

## Commands

```bash
charts-design dashboard init ./board --title "经营决策看板" --org "经营分析部"

charts-design dashboard import-csv ./board --csv ./data.csv --title "渠道经营看板"

charts-design dashboard meta set ./board --subtitle "2026 年 7 月" --system "月度经营复盘"

charts-design dashboard add kpi ./board revenue \
  --label "营业收入" --value 224 --unit "万元" --yoy "+12.6% YoY"

charts-design dashboard add kpi ./board gross-margin --from ./gross-margin.json

charts-design dashboard add chart ./board regional-sales \
  --from ./regional-sales.chart.json

charts-design dashboard add chart ./board revenue-trend --from ./revenue-trend.json

charts-design dashboard table set ./board --from ./store-table.json

charts-design dashboard inspect ./board --json
charts-design dashboard validate ./board --strict --json
```

When calling the Python script directly, invoke `skills/executive-charts/scripts/dashboard_workspace.py`.

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
  "yoy": "+1.8 pts YoY"
}
```

Keep the display value and unit consistent. Optional comparisons render as a dash when omitted. Comparison fields `yoy`, `mom`, `leftYoy` and `rightYoy` accept finite numbers or signed display text. Numbers carry their direction and the renderer adds `+` to positive values; use a metric binding to retain units and precision during filtering. Display text must preserve its sign (`+12.4%`, `-1%`). Strict validation rejects nonzero unsigned comparison text instead of silently delivering grey badges. Zero, missing values and status text stay neutral. Do not infer a business direction from an ambiguous unsigned string. Strict mode also checks the primary visual data of specialized cards:

- `mc03`: non-empty `sparkMonths` and finite `sparkData` arrays of equal length;
- `mc04` / `mc05`: a numeric display value, including zero;
- `mc06`: explicit `leftTitle`, `leftVal`, `rightTitle`, and `rightVal`;
- `mc09`: `segLeftWidth` and `segRightWidth` percentages totaling 100, with explicit `subLabel` and `subVal`;
- `mc10`: displayed median `value` and finite `stats` with `min <= p25 <= median <= p75 <= max`;
- `mc11`: `percent` (0–100 scale, may exceed 100) or a numeric display value;
- `mc12`: `sparkMonths` and finite `sparkData` of equal length, like `mc03`;
- `mc13`: finite `actual` and `target`; optional up to three ascending `ranges` (`rangeBasis: "target"` makes them fractions of target) and positive `max`;
- `mc14`: finite `currentValue` and `priorValue`;
- `mc15`: 1–4 `items`, each with `label`, `value` and an optional signed `delta`;
- `mc16`: headline `value`. KPI descriptions, subtitles and notes are forbidden.

These fields have no sample-data fallback.

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
  },
  "presentation": {
    "axisLabels": {"x": "区域", "y": "营业收入"},
    "seriesLabels": ["营业收入"],
    "tooltipValueLabels": ["营业收入"],
    "units": ["万元"],
    "tableHeaders": ["区域", "营业收入"]
  }
}
```

The `code` selects the preset renderer. The component's `title`, `subtitle`, `data` and `unit` replace catalog preview content during rendering.

Use a focused component file when a chart needs multiple series. Keep data values in the component; keep formatter and renderer behavior in the chart system.

Custom rendering uses `renderer: "echarts"` or `renderer: "html"` with an explicit `code`. See [component rendering](component-html-generation.md) for configuration and capabilities.

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

### Filter bindings

Load the table before strict validation. Every filter field must name a declared table column present in each row, and each consumer must exist and declare a supported `binding`. An empty `componentIds` array means table-only filtering. Each consumer uses only its assigned dimension filters; keyword search and chart cross-filtering apply globally. Clearing all multi-select options selects zero rows.

For a KPI whose main value is the sum of table `sales`, add:

```json
"binding": {"field": "sales", "aggregate": "sum", "precision": 0}
```

Main-value bindings support `mc01`, `mc02`, `mc04`, `mc05`, and `mc08`. Supplemental comparisons remain explicit configuration. Cards with sparkline, dual-metric, ranking, or segment data need a framework adapter for those additional calculations and cannot declare this main-value binding.

For a `c01` chart grouped by table `region`, add:

```json
"binding": {
  "groupBy": "region",
  "category": "categories",
  "series": {"values": {"field": "sales", "aggregate": "sum"}}
}
```

`category` names the renderer's category vector; `series` must bind every numeric vector in its registered schema. This path supports schemas with one string vector and one or more numeric vectors. Structured, multi-period, graph, and hierarchical shapes require an adapter; validation reports unsupported bindings instead of accepting a filter that cannot update the chart.

Aggregations are `sum`, `mean`, `min`, `max`, and `count` (non-null field values). Numeric aggregations require finite numbers already expressed in the component's display unit; they perform no string parsing or scaling. With zero matching rows, sum/count return zero and mean/min/max render as a dash. Binding recomputation updates the underlying chart data so chart view, table view, and CSV export share the same rows.

The [sample KPI](quickstart/revenue.kpi.json), [sample chart](quickstart/regional-sales.chart.json), and [sample table](quickstart/sales.table.json) form a complete runnable example. Use them only to verify tooling. The repository README provides the CLI sequence; replace example data for business delivery.

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
- strict filter fields resolve to table columns and rows; consumers resolve to components with valid aggregation bindings;
- preset chart codes exist; custom renderers declare their ECharts options or HTML content;
- KPI and chart units are declared;
- table columns have stable keys and titles;
- the dashboard has at least one KPI or chart.

Warnings identify missing units or incomplete executive metadata. Resolve relevant warnings before final delivery.

## Complete supported component surface

The workspace contract covers all shipped component families:

- KPI cards: `mc01`–`mc16` (16 types; see the selection guide in [kpi-cards.md](kpi-cards.md));
- chart renderers: 40 preset codes plus native ECharts and HTML/JavaScript declarations;
- dynamic filters: 0–N `select` or `multi-select` components with explicit fields and consumers;
- one structured table component with stable column keys and typed units;
- shared card shell capabilities: chart/table view, export, copy, fullscreen, explanation, resize and destroy lifecycle.

`component.id` is unique and preserved. `component.code` selects the visual renderer and may repeat.
