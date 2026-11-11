# charts-design 工作入口

本项目维护经营看板与分析报告的数据资产、声明合同、CLI 与 MCP Runtime。按任务读取下列文档；新增和整理文件前先读文件管理规则。

> **当前状态（2026-11-10）**
> 新 React 组件库使用 Tailwind CSS v4、shadcn/ui、TanStack Table、ECharts、GridStack 和 Lucide。MCP 应用、HTML 快照及静态站点资源通过独立构建与打包步骤交付；原生 HTML 生成器和旧单体界面继续下线。实施状态与检查边界见 [UI 整改计划](docs/ui-refactor-plan.md) 和 [组件清单](docs/ui-component-inventory.md)。

## 文档阅读

- 修改新 UI 时先读 [UI 整改计划](docs/ui-refactor-plan.md) 与 [组件清单](docs/ui-component-inventory.md)：组件、画布、应用、宿主及后端边界；本轮不运行 UI 测试或浏览器自动化。

- 初次了解项目时读 [README.md](README.md)：当前可用入口、重构状态与快速开始。
- 查找专题或历史证据时读 [文档总览](docs/README.md)：文档职责、维护时机与重构索引。
- 新增、移动或清理文件时读 [文件管理](docs/agent/file-management.md)：目录职责、维护源码、生成文件和业务资产边界。
- 修改 Runtime、CLI 或导出时读 [Runtime 说明](docs/dashboard-runtime.md)：状态存储、数据模式、接口和兼容边界。
- 创建 Dashboard 或分析报告时读 [生成路径](docs/generation-tracks.md)：数据声明、组件编排和 Markdown 写作。
- 修改项目存储、多项目路由、历史或渐进加载时读 [项目资产与加载](docs/project-runtime.md)：项目参数、检查点和查询流程。
- 修改操作区、图标或组件绑定时读 [标题区与绑定](docs/icon-header-and-bindings.md)：新 UI 设计体系的操作区排版与筛选绑定规范。
- 修改原版组件提取、迁移或构建时读 [组件保真](docs/original-component-fidelity.md)：原配置与无损迁移保留要求（历史参考）。
- 修改动态系列、散点或 KPI 比较时读 [动态编码](docs/dynamic-encoding.md)：字段、比例、排序和下钻。
- 修改 ECharts 显示配置时读 [原生配置覆盖](docs/echarts-options.md)：合并顺序、覆盖规则和数据边界。
- 修改统计图时读 [Seaborn 后端](docs/seaborn-backend.md)：独立于旧 UI；原始观测、声明、产物和限制。
- 修改位置批注或对话附件时读 [批注说明](docs/annotation-composer.md)：批注数据结构与坐标系规范（新 UI 规范）。
- 更新本地安装或排查旧进程时读 [本地 MCP 更新](docs/local-mcp-update.md)：打包更新、文件清单更新和重连检查。
- 排查预览、大响应或版本缓存时读 [传输与诊断](docs/mcp-transport-diagnostics.md)：预览入口、分块读取和请求日志。
- 修改独立网页导出时读 [静态部署包](docs/static-deployment.md)：静态网站部署包规范（历史参考/待新 UI 接入）。
- 部署远程 MCP、修改服务器或网页预览与分享链接时读 [自托管服务器](docs/self-hosted-server.md)：远程 MCP、令牌、项目隔离与边界。
- 修改测试、CI 或检查脚本时读 [测试与 CI](docs/testing.md)：三层检查、无浏览器验收、全量测试授权要求。
- 组织看板资产时读 [executive-charts](skills/executive-charts/SKILL.md)：组件编排、业务数据和合同校验。
- 生成 Markdown 分析报告时读 [analytical-reports](skills/analytical-reports/SKILL.md)：学术单栏正文与底层数据声明。
- 使用 MCP 创建、编辑或诊断时读 [共享交付流程](skills/executive-charts/references/mcp-delivery.md)：项目参数、语义保留与批次完成。
- 重构图表视觉时先读 [图表 UI 保留说明](docs/design-system/project/chart-ui.md)：40 个图表原定义、几何、标签、Tooltip、交互与视觉案例；原始参考保存在该设计系统内，勿当作新 UI 的运行源码。
- 修改组件视觉时读 [设计规范](skills/executive-charts/references/design_standards.md)：配色、排版、几何和表格要求；Runtime 操作区按标题区与绑定文档执行。
- 选择或修改指标卡与布局构图时读 [指标卡选型](skills/executive-charts/references/kpi-cards.md) 与 [布局模板](skills/executive-charts/references/layout_templates.md)：按问题选卡、七种构图与避免同质化的规则。
- 编写指标说明时读 [指标定义](skills/executive-charts/references/metric-definitions.md)：统计对象、范围、单位与计算语义。
- 追溯早期架构治理时读 [历史治理复盘](docs/ISSUES_AND_POSTMORTEM.md)：当时的原因、方案和版本结果。
- 复查动态编码验收时读 [验收记录](docs/dynamic-encoding-validation.md)：2026-10-28 的对象、结果和宿主限制。
- 追溯 MCP 改进原因时读 [迭代复盘](docs/retro-20261028.md)：当时的待办、性能证据与后续记录。
- 复查 MCP 优化交付时读 [交付记录](docs/mcp-improvements-20261028.md)：改动、响应体积与安装验收边界。
- 复查自托管、构图与指标卡改动时读 [验收记录](docs/records/2026-11-07-server-layout-kpi.md)：2026-11-07 的性能对比、验证范围与未验证项。

## 修改与检查
