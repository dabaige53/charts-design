# charts-design 文档

本项目提供经营看板与分析报告的共享组件、生成脚本和本地 Runtime。使用者通过 CLI 或 MCP 声明数据、指标和组件，产出可保存的看板、Markdown 报告、离线快照或独立网页部署包。

## 开始使用

快速开始见根目录 [README](../README.md)。选择生成方式时读 [生成路径](generation-tracks.md)；开发与运行步骤见 [Runtime 说明](dashboard-runtime.md)。Agent 按根目录 [AGENTS.md](../AGENTS.md) 的任务条件读取文档。

## 现行规范

| 文档 | 用途与查阅时机 | 更新时机 |
| --- | --- | --- |
| [文件管理](agent/file-management.md) | 新增、移动或清理文件前，确定位置和维护入口 | 目录职责或保留规则变化 |
| [标题区与绑定](icon-header-and-bindings.md) | 修改 Runtime 操作区、图标或绑定前，确认适用规则 | 界面约定或绑定范围变化 |
| [设计规范](../skills/executive-charts/references/design_standards.md) | 修改组件配色、排版、几何或表格时查阅 | 设计要求变化 |
| [指标定义](../skills/executive-charts/references/metric-definitions.md) | 撰写业务说明与统计口径时查阅 | 指标说明要求变化 |
| [MCP 共享交付流程](../skills/executive-charts/references/mcp-delivery.md) | 创建、编辑、替换数据或诊断 MCP 页面时查阅 | 交付流程变化 |
| [指标卡选型](../skills/executive-charts/references/kpi-cards.md) 与 [布局模板](../skills/executive-charts/references/layout_templates.md) | 选择指标卡形态与看板构图时查阅 | 卡片类型、模板或选型规则变化 |

## 当前实现与操作

| 文档 | 用途与查阅时机 | 更新时机 |
| --- | --- | --- |
| [Runtime 说明](dashboard-runtime.md) | 运行 CLI、本地网页、MCP 或编辑报告时查阅 | 运行方式、接口或兼容行为变化 |
| [生成路径](generation-tracks.md) | 从空白创建 Dashboard 或分析报告时查阅 | 案例、声明或编辑流程变化 |
| [项目资产与加载](project-runtime.md) | 处理多项目、历史、数据存储和渐进加载时查阅 | 存储、路由或加载行为变化 |
| [原版组件保真](original-component-fidelity.md) | 修改原组件提取、导入或构建时查阅 | 迁移与组件保留行为变化 |
| [动态编码](dynamic-encoding.md) | 声明动态系列、散点、比较或下钻时查阅 | 编码能力或绑定规则变化 |
| [ECharts 配置覆盖](echarts-options.md) | 调整原生显示配置时查阅 | 合并或覆盖行为变化 |
| [Seaborn 后端](seaborn-backend.md) | 使用原始观测生成统计图时查阅 | 统计声明、依赖或限制变化 |
| [位置引用与批注](annotation-composer.md) | 使用或修改位置批注、对话附件时查阅 | 宿主能力与批注行为变化 |
| [本地 MCP 更新](local-mcp-update.md) | 更新安装包、判断重连或重开页面时查阅 | 更新入口和进程行为变化 |
| [传输与诊断](mcp-transport-diagnostics.md) | 排查大响应、旧预览或日志时查阅 | 传输与诊断行为变化 |
| [静态部署包](static-deployment.md) | 导出、重建或发布独立网页时查阅；末节为当次验收 | 导出与重建方式变化 |
| [自托管服务器](self-hosted-server.md) | 部署远程 MCP、网页预览与分享链接时查阅；末节为当次验收 | 入口、鉴权、项目隔离或链接权限变化 |

## 历史记录与证据

以下记录保存当时的现象、计划和结果。记录中的安装路径、构建标识、测试数量和未完成项须按需重新检查；不能据此认定当前安装或宿主已经通过验收。

- [早期问题清单](ISSUES.md)：原始缺陷现象。
- [早期治理复盘](ISSUES_AND_POSTMORTEM.md)：v1.0.3 治理方案与结果；末节为当时的规范。
- [动态编码验收](dynamic-encoding-validation.md)：2026-10-28 的产品检查和虚拟看板集成。
- [迭代复盘](retro-20261028.md)：2026-10-28 的改进原因、待办和性能结论。
- [MCP 优化交付](mcp-improvements-20261028.md)：后续实现、传输体积与安装验收记录。
- [自托管、构图与指标卡验收](records/2026-11-07-server-layout-kpi.md)：2026-11-07 的性能对比、验证范围与未验证项。
- [性能原始记录](performance-results.json)：2026-10-20 的环境、测量、验证与限制。
- [零售验收截图](images/dynamic-encoding-retail.png)与[虚拟看板截图](images/transfer-prototype-validation.png)：配套历史附件。

已有记录原位保留。新任务的方案和单次验收证据按文件管理规则存放，不覆盖旧记录中的历史事实。
