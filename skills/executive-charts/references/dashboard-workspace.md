# 声明文件与 CLI

MCP 创作直接传对象。用户已有文档、操作文件或外部工作区时，用统一 Rust CLI 处理这些资产；文件仍放在业务项目，不写入 Skill 目录。

## 读取、审阅与提交

```sh
charts-design-runtime --project-root /absolute/path/project get overview
charts-design-runtime --project-root /absolute/path/project export overview --format json --output overview.json
charts-design-runtime validate --file overview.json
charts-design-runtime --project-root /absolute/path/project call dashboard_submit --json-file submit.json
```

`get` 输出服务回执，`export --format json` 输出完整文档。`validate --file` 接受文档或含 `document` 的回执，不创建项目。`call --json-file -` 可从标准输入读取工具参数。只有已有文件需要上传或审阅时才走文件流程，不要求 Agent 先生成临时脚本。

提交文件使用当前 `charts://contract` 的对象结构：

```json
{
  "dashboardId": "overview",
  "expectedRevision": 3,
  "operations": [
    {"op": "set_title", "value": "月度经营"},
    {"op": "set_meta", "value": {"subtitle": "已核实的分析范围"}}
  ]
}
```

新成果用 `createTitle` 替代 `expectedRevision`。`set_meta` 整体替换；`put_component` 也替换完整组件，必须保留仍在使用的来源、指标、绑定、结构图和其他配置。每批最多 200 个操作；需要拆批时按能独立校验的依赖组拆分，并沿用最新修订。

需要保存中间草稿时可用 `patch ID --expected REVISION --file operations.json`；完成后用 `dashboard_submit` 检查并保存。修订冲突或未知回执先读实际草稿，不能重放旧写入。

## 数据与组件

- 小型 CSV/JSON 使用 `dataset_import` 的 `csvText` 或 `rows`，显式 `fields` 控制 ID、日期、布尔和数值类型。输入检查拒绝重复表头、错列数和非法值，保留空值与前导零。
- 数据回执提供字段、精确行数、来源与实际指标 ID。执行其 `nextCalls` 的 `dataset_preview` 检查有界样本；全量分布、缺失率与时间范围用来源聚合查询确认。
- SQLite 表与 SQL 使用已配置别名，见[数据流程](local-data.md)。不要生成整表 JSON 放入普通声明审阅输出。
- 图表、KPI、表格、筛选器和布局使用 `chart_declarations` 与 `charts://contract` 的同一结构。预设 `presentation` 必须明确轴、系列、单位和表头；自定义渲染按[组件说明](component-html-generation.md)。
- 报告 Markdown 放在 `set_report_markdown.value`，与引用组件一起提交；JSON 导出保留精确源文。

字段类型推断只解决合法输入，指标口径和单位需要来源证据。样本不自动认证分布，数值字符串不自动剥除单位后求和。

## 导入已有资产

完整文档导入新的 ID：

```sh
charts-design-runtime --project-root /absolute/path/project import imported --file dashboard.json
```

用户提供由 `dashboard.json` 与组件引用文件组成的工作区时：

```sh
charts-design-runtime --project-root /absolute/path/project import-workspace imported --path /absolute/path/workspace
```

导入保留图表、KPI、表格和元信息，拒绝逃离工作区目录的引用。读取导入结果，核实来源、字段、消费者和指标定义，再用 `dashboard_submit` 保存。外部页面先按[源端审查](existing-project-checklist.md#从外部历史报表迁入-mcp)逐项映射，保留有效内容、读图顺序、几何和操作能力。
