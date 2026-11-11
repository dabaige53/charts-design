# 组件渲染与交付

组件通过声明进入共享 React Runtime。`component.id` 标识实例，`config.code` 标识图形；同一图形可创建多个实例。业务数据和渲染实现分别维护。

## 选择输出

- 交互看板：用 MCP 创建来源、数据集、指标和组件，按 [交付流程](mcp-delivery.md) 完成编辑批次与预览。
- CLI 资产：用 [工作区命令](dashboard-workspace.md) 管理 JSON，并执行 `charts-design dashboard validate ./board --strict --json`。
- 独立网页：使用 Runtime 的 HTML 或静态站点导出；导出能力见 [Runtime 说明](../../../docs/implementation/dashboard-runtime.md)。
- Markdown 分析报告：使用 [analytical-reports](../../analytical-reports/SKILL.md)，引用保存的组件。

## 渲染方式

图表声明使用 `kind: "legacy"`、`family: "chart"`：

| 方式 | 配置 | 数据与交互 |
| --- | --- | --- |
| 预设 | `code`、`data`、`presentation` | 使用公开声明支持的数据绑定、筛选与粒度 |
| 自由 ECharts | `renderer: "echarts"`、自定义 `code`、完整 `echarts` 对象 | 显式快照；由作者控制系列、坐标和图形 |
| HTML/JavaScript | `renderer: "html"`、自定义 `code`、`html`，可选 `data` | 隔离 iframe 执行脚本；`window.chartData` 提供数据，可载入浏览器可执行的 React 和 HTTPS 库 |

自定义方式可声明 `table: {headers, rows}` 来提供转表与 CSV。HTML 组件的内部交互由脚本实现。完整配置与执行边界见 [自由渲染](../../../docs/implementation/echarts-options.md)。

## 共享外壳

标题、操作、详情和全屏由共享组件维护。仅显示当前组件实现的动作。KPI 内容按 [指标卡选型](kpi-cards.md) 声明，禁止描述；解释内容按 [指标定义](metric-definitions.md) 提供。

筛选消费者、系列和表格列使用稳定标识。更新保持实例和选择状态；卸载清理监听器及图表。图表、转表和 CSV 使用同一份已解析数据。

## 构建与检查

前端源码位于 `runtime-ui/src`。类型检查、构建和测试默认由 GitHub CI 执行。仅在需要本地预览或安装时运行 `npm run ui:prepare`，复用与源码相符的产物，否则构建一次并打包 Runtime。设计系统资源通过 `npm run ui:package:design` 单独更新。

交付前检查声明校验、数据单位、筛选范围和所需动作；测试范围遵循 [项目测试规则](../../../docs/operations/testing.md)。
