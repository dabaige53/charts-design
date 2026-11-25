# Shared MCP delivery

Use this flow for dashboards and Markdown reports. Read the connected tools' schemas and `charts://contract` before forming calls.

## Project and data

Pass `projectRoot` on every project call, including discovery, diagnostics and chunk reads. Locally it is the absolute durable asset directory; on the self-hosted server it is the configured project name. One MCP registration serves multiple projects.

Read `dashboard_get` before editing. Keep the returned revision, stable component IDs, data references and comments. For affected components, retain the metric scope, aggregation, baseline, units, tooltip fields, sorting, drilldown and filter consumers.

Use `dataset_import` with exactly one of `rows` or `csvText` for small data. Use `dataset_attach` for configured SQLite sources; take connection aliases from operator configuration. Inspect imported fields and inferred metrics before binding them. Reuse immutable references returned by the tools.

For large local data, use the [remote upload client](../../../docs/operations/self-hosted-server.md#更新已有看板的数据): `bin/remote-project.py upload` transfers a data version for an existing dashboard; `bin/transfer-project.py` imports selected new pages. Both share preflight, bounded concurrency and verified resume. Keep the state file after interruption. Bind the verified output ref with `put_dataset_ref` and the current revision, preserving dataset metadata and metric definitions. For a large component configuration, use [complete configuration download](../../../docs/operations/mcp-transport-diagnostics.md#完整配置下载) before editing.

For KPI comparisons, aggregate each period at the same scope and grain before calculating the change. Distinguish percentage changes from percentage-point differences. Tooltip totals, shares and detail tables must use the same denominator, including the declared treatment of hidden series.

## Cloud storage

Cloud projects default to `cos-v1`; local workspaces keep their local storage. For an existing dashboard inspect the document's `storageFormat` before importing. To partition existing COS data by branch or region, call `dataset_repartition` on the current connection with the dataset ID, version and partition field. Verify the returned reference before attaching it with `dashboard_submit`. For a project-wide storage inventory use the operator CLI.

If an existing project reports `postgres`, use the [COS migration procedure](../../../docs/operations/self-hosted-server.md#cos-业务内容迁移与删除任务). Read its inventory first. Within the user's migration authorization, upload and verify datasets and all draft/checkpoint/release documents, then switch references atomically. Retain drafts, stable IDs, annotations and history unless the user explicitly requests deletion. Never change the format flag by itself or silently continue through the legacy path.

Before handover, confirm `storageFormat: "cos-v1"`, data references and row counts, saved values and filter behavior. Distinguish application deployment, project migration, and editor verification in the result.

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

Use the version controls in the editor or the operator CLI for history, restoration and publication. A restored version creates a new draft; save it before opening the preview.

## Export and publication

| Requested result | Route |
| --- | --- |
| JSON configuration or HTML snapshot | `dashboard_export`; deliver the returned local file or remote download link |
| Full matching CSV rows | `dataset_export`; deliver the returned CSV |
| Standalone static website ZIP | `dashboard_export_site`; deliver the returned ZIP |
| Formal publication of a saved version | Read `dashboard_version_status`, then `dashboard_version_publish` |
| Tencent cloud share | Publish the intended version, then `dashboard_share_publish` |
| Replace or revoke an existing cloud share | `dashboard_share_replace` or `dashboard_share_delete` using its returned share ID |

Run publication and sharing operations when requested. Cloud shares are independent copies with their own access key and expiration. Static website ZIPs contain the React application and used dataset shards. Remote file exports return managed download links.

Details: [static website export](../../../docs/operations/static-deployment.md), [self-hosted service and sharing](../../../docs/operations/self-hosted-server.md).

## Diagnose a failed delivery

Use the operator CLI for `runtime_info` to locate the installed backend, UI build and project assets. `UI_UNAVAILABLE` requires building and packaging the UI resources using the repository's [local update procedure](../../../docs/operations/local-mcp-update.md).

Give the request ID to the operator for `runtime_diagnostics` in the CLI. Correct the reported cause and repeat the failed step. Keep credentials and raw business rows out of logs.

If a tool returns `transport.resourceUri`, read that MCP resource for the complete JSON. Chunk assembly is a client protocol, not an authoring step. For hosts with resource size limits use the complete configuration download client.

For a requested performance investigation, read [local data](local-data.md) and [transport diagnostics](../../../docs/operations/mcp-transport-diagnostics.md). Compare equivalent data and filters, and separate query duration from rendering duration.
