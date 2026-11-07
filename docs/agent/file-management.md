# 文件管理

新增、移动、合并或清理文件时，先确定文件用途及维护入口。维护源码、生成产物、项目业务资产分别保存。

## 目录职责

| 位置 | 内容 | 维护方式 |
| --- | --- | --- |
| `README.md`、`AGENTS.md` | 项目快速开始与按任务阅读入口 | 用途、流程或文档路径变化时更新 |
| `docs/` | 项目规范、当前实现说明、操作步骤和已有历史记录 | 每个主题保留一份负责该要求的正文 |
| `docs/agent/` | 文件管理等长期项目准则 | 已确认的项目约定变化时原位更新 |
| `docs/plans/`、`docs/records/`、`docs/adr/` | 按需新增的专项方案、验证记录和架构决定 | 有实际内容时创建；已有清楚路径沿用 |
| `docs/images/`、`docs/performance-results.json` | 文档配套截图与已有性能证据 | 与对应记录一同保留，标明测量范围 |
| `skills/executive-charts/` | Dashboard Skill、组件渲染器、声明、设计规范和脚本 | 维护源码；本地安装指向此目录，避免另存渲染器副本 |
| `skills/analytical-reports/` | 分析报告 Skill 与随包参考材料 | 保留相对引用和随包可用性 |
| `dashboard_runtime/`、`runtime-ui/`、`bin/` | 后端、前端构建与启动更新脚本 | 修改对应维护源码后重新构建 |
| `deploy/` | 自托管服务器的 Dockerfile、compose、systemd 与 nginx 示例 | 服务器参数或运行方式变化时同步 `docs/self-hosted-server.md`；不存放令牌、密钥或 `charts.env` |
| `examples/`、`skills/executive-charts/examples/` | 人工浏览与视觉比较案例 | 作为展示材料，不把案例数据当真实业务输入 |
| `dashboard_runtime/examples/academic-report.md` | 分析报告案例的唯一 Markdown 母稿 | CLI 与 MCP 案例共同读取，避免独立副本 |
| `tests/`、`.github/workflows/` | 自动检查与 CI | 以已有命令及 CI 配置确定检查入口 |

Skill 的 `SKILL.md`、组件旁使用说明和随包参考材料继续保留原位。项目级文档正文放在 `docs/`，不为工具发现另建根目录正文、链接入口或符号链接。适配 Skill 或插件要求时优先改用已有正文；自动发现失败时直接读取实际路径。

## 生成文件

以下目录可重新构建，不独立维护其中的渲染实现：

- `runtime-ui/generated/`：在仓库执行 `npm --prefix runtime-ui run build` 生成。
- `dashboard_runtime/web/dist/`：由同一次前端构建生成，供预览和安装包使用。
- `.runtime-installs/project-20261028/package/runtime-ui/generated/`：既有本机安装包的构建中间文件，由该安装包的 `runtime-ui` 构建生成；维护源码仍在仓库对应目录。此路径是已有安装记录，不保证当前安装正在使用它。

清理生成文件前检查其维护源码和重建入口。重建源码目录不会自动更新其他安装目录或已经打开的宿主页面；安装更新按本地 MCP 更新说明执行。

## 业务资产与临时文件

业务工作区、来源数据和交付文件放在用户指定项目中，不放进 Skill 工具目录。项目内的 `charts-project.json`、`dashboards/` 和 `data/` 属于持久资产；运行缓存和诊断目录可与项目资产分开。

项目模式下，`dashboards/dashboards.sqlite3` 保存事务状态，草稿、检查点和批注 JSON 是自动生成的可读镜像，不另行手工维护。数据版本与历史引用的保留方式见项目存储实现，不因清理缓存删除业务资产。含业务快照、SQL 参数或敏感数据的文件不作为公共仓库产物提交。

临时和备份文件放在 `/private/tmp`，不用日期副本替代 Git 历史。需要长期保留的验收附件放入对应项目的文档位置，并标明日期、对象、环境和结论边界。

## 文档维护

项目准则、设计规范和当前实现说明原位更新；Git 保存旧版。历史记录保留当时事实，标明后续决定与替代关系。未验证的计划不写成已实现，工具返回成功不写成宿主页面已验收。

新增文档时先检查是否已有同类正文。规则只维护一处，定义、条件和例外放在一起；使用说明通过必要链接引用该规则。移动、改名、合并或删除文档时，同步 `AGENTS.md`、`docs/README.md`、正文链接、章节锚点、脚本、检查配置和包发布清单。

维护时机：目录职责、文档职责、生成方式或文件保留规则变化时更新本文。
