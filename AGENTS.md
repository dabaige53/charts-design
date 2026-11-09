# charts-design 工作入口

本项目维护经营看板与分析报告的组件生成器、CLI 和 MCP Runtime。按任务读取下列文档；新增和整理文件前先读文件管理规则。

## 文档阅读

- 初次了解项目时读 [README.md](README.md)：用途、生成方式和快速开始。
- 查找专题或历史证据时读 [文档总览](docs/README.md)：文档职责、维护时机和附件。
- 新增、移动或清理文件时读 [文件管理](docs/agent/file-management.md)：目录职责、维护源码、生成文件和业务资产边界。
- 修改 Runtime、CLI 或导出时读 [Runtime 说明](docs/dashboard-runtime.md)：运行、报告源文、状态、接口和兼容边界。
- 创建 Dashboard 或分析报告时读 [生成路径](docs/generation-tracks.md)：案例发现、组件声明和编辑批次。
- 修改项目存储、多项目路由、历史或渐进加载时读 [项目资产与加载](docs/project-runtime.md)：项目参数、检查点和查询流程。
- 修改操作区、图标或组件绑定时读 [标题区与绑定](docs/icon-header-and-bindings.md)：界面约束与绑定范围。
- 修改原版组件提取、迁移或构建时读 [组件保真](docs/original-component-fidelity.md)：原配置、渲染器和迁移保留要求。
- 修改动态系列、散点或 KPI 比较时读 [动态编码](docs/dynamic-encoding.md)：字段、比例、排序和下钻。
- 修改 ECharts 显示配置时读 [原生配置覆盖](docs/echarts-options.md)：合并顺序、覆盖规则和数据边界。
- 修改统计图时读 [Seaborn 后端](docs/seaborn-backend.md)：原始观测、声明、产物和限制。
- 修改位置批注或对话附件时读 [批注说明](docs/annotation-composer.md)：宿主能力、页面批注和连续位置引用。
- 更新本地安装或排查旧进程时读 [本地 MCP 更新](docs/local-mcp-update.md)：打包更新、文件清单更新和重连检查。
- 排查预览、大响应或版本缓存时读 [传输与诊断](docs/mcp-transport-diagnostics.md)：预览入口、分块读取和请求日志。
- 修改独立网页导出时读 [静态部署包](docs/static-deployment.md)：数据范围、重建、发布和验收边界。
- 部署远程 MCP、修改服务器或网页预览与分享链接时读 [自托管服务器](docs/self-hosted-server.md)：入口、令牌、项目隔离、链接权限与边界。
- 修改测试、CI 或检查脚本时读 [测试与 CI](docs/testing.md)：五层检查、浏览器标记、本地准备与产物。
- 使用 Dashboard 生成器时读 [executive-charts](skills/executive-charts/SKILL.md)：组件编排、业务数据和生成检查。
- 生成 Markdown 分析报告时读 [analytical-reports](skills/analytical-reports/SKILL.md)：学术单栏正文与图文核对。
- 使用 MCP 创建、编辑或诊断时读 [共享交付流程](skills/executive-charts/references/mcp-delivery.md)：项目参数、语义保留、批次完成与一次预览。
- 修改组件视觉时读 [设计规范](skills/executive-charts/references/design_standards.md)：配色、排版、几何和表格要求；Runtime 操作区按标题区与绑定文档执行。
- 选择或修改指标卡与布局构图时读 [指标卡选型](skills/executive-charts/references/kpi-cards.md) 与 [布局模板](skills/executive-charts/references/layout_templates.md)：按问题选卡、七种构图与避免同质化的规则。
- 编写指标说明时读 [指标定义](skills/executive-charts/references/metric-definitions.md)：统计对象、范围、单位与计算语义。
- 追溯早期架构治理时读 [历史治理复盘](docs/ISSUES_AND_POSTMORTEM.md)：当时的原因、方案和版本结果。
- 复查动态编码验收时读 [验收记录](docs/dynamic-encoding-validation.md)：2026-10-28 的对象、结果和宿主限制。
- 追溯 MCP 改进原因时读 [迭代复盘](docs/retro-20261028.md)：当时的待办、性能证据与后续记录。
- 复查 MCP 优化交付时读 [交付记录](docs/mcp-improvements-20261028.md)：改动、响应体积与安装验收边界。
- 复查自托管、构图与指标卡改动时读 [验收记录](docs/records/2026-11-07-server-layout-kpi.md)：2026-11-07 的性能对比、验证范围与未验证项。

## 修改与检查
