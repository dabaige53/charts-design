# Component HTML Generation Contract

> **Historical Reference Notice (2026-11-10 Architecture Rebuild)**
> The native standalone HTML generation scripts (`generate_dashboard.py`, `generate_chart.py`, `dashboard_template.py`, `runtime_bundle.py`) have been removed for the React + TypeScript / Tailwind CSS v4 / shadcn/ui / ECharts / GridStack / Lucide rebuild.
> This document is retained as a reference for historical DOM contracts, component mounting structure, and visual interactions. It cannot be used as an active execution command set in the current rebuild phase.

Read this reference whenever understanding component DOM identity, structure, styles, and interaction contracts. The component JSON is the source; the renderer owns the presentation.

Use [dashboard-workspace.md](dashboard-workspace.md) for component JSON fields and current CLI syntax. Use [existing-project-checklist.md](existing-project-checklist.md) when applying this contract to an existing project.

## Historical generation pipeline (Reference)

In the previous generation pipeline, dashboard HTML was produced in this order:

1. `dashboard_workspace.py` resolved component files into one validated configuration.
2. `generate_dashboard.py` serialized business data and merged each chart component with the selected renderer.
3. `dashboard_template.py` emitted the document shell, root mounting points, and interaction engine.
4. `runtime_bundle.py` mounted the component sections in sequence.
5. ECharts initializes only after its chart and KPI canvas containers exist. Event handlers attach to the generated component identities.
6. Static HTML inspection checked document metadata, DOM references, local assets, and preservation requirements.

In the current rebuild phase, workspace contracts are strictly validated with `charts-design dashboard validate ./board --strict --json` without invoking legacy HTML builders.

## Choose the output mode

### Standalone chart

In the historical workflow, standalone charts were compiled via `generate_chart.py --config`. In the current rebuild phase, chart components are authored as JSON declarations adhering to `presentation` contracts and validated via workspace tools. Standalone HTML compilation is deferred until the new UI is connected.

### Dashboard

Use the workspace commands for KPI, chart, filter, and table composition. These components are validated together in the workspace before rendering.

Completion criterion: strict workspace validation passes, and the configuration contains every declared component by stable identity.

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
| `mc10` | Median with P25–P75 range box and min/max (distribution) |
| `mc11` | Value with ECharts ring progress container |
| `mc12` | Value with ECharts mini column trend container (last period emphasized) |
| `mc13` | Bullet: actual bar, target marker, optional qualitative ranges |
| `mc14` | Current vs prior period paired bars with change badge |
| `mc15` | Metric list: 1–4 related sub-metrics with signed changes |
| `mc16` | Hero number with an authored one-line takeaway |

Every KPI explanation action uses `data-explain-chart`; the shared dialog renders its definition and formula. Sparkline, gauge, ring and mini-bar DOM are initialized as ECharts instances after the cards render. Define a supported `binding` for each filter-dependent KPI. Missing optional values render as a dash; specialized cards require their explicit visual data in strict workspaces. Zero remains zero.

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

