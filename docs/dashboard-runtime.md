# Runtime：架构、配置与接口入口

Runtime 复用同一套 Service，为 CLI、本地 stdio MCP、自托管 HTTP MCP 和网页编辑器提供数据、指标计算、版本与文件导出。看板和报告使用共享 React 应用；视图切换不执行上游 SQL，也不生成业务结论。

## 模块职责

| 维护入口 | 职责 |
| --- | --- |
| `service.py` | 工具执行、数据计算编排与返回结果 |
| `tool_contract.py`、`contract.py` | 工具用途、参数说明、操作结构与发现资源 |
| `mcp_server.py`、`project_routing.py` | MCP 协议适配、请求项目选择与结果传输 |
| `store.py`、`project.py`、`local_data.py` | 事务状态、草稿/检查点、批注与不可变数据 |
| `local_view.py`、`bindings.py` | 当前范围的聚合、表格分页及显式指标绑定 |
| `server.py`、`http_app.py` | 自托管远程服务与本机网页入口 |
| `runtime-ui/src/` | 展示组件、应用状态、布局和宿主能力适配 |

展示组件接收 props 和事件，不访问数据库或直接调用 MCP；应用适配层管理工具请求、结果合并和宿主能力。画布与应用共享组件，分别构建与打包。业务状态通过 Service 修改，不手工维护 SQLite 的 JSON 镜像。

## 启动与依赖

Python 版本和可选依赖以 `pyproject.toml` 为准。使用项目选定的解释器；下列 `python3` 表示该解释器。

```sh
python3 -m dashboard_runtime --root ./boards init demo
python3 -m dashboard_runtime --root ./boards serve
```

普通 `init` 创建空白文档，只有显式 `--demo` 才插入合成数据。业务目录包含数据快照、来源 SQL 与参数，不提交到公共仓库。报告创建和源文约定见 [生成路径](generation-tracks.md)。

共享应用先构建，再显式打包到后端：

```sh
npm run ui:build
npm run ui:package
```

缺少资源时预览返回 `UI_UNAVAILABLE`。构建与打包命令维护在 `package.json` 和 `runtime-ui/package.json`；设计组件包通过独立入口更新，不隐式改写画布。

Node 启动器读取项目根目录忽略的 `.charts-runtime-env.json`：

```json
{
  "python": "/absolute/path/to/python",
  "isolated": true,
  "dependencies": ".mcp-test-deps",
  "cache": ".runtime-cache",
  "browsers": ".browser-cache"
}
```

用同一解释器安装 `pyproject.toml` 声明的依赖。`isolated` 与依赖目录同时配置时，启动器不加载共享 Python site-packages；`PYTHON` 可显式覆盖解释器。`PYTHONPATH`、缓存与浏览器路径的构造由 `bin/python-runtime.js` 维护，不另开一套环境加载方式。

本地 Python 工作进程和网页服务器在没有请求或可见预览时按配置空闲退出；请求执行期间不计空闲。Node MCP 启动器保留 stdio 连接，并在下次请求恢复工作进程与初始化；直接 Python MCP 退出后需重连。App 仅在可见时保活，不增加后台轮询。超时参数与默认值以 `__main__.py`、`lifecycle.py` 为准。

## MCP 发现与项目选择

```sh
node /absolute/path/charts-design/bin/dashboard-runtime.js --runtime-root /absolute/path/runtime-cache mcp
```

单入口服务多个项目。每次项目请求显式传入 `projectRoot`；本地使用资产目录绝对路径，远程使用工作区内项目名。请求不会选中一个供后续调用沿用的“当前项目”。默认项目、旧集中存储及 Router 转发约定统一见 [项目资产与加载](project-runtime.md)。

注册由既有注册管理流程维护；生成内容不为每个业务项目新增注册或改写 Agent 配置。更新安装与重连见 [本地更新](local-mcp-update.md)。日志写 stderr，stdout 只承载协议消息。

| 发现入口 | 内容 |
| --- | --- |
| `tools/list` | 当前安装与传输实际提供的工具、参数、影响标记和 App 可见范围 |
| `charts://contract` | 同一份传输适配后的工具定义、原子操作结构和编辑约定 |
| `chart_catalog`、`chart_declarations` | 当前预设、指标卡、声明要求、示例和绑定能力 |
| `generation_examples`、`charts://examples` | 明确标记为合成数据的案例；读取不创建资产 |
| `layout_templates`、`charts://layouts` | 可选构图建议；显式布局继续可用 |

工具定义由 `tool_contract.py` 维护，输入结构说明参数来源、默认值和替换影响。修改定义时同步发现资源与调用方，不在文档手工复制工具枚举。

`runtime_keepalive`、`runtime_report_error` 与本地 `dashboard_export_open` 标为 App 专用。可见范围是宿主路由规则，不是服务器鉴权。Agent 读取诊断和下载受管导出，不代替客户端上报渲染完成或触发桌面文件按钮。远程服务额外提供签名分享工具，并隐藏桌面文件操作。

## 编辑与结果确认

写操作使用最新 `expectedRevision`，一次 patch 的操作原子提交。项目草稿、检查点、独立批注、恢复及冲突恢复统一由项目存储约定管理；标准交付顺序见 [共享交付流程](../skills/executive-charts/references/mcp-delivery.md)。

`dashboard_get` 读取可编辑草稿，不等于预览当前展示的检查点；实际计算结果通过 `dashboard_view` 取得。检查失败不能报告保存完成。MCP 用 `isError` 和结构化错误标识失败；确认 `ok`、检查报告与文档版本后再展示。响应丢失或过期时先读取现有状态，不能盲目重放写入。

预览工具固定名为 `dashboard_preview`，UI 资源 URI 带运行版本与构建标识。宿主决定显示为对话卡片或面板，正常 MCP 连接不等于 MCP App 界面已验收。分块、资源过期和诊断字段见 [传输与诊断](mcp-transport-diagnostics.md)。

## 页面元信息与组件声明

页面标题使用 `manifest.title` / `set_title`。`manifest.meta` 提供 `iconKey`、`subtitle`、`org`、`system`、`statusText`；`set_meta` 整体替换，`{}` 清空。文本长度、枚举和兼容读取以当前操作结构与校验器为准；没有 meta 的旧导入仍可读取 `originalWorkspace.meta`。

组件声明保存稳定 ID、来源、数据集与指标引用、渲染配置和断点布局。预设、完整 ECharts 与自由 HTML/JavaScript 均通过明确声明进入；执行隔离、原生覆盖与绑定限制见 [渲染与覆盖](echarts-options.md)。历史 `kind=chart` 保留兼容读取，新组件遵循当前声明要求。

KPI 内容边界维护在产品规则，形态接口与接入状态维护在组件清单。不能把非 KPI 的 subtitle 规则套到 KPI，也不能从标题推断目标、同比基期或指标公式。

```sh
python3 -m dashboard_runtime --root ./boards import-workspace imported --path ./old-workspace
```

工作区导入保留原图表、指标卡和表格声明，不把复杂图表替换为普通柱状图或文本。已有快照不会因导入而得到动态筛选能力；历史已丢失字段需要从原资产恢复，不能由 Runtime 推造。

## 数据导入与查询来源

```sh
python3 -m dashboard_runtime --root ./boards call dataset_import --json-file import.json
```

`dataset_import` 明确提供 `rows` 或 `csvText` 其中一种，不能同时提供，也不能都省略。目标数据集存在时替换其数据与元信息。推断得到的数值指标是未复核的默认求和，业务定义、单位和粒度仍需确认。需要保留数字标识或前导零时，用 JSON 字符串明确类型。整份 schema-v2 文档可通过 `import NEW_ID --file artifact.json` 创建新看板。

SQL 执行只连接运维配置的 SQLite 来源别名；展示其他引擎 SQL 不代表已建立连接。别名配置为：

```json
{"analytics":{"engine":"sqlite","path":"/absolute/path/analytics.sqlite3"}}
```

```sh
python3 -m dashboard_runtime --root ./boards --sources ./sources.json call query_execute --json-file query.json
```

```json
{
  "dashboardId":"demo","expectedRevision":1,"datasetId":"sql-result",
  "connection":"analytics",
  "sql":"SELECT region, SUM(revenue) AS revenue FROM sales WHERE month >= :start GROUP BY region",
  "parameters":{"start":"2026-01"}
}
```

查询连接采用只读模式、授权器和函数限制；不接受扩展加载、ATTACH、PRAGMA、DDL 或 DML。时间与行数超限明确失败，不静默截断。查询成功时将 SQL、参数、别名、引擎、耗时、时间与行数和快照一起保存；调用方提供的来源只标记为 supplied，不冒充 runtime-executed。

`query_inspect` 读取来源而不执行 SQL；`semantic_inspect` 使用实际保存的业务定义和聚合规则。`reviewed` 是说明状态，不是企业审批。完整本地数据导入、不可变版本与分页计算由项目数据流程负责。

## 导出、部署与验证

| 交付 | 数据与操作范围 |
| --- | --- |
| JSON | 保存配置与不可变本地引用，不等于可移植的全量明细备份 |
| HTML | 当前计算视图的只读快照，不连接上游来源 |
| CSV | 导出全部匹配记录；筛选、排序和列选择在完整结果上执行 |
| 静态网页 ZIP | 使用中的完整数据集分片及共享应用；格式与离线能力见 [静态部署包](static-deployment.md) |
| 远程网页与腾讯云副本 | 鉴权、密钥、存储、有效期和 SCF 清理见 [自托管服务器](self-hosted-server.md) |

导出文件使用受管 ID，通过读取工具或远程下载链接交付，不接受任意导出路径。创建文件不意味着已部署；协议通过、目标宿主显示、剪贴板、全屏、下载和云端执行分别确认。

测试层次与授权边界统一见 [测试与 CI](testing.md)。普通维护只运行受影响的局部检查，不从本文复制整套测试命令。OAuth、多用户行级权限、数据仓库连接、企业审批与定时业务刷新不因上述入口存在而自动具备。

维护时机：模块边界、配置入口、发现方式或导入/交付边界改变时更新；组件外观、报告语法、项目存储和单次验收结果在各自负责正文维护。
