# Shared MCP delivery

Use this flow for dashboards and Markdown reports. Read the connected tools' schemas and `charts://contract` before forming calls.

## Project and data

Pass `projectRoot` on every project call, including discovery, diagnostics and chunk reads. Locally it is the absolute durable asset directory; on the self-hosted server it is the configured project name. One MCP registration serves multiple projects.

Read `dashboard_get` before editing. Keep the returned revision, stable component IDs, data references and comments. For affected components, retain the metric scope, aggregation, baseline, units, tooltip fields, sorting, drilldown and filter consumers.

Use `dataset_import` with exactly one of `rows` or `csvText` for small data. Use `dataset_attach` for configured SQLite sources; take connection aliases from operator configuration. Inspect imported fields and inferred metrics before binding them. Reuse immutable references returned by the tools.

For KPI comparisons, aggregate each period at the same scope and grain before calculating the change. Distinguish percentage changes from percentage-point differences. Tooltip totals, shares and detail tables must use the same denominator, including the declared treatment of hidden series.

## Edit, check and display

1. For a new artifact call `dashboard_create`; for an existing one read `dashboard_get`.
2. Call `dashboard_edit_begin` with the latest `expectedRevision` and retain its `batch_id`.
3. Apply related operations with `dashboard_patch`, using each successful receipt's `revision` as the next `expectedRevision`. Writes default to compact summaries. Request `responseMode=full` or use `dashboard_get` when the updated declarations are needed. Replacement operations must include all fields being retained.
4. Use `dashboard_view` for affected computed results. Match its revision and data version to the document being inspected. Verify source totals, units, ratios, baselines, filter scope and figure references.
5. Call `dashboard_edit_finish` with the batch ID and current revision. This runs Doctor checks and creates the completed checkpoint.
6. After success, call `dashboard_preview` once with the same project and dashboard. Deliver the saved result and relevant source details.

`dashboard_get` reads the editable draft; project previews read the latest completed checkpoint. On `DOCTOR_FAILED`, read the issues, correct the draft and finish again. On `REVISION_CONFLICT`, read the current document and reconcile the requested changes before retrying.

Use `dashboard_data_inspect` for dataset counts and version references. Refreshing data creates a new dataset version; authored prose must be recalculated for that version or remain explicitly tied to its earlier snapshot.

## Comments and history

Read `dashboard_annotations` for comments and their original targets, then inspect the current document. Use stable component IDs to locate the affected content. When a visual anchor is ambiguous, confirm its location before editing.

Annotations save independently of design revisions. Preserve their original context across restoration. To change comments when requested, use `set_annotations` with the exact previously read `expectedAnnotations`.

Read `dashboard_history` or `dashboard_version_status` for saved versions. `dashboard_version_get` reads a historical version. A requested `dashboard_restore` creates a new draft; complete its checkpoint before opening the restored preview.

## Export and publication

| Requested result | Route |
| --- | --- |
| JSON configuration or HTML snapshot | `dashboard_export`, then `dashboard_export_read` |
| Full matching CSV rows | `dataset_export`, then `dashboard_export_read` with `format=csv` |
| Standalone static website ZIP | `dashboard_export_site`, then `dashboard_export_read` with `format=zip` |
| Formal publication of a saved version | Read `dashboard_version_status`, then `dashboard_version_publish` |
| Tencent cloud share | Publish the intended version, then `dashboard_share_publish` |
| Replace or revoke an existing cloud share | `dashboard_share_replace` or `dashboard_share_delete` using its returned share ID |

Run publication and sharing operations when requested. Cloud shares are independent copies with their own access key and expiration. Static website ZIPs contain the React application and used dataset shards. Remote file exports return managed download links.

Details: [static website export](../../../docs/operations/static-deployment.md), [self-hosted service and sharing](../../../docs/operations/self-hosted-server.md).

## Diagnose a failed delivery

Use `runtime_info` to locate the installed backend, UI build and project assets. `UI_UNAVAILABLE` requires building and packaging the UI resources using the repository's [local update procedure](../../../docs/operations/local-mcp-update.md).

Use request IDs with `runtime_diagnostics` to locate query, serialization, transport or rendering failures. Read the reported data and configuration, correct the cause and repeat the failed step. Keep credentials and raw business rows out of logs.

For a requested performance investigation, read [local data](local-data.md) and [transport diagnostics](../../../docs/operations/mcp-transport-diagnostics.md). Compare equivalent data and filters, and separate query duration from rendering duration.
