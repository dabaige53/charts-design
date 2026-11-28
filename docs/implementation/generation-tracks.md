# 两条生成路径：Dashboard 与分析报告

两条 Skill 独立保留，共用来源、数据集、指标和声明式图表。MCP 提供案例、声明约定和原子写入工具，支持从空白文档生成完整内容。

| 目标 | Skill | 可执行参考案例 |
| --- | --- | --- |
| KPI、图表、表格、筛选组成的 Dashboard | `skills/executive-charts/SKILL.md` | `charts://examples/executive-dashboard`、`charts://examples/operations-scorecard` |
| Markdown 正文与嵌入图表组成的论文式报告 | `skills/analytical-reports/SKILL.md` | `charts://examples/academic-report` |

分析报告以当前认可的学术单栏案例作为母稿；其唯一 Markdown 源文是 `dashboard_runtime/examples/academic-report.md`，CLI 示例和 MCP 案例均从它读取。历史 HTML 示例已从仓库清理。

## 从空白报告生成，而非套一个静态页面

每次 MCP 项目调用都显式传入 `projectRoot`，值为报表资产目录的绝对路径；包括案例与声明发现、读取、编辑、诊断和分块读取。以下示例省略重复参数。旧启动默认项目仅用于兼容，不沿用上一次调用的项目。

已经掌握数据与组件声明时，可直接一次提交初始 `operations`。需要先认识数据时，先创建空容器并调用 `dataset_import`、`dataset_attach` 或 `query_execute`，再使用回执 `nextCalls` 的 `dataset_preview` 检查字段和有界原始样本。该检查不需要临时组件，也不应用页面筛选；样本不代表全量统计。指标与来源沿用回执中的实际 ID，确认业务口径后再编排以下内容。

1. 从 `charts://examples` 发现看板与报告案例。`charts://examples/academic-report` 提供母稿 Markdown、合成来源、数据、指标、图表声明及完整 `operations`。
2. 按需要使用 `chart_recommend {"intent":"trend","measures":1}` 排列候选图表。通过 `chart_declarations {"code":"c01"}` 阅读所选声明要求与示例，从 `charts://layouts` 选择构图，从 `charts://contract` 阅读操作合同。
3. 新报告选择 ID 与标题，已有报告用 `dashboard_get` 读取当前修订。
4. 用 `dashboard_submit` 提交相关声明操作。新报告传 `createTitle`，修改已有报告传 `expectedRevision`。组件、指标与 Markdown 引用在同一组操作完成后统一校验，服务端检查草稿并保存。
5. 成功后按 `nextAction=dashboard_preview` 打开已保存预览。若完整检查失败，读取保留的草稿并提交修正，不重复提交原操作。
6. 通过 `dashboard_get` 核实草稿与组件声明，通过 `dashboard_view` 核对实际计算结果；检查数值与单位、图号、图文顺序、指标定义、来源与局限。发生版本冲突时先读取新版本，不盲目覆盖。

## 报告源文与兼容约定

报告以一个 Markdown 文档作为正式源文，按学术单栏阅读顺序排版。普通标题、段落、加粗、列表和引用照常使用；顶层 `chart` 围栏在正文中引用既有图表、指标卡或表格，并可提供图注和来源。每个成果保存一种呈现类型；看板网格与报告正文使用相同组件和数据。

```sh
# 空白报告，不插入业务数据。
bun bin/python-runtime.js -m dashboard_runtime --root ./boards init analysis --mode report --title "我的分析报告"

# 显式合成案例，含正文与图表。
bun bin/python-runtime.js -m dashboard_runtime --root ./boards init report-demo --mode report --demo
```

### 正文、图号与阅读顺序

报告 Markdown 决定图文顺序，网格布局保持独立。一级标题居中；紧随其后的强调段落可作为副标题。摘要和关键词用 `**摘要：**`、`**关键词：**` 开头的普通段落。二级标题由展示层编号，不手写章节号；系统不会为旧文档补造作者、日期、摘要或关键词。

````markdown
# 我的经营观察

*——基于明确标记的合成快照*

**摘要：** 描述已提供数据中的收入变化，不作因果推断。

**关键词：** 收入变化；区域结构

## 收入走势

如[图](#fig-trend)所示，先说明观察与依据。

```chart
{"componentId":"trend","caption":"收入变化","source":"数据来源：已提供的合成快照；金额单位为万元。"}
```

再解释观察范围和数据限制。
````

示例的 `trend` 组件必须事先存在，或在同一原子批次中创建。图注不手写图号；渲染器按围栏顺序编号。`[图](#fig-trend)` 显示对应图号并跳转到该组件的首次出现位置。一个组件可重复引用，每次生成新的图号；重排围栏会更新编号，不改写源文。不接受额外 `figureId`。

数据或筛选变化后要复核正文数值、图注与来源。

### 源文结构与保存校验

schema-v2 文档通过 `manifest.viewMode` 保存 `dashboard` 或 `report`；旧文档省略时默认 `dashboard`。报告正式源文为 `manifest.report.markdown`：

```json
{
  "viewMode": "report",
  "report": {
    "markdown": "# 我的报告\n\n先写分析。\n\n```chart\n{\"componentId\":\"trend\"}\n```\n"
  }
}
```

- `markdown` 为 0–200,000 字符的字符串；空字符串表示刻意保留空白报告。
- 顶层围栏的 info 必须精确为 `chart`，内容为一个 JSON 对象；必填 `componentId`，可选 `caption` 和 `source`，不接受其他字段或重复 JSON 键。
- `componentId` 沿用 1–80 字符的标识规则，在整个原子批次完成后必须指向非 text 组件；原有仅含 componentId 的声明保持兼容。
- `caption` 是 0–500 字符的字符串，`source` 是 0–1,000 字符的字符串；可省略或为空，不接受 null、对象、数组或布尔值。两者只显示普通文字，不执行代码或自动获取来源。
- 围栏可用反引号或波浪线，至少三个字符，最多缩进三个空格。结束围栏使用相同字符，长度不短于开始围栏。较长普通代码围栏内的 chart 示例保持普通代码。
- 围栏未闭合、JSON 不合法、字段不合法、引用不存在或引用 text 组件时，保存、导入和 patch 都会拒绝。编辑器可在本地暂存未完成输入，不绕过保存校验。

### 修改与组件引用

`set_report_markdown` 的 `value` 是完整字符串，整体替换正式源文，不改变类型、数据、组件或网格布局。修改时保留用户未要求改动的正文。创建组件和写入围栏可以在同一原子批次中完成，组件可在源文操作之后创建。

`remove_component` 拒绝删除仍被正式 Markdown 引用的组件，错误为 `REPORT_COMPONENT_REFERENCED`。先用 `set_report_markdown` 移除围栏，再删除组件；两个操作可以按此顺序放在同一 patch 中。新增组件不会自动追加到正式 Markdown。

`set_view_mode=report` 在缺少正式 Markdown 时，从标题、旧报告或桌面布局阅读顺序（先 y、后 x）初始化源文，并转义旧纯文本。已有源文在类型切换时保留；文档类型不改变看板布局。

### CLI 与 MCP 写入

MCP 原生路径直接把完整 Markdown 字符串传给 `set_report_markdown.value`，与相关组件操作一起交给 `dashboard_submit`；无需先写 `.md`、生成 patch 文件或执行脚本。[MCP 创作示例](../../skills/executive-charts/references/mcp-authoring.md#直接初始化小型看板)提供完整看板初始化和报告变体。

需要文件审阅、离线写作或可重复批处理时，再使用 CLI 文件流程。先读取最新版本，再将源文装入操作：

```sh
bun bin/python-runtime.js -m dashboard_runtime --root ./boards get report-demo
bun bin/python-runtime.js - <<'PYCODE'
import json
from pathlib import Path
operations = [
    {"op": "set_report_markdown", "value": Path("analysis.md").read_text()},
    {"op": "set_view_mode", "value": "report"},
]
Path("report-patch.json").write_text(json.dumps(operations, ensure_ascii=False))
PYCODE
# expected 使用 get 返回的最新 revision；此处演示值为 1。
bun bin/python-runtime.js -m dashboard_runtime --root ./boards patch report-demo --expected 1 --file report-patch.json
```

MCP 用同样的 `set_report_markdown` 操作，传入项目、看板和最新版本，并完成编辑批次。JSON 导入导出保留精确源文；整份 HTML 导出用共享渲染器保存只读报告。单组件导出按独立看板卡片呈现，不带其他组件和报告元信息。

### 旧报告兼容

旧 `report.subtitle`、`report.blocks` 和 `set_report` 继续支持。没有正式 Markdown 时，subtitle 最多 1,000 字符，blocks 最多 100 个唯一 block ID 和组件引用。旧 text 组件转换成 Markdown 标题下的转义纯文本，非 text 组件转换成 chart 围栏；迁移不执行旧内容，保留组件、布局和元信息。

存在 `markdown` 时按它呈现；`set_report_markdown` 保留历史 subtitle/blocks 元信息。旧 `set_report` 整体替换 report 对象；只提交旧字段会回到旧表示方式。只有未迁移的旧 block 报告保留自动追加/清理行为，新建报告使用正式 Markdown。

## 声明式图表的适用范围

交互图表可用内置预设、完整原生 ECharts 或 HTML/JavaScript 自由组件。内置预设通过 `kind=legacy`、`family` 和 `config` 声明，并明确提供 data/presentation；自由入口的输入、隔离与绑定边界见 [渲染与覆盖](echarts-options.md)。需要筛选时再声明受支持的数据集、指标和字段绑定；不能只给 code 或 datasetId 就认定图表可正确计算。`chart_declarations` 按 `code` 查询，拒绝 `chartType` 参数；历史通用图表保留兼容读取。目录条目数与渲染器数不同，以当前目录和声明返回的范围为准。可选统计图使用单独的 statistical 声明。

案例中的 Dashboard 和报告可复用相同数据声明，但分别生成独立文档。Dashboard 按看板布局打开，报告按 Markdown 单栏正文打开，页面不提供两种类型的切换按钮。生成阶段通过 `set_view_mode` 明确文档类型；报告只选择需要的图表嵌入正文。

`report` 的浏览器预览、MCP App 和网页导出使用独立阅读页。作者通过 MCP 或 CLI 更新 Markdown 和图表声明。需要页面内筛选时，使用下文的 `filtered-report`。

## 指标口径、数据说明与备注

使用标准 Markdown 脚注语法：正文 `收入[^revenue]`，末尾定义 `[^revenue]: 指标按观察范围对收入求和，单位万元。` 渲染为带编号、可跳转和返回正文的文末「注释」。重复引用复用编号；未定义的引用保留为原文，交付前应补齐。网页没有稳定分页，故不假称为逐页页脚。较长定义放在普通 `## 附录：指标口径` 中。母稿同时演示注释与附录，正文与说明均由调用方通过 `set_report_markdown` 生成并保存。

## 两个对照看板案例

`executive-dashboard` 与 `operations-scorecard` 使用同一份合成数据与指标，构图完全不同：前者为经典三段式（mc01–mc04、t06、c01），后者使用 `scorecard` 布局模板、mc16 主指标、mc11 环形、mc13 子弹目标、mc14 双期对比、mc12 迷你柱与 mc05 仪表，以及 c02 排名、c03 预算对实际、t01 走势，并以 `apply_layout_template` 而非手写坐标排版。两者均为合成参考，不直接沿用其业务结论。按问题选图、选卡和安排布局；`chart_recommend`、`kpiGuide` 和 `layout_templates` 是可选辅助，不是生成限制。选型规则见 `skills/executive-charts/references/kpi-cards.md` 与 `layout_templates.md`。

## 完整经营看板案例与能力边界

所有四卡及 t06 都声明数据集和指标 binding。收入与旅客量求和；客座率、预算达成率、收益变动率用分子总和除以分母总和。mc03 趋势来自 timeField，mc04 进度 percent 从达成率乘 100；案例不填没有基期证据的同比或环比。t06 同时提供合法的 month/quarter 合成快照，再通过日期字段绑定按月与季度重算。区域、日期范围及区域文本搜索筛选均明确列出 componentIds；空 values 表示不筛选。文本搜索可用 `contains`，指定一个文本 values、明确 field 与 componentIds，不执行隐式跨字段搜索。

`chart_declarations {"code":"t06"}` 和 `{"code":"m01"}` 各返回自身合法的完整合成声明。m01 可以展示目标对比快照，但没有通用筛选绑定；不能用 c01 示例冒充它。目录每个代码的 `filterBinding` 指明 supported、snapshotOnly 与显式绑定要求。当前可绑定代码以 `dashboard_runtime/bindings.py` 为准；其余形状需要单独审查数据变换，不能只把数据集名称写上就宣称支持筛选。mc07–mc09 排名、阈值和拆分辅助字段也没有完整动态变换。

表格列头优先使用 `columns[].title`；`label` 保持兼容，未提供两者时使用 key。真实交付须替换 fixture 来源与数据，重新计算全部说明、基期比较及指标，不沿用合成案例结论。

维护时机：文档类型、报告源文语法、生成流程或案例引用方式变化时更新；具体渲染能力从当前声明发现入口读取。

## 原生筛选式报告

`set_view_mode` 设为 `filtered-report`，正文单栏铺满可用内容区，继续使用 `set_report_markdown` 和 `chart` 围栏按顺序引用组件。可在围栏前写小节标题和分析段落；提供 `caption` 的表格显示表序号及图注。表格随内容排版，其他图表仍显示图号。

筛选通过 `set_filters` 声明。默认或 `scope: "report"` 的筛选显示在页首；`scope: "table"` 的筛选必须且只能指定一张原生表格作为 `componentIds`，显示在该表上方。报告级与表级条件按各自消费者叠加，选择属于临时查看状态。可通过 `generation_examples {"caseId":"filtered-report"}` 或 `charts://examples/filtered-report` 获取含两张表的合成案例。已有 `report` 和 `dashboard` 保持原有呈现。
