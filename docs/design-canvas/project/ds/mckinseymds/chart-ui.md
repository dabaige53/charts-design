# 图表 UI：保留与重构边界

图表本体的视觉和交互是本次重点。保留数据色、坐标轴、网格线、图例、数据标签、Tooltip、线条与柱形几何、复杂标记，以及图表专用的缩放和状态表现。

## 已单独保存

| 内容 | 位置 |
| --- | --- |
| 40 个图表原始定义 | `assets/ChartUI/chart-builders.json`、`assets/ChartUI/definitions/` |
| 旧项目图表颜色 | `assets/ChartUI/project-chart-palette.json` |
| 坐标、网格、图例、Tooltip 与标签 | 图表定义内各自的 ECharts 配置 |
| 指标卡主体与微图 | `assets/ChartUI/original-dashboard-engine.js.txt` 和 KPI 样式源文 |
| 缩放、自适应、配置覆盖、图表数据编码 | `assets/ChartUI/source/dashboard_runtime/web/` 和原 chart_interactions 源文 |
| 原视觉比较案例 | `assets/ChartUI/source/examples/` |
| 来源提交与文件清单 | `assets/ChartUI/preservation.json` |

## 两套颜色依据分开

- PDF 的 Functional Colors 是 11 个数据色，保留在 `tokens.json` 的 `color-data-*`。PDF 没有规定完整的分类轮用顺序、发散两极或业务状态色映射。
- 旧项目配色单独保存在 `project-chart-palette.json`；它是项目既有设计，不是 PDF 原始配色。迁移时明确选择与映射，不混成一套“官方值”。

## 迁移要求

先保留每个图表的信息结构、比例编码、特殊标记、单位、Tooltip 字段和交互，再调整配色。新框架可以替换图表外的按钮、菜单、工具栏和页面容器。不要通过恢复整个旧 UI 来保留图表。

本次保存了 40 个图表定义和 30 份来源文件，取自提交 `aefb7e857663a42a6bb426f8b5ba3eca48cb950e`。全部源文在独立目录中作为参考文本保存，主项目工作区未改动。本次未执行浏览器渲染或逐图视觉验收。
