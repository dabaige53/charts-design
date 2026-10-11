# Optional statistical charts (Seaborn)

Install `python -m pip install '.[statistics]'`. The ECharts dashboard remains the
interactive backend. Statistical components produce headless SVG or PNG and can
be embedded in the same canonical Markdown report using a `chart` fence.
Python 3.10+ is supported; dependency ranges are in `pyproject.toml`.

## Declare, validate, preview

Use the same MCP server, `dashboard_create`, `dashboard_patch`,
`dashboard_validate`, and `dashboard_preview`. `chart_declarations` and
`charts://declarations` expose the statistical contract alongside native charts.
First supply a source and typed dataset as usual. Then add:

```json
{"op":"put_component","id":"distribution","value":{
  "kind":"statistical","title":"Measurement distribution",
  "datasetId":"observations",
  "plot":{"type":"histogram","x":"value","bins":20},
  "analysis":{"definition":"One row per observed item; value is its measured quantity.","unit":"ms"}
}}
```

Use `plot={"type":"boxplot","x":"group","y":"value"}` for categorical
group distributions, or `plot={"type":"regression","x":"elapsed","y":"value"}`
for scatter with an ordinary least-squares line. Regression does not compute a
confidence interval or establish causation. No aggregated metric is substituted
for a raw observation. `analysis.definition` must state grain and measurement;
`analysis.unit` labels histogram x or boxplot/regression y. Put regression x units
in its dataset field label.

````markdown
## Distribution

```chart
{"componentId":"distribution","caption":"Observed distribution","source":"Describe the actual supplied source"}
```
````

`statistical_render({dashboardId,componentId,format:"svg"|"png"})` returns a
base64 data URI, caption and provenance. SVG is embedded in normal preview and
self-contained HTML export; PNG supports other document workflows. Canonical
JSON stores only data and declarations. Artifacts are derived and cached by the
complete rendering input, so edits never retain stale images. Source metadata,
snapshot time, row counts, specification/data SHA-256 and backend versions are
returned. Source metadata is supplied evidence, never certification.

## Deliberate limits

- Histogram: numeric x, 1–100 equal-width bins, counts, no KDE.
- Boxplot: string/boolean x, numeric y, at most 20 groups, 1.5×IQR whiskers and outliers.
- Regression: numeric x/y, at least 3 complete rows and 2 distinct x values, no bootstrap.
- Up to 5,000 raw rows per chart and 10 statistical components per document.
- Null/missing selected values are omitted with an explicit count; other declared data types are validated.
- Numeric magnitudes up to 1e12 and category labels up to 100 characters.
- No arbitrary Python, file paths, URLs, unbounded keyword arguments or external datasets.
- No interactive filter targets in this first version. Change the reviewed dataset and rerender.
- Optional dependency absence is shown as an actionable rendering error; ECharts remains usable.
- CJK labels use Noto Serif CJK SC when installed; install a suitable font for Chinese text.

Official references: [Seaborn installation](https://seaborn.pydata.org/installing.html),
[histplot](https://seaborn.pydata.org/generated/seaborn.histplot.html),
[boxplot](https://seaborn.pydata.org/generated/seaborn.boxplot.html),
[regplot](https://seaborn.pydata.org/generated/seaborn.regplot.html),
[Matplotlib Agg](https://matplotlib.org/stable/api/backend_agg_api.html).
