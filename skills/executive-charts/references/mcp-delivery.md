# Shared MCP delivery

Use this flow for dashboards and Markdown reports. Read the connected tools' schemas and `charts://contract` before forming calls.

## Project and data

Pass `projectRoot` on every project call, including discovery, diagnostics and chunk reads. Locally it is the absolute durable asset directory; on the self-hosted server it is the configured project name. One MCP registration serves multiple projects.

Read `dashboard_get` before editing. Keep the returned revision, stable component IDs, data references and comments. For affected components, retain the metric scope, aggregation, baseline, units, tooltip fields, sorting, drilldown and filter consumers.

Use `dataset_import` with exactly one of `rows` or `csvText` for small data. Use `dataset_attach` for configured SQLite sources; take connection aliases from operator configuration. Inspect imported fields and inferred metrics before binding them. Reuse immutable references returned by the tools.

For large local data, use the [remote upload client](../../../docs/operations/self-hosted-server.md#更新已有看板的数据): `bin/remote-project.py upload` transfers a data version for an existing dashboard; `bin/transfer-project.py` imports selected new pages. Both share preflight, bounded concurrency and verified resume. Keep the state file after interruption. Bind the verified output ref with `put_dataset_ref` and the current revision, preserving dataset metadata and metric definitions. For a large component configuration, use [complete configuration download](../../../docs/operations/mcp-transport-diagnostics.md#完整配置下载) before editing.

For KPI comparisons, aggregate each period at the same scope and grain before calculating the change. Distinguish percentage changes from percentage-point differences. Tooltip totals, shares and detail tables must use the same denominator, including the declared treatment of hidden series.

## Edit, check and display

1. For a new artifact submit `createTitle` and initial `operations` together. Use `dashboard_create` when importing a complete reviewed document or when an empty container is needed before data import. For an existing artifact read `dashboard_get`.
2. For edits, call `dashboard_submit` with the latest `expectedRevision` and related `operations`. Replacement operations must include all fields being retained. Omit operations when saving an already reviewed draft, e.g. after a data import. The service checks all components and saves the checked revision. It never publishes.
3. Use `dashboard_view` to verify totals, units, ratios, baselines and filter scope against the source. Automated checks cannot establish that a business definition is correct.
4. After success, call `dashboard_preview` once with the same project and dashboard. Deliver the saved result and relevant source details.

For an affected filter or chart interaction, check the [interaction defaults](design_standards.md#操作与更新) in the actual delivery view. Apply a filter and close the menu, or click a chart item and move the pointer away. Confirm the visible active state survives the update, the intended components update, and clearing the selection restores both the styling and the prior filter scope. Repeat in the standalone export when it is part of the delivery.

`dashboard_get` reads the editable draft; project previews read the latest completed checkpoint. On `DOCTOR_FAILED`, read the issues and submit corrections to the retained draft. On `REVISION_CONFLICT` or an uncertain write, read the current state before retrying.

Use data write receipts for row counts and version references. Request `includeEvidence: true` in a component `dashboard_view` to compare results with their sources and metric definitions in the same revision. Refreshing data creates a new dataset version; authored prose must be recalculated for that version or remain explicitly tied to its earlier snapshot.

## Comments and history

Read `dashboard_annotations` for comments and their original targets, then inspect the current document. Use stable component IDs to locate the affected content. When a visual anchor is ambiguous, confirm its location before editing.

Annotations save independently of design revisions. Preserve their original context across restoration. To change comments when requested, use `dashboard_annotations_update` with the exact previously read `expectedAnnotations` and the replacement `annotations`.

Use the editor's **版本与分享 → 版本** tab to view or restore a saved version. A restored version creates a new draft. Save it before opening the preview.

## Export and publication

| Requested result | Route |
| --- | --- |
| JSON configuration or HTML snapshot | `dashboard_export`; deliver the returned local file or remote download link |
| Full matching CSV rows | `dataset_export`; deliver the returned CSV |
| Standalone static website ZIP | `dashboard_export_site`; deliver the returned ZIP |
| Set a saved version as the formal publication | Call `dashboard_publish` with the saved `revision`. |
| Create a visitor link | Call `dashboard_share_publish` with a saved `revision` and a new UUID v4 `requestId`. Omit `expiration` for a seven-day link. |
| Manage existing shares | Open **版本与分享 → 分享** in the editor. |

Save a draft with `dashboard_submit`. In the editor, select a saved version and choose **设为正式发布版** or **分享此版本** for the requested action. Each share has its own key and expiration. Retry a share with identical arguments and the original `requestId` after an uncertain receipt. `dashboard_share_status` lists shares without exposing visitor keys. Static website ZIPs contain the React application and used dataset shards. Remote file exports return managed download links.

Details: [static website export](../../../docs/operations/static-deployment.md), [self-hosted service and sharing](../../../docs/operations/self-hosted-server.md).

## Diagnose a failed delivery

For `UI_UNAVAILABLE`, see the [local update procedure](../../../docs/operations/local-mcp-update.md). For service failures, give the operator the request ID and follow the project's [transport diagnostics](../../../docs/operations/mcp-transport-diagnostics.md). Correct the reported cause and repeat the failed step. Keep credentials and raw business rows out of logs.

If a tool returns `transport.resourceUri`, read that MCP resource for the complete JSON. Chunk assembly is a client protocol, not an authoring step. For hosts with resource size limits use the complete configuration download client.

For a requested performance investigation, read [local data](local-data.md) and [transport diagnostics](../../../docs/operations/mcp-transport-diagnostics.md). Compare equivalent data and filters, and separate query duration from rendering duration.
