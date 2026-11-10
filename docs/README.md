# charts-design 文档

> **当前状态（2026-11-10）**
> React 组件、设计画布和 MCP 应用已使用独立适配入口。构建与运行资源通过显式打包同步，历史原生生成器继续下线。实际完成情况与检查结果以 [UI 整改计划](ui-refactor-plan.md) 和 [组件清单](ui-component-inventory.md) 为准。

## 开始使用

快速开始见根目录 [README](../README.md)。选择生成方式时读 [生成路径](generation-tracks.md)；开发与运行步骤见 [Runtime 说明](dashboard-runtime.md)。Agent 按根目录 [AGENTS.md](../AGENTS.md) 的任务条件读取文档。

## 现行规范与设计参考

| 文档 | 用途与查阅时机 | 更新时机 |
| --- | --- | --- |
| [当前 UI 设计记录](DESIGN.md) | 从 React 源码提取的颜色、字阶、布局、组件与动效规则；配套预览说明位于 `docs/.impeccable/design.json` | 当前实现的视觉规则变化后同步 |
| [图表 UI 与设计系统](design-system/project/chart-ui.md) | 重构前查阅保留的 40 个图表定义、视觉、配色与交互参考；PDF 数据色盘与旧项目配色分开 | 图表视觉迁移或来源规范变化 |
| [文件管理](agent/file-management.md) | 新增、移动或清理文件前，确定位置和维护入口 | 目录职责或保留规则变化 |
| [指标定义](../skills/executive-charts/references/metric-definitions.md) | 撰写业务说明与统计口径时查阅 | 指标说明要求变化 |
| [数据格式标准](../skills/executive-charts/references/data_formatting_standards.md) | 处理指标数值、百分比与单位格式化时查阅 | 格式化标准变化 |
| [标题区与绑定](icon-header-and-bindings.md) | 组件操作区、Lucide 图标与筛选绑定规范；新 UI 的设计与绑定准则 | 界面约定或绑定范围变化 |
| [设计规范](../skills/executive-charts/references/design_standards.md) | 组件配色、排版、几何与红涨绿跌准则；新 UI 的设计参考 | 设计要求变化 |
| [指标卡选型](../skills/executive-charts/references/kpi-cards.md) 与 [布局模板](../skills/executive-charts/references/layout_templates.md) | 选择指标卡形态与看板构图时查阅 | 卡片类型、模板或选型规则变化 |
| [MCP 共享交付流程](../skills/executive-charts/references/mcp-delivery.md) | 数据资产保存、编辑批次与合同检查；协议与宿主显示分别确认 | 交付流程变化 |

## 当前实现与操作

- [UI 整改计划](ui-refactor-plan.md)：范围、阶段、构建路径和完成条件。
- [UI 组件清单](ui-component-inventory.md)：实际输入、事件、状态、数据与宿主依赖。
- [产品 React 组件](design-system/project/react-ui.md)：设计系统与运行变量映射、可运行预览。

| 文档 | 用途与查阅时机 | 当前状态 / 维护说明 |
| --- | --- | --- |
| [Runtime 说明](dashboard-runtime.md) | 状态存储、数据模式、SQLite 与 MCP 协议说明 | 组件与数据协议已接入，宿主显示单独确认 |
| [生成路径](generation-tracks.md) | 从空白创建数据资产或分析报告源文时查阅 | 数据声明、Markdown 与新 React 预览 |
| [项目资产与加载](project-runtime.md) | 处理多项目、历史、数据存储和渐进加载时查阅 | 存储、路由与分片协议继续正常维护 |
| [动态编码](dynamic-encoding.md) | 声明动态系列、散点、比较或下钻时查阅 | 编码能力与绑定规则继续维护 |
| [ECharts 配置覆盖](echarts-options.md) | 调整原生显示配置时查阅 | 合并与覆盖规则继续维护 |
| [Seaborn 后端](seaborn-backend.md) | 独立于旧 UI；使用原始观测生成统计图时查阅 | 统计声明、依赖与绘图产物完整可用 |
| [自托管服务器](self-hosted-server.md) | 部署远程 HTTP MCP 与项目隔离时查阅 | 远程协议与新应用资源路由 |
| [本地 MCP 更新](local-mcp-update.md) | 更新本地安装包与连接检查时查阅 | 独立构建、资源打包和连接检查 |
| [传输与诊断](mcp-transport-diagnostics.md) | 排查响应分块、请求日志与性能时查阅 | 诊断接口继续正常维护 |
| [测试与 CI](testing.md) | 静态检查、后端单元测试与容器镜像冒烟测试 | 仅三层检查；无浏览器验收；全量需授权 |
| [位置引用与批注](annotation-composer.md) | 批注数据模型与坐标系规范（新 UI 规范） | 数据模型保留；前端宿主实现待新 UI 接入 |
| [原版组件保真](original-component-fidelity.md) | 历史原版组件提取与保真准则（历史参考） | 旧提取脚本已移除；作为设计保真准则参考 |
| [静态部署包](static-deployment.md) | 静态网站部署包结构与数据范围 | 共享 React 资源与数据分片 ZIP |

## 历史记录与证据（已移除旧实现）

- [早期问题清单](ISSUES.md)：原始缺陷现象。
- [早期治理复盘](ISSUES_AND_POSTMORTEM.md)：v1.0.3 治理方案与结果；末节为当时的规范。
- [动态编码验收](dynamic-encoding-validation.md)：2026-10-28 的产品检查和虚拟看板集成。
- [迭代复盘](retro-20261028.md)：2026-10-28 的改进原因、待办和性能结论。
- [MCP 优化交付](mcp-improvements-20261028.md)：后续实现、传输体积与安装验收记录。
- [自托管、构图与指标卡验收](records/2026-11-07-server-layout-kpi.md)：2026-11-07 的性能对比、验证范围与未验证项。
- [性能原始记录](performance-results.json)：2026-10-20 的环境、测量、验证与限制。
- [测试清剿记录](records/test-purge-20261106.md)：2026-11-06 的逐用例处置、附属资产清理和局部验证。
- [测试清剿变基记录](records/test-purge-rebase-20261108.md)：2026-11-08 变基到 PR #6 之后的冲突处理、新增标注、待决定项和验证结果。
- [零售验收截图](images/dynamic-encoding-retail.png)与[虚拟看板截图](images/transfer-prototype-validation.png)：配套历史附件。

已有记录原位保留。新任务的方案和单次验收证据按文件管理规则存放，不覆盖旧记录中的历史事实。
