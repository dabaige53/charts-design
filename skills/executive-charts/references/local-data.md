# Pure local data for MCP dashboards

The existing MCP process queries SQLite in the same process. No HTTP listener, network data engine, cloud connection or extra daemon is required. Full data lives in `data.sqlite3`; `dashboards.sqlite3` stores configurations and their revision history, with immutable content hashes referring to data versions.

## Build and preview

1. Configure a local SQLite alias in the runtime's operator-owned `--sources` JSON. Each alias declares `engine: "sqlite"` and the existing file's `path`. Tool arguments cannot add arbitrary filesystem access.
2. Create the dashboard, then call `dataset_attach` with `dashboardId`, `expectedRevision`, `datasetId`, `connection` and `table`. Supply explicit field metadata for dates and booleans. The entire source table is read with a read-only connection and streamed into one immutable version; it is not passed through tool arguments.
3. Add reviewed metrics and components with `dashboard_patch`. Original charts and KPIs use their existing codes and bindings; tables use the same dataset. Keep units, precision, ratio numerator/denominator and filter consumers explicit.
4. Call `dashboard_preview`. The result's `structuredContent.document` has `snapshot.datasetRefs`, an empty `snapshot.datasets`, and `computed` component results. Table results include the current page and the full matching row count. The text block is a summary, not a second artifact.
5. Use `dashboard_view` for reader-only `filters`, `tableStates` and `granularities`. `tableStates` maps component IDs to `page`, `pageSize`, optional `sortCol`, `sortDir` and `keyword`. Reader changes do not create a revision. Existing explicit filter scopes and ratio recomputation are preserved.
6. Use `dataset_export` with `componentId` and the active filters to stream all matching table rows to a managed local CSV. Pass displayed column keys, sort and search when exporting the current table view. The result returns the local file path, total rows, bytes and duration; the full CSV is not sent back through MCP.

Large option lists use `dashboard_filter_options` with `filterId`, optional `search`, `offset` and `limit`. The total option universe remains available; the preview only loads the first page. Never interpret the current option page as the full domain.

## Data and revision invariants

- A dataset has inline rows or an immutable local reference, never both. Stored configuration revisions use references. Identical data and field contracts share a version across dataset aliases.
- Formatting belongs to metric/column presentation, not a second display dataset. Bound original tables do not persist a duplicate `config.rows`. Unbound original tables also store their observations in immutable local versions.
- A title, layout or filter-default edit reuses existing data versions. Undo restores configuration and its referenced versions; it does not duplicate observations.
- Metric aggregates share a bounded in-process cache keyed by version, metric definitions, filters, grouping and time grain. New data versions cannot reuse old results accidentally.
- A high-cardinality aggregate that exceeds result bounds raises an explicit error. No sampling, silent truncation or automatic narrowing of filters occurs. Full matching observations remain exportable as CSV.
- Statistical components retain their existing 5,000-observation limit and raw-observation validation; the local architecture does not reinterpret them as aggregates.

## Legacy compatibility and migration

Small inline artifacts remain supported by the CLI and service. MCP defaults to local result mode; explicit `dataMode: "snapshot"` provides the old bounded snapshot behavior when the artifact is small and not configured in local mode. It is not a way to embed a million-row dataset.

CLI `export <id> --format csv --dataset <datasetId> --output <path>` streams every matching row. Use `--component <tableId>` for a table's filter scope. Bounded JSON/HTML exports explicitly hydrate the legacy snapshot; oversized exports fail with `LOCAL_DATA_REQUIRED` and point to full CSV instead. A standalone component with computed local pages is labelled as a current-page snapshot and disables remote pagination/search/full CSV actions while offline.

`dashboard_migrate` takes `dashboardId` and `expectedRevision`. It writes a managed backup, then converts the active document and all retained configuration revisions to references without changing business revision numbers. It returns `migration.backupId`. `dashboard_migration_rollback` takes that backup ID and the current expected revision; it restores backed-up content as a new revision, preserving later history. The MCP response remains compact. Backups and old data versions are retained for recovery.

Do not migrate or edit a user's source board merely to test performance. Copy its document into an isolated store and read the original database in read-only mode.

## Verify and report

Use `dashboard_data_inspect` and `document.computed` for source rows, logical data bytes, physical data-file bytes, response bytes, query time and cache hits. Physical SQLite files may grow when indexes are created; do not describe that as data compression. Report source and export row counts and independently recomputed sums and ratios.

Run `tests/runtime/benchmark_local.py --rows 1000000 --output <report.json>` through the project Python entry point. The benchmark records import, preview, filter, aggregate, page, sort, search, export, edit and restore costs. `tests/runtime/local_browser_acceptance.py` uses stdio MCP and the official AppBridge with intercepted in-memory browser requests, without starting an HTTP listener. It checks million-row interaction and optional original-board copies. This fixture is separate from the actual Codex desktop host; identify which host was verified.
