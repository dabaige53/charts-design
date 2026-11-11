---
name: executive-charts
description: Create and revise analytical dashboards and reports through the project MCP or CLI, using built-in presets, native ECharts, or custom HTML/CSS/JavaScript components. Preserve business data and interaction semantics without limiting charts to the catalog.
---

# Executive Charts

Use the user's analytical question and current product requirements to choose the presentation. The catalog supplies starting points.

## Current product rules

- **KPI cards contain no descriptions.** Do not add subtitles, prose, notes, takeaways or interpretation paragraphs to any KPI, including mc16. Forbidden fields are `subtitle`, `description`, `desc`, `note`, `detail`, `rankSub`, `trendLabel` and `gaugeSub`. Keep the title, values, units, comparisons, concise value labels and data graphics. Put business definitions in metric metadata and analysis in a separate text component.
- **Charts have broad creative freedom.** Choose a built-in preset, a complete native ECharts option, or a custom HTML/CSS/JavaScript component. Do not force an unfamiliar visualization into one of the 40 preset codes. React components may be delivered as browser-ready JavaScript inside the custom frame; there is no raw JSX compiler.
- **Saving and rendering use the same route.** A custom business code must declare `renderer: "echarts"` or `renderer: "html"` and its corresponding content. Unknown preset codes are rejected with instructions for the custom routes. Do not mislabel a custom visual as a registered preset to bypass validation.
- **Data semantics stay explicit.** Preserve units, actual comparison baselines, dataset references, stable component IDs and versions. Never fabricate targets, forecasts, confidence intervals or conclusions. Clearly identify synthetic examples.
- **Capabilities are declared, not assumed.** Preset bindings provide supported Runtime aggregation and filtering. Custom renderers currently use explicit snapshots, with optional explicit data tables; they do not automatically acquire global filtering, aggregation or drilldown. Local interaction can be implemented in the custom script.


## Choose a rendering route

All three chart routes use `put_component` with `kind: "legacy"`, `family: "chart"`.

| Route | Configuration | Use |
| --- | --- | --- |
| Preset | `code`, `data`, `presentation`; optional `renderer: "preset"` | Existing defaults, supported bindings and shared actions |
| Native ECharts | `renderer: "echarts"`, any non-empty `code`, complete `echarts` object | Arbitrary supported ECharts series, combinations, coordinates, annotations and styling without preset geometry |
| Custom component | `renderer: "html"`, any non-empty `code`, `html` string; optional `data` object | Custom SVG/Canvas/HTML, scripts, browser-ready React and HTTPS libraries in an isolated frame |

Custom routes may supply `table: {headers: string[], rows: array[]}` for shared table view and CSV. Without a declared table, those actions are absent. HTML components do not expose the host ECharts PNG/clipboard actions. `window.chartData` provides their `config.data`.

Read package-root [native and custom rendering](../../docs/implementation/echarts-options.md) for declarations, examples and execution boundaries. Read `charts://declarations` or call `chart_declarations` for the currently connected server's capabilities.

## Work on an existing artifact

1. Read `dashboard_get` and the current revision. Preserve the user's accepted content and unrelated edits.
2. Identify the requested changes, data sources, metrics and affected filter consumers. A title/style edit must not replace business data or bindings.
3. Modify only the needed components and layout. Keep stable IDs. Use `set_layout` for a custom composition or `apply_layout_template` as an optional starting point.
4. Save through the existing edit batch and `expectedRevision` flow. Report implementation, resource build and actual host acceptance separately.

For project routing, batches, attachments and annotations, read [shared delivery workflow](references/mcp-delivery.md). User instructions about tests, browser use or approval take precedence over any checklist in a reference. Do not automatically run all tests or launch a preview server.

## Create a dashboard

- Start from the question and data. Use `chart_recommend` if the preset catalog is useful; it is optional and cannot forbid a custom visual.
- Define sources, datasets and metrics before binding components. Use one dataset for shared calculations instead of copying observations into every chart.
- Select KPI shapes by the information being compared. [KPI selection](references/kpi-cards.md) describes the 16 available forms. Shape diversity and hero-card count are suggestions; directly comparable metrics may use the same form.
- Choose a layout for the reading order and available space. [Layout templates](references/layout_templates.md) are examples, not a mandatory set of compositions.
- Expose only implemented interactions. Explicitly identify snapshot components when the page also contains live filter consumers.
- Put narrative analysis outside KPI cards. Sources, definitions, formulas and detail rows belong in the shared detail view when supported.

For local datasets that must remain outside the preview, read [local data](references/local-data.md). Use configured dataset attachment and export tools rather than inserting entire observation tables into chart configs. Custom snapshot data should contain the values needed by the visual.

## CLI and project assets

Maintain this skill in `skills/executive-charts/`; installed aliases should point here. Store business datasets and declarations in the user's project, never in the skill tooling directory.

The CLI workspace accepts KPI and chart declaration files. Its custom chart renderer validation matches Runtime. Use the shared React Runtime and explicit build/package steps. The implementation status is in package-root `docs/plans/ui-refactor-plan.md`.

Markdown reports use the analytical-reports path and reference the same saved components. Report prose does not belong inside KPI cards.

## Definitions and visual rules

Read [design standards](references/design_standards.md) for component titles, alignment and actions.

For business definitions, read [metric definitions](references/metric-definitions.md). For calculations and supported dynamic fields, read the current Runtime declarations. Keep facts, labels and formulas consistent; creative freedom applies to presentation, not invented data.

## Saved structure diagrams

Generate a separate structure diagram for each component from its actual marks, field bindings and series meaning. Submit it in the same `put_component` batch: `config.presentation.structureDiagram` for legacy components, `presentation.structureDiagram` for other components, including statistical images, KPI cards and tables. Use the shared `structureDiagramSchema` from declarations; never select a generic diagram by chart type.

Save `{version:1, viewBox:[0,0,width,height], svg, annotations}`. An annotation has a stable `id`, an `anchor:[x,y]` on the shape and `label:[x,y]`; optional `align` is `left`, `center` or `right`. Reference a canonical `metricId` without duplicated name/definition, or provide `name` and `description` for axes, nodes and other parts. Keep label areas clear. SVG contains only static geometry/text, no business values, scripts, events, external references, CSS or URL paints.

When geometry, field bindings or series meaning changes, regenerate the diagram before submitting the component. Omission after a declaration change retains the previous diagram as stale; explicit submission confirms the supplied diagram. Data refreshes, filters and resize reuse the saved geometry. Old components remain usable without diagrams; explicitly add an authored diagram to each component being delivered. Do not develop chart-family adapters or substitute catalog sample business definitions.
