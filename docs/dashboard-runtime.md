# Dashboard and Analysis Report Runtime: web + CLI + MCP

The runtime extends charts-design. Original chart builders, KPI bodies, table and explanation components remain the rendering foundation; the runtime adds persistence, editing, transport and a shared SVG-only action layer.

> **Current status (2026-11-10)**
> The shared React component library and MCP application use separate adapters and explicit build/package steps. Preview, JSON/CSV, HTML snapshots and static site exports use the new resources. Missing builds return `UI_UNAVAILABLE`. Current completion and host acceptance are tracked in package-root `docs/ui-refactor-plan.md`.

## Run locally

Python requirements and optional dependency groups are declared in `pyproject.toml`. Use the project-selected Python interpreter. The commands below use `python3` as its placeholder.

```sh
python3 -m dashboard_runtime --root ./boards init demo --demo
```

Plain `init` creates an empty dashboard; `--demo` explicitly inserts synthetic data. The test fixtures also use explicitly labelled demonstration data. Keep `./boards` outside source control: it contains business snapshots, SQL and parameters.

## Personal analysis reports

A report is one Markdown document, presented as a single-column academic reading layout. Write headings, paragraphs, bold text, lists and blockquotes as usual; put a fenced `chart` block where a shared chart should appear. Charts render inline between the surrounding prose, with numbered captions and optional source notes below them. Dashboard mode remains an independent responsive grid using the same components, data, filters, metric definitions and source inspectors. Switching views does not execute SQL or generate new claims.

```sh
# An empty Markdown report; no business data is inserted.
python3 -m dashboard_runtime --root ./boards init analysis --mode report --title "我的分析报告"

# An explicitly synthetic Markdown example, with prose and two inline charts.
python3 -m dashboard_runtime --root ./boards init report-demo --mode report --demo
```

Each generated artifact has one saved presentation: dashboard or report. Editing supports layout dragging and direct plain-text editing of page/component titles and descriptions. GridStack enables dragging and resizing in edit mode and locks layout in view mode. Adding, duplicating, deleting charts and importing data are hidden in the UI. Chart type switching remains available. Annotation behavior depends on host capabilities; the rules and stored-note contract are in [位置引用与批注](annotation-composer.md). Report Markdown remains editable. Report Markdown determines reading order, and chart fences reference existing component IDs.

For example, this is the entire source of a small report. The `trend` and `regions` components must already exist, or be created in the same atomic update:

````markdown
# 我的经营观察

*——基于合成快照的描述性分析*

**摘要：** 这里只使用明确标记的合成数据，描述收入变化，不作因果推断。

**关键词：** 收入变化；区域结构；合成数据

## 收入走势

如[图](#fig-trend)所示，9 月收入**高于 7 月**，但低于 8 月。先观察变化，再验证原因。

```chart
{"componentId":"trend","caption":"2026 年 7—9 月收入变化","source":"数据来源：内置合成快照；金额单位为万元。"}
```

三个观测点不足以判断变化是否持续，需要结合更长时期的数据。

## 区域拆解

两地区的累计收入规模存在差异（见[图](#fig-regions)）。还需复核 East 的月度变化，并对照更细时间粒度的数据。

```chart
{"componentId":"regions","caption":"East 与 South 的季度累计收入","source":"数据来源：同一内置合成快照，统计期间为 2026 年 7—9 月。"}
```

图表之后可以继续写分析、限制和下一步。
````

Conclusions are authored and do not recalculate when filters change. Review the Markdown after changing data or filters. Raw HTML and ordinary code are not executable report instructions.

### Academic reading conventions

An authored level-one heading is the centered title; an emphasized paragraph immediately after it can provide a centered subtitle. Write abstract and keywords as ordinary paragraphs beginning with `**摘要：**` and `**关键词：**`. Level-two section headings receive presentation-only section numbers, so omit manual numbers in their Markdown. These conventions style supplied content; they do not invent authors, dates, abstracts, keywords or other metadata for existing documents.

Figures receive numbers in Markdown source order. Optional `caption` and `source` strings render as plain text under their chart; do not include a manual figure number in the caption. Use a standard Markdown link such as `[图](#fig-trend)` in prose to display the corresponding figure number and jump to the figure for component `trend`. Repeating a chart fence creates another numbered figure; links using `#fig-trend` still refer to that component's first occurrence. No extra `figureId` field is needed or accepted. Reordering the chart fences updates the rendered numbering without rewriting the canonical Markdown.

### Canonical source and validation (backward-compatible schema v2)

`manifest.viewMode` is optional: `"dashboard"` (the default for older documents) or `"report"`. The canonical report source is `manifest.report.markdown`:

```json
{
  "viewMode": "report",
  "report": {
    "markdown": "# 我的报告\n\n先写分析。\n\n```chart\n{\"componentId\":\"trend\"}\n```\n\n再写解读。"
  }
}
```

- `markdown` is a string of 0–200,000 characters. An empty string is a valid, intentionally empty report.
- A top-level fence whose exact info string is `chart` contains a JSON object with required `componentId` and optional `caption` and `source`. The existing 1–80 character identifier rule applies to `componentId`. It must resolve to a non-text component: chart, KPI, table or original catalog component. The same component may appear more than once. Existing `{"componentId":"trend"}` fences remain valid.
- `caption` must be a string of 0–500 characters; `source` must be a string of 0–1,000 characters. Both fields are plain text, may be omitted or empty, and cannot be `null`, objects, arrays, booleans or numbers. They do not execute code or fetch a source; author and verify the actual description and provenance yourself.
- Fences use backticks or tildes, at least three characters, optionally indented by up to three spaces. A closing fence uses the same character and is at least as long as its opener. Ordinary fenced code is inert, including examples of chart syntax inside a longer non-chart code fence.
- Invalid or unclosed chart JSON, duplicate JSON keys, unknown fields, missing components and references to text components are rejected when saving, importing or patching. A frontend may keep unfinished source locally while the author is typing; that does not bypass persistence validation.
- `set_report_markdown` takes the complete string as `value`, without changing mode, data or grid layouts. References are checked after the entire atomic batch, so component creation may follow the source operation.
- `remove_component` rejects deletion if canonical Markdown still references it, with `REPORT_COMPONENT_REFERENCED`. First remove its chart fence using `set_report_markdown`; both operations can be in the same batch, in that order.
- `set_view_mode` with `value: "report"` initializes missing Markdown from the title, existing legacy report or desktop reading order (top-to-bottom, then left-to-right). Existing canonical source survives view switching. Imported old reports can be displayed through the same non-mutating migration utility.

### Write source from CLI or MCP

Save your document as `analysis.md`, read the latest revision with `get`, and wrap the source in a JSON operation:

```sh
python3 -m dashboard_runtime --root ./boards get report-demo
python3 - <<'PYCODE'
import json
from pathlib import Path
operations = [
    {"op": "set_report_markdown", "value": Path("analysis.md").read_text()},
    {"op": "set_view_mode", "value": "report"},
]
Path("report-patch.json").write_text(json.dumps(operations, ensure_ascii=False))
PYCODE
# Replace 1 with the revision returned by get.
python3 -m dashboard_runtime --root ./boards patch report-demo --expected 1 --file report-patch.json
```

Use the same `set_report_markdown` operation in `dashboard_patch` over HTTP or MCP, with `dashboardId`, the latest `expectedRevision`, and `operations`. Revision checks, validation, history and restore are shared across transports. JSON export/import preserves the exact source. Full-document HTML export opens a read-only Markdown report snapshot using the shared renderer. Single-component export resets presentation to a standalone dashboard card and omits report metadata and unrelated components.

### Legacy report compatibility

Old `report.subtitle` plus `report.blocks` documents and the `set_report` operation remain supported. Without canonical Markdown, the subtitle is bounded at 1,000 characters and blocks at 100 unique block IDs and component references. Existing text components become escaped literal text under Markdown headings; non-text components become chart fences. Migration preserves the old components, grid and metadata and does not execute their contents.

When `markdown` is present, it alone determines the report. Retained subtitle/blocks are historical metadata and cannot override the source or prevent deletion of an unreferenced component. `set_report_markdown` retains those fields. The legacy `set_report` operation still explicitly replaces the whole report object; supplying only legacy fields returns to legacy representation. Only unmigrated block reports retain their old auto-append/cleanup behavior. New authoring should use Markdown source and `set_report_markdown`.

## MCP

```sh
python3 -m pip install 'mcp>=1.28,<2'
node /absolute/path/charts-design/bin/dashboard-runtime.js --runtime-root /absolute/path/runtime-cache mcp
```

MCP uses one entry point for multiple projects. Pass the absolute asset directory as `projectRoot` on every project call; it is not the Agent working directory. A call never selects a shared current project. Registration, source aliases, startup defaults, legacy `--root` compatibility and router requirements are defined in [项目资产与加载](project-runtime.md). CLI and the local HTTP editor use the storage selected at startup. `mcp.json` remains a legacy centralized-storage template and uses `${PLUGIN_ROOT}`; clients that do not expand it need actual absolute paths. Logs go to stderr; stdout is reserved for MCP protocol messages.

The Python worker and local web server exit by default after 60 seconds without requests or a visible preview. Active requests finish before the idle countdown starts. Visible previews renew the lifetime every 20 seconds; hidden tabs stop polling. Documents and history remain saved. The Node MCP launcher retains the stdio connection and restarts its Python worker on the next request, restoring initialization. Direct Python MCP entry points close the whole connection and require client reconnection. Restart an idle local web server before using it again. Adjust the positive timeout with `mcp --idle-timeout 120` or `serve --idle-timeout 120`; do not add background keepalive calls for unused processes.

For project-local dependencies, use the selected Python interpreter to run `python -m pip install --target .mcp-test-deps --upgrade '.[mcp,statistics,test]'`. Pyright also searches this ignored directory. Save the interpreter and local paths in the ignored `.charts-runtime-env.json`:

```json
{
  "python": "/absolute/path/to/python",
  "isolated": true,
  "dependencies": ".mcp-test-deps",
  "cache": ".runtime-cache",
  "browsers": ".browser-cache"
}
```

The Node launchers use this interpreter and dependency directory. With `isolated` enabled, they omit shared Python site-packages. `PYTHON` can explicitly override the interpreter; install the dependencies with the same Python version. Do not run UI tests or browser automation for this refactor; use the scoped checks in the plan. Tests run in separate directories to avoid duplicate module names. `npm run runtime:mcp` and `npm run runtime:serve` use the same setup.

Registration is managed once through Magpie, with absolute paths for Node, the launcher and runtime cache. Do not create per-project registrations or modify Agent configuration as part of chart generation. Existing project-local registrations and `--project-root` startup defaults remain compatible; configuration changes belong to the registration-management task. Installation updates and reconnect checks are described in [本地 MCP 更新](local-mcp-update.md).

Tools: `dashboard_create`, `dashboard_list`, `dashboard_get`, `dashboard_patch`, `dashboard_validate`, `dashboard_preview`, `dashboard_history`, `dashboard_restore`, `chart_catalog`, `dataset_import`, `query_execute`, `query_inspect`, `semantic_inspect`, `legacy_render`, `generation_examples`, `chart_declarations`, `chart_recommend`, `layout_templates`. The self-hosted server adds `dashboard_share` and `dashboard_share_revoke` and hides `dashboard_export_open`.

Preview tools link to a resource whose URI includes the runtime version and UI build ID, with MIME `text/html;profile=mcp-app`. It uses `@modelcontextprotocol/ext-apps` and the same built UI as the independent web editor. Prefer the current build-specific preview tool listed by the server; the fixed `dashboard_preview` name remains compatible. Tool discovery, result chunking and stale-page checks are defined in [传输与诊断](mcp-transport-diagnostics.md). A normal MCP connection does not establish MCP Apps host acceptance. Remote Streamable HTTP MCP with bearer tokens, project names instead of server paths and expiring browser preview links is provided by the self-hosted server described in [自托管服务器](self-hosted-server.md); OAuth and multi-user permissions are not included. Independent static-site export is available as described in [静态部署包](static-deployment.md); it does not provide a hosted multi-user backend.

## Canonical state and editing

`dashboard_runtime.service.Service` is the mutation service for all transports. Every edit supplies `expectedRevision`; stale writes fail with `REVISION_CONFLICT`. Operations in one patch validate and commit atomically. Project mode stores drafts and checkpoints separately: begin a batch with `dashboard_edit_begin`, apply patches with the latest revision, then call `dashboard_edit_finish` with that revision and the batch ID. Finish runs full Doctor checks and creates one checkpoint; preview once after success. Legacy centralized storage retains its document/revision workflow. Storage, checkpoint retention, comparison and restore rules are defined in [项目资产与加载](project-runtime.md).

Schema v2 separates components, datasets/field metadata, metric definitions, source/query provenance, per-breakpoint layout, and bounded snapshot rows. It contains no executable application code. View changes never execute SQL.

```sh
python3 -m dashboard_runtime contract
python3 -m dashboard_runtime --root ./boards get demo
python3 -m dashboard_runtime --root ./boards patch demo --expected 1 --file changes.json
python3 -m dashboard_runtime --root ./boards history demo
python3 -m dashboard_runtime --root ./boards restore demo --expected 2 --revision 1
```

Example changes.json:

```json
[
  {"op":"set_title","value":"Revenue review"},
  {"op":"set_meta","value":{"subtitle":"Monthly revenue review"}}
]
```

Restore creates a new revision; it does not rewrite history. Project-mode annotations are independent and survive design restore; legacy centralized revisions retain their historical annotation behavior. Browser undo/redo uses the same service. New external revisions clear the browser undo stack instead of silently undoing another writer's work. Visible, idle readers check for external revisions every five seconds; editing, annotations and unsaved input pause this polling.

GridStack uses independent desktop/tablet/mobile 12/8/4-column layouts. `apply_layout_template` computes all three from one of seven named compositions (executive, focus, bento, sidebar, grid3, narrative, scorecard), runs after the rest of its batch, is saved as `manifest.layoutTemplate` and re-flows when components are added or removed; `set_layout` replaces it. Without a template, new components are placed by role (KPI rows, paired charts, full-width tables/text) instead of stacking full width. Selection rules: `skills/executive-charts/references/layout_templates.md`. Edit mode supports layout dragging; component resizing is enabled only in edit mode. Adding, duplicating, deleting components and importing data remain API/CLI operations rather than visible editor controls. Read/edit modes, titles/descriptions, undo/redo, filters, export and SQL/semantic inspectors remain available.

Component action placement, Lucide controls, code-label visibility, table pagination and saved versus temporary presentation state are defined in [标题区与绑定](icon-header-and-bindings.md). Menus and forms retain readable text. Runtime previews and exports share the Runtime bundle; the standalone Python generators have their own card shell.

## Original components and chart switching

The runtime directly bundles all 40 original chart builders, 16 KPI rendering branches (the original mc01–mc09 plus mc10–mc16, added in the same shared engine for selection variety), the detail table and business explanation dialog. Bodies render as React components; the original chart definitions are maintained in independent TypeScript modules. The migration preserves geometry, labels, microcharts and semantics while using shadcn/ui and Lucide for controls.

```sh
python3 -m dashboard_runtime --root ./boards import-workspace imported --path ./old-workspace
```

Workspace import preserves original chart/KPI/table JSON, including c01/c02 designs and KPI auxiliary fields. It does not turn charts into generic bars or KPI cards into text. Original filter metadata is retained; working cross-component filtering requires explicit dataset/metric bindings. Supported bindings include 14 one-dimensional chart shapes, mc01-mc06 and detail tables. Complex shapes and mc07-mc09 require additional reviewed transforms; incomplete bindings fail rather than inventing data. Their static original configurations remain usable.

The product chart system consists only of the 40 original registered chart codes. MCP declarations and generation do not expose the additional eight generic types. New generic charts are rejected; historical documents retain compatibility reading. Reviewed original switching currently supports c01/c02 in edit mode, preserving data and swapping axis labels. Other code pairs require a reviewed conversion before they can be offered.

Metrics support sum, average, min, max, row count and ratio-of-sums. Filters recalculate SUM(numerator)/SUM(denominator), never the average of percentages. Nulls remain missing; a zero denominator yields no value. Percent formatting requires fractional values. Existing aggregate snapshots cannot produce missing finer-grained dimensions or statistically valid averages without the underlying data.

## Import data

Use the common CLI tool entrance or `dataset_import` over MCP. Import controls are hidden in the current web editor:

```sh
python3 -m dashboard_runtime --root ./boards call dataset_import --json-file import.json
```

```json
{
  "dashboardId":"demo","expectedRevision":1,"datasetId":"sales2",
  "rows":[{"region":"East","revenue":128},{"region":"South","revenue":96}]
}
```

Use `csvText` instead of `rows` for CSV. Inferred numeric metrics are unreviewed default sums; confirm definitions, units and grain before use. Leading-zero strings remain strings. A complete exported v2 artifact can be imported as a new dashboard using `import NEW_ID --file artifact.json`.

## SQL and semantic provenance

SQL execution currently supports SQLite only. Displaying SQL from another engine does not make that engine a live connector. Operators configure allowed source aliases, not MCP callers:

```json
{"analytics":{"engine":"sqlite","path":"/absolute/path/analytics.sqlite3"}}
```

```sh
python3 -m dashboard_runtime --root ./boards --sources ./sources.json serve
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

Read-only SQLite connections use query_only, an authorizer and a function allowlist. Extension loading, ATTACH, PRAGMA, DDL and DML are blocked. Time and row limits fail explicitly instead of silently truncating data. Successful query provenance records exact SQL, parameters, source alias, engine, duration, timestamp and row count in the same transaction as the snapshot. Supplied sources are marked supplied, never runtime-executed.

The semantic inspector uses stored business definitions and aggregation rules, not generated explanations inferred from labels. `reviewed` is descriptive metadata, not an enterprise approval system. Local query restrictions are not a hardened multi-tenant sandbox. Exported parameters and snapshots remain sensitive.

## Export and verification

```sh
python3 -m dashboard_runtime --root ./boards validate demo
python3 -m dashboard_runtime --root ./boards export demo --format json --output ./dist/demo.json
python3 -m pytest tests/runtime -q
node --test tests/runtime/*.test.mjs
```

JSON export preserves canonical configuration and local references. HTML exports a read-only snapshot of the current computed view. CSV exports the complete matching table result; static site export includes the used dataset shards.

Test layers, local commands and CI jobs are described in [测试与 CI](testing.md). MCP integration uses a real stdio SDK client. Running full test suites requires explicit user authorization; local development uses scoped verification.

## Remaining boundaries

Complex original-data transforms, warehouse execution, OAuth, multi-user permissions/RLS, enterprise approval, scheduled refresh, and actual Codex host acceptance are not established by the checks described here. The self-hosted server provides token-authenticated remote MCP and browser previews, not a multi-tenant application backend. UI completion does not imply these platform capabilities exist. 

Local server launch links now use an explicit `#token=...` fragment. Ordinary Markdown section and figure anchors never replace an existing session token. Legacy bare-token links are accepted for a fresh browser session; use the newly printed launch link to replace a token after a server restart.


## MCP 生成案例与声明发现

两条 Skills、案例和空白生成流程见 [generation-tracks.md](generation-tracks.md)。新增只读工具 `generation_examples`（可选 caseId）与 `chart_declarations`。对应 JSON 资源：`charts://examples`、`charts://examples/executive-dashboard`、`charts://examples/academic-report`、`charts://declarations`。案例返回完整原子操作和 Markdown；读取不会创建文档或写入示例数据。

## 在对话内展示 MCP App

单入口与 Python 工作进程生命周期按上方 MCP 章节执行。支持 MCP Apps 的宿主通过已注册的本地 MCP 展示界面；本项目不要求创建插件。

先执行 `npm run ui:build` 和 `npm run ui:package`。`dashboard_preview` 指向包含构建标识的 React 资源；协议可用与宿主内显示分别确认。

工具结果携带文档与统计图资源。界面通过官方 MCP Apps SDK 接收结果，通过宿主桥接调用工具保存图表类型与布局；筛选保持临时查看状态；迟到的旧版本不会覆盖新版本。宿主支持全屏时，工具栏显示“全屏查看”和“返回对话”。`runtime_keepalive` 仅向 App 开放，界面可见时才调用。

批次完成后，调用当前构建的预览工具，提供 `projectRoot` 和已保存的 `dashboardId`。具体出现为对话卡片还是面板由宿主决定。创建与修改返回保存结果；已有页面可按版本检测更新。普通客户端仍获得结构化结果，HTML 导出用于离线快照。


页面说明使用 `manifest.meta`：可选字段 `subtitle`、`org`、`system`、`statusText`，均为最多 1000 字符的文本。`set_meta` 整体替换这些字段；传入 `{}` 清空页面说明。未设置 `meta` 的旧导入项目继续读取 `originalWorkspace.meta`。标题仍使用 `manifest.title` / `set_title`。通过 MCP 的 `set_meta` 修改这些字段。

同一项目保存多个页面时，页面操作区提供“切换看板”选择器，由 `dashboard_list` 读取列表，切换通过 `dashboard_get` 加载。编辑时禁用切换。切换后清空临时表格、筛选与粒度状态；离线 HTML 不提供切换。

组件的 `subtitle` 为最多 1000 字符的说明，图表、指标卡和表格均显示。原版组件未设置顶层说明时使用 `config.subtitle`。原生指标卡默认 `presentation.type=mc01`，也支持 `mc02`–`mc16`（选型见 `skills/executive-charts/references/kpi-cards.md`）；同比、环比、目标等字段需要明确提供，系统不会自动推算。`mc03` 需要有效数据字段 `timeField` 或显式 `sparkData` / `sparkline`；`mc06` 需要 `leftVal` 和 `rightVal`。

筛选栏集中显示条件标签与“清空全部”。清除操作同时取消单选、多选、范围、搜索和图表联动条件；无条件时按钮保持可见并禁用。窄屏时摘要与清除按钮换到同一行。多组件筛选的候选项取关联数据集的并集。新增 `op=contains`：`values` 为空或一个最多 1000 字符的文本，对明确声明的字符串 `field` 做不区分大小写的包含匹配；仅影响 `componentIds`。全页搜索使用本地数据版本，不重新执行来源 SQL。表格自己的搜索框只搜索本表。

原生 KPI 筛选后只显示能重算的主值、时间趋势；未绑定的同比、环比、参考值等清空为 `—`，避免混用统计范围。需要这些衍生指标跟随筛选时，使用原版 KPI 的显式 `binding.measures`。表格列标题按 `title`、旧字段 `label`、`key` 的顺序读取。原版图表的月／季度控件常驻显示；目录中的 `filterBinding` 明确各组件是否支持动态重算，`snapshotOnly` 表示仅支持快照展示。

位置引用和批注的数据合同见 [批注说明](annotation-composer.md)。新 React 页面保留读取和语义说明，位置批注编辑入口尚未迁移。项目模式恢复设计不回退批注；JSON 导出保留已有批注，离线 HTML 只读。

页面固定使用浅色样式，不提供深色模式切换；旧文档的 theme 字段仍可读取。

预览与编辑的操作范围、标题区、直接入口与表格分页统一见 [标题区与绑定](icon-header-and-bindings.md)。信息图标打开只读“指标定义与语义”面板，保留 720px 弹窗与 52px 标题栏，正文用分隔线组织概览、图表结构、指标说明、数据来源和明细数据，不再嵌套大圆角卡片或折叠内容。指标卡不显示坐标结构；业务定义、计算公式、汇总方式、单位、判定规则和复核状态直接展开，公式使用轻底色。字段与指标按结构化说明呈现，不展示整份诊断 JSON。底部明细为当前筛选范围的最多 10 行只读示例，由 `component_data` 读取；不提供搜索、自定义列、排序、导出或分页操作，显示实际示例行数和匹配总行数。绑定指标 ID 从当前声明读取并去重，接口空指标列表不能使界面退回目录案例定义；数据集字段同样优先读取当前绑定。查看语义展示实际数据集、分组、换算和筛选范围，不拿目录案例定义替代业务指标。数据区的分页与图表转表的滚动范围见下方局部更新说明。


## 大数据看板：纯本地模式

复用 stdio MCP 进程和本机 SQLite，无需启动 HTTP 服务或增加常驻进程。完整数据保存在 `data.sqlite3`；看板配置及历史只保存不可变版本引用。指标卡与图表读取聚合结果，表格只读取当前页；筛选、排序、分页和全量 CSV 导出在本机执行。比例使用分子合计除以分母合计。

使用配置好的只读 SQLite 来源别名调用 `dataset_attach`；用 `dashboard_view` 读取交互结果，`dashboard_data_inspect` 检查行数、体积与耗时，`dataset_export` 导出全部匹配行。高基数筛选选项可搜索并逐页加载，超出聚合结果上限明确报错，不截断数据。标题与布局修改复用原数据版本。

旧快照可调用 `dashboard_migrate`，先生成备份再迁移全部配置历史；`dashboard_migration_rollback` 将备份恢复为新修订。小数据保留旧快照兼容。详细契约和复测命令见 [local-data.md](../skills/executive-charts/references/local-data.md)。本地 AppBridge 验证与真实 Codex 宿主验证分别记录，不互相替代。


指标说明的文案要求见 [指标定义与统计口径写作规范](../skills/executive-charts/references/metric-definitions.md)。业务定义用中文说明统计对象、范围及数值含义，计算公式采用业务名称；实际字段与聚合表达式在查看语义中展示。不得从名称推断净额扣减、税费、退款、去重或绩效政策。


## 密集图表、筛选与刷新

- 单轴柱状图超过 12 项、折线图超过 24 项时，默认显示可读窗口，保留完整数据；支持滑块、滚轮缩放、拖动和平移及重置。已有专用缩放配置保持有效，多绘图区图表不强行套用单轴规则。
- 单选采用 shadcn/ui Select，多选采用 Popover 与 Command。选择即时更新查看状态；多选提供候选项搜索、已选数量、全选和清空。全选读取候选项全部分页。
- `runtime_info` 返回安装版本、前后端构建标识、模块来源、进程与项目路径及报表版本，不读取图表明细；`dashboard_refresh` 使用最新定义重新读取当前视图，并保留读者筛选、表格和粒度状态。读者的临时条件不会写回正式报表。
- 在线阅读界面提供“刷新报表”，可见且无未保存操作时每 5 秒检查报表版本；版本改变才重新取视图。离线 HTML 是当前视图快照，不自动取数。
- MCP UI 资源地址随最新 bundle 内容变化，并发出资源与工具目录更新通知。已加载的旧 iframe 无法由服务端强制替换；新版界面检测到构建差异会提示重新打开最新预览。主机若仍缓存旧工具目录，需要重新连接 MCP 后打开新预览。

本地数据模式按不可变版本保存 SQLite 引用，筛选与汇总由本机计算；HTML/JSON 导出不嵌入全量明细。CSV 导出全部匹配结果；HTML 保留当前视图快照。安装包与 GitHub 发布不包含用户的数据库或业务明细。




### 局部更新与性能验证

`dashboard_view` 默认返回完整 `document`。交互调用可传 `responseMode: "patch"`、`componentIds` 和 `expectedRevision`，返回 `{id, revision, componentIds, computed, statisticalArtifacts}`。`computed.components`、`tables`、`grouped` 只包含选中的组件；省略字段表示保留已有值，空数组表示清空。省略 `componentIds` 表示全部，空列表表示不计算组件。仅在需要重新加载筛选选项时传 `includeFilterOptions: true`。版本不符返回 `REVISION_CONFLICT`；先刷新最新定义再重试。MCP 结构化结果与文本回退返回相同的小结果；超过阈值时均返回分块描述，消费者读取完整分块。不得把摘要或截断文本当完整响应，详细协议见传输与诊断文档。

`component_data` 接受 `sort: [{field, direction}]` 与 `search`，沿用表格排序和子串搜索规则。指标定义面板展示 `semantic_inspect` 返回的实际结果。图表转表显示对应完整聚合结果，并在自身容器内滚动。主表默认每页 10 行，明确配置继续保留；搜索、排序、分页由后端执行。CSV 导出全部匹配行，HTML 快照保留当前计算视图。

本项目 MCP 中，有数据集绑定的组件在详情面板底部显示“明细数据”，打开面板后通过 `component_data` 读取当前筛选范围内的原始行，并携带当前版本检查。每页默认 10 行，搜索、排序和翻页在后端执行；明细的表格状态独立于看板主表，关闭面板后丢弃。来源与原始定义折叠区保留在明细之后。静态快照、无数据集绑定的组件不调用此接口。

前端按可见组件 ID 查询并合并结果，最多四个查询并发。筛选只更新绑定的组件；表格搜索、排序、分页和图表粒度切换只更新当前组件。请求按组件记录代次，过期的排队请求不再发送，旧响应不覆盖新选择。无需数据绑定的静态图表直接读取配置，不请求计算视图。

更新时保留现有内容，不在已有卡片内反复显示更新提示；加载状态通过 `aria-busy` 表达。图表尺寸变化和配置变化合并到同一帧处理，尺寸未变且配置未变时不重复绘制；指标卡配置未变时跳过重复渲染。表格自动高度只观察相关表格，统一读取尺寸后再更新布局。切换看板时保留当前页面至新定义返回，再替换内容；进入布局编辑不插入占据页面高度的说明。取消布局编辑会恢复原布局。HTML 快照和静态站点使用同一套 React 组件，导出不依赖浏览器自动化。

图表联动只刷新旧、新条件的关联组件，来源图保留完整类别；再次点击同一来源的同一类别取消选择。图表以稳定系列 ID 和类别名称合并数据，柱状图选中类别保留原色，其余柱子变灰；清除联动条件恢复原色。图形与指标卡主数值使用 260ms 更新过渡，生效条件行展开、收起使用短过渡；系统启用减少动态效果时直接呈现最终数据。本次仅构建和同步资源，未运行 UI 测试、浏览器自动化或性能实测。

百万行本地数据的独立合成验收：

```sh
node bin/python-runtime.js tests/runtime/benchmark_local.py --rows 1000000 --output /private/tmp/charts-performance.json
```

该命令创建独立临时 SQLite 数据，以两张指标卡、一个分类图和一张明细表检查导入、打开、筛选、聚合、翻页、排序、搜索和完整 CSV 导出，并记录响应体积、进程峰值内存及磁盘大小。结果核对独立计算的行数与合计，测量范围为后端查询和数据导出。首次全字段子串搜索需扫描完整数据；自然字符串排序、多列排序及随机深页使用 OFFSET。缓存绑定不可变数据版本。


### 位置批注

位置引用、页面保存、锚点、失效位置及 Codex 读取处理的字段和流程统一见 [位置引用与对话批注](annotation-composer.md)。批注本身不自动触发 Agent，修改看板后保留原批注，除非用户要求修改或删除。
