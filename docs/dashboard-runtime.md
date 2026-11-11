# Runtime：架构、配置与接口入口

Runtime 复用同一套 Service，为 CLI、本地 stdio MCP、自托管 HTTP MCP 和网页编辑器提供数据、指标计算、版本与文件导出。看板和报告使用共享 React 应用。

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

`dashboard_get` 读取可编辑草稿，`dashboard_view` 返回实际计算结果。MCP 用 `isError` 和结构化错误标识失败；确认 `ok`、检查报告与文档版本后再展示。响应丢失或过期时先读取现有状态。

MCP 中，创建、patch、恢复、数据导入/挂接/查询和数据迁移这八个原本返回文档的写入工具，默认 `responseMode=summary`：返回 `dashboardId`、顶层 `revision`、可能受影响的 `affectedComponentIds`、组件/数据集/指标数量及原有操作元数据；完整 `document` 与图表产物按需读取。共享指标、数据和布局操作可影响多个组件，受影响 ID 可能包含间接受影响或已删除的组件。下一次写入直接使用返回的顶层 `revision`。

需要完整结果时可显式传 `responseMode=full`，或按需调用 `dashboard_get`。MCP 编辑器显式请求 full，以继续更新页面；共享 Service、CLI 和网页 HTTP API 保留原文档返回。写入、权限、版本冲突和保存检查沿用既有规则；完整 Doctor 检查在完成编辑批次时执行。读取、预览、完成编辑及错误响应沿用各自原有结构。

预览工具为 `dashboard_preview`，UI 资源 URI 带运行版本与构建标识。宿主决定显示为对话卡片或面板。分块、资源过期和诊断字段见 [传输与诊断](mcp-transport-diagnostics.md)。

## 页面元信息与组件声明

页面标题使用 `manifest.title` / `set_title`。`manifest.meta` 提供 `iconKey`、`subtitle`、`org`、`system`、`statusText`；`set_meta` 整体替换，`{}` 清空。文本长度、枚举和兼容读取以当前操作结构与校验器为准；没有 meta 的旧导入仍可读取 `originalWorkspace.meta`。

组件声明保存稳定 ID、来源、数据集与指标引用、渲染配置和断点布局。预设、完整 ECharts 与自由 HTML/JavaScript 均通过明确声明进入；执行隔离、原生覆盖与绑定限制见 [渲染与覆盖](echarts-options.md)。历史 `kind=chart` 保留兼容读取，新组件遵循当前声明要求。

```sh
python3 -m dashboard_runtime --root ./boards import-workspace imported --path ./old-workspace
```

工作区导入保留原图表、指标卡和表格声明。历史已丢失字段需要从原资产恢复。

## 数据导入与查询来源

```sh
python3 -m dashboard_runtime --root ./boards call dataset_import --json-file import.json
```

`dataset_import` 必须提供 `rows` 或 `csvText` 中的一种。目标数据集存在时替换其数据与元信息。推断得到的数值指标采用默认求和；业务定义、单位和粒度需确认。需要保留数字标识或前导零时，用 JSON 字符串明确类型。整份 schema-v2 文档可通过 `import NEW_ID --file artifact.json` 创建新看板。

SQL 执行只连接运维配置的 SQLite 来源别名。别名配置为：

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
| JSON | 保存配置与不可变本地引用 |
| HTML | 当前计算视图的只读快照，不连接上游来源 |
| CSV | 导出全部匹配记录；筛选、排序和列选择在完整结果上执行 |
| 静态网页 ZIP | 使用中的完整数据集分片及共享应用；格式与离线能力见 [静态部署包](static-deployment.md) |
| 远程网页与腾讯云副本 | 鉴权、密钥、存储、有效期和 SCF 清理见 [自托管服务器](self-hosted-server.md) |

导出文件使用受管 ID，通过读取工具或远程下载链接交付。

测试层次与授权边界统一见 [测试与 CI](testing.md)。普通维护只运行受影响的局部检查。

维护时机：模块边界、配置入口、发现方式或导入/交付边界改变时更新；组件外观、报告语法、项目存储和单次验收结果在各自负责正文维护。

## 保存的结构简图

`structure_diagram.py` 维护静态 SVG 清理、标注参数和失效规则。所有组件使用同一声明：legacy 位于 `config.presentation.structureDiagram`，其他组件位于 `presentation.structureDiagram`。MCP 与 Runtime CLI 共用 `put_component`，不新增生成服务。

```json
{
  "version": 1,
  "viewBox": [0, 0, 600, 360],
  "svg": "<svg xmlns=\"http://www.w3.org/2000/svg\"><rect x=\"220\" y=\"100\" width=\"60\" height=\"180\" fill=\"#123b5d\"/></svg>",
  "annotations": [
    {"id": "revenue-mark", "metricId": "revenue", "anchor": [250, 180], "label": [30, 180], "align": "left"}
  ]
}
```

该示例只说明保存格式；生成时必须依据当前组件实际结构绘制。坐标范围固定从 `[0,0]` 开始，宽高为正数且不超过 10000；标注点都在范围内。`align=left` 的文字向右展开，`right` 向左展开，默认居中。标签应留足空间，前端不承担自动排布或类型识别。标注 ID 唯一且稳定，每张简图 1–32 个。指标引用从当前指标声明读取名称与定义；无指标引用时提供名称和描述。未提供定义或引用指标已不存在时，详情明确显示缺失状态，不生成业务解释。

SVG 限制为静态基本图形、分组和文字，最多 100000 字符、2000 个元素。脚本、事件、外部资源、样式、`foreignObject`、嵌套 SVG 和 URL 填充会移除；DTD 与实体声明、无效 XML 会拒绝。后端统一写入 viewBox，前端再次清理并以图片展示。SVG 不含业务数值，与筛选结果无关。

`put_component` 明确携带简图代表 Agent 已同步确认该简图；保存时状态为 `ready`。省略简图且组件声明改变时，保留原简图并标记 `stale`；完全相同的声明不改变状态。预设切换也使简图失效。数据刷新、布局与筛选操作不使简图失效。图形、绑定或系列含义改变时，Agent 必须同步重绘，不能复制未经确认的旧简图。旧组件无简图时只显示未配置状态，其余详情保持可用。

内置案例的简图维护在 `demo_diagrams.py`，按组件 ID 保存独立资产，随案例创建批次提交，不作为生产图表类型适配器。已保存的业务看板和远程分享副本不会因更新案例源码自动迁移；需要读取其实际声明，逐个生成简图并通过现有编辑流程保存。
