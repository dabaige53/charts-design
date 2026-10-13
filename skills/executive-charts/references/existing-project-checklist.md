# Existing Project Adoption Checklist

Read this checklist before using `executive-charts` to restyle, migrate, or extend an existing HTML dashboard or frontend project. Treat the existing product as the baseline: preserve its business meaning and working behavior while replacing presentation through explicit component contracts.

Use [dashboard-workspace.md](dashboard-workspace.md) for current CLI syntax, component schemas, Preservation Manifest fields, and Inspector commands.
Use [component-html-generation.md](component-html-generation.md) when mapping an existing region to generated DOM or adapting the runtime contract to another frontend framework.
Use [design_standards.md](design_standards.md) when changing the page's visual system, chart geometry, Tooltip, typography, spacing, color, or responsive behavior.

## 1. Establish the baseline

- [ ] Identify every page entry, build command, framework, styling system, chart library, table library, and runtime dependency in scope.
- [ ] Record whether the deliverable must remain a framework page, become a standalone HTML file, or support both.
- [ ] Record browser, viewport, offline, CDN, CSP, authentication, and data-privacy constraints.
- [ ] Open each in-scope state with representative business data, including loading, empty, error, filtered, overflow, and narrow-screen states that already exist.
- [ ] Run `inventory-html` for each existing HTML entry and reduce the generated Preservation Manifest to business-critical ids, visible text, assets, and component roots.
- [ ] Run strict static inspection on the baseline; classify every existing failure as an accepted baseline issue or a migration blocker.

Completion criterion: every in-scope page and state has a reproducible entry, its constraints are recorded, and every Preservation Manifest contains only requirements that must survive migration.

## 2. Choose the adoption mode

Choose one mode for each page before editing:

| Mode | Use when | Delivery shape |
| --- | --- | --- |
| Standalone replacement | The user wants a generated single-file dashboard and the existing framework does not need to remain the page owner | Workspace sources plus generated HTML |
| In-place adapter | Existing routing, authentication, state, data fetching, or framework components must remain | Existing page with components adapted to the shared DOM and capability contracts |
| Hybrid | Individual charts can be standalone while the existing page retains navigation, forms, or tables | Explicit boundary and lifecycle for each embedded generated component |

- [ ] Record the owner of page layout, data fetching, filter state, component lifecycle, and final HTML for the chosen mode.
- [ ] Keep the baseline entry operable while developing the first migrated slice, using the project's recoverable change workflow.
- [ ] Record framework-specific differences as Adapters with their verification method.

Completion criterion: every page has one declared adoption mode, every cross-boundary responsibility has one owner, and the first slice preserves the working entry during baseline comparison.

## 3. Inventory components and behavior

Create one row for every visible or interactive region. Split a region when parts have different data ownership, lifecycle, or filtering behavior.

| Existing region | Stable id | Business question | Data source | Current behavior | Target contract | Gap or adapter |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  | `KPI` / chart code / filter / table / shell |  |

Account for all of the following where present:

- [ ] KPI value, unit, scale, precision, comparison period, status semantics, and explanation.
- [ ] Chart title, subtitle, code, data shape, series meaning, axes, legend, Tooltip, mark lines, annotations, and empty state.
- [ ] Chart/table view toggle, CSV export, image copy, fullscreen, explanation dialog, resize, and destroy lifecycle.
- [ ] Internal chart zoom or `dataZoom`; mark it as renderer-specific when the selected chart does not provide it.
- [ ] Filters, option values, default selections, explicit `fields`, and every consumer `component.id`.
- [ ] KPI aggregation and chart recomputation needed after filtering; use the declarative `binding` contract where supported, or record the framework adapter needed for a structured component.
- [ ] Table columns, units, alignment, sorting, pagination, keyword search, filter behavior, column visibility, drag order, copying, export, and overflow behavior.
- [ ] Dialogs, drawers, menus, keyboard actions, focus order, labels, and ARIA references.
- [ ] Render metric/chart explanations as read-only reference overlays with a title-bar close control, backdrop dismissal, `Escape`, and a content-focused body.

Completion criterion: every existing region appears exactly once in the inventory, every behavior has an owner, and every unsupported behavior has an explicit adapter, scoped follow-up, or accepted exclusion.

## 4. Lock identity, content, and assets

- [ ] Preserve each business component's stable `id`; use chart `code` only to select its renderer.
- [ ] Resolve duplicate ids before migration and update every `for`, `href`, `aria-controls`, and script reference together.
- [ ] Add required legal text, business labels, definitions, image references, fonts, stylesheets, and scripts to the Preservation Manifest.
- [ ] Add known demo, preset, wrong-industry, stale-unit, or placeholder terms to `forbiddenText`.
- [ ] Record intentional removals separately; obtain user approval before removing business content or working behavior.

Completion criterion: every retained identity, text, and asset is machine-checkable, and every intentional removal is explicitly approved rather than silently omitted.

## 5. Map data contracts

- [ ] Give every KPI and chart explicit business data; catalog and preset values remain preview inputs only.
- [ ] For every registered chart code, map the original axes, series, Tooltip labels, units, complete table-column names, domains, thresholds, totals, and classification labels into `presentation` according to `CHART_PRESENTATION_CONTRACTS` and `CHART_TABLE_HEADER_COUNTS`.
- [ ] Validate chart data collections, paired vector lengths, unit, scale, null handling, and formatter assumptions before rendering.
- [ ] Give every filter at least one explicit `field`; list only stable consumer ids in `componentIds`.
- [ ] Verify option `value` exactly matches the bound source field; `label` is display text.
- [ ] Define filtered KPI aggregation and chart updates wherever values must change with the table rows.
- [ ] Give every table column a stable key and title; give numeric right-aligned columns an explicit unit.
- [ ] Preserve parse failures and missing values as errors or missing data rather than converting them to zero.

Completion criterion: strict workspace validation passes, and each displayed value can be traced from source field through transformation, unit, and consumer component.

## 6. Iterate one vertical slice

Use a **thin slice**: migrate one complete business region through data, HTML generation, styling, interaction, and verification before starting the next region.

1. Select one region whose data and current behavior are reproducible.
2. Capture its baseline content, state, viewport, and required interactions.
3. Map it to one supported component contract or define one scoped Adapter.
4. Generate its HTML through the shared renderer, or implement the declared in-place adapter against the same identity and capability contract.
5. Compare business content, information hierarchy, geometry, visual tokens, and interactions with the baseline.
6. Run applicable static, preservation, and component behavior checks; correct the slice until its Blockers are zero.
7. Record the evidence and accepted differences, then select the next region.

Track each iteration:

| Slice | Baseline evidence | Component/Adapter | Visual delta | Interaction evidence | Result |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  | Blocked / accepted |

Completion criterion: every accepted slice works end to end, has recorded comparison evidence, and leaves no unresolved Blocker before the next slice begins.

## 7. Integrate the visual system

- [ ] Map existing design tokens to the Skill tokens before changing individual component CSS.
- [ ] Check typography, spacing, radius, border, shadow, categorical colors, and positive/negative/attention semantics.
- [ ] Scope Skill styles so existing navigation, forms, dialogs, and third-party widgets retain their intended appearance.
- [ ] Check card headers with long titles, units, legends, Tooltip content, axis labels, annotations, and action controls for collision or clipping.
- [ ] Check charts and tables at every required viewport; verify zero-width, hidden-tab, fullscreen, and container-resize transitions.
- [ ] Verify the selected renderer matches the original component's information hierarchy, not merely its broad chart category.

Completion criterion: each mapped component preserves the original business hierarchy, meets the required viewport constraints, and introduces no style leakage outside its owned region.

## 8. Verify generated output

- [ ] Build the candidate through the workspace path; confirm automatic static inspection passes.
- [ ] Run strict `inspect-html` with the Preservation Manifest.
- [ ] Run `compare-html` from the exact baseline file to the candidate file.
- [ ] Exercise filters, filter reset, chart Tooltip, renderer-specific zoom, chart/table toggle, sorting, pagination, column controls, export, copy, fullscreen, explanation dialog, and keyboard dismissal where those capabilities are in scope.
- [ ] Open every KPI/chart explanation trigger and verify the expected read-only sections and dismissal controls.
- [ ] Verify filtered KPIs and charts actually recompute; a changed chip or filtered table alone is not evidence of consumer updates.
- [ ] Inspect browser console errors, missing network resources, CSP violations, font fallback, and offline behavior required by the project.
- [ ] Compare representative screenshots at required viewports when visual preservation is an acceptance criterion.

After all slices pass individually, repeat the full-page states captured in the baseline. Verify cross-component filters, layout flow, shared overlays, resize behavior, and style isolation across slice boundaries.

Completion criterion: static inspection, preservation comparison, and component behavior checks pass; each in-scope interaction has direct observed evidence, and the assembled page preserves the evidence already accepted for each slice.

## 9. Decide readiness

Classify every remaining item before delivery:

- **Blocker:** lost business content, broken identity/reference, missing asset, incorrect data or unit, runtime error, unusable interaction, or unapproved behavior removal.
- **Adapter:** required existing behavior implemented outside the current shared component contract, with its owner and verification recorded.
- **Accepted difference:** intentional visual or behavioral change approved by the user and excluded from the Preservation Manifest where appropriate.
- **Follow-up:** valuable improvement outside the migration acceptance boundary, recorded with its future scope.

The migration is ready when Blockers are zero, every Adapter has passing evidence, every Accepted difference has approval, and the final component inventory accounts for every original region.

## Handoff record

Deliver these artifacts together:

- [ ] baseline entry and candidate entry;
- [ ] component inventory and mapping table;
- [ ] edited Preservation Manifest;
- [ ] workspace source files and generated HTML;
- [ ] static inspection, comparison, and component behavior test results;
- [ ] approved differences, adapters, exclusions, and follow-ups.

Completion criterion: another agent can reproduce the build and verification from the delivered artifacts and evidence record.
