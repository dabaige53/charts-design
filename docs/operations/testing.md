# 开发检查与 GitHub CI

源码、测试、锁文件和工作流配置通过 GitHub 分支与 PR 管理。GitHub Actions 是完整测试和交付构建的执行入口；本地用于编辑、定向排错和明确需要的预览。工作流定义在 `.github/workflows/dashboard-runtime.yml`，命令维护在根目录及 `runtime-ui/package.json`。

## 统一开发环境

- Bun 版本维护在 `.bun-version`，包声明与容器采用相同版本。根目录 `bun.lock` 锁定发布工具，`runtime-ui/bun.lock` 锁定前端依赖；两个包分别安装，不混用 npm 或 pnpm 锁文件。
- uv 版本由 `pyproject.toml` 的 `tool.uv.required-version` 固定，CI 和容器使用同版。`.python-version` 选择开发 Python 3.11；运行库保留 Python 3.10 兼容，CI 覆盖 3.10、3.11、3.13。
- `uv.lock` 锁定 Python 直接与间接依赖。开发、统计、MCP 和云端依赖安装到 `.venv`，不依赖共享 Conda 环境、系统 site-packages 或旧 `.mcp-test-deps`。

安装对应版本的 Bun 与 uv 后，在仓库根目录执行 `bun run setup`。该入口使用冻结锁文件安装两套 Bun 依赖和 uv 环境，保存本机解释器配置；迁移旧配置前在系统临时目录保留原件。安装不运行应用构建或测试。

Python 命令使用 `bun run python -- <参数>`，它只启动已准备的解释器，不自动安装依赖；uv 负责环境安装与同步。源码无需安装成 Python 包，通过项目入口加载。`PYTHON` 可显式指定其他环境，缺少解释器时直接报错，不自动回退系统 Python。

修改 Python 依赖后执行 `uv lock`，修改 Bun 包依赖后在对应包目录执行 `bun install`，将声明与锁文件一起提交；普通安装使用 `--locked` 或 `--frozen-lockfile`。单独执行 `uv sync` 会按所选依赖组同步环境，完整开发环境统一回到 `bun run setup`。

JavaScript 与 TypeScript 测试使用 `bun test`，React 测试通过 `runtime-ui/bunfig.toml` 预加载 jsdom；TypeScript 编译器由 Bun 执行。Bun 使用兼容的 `node:` 标准库接口。

Docker 只在 GitHub 或部署平台构建；开发机不必安装 Docker。容器从锁文件安装 Python 生产依赖，用独立 Bun 阶段构建 UI，运行阶段只保留 Python、依赖及已构建资源。SCF 函数按其 Python 3.10 平台打包，依赖从同一 uv 锁文件导出。

## 按改动选择检查

| 改动 | 本地 | GitHub |
| --- | --- | --- |
| 仅文档、导航或历史记录 | 文档目录、链接、锚点与 Skill 入口检查 | 静态检查；跳过 UI 构建、组件测试、Python 矩阵与容器 |
| Python、Bun、协议或数据处理 | 直接受影响的用例；需要排错时才执行 | 完整后端与数据测试、共享 UI 资源、容器检查 |
| React、样式、共享 Worker 或依赖 | 按需类型检查；需要预览时运行 `bun run ui:prepare` | 类型检查、构建、组件测试、后端测试与容器检查 |
| CI、开发脚本或未知路径 | 脚本语法与相关局部测试 | 完整工作流 |

本项目的常规 GitHub 工作流按上述范围自动执行，包含 Python、Bun、React 组件及容器检查。手动 `workflow_dispatch` 执行完整工作流。本地全量测试仍需针对当前任务的明确授权，不因提交、PR 或云端 CI 授权而自动执行；浏览器自动化和目标宿主验收另行授权。

`docs/` 不承载生产源码，根目录仅保留 `README.md`。目录规则、本地链接和章节锚点由 `bin/check-doc-links.js` 检查。Skill 的随包说明是运行资源，修改 `skills/` 仍进入完整 CI。

## CI 作业与产物

- Static checks：Python ruff、语法、文档与 Skill 链接、开发流程及发布脚本的 Bun 检查。
- Shared UI build：安装锁定依赖、类型检查、构建一次，并上传 `shared-ui-<提交号>`；执行 React 组件与 Runtime 交互测试，上传 JUnit 报告。
- Unit tests：Python 3.10、3.11、3.13 下载同一 UI 产物并打包到后端，不重复安装前端依赖或构建。检查 Runtime、MCP、Bun 数据模块、工作区合同；Runtime 覆盖率下限保留 84%。
- MCP 协议测试会启动独立 Python 服务进程；覆盖率配置同时统计这些进程中实际执行的代码。
- Container image smoke test：独立从源码构建部署镜像，经 HTTP 验证 MCP、预览、下载、非 root 权限和环境文件隔离。保留该独立构建，检查真实部署路径。

前端依赖缓存按锁文件区分。新提交取消同一 PR 的旧 CI；失败时先读取对应作业日志及报告，不在本地重新跑整套。JUnit、覆盖率和 UI 构建产物保留 14 天。构建产物与报告由 Actions 保存，`runtime-ui/dist/`、后端资源副本和本地依赖不提交 Git。

需要使用 GitHub 生成的 UI 时，从目标提交成功的工作流下载 `shared-ui-<提交号>`，解压到该提交检出的 `runtime-ui/dist/`，再执行 `bun run ui:prepare`。脚本核对源码与产物；对应时只打包，不重建。交付使用目标提交成功工作流生成的产物。

## 本地准备与构建条件

Python 使用项目解释器和 `pyproject.toml` 中的依赖；运行配置见 [Runtime](../implementation/dashboard-runtime.md#启动与依赖)。前端依赖使用 `bun run ui:install`，按锁文件安装。

日常修改不自动执行 UI 构建。需要本地预览、导出或安装更新时，运行 `bun run ui:prepare`：

1. 比较源码、构建脚本、前端配置、锁文件、设计预览输入及共享 Worker 的内容标识。
2. 输入与完整产物相符时复用；首次准备、输入改变、产物缺失或被修改时构建一次。
3. 成功后将应用资源打包到 `dashboard_runtime/web/dist/`。

`bun run ui:build` 始终强制构建；`bun run ui:prepare -- --force` 强制构建并打包，仅用于排错。设计系统和画布仅在明确要求更新设计资源时运行 `ui:package:design`，普通应用交付不顺带同步。

## 测试维护

- 选择能保护本次行为、边界或已知回归的最小检查；通过后停止，无新改动或失败证据不重复执行。
- 每个新增或修改用例在定义前保留 `@wu-test type=<类型> | scope=<代码范围> | protects=<具体失败后果>`；标注规则与全局约定一致。
- 不通过跳过、删除或放宽断言让 CI 变绿。明确的环境条件可跳过并记录原因，例如本地配置更新器需要 Python 3.11 的 `tomllib`。
- 自动测试通过、构建成功和真实 MCP 宿主验收分别报告；组件测试不替代浏览器或宿主验收。

版本部署由独立的 `cloudbase-release.yml` 执行，流程见 [自托管服务器](self-hosted-server.md#按版本自动发布到-cloudbase)。修改 CI 不自动触发生产部署。

维护时机：开发入口、检查范围、构建复用或交付流程变化时更新本文。
