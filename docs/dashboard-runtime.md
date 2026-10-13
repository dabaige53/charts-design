# Dashboard and Analysis Report Runtime: web + CLI + MCP

The runtime extends charts-design. Original chart builders, KPI bodies, table and explanation components remain the rendering foundation; the runtime adds persistence, editing, transport and a shared SVG-only action layer.

## Run locally

Python 3.10+ runs the CLI and local API. Node 22 is the tested UI build target.

```sh
npm --prefix runtime-ui install
npm --prefix runtime-ui run build
python3 -m dashboard_runtime --root ./boards init demo --demo
python3 -m dashboard_runtime --root ./boards serve --port 8765
```

Open the token-bearing URL printed by `serve`. It binds only to 127.0.0.1. The token is carried in the URL fragment, removed from the address bar and retained in session storage. Do not share it. This is not an Internet-facing multi-tenant service.

Plain `init` creates an empty dashboard; `--demo` explicitly inserts synthetic data. The test fixtures also use explicitly labelled demonstration data. Keep `./boards` outside source control: it contains business snapshots, SQL and parameters.

## Personal analysis reports

A report is one Markdown document, presented as a single-column academic reading layout. Write headings, paragraphs, bold text, lists and blockquotes as usual; put a fenced `chart` block where a shared chart should appear. Charts render inline between the surrounding prose, with numbered captions and optional source notes below them. Dashboard mode remains an independent responsive grid using the same components, data, filters, metric definitions and source inspectors. Switching views does not execute SQL or generate new claims.

```sh
# An empty Markdown report; no business data is inserted.
python3 -m dashboard_runtime --root ./boards init analysis --mode report --title "我的分析报告"

# An explicitly synthetic Markdown example, with prose and two inline charts.
python3 -m dashboard_runtime --root ./boards init report-demo --mode report --demo
python3 -m dashboard_runtime --root ./boards serve --port 8765
```

Each generated artifact has one saved presentation: dashboard or report. Editing supports layout dragging and direct plain-text editing of page/component titles and descriptions. Component resizing is disabled. Adding, duplicating, deleting charts and importing data are hidden in the UI. Chart type switching remains available. Page and component annotations can be added, edited and removed; they persist in manifest.annotations through set_annotations and reopen with the saved artifact. Report Markdown remains editable. Report Markdown determines reading order, and chart fences reference existing component IDs.

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

Conclusions are authored and do not recalculate when filters change. Review the Markdown after changing data or filters. Raw HTML and ordinary code are not executable report instructions. The demo labels its synthetic snapshot and the limits of its observations; it does not imply an AI-generated diagnosis or an enterprise reporting workflow.

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
python3 /absolute/path/charts-design/bin/dashboard_runtime.py --root /absolute/path/boards mcp
```

Web, CLI and MCP must use the same absolute `--root`. `mcp.json` uses `${PLUGIN_ROOT}`; replace it with actual paths in clients that do not expand the convention. Logs go to stderr; stdout is reserved for MCP protocol messages.

Local MCP and web preview processes exit by default after 60 seconds without requests or a visible preview. Active requests finish before the idle countdown starts. Visible previews renew the lifetime every 20 seconds; hidden tabs stop all background polling. Documents and revision history remain saved. Adjust the positive timeout with `mcp --idle-timeout 120` or `serve --idle-timeout 120`. After exit, restart the web server; MCP clients must reconnect or relaunch the configured command (automatic relaunch depends on the host). Do not use background keepalive calls to retain an unused process.

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

The Node launchers use this interpreter and dependency directory. With `isolated` enabled, they omit shared Python site-packages. `PYTHON` can explicitly override the interpreter; install the dependencies with the same Python version. Install the test browser with `node bin/python-runtime.js -m playwright install chromium --only-shell`, then run `npm test`. Tests run in separate directories to avoid duplicate module names. `npm run runtime:mcp` and `npm run runtime:serve` use the same setup.

To enable this MCP only in this trusted project, add the server table to `.codex/config.toml` instead of running `codex mcp add`, which writes user-level configuration:

```toml
[mcp_servers.charts-design]
command = "node"
args = ["/absolute/path/charts-design/bin/dashboard-runtime.js", "--root", "/absolute/path/charts-design/.charts-runtime", "mcp"]
enabled = true
```

Verify with `codex mcp get charts-design --json` from the project directory. Project-local configuration requires a trusted project. Refresh the MCP connection or reopen a project chat to load configuration changes in an existing desktop session.

Tools: `dashboard_create`, `dashboard_list`, `dashboard_get`, `dashboard_patch`, `dashboard_validate`, `dashboard_preview`, `dashboard_history`, `dashboard_restore`, `chart_catalog`, `dataset_import`, `query_execute`, `query_inspect`, `semantic_inspect`, `legacy_render`, `generation_examples`, `chart_declarations`.

`dashboard_preview` links to the versioned resource `ui://charts-design/dashboard-v0.4.0.html`, MIME `text/html;profile=mcp-app`. It uses `@modelcontextprotocol/ext-apps` and the same built UI as the independent web editor. A normal MCP connection does not imply support for embedded MCP Apps. Actual Codex/ChatGPT host installation remains a separate acceptance step. Remote Streamable HTTP MCP, OAuth and hosted publishing are not included.

## Canonical state and editing

`dashboard_runtime.service.Service` is the mutation service for all transports. SQLite stores the document and last 100 revisions. Every edit supplies `expectedRevision`; stale writes fail with `REVISION_CONFLICT`. Batched operations validate and commit atomically.

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

Restore creates a new revision; it does not rewrite history. Browser undo/redo uses the same service. New external revisions clear the browser undo stack instead of silently undoing another writer's work. Web clients check for external revisions every five seconds.

GridStack uses independent desktop/tablet/mobile 12/8/4-column layouts. This is flexible responsive positioning and resizing, not arbitrary overlapping pixel placement. Read/edit modes, component add/delete/duplicate, titles/descriptions, undo/redo, global filters, import/export and SQL/semantic inspectors remain available.

All main-card action buttons are real Lucide SVGs with accessible names, hover help and keyboard focus. Titles/descriptions stay upper-left, actions upper-right; narrow cards expose secondary actions through More. Menus and forms keep normal readable text. Table order, visibility, pagination and sorting persist. See `icon-header-and-bindings.md` for bindings and the component UI contract.

## Original components and chart switching

The runtime directly bundles all 40 original chart builders, 9 KPI rendering branches, the detail table and business explanation dialog. Bodies run inside ShadowRoots, not nested iframe cards. Source extraction preserves the original geometry, labels, microcharts and original actions while replacing the header controls with consistent SVG chrome.

```sh
python3 -m dashboard_runtime --root ./boards import-workspace imported --path ./old-workspace
```

Workspace import preserves original chart/KPI/table JSON, including c01/c02 designs and KPI auxiliary fields. It does not turn charts into generic bars or KPI cards into text. Original filter metadata is retained; working cross-component filtering requires explicit dataset/metric bindings. Supported bindings include 14 one-dimensional chart shapes, mc01-mc06 and detail tables. Complex shapes and mc07-mc09 require additional reviewed transforms; incomplete bindings fail rather than inventing data. Their static original configurations remain usable.

The product chart system consists only of the 40 original registered chart codes. MCP declarations and generation do not expose the additional eight generic types. New generic charts are rejected; historical documents retain compatibility reading. Reviewed original switching currently supports c01/c02 in edit mode, preserving data and swapping axis labels. Other code pairs require a reviewed conversion before they can be offered.

Metrics support sum, average, min, max, row count and ratio-of-sums. Filters recalculate SUM(numerator)/SUM(denominator), never the average of percentages. Nulls remain missing; a zero denominator yields no value. Percent formatting requires fractional values. Existing aggregate snapshots cannot produce missing finer-grained dimensions or statistically valid averages without the underlying data.

## Import data

Use the web import dialog or the common CLI tool entrance:

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
python3 -m dashboard_runtime --root ./boards export demo --output ./dist/demo.html
python3 -m dashboard_runtime --root ./boards export demo --format json --output ./dist/demo.json
python3 -m pytest tests/runtime -q
node --test tests/runtime/*.test.mjs
```

HTML is a read-only snapshot with bundled original components, ECharts, icons and UI; it needs no CDN after building. It is not a live shared dashboard. JSON preserves editable canonical state. The historical standalone Python generators remain separate compatibility entrances and retain their own historical behavior.

MCP integration uses a real stdio SDK client. Browser acceptance uses actual Chromium, ECharts and GridStack. The full component test renders all 40 charts and 9 KPI types, checks icon-only headers, original chart/table actions and CSV downloads, and writes screenshots plus `component-review/coverage.json`. This is rendering and behavioral coverage, not a claim of pixel-exact equivalence with historical screenshots. Optional unavailable runtimes are explicitly skipped outside CI, never counted as passed.

## Remaining boundaries

Complex original-data transforms, warehouse execution, remote MCP, multi-user permissions/RLS, enterprise approval, scheduled refresh, hosted publishing, and real Codex host installation are not complete. UI completion does not imply these platform capabilities exist. Keep the PR Draft until visual review, code review and target-host acceptance; do not merge automatically.

Local server launch links now use an explicit `#token=...` fragment. Ordinary Markdown section and figure anchors never replace an existing session token. Legacy bare-token links are accepted for a fresh browser session; use the newly printed launch link to replace a token after a server restart.


## MCP 生成案例与声明发现

两条 Skills、案例和空白生成流程见 [generation-tracks.md](generation-tracks.md)。新增只读工具 `generation_examples`（可选 caseId）与 `chart_declarations`。对应 JSON 资源：`charts://examples`、`charts://examples/executive-dashboard`、`charts://examples/academic-report`、`charts://declarations`。案例返回完整原子操作和 Markdown；读取不会创建文档或写入示例数据。

## 在对话内展示 MCP App

项目 Node 启动入口保留一个轻量连接进程。Python 运行进程空闲 60 秒后退出，下次请求才重启，并恢复 MCP 初始化协商；无后台轮询。这样可以释放图表运行环境，同时保持 Codex 的 stdio 连接。直接使用 Python 入口时会关闭整个连接，客户端需要自行重连。宿主断开或关闭连接后，Node 进程也会退出。完全关闭所有进程与保持现有 stdio 连接无法同时实现。

不需要创建或安装插件。项目的 `.codex/config.toml` 连接本地 MCP 服务；支持 MCP Apps 的客户端可直接展示它提供的界面。

`dashboard_create`、`dashboard_preview`、`dashboard_patch`、`dashboard_restore`、`dataset_import` 和 `query_execute` 都声明同一 `ui://` 界面资源，使用标准 `_meta.ui.resourceUri`，并保留旧客户端的 `ui/resourceUri` 字段。界面资源使用 `text/html;profile=mcp-app`，HTML、脚本和样式都已打包，不需要 CDN。

工具结果携带文档与统计图资源。界面通过官方 MCP Apps SDK 接收结果，通过宿主桥接调用工具保存图表类型与筛选状态；迟到的旧版本不会覆盖新版本。宿主支持全屏时，工具栏显示“全屏查看”和“返回对话”。`runtime_keepalive` 仅向 App 开放，界面可见时才调用。

加载本项目 MCP 后，调用 `dashboard_preview` 并提供已保存的 `dashboardId`，可作为明确的展示入口。创建和修改操作也可由兼容宿主展示；具体出现为对话卡片还是面板由宿主决定。普通客户端仍获得结构化文档，HTML 导出用于离线快照。

`test_mcp_app_browser.py` 使用真实 MCP 服务、官方 `AppBridge` 和 Chromium 检查内嵌图表、MCP 更新、重新打开、全屏切换及旧结果保护。这是兼容宿主验收，不代表 Codex 桌面客户端已验收。若当前聊天尚未出现项目工具，需要重新加载项目 MCP；实际 Codex 展示须在加载后的聊天中检查。

页面说明使用 `manifest.meta`：可选字段 `subtitle`、`org`、`system`、`statusText`，均为最多 1000 字符的文本。`set_meta` 整体替换这些字段；传入 `{}` 清空页面说明。未设置 `meta` 的旧导入项目继续读取 `originalWorkspace.meta`。标题仍使用 `manifest.title` / `set_title`。通过 MCP 的 `set_meta` 修改这些字段。

组件的 `subtitle` 为最多 1000 字符的说明，图表、指标卡和表格均显示。原版组件未设置顶层说明时使用 `config.subtitle`。原生指标卡默认 `presentation.type=mc01`，也支持 `mc02`–`mc09`；同比、环比、目标等字段需要明确提供，系统不会自动推算。`mc03` 需要有效数据字段 `timeField` 或显式 `sparkData` / `sparkline`；`mc06` 需要 `leftVal` 和 `rightVal`。

仪表盘筛选栏常驻显示条件摘要与“一键重置”。多组件筛选的候选项取关联数据集的并集。新增 `op=contains`：`values` 为空或一个最多 1000 字符的文本，对明确声明的字符串 `field` 做不区分大小写的包含匹配；仅影响 `componentIds`。全页搜索不执行 SQL。表格自己的搜索框只搜索本表。

原生 KPI 筛选后只显示能重算的主值、时间趋势；未绑定的同比、环比、参考值等清空为 `—`，避免混用统计范围。需要这些衍生指标跟随筛选时，使用原版 KPI 的显式 `binding.measures`。表格列标题按 `title`、旧字段 `label`、`key` 的顺序读取。原版图表的月／季度控件常驻显示；目录中的 `filterBinding` 明确各组件是否支持动态重算，`snapshotOnly` 表示仅支持快照展示。

界面批注保存为 `manifest.annotations`，每条包含 `id`、`componentId`（页面批注为 `null`）、`text`、`createdAt`。`set_annotations` 整体替换列表，最多 100 条，每条正文最多 4000 字。修改受版本检查约束；批注随 JSON 导出和版本恢复保留。离线 HTML 可查看批注，不能保存修改。

页面固定使用浅色样式，不提供深色模式切换；旧文档的 theme 字段仍可读取。

预览与编辑明确分离：预览只显示查看操作；批注与原版类型切换只在编辑时开放。预览筛选、表格列配置、排序、分页与月季度切换只改变当前查看状态，不写入保存的默认配置。图表标题不显示 C01 等组件编号。右上角恢复原版直接入口：图表／数据表、导出数据、复制图片、全屏、指标定义与语义；月／季度切换同样位于操作区，窄屏换行，不隐藏到更多菜单。编辑模式下每张原版图表显示“切换图表类型”；目前只有 c01／c02 支持兼容切换，其余图表展示当前类型及暂无兼容类型的原因。批注和拖动仅在编辑模式出现，卡片尺寸调整保持关闭。表格保留自定义列配置、导出 Excel (CSV) 和底部分页。信息图标打开只读面板，分为业务说明、指标定义、查看语义、SQL 与来源、数据；定义优先采用当前绑定指标，查看语义展示实际计算方式、数据集、分组、展示换算及筛选范围，不拿目录示例定义替代已绑定的业务指标。已保存批注在业务说明内展示。
