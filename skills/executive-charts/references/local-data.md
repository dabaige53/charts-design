# Local data for MCP dashboards

SQLite holds the full data in `data.sqlite3`. `dashboards.sqlite3` stores configurations and revision history with immutable references to data versions.

## Attach and inspect data

Follow [shared delivery](mcp-delivery.md) for project routing, revisions and edit batches.

1. Read the runtime's configured SQLite connection aliases. Each alias declares `engine: "sqlite"` and an existing file's `path` in the operator-owned `--sources` JSON.
2. Create or read the dashboard and begin an edit batch. Call `dataset_attach` with `dashboardId`, `expectedRevision`, `datasetId`, `connection` and `table`. Supply explicit field metadata for dates and booleans. The source table streams through a read-only connection into an immutable version.
3. Inspect fields and row counts with `dashboard_data_inspect`. Add reviewed metrics and components with `dashboard_patch`. Keep units, precision, ratio numerator/denominator and filter consumers explicit.
4. Inspect calculated values with `dashboard_view`, complete the batch and open `dashboard_preview`. The result's `structuredContent.document` includes `snapshot.datasetRefs` and `computed` component results. Tables return the current page and full matching row count.

## Filters and table pages

Use `dashboard_view` with temporary `filters`, `tableStates` and `granularities`. `tableStates` maps component IDs to `page`, `pageSize`, optional `sortCol`, `sortDir` and `keyword`. Reader changes preserve the saved design revision.

Large option lists use `dashboard_filter_options` with `filterId`, optional `search`, `offset` and `limit`. Load additional option pages when the required value is outside the current page.

Use `dataset_export` with `componentId` and active filters to stream all matching table rows to CSV. Pass displayed column keys, sort and search when exporting the current table view. Download the managed result with `dashboard_export_read` and `format=csv`.

## Data versions and limits

- Each dataset uses inline rows or an immutable local reference. Reuse returned references across configuration edits and compatible dataset aliases.
- Store display formatting in metric or column presentation. Bound tables derive rows from their dataset.
- Title, layout and filter-default changes reuse existing data versions. Restoration uses the selected configuration's references.
- Aggregates exceeding result bounds return an error. Use filtered aggregates for the visual or export all matching observations as CSV, according to the user's analytical scope.
- Statistical components accept up to 5,000 raw observations.

## Snapshots and migration

MCP defaults to local result mode. Explicit `dataMode: "snapshot"` supports bounded snapshots for small artifacts outside local mode. Oversized JSON/HTML snapshots return `LOCAL_DATA_REQUIRED`; use full CSV for the observations. Offline component snapshots retain the current computed page.

CLI `export <id> --format csv --dataset <datasetId> --output <path>` streams every matching row. Use `--component <tableId>` for a table's filter scope.

When migration is requested, `dashboard_migrate` takes `dashboardId` and `expectedRevision`. It creates a managed backup and converts retained configurations to data references, returning `migration.backupId`. `dashboard_migration_rollback` takes that backup ID and the current revision to restore the content as a new revision.

## Performance investigations

For a requested performance investigation, use an isolated store and read the original source database in read-only mode. Inspect source counts, logical data bytes, physical file sizes, query duration, response size and cache hits with `dashboard_data_inspect` and computed results. Compare independently calculated sums and ratios at the same scope.

The targeted benchmark is `tests/runtime/benchmark_local.py --rows 1000000 --output <report.json>`, run through the project Python entry point. It measures import, preview, filter, aggregate, page, sort, search, export, edit and restore costs.
