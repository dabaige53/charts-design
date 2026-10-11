# 两条生成路径：Dashboard 与分析报告

两条 Skill 独立保留，共用来源、数据集、指标和声明式图表。MCP 不仅提供截图或母稿：它提供可读取的案例、声明合同和原子写入工具，调用方可以从空白文档生成完整内容。

| 目标 | Skill | 可执行参考案例 |
| --- | --- | --- |
| KPI、图表、表格、筛选组成的 Dashboard | `skills/executive-charts/SKILL.md` | `charts://examples/executive-dashboard` |
| Markdown 正文与嵌入图表组成的论文式报告 | `skills/analytical-reports/SKILL.md` | `charts://examples/academic-report` |

原 Dashboard HTML 案例继续保留在 `skills/executive-charts/examples/`。分析报告以当前认可的学术单栏案例作为母稿；其唯一 Markdown 源文是 `dashboard_runtime/examples/academic-report.md`，CLI 示例和 MCP 案例均从它读取。

## 从空白报告生成，而非套一个静态页面

1. `generation_examples {}` 发现两种案例；`generation_examples {"caseId":"academic-report"}` 返回母稿 Markdown、明确标注的合成来源、数据/指标/图表声明及完整 `operations`。
2. `chart_declarations {}` 发现类型索引，`chart_declarations {"chartType":"line"}` 或 `{"code":"c01"}` 阅读所选声明要求与工作示例；`chart_catalog {}` 选择合适图表；`charts://contract` 阅读操作合同。相应资源为 `charts://declarations`、`charts://catalog`。
3. `dashboard_create {"dashboardId":"my-report","title":"我的分析报告"}` 建立空白文档，取得 revision。
4. 调用方根据自己的数据和问题编写内容，并通过一次 `dashboard_patch` 提交 `put_source`、`put_dataset`、`put_metric`、`put_component`、`set_report_markdown`、`set_view_mode=report`。传入当前 `expectedRevision`。组件与 Markdown 引用在整批操作结束后统一校验，创建与嵌入可以在同一批完成。
5. `dashboard_validate` 检查结构；`dashboard_preview` 返回同一真实渲染器使用的文档，并向支持 MCP Apps 的宿主暴露 UI。没有 UI 的宿主可通过本地 CLI serve/export 检查实际页面。
6. 核对数值与单位、图号、图文顺序、指标定义、来源、局限及保存/重载。发生冲突时先读取新版本，不盲目覆盖。

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

原生八类图表绑定数据集、指标及字段，适合快速声明、聚合、筛选和嵌入报告。原组件以 `kind=legacy`、`family` 和 `config` 保留已有渲染器，仍需完整显式 data/presentation；不能只给 code 就期待生成正确业务含义。目录条目数与渲染器数不同，最新资源会分别说明计数和合同覆盖范围。

案例中的 Dashboard 和报告使用相同数据声明，报告只选择需要的图表嵌入正文。二者不会互相替换布局，也不会因为切换呈现而执行 SQL。

## 指标口径、数据说明与备注

使用标准 Markdown 脚注语法：正文 `收入[^revenue]`，末尾定义 `[^revenue]: 指标按观察范围对收入求和，单位万元。` 渲染为带编号、可跳转和返回正文的文末「注释」。重复引用复用编号；未定义的引用保留为原文，交付前应补齐。网页没有稳定分页，故不假称为逐页页脚。较长定义放在普通 `## 附录：指标口径` 中。母稿同时演示注释与附录，正文与说明均由调用方通过 `set_report_markdown` 生成并保存。
