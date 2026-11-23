# 用项目脚本构建 MCP 声明

从 Charts Design 仓库或安装包根目录运行[声明脚本](../scripts/mcp_author.py)。使用随该版本提供的 Python 入口。先调用目标服务的 `runtime_info`、读取 `charts://contract` 和有关的 `chart_declarations(code)`；可用版本、操作参数、预设支持的绑定以该连接为准。业务输入、审查清单、工作文件和输出均放在业务工作区。

## 初始化与调整

以下命令假设当前目录为包根，`work` 是已存在的业务目录，`project` 是 MCP 本地项目绝对路径。在远程服务上传入配置的项目名。

```sh
author() { bun bin/python-runtime.js skills/executive-charts/scripts/mcp_author.py "$@"; }
work=/absolute/path/to/authoring
project=/absolute/path/to/mcp-project
author init "$work/monthly" --id monthly --title "月度经营" --mode filtered-report
author stage "$work/monthly" source ledger --value "$work/source.json"
author stage "$work/monthly" dataset sales --value "$work/dataset.json"
author stage "$work/monthly" metric revenue --value "$work/revenue.json"
author stage "$work/monthly" component detail --value "$work/detail.json"
author stage "$work/monthly" filters --value "$work/filters.json"
author stage "$work/monthly" markdown --value "$work/report.md"
author build "$work/monthly" --out "$work/document.json"
author build "$work/monthly" --format create --project-root "$project" --out "$work/create.json"
```

若只准备声明文件，已有 Python 3.10+ 的环境也可在包根以 `PYTHONPATH="$PWD" /path/to/python skills/executive-charts/scripts/mcp_author.py` 执行相同子命令。这条路径只使用随包 Runtime 和 Python 标准库。

每个业务文件装一个原生值。以下为输入形状示例，空数据行须替换成经核对的记录，或先导入数据版本。

| 文件 | 输入示例 |
| --- | --- |
| source.json | `{"kind":"file","name":"月度销售快照"}` |
| dataset.json | `{"meta":{"sourceId":"ledger","fields":{"region":{"type":"string"},"amount":{"type":"number"}}},"rows":[]}` |
| revenue.json | `{"datasetId":"sales","aggregation":"sum","field":"amount","label":"收入","definition":"所选区域及月份内的销售金额合计","unit":"元"}` |
| detail.json | `{"kind":"table","title":"销售明细","datasetId":"sales"}` |
| filters.json | `[{"id":"region","label":"区域","field":"region","op":"in","values":[],"componentIds":["detail"]}]` |
| report.md | 在源文中插入顶层 `chart` 围栏，其中一行 JSON 为 `{"componentId":"detail"}` |

`base.json` 保存构建基线，`steps/` 按文件名顺序执行原生操作，每个 JSON 文件对应一个操作，每个 Markdown 文件对应一次完整的 `set_report_markdown`。重复执行 `stage` 会返回已有文件的位置，直接修改该文件即可。布局、标题等其他原生操作也可写入编号 JSON 文件。正式报告按原图形、字段及指标编写结构图，要求见对应 Skill。需要查看完整可运行样例时，在另一目录显式运行 `author init "$work/example" --id example --example filtered-report`；`--help` 列出其他合成案例。

对于已有 MCP 成果，先把同项目 `dashboard_get` 的完整结构化结果保存为 `get.json`。若收到分块引用，通过同一项目的 `runtime_result_chunk` 还原完整 JSON，详见[传输与诊断](../../../docs/operations/mcp-transport-diagnostics.md)。可指定 `dataMode=local` 保留不可变数据引用。用以下命令抽出原声明，文件包含应保留的字段和稳定 ID。

```sh
author init "$work/revision" --from-document "$work/get.json"
author stage "$work/revision" filters
author stage "$work/revision" component detail
# 修改上两条命令打印的文件，然后构建。
author build "$work/revision" --out "$work/proposed.json"
author build "$work/revision" --format patch --project-root "$project" --out "$work/patch.json"
```

`document` 用于审阅整体 schema-v2 声明；已有设计的 patch 只携带选中的操作及基线 revision。修订其他页时另取该页基线。每次成功写入后再次修改，须以新草稿重新初始化；遇版本冲突也需对照新草稿合并。一个 patch 最多 200 个操作，超过时按能独立校验的依赖组拆批，后续批次取前一批成功回执的 revision。

## 将源端记录映射为可计算的 MCP 页面

- `manifest.sources` 记录实际来源；`manifest.datasets` 声明行粒度对应的字段类型，行或版本引用位于 `snapshot`。少量数据用 `put_dataset`；已有版本用 `{"meta":…,"ref":…}` 交给 `stage dataset`，它生成 `put_dataset_ref`。同一引用必须在目标项目可读。大数据使用[已有导入和上传工具](mcp-delivery.md#project-and-data)。
- `manifest.metrics` 保存业务定义、聚合、单位、比例和精度。区分行粒度汇总、按实体去重和基期计算。用 `dashboard_view` 核对实际计算结果。图形、表格和下载都应能追溯到审查表上的定义。
- 图形用 `kind=legacy`、`family=chart`，`config.code` 决定渲染器，`binding` 决定数据集、分类、系列及指标。预设的堆叠、排名、气泡和跨数据集联动示例见[动态编码](../../../docs/implementation/dynamic-encoding.md)。先核对每个目标的原生能力；缺少事件或状态语义时，记录影响、现有适配入口与验证条件。
- `set_filters` 整体替换保存的筛选定义。读者临时选值通过 `dashboard_view.filters` 提交，从当前 manifest 复制完整的筛选数组，仅修改选中的 `values`，保留其他条件及每项的字段和消费者。原生 `in` 条件的空数组表示清除此条件。读取选项用 `dashboard_filter_options` 的 filterId、offset、limit；候选集与当前已选值分别验证。Markdown 月报有正文级及独立表内筛选时，使用 `filtered-report`，表内条件写 `scope:"table"` 并给一个表格消费者。
- 如果来源已经是本项目 schema-v1 workspace，先用[工作区命令](dashboard-workspace.md)维护拆分资产，并用 Runtime CLI 的 `--project-root … import-workspace ID --path DIR` 导入新看板。检查返回的 migrationNotes，核对原始筛选和组件的数据绑定后再验收。任意第三方 HTML 或 Excel 走[外部历史报表审查](existing-project-checklist.md#从外部历史报表迁入-mcp)。

## 核对、保存与导出

1. 让源端审查子代理据原件列出每页预期筛选。文件采用数组，每项含目标稳定 ID、field、**全部** componentIds；按业务需要增加 label、op、values、selectionMode、scope。无筛选的页写 `[]`。运行 `author check-filters "$work/document.json" "$work/expected-filters.json"`。命令会报告遗漏、多余及消费者差异，可重复对 `dashboard_get` 回读文件执行。此项只核对声明。用相同授权、数据版本及选中状态逐一重放源端事件，核实受影响与不受影响组件。数值证据来自原报表，不能从待验声明反推。
2. 对新页，将 create 请求交给 `dashboard_create`，读取写入后的实际 revision，再调用 `dashboard_edit_begin`。对已有页，先用基线 revision 调用 `dashboard_edit_begin`，再将 patch 请求交给 `dashboard_patch`。本机可用 `charts-design-runtime --project-root "$project" call dashboard_patch --json-file "$work/patch.json"` 调用同名工具。远程用已连接的 MCP。保存 `batch_id` 和最新 revision。
3. 用 `dashboard_data_inspect` 检查引用、行数，`dashboard_view` 检查受筛选的汇总或表格页。核对报告引用和筛选行为后调用 `dashboard_edit_finish`，传入 `batchId` 及最新 `expectedRevision`。Doctor 失败会保留草稿，修复后在同一批次重试。成功后调用 `dashboard_preview` 读已完成的检查点。
4. 若交付独立交互网页，用 `dashboard_export_site` 并按 `dashboard_export_read(format=zip)` 回读完整 ZIP；生成的 `document.json`、Worker 和数据分片由 Runtime 导出。核对版本和文件清单，在目标宿主复验筛选、联动、数据权限和导出行数。静态包可包含所用数据集的全部行；有权限分区时须复用实际访问控制并验证直接读取分片的权限。详见[静态部署包](../../../docs/operations/static-deployment.md)。
