# MCP 原生创作与可选文件构建

直接将 JSON 对象作为 MCP 工具参数。读取目标服务的 `charts://contract` 和所选 `chart_declarations` 后，使用既有原生操作创建与修改；无需先运行 shell、生成 JSON 文件或建立脚本工作区。已有文件需要审阅、离线编辑或批量提交时，使用[声明文件流程](dashboard-workspace.md)。

## 直接初始化小型看板

已有小型数据及明确字段、口径时，用一个 `dashboard_submit` 请求提交来源、数据集、指标、组件、筛选和布局。将 `projectRoot` 换成当前项目的本地绝对路径或远程配置名，选一个未占用的 `dashboardId`，传 `createTitle`；已有成果改用 `dashboard_get` 返回的 `expectedRevision`。

以下是可执行的**合成演示**，包含收入卡和明细表。只在显式需要演示时使用独立示例项目；真实任务直接按同样操作声明当前业务数据，不先注入这些示例行、fixture 来源或指标定义。

```json
{
  "projectRoot": "/absolute/path/to/example-project",
  "dashboardId": "native-demo",
  "createTitle": "合成收入示例",
  "operations": [
    {"op": "put_source", "id": "fixture", "value": {"kind": "fixture", "name": "合成演示数据，非真实业务"}},
    {
      "op": "put_dataset", "id": "sales",
      "meta": {"sourceId": "fixture", "fields": {"region": {"type": "string", "label": "区域"}, "amount": {"type": "number", "label": "金额（元）"}}},
      "rows": [{"region": "华东", "amount": 128}, {"region": "华南", "amount": 96}]
    },
    {
      "op": "put_metric", "id": "revenue",
      "value": {"datasetId": "sales", "field": "amount", "aggregation": "sum", "label": "收入", "unit": "元", "definition": "合成示例中，对选中区域的金额记录求和；每行表示一个区域的收入。", "status": "unverified"}
    },
    {
      "op": "put_component", "id": "total",
      "value": {
        "kind": "kpi", "title": "收入", "datasetId": "sales", "measures": ["revenue"],
        "presentation": {
          "type": "mc01",
          "structureDiagram": {"version": 1, "viewBox": [0, 0, 240, 100], "svg": "<svg><rect x='20' y='20' width='100' height='45' fill='none' stroke='#64748b'/></svg>", "annotations": [{"id": "amount", "anchor": [120, 42], "label": [160, 42], "align": "left", "metricId": "revenue"}]}
        }
      }
    },
    {
      "op": "put_component", "id": "detail",
      "value": {
        "kind": "table", "title": "收入明细", "datasetId": "sales",
        "columns": [{"key": "region", "title": "区域"}, {"key": "amount", "title": "金额（元）"}],
        "presentation": {
          "structureDiagram": {"version": 1, "viewBox": [0, 0, 240, 120], "svg": "<svg><rect x='20' y='40' width='200' height='60' fill='none' stroke='#64748b'/><path d='M120 40V100M20 60H220M20 80H220' fill='none' stroke='#64748b'/></svg>", "annotations": [{"id": "region", "anchor": [70, 50], "label": [70, 20], "name": "区域"}, {"id": "amount", "anchor": [170, 50], "label": [170, 20], "name": "金额（元）", "description": "每条记录的收入金额"}]}
        }
      }
    },
    {"op": "set_filters", "value": [{"id": "region", "label": "区域", "field": "region", "op": "in", "values": [], "componentIds": ["total", "detail"]}]},
    {"op": "apply_layout_template", "template": "executive", "order": ["total", "detail"]},
    {"op": "set_status", "value": "fixture"}
  ]
}
```

将此对象直接交给 `dashboard_submit`。组件、指标和数据集的引用在整批操作结束后校验；结构图与组件一起保存。成功后用同项目的 `dashboard_view`，传 `responseMode: "patch"`、`componentIds: ["total", "detail"]`、`includeEvidence: true`，核对合计、明细及筛选范围，再调用一次 `dashboard_preview`。新增实际图形时，先读取选定预设的声明，在同一批 `put_component` 中填写真实数据、展示语义和受支持的绑定。

### 报告变体

创建独立报告时，选择新的 ID 与标题，保留已核实的数据和组件操作，在同一 `operations` 中加入以下两项。Markdown 字符串直接传入工具，无需先保存 `.md` 再转成 JSON。示例正文只演示引用，不提供业务结论。

```json
[
  {"op": "set_view_mode", "value": "report"},
  {"op": "set_report_markdown", "value": "# 合成收入报告\n\n以下仅演示正文与组件引用，数据均为合成示例。\n\n```chart\n{\"componentId\":\"total\",\"caption\":\"合成收入\",\"source\":\"合成演示数据\"}\n```\n\n```chart\n{\"componentId\":\"detail\",\"caption\":\"合成明细\",\"source\":\"合成演示数据\"}\n```\n"}
]
```

需要读者筛选控件时将模式设为 `filtered-report`。正文不会随临时筛选重算，数值结论应注明对应范围；真实报告结构与图文核对遵循 [analytical-reports](../../analytical-reports/SKILL.md)。

## 先导入并检查，再编排内容

数据含义尚待检查，或来源需要 CSV 导入、SQLite 附加或 SQL 执行时：

1. 新成果用 `dashboard_create` 建空容器；已有成果读 `dashboard_get`。将返回的修订传给数据写入工具。
2. 小数据用 `dataset_import` 的 `rows` 或 `csvText`，需要明确类型时传 `fields`；空 `rows` 必须有字段声明。SQLite 表和 SQL 使用[本地数据流程](local-data.md)，连接别名与源端 schema 需由当前项目或管理员提供。
3. 回执给出字段、来源、按 ID 映射的指标定义和当前 revision。执行 `nextCalls` 中的 `dataset_preview` 查看数据集小样本，不必先创建临时表，也不必重新构造读取参数。样本不应用组件筛选，不据此推断完整分布；自动求和指标仍为 `unverified`。
4. 用回执修订作为 `expectedRevision`，将核实后的指标、组件、筛选、布局及报告正文一起交给 `dashboard_submit`。数据工具已经登记的来源和数据版本直接复用。需要完整草稿时使用回执中的 `dashboard_get` 调用。

每次写入后沿用新修订；发生冲突或回执不确定时先读当前状态。非法初始操作在创建前被拒绝；`DOCTOR_FAILED` 则表示已有修改草稿，按返回修订修正，不重复创建。不要用新工具链包装来跳过指标口径、图表选型或业务结果核对。

## 已有声明文件

用户已有文件时，直接用统一 Rust CLI 读取、验证与提交。原子操作与 MCP 完全相同，业务文件留在业务项目中：

```sh
charts-design-runtime validate --file document.json
charts-design-runtime --project-root /absolute/path/project call dashboard_submit --json-file submit.json
```

`submit.json` 是完整工具参数对象，包含看板 ID、初始标题或当前修订，以及相关操作。提交成功后取新修订；冲突时先读当前草稿再合并。完整文档可用 `import` 创建新 ID，已有旧格式工作区可用 `import-workspace`。详细命令见[声明文件](dashboard-workspace.md)。

## 将源端记录映射为可计算的 MCP 页面

- `manifest.sources` 记录实际来源；`manifest.datasets` 声明行粒度对应的字段类型，行或版本引用位于 `snapshot`。少量数据用 `put_dataset`；已有版本用 `put_dataset_ref`。文件与 MCP 均显式提交同一条 `put_dataset_ref` 操作。同一引用必须在目标项目可读。大数据使用[已有导入和上传工具](mcp-delivery.md#project-and-data)。
- `manifest.metrics` 保存业务定义、聚合、单位、比例和精度。区分行粒度汇总、按实体去重和基期计算。用 `dashboard_view` 核对实际计算结果。图形、表格和下载都应能追溯到审查表上的定义。
- 图形用 `kind=legacy`、`family=chart`，`config.code` 决定渲染器，`binding` 决定数据集、分类、系列及指标。预设的堆叠、排名、气泡和跨数据集联动示例见[动态编码](../../../docs/implementation/dynamic-encoding.md)。先核对每个目标的原生能力；缺少事件或状态语义时，记录影响、现有适配入口与验证条件。
- `set_filters` 整体替换保存的筛选定义。读者临时选值通过 `dashboard_view.filters` 提交，从当前 manifest 复制完整的筛选数组，仅修改选中的 `values`，保留其他条件及每项的字段和消费者。原生 `in` 条件的空数组表示清除此条件。读取选项用 `dashboard_filter_options` 的 filterId、offset、limit；候选集与当前已选值分别验证。Markdown 报告有正文级及独立表内筛选时，使用 `filtered-report`，表内条件写 `scope:"table"` 并给一个表格消费者。
- 如果来源已经是本项目 schema-v1 workspace，先用[工作区命令](dashboard-workspace.md)维护拆分资产，并用 Runtime CLI 的 `--project-root … import-workspace ID --path DIR` 导入新看板。检查返回的 migrationNotes，核对原始筛选和组件的数据绑定后再验收。任意第三方 HTML 或 Excel 走[外部历史报表审查](existing-project-checklist.md#从外部历史报表迁入-mcp)。

## 核对、保存与导出

1. 按业务问题明确预期筛选；迁移时由源端审查据原件列出每页行为。将实际 `set_filters` 与预期稳定 ID、field、**全部** componentIds 及选中状态比较。文件工作流可将预期保存为数组，无筛选写 `[]`，用 `author check-filters "$work/document.json" "$work/expected-filters.json"` 检查遗漏、多余及消费者差异。声明检查之后，用相同授权、数据版本及选中状态逐一重放受影响事件，核实受影响与不受影响组件；迁移的数值证据来自原报表，不能从待验声明反推。
2. 将原生参数直接交给 `dashboard_submit`；文件工作流则读取生成的 `submit.json` 作为参数。新页请求含 `createTitle`，已有页请求含基线 `expectedRevision`。服务执行编辑、检查并保存。导入已审阅的完整文档时才使用 `dashboard_create`，文件构建对应 `--format create`，随后按返回版本提交检查。
3. 从数据写入回执检查引用和行数，通过 `dashboard_view` 核对受筛选的汇总或表格页。Doctor 失败会保留草稿，读取并提交修正。成功后调用 `dashboard_preview` 读已完成的检查点。
4. 若交付独立交互网页，用 `dashboard_export_site` 返回的本地文件或远程下载链接取得完整 ZIP。核对版本和文件清单，在目标宿主复验筛选、联动、数据权限和导出行数。静态包可包含所用数据集的全部行；有权限分区时须复用实际访问控制并验证直接读取分片的权限。详见[静态部署包](../../../docs/operations/static-deployment.md)。
