---
name: executive-charts
description: Build reusable executive chart, KPI, filter, table, and dashboard components from business data, then generate and verify final HTML with the bundled Python scripts. Use for new dashboards, component embedding, or upgrades of existing HTML/frontend projects.
---

# Executive Charts

Turn business evidence into a restrained executive dashboard. Run the scripts bundled beside this file and compose the result from small, reviewable building blocks.

The goal is a reusable business-component generation system whose deliverable is working HTML or an explicit framework Adapter. Use the Gallery and `examples/` for discovery and visual comparison. Generate final markup from explicit business data through the registered component pipeline.

## Runtime MCP reference case

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

   The command validates the selected renderer contract, writes the HTML, and runs static plus browser-backed Generated HTML inspection.

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
   python3 skills/executive-charts/scripts/dashboard_workspace.py add filter ./board region \
     --label "大区" --option east=华东 --field region \
     --consumer revenue --consumer regional-sales
   ```

   Put the chart's `code`, title, unit, data, and complete `presentation` contract in `regional-sales.chart.json`. After each meaningful block, run `inspect --json`. Proceed when the current values and display semantics match the business requirement.

4. Validate early and build thin slices:

   ```bash
   python3 skills/executive-charts/scripts/dashboard_workspace.py validate ./board --strict --json
   python3 skills/executive-charts/scripts/dashboard_workspace.py build ./board \
     --output ./dist/board.html --manifest ./preservation.json
   ```

   Every workspace build runs the static Generated HTML Inspector. Build after the first useful KPI or chart, then iterate. Generation is complete when strict validation and HTML inspection pass and every rendered block supports a stated management question.

For command shapes and component schemas, read [references/dashboard-workspace.md](references/dashboard-workspace.md) when assembling a dashboard.

## Decision rules

- **Evidence chain:** Choose each chart for a specific comparison, trend, composition, distribution, relationship, flow, attribution, or target question. Prefer the smallest set that closes the decision narrative.
- **Typed metrics:** Give every displayed number a semantic type, unit, scale and precision. Record source parsing outcomes explicitly.
- **Dynamic filters:** Represent filters as an array of 0–N business dimensions. Use business field keys rather than industry aliases.
- **Explicit filter scope:** Declare every consumed data field with `--field` and every affected component with `--consumer`. Strict validation confirms this field-to-consumer mapping.
- **Stable component identity:** Component `id` is the runtime and DOM identity. Chart `code` selects the visual renderer and may repeat across independently identified instances.
- **Business-owned data:** Final workspaces contain explicit user/business data. Use catalog and preset data for structural preview.
- **Business-owned presentation:** Declare `presentation` metadata for axes, series, Tooltip values, units, complete `tableHeaders`, and renderer-specific domains, thresholds, or labels.
- **Bounded context:** Use `inspect --json` for summaries and edit one component file at a time.
- **Visual system:** Generate chart-code badges, explicit units, the restrained categorical palette, and positive/negative/attention semantics. Read [references/design_standards.md](references/design_standards.md) when changing visual behavior.

Select codes from [references/chart_catalog.json](references/chart_catalog.json). Use its metadata for chart choice and CLI-generated previews for visual comparison. Final component markup follows the component JSON → shared renderer → Runtime pipeline.

## Tooling boundary

Treat this skill directory as installed tooling during generation. Put workspaces, source data and generated outputs in the user's project. Improve shared component behavior in the registered schema, renderer, and Runtime source, then regenerate the target HTML.
