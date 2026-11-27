# Charts Design (麦肯锡风格高管决策看板与分析报告套件)

---

本项目使用共享 React 组件构建 MCP 应用、HTML 快照和静态网页。可用能力与宿主接入状态见 [组件清单](docs/implementation/ui-component-inventory.md)，实现与配置见 [Runtime](docs/implementation/dashboard-runtime.md)。

文档总览见 [docs/README.md](docs/README.md)，开发与维护的按任务阅读入口见 [AGENTS.md](AGENTS.md)。

环境统一使用 uv 与 Bun；首次在仓库执行 `bun run setup` 安装锁定依赖。开发默认提交分支与 PR，由 GitHub Actions 执行测试和构建。本地仅在需要预览或更新安装时运行 `bun run ui:prepare`；源码与产物相符时复用，不重复构建。操作与检查范围见 [开发检查与 CI](docs/operations/testing.md)。设计系统资源通过 `bun run ui:package:design` 单独更新。

## 当前真实可用入口

1. **数据资产、指标口径与声明合同**：
   - 业务数据资产：支持 SQLite 事务状态、JSON 镜像与 CSV 导入，项目根目录维护持久资产（`charts-project.json`、`dashboards/`、`data/`）。
   - 指标口径定义规范：见 [指标定义规范](skills/executive-charts/references/metric-definitions.md) 与 [数据格式标准](skills/executive-charts/references/data_formatting_standards.md)。
   - 图表与指标声明：保留 40 种图表规范（`skills/executive-charts/references/chart_catalog.json`）、16 种高管指标卡定义（[指标卡选型](skills/executive-charts/references/kpi-cards.md)）与 7 种构图模式（[布局模板](skills/executive-charts/references/layout_templates.md)）。

2. **CLI 积木式看板资产管理 (`charts-design dashboard`)**：
   - 提供 `init`、`import-csv`、`inspect`、`validate`、`meta`、`add`、`table` 完整资产管理工具。
   - 允许对筛选器、指标卡、图表声明和数据表格进行原子化组装与严格合同校验。

3. **Runtime 后端与 CLI (`charts-design-runtime`)**：
   - 管理多项目路由、SQLite 存储、数据计算、批次修改与版本检查点。
   - 本机项目可直接打开浏览器编辑页与预览页；两者均可保存位置批注，预览页的内容与版本操作保持只读。批注通过本机 HTTP 保存，不需要 MCP 往返或公网。
   - 支持 JSON 配置导出：`charts-design-runtime --root ./boards export <id> --format json --output ./export.json`。
   - 详细接口与数据模式见 [Runtime 说明](docs/implementation/dashboard-runtime.md) 与 [项目资产与加载](docs/implementation/project-runtime.md)。
   - 通过 `bun run native:install` 安装固定版本的预编译 Parquet 导出程序，无需安装 Rust；源码开发可用 `bun run native:build`。服务器容器包含原生程序。`dashboard_export_site` 可导出包含完整运行资源的独立网页，数据格式与交付方式见 [静态部署包](docs/operations/static-deployment.md)。

4. **MCP 协议服务**：
   - 本地 stdio MCP 与自托管 HTTP 远程 MCP（Streamable HTTP + Bearer 令牌）。
   - 有自己的服务器时，可选 [服务器 MCP/API、Neon 数据库和 Cloudflare Pages 网页](docs/operations/self-hosted-server.md#独立服务器neon-与-cloudflare-pages)，不需要腾讯云账号或 Cloudflare Containers。另有 [Cloudflare Containers 方案](docs/operations/self-hosted-server.md#cloudflare-独立部署)；原 CloudBase 发布流程仍可单独使用。
   - 腾讯云独立分享副本支持 8 位数字访问密钥、不过期/7 天/30 天；到期由云端 SCF 删除 COS 数据和访问记录。需要部署私有 COS、HTTPS 网关和 SCF 定时任务，见 [腾讯云分享](docs/operations/self-hosted-server.md#腾讯云在线分享与云端清理)。
   - 版本中心可对明确的已保存版本选择「分享此版本」，权限为「仅查看」或「可批注」。本机项目通过已配置的分享服务发布固定副本，读者页面、数据和批注不依赖作者电脑在线；作者从同一分享记录按需打开原版本反馈。配置见[本机发布与反馈](docs/operations/self-hosted-server.md#本机通过分享服务发布)。
   - 项目编辑使用 `dashboard_get` 读草稿，再用 `dashboard_submit` 一次提交修改、检查全部组件并保存。通过后按 `nextAction=dashboard_preview` 打开已保存版本；检查失败返回 `DOCTOR_FAILED`，保留草稿，不生成检查点。保存不会发布或分享。
   - 规范见 [共享交付流程](skills/executive-charts/references/mcp-delivery.md) 与 [自托管服务器](docs/operations/self-hosted-server.md)。

5. **Seaborn 统计图后端（可选）**：
   - 运行 `uv sync --locked --extra statistics --no-install-project` 后，可基于原始观测数据声明直方图、箱线图、回归散点图，输出纯图产物（SVG/PNG）供嵌入报告。
   - 规范见 [Seaborn 后端说明](docs/implementation/seaborn-backend.md)。

## CLI 工作区使用 (Workspace Flow)

### 打开已有本机项目

```sh
charts-design-runtime --project-root /absolute/path/project \
  --runtime-root /absolute/path/runtime-cache serve --dashboard overview
```

将 `overview` 替换为已有看板或报告的 ID。启动回执提供带权限的 `editUrl`、`viewUrl`；加 `--view` 选择预览作为默认入口。从源码运行时，用 `bun run python -- -m dashboard_runtime` 替换 `charts-design-runtime`。未准备网页资源的源码环境先运行一次 `bun run ui:prepare`。

本地 stdio MCP 的 `dashboard_preview` 继续提供宿主内预览，同时返回普通浏览器的 `browserLinks`。宿主内可通过「在浏览器中批注」进入本机页面；浏览器操作直接连接同进程的 loopback HTTP 服务。重启进程后使用新返回的链接。

### 维护声明资产

CLI workspace 负责将筛选器、KPI、图表和表格组织为清晰的文件资产。开发或 Agent 协作时可以逐块添加、检查和严格校验组件：

```bash
# 1. 初始化空工作区
charts-design dashboard init ./sales-board --title "销售经营看板" --org "经营分析部"

# 2. 添加 KPI 指标卡定义与图表组件
charts-design dashboard add kpi ./sales-board revenue --from ./revenue.kpi.json
charts-design dashboard add chart ./sales-board regional-sales --from ./regional-sales.chart.json

# 3. 关联筛选器与表格
charts-design dashboard add filter ./sales-board region \
  --label "区域" --type multi-select --option 华东=华东 --option 华南=华南 \
  --field region --consumer revenue --consumer regional-sales
charts-design dashboard table set ./sales-board --from ./sales.table.json

# 4. 检查与严格校验资产结构
charts-design dashboard inspect ./sales-board --json
charts-design dashboard validate ./sales-board --strict --json
```

详细工作区命令与组件 schema 见 [工作区说明](skills/executive-charts/references/dashboard-workspace.md)。

## 两条 Skills 生成路径

- **Dashboard 路径**：[executive-charts Skill](skills/executive-charts/SKILL.md)，负责高管业务看板的指标拆解、图表推荐、7 种布局构图和数据建模。
- **分析报告路径**：[analytical-reports Skill](skills/analytical-reports/SKILL.md)，负责以学术单栏规范编写分析报告，包括摘要、章节、图文交叉引用与严谨业务解读。

生成流程与阶段划分见 [生成路径说明](docs/implementation/generation-tracks.md)。两条路径复用共享 React 组件，通过 Runtime 导出 HTML 或打开 MCP 预览。

## 项目结构

```
charts-design/
├── AGENTS.md                           # 任务阅读入口与项目约定
├── README.md                           # 项目入口与常用命令
├── docs/                               # 规范、实现说明与验证记录
│   ├── README.md                       # 文档总览与索引
│   ├── agent/file-management.md         # 文件管理准则
│   ├── implementation/                # Runtime、组件与接口说明
│   ├── reference/                     # 设计规范
│   └── operations/                    # 开发检查、安装、部署与诊断
├── bin/                                # CLI 与 MCP 启动入口
├── deploy/                             # 自托管后端容器镜像与部署配置
├── dashboard_runtime/                  # SQLite 状态、数据计算、查询与 MCP 服务
│   └── examples/academic-report.md      # 分析报告案例唯一 Markdown 基础稿
├── runtime-core/                       # Rust 原生 Parquet 导出与锁定依赖
├── skills/
│   ├── executive-charts/               # 看板设计规范、指标卡、布局模板与 workspace 脚本
│   └── analytical-reports/             # 分析报告 Skill 与学术规范
├── tests/                              # 静态检查、数据与后端单元测试、容器冒烟测试
├── package.json                        # Bun CLI 入口与检查脚本
└── pyproject.toml                      # Python 依赖与包配置
```

## 开源协议

MIT License
