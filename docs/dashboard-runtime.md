# Dashboard Runtime: web + CLI + MCP

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

## MCP

```sh
python3 -m pip install 'mcp>=1.28,<2'
python3 /absolute/path/charts-design/bin/dashboard_runtime.py --root /absolute/path/boards mcp
```

Web, CLI and MCP must use the same absolute `--root`. `mcp.json` uses `${PLUGIN_ROOT}`; replace it with actual paths in clients that do not expand the convention. Logs go to stderr; stdout is reserved for MCP protocol messages.

Tools: `dashboard_create`, `dashboard_list`, `dashboard_get`, `dashboard_patch`, `dashboard_validate`, `dashboard_preview`, `dashboard_history`, `dashboard_restore`, `chart_catalog`, `dataset_import`, `query_execute`, `query_inspect`, `semantic_inspect`, `legacy_render`.

`dashboard_preview` links to the versioned resource `ui://charts-design/dashboard-v0.3.0.html`, MIME `text/html;profile=mcp-app`. It uses `@modelcontextprotocol/ext-apps` and the same built UI as the independent web editor. A normal MCP connection does not imply support for embedded MCP Apps. Actual Codex/ChatGPT host installation remains a separate acceptance step. Remote Streamable HTTP MCP, OAuth and hosted publishing are not included.

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
