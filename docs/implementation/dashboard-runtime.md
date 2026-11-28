# Runtime：架构、配置与接口入口

一个 Rust 服务实现 CLI、本地 stdio MCP、自托管 Streamable HTTP 和网页接口。数据、计算、版本、验证与导出共用同一套实现；共享 React 应用负责展示和交互。

## 模块职责

维护代码位于 `runtime-core/src/runtime/`。

| 模块 | 职责 |
| --- | --- |
| `service.rs`、`cli.rs` | 业务操作与统一命令入口 |
| `contract.rs`、`discovery.rs` | 工具结构、图表声明、示例和推荐 |
| `dataset_authoring.rs`、`model.rs`、`validation.rs` | 有界输入、原子声明操作和完整语义验证 |
| `store.rs`、`versions.rs` | 项目事务、数据引用、草稿、保存版、发布与批注 |
| `data.rs`、`query.rs`、`view.rs`、`encoding.rs` | 数据查询、分页、聚合、绑定和当前视图 |
| `mcp.rs`、`server.rs`、`transport.rs` | 协议、项目路由、权限、完整结果和诊断 |
| `statistics.rs` | 直方图、箱线图、OLS 回归与 SVG/PNG |
| `assets.rs`、`exports.rs`、`deployment.rs` | 共享应用、受管文件与静态网页包 |
| `cloud.rs`、`cloud_assets.rs`、`cloud_data.rs`、`object_storage.rs` | 云端状态、不可变对象与授权数据 |

工具、操作与图表静态声明位于 `runtime-core/resources/`，随原生程序编译；动态校验、推荐与业务逻辑原生执行。展示组件接收 props 和事件，不直接访问数据库；应用适配层负责工具调用、查看状态和结果合并。

## 启动与依赖

`charts-design-runtime` 是原生程序的统一启动器，`charts-design` 是简写；直接运行二进制时使用 `charts-design-core`，运行参数相同。npm 安装阶段准备并验证原生程序；处理 MCP 请求时不下载或编译依赖。启动器使用 Node.js，运行服务不依赖 Python 或 Bun。

```sh
charts-design-runtime --project-root /absolute/path/project --runtime-root /absolute/path/cache init overview
charts-design-runtime --project-root /absolute/path/project --runtime-root /absolute/path/cache serve --dashboard overview
charts-design-runtime --runtime-root /absolute/path/cache mcp
```

`init` 创建空白文档；只有 `--demo` 才插入合成数据。`--mode report` 创建分析报告。`serve` 返回本机回环地址的 `editUrl` 和 `viewUrl`，`--view` 选择预览作为默认入口。编辑页读取草稿，预览页读取已保存版本；内容编辑与批注权限独立。

共享 UI 的唯一产物目录为 `runtime-ui/dist/`。源码开发需要预览或导出时执行 `bun run ui:prepare`，有效产物直接复用；缺少资源返回 `UI_UNAVAILABLE`。可用 `CHARTS_UI_DIST` 显式指定完整产物目录。Bun 用于安装、前端与开发脚本，Rust 依赖由 Cargo 锁定，详见[开发检查](../operations/testing.md)。

本地服务支持空闲退出；请求执行期间不计空闲，界面仅在可见时保活。stdio 的 stdout 只承载协议，诊断写 stderr。更新后的连接和预览需要使用对应构建，见[本地更新](../operations/local-mcp-update.md)。

## MCP 发现与项目选择

每次项目调用显式传 `projectRoot`：本地为资产目录绝对路径，远程为工作区内项目名。不传时仅使用启动默认值；请求不会改变后续调用的项目。工具、资源、分块和诊断保持同一项目路由，详见[项目资产](project-runtime.md#单入口多项目)。

| 发现入口 | 内容 |
| --- | --- |
| `tools/list` | 当前连接的作者工具、参数、影响标记与 App 元信息 |
| `charts://contract` | 同一份传输适配后的工具结构、页面回调与原子操作约定 |
| `charts://catalog`、`charts://declarations` | 图表、KPI、绑定与完整声明 |
| `chart_declarations` | 不带选择时返回索引；`code` 选一个，`codes` 选 1–8 个唯一代码 |
| `charts://examples`、`generation_examples` | 明确标记为合成数据的完整案例，读取不创建资产 |
| `charts://layouts` | 可选布局建议，显式布局同样可用 |

同一构建的声明可以复用。批量声明只携带一份公共合同，各预设附带完整示例；业务使用必须替换数据、单位、阈值和叙述。工具定义以打包合同为准，不在文档维护第二份枚举。

`chart_recommend` 按已知数据形态排序。未知指标数、时间字段和类别数量保持未知。需要筛选重算时传 `requiresFilterBinding: true`，核对候选的 `bindingMode`、`requirements`、`cautions`、`fit` 和 `shapeMismatches`。动态编码需要显式映射。涉及相关系数重算时，核对推荐的计算条件。已有图形继续按分析问题和数据形态参与排序。

## 编辑与结果确认

新成果已有初始内容时，使用 `dashboard_submit` 的 `dashboardId + createTitle + operations`。JSON 对象直接作为工具参数。服务创建前检查整批声明、来源和数据引用，非法初始内容不留下空文档。已有 ID 返回冲突。

修改已有成果先读 `dashboard_get`，用返回的 `revision` 作为 `expectedRevision`。`dashboard_submit` 写入相关修改、检查完整草稿并保存一个检查点；可省略 `operations`，只检查和保存导入后的草稿。检查失败返回 `DOCTOR_FAILED`，保留草稿供修正。数据库、计算和对象存储分阶段执行。回执不明确时，先读取实际状态。

`dashboard_get` 读取可编辑草稿，`dashboard_view` 读取计算结果。用 `responseMode: "patch"`、必要的 `componentIds` 和 `includeEvidence: true` 一次核对结果、口径与来源；完成后打开 `dashboard_preview` 查看保存版。逐项设计规则见[共享交付](../../skills/executive-charts/references/mcp-delivery.md)。

MCP 文档写入默认 `responseMode: "summary"`，返回看板 ID、顶层修订、受影响组件、数量和操作元信息。数据写入另含字段、来源、模式、按实际 ID 索引的指标定义，以及可直接执行的 `nextCalls`。重用返回的指标 ID；自动推断的求和指标仍为 `unverified`。

`nextCalls` 保留项目、修订及数据版本，供调用方选择执行，不是自动队列。完整草稿可用 `dashboard_get` 或写入时的 `responseMode: "full"` 获取。MCP 编辑器显式请求完整结果；CLI、共享服务和 HTTP 保留各自完整响应。大结果遵循[完整结果传输](../operations/mcp-transport-diagnostics.md)。

保存、正式发布和独立分享分别执行：

| 动作 | 工具与结果 |
| --- | --- |
| 保存版本 | `dashboard_submit` 检查并保留不可变修订 |
| 设为正式发布版 | `dashboard_publish` 指向明确的已保存修订 |
| 创建访客副本 | `dashboard_share_publish` 使用已保存修订与稳定 UUID v4 `requestId` |

分享不修改草稿、保存版或正式发布指针。未知分享回执沿用原参数与请求 ID 重试。分享读者是否能新增批注由独立权限决定。历史、删除与分享反馈见[项目资产](project-runtime.md#保存发布与恢复)。

## 页面元信息与组件声明

`manifest.title` 是页面标题。`set_meta` 整体替换 `iconKey`、`subtitle`、`org`、`system` 和 `statusText`，空对象清除元信息。长度、枚举和操作限制以当前合同为准。

组件使用稳定 ID、来源、数据集与指标引用、渲染配置和断点布局。预设、完整 ECharts、自定义 HTML/JavaScript 均有明确声明，见[渲染入口](echarts-options.md)。统计图按原始观测独立计算，见[统计图](statistical-charts.md)。结构图与组件的真实标记、绑定和含义一起维护，不使用虚构业务值。

报告的唯一正式源文为 Markdown；`chart` 围栏引用组件，图注、来源与脚注随源文保存，见[生成路径](generation-tracks.md)。

## 数据导入与查询来源

| 输入 | 入口与边界 |
| --- | --- |
| 小型 JSON / CSV | `dataset_import`，最多 20,000 行、16 MiB；`rows` 与 `csvText` 二选一 |
| 已配置 SQLite 表 | `dataset_attach`，流式导入不可变数据版本，先检查目标修订 |
| SQL | `query_execute`，使用管理员配置的 SQLite、PostgreSQL 或 DuckDB 只读连接 |
| 已有数据版本 | `put_dataset_ref`，字段、版本、行数与内容元信息必须匹配且目标项目可读 |
| 大型远程数据 | 分块上传，完成后校验数据版本。自有服务器的 SQLite 工作区将暂存分块保存在私有运行目录 |

CSV 支持 UTF-8 BOM、带引号的单元格、空值和显式字段类型。重复/空表头、错列数、不完整引号与非法数值会被拒绝。默认推断保护前导零标识符；空数据必须提供字段声明。单位、百分比比例、主键和聚合口径需要按来源确认，不从名称自动认证。

`dataset_preview` 在没有组件时也能读取字段、完整行数和默认 20 行样本，最多 100 行，支持 offset。样本来自所选数据集的未筛选数据。需要完整统计时，在来源执行明确的聚合查询。数据引用和预览可固定 `expectedRevision` 与 `dataVersion`，不一致返回冲突。

`--sources FILE` 是操作员提供的连接别名配置。工具只接收别名、只读 SQL 和绑定参数，不接受任意数据库路径或新的凭据。查询只允许单条只读语句，执行时间与行数有上限；参数不拼接进 SQL。

快照模式将查询结果保存为不可变数据。实时模式保存查询声明和字段，每次请求读源库；临时行仅存在于请求及短期内存响应缓存，不写入项目数据、诊断日志或持久结果缓存。静态导出需要固定快照。

## 导出与验证

`dashboard_export` 生成当前计算视图的 HTML 或完整 JSON，`dataset_export` 输出当前明确范围的 CSV，`dashboard_export_site` 打包完整使用数据和应用资源。静态包保留浏览器筛选能力，见[静态部署](../operations/static-deployment.md)。导出通过受管 ID 读取，不接受任意文件路径。

数据、来源、指标定义和未验证状态在文档中保留。Doctor 检查声明、不可变引用、组件计算和统计产物；成功表示运行与结构检查通过，业务定义仍需对照实际来源。诊断记录请求编号、阶段、耗时、字节数、修订及构建标识，不记录业务行和凭据。
