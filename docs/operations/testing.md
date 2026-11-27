# 开发检查与 GitHub CI

源码、测试、锁文件和工作流配置通过 GitHub 分支与 PR 管理。GitHub Actions 是完整测试和交付构建的执行入口；本地用于编辑、定向排错和明确需要的预览。工作流定义在 `.github/workflows/dashboard-runtime.yml`，命令维护在根目录及 `runtime-ui/package.json`。

## 统一开发环境

- Bun 版本维护在 `.bun-version`，包声明与容器采用相同版本。根目录 `bun.lock` 锁定发布工具，`runtime-ui/bun.lock` 锁定前端依赖；两个包分别安装，不混用 npm 或 pnpm 锁文件。
- uv 版本由 `pyproject.toml` 的 `tool.uv.required-version` 固定，CI 和容器使用同版。`.python-version` 选择开发 Python 3.11；运行库保留 Python 3.10 兼容，CI 覆盖 3.10、3.11、3.13。
- `uv.lock` 锁定 Python 直接与间接依赖。开发、统计、MCP 和云端依赖安装到 `.venv`，不依赖共享 Conda 环境、系统 site-packages 或旧 `.mcp-test-deps`。

安装指定版本的 Bun 和 uv 后运行 `bun run setup`。只改后端时可用 `bun run setup -- --backend-only`，跳过 UI 依赖下载。需要统计图、云后端或 CloudBase 发布工具时加 `--full`。默认保留已存在的 Python 可选依赖。需要网页资源时另行运行 `bun run ui:prepare`。

原生导出是独立的 Rust Cargo 包，工具链由 `runtime-core/rust-toolchain.toml` 固定，依赖由 `runtime-core/Cargo.lock` 锁定。需要使用已发布的 Parquet 程序时执行 `bun run native:install`；修改原生源码或版本尚未发布时执行 `bun run native:build`，将 release 二进制准备到忽略提交的 `dashboard_runtime/native/<平台>-<架构>/`。普通查询与旧 JSON 导出不因此要求用户安装 Rust。

各工作树使用自己的 `.venv` 和 `node_modules`。初始化脚本默认把 Bun 缓存放在工作树的 `.runtime-cache/bun`，避免受限进程写入用户目录失败。可通过 `BUN_INSTALL_CACHE_DIR` 指定可写的共享缓存，uv 缓存可由 `UV_CACHE_DIR` 指定。macOS 安装使用 `/private/tmp`。

Python 命令使用 `bun run python -- <参数>`，它只启动已准备的解释器，不自动安装依赖；uv 负责环境安装与同步。源码无需安装成 Python 包，通过项目入口加载。`PYTHON` 可显式指定其他环境，缺少解释器时直接报错，不自动回退系统 Python。

修改 Python 依赖后执行 `uv lock`，修改 Bun 包依赖后在对应包目录执行 `bun install`，将声明与锁文件一起提交。普通安装使用 `--locked` 或 `--frozen-lockfile`。安装全部可选依赖使用 `bun run setup -- --full`。

JavaScript 与 TypeScript 测试使用 `bun test`，React 测试通过 `runtime-ui/bunfig.toml` 预加载 jsdom；TypeScript 编译器由 Bun 执行。Bun 使用兼容的 `node:` 标准库接口。

Docker 只在 GitHub 或部署平台构建；开发机不必安装 Docker。容器从锁文件安装 Python 生产依赖，用独立 Bun 阶段构建 UI，运行阶段只保留 Python、依赖及已构建资源。SCF 函数按其 Python 3.10 平台打包，依赖从同一 uv 锁文件导出。

## 按改动选择检查

| 改动 | 本地 | GitHub |
| --- | --- | --- |
| 仅文档、导航或历史记录 | 文档目录、链接、锚点与 Skill 入口检查 | 静态检查；跳过 UI 构建、组件测试、Python 矩阵与容器 |
| Python、Bun、协议或数据处理 | 直接受影响的用例；需要排错时才执行 | 完整后端与数据测试、共享 UI 资源、容器检查 |
| React、样式、共享 Worker 或依赖 | 按需类型检查；需要预览时运行 `bun run ui:prepare` | 类型检查、构建、组件测试、后端测试与容器检查 |
| CI、开发脚本或未知路径 | 脚本语法与相关局部测试 | 完整工作流 |
| Rust 原生导出或 Parquet 读取 | 对应 Cargo 用例及静态格式兼容用例 | Rust 检查与构建，Python/网页跨语言读取及导出回归 |

GitHub 工作流按上述范围自动执行。手动运行时可选 `acceptance_only`，只构建必要产物并跑百万行验收。常规 PR 检查保留 Python、Bun、React 组件与容器验证。本地全量测试、浏览器自动化和目标宿主验收均需当前任务明确授权。

`docs/` 不承载生产源码，根目录仅保留 `README.md`。目录规则、本地链接和章节锚点由 `bin/check-doc-links.js` 检查。Skill 的随包说明是运行资源，修改 `skills/` 仍进入完整 CI。

## CI 作业与产物

- Static checks 包含 Ruff、实时查询和验收入口的 Pyright、语法、文档链接、开发流程与发布脚本验证。
- Native Parquet exporter：锁定 Rust 的格式、Clippy、测试及 release 构建，向 UI 和 Python 作业交付同一二进制。容器仍在独立构建阶段编译，运行阶段不携带 Rust 工具链。
- Native runtime packages：独立工作流在原生程序或安装器变更的 PR 中验证五个目标平台，使用实际产物检查安装器；发布标签才会创建原生 GitHub Release，不部署服务。
- Shared UI build：安装锁定依赖、类型检查、构建一次，并上传 `shared-ui-<提交号>`；执行 React 组件与 Runtime 交互测试，上传 JUnit 报告。
- Unit tests 覆盖 Python 3.10、3.11、3.13，复用同一 UI 产物。Bun 数据模块套件在 3.11 作业执行一次，另两个版本仅保留依赖 Python 的 JavaScript 计算一致性用例。Runtime 覆盖率下限保留 84%。
- Container image smoke test：独立从源码构建部署镜像，经 HTTP 验证 MCP、预览、下载、非 root 权限和环境文件隔离。保留该独立构建，检查真实部署路径。
- Dashboard performance acceptance 复用同次构建的原生程序和 UI。可执行代码 PR 跑 48 行，默认分支和手动触发跑百万行。测量在 GitHub 托管的 Linux 执行器内完成。

前端依赖缓存按锁文件区分。新提交取消同一 PR 的旧 CI；失败时先读取对应作业日志及报告，不在本地重新跑整套。JUnit、覆盖率和 UI 构建产物保留 14 天。构建产物与报告由 Actions 保存，`runtime-ui/dist/`、后端资源副本和本地依赖不提交 Git。

`runtime-ui/src/static-data.test.ts` 在设置 `CHARTS_CORE_BIN` 时执行真实 Rust→Parquet→网页读取检查，未提供原生程序的本地环境明确跳过这两项跨语言用例；CI 的 native 作业产物为必需依赖，并设置该路径。Python 导出测试还使用打包 Worker 核对实际分片，不将 receipt 行数当作数据正确性证据。

需要使用 GitHub 生成的 UI 时，从目标提交成功的工作流下载 `shared-ui-<提交号>`，解压到该提交检出的 `runtime-ui/dist/`，再执行 `bun run ui:prepare`。脚本核对源码与产物；对应时只打包，不重建。交付使用目标提交成功工作流生成的产物。

## 本地准备与构建条件

Python 使用项目解释器和 `pyproject.toml` 中的依赖；运行配置见 [Runtime](../implementation/dashboard-runtime.md#启动与依赖)。前端依赖使用 `bun run ui:install`，按锁文件安装。

日常修改不自动执行 UI 构建。需要本地预览、导出或安装更新时，运行 `bun run ui:prepare`：

1. 比较源码、构建脚本、前端配置、锁文件、设计预览输入及共享 Worker 的内容标识。
2. 输入与完整产物相符时复用；首次准备、输入改变、产物缺失或被修改时构建一次。
3. 成功后将应用资源打包到 `dashboard_runtime/web/dist/`。

`bun run ui:build` 始终强制构建；`bun run ui:prepare -- --force` 强制构建并打包，仅用于排错。设计系统和画布仅在明确要求更新设计资源时运行 `ui:package:design`，普通应用交付不顺带同步。

## 测试维护

### 一键数据、功能和性能验收

百万行回归优先用 GitHub Actions 的 [Dashboard runtime](../../.github/workflows/dashboard-runtime.yml)。在 **Run workflow** 选择目标分支并启用 `acceptance_only`，下载作业的 `dashboard-performance` 报告。执行器启动作者服务器和静态分享页，使用合成数据。真实 Cloudflare 及自有服务器的公网耗时通过下面的显式配置测量。

本机排错时，用 `bun run setup` 和 `bun run ui:prepare` 准备依赖和 UI，用 `bun run native:install` 或 `bun run native:build` 准备支持 `--single-file` 的 Parquet 程序。验收在生成数据前检查 Node.js、UI 和原生程序。

| 命令 | 覆盖范围 |
| --- | --- |
| `bun run test:data` | 生成 48 行航线测试项目，包含四个看板和一份报告 |
| `bun run test:function` | 验证 MCP 发现、只读预览、草稿保存、正式发布、项目批注、分享包和 D1 的固定版本行为 |
| `bun run test:performance` | 记录首次候选项、Worker 启动、首批明细、应用筛选和翻页校验 |
| `bun run test:million` | 用同一套流程验证一百万行，独立校验行数和筛选结果 |

使用 `--output /private/tmp/charts-verify` 保存测试项目和 `report.json`，用同一个目录可复用初始化数据。功能验收每次在独立的小型项目执行保存、发布和批注检查，测量和待确认的线上请求使用原测试项目。加 `--ci-server` 可在本机复现 GitHub 作业的作者服务器步骤。失败时查看报告的 `phase` 和对应日志。报告记录首次耗时、各次样本、中位数与 P95，样本较少时以原始值为准。

`test:function`、`test:performance` 和 `test:million` 可加 `--online`。通过环境提供 `CHARTS_SHARE_SERVICE_URL` 和 `CHARTS_SHARE_SERVICE_TOKEN`。测试 Pages 快照时设置 `CHARTS_SHARE_PARQUET_LAYOUT=single`，并准备与上线版本匹配的可信 UI 构建。脚本校验线上 Worker 与本机构建一致，再用本机 Worker 读取线上数据，同时检查读者密钥、批注重试和作者只读反馈。成功后自动撤销本轮测试链接。加 `--keep-share` 保留链接七天。中断后用原输出目录与参数重试，会继续使用同一个发布请求 ID。

`test:function`、`test:performance` 和 `test:million` 均可设置 `CHARTS_TEST_MCP_URL`、`CHARTS_TEST_MCP_TOKEN` 和 `CHARTS_TEST_MCP_PROJECT`，测量自有服务器作者页面。先在指定测试项目初始化同一行数的航线数据。脚本从 MCP 取签名编辑和预览链接，再走网页使用的 HTTP 接口，验证候选值和筛选明细与本机一致。Cloudflare 和作者服务器可独立测量。

报告按环境记录为 `localAuthor`、`ciAuthorServer`、`serverAuthor`、`localShare` 和 `cloudflareShare`。作者端分别记录编辑和预览的 HTML、首个组件、首批十行明细和首次筛选。分享端记录页面资源和实际查询 Worker 的明细耗时与请求数。新 Pages 分享对单数据集样例只允许一次 Parquet 请求。HTML 和资源时间分别记录收到响应头和读完响应体。[历史实测记录](../records/2026-11-27-one-command-acceptance.md)。

### 可重复使用的看板与报告

[合成验收项目](../../tests/fixtures/charts_acceptance.py)生成同一批 48 条航线经营记录和五份页面配置。四个看板页覆盖总览、运量与运力、区域与渠道、可筛选明细，使用六种标准指标卡。分析报告使用同一批数据说明月度、区域和渠道变化。

```sh
PYTHONPATH=. bun run python -- tests/fixtures/charts_acceptance.py --output /private/tmp/charts-acceptance
```

在本机或自有服务器的测试项目中，将生成的 JSON 作为 `dashboard_create.document` 导入，再用 `dashboard_submit` 保存。打开总览，通过「切换看板」检查多个页面。月份、区域、航线类型和销售渠道常显，舱位在「更多筛选」。未筛选的收入应为 3,383.09 万元，直营筛选后应剩 24 条记录。同一套配置可用于静态导出和固定版本分享验收。

- 选择能保护本次行为、边界或已知回归的最小检查；通过后停止，无新改动或失败证据不重复执行。
- 每个新增或修改用例在定义前保留 `@wu-test type=<类型> | scope=<代码范围> | protects=<具体失败后果>`；标注规则与全局约定一致。
- 不通过跳过、删除或放宽断言让 CI 变绿。明确的环境条件可跳过并记录原因，例如本地配置更新器需要 Python 3.11 的 `tomllib`。
- 自动测试通过、构建成功和真实 MCP 宿主验收分别报告；组件测试不替代浏览器或宿主验收。

版本部署由独立的 `cloudbase-release.yml` 执行，流程见 [自托管服务器](self-hosted-server.md#按版本自动发布到-cloudbase)。修改 CI 不自动触发生产部署。

自有服务器使用独立标签 `server-vX.Y.Z`，版本号须与 `package.json` 一致。推送标签触发 `server-release.yml`。任务构建默认 SQLite 作者镜像和可选 Pages 分享代理，验证镜像和代理路由，再发布两个包、远程 MCP 客户端配置和 SHA256 校验文件。生产部署另行执行。

维护时机：开发入口、检查范围、构建复用或交付流程变化时更新本文。
