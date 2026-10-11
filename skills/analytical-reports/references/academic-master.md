# Academic report master

The authoritative, runnable case is `generation_examples(caseId="academic-report")`, also published as `charts://examples/academic-report`. Its Markdown lives at `dashboard_runtime/examples/academic-report.md`, reused by the CLI `init --demo --mode report`; this avoids a drifting screenshot-only template.

The master uses six explicitly synthetic rows, revenue aggregation and two declarative charts. It demonstrates:

1. Centered title, authored subtitle, abstract and keywords.
2. Data/methods section stating grain, interval, units and calculation method.
3. Monthly analysis: finding → prose figure reference → line chart → qualified interpretation.
4. Regional analysis: finding → bar chart → limits of the comparison.
5. Conclusion, limitations, provenance and calculation notes.

Use this structure and restrained typography as the visual baseline, while replacing all case-specific content. Never mechanically add an abstract or keywords to an arbitrary existing document. The report renderer hides chart card titles/actions and numbers figures; native bar/line charts receive a restrained grayscale treatment, while other chart families keep necessary category distinctions.

The existing Dashboard track's reference case is `generation_examples(caseId="executive-dashboard")`. It uses the same dataset and chart declarations with KPI cards, grid layouts, a scoped filter and table, demonstrating that the two outputs share a data model without sharing their presentation structure.
