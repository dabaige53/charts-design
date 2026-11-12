---
name: analytical-reports
description: Create, revise and refresh evidence-based analytical reports as Markdown with inline declarative charts in Charts Design. Use for narrative business reports, research-style analysis and text–figure–text documents with sources and calculation notes. For interactive KPI dashboards, use executive-charts.
---

# Analytical Reports

Write a report that answers the user's question with traceable data and figures. Save Markdown as the report source; the shared React renderer presents it in the academic single-column layout.

## Read the project and evidence

Read [shared MCP delivery](../executive-charts/references/mcp-delivery.md) for project routing and the editing flow. On an existing report, read `dashboard_get`, its Markdown, referenced components and data before changing it.

Use `cos-v1` for cloud projects by default. Follow shared delivery's storage check and migration flow before importing data; verify the saved editor document's format before delivery.

Inspect the source's grain, time range, units and calculations. Register sources, datasets and metrics so figures and prose use the same definitions. Read [metric definitions](../executive-charts/references/metric-definitions.md) when defining calculations.

For a new report, `generation_examples` with `{"caseId":"academic-report"}` returns the master Markdown and a complete synthetic declaration batch. Read [the academic master](references/academic-master.md) for its reading structure. Replace case-specific sources, data, IDs and claims with the current report's evidence.

Read `charts://contract` for operations and `chart_declarations` for component fields. Query selected presets by `code`; [component rendering](../executive-charts/references/component-html-generation.md) covers native ECharts and custom HTML/JavaScript.

## Compose the report

Lead with the main finding, then develop the evidence in reading order. Include the title, relevant context and methods, analytical sections, figures and conclusions. Add an abstract, keywords, appendix or limitations when they help this report's reader. Authors, citations and causal claims require supporting evidence.

Use ordinary Markdown. The renderer numbers second-level sections and figures. Place a top-level `chart` fence where each saved component belongs:

```chart
{"componentId":"trend","caption":"Monthly revenue","source":"Source: reviewed sales snapshot; revenue summed by month, in CNY."}
```

Introduce the finding, reference `[图](#fig-trend)`, insert the figure, then explain what the comparison means. Repeated references to a component target its first figure. Caption and source are plain strings, limited to 500 and 1000 Unicode characters respectively.

Use the reader's language and [data formatting](../executive-charts/references/data_formatting_standards.md). Keep narrative in Markdown and metric definitions in the component detail view. KPI cards follow the [KPI content rules](../executive-charts/references/kpi-cards.md).

## Notes and appendix

Use named notes for definitions, provenance or qualifications:

```markdown
收入[^revenue]

[^revenue]: 收入按同一观察范围求和，单位万元。
```

The renderer numbers notes in a final 注释 section with links back to the text. Define every reference; repeated references share a number. Put note references in prose beside figures. Longer formulas and schema descriptions can use a normal `## 附录：指标口径` section.

## Write and deliver

1. Create the report with `dashboard_create` or read its latest revision with `dashboard_get`.
2. Begin an edit batch. Apply source, dataset, metric and component declarations with `set_report_markdown` and `set_view_mode`=`report`. Components and their Markdown references resolve within the batch. Save structure diagrams using the [component diagram instructions](../executive-charts/SKILL.md#save-structure-diagrams).
3. Inspect computed figure values with `dashboard_view`. Check numeric claims against the same dataset version and filter scope, then check figure references, notes, units and sources.
4. Finish the batch, fix reported Doctor errors and open the saved report with `dashboard_preview`.
5. Deliver the report or requested export with its main finding, data provenance and concrete unresolved issues.

## Revise or refresh

Preserve accepted Markdown, captions, notes, sources and stable component IDs outside the requested change. For refreshed data, recompute affected statements and figures together. If a report intentionally describes a fixed snapshot, retain and identify that snapshot.

Use `dashboard_annotations` to find the referenced component and comment context. Check a questioned number against the source before changing it. Historical versions and export routes follow the shared delivery workflow.

## Statistical figures

For distributions and raw-observation comparisons, read the statistical declarations and [statistical backend](../../docs/implementation/seaborn-backend.md). With statistics dependencies installed, use `kind: "statistical"`, a histogram, boxplot or regression `plot`, a typed dataset, and explicit `analysis.definition` and `unit`.

These figures consume raw observations and render static SVG/PNG. Embed them with the same chart fences. Use the report caption as the figure title.
