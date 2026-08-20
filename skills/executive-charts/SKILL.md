---
name: executive-charts
description: Build executive business charts and dashboards with the charts-design CLI. Use for chart selection, KPI cards, filters, pivot tables, or dashboard assembly from business data; prefer incremental workspace components and bounded inspection over generated HTML or monolithic configuration.
---

# Executive Charts

Turn business evidence into a restrained executive dashboard. Use the CLI as the command layer and compose the result from small, reviewable building blocks.

## Route the task

- For one chart, use `charts-design chart` and deliver the generated component.
- For several candidate charts, use `charts-design batch` only to compare a bounded shortlist.
- For a dashboard, use the workspace loop below.
- For an existing workspace, start with `dashboard inspect` and `dashboard validate`.
- For CSV input, use `dashboard import-csv` as a draft, then review the inferred fields before adding charts.

Run `npx charts-design ...` when the command is not installed on `PATH`.

## Dashboard workspace loop

1. Verify the tool and discover chart codes:

   ```bash
   npx charts-design doctor --json
   npx charts-design list
   ```

   Continue when the runtime is ready and the selected code matches the business question.

2. Create an empty workspace outside this skill directory:

   ```bash
   npx charts-design dashboard init ./board --title "经营决策看板" --org "经营分析部"
   ```

   The workspace is ready when `dashboard inspect --json` reports zero or the intended starting components and no missing files.

3. Add one evidence block at a time. Keep each KPI, chart, or table in its own small JSON file; keep filters in the dynamic array managed by the CLI.

   ```bash
   npx charts-design dashboard add kpi ./board revenue \
     --label "营业收入" --value 224 --unit "万元"
   npx charts-design dashboard add chart ./board regional-sales \
     --code c01 --title "各区域营业收入" --unit "万元" \
     --data-file ./regional-sales.json
   ```

   After each meaningful block, run `dashboard inspect --json`. Add the next block only when the current title, code, data and unit are correct.

4. Validate early and build thin slices:

   ```bash
   npx charts-design dashboard validate ./board --strict --json
   npx charts-design dashboard build ./board --output ./dist/board.html
   ```

   Build after the first useful KPI or chart, then iterate. A dashboard is complete when strict validation passes and every rendered block supports a stated management question.

For command shapes and component schemas, read [references/dashboard-workspace.md](references/dashboard-workspace.md) when assembling a dashboard.

## Decision rules

- **Evidence chain:** Choose each chart for a specific comparison, trend, composition, distribution, relationship, flow, attribution, or target question. Prefer the smallest set that closes the decision narrative.
- **Typed metrics:** Give every displayed number a semantic type, unit, scale and precision. Preserve parse failures as errors or missing values instead of turning them into zero.
- **Dynamic filters:** Represent filters as an array of 0–N business dimensions. Use business field keys rather than industry aliases.
- **Business-owned data:** Final workspaces contain explicit user/business data. Catalog and preset data are for structural preview, not final evidence.
- **Bounded context:** Use `inspect --json` for summaries and edit one component file at a time. Generated HTML and resolved dashboard configuration are build artifacts.
- **Visual system:** Keep chart-code badges, explicit units, the restrained categorical palette, and positive/negative/attention semantics. Read [references/design_standards.md](references/design_standards.md) only when changing visual behavior.

Select codes from [references/chart_catalog.json](references/chart_catalog.json). Use its metadata for chart choice; use CLI-generated previews for visual comparison. Treat `examples/` as a human showcase and open a specific example only when the user explicitly asks to compare against it.

## Tooling boundary

Treat this skill directory as installed tooling during dashboard work. Put workspaces, source data and generated outputs in the user's project. Modify skill scripts or templates only when the user explicitly asks to improve the tool itself.
