---
name: executive-charts
description: Create, revise and refresh data-backed business dashboards, KPI scorecards and interactive analysis through Charts Design MCP or CLI. Use for sources, metrics, charts, filters, tables and saved dashboard delivery. For narrative Markdown reports with inline figures, use analytical-reports.
---

# Executive Charts

Build a dashboard around the user's question and the data available. Use the requested chart and reading order; fill unspecified choices with the project's [design standards](references/design_standards.md).

## Find the project and tools

Use the existing dashboard and asset directory when revising a result. Pass `projectRoot` on every project call: an absolute asset directory locally, or the configured project name on a remote server.

Read `charts://contract` for the connected server's operations. `chart_declarations` returns the component index; query a selected preset with `{"code":"c01"}` to get its fields, binding support and example. `generation_examples` provides complete synthetic cases: `executive-dashboard` and `operations-scorecard`.

| Task | Tools |
| --- | --- |
| Read declarations and editable revision | `dashboard_get` |
| Inspect dataset versions and row counts | `dashboard_data_inspect` |
| Import rows/CSV or attach a configured SQLite table | `dataset_import`, `dataset_attach` |
| Define sources, datasets, metrics, components and layout | `dashboard_patch` |
| Compute chart results and table pages | `dashboard_view` |
| Save one editing session | `dashboard_edit_begin`, `dashboard_edit_finish` |
| Show the completed dashboard | `dashboard_preview` |
| Read comments and version history | `dashboard_annotations`, `dashboard_history`, `dashboard_version_status` |
| Export a file or standalone website | `dashboard_export`, `dataset_export`, `dashboard_export_site`, `dashboard_export_read` |

Read [shared delivery](references/mcp-delivery.md) for revisions, batches, comments and publication.

## Create and fill a dashboard

1. **Read the data.** Inspect the supplied file or query the named source. Establish fields, row grain, time range, units and missing values. Record provenance in sources and calculation rules in metrics. Use existing business definitions when available; label synthetic examples. [Metric definitions](references/metric-definitions.md) covers scope and formulas.
2. **Register the inputs.** Define sources, datasets and metrics before binding components. Reuse a dataset across related calculations. Small imports accept rows or CSV; configured SQLite tables use `dataset_attach`. Read [local data](references/local-data.md) for large datasets, versioned references and exports.
3. **Choose the presentation.** Arrange the overview, comparisons and detail in the order that answers the question. Choose KPI forms by the comparison they show using [KPI selection](references/kpi-cards.md). Use [layout templates](references/layout_templates.md) when they fit. `chart_recommend` can suggest presets.
4. **Declare the components.** Select the renderer below, bind supported filters to explicit consumers and save each component's structure diagram. Put definitions, formulas, sources and detail rows in the shared detail view. KPI cards contain only titles, values, units, comparisons and concise graphical labels; narrative belongs in a separate text component.
5. **Save and inspect.** Follow the shared edit-batch flow. Compare computed totals, ratios, comparison values and table rows with the source at the same filter scope. Complete the batch and open the saved preview once.

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

Use the connected declarations' `structureDiagramSchema`: `{version:1, viewBox:[0,0,width,height], svg, annotations}`. Each annotation has a stable `id`, shape `anchor:[x,y]` and `label:[x,y]`; optional `align` is `left`, `center` or `right`. Reference canonical definitions with `metricId`; use `name` and `description` for axes, nodes and other parts. Keep label areas clear.

SVG contains static geometry and text. Business values, scripts, events, external references, CSS and URL paints are prohibited. Data refreshes, filters and resizing reuse the saved geometry; declaration changes require an updated diagram.

## CLI and handover

Use [workspace commands](references/dashboard-workspace.md) when the user wants local JSON assets. Store business datasets and declarations in their project. For framework integration, read [existing-project integration](references/existing-project-checklist.md).

Deliver the saved dashboard or requested export with a short explanation of what it shows, where its data came from and which assumptions affect interpretation. Mention concrete unresolved issues. Describe changes using the dashboard's own titles and controls.
