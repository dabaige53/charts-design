# 开发检查与 GitHub CI

源码、测试、锁文件和工作流配置通过 GitHub 分支与 PR 管理。GitHub Actions 是完整测试和交付构建的执行入口；本地用于编辑、定向排错和明确需要的预览。工作流定义在 `.github/workflows/dashboard-runtime.yml`，命令维护在根目录及 `runtime-ui/package.json`。

## 按改动选择检查

| 改动 | 本地 | GitHub |
| --- | --- | --- |
| 仅文档、导航或历史记录 | 文档目录、链接、锚点与 Skill 入口检查 | 静态检查；跳过 UI 构建、组件测试、Python 矩阵与容器 |
| Python、Node、协议或数据处理 | 直接受影响的用例；需要排错时才执行 | 完整后端与数据测试、共享 UI 资源、容器检查 |
| React、样式、共享 Worker 或依赖 | 按需类型检查；需要预览时运行 `npm run ui:prepare` | 类型检查、构建、组件测试、后端测试与容器检查 |
| CI、开发脚本或未知路径 | 脚本语法与相关局部测试 | 完整工作流 |

本项目的常规 GitHub 工作流按上述范围自动执行，包含 Python、Node、React 组件及容器检查。手动 `workflow_dispatch` 执行完整工作流。本地全量测试仍需针对当前任务的明确授权，不因提交、PR 或云端 CI 授权而自动执行；浏览器自动化和目标宿主验收另行授权。

`docs/` 不承载生产源码，根目录仅保留 `README.md`。目录规则、本地链接和章节锚点由 `bin/check-doc-links.js` 检查。Skill 的随包说明是运行资源，修改 `skills/` 仍进入完整 CI。

## CI 作业与产物

- Static checks：Python ruff、语法、文档与 Skill 链接、开发流程及发布脚本的 Node 检查。
- Shared UI build：安装锁定依赖、类型检查、构建一次，并上传 `shared-ui-<提交号>`；执行 React 组件与 Runtime 交互测试，上传 JUnit 报告。
- Unit tests：Python 3.10、3.13 下载同一 UI 产物并打包到后端，不重复安装前端依赖或构建。检查 Runtime、MCP、Node 数据模块、工作区合同；Runtime 覆盖率下限保留 84%。
- Container image smoke test：独立从源码构建部署镜像，经 HTTP 验证 MCP、预览、下载、非 root 权限和环境文件隔离。保留该独立构建，检查真实部署路径。

前端依赖缓存按锁文件区分。新提交取消同一 PR 的旧 CI；失败时先读取对应作业日志及报告，不在本地重新跑整套。JUnit、覆盖率和 UI 构建产物保留 14 天。构建产物与报告由 Actions 保存，`runtime-ui/dist/`、后端资源副本和本地依赖不提交 Git。

需要使用 GitHub 生成的 UI 时，从目标提交成功的工作流下载 `shared-ui-<提交号>`，解压到该提交检出的 `runtime-ui/dist/`，再执行 `npm run ui:prepare`。脚本核对源码与产物；对应时只打包，不重建。不要把失败或其他提交的产物作为已验证交付。

## 本地准备与构建条件

Python 使用项目解释器和 `pyproject.toml` 中的依赖；运行配置见 [Runtime](../implementation/dashboard-runtime.md#启动与依赖)。前端依赖使用 `npm run ui:install`，按锁文件安装。

日常修改不自动执行 UI 构建。需要本地预览、导出或安装更新时，运行 `npm run ui:prepare`：

1. 比较源码、构建脚本、前端配置、锁文件、设计预览输入及共享 Worker 的内容标识。
2. 输入与完整产物相符时复用；首次准备、输入改变、产物缺失或被修改时构建一次。
3. 成功后将应用资源打包到 `dashboard_runtime/web/dist/`。

`npm run ui:build` 始终强制构建；`npm run ui:prepare -- --force` 强制构建并打包，仅用于排错。设计系统和画布仅在明确要求更新设计资源时运行 `ui:package:design`，普通应用交付不顺带同步。

## 测试维护

- 选择能保护本次行为、边界或已知回归的最小检查；通过后停止，无新改动或失败证据不重复执行。
- 每个新增或修改用例在定义前保留 `@wu-test type=<类型> | scope=<代码范围> | protects=<具体失败后果>`；标注规则与全局约定一致。
- 不通过跳过、删除或放宽断言让 CI 变绿。明确的环境条件可跳过并记录原因，例如本地配置更新器需要 Python 3.11 的 `tomllib`。
- 自动测试通过、构建成功和真实 MCP 宿主验收分别报告；组件测试不替代浏览器或宿主验收。

版本部署由独立的 `cloudbase-release.yml` 执行，流程见 [自托管服务器](self-hosted-server.md#按版本自动发布到-cloudbase)。修改 CI 不自动触发生产部署。

维护时机：开发入口、检查范围、构建复用或交付流程变化时更新本文。
