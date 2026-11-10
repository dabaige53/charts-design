# Workspace 资产脚本

原生 HTML 生成器、模板和交互代码已移除，供 React 重构使用。本目录保留业务配置的创建、导入、检查和校验能力。

```bash
python3 skills/executive-charts/scripts/dashboard_workspace.py init ./sales-board --title "销售经营看板"
python3 skills/executive-charts/scripts/dashboard_workspace.py add chart ./sales-board regional-sales \
  --from skills/executive-charts/references/quickstart/regional-sales.chart.json
python3 skills/executive-charts/scripts/dashboard_workspace.py inspect ./sales-board --json
python3 skills/executive-charts/scripts/dashboard_workspace.py validate ./sales-board --strict --json
python3 skills/executive-charts/scripts/dashboard_workspace.py import-csv ./csv-board --csv ./data.csv
```

`meta set`、`add kpi`、`add filter`、`table set` 继续维护独立 JSON 资产。`build` 返回 `HTML_GENERATOR_REMOVED` 并以状态码 2 退出，不生成文件。旧 HTML 检查、比较和清单命令已移除。

`core/component_schemas.py` 保留图表与 KPI 声明校验，`core/filter_bindings.py` 保留筛选绑定校验。`core/chart_catalog.py` 的 `CHART_COMPONENTS` 是数据校验测试使用的 40 种图表合成数据，不包含 JavaScript 函数、配色或图形样式。`core/explanations.py` 保留指标定义。CSV 推断只导入筛选项、表格和建议图表数量；KPI 与图表由作者显式添加，不自动编排或补写比较值。
