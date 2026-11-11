# 文件管理

新增、移动、合并或清理文件时，先确定文件用途及维护入口。维护源码、生成产物、项目业务资产分别保存。

## 目录职责

| 位置 | 内容 | 维护方式 |
| --- | --- | --- |
| `README.md`、`AGENTS.md` | 项目快速开始与按任务阅读入口 | 用途、流程或文档路径变化时更新 |
| `docs/` | 仅 `README.md` 总导航 | 专题正文按职责进入下列子目录；文档检查自动执行此约束 |
| `docs/reference/` | 设计规范 | 通用要求原位更新 |
| `docs/implementation/` | 当前架构、功能与接口说明 | 随实现变化原位更新 |
| `docs/operations/` | 开发检查、安装、部署与诊断 | 随执行流程变化原位更新 |
| `docs/agent/` | 文件管理等长期项目准则 | 已确认的项目约定变化时原位更新 |
| `docs/plans/`、`docs/records/`、`docs/adr/` | 按需新增的专项方案、验证记录和架构决定 | 有实际内容时创建；已有清楚路径沿用 |
| `docs/images/`、`docs/records/performance-results.json` | 文档配套截图与已有性能证据 | 与对应记录一同保留，标明测量范围 |
| `skills/executive-charts/` | 看板规范、指标卡、布局模板、图表声明和工作区脚本 | 维护源码；本地安装指向此目录 |
| `skills/analytical-reports/` | 分析报告 Skill 与随包参考材料 | 保留相对引用和随包可用性 |
| `dashboard_runtime/`、`bin/` | 后端 SQLite 存储、数据计算、MCP 服务与启动更新脚本 | 修改对应维护源码后更新 |
| `deploy/` | 自托管服务器的 Dockerfile、compose、systemd 与 nginx 示例 | 服务器参数或运行方式变化时同步 `docs/operations/self-hosted-server.md`；不存放令牌、密钥或 `charts.env` |
| `dashboard_runtime/examples/academic-report.md` | 分析报告案例的唯一 Markdown 母稿 | MCP 案例直接读取，避免独立副本 |
| `tests/`、`.github/workflows/` | 静态检查、后端单元测试与部署镜像冒烟检查 | 检查入口以 `docs/operations/testing.md` 为准，不含浏览器验收 |
| `.bun-version`、`.python-version`、`pyproject.toml`、`uv.lock`、两级 `package.json` 与 `bun.lock` | 运行工具版本、依赖声明和锁定结果 | 环境入口统一见开发检查；声明和锁文件同批提交 |

Skill 的 `SKILL.md`、组件旁使用说明和随包参考材料继续保留原位。项目级文档正文放在 `docs/`，不为工具发现另建根目录正文、链接入口或符号链接。适配 Skill 或插件要求时优先改用已有正文；自动发现失败时直接读取实际路径。

## 生成文件与重构边界

`runtime-ui/src` 维护 React 组件、应用和宿主适配。`runtime-ui/fixtures` 仅保存设计预览数据，生产构建禁止引用该目录及 `docs`。40 个图表定义维护在 `runtime-ui/src/charts`，不再在构建时提取归档源码。

构建输出为 `runtime-ui/dist`，由 GitHub Actions 保存为产物，不提交 Git。本地仅在明确需要预览或安装时通过 `ui:prepare` 核对并复用已有产物。`ui:package` 将应用资源交付到 `dashboard_runtime/web/dist`，供 MCP、npm 与 Python 包使用；容器在独立 Bun 阶段构建。`ui:package:design` 更新设计系统组件 bundle。

## 业务资产与临时文件

业务工作区、来源数据和交付文件放在用户指定项目中，不放进 Skill 工具目录。项目内的 `charts-project.json`、`dashboards/` 和 `data/` 属于持久资产；运行缓存和诊断目录可与项目资产分开。

项目模式下，`dashboards/dashboards.sqlite3` 保存事务状态，草稿、检查点和批注 JSON 是自动生成的可读镜像，不另行手工维护。数据版本与历史引用的保留方式见项目存储实现，不因清理缓存删除业务资产。含业务快照、SQL 参数或敏感数据的文件不作为公共仓库产物提交。

临时和备份文件放在 `/private/tmp`，不用日期副本替代 Git 历史。需要长期保留的验收附件放入对应项目的文档位置，并标明日期、对象、环境和结论边界。

## 文档维护

项目准则、设计规范和当前实现说明原位更新；Git 保存旧版。历史记录保留当时事实，标明后续决定与替代关系。未验证的计划不写成已实现，工具返回成功不写成宿主页面已验收。

新增文档时先检查是否已有同类正文。规则只维护一处，定义、条件和例外放在一起；使用说明通过必要链接引用该规则。移动、改名、合并或删除文档时，同步 `AGENTS.md`、`docs/README.md`、正文链接、章节锚点、脚本、检查配置和包发布清单。

### 正文归属

| 内容 | 负责正文 | 更新条件 |
| --- | --- | --- |
| 产品使用者、目标、边界与强约束 | `docs/agent/PRODUCT.md` | 已确认的产品决定改变 |
| 看板交付与访问方式的领域术语 | `docs/agent/GLOSSARY.md` | 领域概念或称呼确定、改变 |
| 视觉、交互、组件复用与保真要求 | `docs/reference/DESIGN.md` | 已确认的通用设计要求改变 |
| Runtime 架构、配置和接口入口 | `docs/implementation/dashboard-runtime.md` | 模块职责、运行方式或接口入口改变 |
| 项目存储、草稿、历史和渐进数据 | `docs/implementation/project-runtime.md` | 持久化、路由、计算或加载行为改变 |
| 看板/报告写作与源文约定 | `docs/implementation/generation-tracks.md` | 生成方式、报告语法或文档类型改变 |
| UI 组件的接口、能力与接入状态 | `docs/implementation/ui-component-inventory.md` | 组件接口、实现能力或宿主验证状态改变 |
| 标题与绑定、动态编码、自由渲染、统计图、批注 | 各自现有专题正文 | 对应交互或数据约定改变；不在总览另写一份规则 |
| 本地 MCP 更新和传输诊断 | `docs/operations/local-mcp-update.md`、`docs/operations/mcp-transport-diagnostics.md` | 安装、重连、响应传输或排查方式改变 |
| 远程 MCP、网页分享、腾讯云存储和过期清理 | `docs/operations/self-hosted-server.md` | 服务部署、鉴权、分享或云端删除流程改变 |
| 独立静态网页包 | `docs/operations/static-deployment.md` | 资源结构、分片、下载或离线能力改变 |
| 检查要求与检查入口 | `docs/operations/testing.md` | 验证范围、命令入口或通过条件改变 |
| 阶段安排、技术方案与待办 | `docs/plans/` | 对应方案调整；不承载长期规范 |
| 构建编号、运行环境、当次检查结果与历史事实 | `docs/records/` | 同一轮次证据补全；不反向改写当时事实 |

`AGENTS.md` 负责工作顺序与按任务阅读入口，`docs/README.md` 负责文档分类和历史索引。设计资产中的组件 README、API 索引和画布安装副本随资产维护。

### 新增与整理

1. 先说明这份内容回答什么问题，并在正文归属表和现有专题中查找负责位置。
2. 已有正文能承接时原处补充；同一主题的新功能不默认另开文档。只有职责独立且现有正文无法承接时才新建，并同步归属和导航。
3. 先区分产品要求、当前实现、方案和证据，再确定位置。未实现目标保留目标含义并标明状态，不为消除冲突而改写成现有实现。
4. 可从代码、配置、声明或锁文件查询的枚举、版本和命令优先引用其维护入口；文档写用途、选择条件、兼容边界和非显然约定。
5. 从规范中移出过程备注、临时端口和构建编号；有独有证据时归入对应现有记录。普通规范通过 Git 保存旧版，不生成日期副本或备份正文。
6. 合并前确认独有内容去向；移动后重写相对链接和附件路径，检查所有旧路径引用。包内必须可读的 Skill 参考保留随包路径，不用无法打包的链接替代。

维护时机：目录职责、文档职责、生成方式或文件保留规则变化时更新本文。
