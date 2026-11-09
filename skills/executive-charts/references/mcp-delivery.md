# Shared MCP delivery workflow

Use this workflow for executive dashboards and analytical reports. Read current tool schemas before forming calls; capabilities depend on the connected runtime.

One MCP registration can serve multiple projects. Pass the absolute asset directory as `projectRoot` on every project call, including list, diagnostics and chunk reads; never assume a previous call selected a current project. The preview retains its own project for subsequent UI calls. Existing startup `--project-root` remains a default for compatibility. See package-root `docs/project-runtime.md` for the unified entry point and router requirements; do not create per-project MCP registrations.

## Preserve the accepted artifact

Inspect the current artifact before editing. Record the requested changes and retain stable dashboard/component IDs. For each affected component compare the before/after configuration: data and metric references, aggregation, comparison baselines, units, explanations, tooltip fields, filter consumers, sorting and drilldown.

For KPI comparisons, bind real prior-period data at the same scope and grain. Compute aggregate values or ratios before their changes; distinguish relative percent changes from percentage-point differences. Missing baselines remain missing. Keep the visible subtitle separate from the detailed metric definition: removing a subtitle must preserve the explanation.

For tooltip references, inspect content and interaction together: heading, aggregate total, denominator, units, series order/colors, value/share rows and pointer placement. When showing only top series, state whether totals include hidden series; verify that the tooltip and table use that same definition. Loading, empty results and errors are distinct states; a completed empty result clears the previous result.

## Compose before writing

Pick chart codes with `chart_recommend`, KPI shapes from `kpiGuide` (returned by `chart_declarations {}`), and one composition from `layout_templates`. Put `apply_layout_template` in the same batch as the components; it runs after the other operations. Vary compositions across the pages of a project.

## Save and display

1. Resolve the project's durable assets and the disposable runtime directory. Keep data references, design checkpoints and annotations in the project. Prefer existing immutable data versions over duplicate copies.
2. Begin an edit batch, apply draft changes with the latest revision, and finish it. Resolve Doctor errors before automatic display. If checks are explicitly waived, preserve the draft and report the skipped gate; do not label it validated.
3. Deliver preview as a URL, rather than opening an embedded MCP App panel. Prefer an existing browser URL; on the self-hosted server use `dashboard_share` to issue a view/edit URL with the access needed for the task. `dashboard_share_revoke` invalidates these links. Do not call an embedded preview tool solely to display the artifact. Use component-scoped `dashboard_view` patches for reader interactions, search/page large filter lists and paginate tables. Use file exports for full data.
4. Check the actual target page for the changed states. Report source checks, installed package, connected worker and host rendering separately. A preview response or test host is not actual host acceptance. A required restart remains pending until the connected worker is verified.

Annotations remain independent of design restoration. Preserve their original context when anchors become unavailable.

## Locate failures and performance work

Use request IDs with `runtime_diagnostics`. Distinguish backend query, serialization, chunk transport, client decoding and rendering. Retain the failing response and error position when available. Record version, phase, elapsed time and payload size; keep raw business rows and credentials out of logs.

For a performance claim, compare equivalent data, filters and outputs; record cold/warm cache conditions and repeat alternating baseline/candidate runs. Report median and range, query count, response size and failures. Separate menu-ready, query-complete and rendered-result timings. Identify the actual Python import location as well as the installed entry point: inherited working directories can shadow the installed module. A UI build ID alone does not identify backend code.

Read the repository's check scripts and CI before adding checks. Attach mechanical regressions to existing automated checks; use visual review for hierarchy and reference fidelity. Bound source searches to the relevant modules, excluding generated bundles and business output.

## Source navigation

Paths below are relative to the package root:

- `dashboard_runtime/web/`: MCP UI, filters, encoding, tooltip and transport behavior.
- `dashboard_runtime/local_data.py`, `local_view.py`, `bindings.py`: option queries, component calculations and binding validation.
- `dashboard_runtime/service.py`: MCP operations and diagnostics.
- `skills/executive-charts/scripts/core/dashboard_template.py`: shared original-chart engine source. Rebuild through `runtime-ui`; generated engine files are build output.
- `docs/project-runtime.md`: storage, loading and edit lifecycle; `docs/mcp-transport-diagnostics.md`: transport diagnosis; `docs/dynamic-encoding.md`: dynamic bindings.

## Self-hosted server

`python3 -m dashboard_runtime server` serves Streamable HTTP MCP on `/mcp` with bearer tokens and browser previews of dashboards and reports. `projectRoot` is then a project name inside the server workspace, never an arbitrary server path. Desktop file actions (`dashboard_export_open`) are unavailable remotely; exports return signed `downloadUrl` links instead. See package-root `docs/self-hosted-server.md` for deployment, tokens, share links and limits.

## Standalone hosting

For a website that must survive without MCP, call `dashboard_export_site`; ordinary HTML export is only a fixed-view snapshot. The deployment project includes `dist/`, data chunks, source and a Node build. Verify filtering through a static HTTP server and rebuild using only the exported project before claiming independence. Static export includes every row of the used datasets, not just the selected filter. See package-root `docs/static-deployment.md` for deployment and data-loading limits.
