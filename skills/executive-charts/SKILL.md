---
name: executive-charts
description: Create, revise and refresh data-backed business dashboards, KPI scorecards and interactive analysis through Charts Design MCP or CLI. Migrate existing non-MCP dashboards into editable Charts Design dashboards. Use for sources, metrics, charts, filters, tables and saved dashboard delivery. For narrative Markdown reports with inline figures, use analytical-reports.
---

# Executive Charts

Build around the decision the reader needs to make. Establish the question, audience and available evidence from the request and project; choose unspecified layout and chart details using [design standards](references/design_standards.md). Ask only when missing data access or an unresolved business definition would change the result. Do not pause for routine styling choices.

| Starting point | Read and act |
| --- | --- |
| New dashboard with known data | Profile the fields and grain, then follow **Create and fill** below. Use one representative case only if the declaration shape is unfamiliar. |
| Existing dashboard or refresh | Read `dashboard_get`; preserve stable IDs and reuse dataset references. Follow **Change or refresh**. |
| External dashboard migration | First delegate a page-by-page [source audit and MCP mapping](references/existing-project-checklist.md#从外部历史报表迁入-mcp) when a subagent is available; otherwise perform it directly. Preserve content, reading order, geometry and operations. Compare against the original, not the chosen template. |

Use MCP directly for creation and editing. The [native authoring guide](references/mcp-authoring.md) includes a complete initial `dashboard_submit` call and a report variant. JSON objects are tool arguments; creating intermediate files or running a script is optional, for file-based review, offline edits or repeatable batch work.

## Find the project and tools

Use the existing dashboard and asset directory when revising a result. Pass `projectRoot` on every project call: an absolute asset directory locally, or the configured project name on a remote server.

Read the connected server's `charts://contract` once for the relevant operations; reuse discovery while that server build is unchanged. Fetch selected presets together with `chart_declarations {"codes":["c02","t01","mc03"]}`: 1–8 unique codes share common schemas once. Use `code` for one preset, without `codes`; omit both for the compact index. Chart examples live under `legacy.chartCodes[code].example`, KPI configurations under `legacy.kpiTypes[code].exampleConfig`. `charts://examples` provides optional full-page synthetic cases; all example values must be replaced by current evidence.

| Task | Tools |
| --- | --- |
| Read declarations and editable revision | `dashboard_get` |
| Inspect dataset references and row counts | Import or attachment receipt, existing references in `dashboard_get` |
| Inspect dataset fields and a small row sample before creating components | `dataset_preview` with `datasetId`; follow the data write receipt's `nextCalls` |
| Import rows/CSV or attach a configured SQLite table | `dataset_import`, `dataset_attach` |
| Register a configured read-only SQL snapshot or live source | `query_execute`; choose the data lifecycle using [local data](references/local-data.md) |
| Submit declarations or layout, check and save | `dashboard_submit` |
| Verify selected results and their definitions | `dashboard_view` with `responseMode: "patch"`, `componentIds`, `includeEvidence: true` |
| Inspect a small page of underlying rows | `component_data` with explicit `limit`, then paginate only as needed |
| Show the completed dashboard | `dashboard_preview` |
| Set a saved version as the formal publication | `dashboard_publish` |
| Create a visitor link for a saved version | `dashboard_share_publish` |
| Read comments | `dashboard_annotations` |
| Export a file or standalone website | `dashboard_export`, `dataset_export`, `dashboard_export_site` |

Read [shared delivery](references/mcp-delivery.md) for revisions, batches, comments and publication.

Use native filter and chart-linking controls where supported. Every applied filter needs a visible active state, and a chart selection that drives filtering stays highlighted after the pointer leaves. Follow the [interaction defaults](references/design_standards.md#操作与更新) and verify them in the delivered view.

## Create and fill a dashboard

1. **Read the data.** Inspect available metadata and rows for fields, grain, types and units. For a registered dataset, `dataset_preview` works before any component exists and does not apply component filters. Obtain time ranges, category counts and missing-value rates from source metadata or full-scope summary queries, not the sample. Record provenance in sources and calculation rules in metrics. Use existing business definitions when available; label synthetic examples. [Metric definitions](references/metric-definitions.md) covers scope and formulas.
2. **Register the inputs.** If small data and its meaning are already known, include `put_source`, `put_dataset`, reviewed metrics and components in one initial `dashboard_submit(createTitle, operations)`. If inspection must come first, create an empty container, import or attach the data, then follow the receipt's `nextCalls` to `dataset_preview`. `dataset_import` accepts rows or CSV and optional explicit `fields`; imported sum metrics remain `unverified`. Reuse a dataset across related calculations. Read [local data](references/local-data.md) for configured SQL, large datasets, versioned references and exports.
3. **Choose the presentation.** Arrange the decision, evidence and detail in reading order. Follow the [question-to-chart guide](references/design_standards.md#按问题与证据选图) and [KPI selection](references/kpi-cards.md). Pass known shape to `chart_recommend`; set `requiresFilterBinding: true` for charts that must respond to filters. Check each candidate's `requirements`, `cautions` and `bindingMode`; an `encoding` path needs its explicit encoding declaration. Use returned questions to inspect the source first. Keep comparable charts consistent and choose one [layout template](references/layout_templates.md) or retain the accepted layout.
4. **Declare the components.** Select the renderer below, bind supported filters to explicit consumers and save each component's structure diagram. Put definitions, formulas, sources and detail rows in the shared detail view. KPI cards contain only titles, values, units, comparisons and concise graphical labels; narrative belongs in a separate text component.
5. **Save and inspect.** Submit sources, datasets, metrics, components, filters and layout in one related batch where possible. `dashboard_submit` already performs full checks and saves; do not add a separate routine validate/doctor/checkpoint sequence. Verify affected results together using one patch view, then inspect only the necessary detail rows. Compare with the source at the same revision and filter scope. Open the saved preview once and use the [design review](references/design_standards.md#交付前的设计复核).

Use the reader's language for titles, labels, dates and state messages. Follow [data formatting](references/data_formatting_standards.md) for units and precision. Preserve actual comparison baselines; leave missing baselines missing.

## Choose a renderer

Chart components use `put_component` with `kind: "legacy"` and `family: "chart"`.

| Route | Configuration | Data and interactions |
| --- | --- | --- |
| Preset | `code`, `data`, `presentation`; optional `renderer: "preset"` | Runtime aggregation, filters and shared actions declared for that code |
| Native ECharts | `renderer: "echarts"`, custom `code`, complete `echarts` object | Explicit snapshot with authored series, coordinates, annotations and styling |
| HTML/JavaScript | `renderer: "html"`, custom `code`, `html`; optional `data` | Isolated frame with `window.chartData`, SVG/Canvas and browser-ready JavaScript, including compiled React |

For native and custom components, declare `table: {headers: string[], rows: array[]}` to enable shared table view and CSV. Implement custom local interactions in the component script. Distinguish snapshots from filter consumers when both appear on a page.

Read [component rendering](references/component-html-generation.md) for shared actions and [native/custom configuration](../../docs/implementation/echarts-options.md) for complete declarations.

## Change or refresh

Read the current document and affected source data first. Preserve stable component IDs, unrelated content, metric definitions, filter consumers and comments. `put_component` replaces the complete component, so carry forward fields that remain in use.

For a data refresh, import or attach the new dataset version, inspect its fields and counts, then recompute affected components and authored claims. Compare ratios from aggregated numerators and denominators; calculate changes at the same scope and grain. Update prose tied to the refreshed data together with its figures.

For a visual edit, change the requested layout or presentation fields. When geometry, field bindings or series meaning changes, regenerate the component's structure diagram.

## Save structure diagrams

Author each diagram from the component's actual marks, field bindings and series meaning. Submit it with `put_component`: `config.presentation.structureDiagram` for legacy components, `presentation.structureDiagram` for other kinds, including KPI cards, tables and statistical images.

Use the connected declarations' `structureDiagramSchema`: `{version:1, viewBox:[0,0,width,height], svg, annotations}`. Each annotation has a stable `id`, shape `anchor:[x,y]` and `label:[x,y]`; optional `align` is `left`, `center` or `right`. Reference canonical definitions with `metricId`; use `name` and `description` for axes, nodes and other parts. Keep label areas clear. Preserve the actual chart’s axis titles, units, category labels, legend and distinctive marks when present. Use representative category labels when the structure needs them; do not invent business values. Make the plot use the available space, reserving only enough room for readable annotations and avoiding overlaps.

SVG contains static geometry and text. Business values, scripts, events, external references, CSS and URL paints are prohibited. Data refreshes, filters and resizing reuse the saved geometry; declaration changes require an updated diagram.

## CLI and handover

Use [workspace commands](references/dashboard-workspace.md) when the user wants local JSON assets. Store business datasets and declarations in their project. For framework integration, read [existing-project integration](references/existing-project-checklist.md).

Deliver the saved dashboard or requested export with a short explanation of what it shows, where its data came from and which assumptions affect interpretation. Mention concrete unresolved issues. Describe changes using the dashboard's own titles and controls.
