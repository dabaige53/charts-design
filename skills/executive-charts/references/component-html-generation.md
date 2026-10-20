# Component HTML Generation Contract

Read this reference whenever the task produces, changes, embeds, or migrates HTML for an `executive-charts` component. The component JSON is the source; the shared renderer owns the HTML. Generate through the bundled scripts so the same component identity, structure, styles, interactions, and inspection rules apply on every run.

Use [dashboard-workspace.md](dashboard-workspace.md) for component JSON fields and current CLI syntax. Use [existing-project-checklist.md](existing-project-checklist.md) when applying this contract to an existing project.

## Generation pipeline

Dashboard HTML is produced in this order:

1. `dashboard_workspace.py` resolves `dashboard.json`, `filters.json`, KPI files, chart files, and `table.json` into one validated configuration.
2. `generate_dashboard.py` serializes business data and merges each chart component with the renderer selected by its `code`. The component's explicit `id`, title, data, and unit override catalog preview values.
3. `dashboard_template.py` emits the document shell, design tokens, root mounting points, serialized `window.DASHBOARD_CONFIG`, renderer classes, and interaction engine into one HTML file.
4. `runtime_bundle.py` creates `DashboardRuntime`; `mount()` constructs `DashboardApp`, which calls `renderHeader`, `renderFilters`, `renderKPIs`, `renderChartsGrid`, `renderTableSection`, and `renderTableEngine` in that order.
5. ECharts initializes only after its chart and KPI canvas containers exist. Event handlers attach to the generated component identities.
6. `build` runs static HTML inspection to check document metadata, DOM references, local assets, and any supplied preservation requirements.

Completion criterion: the delivered HTML comes from this pipeline and passes strict component validation and static HTML inspection.

For an interactive preview, also check the rendered target page. Server-side JSON parsing and static inspection do not verify host decoding or frontend rendering. On failure, separate serialization, transport, decoding and rendering evidence; retain the error and response size, and do not claim a fix merely because reducing data made a local JSON check pass. Synthetic prototypes should reuse a bounded dataset across charts and tables, with row counts and response size reviewed before preview. Preserve required filter choices and aggregation semantics; do not silently truncate real data.

## Choose the output mode

### Standalone chart

Use `generate_chart.py --config <chart.json> --output <chart.html>` when the deliverable is one business chart card. The JSON supplies the chart code, business data, title, unit, and full `presentation` contract. The command validates the selected renderer, generates the standalone HTML document, and runs static inspection. Use code-only generation for catalog preview and `--snippet` for ECharts option source.

Completion criterion: the selected chart code answers the stated business question and the standalone HTML passes component validation and static inspection.

### Dashboard

Use the workspace commands for KPI, chart, filter, and table composition. These components are rendered into the shared dashboard shell at runtime; they are not independent handwritten HTML partials. Build after adding the smallest useful component slice.

Completion criterion: strict workspace validation passes before build, and the built dashboard contains every declared component by stable identity.

### Existing frontend project

Keep the existing framework as the page owner when the user needs an in-place migration. Map its component model to the JSON contracts, then either embed the generated standalone file or implement an adapter that preserves the DOM identities and capabilities below. Keep the shared renderer as the reference behavior; record any framework-specific Adapter in the existing-project checklist.

Completion criterion: each adapted region has one source component, one stable identity, an explicit capability mapping, and preservation evidence.

For embedded dashboards, mount against the owning container instead of the global document:

```js
const root = document.querySelector('#analytics-region');
const runtime = window.createDashboardRuntime(config, root);
runtime.mount();

// Framework unmount
runtime.destroy();

// The same root remains available for a later remount.
runtime.mount();
```

Only a document-root runtime owns the compatibility singleton `window.App`. A container-scoped runtime must keep queries, listeners, rendered identities, update, destroy, and remount inside its root so multiple embedded dashboards can coexist.

## Document shell

The generated dashboard contains these fixed mounting points:

```html
<div id="dashboard-app">
  <header id="app-header"></header>
  <section id="app-filters"></section>
  <main>
    <section id="app-kpis"></section>
    <section id="app-charts-grid"></section>
    <section id="app-table-section"></section>
  </main>
  <dialog id="app-explain-dialog"></dialog>
  <div id="app-toast-container"></div>
</div>
```

The shell owns layout, shared design tokens, explanation UI, toast feedback, and component mounting order. Business pages supply configuration; component renderers supply the child markup.

Completion criterion: each fixed mounting point occurs exactly once and all generated DOM references resolve to an existing id.

## Component DOM contracts

### Filters

`renderFilters()` maps every filter definition to one control inside `#app-filters`.

```html
<div id="filterWrap_<key>" data-component-id="<filter.id>">
  <!-- select or multi-select control and option menu -->
</div>
```

- `filter.id` is the component identity; `key` is the data-state key.
- `type` selects the single-select or multi-select HTML branch.
- `options` generate labels and menu items.
- `fields` bind filtering to explicit table fields.
- `componentIds` identify KPI and chart consumers.
- Active chips, reset, and keyword search belong to the shared filter bar rather than to individual filter component files.

Completion criterion: every filter has one `data-component-id`, every strict filter has explicit fields, and every consumer resolves to a declared component id.

### KPI cards

`renderKPIs()` selects one HTML renderer by `kpi.type`, inserts the card into `#app-kpis`, then assigns the root `id` and `data-component-id` from `kpi.id`.

| Type | Generated card structure |
| --- | --- |
| `mc01` | Standard value, status badge, comparison, supporting metric |
| `mc02` | Value with YoY and MoM deltas |
| `mc03` | Value with ECharts sparkline container |
| `mc04` | Goal value and progress bar |
| `mc05` | Value with ECharts semi-gauge container |
| `mc06` | Dual-metric split card |
| `mc07` | Ranking or tier badge card |
| `mc08` | Threshold alert card |
| `mc09` | Segment breakdown card |

Every KPI explanation action uses `data-explain-chart`; the shared dialog renders its definition and formula. Sparkline and gauge DOM are initialized after the cards render. Define a supported `binding` for each filter-dependent KPI. Missing optional values render as a dash; specialized cards require their explicit visual data in strict workspaces. Zero remains zero.

Completion criterion: every KPI root preserves `kpi.id`, the selected type has all data it displays, and any filter-dependent value has a verified recomputation path.

### Chart cards

`renderChartsGrid()` creates one shared card shell for every chart component. `code` selects the ECharts renderer; `instanceId`/`id` identify this occurrence.

```html
<div class="section-card" data-component-id="<chart.instanceId>">
  <div class="card-header-wrap" id="header-<chart.instanceId>">
    <!-- title, code badge, optional granularity, shared actions -->
  </div>
  <div class="card-body-wrap">
    <div id="<chart.id>" class="card-chart-pane"></div>
    <div id="table-pane-<chart.instanceId>" class="card-table-pane hidden"></div>
  </div>
</div>
```

The shared shell generates:

- optional month/quarter controls when `hasGranularity` is true;
- chart/table toggle;
- CSV export;
- image copy;
- fullscreen and restore;
- explanation action;
- chart pane and generated table pane.

Each action carries `data-component-id="<chart.instanceId>"`; runtime registries are keyed by that identity. Reusing one chart `code` produces separate instances. Tooltip, axes, legend, annotations, series, and renderer-specific `dataZoom` come from the selected chart renderer rather than from the card shell.

Completion criterion: the card, panes, actions, and runtime registry resolve to the same unique instance identity, and the renderer displays the component's explicit data, axes, series, Tooltip fields, units, and `tableHeaders`.

### Table

`renderTableSection()` creates the table shell inside `#app-table-section`; the root receives `data-component-id` from `table.id` or the stable default `table`. `renderTableEngine()` generates the current header and body from `columns`, filtered rows, ordering, visibility, sorting, page, and page size.

The shared table shell owns keyword filtering, active cross-filter state, column visibility, drag ordering, pagination, cell copying, and CSV export. Column HTML comes from stable column keys and titles; numeric right-aligned columns require units in strict workspaces.

Completion criterion: the root has one stable component identity, every visible header maps to a declared column key, and filtering, sorting, pagination, column controls, overflow, and export operate on the same resolved rows.

### Shared overlays and feedback

Author business definitions, scope, formulas and decision rules using [metric-definitions.md](metric-definitions.md). Do not use a metric title, SQL expression or generic policy sentence as its business definition.

Explanation content is generated into `#app-explain-dialog` when a KPI or chart explanation action fires. Render it as a read-only reference overlay with a title-bar close control, backdrop dismissal, `Escape` support, and a content-focused body. Toasts are appended to `#app-toast-container` for transient action feedback. Fullscreen changes the owning chart card state while preserving its component identity.

Completion criterion: overlays have one shared root, opening and dismissal work by mouse and required keyboard actions, and repeated updates do not duplicate roots or handlers.

## What may vary

Business configuration may vary titles, subtitles, values, units, series data, filter definitions, table columns and rows, explanations, chart code, layout span, and supported renderer options. Existing-project adapters may translate classes or framework events while preserving component identities and observable capabilities.

The shared shell owns mounting points, component identity attributes, action hooks, chart and table panes, lifecycle registration, and cleanup. Change these in the renderer/runtime source when the component system itself needs a new contract; regenerate the HTML afterward.

Completion criterion: business changes live in component data, while system-wide structural changes have one implementation in the shared renderer.

## Extend a missing component

When no existing type or code represents the required component:

1. Define its input data, unit rules, stable identity, rendered states, capabilities, and cleanup behavior.
2. Add the renderer or card branch to the shared generator/runtime rather than placing a one-off block in generated HTML.
3. Register its schema and discovery metadata.
4. Add behavior-level coverage for generation, identity, required interactions, and runtime cleanup.
5. Generate a thin dashboard containing the new component and run strict component validation and static HTML inspection.

Completion criterion: the new component is discoverable, schema-validated, generated through the shared path, independently identifiable, and verified from registered renderer output.

## Delivery gate

Before presenting component HTML as complete:

- strict workspace validation passes;
- generated static HTML inspection passes;
- every declared component appears under the correct mounting point with its stable identity;
- required Tooltip, zoom, explanation, filtering, table, export, copy, and fullscreen behaviors are directly exercised where in scope;
- existing-project migrations also pass Preservation Manifest inspection and baseline comparison.

Generation is complete when every in-scope component and capability has observable evidence through the delivery gate.
