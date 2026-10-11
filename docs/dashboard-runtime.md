# Dashboard and Analysis Report Runtime: web + CLI + MCP

The runtime extends charts-design. Original chart builders, KPI bodies, table and explanation components remain the rendering foundation; the runtime adds persistence, editing, transport and a shared SVG-only action layer.

## Run locally

Python 3.10+ runs the CLI and local API. Node 22 is the tested UI build target.

```sh
npm --prefix runtime-ui install
npm --prefix runtime-ui run build
python3 -m dashboard_runtime --root ./boards init demo --demo
python3 -m dashboard_runtime --root ./boards serve --port 8765
```

Open the token-bearing URL printed by `serve`. It binds only to 127.0.0.1. The token is carried in the URL fragment, removed from the address bar and retained in session storage. Do not share it. This is not an Internet-facing multi-tenant service.

Plain `init` creates an empty dashboard; `--demo` explicitly inserts synthetic data. The test fixtures also use explicitly labelled demonstration data. Keep `./boards` outside source control: it contains business snapshots, SQL and parameters.

## Personal analysis reports

A report is one Markdown document, presented as a single-column academic reading layout. Write headings, paragraphs, bold text, lists and blockquotes as usual; put a fenced `chart` block where a shared chart should appear. Charts render inline between the surrounding prose, with numbered captions and optional source notes below them. Dashboard mode remains an independent responsive grid using the same components, data, filters, metric definitions and source inspectors. Switching views does not execute SQL or generate new claims.

```sh
# An empty Markdown report; no business data is inserted.
python3 -m dashboard_runtime --root ./boards init analysis --mode report --title "我的分析报告"

# An explicitly synthetic Markdown example, with prose and two inline charts.
python3 -m dashboard_runtime --root ./boards init report-demo --mode report --demo
python3 -m dashboard_runtime --root ./boards serve --port 8765
```

Use **分析报告 / 仪表盘** to switch the saved presentation. Edit report Markdown directly and preview the document. The source is the report's reading order: move a paragraph or a `chart` fence in the text to move it in the report. Insert an existing chart's component ID in a fence; adding a dashboard component does not insert it into the Markdown automatically. Removing a fence hides that chart from the report and preserves its component in the dashboard.

For example, this is the entire source of a small report. The `trend` and `regions` components must already exist, or be created in the same atomic update:

````markdown
# 我的经营观察

*——基于合成快照的描述性分析*

**摘要：** 这里只使用明确标记的合成数据，描述收入变化，不作因果推断。

**关键词：** 收入变化；区域结构；合成数据

## 收入走势

如[图](#fig-trend)所示，9 月收入**高于 7 月**，但低于 8 月。先观察变化，再验证原因。

```chart
{"componentId":"trend","caption":"2026 年 7—9 月收入变化","source":"数据来源：内置合成快照；金额单位为万元。"}
```

三个观测点不足以判断变化是否持续，需要结合更长时期的数据。

## 区域拆解

两地区的累计收入规模存在差异（见[图](#fig-regions)）。还需复核 East 的月度变化，并对照更细时间粒度的数据。

```chart
{"componentId":"regions","caption":"East 与 South 的季度累计收入","source":"数据来源：同一内置合成快照，统计期间为 2026 年 7—9 月。"}
```

图表之后可以继续写分析、限制和下一步。
````

Conclusions are authored and do not recalculate when filters change. Review the Markdown after changing data or filters. Raw HTML and ordinary code are not executable report instructions. The demo labels its synthetic snapshot and the limits of its observations; it does not imply an AI-generated diagnosis or an enterprise reporting workflow.

### Academic reading conventions

An authored level-one heading is the centered title; an emphasized paragraph immediately after it can provide a centered subtitle. Write abstract and keywords as ordinary paragraphs beginning with `**摘要：**` and `**关键词：**`. Level-two section headings receive presentation-only section numbers, so omit manual numbers in their Markdown. These conventions style supplied content; they do not invent authors, dates, abstracts, keywords or other metadata for existing documents.

Figures receive numbers in Markdown source order. Optional `caption` and `source` strings render as plain text under their chart; do not include a manual figure number in the caption. Use a standard Markdown link such as `[图](#fig-trend)` in prose to display the corresponding figure number and jump to the figure for component `trend`. Repeating a chart fence creates another numbered figure; links using `#fig-trend` still refer to that component's first occurrence. No extra `figureId` field is needed or accepted. Reordering the chart fences updates the rendered numbering without rewriting the canonical Markdown.

### Canonical source and validation (backward-compatible schema v2)

`manifest.viewMode` is optional: `"dashboard"` (the default for older documents) or `"report"`. The canonical report source is `manifest.report.markdown`:

```json
{
  "viewMode": "report",
  "report": {
    "markdown": "# 我的报告\n\n先写分析。\n\n```chart\n{\"componentId\":\"trend\"}\n```\n\n再写解读。"
  }
}
```

- `markdown` is a string of 0–200,000 characters. An empty string is a valid, intentionally empty report.
- A top-level fence whose exact info string is `chart` contains a JSON object with required `componentId` and optional `caption` and `source`. The existing 1–80 character identifier rule applies to `componentId`. It must resolve to a non-text component: chart, KPI, table or original catalog component. The same component may appear more than once. Existing `{"componentId":"trend"}` fences remain valid.
- `caption` must be a string of 0–500 characters; `source` must be a string of 0–1,000 characters. Both fields are plain text, may be omitted or empty, and cannot be `null`, objects, arrays, booleans or numbers. They do not execute code or fetch a source; author and verify the actual description and provenance yourself.
- Fences use backticks or tildes, at least three characters, optionally indented by up to three spaces. A closing fence uses the same character and is at least as long as its opener. Ordinary fenced code is inert, including examples of chart syntax inside a longer non-chart code fence.
- Invalid or unclosed chart JSON, duplicate JSON keys, unknown fields, missing components and references to text components are rejected when saving, importing or patching. A frontend may keep unfinished source locally while the author is typing; that does not bypass persistence validation.
- `set_report_markdown` takes the complete string as `value`, without changing mode, data or grid layouts. References are checked after the entire atomic batch, so component creation may follow the source operation.
- `remove_component` rejects deletion if canonical Markdown still references it, with `REPORT_COMPONENT_REFERENCED`. First remove its chart fence using `set_report_markdown`; both operations can be in the same batch, in that order.
- `set_view_mode` with `value: "report"` initializes missing Markdown from the title, existing legacy report or desktop reading order (top-to-bottom, then left-to-right). Existing canonical source survives view switching. Imported old reports can be displayed through the same non-mutating migration utility.

### Write source from CLI or MCP

Save your document as `analysis.md`, read the latest revision with `get`, and wrap the source in a JSON operation:

```sh
python3 -m dashboard_runtime --root ./boards get report-demo
python3 - <<'PYCODE'
import json
from pathlib import Path
operations = [
    {"op": "set_report_markdown", "value": Path("analysis.md").read_text()},
    {"op": "set_view_mode", "value": "report"},
]
Path("report-patch.json").write_text(json.dumps(operations, ensure_ascii=False))
PYCODE
# Replace 1 with the revision returned by get.
python3 -m dashboard_runtime --root ./boards patch report-demo --expected 1 --file report-patch.json
```

Use the same `set_report_markdown` operation in `dashboard_patch` over HTTP or MCP, with `dashboardId`, the latest `expectedRevision`, and `operations`. Revision checks, validation, history and restore are shared across transports. JSON export/import preserves the exact source. Full-document HTML export opens a read-only Markdown report snapshot using the shared renderer. Single-component export resets presentation to a standalone dashboard card and omits report metadata and unrelated components.

### Legacy report compatibility

Old `report.subtitle` plus `report.blocks` documents and the `set_report` operation remain supported. Without canonical Markdown, the subtitle is bounded at 1,000 characters and blocks at 100 unique block IDs and component references. Existing text components become escaped literal text under Markdown headings; non-text components become chart fences. Migration preserves the old components, grid and metadata and does not execute their contents.

When `markdown` is present, it alone determines the report. Retained subtitle/blocks are historical metadata and cannot override the source or prevent deletion of an unreferenced component. `set_report_markdown` retains those fields. The legacy `set_report` operation still explicitly replaces the whole report object; supplying only legacy fields returns to legacy representation. Only unmigrated block reports retain their old auto-append/cleanup behavior. New authoring should use Markdown source and `set_report_markdown`.

## MCP

```sh
python3 -m pip install 'mcp>=1.28,<2'
python3 /absolute/path/charts-design/bin/dashboard_runtime.py --root /absolute/path/boards mcp
```

Web, CLI and MCP must use the same absolute `--root`. `mcp.json` uses `${PLUGIN_ROOT}`; replace it with actual paths in clients that do not expand the convention. Logs go to stderr; stdout is reserved for MCP protocol messages.

Tools: `dashboard_create`, `dashboard_list`, `dashboard_get`, `dashboard_patch`, `dashboard_validate`, `dashboard_preview`, `dashboard_history`, `dashboard_restore`, `chart_catalog`, `dataset_import`, `query_execute`, `query_inspect`, `semantic_inspect`, `legacy_render`, `generation_examples`, `chart_declarations`.

`dashboard_preview` links to the versioned resource `ui://charts-design/dashboard-v0.4.0.html`, MIME `text/html;profile=mcp-app`. It uses `@modelcontextprotocol/ext-apps` and the same built UI as the independent web editor. A normal MCP connection does not imply support for embedded MCP Apps. Actual Codex/ChatGPT host installation remains a separate acceptance step. Remote Streamable HTTP MCP, OAuth and hosted publishing are not included.

## Canonical state and editing

`dashboard_runtime.service.Service` is the mutation service for all transports. SQLite stores the document and last 100 revisions. Every edit supplies `expectedRevision`; stale writes fail with `REVISION_CONFLICT`. Batched operations validate and commit atomically.

Schema v2 separates components, datasets/field metadata, metric definitions, source/query provenance, per-breakpoint layout, and bounded snapshot rows. It contains no executable application code. View changes never execute SQL.

```sh
python3 -m dashboard_runtime contract
python3 -m dashboard_runtime --root ./boards get demo
python3 -m dashboard_runtime --root ./boards patch demo --expected 1 --file changes.json
python3 -m dashboard_runtime --root ./boards history demo
python3 -m dashboard_runtime --root ./boards restore demo --expected 2 --revision 1
```

Example changes.json:

```json
[
  {"op":"set_title","value":"Revenue review"},
  {"op":"set_chart","id":"trend","chartType":"bar"}
]
```

Restore creates a new revision; it does not rewrite history. Browser undo/redo uses the same service. New external revisions clear the browser undo stack instead of silently undoing another writer's work. Web clients check for external revisions every five seconds.

GridStack uses independent desktop/tablet/mobile 12/8/4-column layouts. This is flexible responsive positioning and resizing, not arbitrary overlapping pixel placement. Read/edit modes, component add/delete/duplicate, titles/descriptions, undo/redo, global filters, import/export and SQL/semantic inspectors remain available.

All main-card action buttons are real Lucide SVGs with accessible names, hover help and keyboard focus. Titles/descriptions stay upper-left, actions upper-right; narrow cards expose secondary actions through More. Menus and forms keep normal readable text. Table order, visibility, pagination and sorting persist. See `icon-header-and-bindings.md` for bindings and the component UI contract.

## Original components and chart switching

The runtime directly bundles all 40 original chart builders, 9 KPI rendering branches, the detail table and business explanation dialog. Bodies run inside ShadowRoots, not nested iframe cards. Source extraction preserves the original geometry, labels, microcharts and original actions while replacing the header controls with consistent SVG chrome.

```sh
python3 -m dashboard_runtime --root ./boards import-workspace imported --path ./old-workspace
```

Workspace import preserves original chart/KPI/table JSON, including c01/c02 designs and KPI auxiliary fields. It does not turn charts into generic bars or KPI cards into text. Original filter metadata is retained; working cross-component filtering requires explicit dataset/metric bindings. Supported bindings include 14 one-dimensional chart shapes, mc01-mc06 and detail tables. Complex shapes and mc07-mc09 require additional reviewed transforms; incomplete bindings fail rather than inventing data. Their static original configurations remain usable.

The separate native field-mapping engine supports bar, line, area, pie, scatter, heatmap, funnel and waterfall. It validates field roles and compatible measures; mixed-unit plots are rejected unless explicitly provided by an original dual-axis component. Waterfall needs an additive delta metric, heatmap a second category, scatter numeric X, and pie/funnel additive nonnegative values.

Metrics support sum, average, min, max, row count and ratio-of-sums. Filters recalculate SUM(numerator)/SUM(denominator), never the average of percentages. Nulls remain missing; a zero denominator yields no value. Percent formatting requires fractional values. Existing aggregate snapshots cannot produce missing finer-grained dimensions or statistically valid averages without the underlying data.

## Import data

Use the web import dialog or the common CLI tool entrance:

```sh
python3 -m dashboard_runtime --root ./boards call dataset_import --json-file import.json
```

```json
{
  "dashboardId":"demo","expectedRevision":1,"datasetId":"sales2",
  "rows":[{"region":"East","revenue":128},{"region":"South","revenue":96}]
}
```

Use `csvText` instead of `rows` for CSV. Inferred numeric metrics are unreviewed default sums; confirm definitions, units and grain before use. Leading-zero strings remain strings. A complete exported v2 artifact can be imported as a new dashboard using `import NEW_ID --file artifact.json`.

## SQL and semantic provenance

SQL execution currently supports SQLite only. Displaying SQL from another engine does not make that engine a live connector. Operators configure allowed source aliases, not MCP callers:

```json
{"analytics":{"engine":"sqlite","path":"/absolute/path/analytics.sqlite3"}}
```

```sh
python3 -m dashboard_runtime --root ./boards --sources ./sources.json serve
python3 -m dashboard_runtime --root ./boards --sources ./sources.json call query_execute --json-file query.json
```

```json
{
  "dashboardId":"demo","expectedRevision":1,"datasetId":"sql-result",
  "connection":"analytics",
  "sql":"SELECT region, SUM(revenue) AS revenue FROM sales WHERE month >= :start GROUP BY region",
  "parameters":{"start":"2026-01"}
}
```

Read-only SQLite connections use query_only, an authorizer and a function allowlist. Extension loading, ATTACH, PRAGMA, DDL and DML are blocked. Time and row limits fail explicitly instead of silently truncating data. Successful query provenance records exact SQL, parameters, source alias, engine, duration, timestamp and row count in the same transaction as the snapshot. Supplied sources are marked supplied, never runtime-executed.

The semantic inspector uses stored business definitions and aggregation rules, not generated explanations inferred from labels. `reviewed` is descriptive metadata, not an enterprise approval system. Local query restrictions are not a hardened multi-tenant sandbox. Exported parameters and snapshots remain sensitive.

## Export and verification

```sh
python3 -m dashboard_runtime --root ./boards validate demo
python3 -m dashboard_runtime --root ./boards export demo --output ./dist/demo.html
python3 -m dashboard_runtime --root ./boards export demo --format json --output ./dist/demo.json
python3 -m pytest tests/runtime -q
node --test tests/runtime/*.test.mjs
```

HTML is a read-only snapshot with bundled original components, ECharts, icons and UI; it needs no CDN after building. It is not a live shared dashboard. JSON preserves editable canonical state. The historical standalone Python generators remain separate compatibility entrances and retain their own historical behavior.

MCP integration uses a real stdio SDK client. Browser acceptance uses actual Chromium, ECharts and GridStack. The full component test renders all 40 charts and 9 KPI types, checks icon-only headers, original chart/table actions and CSV downloads, and writes screenshots plus `component-review/coverage.json`. This is rendering and behavioral coverage, not a claim of pixel-exact equivalence with historical screenshots. Optional unavailable runtimes are explicitly skipped outside CI, never counted as passed.

## Remaining boundaries

Complex original-data transforms, warehouse execution, remote MCP, multi-user permissions/RLS, enterprise approval, scheduled refresh, hosted publishing, and real Codex host installation are not complete. UI completion does not imply these platform capabilities exist. Keep the PR Draft until visual review, code review and target-host acceptance; do not merge automatically.

Local server launch links now use an explicit `#token=...` fragment. Ordinary Markdown section and figure anchors never replace an existing session token. Legacy bare-token links are accepted for a fresh browser session; use the newly printed launch link to replace a token after a server restart.


## MCP 生成案例与声明发现

两条 Skills、案例和空白生成流程见 [generation-tracks.md](generation-tracks.md)。新增只读工具 `generation_examples`（可选 caseId）与 `chart_declarations`。对应 JSON 资源：`charts://examples`、`charts://examples/executive-dashboard`、`charts://examples/academic-report`、`charts://declarations`。案例返回完整原子操作和 Markdown；读取不会创建文档或写入示例数据。
