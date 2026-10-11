---
name: analytical-reports
description: Generate evidence-based analytical reports as canonical Markdown with inline declarative charts, using the academic single-column reading master. Use for narrative reports, research-style analysis and text–figure–text documents; use executive-charts for dashboards.
---

# Analytical reports

Use the approved academic reading master, not a dashboard grid or an always-open split editor. Preserve Markdown as the portable source. The reader sees a quiet, single-column paper; Edit opens authoring separately.

## Discover before generating

1. Read `charts://examples` or call `generation_examples` with no arguments. The two tracks remain separate: `executive-dashboard` and `academic-report`.
2. Call `generation_examples` with `{"caseId":"academic-report"}` (equivalently read `charts://examples/academic-report`). This returns the actual master Markdown, synthetic data and a complete atomic declaration batch. The packaged source is `dashboard_runtime/examples/academic-report.md`.
3. Call `chart_declarations` for the compact index, then select `{"chartType":"line"}` or `{"code":"c01"}` for requirements and a working declaration batch. The complete reference is `charts://declarations`; consult `chart_catalog` for visual discovery. Prefer native dataset-bound charts when they answer the question. Original chart families can be embedded too, but require explicit data and presentation contracts; do not guess their shape.
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

- Create an empty artifact with `dashboard_create`, or read the existing one with `dashboard_get`.
- Adapt the case's `operations`: replace sources, data, metrics, chart IDs, captions and every numeric statement. Do not overwrite an existing document wholesale just to change a paragraph.
- Submit one `dashboard_patch` with the latest `expectedRevision`. Include declarations, `set_report_markdown` and `set_view_mode`=`report` in the same atomic batch. References are validated after the whole batch.
- Run `dashboard_validate`, then `dashboard_preview`. A supported MCP Apps host renders the shared UI; a non-UI host receives the canonical document and can use local CLI export/serve.
- Inspect actual rendering: prose–figure–prose order, units/legends, caption numbering, source notes, figure links, and no edit controls in reading mode. Check save/reload when authoring.
- Re-read after a revision conflict rather than blindly retrying. Changing filters/data does not rewrite narrative: recompute and review claims explicitly.

Dashboard layouts and report source coexist. Route dashboard-first requests to `../executive-charts/SKILL.md`; retain their examples and interactive controls.

## Optional Seaborn statistical figures

For distributions and raw-observation comparisons, read the statistical section of `charts://declarations`. With `.[statistics]` installed, declare `kind=statistical` with histogram, boxplot or regression `plot`, typed dataset, and explicit `analysis.definition`/`unit`. These do not consume aggregated metrics. Use the same Markdown chart fences; previews and offline HTML embed static SVG with source, grain and missing-row captions. `statistical_render` also returns PNG. Do not add an internal chart title in the paper. No interactive filter targets, confidence-interval claims or causal interpretation; see `docs/seaborn-backend.md`.
