# 两条生成路径：Dashboard 与分析报告

两条 Skill 独立保留，共用来源、数据集、指标和声明式图表。MCP 不仅提供截图或母稿：它提供可读取的案例、声明合同和原子写入工具，调用方可以从空白文档生成完整内容。

| 目标 | Skill | 可执行参考案例 |
| --- | --- | --- |
| KPI、图表、表格、筛选组成的 Dashboard | `skills/executive-charts/SKILL.md` | `charts://examples/executive-dashboard`、`charts://examples/operations-scorecard` |
| Markdown 正文与嵌入图表组成的论文式报告 | `skills/analytical-reports/SKILL.md` | `charts://examples/academic-report` |

原 Dashboard HTML 案例继续保留在 `skills/executive-charts/examples/`。分析报告以当前认可的学术单栏案例作为母稿；其唯一 Markdown 源文是 `dashboard_runtime/examples/academic-report.md`，CLI 示例和 MCP 案例均从它读取。

## 从空白报告生成，而非套一个静态页面

每次 MCP 项目调用都显式传入 `projectRoot`，值为报表资产目录的绝对路径；包括案例与声明发现、读取、编辑、诊断和分块读取。以下示例省略重复参数。旧启动默认项目仅用于兼容，不沿用上一次调用的项目。

1. `generation_examples {}` 发现两种案例；`generation_examples {"caseId":"academic-report"}` 返回母稿 Markdown、明确标注的合成来源、数据/指标/图表声明及完整 `operations`。
2. `chart_recommend {"intent":"trend","measures":1}` 按问题与数据形态排列候选图表；`chart_declarations {}` 发现类型索引与指标卡选型 `kpiGuide`，`chart_declarations {"code":"c01"}` 阅读所选声明要求与工作示例；`layout_templates {}` 选择构图；`charts://contract` 阅读操作合同。相应资源为 `charts://declarations`、`charts://catalog`、`charts://layouts`。
3. `dashboard_create {"dashboardId":"my-report","title":"我的分析报告"}` 建立空白文档，取得 revision。
4. 用当前 `expectedRevision` 调用 `dashboard_edit_begin` 开始或恢复编辑批次，保存返回的批次 ID。调用方根据自己的数据和问题编写内容，并通过一次或多次 `dashboard_patch` 提交 `put_source`、`put_dataset`、`put_metric`、`put_component`、`set_report_markdown`、`set_view_mode=report`。传入当前 `expectedRevision`。组件与 Markdown 引用在整批操作结束后统一校验，创建与嵌入可以在同一批完成。
5. 用最新 `expectedRevision` 和批次 ID 调用 `dashboard_edit_finish`；完整 Doctor 检查通过后生成一个检查点。检查失败时保留草稿、修正问题再完成批次。`dashboard_validate` 可用于中途结构检查，不能替代批次完成。
6. 完成后预览一次，优先使用当前工具列表中的 `dashboard_preview_<uiBuildId>`；固定名称 `dashboard_preview` 保留兼容。只有预览工具声明界面资源。没有 UI 的宿主可通过本地 CLI serve/export 检查实际页面。
7. 核对数值与单位、图号、图文顺序、指标定义、来源、局限及保存/重载。发生冲突时先读取新版本，不盲目覆盖。

MCP 负责发现、验证、保存和渲染声明；调用它的模型或程序负责撰写分析文字。工具不会自动编造推断，也不会在筛选后悄悄改写文字。

## 内容合同

报告源文就是普通 Markdown；顶层 `chart` 围栏的 JSON 引用已声明组件：

````markdown
## 月度变化

如[图](#fig-monthly)所示，先说明观察及依据，再展示图表。

```chart
{"componentId":"monthly","caption":"月度收入","source":"来源：已核对的数据快照，单位万元。"}
```

继续解释图表，并说明不确定性。
````

不在源码里手工锁定图号；渲染器按顺序编号。图表配置是数据，不执行任意 JavaScript/HTML。真实报告不得直接沿用案例数值、来源或结论。默认空白创建不会注入示例数据。

## 声明式图表的适用范围

新建交互图表使用 40 个原版注册代码，通过 `kind=legacy`、`family` 和 `config` 保留已有渲染器，并明确提供 data/presentation。需要筛选时再声明受支持的数据集、指标和字段绑定；不能只给 code 或 datasetId 就认定图表可正确计算。`chart_declarations` 按 `code` 查询，拒绝 `chartType` 参数；历史通用图表保留兼容读取。目录条目数与渲染器数不同，以当前目录和声明返回的范围为准。可选统计图使用单独的 statistical 声明。

案例中的 Dashboard 和报告可复用相同数据声明，但分别生成独立文档。Dashboard 按看板布局打开，报告按 Markdown 单栏正文打开，页面不提供两种类型的切换按钮。生成阶段通过 `set_view_mode` 明确文档类型；报告只选择需要的图表嵌入正文。

## 指标口径、数据说明与备注

使用标准 Markdown 脚注语法：正文 `收入[^revenue]`，末尾定义 `[^revenue]: 指标按观察范围对收入求和，单位万元。` 渲染为带编号、可跳转和返回正文的文末「注释」。重复引用复用编号；未定义的引用保留为原文，交付前应补齐。网页没有稳定分页，故不假称为逐页页脚。较长定义放在普通 `## 附录：指标口径` 中。母稿同时演示注释与附录，正文与说明均由调用方通过 `set_report_markdown` 生成并保存。

## 两个对照看板案例

`executive-dashboard` 与 `operations-scorecard` 使用同一份合成数据与指标，构图完全不同：前者为经典三段式（mc01–mc04、t06、c01），后者使用 `scorecard` 布局模板、mc16 主指标、mc11 环形、mc13 子弹目标、mc14 双期对比、mc12 迷你柱与 mc05 仪表，以及 c02 排名、c03 预算对实际、t01 走势，并以 `apply_layout_template` 而非手写坐标排版。两者都不应被整体复制：先用 `chart_recommend` 按问题选图、按 `kpiGuide` 选指标卡、用 `layout_templates` 选构图。选型规则见 `skills/executive-charts/references/kpi-cards.md` 与 `layout_templates.md`。

## 完整经营看板案例与能力边界

`executive-dashboard` 使用独立编写的 `executive_document`，不从 HTML 提取配置作为生产输入。视觉母稿是 `skills/executive-charts/examples/sample_executive_monthly.html`：桌面首行保留 mc01 收入、mc02 客座率、mc03 旅客量趋势、mc04 预算推进四卡。页面说明通过 `set_meta` 保存 subtitle、org、system、statusText、iconKey（chart 或 plane）；组件说明使用 `subtitle`。来源明确是 fixture，状态文字不表示真实、实时或已认证的数据。

所有四卡及 t06 都声明数据集和指标 binding。收入与旅客量求和；客座率、预算达成率、收益变动率用分子总和除以分母总和。mc03 趋势来自 timeField，mc04 进度 percent 从达成率乘 100；案例不填没有基期证据的同比或环比。t06 同时提供合法的 month/quarter 合成快照，再通过日期字段绑定按月与季度重算。区域、日期范围及区域文本搜索筛选均明确列出 componentIds；空 values 表示不筛选。文本搜索可用 `contains`，指定一个文本 values、明确 field 与 componentIds，不执行隐式跨字段搜索。

`chart_declarations {"code":"t06"}` 和 `{"code":"m01"}` 各返回自身合法的完整合成声明。m01 可以展示目标对比快照，但没有通用筛选绑定；不能用 c01 示例冒充它。目录每个代码的 `filterBinding` 指明 supported、snapshotOnly 与显式绑定要求。当前可绑定代码以 `dashboard_runtime/bindings.py` 为准；其余形状需要单独审查数据变换，不能只把数据集名称写上就宣称支持筛选。mc07–mc09 排名、阈值和拆分辅助字段也没有完整动态变换。

表格列头优先使用 `columns[].title`；`label` 保持兼容，未提供两者时使用 key。真实交付须替换 fixture 来源与数据，重新计算全部说明、基期比较及指标，不沿用合成案例结论。
