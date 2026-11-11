# Workspace 资产脚本

本目录负责业务配置的创建、导入、检查和校验。页面通过共享 React Runtime 渲染。

```bash
bun bin/python-runtime.js skills/executive-charts/scripts/dashboard_workspace.py init ./sales-board --title "销售经营看板"
bun bin/python-runtime.js skills/executive-charts/scripts/dashboard_workspace.py add chart ./sales-board regional-sales \
  --from skills/executive-charts/references/quickstart/regional-sales.chart.json
bun bin/python-runtime.js skills/executive-charts/scripts/dashboard_workspace.py inspect ./sales-board --json
bun bin/python-runtime.js skills/executive-charts/scripts/dashboard_workspace.py validate ./sales-board --strict --json
bun bin/python-runtime.js skills/executive-charts/scripts/dashboard_workspace.py import-csv ./csv-board --csv ./data.csv
```

`meta set`、`add kpi`、`add filter`、`table set` 维护独立 JSON 资产。

`core/component_schemas.py` 保留图表与 KPI 声明校验，`core/filter_bindings.py` 保留筛选绑定校验。`core/chart_catalog.py` 的 `CHART_COMPONENTS` 是数据校验测试使用的 40 种图表合成数据，不包含 JavaScript 函数、配色或图形样式。`core/explanations.py` 保留指标定义。CSV 推断只导入筛选项、表格和建议图表数量；KPI 与图表由作者显式添加，不自动编排或补写比较值。
