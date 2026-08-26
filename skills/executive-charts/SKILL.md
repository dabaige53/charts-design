---
name: executive-charts
description: Build executive business charts and dashboards with the bundled Python scripts. Use for chart selection, KPI cards, filters, pivot tables, or dashboard assembly from business data; prefer incremental workspace components and bounded inspection over generated HTML or monolithic configuration.
---

# Executive Charts

Turn business evidence into a restrained executive dashboard. Run the scripts bundled beside this file and compose the result from small, reviewable building blocks.

## Route the task

- For one chart, run `scripts/generate_chart.py` and deliver the generated component.
- For several candidate charts, use its bounded batch mode only to compare a shortlist.
- For a dashboard, run `scripts/dashboard_workspace.py` and use the workspace loop below.
- For an existing workspace, start with `inspect` and `validate`.
- For an existing HTML dashboard, inventory its DOM ids, visible text, assets and component regions before changing styles. Record the non-negotiable items in a Preservation Manifest, then use `compare-html` after migration.
- For CSV input, use `import-csv` as a draft, then review the inferred fields before adding charts.

Resolve the directory containing this `SKILL.md` once, then invoke its sibling scripts with `python3`. The bundled scripts are the execution interface; package-manager wrappers are unnecessary.

## Dashboard workspace loop

1. Discover chart codes without loading generator source or example HTML:

   ```bash
   python3 skills/executive-charts/scripts/generate_chart.py --list
   ```

   Continue when the selected code matches the business question.

2. Create an empty workspace outside this skill directory:

   ```bash
   python3 skills/executive-charts/scripts/dashboard_workspace.py init ./board \
     --title "经营决策看板" --org "经营分析部"
   ```

   The workspace is ready when `inspect --json` reports zero or the intended starting components and no missing files.

3. Add one evidence block at a time. Keep each KPI, chart, or table in its own small JSON file; keep filters in the dynamic array managed by the CLI.

   ```bash
   python3 skills/executive-charts/scripts/dashboard_workspace.py add kpi ./board revenue \
     --label "营业收入" --value 224 --unit "万元"
   python3 skills/executive-charts/scripts/dashboard_workspace.py add chart ./board regional-sales \
     --code c01 --title "各区域营业收入" --unit "万元" \
     --data-file ./regional-sales.json
   python3 skills/executive-charts/scripts/dashboard_workspace.py add filter ./board region \
     --label "大区" --option east=华东 --field region \
     --consumer revenue --consumer regional-sales
   ```

   After each meaningful block, run `inspect --json`. Add the next block only when the current title, code, data and unit are correct.

4. Validate early and build thin slices:

   ```bash
   python3 skills/executive-charts/scripts/dashboard_workspace.py validate ./board --strict --json
   python3 skills/executive-charts/scripts/dashboard_workspace.py build ./board \
     --output ./dist/board.html --manifest ./preservation.json
   ```

   Every build runs the static Generated HTML Inspector. Build after the first useful KPI or chart, then iterate. A dashboard is complete when strict validation and HTML inspection pass and every rendered block supports a stated management question.

## Existing HTML migration loop

1. Run `inventory-html <before.html> --output preservation.json --json`, edit its generated baseline down to the business-critical ids, text and assets, then run `inspect-html <before.html> --strict --manifest preservation.json --json`.
2. Map each existing region to a supported component contract. Preserve its business content and stable id; change presentation through shared tokens, the card shell and runtime capabilities rather than copying showcase markup.
3. Generate or update the candidate HTML, then run both `inspect-html <after.html> --manifest preservation.json --strict --json` and `compare-html <before.html> <after.html> --manifest preservation.json --json`.
4. Stop on any missing id, text, asset, broken reference or duplicate id. Run `inspect-html <after.html> --runtime --strict --json` when Playwright and Chrome are available to verify rendered component DOM, card actions, runtime errors and cleanup.

For command shapes and component schemas, read [references/dashboard-workspace.md](references/dashboard-workspace.md) when assembling a dashboard.

## Decision rules

- **Evidence chain:** Choose each chart for a specific comparison, trend, composition, distribution, relationship, flow, attribution, or target question. Prefer the smallest set that closes the decision narrative.
- **Typed metrics:** Give every displayed number a semantic type, unit, scale and precision. Preserve parse failures as errors or missing values instead of turning them into zero.
- **Dynamic filters:** Represent filters as an array of 0–N business dimensions. Use business field keys rather than industry aliases.
- **Explicit filter scope:** Declare every consumed data field with `--field` and every affected component with `--consumer`. Strict validation rejects filters that rely on whole-row guessing.
- **Stable component identity:** Component `id` is the runtime and DOM identity. Chart `code` selects a renderer only; repeated uses of one code remain separate instances.
- **Business-owned data:** Final workspaces contain explicit user/business data. Catalog and preset data are for structural preview, not final evidence.
- **Bounded context:** Use `inspect --json` for summaries and edit one component file at a time. Generated HTML and resolved dashboard configuration are build artifacts.
- **Visual system:** Keep chart-code badges, explicit units, the restrained categorical palette, and positive/negative/attention semantics. Read [references/design_standards.md](references/design_standards.md) only when changing visual behavior.

Select codes from [references/chart_catalog.json](references/chart_catalog.json). Use its metadata for chart choice; use CLI-generated previews for visual comparison. Treat `examples/` as a human showcase and open a specific example only when the user explicitly asks to compare against it.

## Tooling boundary

Treat this skill directory as installed tooling during dashboard work. Put workspaces, source data and generated outputs in the user's project. Modify skill scripts or templates only when the user explicitly asks to improve the tool itself.
