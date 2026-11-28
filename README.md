# Charts Design

通过 MCP 创建、维护和交付经营看板与分析报告。Rust 运行时统一负责数据、计算、版本、导出和服务；共享 React 界面用于 MCP App、本机编辑器、在线预览与独立网页。

## 开始使用

本地 MCP 客户端启动一个入口，在每次调用中传入项目资产目录 `projectRoot`：

```sh
npx --package charts-design charts-design-runtime mcp --runtime-root /absolute/path/runtime-cache
```

远程服务使用 Streamable HTTP `/mcp` 和 Bearer 令牌。单一连接可处理多个项目；本地 `projectRoot` 为绝对目录，远程为工作区内项目名。连接不会记住上一次调用所选的项目。

npm 首次安装会下载并校验对应平台的 Rust 程序；已有同版本程序直接复用。npm 启动器使用 Node.js，运行 MCP 不需要 Python、Bun 或本地 Rust 工具链。直接使用已下载的二进制时，将命令名换为 `charts-design-core`。本地安装与更新见[安装说明](docs/operations/local-mcp-update.md)，服务器与分享配置见[自托管服务](docs/operations/self-hosted-server.md)。

## 从数据到可交付成果

1. **找到项目与数据。** 修改已有成果先用 `dashboard_get` 读取草稿。新成果在数据和声明已经明确时，可直接用 `dashboard_submit` 的 `createTitle + operations` 初始化；需要先看数据时，创建空容器后调用 `dataset_import`、`dataset_attach` 或 `query_execute`。
2. **检查数据。** 导入回执包含字段、来源、实际指标 ID、修订号和 `nextCalls`。直接执行其中的 `dataset_preview`，无需先创建组件。样本保留空值与字段类型，明确标识完整行数、分页和读取范围。
3. **选择呈现。** 用 `chart_recommend` 的数据形态、绑定要求与设计提示确定候选，再用 `chart_declarations` 批量获取所选图表/KPI 的结构与示例。推荐保留未知条件，自动生成的指标标记为待核实。
4. **提交并核对。** 将相关来源、指标、组件、筛选、布局或报告 Markdown 一起交给 `dashboard_submit`。服务校验并保存同一修订；检查失败保留可修正的草稿。用 `dashboard_view` 一次核对受影响组件与来源，再打开 `dashboard_preview`。
5. **按需要交付。** 保存版本、设为正式发布版、创建独立分享是三个明确动作。可导出 HTML、JSON、CSV 或可继续筛选的静态网页包。

JSON 对象直接作为 MCP 参数，文件不是创作前提。完整示例和恢复规则见[原生创作](skills/executive-charts/references/mcp-authoring.md)与[共享交付](skills/executive-charts/references/mcp-delivery.md)。

## 能力

| 需求 | 支持方式 |
| --- | --- |
| 经营看板 | 指标卡、图表、表格、筛选、联动、粒度切换、稳定布局 |
| 分析报告 | Markdown 正文、图注、来源、交叉引用、脚注与内嵌组件；可选筛选控件 |
| 图形表达 | 40 种预设图表、16 种 KPI 形态、完整 ECharts、自定义 HTML/JavaScript |
| 统计分析图 | 原始观测的直方图、箱线图和 OLS 回归图；Rust 输出 SVG/PNG |
| 数据 | 有界 JSON/CSV 导入、SQLite 表挂接、SQLite/PostgreSQL/DuckDB 只读查询、不可变快照与实时模式 |
| 查看性能 | 按可见组件计算、精确分页、筛选候选项分页、查询缓存、共享 Worker 与 Parquet 分片 |
| 版本与协作 | 草稿、完整检查、不可变保存版、正式发布、恢复、独立位置批注 |
| 交付 | 本机页面、在线编辑/只读页面、固定版本分享、受管文件和静态网页 |

数据、指标口径、比较基准与来源由项目保存。图表推荐和布局是选型帮助，不限制自定义图形，也不替代业务判断。详见[产品约定](docs/agent/PRODUCT.md)和[设计规范](docs/reference/DESIGN.md)。

## CLI

CLI 与 MCP 调用同一 Rust 服务。创建空白成果或打开已有项目：

```sh
charts-design-runtime --project-root /absolute/path/project init overview --title "月度经营"
charts-design-runtime --project-root /absolute/path/project serve --dashboard overview
```

启动回执提供本机编辑页与已保存版本预览页。创建合成演示必须显式加 `--demo`；创建报告用 `--mode report`。

已有声明文件可以直接审阅、导入、提交和导出：

```sh
charts-design-runtime --project-root /absolute/path/project get overview
charts-design-runtime --project-root /absolute/path/project call dashboard_submit --json-file submit.json
charts-design-runtime --project-root /absolute/path/project validate overview
charts-design-runtime --project-root /absolute/path/project export overview --format json --output overview.json
```

`call` 支持 `--json-file -` 从标准输入读取参数；所有原子操作以 `contract` 或连接中的 `charts://contract` 为准。外部工作区导入和文件修改见[声明文件](skills/executive-charts/references/dashboard-workspace.md)。

## Skills 与开发

- [executive-charts](skills/executive-charts/SKILL.md)：从决策问题、数据口径到图表选型、筛选和看板交付。
- [analytical-reports](skills/analytical-reports/SKILL.md)：以证据组织 Markdown 报告，保持正文、图表和指标定义一致。
- [文档目录](docs/README.md)：按产品、实现和运维查找说明。
- [开发入口](AGENTS.md)：源码职责、变更边界与验证要求。

源码开发执行 `bun run setup` 准备锁定依赖，`bun run native:build` 构建运行时。需要本地预览时执行 `bun run ui:prepare`；有效资源直接复用。完整验证由 GitHub Actions 执行，本地只运行与改动相关的检查，见[开发检查](docs/operations/testing.md)。

## 开源协议

MIT License
