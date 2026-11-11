---
name: analytical-reports
description: Generate evidence-based analytical reports as canonical Markdown with inline declarative charts, using the academic single-column reading master. Use for narrative reports, research-style analysis and text–figure–text documents; use executive-charts for dashboards.
---

# Analytical reports

Use the approved academic reading structure. Preserve Markdown as the portable canonical source. Reports use the same React chart components through the single-column Markdown adapter.

> **Current status (2026-11-10)**
> The shared React component library and MCP application use separate adapters and explicit build/package steps. Preview, JSON/CSV, HTML snapshots and static site exports use the new resources. Missing builds return `UI_UNAVAILABLE`. Current completion and host acceptance are tracked in package-root `docs/plans/ui-refactor-plan.md`.

## Discover before generating

1. Read `charts://examples` or call `generation_examples` with no arguments. The two tracks remain separate: `executive-dashboard` and `academic-report`.
2. Call `generation_examples` with `{"caseId":"academic-report"}` (equivalently read `charts://examples/academic-report`). This returns the actual master Markdown, synthetic data and a complete atomic declaration batch. The packaged source is `dashboard_runtime/examples/academic-report.md`.
3. Call `chart_declarations` for the compact index, then select a preset code such as `{"code":"c01"}` for its requirements and available example. The complete reference is `charts://declarations`; consult `chart_catalog` for visual discovery. Presets use explicit data, presentation and supported dataset/metric bindings. Custom ECharts and HTML/JavaScript declarations are described in [component rendering](../executive-charts/references/component-html-generation.md).
4. Read `charts://contract` for current mutation rules. All examples are synthetic. Never silently reuse their facts or label them as real user data.

## Compose the report

Follow [the master structure](references/academic-master.md): title, optional authored subtitle/abstract/keywords, methods and provenance, numbered analytical sections, inline figures surrounded by interpretation, conclusions and limitations. Include only sections the evidence warrants. Never invent an author, citation, methodology or causal claim.

Write ordinary Markdown. Register charts using `put_source`, `put_dataset`, `put_metric` and `put_component`. Put a top-level `chart` fence where each figure belongs:

```chart
{"componentId":"trend","caption":"Monthly revenue","source":"Source: reviewed sales snapshot; revenue summed by month, in CNY."}
```

Follow with prose, then another chart fence as needed. Reference figures using `[图](#fig-trend)`. Numbers are assigned by source order; repeated references to one component target its first figure. Caption and source are plain strings, limited to 500 and 1000 Unicode characters respectively. Ordinary code fences stay code. No HTML or JavaScript execution is allowed.

## Notes and appendix

Use standard Markdown named notes for metric definitions, provenance or key qualifications: `收入[^revenue]`, then `[^revenue]: 收入按同一观察范围求和，单位万元。` Definitions may contain normal Markdown; references are numbered and link to the final 注释 section with return links. Repeated references reuse the note number. This is an honest endnote implementation, not physical per-page footnotes. Undefined notes remain literal text: resolve them before delivery. Use a normal `## 附录：指标口径` section for longer formulas, schema descriptions or review checklists. Keep captions/source fields plain text, placing note references in nearby prose.

## MCP generation loop

Read [the shared MCP delivery workflow](../executive-charts/references/mcp-delivery.md) before creating, editing, replacing data or diagnosing loading. Use its project storage, edit-batch and one-preview workflow for reports too.

- Pass the absolute asset directory as `projectRoot` on every project call (on the self-hosted server, the project name). Create an empty artifact with `dashboard_create`, or inspect the existing document and referenced component IDs. Begin an edit batch with the latest revision. Preserve accepted Markdown, captions, notes and sources outside the requested change.
- Adapt the case's declarations: replace sources, data, metrics, chart IDs, captions and every numeric statement. Apply declarations, `set_report_markdown` and `set_view_mode`=`report` together so references resolve after the batch.
- Finish the edit batch and resolve Doctor errors. Re-read with `dashboard_get` after a revision conflict.
- Finish the edit batch, verify Markdown references and metric definitions, then open the saved report with `dashboard_preview`. Host display acceptance is separate from protocol and build checks.
- Data or filter changes update charts, not authored claims. Recompute each affected numeric statement against the same data version and filter scope, or explicitly keep the narrative tied to its original snapshot. Record unresolved statements rather than reusing stale values.

Dashboard layouts and report source coexist. Route dashboard-first requests to `../executive-charts/SKILL.md`; retain their examples and interactive controls.

## Optional Seaborn statistical figures

For distributions and raw-observation comparisons, read the statistical section of `charts://declarations`. With `.[statistics]` installed, declare `kind=statistical` with histogram, boxplot or regression `plot`, typed dataset, and explicit `analysis.definition`/`unit`. These do not consume aggregated metrics. In the Markdown source, use standard chart fences; statistical calculations produce static SVG/PNG artifacts through the statistical renderer. Do not add an internal chart title in the paper. No interactive filter targets, confidence-interval claims or causal interpretation; see `docs/implementation/seaborn-backend.md`.
