---
name: executive-charts
description: Build or revise executive dashboard data assets, declarations, KPI cards, filters and tables through the project MCP runtime or CLI workspace tools. Use for dashboard data modeling, component declarations and analytical workspaces.
---

# Executive Charts

Turn business evidence into a restrained executive dashboard. Run the scripts bundled beside this file and compose the result from small, reviewable building blocks.

> **Current status (2026-11-10)**
> The shared React component library and MCP application use separate adapters and explicit build/package steps. Preview, JSON/CSV, HTML snapshots and static site exports use the new resources. Missing builds return `UI_UNAVAILABLE`. Current completion and host acceptance are tracked in package-root `docs/ui-refactor-plan.md`.

The goal is a reusable business-component generation system whose configuration is grounded in explicit business evidence, typed metrics, and strict component declarations.

## Project MCP editing and display

For MCP creation, edits, data replacement, installation or loading failures, read [the shared delivery workflow](references/mcp-delivery.md). It defines project storage, edit batches, semantic preservation and separate source/install/host acceptance.

Before revising an accepted dashboard, read [the existing-project checklist](references/existing-project-checklist.md), including for MCP dashboards without standalone HTML. Use the HTML Preservation Manifest only for the HTML branch; it is not evidence that MCP bindings survived.

## Runtime MCP reference case

For local datasets that must remain outside the preview, read [local-data.md](references/local-data.md). Use `dataset_attach` to stream an operator-configured SQLite table into a versioned local dataset; bind components to that dataset. MCP returns local aggregate results and table pages by default. Use `dashboard_view` for unsaved reader filters, pagination, sorting and time-grain changes; `dataset_export` streams every matching row to a managed local CSV. Do not expand rows per chart, send full observations in component configs, or launch an HTTP service. Inspect data versions, row counts and sizes with `dashboard_data_inspect`.

This is the Dashboard generation track. For the local runtime, call `generation_examples` with `{"caseId":"executive-dashboard"}` or read `charts://examples/executive-dashboard`: it returns synthetic KPI/chart/table/filter declarations ready for an atomic patch. Read `charts://declarations` for chart contracts and `charts://contract` for mutation rules. Pass `projectRoot` on every project call; create, begin an edit batch, patch with the latest revision, finish the batch and resolve Doctor errors. Open the saved dashboard with `dashboard_preview` after finishing its edit batch. New interactive charts use registered original codes and explicit supported bindings; `chartType` authoring is rejected, with compatibility reading for historical generic charts.

For Markdown-first analytical documents, use [analytical-reports](../analytical-reports/SKILL.md) and its approved academic master instead of composing a dashboard grid. Both tracks reuse existing chart definitions and source/data semantics.

## Compose for the question, not from one template

Generated dashboards must not all look alike. Decide the composition from the business questions before writing operations:

1. For each evidence block, call `chart_recommend` with its intent (comparison, ranking, trend, composition, distribution, relationship, flow, change, attribution, target, forecast) and data shape. It ranks registered codes, marks filter-bindable ones, suggests KPI shapes and down-ranks codes already on the page.
2. Choose KPI shapes per question from [the KPI selection guide](references/kpi-cards.md) (16 types, mc01–mc16). Use two to four different shapes in a KPI row; mc01 is not the default for every metric.
3. Choose one of the seven layout templates in [layout templates](references/layout_templates.md) and apply it with `apply_layout_template`; do not hand-write coordinates or stack every card full width. Different pages of one project should not repeat one composition.
4. Compare the two dashboard generation cases (`executive-dashboard` and `operations-scorecard`): they share data but differ in layout, KPI shapes and charts. Copy neither; use them to see the contract.

## Self-hosted server

When the MCP runs as the self-hosted server (`python3 -m dashboard_runtime server`), `projectRoot` is a project name on that server. Deployment, authentication and boundaries are described in package-root `docs/self-hosted-server.md`. Remote browser preview and sharing links will resume once the replacement UI is connected.

## Route the task

- For a dashboard workspace, use `charts-design dashboard` or run `scripts/dashboard_workspace.py` with `init`, `add`, `inspect`, and `validate`.
- For an existing workspace, start with `inspect` and `validate`.
- For an existing dashboard migration or frontend project, read [references/existing-project-checklist.md](references/existing-project-checklist.md) to preserve IDs, metrics, bindings, and business questions.
- For CSV input, use `import-csv` as a draft, then review the inferred fields before adding charts.
- Note: Standalone HTML generation scripts (`generate_chart.py`, `generate_dashboard.py`) and `workspace build` are unavailable; HTML outputs cannot be compiled until the new UI is connected.

Resolve the directory containing this `SKILL.md` once, then invoke its sibling scripts with `python3` as the execution interface.

In this source repository, `skills/executive-charts/` is the maintained implementation. Point local agent skill installations at that directory; do not maintain independent renderer copies in `.agents/skills/`. Verify the resolved script path before generating or diagnosing output.

For component structure, mounting contracts and historical HTML architecture, read [references/component-html-generation.md](references/component-html-generation.md).

## Dashboard workspace loop

1. Discover registered chart codes and metadata:

   Read [references/chart_catalog.json](references/chart_catalog.json) or run `charts-design list`.

   Continue when the selected code matches the business question.

2. Create an empty workspace outside this skill directory:

   ```bash
   charts-design dashboard init ./board --title "经营决策看板" --org "经营分析部"
   ```

   The workspace is ready when `inspect --json` reports the intended starting components and every reference resolves.

3. Add one evidence block at a time. Keep each KPI, chart, or table in its own small JSON file; manage filters with the CLI:

   ```bash
   charts-design dashboard add kpi ./board revenue --label "营业收入" --value 224 --unit "万元"
   charts-design dashboard add chart ./board regional-sales --from ./regional-sales.chart.json
   ```

   Put the chart's `code`, title, unit, data, and complete `presentation` contract in `regional-sales.chart.json`. After each meaningful block, run `inspect --json`. Proceed when the current values and display semantics match the business requirement.

   When adding filters, first load table rows and declare each consumer's aggregation `binding` using [dashboard-workspace.md](references/dashboard-workspace.md#filter-bindings). Validation checks the referenced columns, consumers, and supported aggregation shape.

4. Validate early and verify strict contracts:

   ```bash
   charts-design dashboard validate ./board --strict --json
   ```

   Workspace validation confirms reference integrity, schema compliance, and binding correctness. Iteration is complete when strict validation passes and every block supports a stated management question.

For command shapes and component schemas, read [references/dashboard-workspace.md](references/dashboard-workspace.md) when assembling a dashboard.

## Decision rules

Before authoring or revising metric explanations, read [metric-definitions.md](references/metric-definitions.md). Business definitions must explain the business object, scope and meaning in plain Chinese; keep SQL and field expressions in calculation semantics. Define inclusion/exclusion rules only from confirmed evidence.

- **Evidence chain:** Choose each chart for a specific comparison, trend, composition, distribution, relationship, flow, attribution, or target question. Prefer the smallest set that closes the decision narrative.
- **Typed metrics:** Give every displayed number a semantic type, unit, scale and precision. Record source parsing outcomes explicitly.
- **KPI comparisons:** Keep numeric comparisons numeric until formatting; use metric bindings for units and precision. Legacy display strings must include their actual direction (`+12.4%`, `-1%`); never guess a sign from an unsigned string. Zero and missing values stay neutral. Run strict validation and check positive, negative, zero, missing and filtered states. Preserve signs during recomputation and label YoY/MoM explicitly.
- **Prototype data:** Start from the smallest explicit fixture that covers the required states and filter choices. Reuse one dataset for calculations and tables; do not expand every dimension combination or duplicate rows for each visualization. Label synthetic data. Inspect row counts and serialized response size before preview; never silently sample real business data or narrow required filter coverage.
- **Dynamic filters:** Represent filters as an array of 0–N business dimensions. Use business field keys rather than industry aliases.
- **Explicit filter scope:** Declare every consumed data field with `--field` and every affected component with `--consumer`. Strict validation confirms this field-to-consumer mapping.
- **Stable component identity:** Component `id` is the runtime and DOM identity. Chart `code` selects the visual renderer and may repeat across independently identified instances.
- **Business-owned data:** Final workspaces contain explicit user/business data. Use catalog and preset data for structural preview.
- **Business-owned presentation:** Declare `presentation` metadata for axes, series, Tooltip values, units, complete `tableHeaders`, and renderer-specific domains, thresholds, or labels.
- **Bounded context:** Use `inspect --json` for summaries and edit one component file at a time.
- **Visual system:** The replacement presentation system is under redesign and new visual tokens are not yet finalized. Historical palettes and guidelines in [references/design_standards.md](references/design_standards.md) serve as historical reference only and do not automatically bind the new UI.
- **Catalog metadata:** Select codes from [references/chart_catalog.json](references/chart_catalog.json). Use its metadata for chart choice and intent alignment.

## Tooling boundary

Treat this skill directory as installed tooling during generation. Put workspaces, source data and configured assets in the user's project. Component definitions and data structures are maintained in the workspace and project stores.
