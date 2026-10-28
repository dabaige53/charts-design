---
name: executive-charts
description: Build reusable executive chart, KPI, filter, table, and dashboard components from business data, then generate and verify final HTML with the bundled Python scripts. Use for new dashboards, component embedding, or upgrades of existing HTML/frontend projects.
---

# Executive Charts

Turn business evidence into a restrained executive dashboard. Run the scripts bundled beside this file and compose the result from small, reviewable building blocks.

The goal is a reusable business-component generation system whose deliverable is working HTML or an explicit framework Adapter. Use the Gallery and `examples/` for discovery and visual comparison. Generate final markup from explicit business data through the registered component pipeline.

## Project MCP editing and display

Use a project-configured runtime (`--project-root` for durable assets and `--runtime-root` for disposable runtime files). Do not create business dashboards inside a plugin installation or shared cache directory.

For a multi-step edit, call `dashboard_edit_begin`, apply draft patches with the latest concurrency revision, then call `dashboard_edit_finish`. If its Doctor report fails, fix the listed components and finish again. After success call `dashboard_preview` once; do not open previews after intermediate patches, data attachment or queries. Existing connected pages refresh in place. Report source checks, installed version and actual host rendering separately.

Use `dashboard_view` with explicit component IDs for on-demand results; use full mode only for explicit complete exports or analysis. Never embed full dataset rows into a page to work around loading. Query `runtime_diagnostics` using a request ID when loading fails. Keep annotations independent of design restoration and preserve their context.

## Runtime MCP reference case

For local datasets that must remain outside the preview, read [local-data.md](references/local-data.md). Use `dataset_attach` to stream an operator-configured SQLite table into a versioned local dataset; bind components to that dataset. MCP returns local aggregate results and table pages by default. Use `dashboard_view` for unsaved reader filters, pagination, sorting and time-grain changes; `dataset_export` streams every matching row to a managed local CSV. Do not expand rows per chart, send full observations in component configs, or launch an HTTP service. Inspect data versions, row counts and sizes with `dashboard_data_inspect`.

This is the Dashboard generation track. Preserve the existing Gallery and `examples/` cases. For the local runtime, call `generation_examples` with `{"caseId":"executive-dashboard"}` or read `charts://examples/executive-dashboard`: it returns synthetic KPI/chart/table/filter declarations ready for an atomic patch. Read `charts://declarations` for chart contracts and `charts://contract` for mutation rules; create, patch with the latest revision, validate, then preview.

For Markdown-first analytical documents, use [analytical-reports](../analytical-reports/SKILL.md) and its approved academic master instead of composing a dashboard grid. Both tracks reuse existing chart definitions and source/data semantics.

## Route the task

- For one chart, provide a complete chart component JSON and run `scripts/generate_chart.py --config`; deliver the generated HTML component.
- For several candidate charts, use bounded batch mode to compare one focused shortlist.
- For a dashboard, run `scripts/dashboard_workspace.py` and use the workspace loop below.
- For an existing workspace, start with `inspect` and `validate`.
- For an existing HTML dashboard or frontend project, read [references/existing-project-checklist.md](references/existing-project-checklist.md) before mapping components and generating the target page.
- For CSV input, use `import-csv` as a draft, then review the inferred fields before adding charts.

Resolve the directory containing this `SKILL.md` once, then invoke its sibling scripts with `python3` as the execution interface.

In this source repository, `skills/executive-charts/` is the maintained implementation. Point local agent skill installations at that directory; do not maintain independent renderer copies in `.agents/skills/`. Verify the resolved script path before generating or diagnosing output.

For any task that creates, restyles, migrates, or embeds component HTML, read [references/component-html-generation.md](references/component-html-generation.md) before writing markup. It defines which layer generates each component, the stable DOM contract, and the completion gate.

## Dashboard workspace loop

1. Discover registered chart codes through the catalog command:

   ```bash
   python3 skills/executive-charts/scripts/generate_chart.py --list
   ```

   Continue when the selected code matches the business question.

   For a standalone chart, place the selected code, title, data, and full `presentation` contract in one JSON object, then generate it directly:

   ```bash
   python3 skills/executive-charts/scripts/generate_chart.py \
     --config ./regional-sales.chart.json --output ./dist/regional-sales.html
   ```

   The command validates the selected renderer contract, writes the HTML, and runs static Generated HTML inspection.

2. Create an empty workspace outside this skill directory:

   ```bash
   python3 skills/executive-charts/scripts/dashboard_workspace.py init ./board \
     --title "经营决策看板" --org "经营分析部"
   ```

   The workspace is ready when `inspect --json` reports the intended starting components and every reference resolves.

3. Add one evidence block at a time. Keep each KPI, chart, or table in its own small JSON file; keep filters in the dynamic array managed by the CLI.

   ```bash
   python3 skills/executive-charts/scripts/dashboard_workspace.py add kpi ./board revenue \
     --label "营业收入" --value 224 --unit "万元"
   python3 skills/executive-charts/scripts/dashboard_workspace.py add chart ./board regional-sales \
     --from ./regional-sales.chart.json
   ```

   Put the chart's `code`, title, unit, data, and complete `presentation` contract in `regional-sales.chart.json`. After each meaningful block, run `inspect --json`. Proceed when the current values and display semantics match the business requirement.

   When adding filters, first load table rows and declare each consumer's aggregation `binding` using [dashboard-workspace.md](references/dashboard-workspace.md#filter-bindings). Validation checks the referenced columns, consumers, and supported aggregation shape.

4. Validate early and build thin slices:

   ```bash
   python3 skills/executive-charts/scripts/dashboard_workspace.py validate ./board --strict --json
   python3 skills/executive-charts/scripts/dashboard_workspace.py build ./board \
     --output ./dist/board.html
   ```

   Every workspace build runs the static Generated HTML Inspector. Build after the first useful KPI or chart, then iterate. Generation is complete when strict validation and HTML inspection pass and every rendered block supports a stated management question.

   For migrations, create and review the Preservation Manifest from the baseline with `inventory-html`, then add `--manifest <existing-file>` to build. New dashboards do not need a preservation file.

For command shapes and component schemas, read [references/dashboard-workspace.md](references/dashboard-workspace.md) when assembling a dashboard.

## Decision rules

Before authoring or revising metric explanations, read [metric-definitions.md](references/metric-definitions.md). Business definitions must explain the business object, scope and meaning in plain Chinese; keep SQL and field expressions in calculation semantics. Define inclusion/exclusion rules only from confirmed evidence.

- **Evidence chain:** Choose each chart for a specific comparison, trend, composition, distribution, relationship, flow, attribution, or target question. Prefer the smallest set that closes the decision narrative.
- **Typed metrics:** Give every displayed number a semantic type, unit, scale and precision. Record source parsing outcomes explicitly.
- **KPI comparisons:** Keep numeric comparisons numeric until formatting; use metric bindings for units and precision. Legacy display strings must include their actual direction (`+12.4%`, `-1%`); never guess a sign from an unsigned string. Zero and missing values stay neutral. Run strict validation and check positive, negative, zero, missing and filtered states. Preserve signs during recomputation and label YoY/MoM explicitly.
- **Prototype data:** Start from the smallest explicit fixture that covers the required states and filter choices. Reuse one dataset for calculations and tables; do not expand every dimension combination or duplicate rows for each visualization. Label synthetic data. Inspect row counts and serialized response size before preview; never silently sample real business data or narrow required filter coverage.
- **Preview failures:** Separate JSON serialization, MCP transport, frontend decoding and rendering. Record the failing response and error position when available. A smaller response or a successful server JSON parse does not prove the preview is repaired; verify the target preview or report that verification is pending.
- **Dynamic filters:** Represent filters as an array of 0–N business dimensions. Use business field keys rather than industry aliases.
- **Explicit filter scope:** Declare every consumed data field with `--field` and every affected component with `--consumer`. Strict validation confirms this field-to-consumer mapping.
- **Stable component identity:** Component `id` is the runtime and DOM identity. Chart `code` selects the visual renderer and may repeat across independently identified instances.
- **Business-owned data:** Final workspaces contain explicit user/business data. Use catalog and preset data for structural preview.
- **Business-owned presentation:** Declare `presentation` metadata for axes, series, Tooltip values, units, complete `tableHeaders`, and renderer-specific domains, thresholds, or labels.
- **Bounded context:** Use `inspect --json` for summaries and edit one component file at a time.
- **Visual system:** Generate chart-code badges, explicit units, the restrained categorical palette, and 红涨绿跌 semantics: red (`positive`) for increases, green (`negative`) for decreases, and neither for status or series identity. Colors come from `scripts/core/palette.py`. Read [references/design_standards.md](references/design_standards.md) when changing visual behavior.

Select codes from [references/chart_catalog.json](references/chart_catalog.json). Use its metadata for chart choice and CLI-generated previews for visual comparison. Final component markup follows the component JSON → shared renderer → Runtime pipeline.

## Tooling boundary

Treat this skill directory as installed tooling during generation. Put workspaces, source data and generated outputs in the user's project. Improve shared component behavior in the registered schema, renderer, and Runtime source, then regenerate the target HTML.
