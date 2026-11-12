# charts-design 文档

项目入口与命令见根目录 [README](../README.md)，Agent 的工作顺序见 [AGENTS.md](../AGENTS.md)。本页用于查找专题文档和历史记录。根目录仅保留此导航；长期准则放 `agent/`，设计规范放 `reference/`，实现说明放 `implementation/`，开发与运维步骤放 `operations/`。新增内容先按 [文件管理](agent/file-management.md) 确定归属。

## 项目准则与设计规范

| 文档 | 何时读取 | 更新时机 |
| --- | --- | --- |
| [产品上下文](agent/PRODUCT.md) | 判断产品目标、用户和强约束 | 已确认的产品决定改变 |
| [看板交付术语](agent/GLOSSARY.md) | 区分看板访问链接和业务术语 | 领域概念或称呼确定、改变 |
| [设计规范](reference/DESIGN.md) | 修改视觉、交互、组件复用或迁移保真 | 通用设计要求改变 |
| [文件管理](agent/file-management.md) | 新增、移动、合并或清理文件 | 目录、正文职责或保留方式改变 |

## 当前实现与操作

| 文档 | 负责内容 | 更新时机 |
| --- | --- | --- |
| [Runtime](implementation/dashboard-runtime.md) | 架构、运行配置、工具发现、导入与接口入口 | 模块或运行/接口边界改变 |
| [项目资产与加载](implementation/project-runtime.md) | 项目选择、存储、草稿、历史、本地数据和渐进视图 | 持久化、路由或查询行为改变 |
| [生成路径](implementation/generation-tracks.md) | 看板与报告、Markdown 源文、图号及兼容约定 | 生成与源文规则改变 |
| [组件清单](implementation/ui-component-inventory.md) | 组件源码、输入输出、动态能力与宿主接入状态 | 组件接口或能力改变 |
| [标题区与绑定](implementation/icon-header-and-bindings.md) | 标题、工具栏、图标、普通绑定与切换 | 操作或绑定约定改变 |
| [动态编码](implementation/dynamic-encoding.md) | 动态系列、散点、比例、比较和下钻 | 编码与汇总规则改变 |
| [渲染与覆盖](implementation/echarts-options.md) | 预设、完整 ECharts、自由 HTML/JavaScript、隔离及覆盖 | 渲染入口或合并规则改变 |
| [统计图后端](implementation/seaborn-backend.md) | Seaborn 原始观测声明、产物和依赖 | 统计能力或限制改变 |
| [位置批注](implementation/annotation-composer.md) | 选点、锚点、独立保存、冲突与宿主附件目标 | 批注字段、交互或接入状态改变 |
| [本地更新](operations/local-mcp-update.md) | 构建、安装更新、进程切换与重连 | 本地交付方式改变 |
| [传输与诊断](operations/mcp-transport-diagnostics.md) | 预览资源、分块、过期结果与请求日志 | 传输或排查方式改变 |
| [静态部署包](operations/static-deployment.md) | 独立网页资源、数据分片、下载与离线能力 | 静态交付格式改变 |
| [自托管服务器](operations/self-hosted-server.md) | 远程 MCP、签名链接、腾讯云密钥分享、COS 与 SCF 清理 | 服务、鉴权或云端交付流程改变 |
| [测试与 CI](operations/testing.md) | 检查层次、环境、标记与授权边界 | 检查入口或要求改变 |

## 生成与设计资产参考

- [看板 Skill](../skills/executive-charts/SKILL.md)、[报告 Skill](../skills/analytical-reports/SKILL.md)及[共享交付流程](../skills/executive-charts/references/mcp-delivery.md)：随包提供的生成步骤与成果保留要求。
- [指标定义](../skills/executive-charts/references/metric-definitions.md)、[数据格式](../skills/executive-charts/references/data_formatting_standards.md)：业务对象、范围、计算和显示。
- [指标卡选型](../skills/executive-charts/references/kpi-cards.md)、[布局模板](../skills/executive-charts/references/layout_templates.md)、[生成设计参考](../skills/executive-charts/references/design_standards.md)：按问题选择，不覆盖当前产品与设计规则。
- [图表参考](design-system/project/chart-ui.md)、[产品 React 组件](design-system/project/react-ui.md)：图形来源、组件映射、构建与设计资源。
- `design-system/`、`design-canvas/` 内的 README、API 索引和安装副本随资产维护；不作为项目主规范的重复版本。

## 方案

- [UI 组件与 MCP 整改](plans/ui-refactor-plan.md)：原方案范围、阶段与待确认事项；当前能力读取组件清单。
- [云端托管与版本管理](plans/cloud-hosting-and-version-control.md)：云端部署、API Key、密钥轮换与版本中心的产品方案，未实现部分按文内状态区分。

## 历史记录与附件

- [CloudBase 资源消耗基线](records/2026-11-12-cloudbase-resource-baseline.md)：云托管、函数、PostgreSQL 和 COS 的只读盘点。
- [CloudBase 存储与版本管理部署](records/2026-11-11-cloudbase-deployment.md)：本轮存储适配、局部检查、云端部署与验收边界。
- [早期问题清单](records/ISSUES.md)、[治理复盘](records/ISSUES_AND_POSTMORTEM.md)：旧实现的缺陷与治理事实，不作为现行规则。
- [动态编码验收](records/dynamic-encoding-validation.md)、[迭代复盘](records/retro-20261028.md)、[MCP 优化交付](records/mcp-improvements-20261028.md)：2026-10-28 的对象、测量、改动与验证边界。
- [自托管、构图与指标卡验收](records/2026-11-07-server-layout-kpi.md)：对应轮次的性能与部署检查。
- [共享工作区交付检查](records/2026-11-10-polish-validation.md)：共享工作区、UI 分批调整、批注与保真的既有记录。
- [测试清理](records/test-purge-20261106.md)、[测试清理变基](records/test-purge-rebase-20261108.md)：逐项处置和当次验证结果。
- [性能原始记录](records/performance-results.json)、[共享工作区性能结果](records/2026-11-10-polish-performance.json)、[零售截图](images/dynamic-encoding-retail.png)、[虚拟看板截图](images/transfer-prototype-validation.png)：与对应历史记录一起阅读，不替代当前验证。

维护时机：正文职责、位置或方案/记录入口变化时更新。
