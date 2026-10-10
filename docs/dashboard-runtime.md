# Dashboard Runtime: web + CLI + MCP

This is an additive runtime for charts-design, not a replacement for the existing executive-charts generator. The original CLI, registered chart builders and generation tests remain unchanged.

## Run locally

Python 3.10+ runs the CLI and local API without third-party packages. Node 22 is the tested UI build target.

```sh
npm --prefix runtime-ui install
npm --prefix runtime-ui run build
python3 -m dashboard_runtime --root ./boards init demo --demo
python3 -m dashboard_runtime --root ./boards serve --port 8765
```

Open the token-bearing URL printed by `serve`. The token is carried in the URL fragment, removed from the address bar and retained in session storage. Do not share the token. The server binds only to 127.0.0.1; this is not an Internet-facing multi-tenant service.

`--demo` is the only path that inserts synthetic data. Plain `init` creates an empty dashboard. `./boards` contains data snapshots, SQL and parameters: keep it outside source control and protect it as business data.

## MCP (official SDK, stdio)

```sh
python3 -m pip install 'mcp>=1.28,<2'
python3 /absolute/path/charts-design/bin/dashboard_runtime.py --root /absolute/path/boards mcp
```

Configure any compatible MCP client with the same command and arguments. `mcp.json` uses the portable `${PLUGIN_ROOT}` convention; replace it with absolute paths for clients that do not expand this convention. MCP logging goes to stderr; stdout is reserved for protocol messages.

The server exposes `dashboard_create`, `dashboard_list`, `dashboard_get`, `dashboard_patch`, `dashboard_validate`, `dashboard_preview`, `dashboard_history`, `dashboard_restore`, `chart_catalog`, `dataset_import`, `query_execute`, `query_inspect`, `semantic_inspect`, and `legacy_render`.

`dashboard_preview` links to `ui://charts-design/dashboard-v1.html` with MIME type `text/html;profile=mcp-app`. Its UI uses the official `@modelcontextprotocol/ext-apps` client and the **same bundle** as the web editor. A regular MCP connection does not imply MCP Apps support: a host without UI support can still call tools and use the separate web editor. No claim is made that a particular Codex/ChatGPT release has been tested in this repository.

MCP stdio and the browser HTTP API are implemented. Remote Streamable HTTP MCP, OAuth and Internet hosting are **not** included in this version.

## One state, three entrances

`dashboard_runtime.service.Service` is the only mutation service. CLI, HTTP and MCP delegate to it. SQLite stores the canonical document and the last 100 revisions, using transactional optimistic concurrency. Every edit supplies `expectedRevision`; stale edits fail with `REVISION_CONFLICT` instead of overwriting another writer.

Schema v2 separates:

- `manifest.components`: card kinds, chart types, field and metric bindings.
- `manifest.datasets`: field metadata and source references.
- `manifest.metrics`: business definitions, aggregation, unit, formatting and review status.
- `manifest.sources`: file/import provenance or captured SQL execution records.
- `manifest.layout`: independent desktop/tablet/mobile integer-grid placements.
- `snapshot.datasets`: bounded arrays of reviewed row objects; no executable code.

`python3 -m dashboard_runtime contract` prints all tools and typed operations. Unknown operations are rejected. Batched operations commit atomically after reference, type, unit, filter, layout and size validation.

```sh
python3 -m dashboard_runtime --root ./boards get demo
python3 -m dashboard_runtime --root ./boards patch demo --expected 1 --file changes.json
python3 -m dashboard_runtime --root ./boards history demo
python3 -m dashboard_runtime --root ./boards restore demo --expected 2 --revision 1
```

Example `changes.json`:

```json
[
  {"op":"set_title","value":"Revenue review"},
  {"op":"set_chart","id":"trend","chartType":"bar"}
]
```

Restore creates a new revision. It does not rewrite history. Browser undo/redo uses this same operation. A new external revision clears the browser's local undo stack to avoid reverting another writer accidentally.

## Web editing

The editor provides read/edit modes, card creation/deletion/duplication, title edits, responsive GridStack drag/resize, independent breakpoint layouts, chart selection, field/series/measure binding, table views with sorting/pagination/CSV export, global filters, undo/redo, theme switching, JSON/HTML export, and SQL/semantic inspectors.

Layouts use 12/8/4 columns. This is a high-freedom responsive grid, **not** an arbitrary pixel-overlap canvas. Layout changes never execute SQL. SQL execution requires an explicit separate action. Live web changes and MCP/CLI changes share the same persisted document; web clients check for external revisions every five seconds and reject stale writes.

The SQL inspector shows recorded/supplied source data. The semantic inspector shows stored metric definitions, not an AI explanation guessed from chart labels. Imported definitions are marked unverified. `reviewed` is descriptive metadata, **not** an enterprise approval/authorization system.

## Chart switching and aggregation

The native engine supports bar, line, area, pie, scatter, heatmap, funnel and waterfall. Compatibility is evaluated from field types, grouping and metric semantics. Unavailable choices explain the missing requirement. Negative pie/funnel values are rejected. Heatmaps need a second categorical field. Scatter needs numeric X. Waterfall needs an additive `semantic: "delta"` metric. Mixed-unit axes are rejected; use separate native charts or an explicitly configured legacy dual-axis chart.

Metrics support sum, average, min, max, row count, and ratio-of-sums. Ratio definitions contain numerator and denominator field references. Filters recompute `sum(numerator)/sum(denominator)` instead of averaging precomputed percentages. Nulls remain missing; a zero denominator returns no value. Percent formatting requires fractional values and `scale: "fraction"`.

These are operations on a **bounded snapshot**, not arbitrary re-querying of missing dimensions. A dimension absent from the snapshot cannot become a working filter. Previously aggregated averages cannot be reconstructed into correct finer-grained metrics without additional data.

## Import JSON or CSV

Use the web Import dialog, or the common CLI tool entrance:

```sh
python3 -m dashboard_runtime --root ./boards call dataset_import --json-file import.json
```

```json
{
  "dashboardId":"demo",
  "expectedRevision":1,
  "datasetId":"sales2",
  "rows":[{"region":"East","revenue":128},{"region":"South","revenue":96}]
}
```

CSV is accepted as `csvText` instead of `rows`. Numeric columns get explicitly **unreviewed** default sum metrics; review aggregation, units and definitions before business use. Postal-code-like strings with leading zeros are preserved. A complete exported v2 JSON artifact can be imported as a new dashboard with `import NEW_ID --file artifact.json`.

## SQL execution

This version executes **SQLite only**. It can display SQL provenance supplied by other engines, but that does not make them live connectors. DuckDB/PostgreSQL/warehouse execution needs a subsequent connector implementation.

The operator, not the MCP caller, configures local source aliases:

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

The executor uses a read-only SQLite connection, `query_only`, an authorizer and a function allowlist; extension loading, ATTACH, PRAGMA, DDL and DML are blocked. It enforces a time limit and a 10,000-row cap without silent truncation. Each successful query stores exact SQL, parameters, engine, source alias, timestamp, duration and row count. The same transaction installs its dataset. Calls supplying source metadata are marked `supplied`, never `runtime-executed`.

This is a local read-only guardrail, not a hardened query sandbox for hostile tenants. Sensitive SQL parameters and snapshots remain sensitive after saving/exporting.

## Existing 40-chart catalog

The existing 40 registered charts and old Python generator are not rewritten. The adapter imports their actual builder registry and template, requires explicit business data/presentation, and isolates output in a sandboxed iframe. It never falls back to sample data. Advanced legacy charts are not falsely advertised as compatible with every native field mapping.

```sh
python3 -m dashboard_runtime --root ./boards import-workspace imported --path ./old-workspace
```

Simple c01/c02 charts migrate to native datasets/bindings. Advanced charts keep their original config in legacy cards. Legacy KPIs without a trustworthy numeric definition are preserved as text instead of fabricating a metric. The migration report calls out filters that need explicit rebinding. Legacy templates retain their original CDN dependencies; their preview requires network access. Native bundles and exports do not require a CDN after build.

## Export and validation

```sh
python3 -m dashboard_runtime --root ./boards validate demo
python3 -m dashboard_runtime --root ./boards export demo --output ./dist/demo.html
python3 -m dashboard_runtime --root ./boards export demo --format json --output ./dist/demo.json
```

HTML is a read-only snapshot with bundled native ECharts/UI code. It is not a live shared dashboard. JSON preserves the editable canonical document. Exported legacy frames retain the legacy network requirements above.

```sh
python3 -m pytest tests/runtime -q
node --test tests/runtime/engine.test.mjs
```

Core tests cover atomicity, concurrent conflicts, restores, types, layout bounds, chart compatibility, ratios, SQL restrictions, provenance, HTTP authentication and CLI round-trips. MCP integration uses an actual stdio SDK client. Browser acceptance uses actual Chromium, ECharts and GridStack; build assets and install `playwright`/Chromium first. Tests explicitly skip unavailable optional runtimes instead of claiming coverage.

## Current boundary

The implementation is a local-first, reviewable first release. It does not include multi-user authentication, row-level permissions, enterprise certification, scheduling, remote publishing, live warehouse connections, or a tested Codex host installation. Native and legacy chart behavior have distinct compatibility limits. The PR must pass the supplied CI/browser checks before being treated as release-ready.
