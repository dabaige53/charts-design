# charts-design 工作入口

本项目通过 MCP 和 CLI 创建、维护经营看板与分析报告，管理数据资产、指标定义、组件声明、编辑历史和交付资源。先确认任务影响的层，再读取对应正文。

## 项目职责与源码位置

| 位置 | 职责 |
| --- | --- |
| `dashboard_runtime/` | 数据计算、持久化、版本与批注、CLI 后端和 MCP/HTTP 服务 |
| `dashboard_runtime/tool_contract.py`、`contract.py` | 工具说明、参数结构、操作约定与发现入口 |
| `runtime-ui/src/` | 共享 React 组件、交互状态、GridStack 布局及宿主适配 |
| `runtime-ui/src/charts/` | 独立维护的预设图表；其他渲染入口按当前声明约定工作 |
| `bin/` | CLI、MCP 启动器、安装更新与检查脚本 |
| `skills/` | 看板与报告生成指引、随包参考及工作区资产管理 |
| `deploy/` | 自托管服务与腾讯云清理函数的部署源码 |
| `tests/`、`.github/workflows/` | 局部行为检查、协议检查和 CI 配置 |
| `docs/design-system/`、`docs/design-canvas/` | 可编辑设计资产、组件预览与归档参考，不作为生产运行源码 |

## 开始任务

1. 检查当前工作区的未提交改动，确认本次任务涉及的代码、文档和业务资产，保留无关改动。
2. 初次接触项目时读 [README.md](README.md)，了解可用入口与启动方式。
3. 判断产品目标、能力边界或新增功能时读 [产品上下文](docs/agent/PRODUCT.md)；修改视觉和交互前读 [设计规范](docs/reference/DESIGN.md)。
4. 新增、移动、合并或删除文件前读 [文件管理](docs/agent/file-management.md)，确定现有负责正文和目标位置。
5. 查历史记录时读 [文档总览](docs/README.md)。

## 按任务阅读

- 修改 Runtime、CLI、MCP 注册或工具定义时读 [Runtime 说明](docs/implementation/dashboard-runtime.md)：模块边界、配置、发现、数据导入与接口副作用。
- 修改项目路由、存储、草稿、检查点、历史或渐进查询时读 [项目资产与加载](docs/implementation/project-runtime.md)：项目隔离、版本检查、数据引用和查询状态。
- 创建看板或分析报告时读 [生成路径](docs/implementation/generation-tracks.md)：文档类型、报告源文、图表引用与案例的使用边界。
- 通过 MCP 交付内容时读 [共享交付流程](skills/executive-charts/references/mcp-delivery.md)：检查现有成果、保留语义、完成编辑批次后展示。
- 生成经营看板时读 [executive-charts](skills/executive-charts/SKILL.md)：指标拆解、渲染入口与组件编排。
- 生成 Markdown 分析报告时读 [analytical-reports](skills/analytical-reports/SKILL.md)：学术单栏正文、数据声明与图文核对。
- 修改 UI 组件及宿主适配时读 [组件清单](docs/implementation/ui-component-inventory.md)：组件维护位置、输入输出、动态能力和接入状态。
- 修改标题、工具栏、图标、图表切换或普通绑定时读 [标题区与绑定](docs/implementation/icon-header-and-bindings.md)：操作范围、保存边界与兼容切换。
- 修改动态系列、散点、比例、KPI 比较或下钻时读 [动态编码](docs/implementation/dynamic-encoding.md)：字段、汇总、排序、编码与联动。
- 修改原生 ECharts 或自由 HTML/JavaScript 组件时读 [渲染与覆盖](docs/implementation/echarts-options.md)：三种入口、合并规则、隔离和数据绑定限制。
- 修改 Seaborn 统计图时读 [统计图后端](docs/implementation/seaborn-backend.md)：原始观测、统计声明、产物和依赖。
- 修改位置批注或宿主对话附件时读 [批注说明](docs/implementation/annotation-composer.md)：锚点、独立保存、冲突、宿主能力和未接入部分。
- 更新本地 MCP 安装或确认运行版本时读 [本地更新](docs/operations/local-mcp-update.md)：构建、指定文件更新、进程切换与重连。
- 排查预览、分块响应或查询日志时读 [传输与诊断](docs/operations/mcp-transport-diagnostics.md)：完整响应读取、过期资源和请求编号。
- 修改静态网页导出时读 [静态部署包](docs/operations/static-deployment.md)：资源、数据分片、下载和离线能力。
- 部署远程 MCP、网页分享或腾讯云到期清理时读 [自托管服务器](docs/operations/self-hosted-server.md)：鉴权、8 位数字密钥、COS 私有副本及云端 SCF 删除。
- 处理 CloudBase（腾讯云开发）相关问题，包括能力咨询、方案设计、部署、鉴权、存储与排错时，先阅读官方 [CloudBase SKILL.md](https://github.com/TencentCloudBase/cloudbase-skills/blob/main/skills/cloudbase/SKILL.md)，再按任务读取其中对应的参考文档。
- 修改测试、CI 或选择验证范围时读 [测试与 CI](docs/operations/testing.md)：检查层次、环境、测试标记和全量授权要求。
- 修改设计画布或追溯原图形时读 [图表参考](docs/design-system/project/chart-ui.md)：几何、标签、Tooltip 和原始资料。
- 修改设计组件导出或画布安装资源时读 [产品 React 组件](docs/design-system/project/react-ui.md)：组件映射与独立构建、打包入口。
- 选择指标卡时读 [指标卡选型](skills/executive-charts/references/kpi-cards.md)：按问题选择形态，保留真实比较基准。
- 编写指标说明时读 [指标定义](skills/executive-charts/references/metric-definitions.md)：业务对象、范围、单位、公式和待确认事项。
- 修改显示格式时读 [数据格式标准](skills/executive-charts/references/data_formatting_standards.md)：数值、单位、比例与显示精度。
- 查阅随包图表视觉建议时读 [生成设计参考](skills/executive-charts/references/design_standards.md)：参考不能覆盖当前产品与设计规则。
- 调整 UI 重构阶段和待办时读 [UI 整改计划](docs/plans/ui-refactor-plan.md)：方案范围与阶段；当前接入状态以组件清单为准。

## 修改与检查

- 业务成果先读取当前声明再修改；数据、指标定义、稳定 ID、比较基准、过滤消费者与批注的保留要求按共享交付流程执行。
- UI 改动从共享 React 源码进入；本地需要预览或更新安装时运行 `ui:prepare` 复用有效资源，设计资产另行打包。
- 开发、测试或构建前读 [开发检查与 CI](docs/operations/testing.md)：GitHub 执行完整检查，本地按需排错和准备预览；本地全量与浏览器验收遵循授权边界。
- 纯文档整理只检查内容归属、旧路径引用、Skill 入口和本地链接/锚点，不顺带运行功能测试。
- 交付说明实际改动、已执行检查和未验证边界；源码、打包资源、安装位置、连接进程及云端部署状态分别确认。

## 文档维护

正文归属和新增条件统一维护在文件管理规则。现行规范原处更新；方案进入 `docs/plans/`，单次证据进入 `docs/records/`。文档路径变化时同步本入口、文档总览、Skill 引用及实际引用它的配置或脚本。
