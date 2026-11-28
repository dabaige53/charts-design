# 开发检查与 GitHub CI

Rust 运行后端与原生 CLI，Bun 管理前端和开发脚本。完整检查在 GitHub Actions 执行；本地选保护本次行为的定向检查，通过后停止，没有新变更或失败证据不重复运行。

## 统一开发环境

```sh
bun run setup
bun run native:build
```

Rust 工具链由 `runtime-core/rust-toolchain.toml` 固定，依赖由 `runtime-core/Cargo.lock` 锁定；前端依赖使用各包的 `package.json` 和 Bun 锁文件。修改依赖时同时提交声明与锁文件。普通安装使用锁定模式，不依赖系统 Python。

发布用户可以安装预编译原生程序，无需本地 Rust 工具链。源码开发用 Cargo 构建。各工作树保留自己的依赖和产物，缓存可按环境指定可写路径。Docker 在 GitHub 或部署平台构建，运行镜像只保留原生程序、共享 UI 和必要系统库。

## 按改动选择检查

| 改动 | 本地定向检查 | CI |
| --- | --- | --- |
| 文档、导航、Skills 说明 | `bun run check:docs`、`bun run check:skills` | 链接、锚点、打包引用 |
| Rust 服务、数据、版本或协议 | 对应 Cargo 测试；必要时 `cargo check` | 格式、Clippy、Rust 测试与原生构建 |
| React、样式、Worker | 对应 Bun 用例；需要时类型检查 | 类型、组件、共享数据与 UI 构建 |
| CLI、安装、部署、构建脚本 | 相关脚本行为检查 | 安装产物、协议和镜像冒烟 |
| Parquet 与静态导出 | 实际编码/解码和相关页面数据用例 | 同一原生产物的 Rust→浏览器互操作 |

在仓库根目录使用 Cargo：

```sh
cargo test --locked --manifest-path runtime-core/Cargo.toml --test runtime_authoring
cargo test --locked --manifest-path runtime-core/Cargo.toml --test runtime_data
cargo fmt --manifest-path runtime-core/Cargo.toml -- --check
```

测试名与工作流以当前源码为准。不要通过放宽断言、跳过或删除仍有用的行为检查来得到绿色结果。本地全量套件、浏览器自动化和目标宿主验收需要当前任务授权。

完整 Rust 套件包含真实 PostgreSQL 工作区、查询与分享集成。运行前启动本机临时 PostgreSQL 17，并将 `CHARTS_TEST_DATABASE_URL` 指向回环地址上的测试管理员连接，例如 `postgresql://postgres:charts-ci-password@127.0.0.1:5432/postgres?sslmode=disable`。每个场景创建独立数据库和受限运行角色，执行正式迁移，再清理测试资产。缺少测试连接时，数据库验证返回失败。无需数据库的定向检查可使用 `--test runtime_authoring` 等单个目标。

## 本地准备与构建条件

需要预览、静态导出或安装更新时运行 `bun run ui:prepare`。它核对源码、脚本、配置、锁文件及完整产物；输入不变且产物有效时复用，否则构建一次。唯一应用产物目录为 `runtime-ui/dist/`。

`bun run ui:build` 强制构建；`ui:prepare -- --force` 用于明确排错。设计系统和画布仅在要求更新设计资源时运行 `ui:package:design`。生产构建不从设计归档提取源码。

前端测试使用 Bun，React 用例通过配置加载 DOM 环境。启用真实 Rust→Parquet→浏览器用例时提供 `CHARTS_CORE_BIN`；CI 必须传入同次构建的原生程序。数据正确性检查实际行、类型、缺失值、筛选范围与顺序，不只信任导出回执中的行数。

## CI 作业与产物

工作流定义在 `.github/workflows/`。主 CI 固定使用 Ubuntu 24.04；`Prepare reusable CI environment` 先通过 [共享环境动作](../../.github/actions/ci-environment/action.yml) 准备可直接运行的环境快照。后续作业恢复已安装好的工具与依赖，命中时不执行安装。首次使用、环境配置或锁文件变化、缓存被淘汰时，才重新准备缺失部分并立即保存；后续测试失败不影响已保存的环境。

环境按职责分别缓存：

| 快照 | 内容与失效条件 |
| --- | --- |
| JavaScript 工具 | 固定 Bun 与 Node 24；环境配置、操作系统或架构变化时更新 |
| Rust 工具 | 固定编译器、rustfmt、Clippy、LLVM 工具及 cargo-llvm-cov；工具链或环境配置变化时更新 |
| 根目录依赖 | production `node_modules`；根包声明、锁文件或 Bun 版本变化时更新 |
| UI 依赖 | 完整 `runtime-ui/node_modules`；UI 包声明、锁文件或 Bun 版本变化时更新 |

环境版本集中在 `.github/ci/environment.json`，Bun 和 Rust 分别沿用仓库版本文件。Node 24 的补丁版本由首次生成的快照固定。需要刷新工具时递增环境 `revision`。锁文件精确匹配时才能复用依赖快照。纯文档改动仅恢复 JavaScript 工具和根目录依赖。快照只保存构建工具和锁定的依赖。

共享 UI 由独立作业构建一次并按提交上传。Rust 预览测试、覆盖率和协议与性能验收下载同一份 UI；验收继续复用本次构建的原生程序。覆盖率与普通 Rust 构建并行运行，使用各自独立的编译缓存和原生产物，不混用插桩结果。

Rust 编译依赖与 Docker 层继续使用独立缓存。PR 可恢复默认分支缓存，并保存自身运行范围内的缓存，重复推送不再必须等待合并后才能复用。部署镜像保留 Debian Bookworm 编译基线，通过固定版本 cargo-chef 将依赖预编译层与业务源码分开；只改源码时复用依赖层，最终镜像仍独立构建并执行真实冒烟检查。构建工具、依赖源码和环境文件不进入生产镜像。

后端行覆盖率使用 `cargo-llvm-cov` 测量。Cargo 用例和使用同次构建的端到端用例共同生成报告，保留 84% 硬门槛。覆盖率报告包含所有运行时模块；单元测试正文统一放在 `runtime-core/tests/unit/`，由源模块通过 `#[cfg(test)]` 引用，避免把测试代码本身计入运行时覆盖率。更换实现后，用新版本重新测量，并继续检查行为用例。

主 CI 的原生测试与覆盖率作业各自启动独立 PostgreSQL 服务；Linux 原生发布检查使用相同版本的临时数据库。覆盖率作业在执行门槛前输出逐文件摘要，并将 `coverage-summary.txt` 与 `coverage.lcov` 一起上传，失败时可直接定位未覆盖路径。

PR 和原生发布的自动测试均在 Linux 执行。原生发布按标签或手动触发，Linux x64 和 ARM64 执行编码与安装检查，macOS 和 Windows 只编译安装包。原生程序与 npm 包使用同一产品版本 `vX.Y.Z`。独立执行云平台部署。发布前核对目标提交、版本和镜像或二进制校验值。部署后从健康接口确认实际版本。

## 测试维护

使用 `bun test tests/integration/neon-workspace.test.mjs` 检查已有 Neon 工作区的版本保存。提供 `CHARTS_CORE_BIN` 和指向已迁移、可丢弃 PostgreSQL 测试库的 `CHARTS_TEST_NEON_DATABASE_URL`。用例使用测试库的运行账号并创建独立的测试项目。

新增用例优先保护真实失败后果：修订冲突、数据丢失、权限越界、查询范围、传输完整性和渲染声明。每个用例在定义前保留 `@wu-test type=<类型> | scope=<范围> | protects=<失败后果>`。可逆文字改动不另写镜像实现的测试。

文档只记录可复现的现行入口。执行记录由 CI 产物与 Git 历史保存，不维护重复的日期报告。交付说明实际执行的检查与具体未验证边界。

## 性能记录

汇报正文用「功能／阶段／耗时」三列。每个阶段说明起点、完成条件和实际处理量。对照前后版本时，使用同一数据、入口和环境，在耗时列并排写两次结果。另记行数、请求数和传输字节数。传输量区分 HTTP 响应体、解码后的内容和导出文件大小。

网页预览从浏览器导航开始计时。分别记录页面首次绘制、KPI 值可见、图表首次绘制、首批明细行可见以及三个组件全部可用。筛选和翻页单独计时，记录是否追加数据请求。用 `bun run test:million --samples 5 --ci-server` 测接口、静态 Worker 和导出。需要比较用户等到内容可见的时间时，在真实浏览器里采样。

原始样本用 `report.json` 或浏览器采样 JSON 保存。记录提交、输入行数、浏览器与运行环境、缓存状态、原始样本和错误。汇总写中位数与最小、最大值。少量样本使用范围。CI 将验收 JSON 上传为 `dashboard-acceptance`，适合跨提交追查。需要定位请求顺序或传输差异时，保留浏览器网络记录中必要的时间、大小和状态。公网测量和真实云端写入需要对应环境的明确授权。
