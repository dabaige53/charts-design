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

## 本地准备与构建条件

需要预览、静态导出或安装更新时运行 `bun run ui:prepare`。它核对源码、脚本、配置、锁文件及完整产物；输入不变且产物有效时复用，否则构建一次。唯一应用产物目录为 `runtime-ui/dist/`。

`bun run ui:build` 强制构建；`ui:prepare -- --force` 用于明确排错。设计系统和画布仅在要求更新设计资源时运行 `ui:package:design`。生产构建不从设计归档提取源码。

前端测试使用 Bun，React 用例通过配置加载 DOM 环境。启用真实 Rust→Parquet→浏览器用例时提供 `CHARTS_CORE_BIN`；CI 必须传入同次构建的原生程序。数据正确性检查实际行、类型、缺失值、筛选范围与顺序，不只信任导出回执中的行数。

## CI 作业与产物

工作流定义在 `.github/workflows/`。格式、静态检查、后端、前端、协议与容器分别验证；成功的编译不代替实际协议与宿主验收。UI 和原生产物按提交保存，后续作业复用相同版本；部署镜像仍从源码独立构建，防止打包路径与开发环境不一致。

后端行覆盖率使用 `cargo-llvm-cov` 测量，保留 84% 硬门槛。覆盖率报告与行为用例分别检查；运行时实现更换后需要重新测量，不能沿用旧实现的覆盖结果，也不能通过删除有效检查或排除未覆盖模块达标。

原生程序与 npm 包使用同一产品版本 `vX.Y.Z`，云平台部署独立执行。推送代码或修改 CI 不等于部署生产环境；发布前核对目标提交、版本、镜像/二进制校验与健康返回。

## 测试维护

新增用例优先保护真实失败后果：修订冲突、数据丢失、权限越界、查询范围、传输完整性和渲染声明。每个用例在定义前保留 `@wu-test type=<类型> | scope=<范围> | protects=<失败后果>`。可逆文字改动不另写镜像实现的测试。

性能测量使用明确的数据量、冷/热状态、请求范围和环境。首次候选项、首批明细、筛选、翻页、保存与静态读取分别计时，报告原始样本与中位数；少量样本不声称稳定 P95。公网测量和真实云端写入需要对应环境的明确授权。

文档只记录可复现的现行入口。执行记录由 CI 产物与 Git 历史保存，不维护重复的日期报告。交付说明实际执行的检查与具体未验证边界。
