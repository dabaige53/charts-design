# Academic report master

Read the runnable case with `generation_examples(caseId="academic-report")` or `charts://examples/academic-report`. Its Markdown lives at `dashboard_runtime/examples/academic-report.md`, reused by the CLI `init --demo --mode report`.

The master uses six explicitly synthetic rows, revenue aggregation and two declarative charts. It demonstrates:

1. Centered title, authored subtitle, abstract and keywords.
2. Data/methods section stating grain, interval, units and calculation method.
3. Monthly analysis: finding → prose figure reference → line chart → qualified interpretation.
4. Regional analysis: finding → bar chart → limits of the comparison.
5. Conclusion, limitations, provenance and calculation notes.

Use this structure and restrained typography as the visual baseline, replacing case-specific content and selecting sections for the reader's needs. The report renderer hides chart card titles/actions and numbers figures; native bar/line charts receive a restrained grayscale treatment, while other chart families keep necessary category distinctions.

The Dashboard case, `generation_examples(caseId="executive-dashboard")`, uses the same dataset and chart declarations with KPI cards, grid layouts, a scoped filter and table.
