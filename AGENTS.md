# Charts Design 工作入口

本项目用一个 Rust Runtime 和共享 React 界面创建、维护和交付看板与分析报告。中文回复。先识别任务影响的层，再读取负责正文；保留用户已有数据、稳定 ID、指标口径和无关改动。

## 源码职责

| 路径 | 负责内容 |
| --- | --- |
| `runtime-core/src/runtime/` | 服务、协议、查询、持久化、版本、统计图、导出和分享 |
| `runtime-core/resources/` | 工具合同、图表声明、案例与报告母稿 |
| `runtime-ui/src/` | React 组件、状态、布局及宿主适配 |
| `runtime-ui/src/charts/`、`runtime-ui/shared/` | 图表预设与浏览器/静态导出共享数据模块 |
| `bin/` | 原生程序安装、统一启动、工作树 Skill 链接与开发检查 |
| `skills/` | 看板、报告创作流程与随包设计参考 |
| `deploy/` | 自托管、云端分享与清理部署源码 |
| `runtime-core/tests/`、`tests/`、`.github/workflows/` | Rust、前端、协议和部署验证 |
| `docs/design-system/`、`docs/design-canvas/` | 设计资产与原始参考，生产构建不依赖它们 |

## 按任务阅读

| 任务 | 负责正文 |
| --- | --- |
| 首次接触、产品目标与强约束 | [README](README.md)、[产品上下文](docs/agent/PRODUCT.md) |
| 视觉、交互、组件复用与外部报告保真 | [设计规范](docs/reference/DESIGN.md) |
| CLI/MCP/HTTP、合同与数据初始化 | [Runtime](docs/implementation/dashboard-runtime.md) |
| 项目路由、数据、草稿、保存与历史 | [项目资产](docs/implementation/project-runtime.md) |
| 看板或报告生成与修改 | [生成路径](docs/implementation/generation-tracks.md)、对应 [看板 Skill](skills/executive-charts/SKILL.md) / [报告 Skill](skills/analytical-reports/SKILL.md) |
| MCP 交付、冲突与完成确认 | [共享交付](skills/executive-charts/references/mcp-delivery.md) |
| 图形声明与数据绑定 | [动态编码](docs/implementation/dynamic-encoding.md)、[渲染入口](docs/implementation/echarts-options.md)、[统计图](docs/implementation/statistical-charts.md) |
| UI 与批注 | [组件清单](docs/implementation/ui-component-inventory.md)、[标题与绑定](docs/implementation/icon-header-and-bindings.md)、[位置批注](docs/implementation/annotation-composer.md) |
| 安装、诊断、导出与服务部署 | [文档目录](docs/README.md#运行与交付) |
| 新增、移动、合并或删除文件 | [文件管理](docs/agent/file-management.md) |
| 安装依赖、构建、测试或改 CI | [开发检查](docs/operations/testing.md) |

CloudBase 相关能力、方案、部署、鉴权、存储和排错，先阅读官方 [CloudBase Skill](https://github.com/TencentCloudBase/cloudbase-skills/blob/main/skills/cloudbase/SKILL.md)，再按需阅读其专题参考。

## 修改与验证

- 业务修改先读当前声明和修订。批次提交后核对受影响结果，确认保存成功再展示；发布、分享按用户目的分别执行。
- UI 修改进入共享 React 源码。预览或安装时用 `ui:prepare` 复用有效产物；设计资源按需独立更新。
- 本地只运行保护本次行为的定向检查。完整套件在 GitHub 执行；本地全量、浏览器自动化和目标宿主验收需要当前任务授权。
- 纯文档整理只查内容归属、链接、锚点和 Skill 引用，不顺带跑功能测试。
- 报告实际改动、验证结果和具体未验证边界。自动检查、MCP 协议、真实宿主显示和云端部署分别确认。

## 文档

现行规则在负责正文维护，Git 保存历史。README 负责开始使用，本文件负责开发工作入口，docs/README 负责专题导航。合并或删除内容时保留独有的有效约定，并同步全部引用；不保留重复入口、执行日志或阶段性迁移说明。
