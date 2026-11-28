# Local data for MCP dashboards

In a local snapshot project, SQLite holds full data in `data.sqlite3`; `dashboards.sqlite3` stores configurations and revision history with immutable references. A live SQL dataset instead stores a query definition and obtains rows from its configured source at read time.

## Choose the data lifecycle

| Need | Route | Behavior |
| --- | --- | --- |
| Small supplied rows or CSV | `dataset_import` | Save an immutable snapshot; review inferred types and metrics. |
| An existing configured SQLite table | `dataset_attach` | Stream the table through a read-only connection into a snapshot. |
| A bounded SQL result from SQLite, PostgreSQL or DuckDB | `query_execute` with `mode: "snapshot"` | Execute the source query and retain its result for reproducible editing, saved versions and independent delivery. |
| Current upstream SQL values while viewing | `query_execute` with `mode: "live"` | Register the source query; subsequent reads execute it and do not store its rows as a data version. |

Source aliases come from operator configuration. Use typed parameters and explicit result-column names; supply live `fields` for dates and booleans when inference is insufficient. SQL results are bounded by the connected runtime. Aggregate or narrow an oversized result without changing the intended analytical scope; do not add an arbitrary `LIMIT` and present it as a complete dataset.

Live mode needs the source service online and does not make separate requests a shared database snapshot. Batch related components in one `dashboard_view` so that a request can reuse the same live dataset. For a reproducible report or independent share, use a deliberate snapshot. Static export/sharing of live definitions is rejected; preserve the live original when creating a requested fixed copy.

## Attach and inspect data

Follow [shared delivery](mcp-delivery.md) for project routing, revisions and edit batches.

1. Read the runtime's configured SQLite connection aliases. Each alias declares `engine: "sqlite"` and an existing file's `path` in the operator-owned `--sources` JSON.
2. Read the dashboard revision or create an empty dashboard for attachment. Call `dataset_attach` with `dashboardId`, `expectedRevision`, `datasetId`, `connection` and `table`. Supply explicit field metadata for dates and booleans. The source table streams through a read-only connection into an immutable version.
3. Check the row count and dataset version in the attachment receipt. Pass its dashboard revision to `dashboard_submit` with the reviewed metrics and components. Include units, precision, ratio numerator and denominator, and filter consumers.
4. Use `dashboard_view` with `includeEvidence: true` to check calculated values, metric definitions and sources together. Open `dashboard_preview` after a successful submission.

## Filters and table pages

Use `dashboard_view` with `responseMode: "patch"`, selected `componentIds`, temporary `filters`, `tableStates` and `granularities` when checking a subset. `tableStates` maps component IDs to `page`, `pageSize`, optional `sortCol`, `sortDir` and `keyword`. Reader changes preserve the saved design revision. Carry the revision and data version from the same displayed document to detect stale reads.

Use `component_data` with explicit `offset` and a small `limit` for underlying row previews. Check field types, nulls and units from the sample; use full-scope calculations for totals and ratios. Do not fetch the full dataset merely to show the first ten rows.

Large option lists use `dashboard_filter_options` with `filterId`, optional `search`, `offset` and `limit`. Load additional option pages when the required value is outside the current page.

Use `dataset_export` with `componentId` and active filters to stream all matching table rows to CSV. Pass displayed column keys, sort and search when exporting the current table view. Deliver the returned local file or remote download link.

## Data versions and limits

- Snapshot datasets use inline rows or immutable local references. Reuse returned references across configuration edits and compatible dataset aliases. Live definitions have a different lifecycle described above.
- Store display formatting in metric or column presentation. Bound tables derive rows from their dataset.
- Title, layout and filter-default changes reuse existing data versions. Restoration uses the selected configuration's references.
- Aggregates exceeding result bounds return an error. Use filtered aggregates for the visual or export all matching observations as CSV, according to the user's analytical scope.
- Statistical components accept up to 5,000 raw observations.

## Snapshots and migration

MCP defaults to local result mode. Explicit `dataMode: "snapshot"` supports bounded snapshots for small artifacts outside local mode. Oversized JSON/HTML snapshots return `LOCAL_DATA_REQUIRED`; use full CSV for the observations. Offline component snapshots retain the current computed page.

CLI `export <id> --format csv --dataset <datasetId> --output <path>` streams every matching row. Use `--component <tableId>` for a table's filter scope.

Use the operator CLI for storage migration and rollback. See [project storage](../../../docs/implementation/project-runtime.md).

## Performance investigations

For a requested performance investigation, use an isolated store and read the original source database in read-only mode. Compare independently calculated sums and ratios at the same scope. Use computed results for query duration, response size and cache hits.

The targeted benchmark is `tests/runtime/benchmark_local.py --rows 1000000 --output <report.json>`, run through the project Python entry point. It measures import, preview, filter, aggregate, page, sort, search, export, edit and restore costs.
