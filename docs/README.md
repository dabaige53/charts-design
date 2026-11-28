# Charts Design 文档

[快速开始](../README.md)介绍产品与操作，[开发入口](../AGENTS.md)说明源码职责。各主题只维护一份正文；更改结构前读[文件管理](agent/file-management.md)。

## 产品与设计

- [产品上下文](agent/PRODUCT.md)：使用者、目标、能力边界与强约束。
- [交付术语](agent/GLOSSARY.md)：本机、在线和独立分享的访问方式。
- [设计规范](reference/DESIGN.md)：视觉、交互、可访问性、组件复用与外部报告保真。
- [图表参考](design-system/project/chart-ui.md)、[React 组件](design-system/project/react-ui.md)：设计资产与生产组件映射。

## 创建与维护

- [看板 Skill](../skills/executive-charts/SKILL.md)、[报告 Skill](../skills/analytical-reports/SKILL.md)：按决策问题与证据生成成果。
- [原生创作](../skills/executive-charts/references/mcp-authoring.md)、[共享交付](../skills/executive-charts/references/mcp-delivery.md)：初始化、数据预览、提交、检查与交付。
- [指标定义](../skills/executive-charts/references/metric-definitions.md)、[数据格式](../skills/executive-charts/references/data_formatting_standards.md)：口径、公式、单位和精度。
- [图表与设计选型](../skills/executive-charts/references/design_standards.md)、[指标卡](../skills/executive-charts/references/kpi-cards.md)、[布局](../skills/executive-charts/references/layout_templates.md)：比较关系、阅读顺序与明确适用条件。
- [生成路径](implementation/generation-tracks.md)：Dashboard、Markdown 报告、图号、来源和脚注。

## 实现

| 正文 | 内容 |
| --- | --- |
| [Runtime](implementation/dashboard-runtime.md) | Rust 服务、CLI/MCP/HTTP、合同、输入与查询 |
| [项目资产](implementation/project-runtime.md) | 项目隔离、不可变数据、草稿、保存、发布、历史与渐进加载 |
| [组件清单](implementation/ui-component-inventory.md) | 维护位置、输入输出、动态能力与宿主边界 |
| [标题与绑定](implementation/icon-header-and-bindings.md) | 元信息、工具栏、图形切换与保存 |
| [动态编码](implementation/dynamic-encoding.md) | 系列、散点、比例、比较与下钻 |
| [渲染入口](implementation/echarts-options.md) | 预设、ECharts、HTML/JavaScript 和隔离 |
| [统计图](implementation/statistical-charts.md) | 原始观测、统计声明、SVG/PNG 与数值限制 |
| [位置批注](implementation/annotation-composer.md) | 锚点、独立权限、冲突、保存与分享反馈 |

## 运行与交付

- [本地安装与更新](operations/local-mcp-update.md)：原生程序、共享 UI、连接与构建标识。
- [大响应与诊断](operations/mcp-transport-diagnostics.md)：完整资源、分块、过期响应与日志。
- [静态部署包](operations/static-deployment.md)：完整资源、Parquet、JSON 分片、离线与权限边界。
- [自托管服务](operations/self-hosted-server.md)：远程 MCP、签名链接、分享服务和物理清理。
- [开发检查与 CI](operations/testing.md)：环境、定向验证、构建与发布流程。
