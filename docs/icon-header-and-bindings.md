# 图标、标题区与原版数据绑定

## 适用范围与交互约束

本文约定 Runtime 网页、MCP App、Runtime CLI HTML 导出和独立网页部署包中的组件交互；这些入口复用 Runtime 构建。`generate_chart.py`、`generate_dashboard.py` 与 workspace build 使用独立 HTML 生成器，其卡片结构与默认分页保持该生成器的合同，不直接套用 Runtime 操作区。

Runtime 看板、图表、KPI 和表格的标题与描述在左上角，操作位于右上角。图标使用 Lucide SVG，不使用字符、Emoji 或 icon font 冒充图标；图标按钮保留 aria-label、悬停提示和键盘焦点。菜单、表单及数据保留正常文字。SVG 为 16px、1.65 描边，图标点击区为 28px。

Runtime 图表标题不显示 C01 等代码标签；独立 HTML 生成器保留图表代码标签。注册代码仍用于组件选型与渲染，不代替组件稳定 ID。

图表右上角直接保留图表／数据表、导出数据、复制图片、全屏、指标定义与语义，以及适用的月／季度切换。窄卡片允许操作区换行，不把这些入口统一藏入更多菜单。原图形的几何、指标卡主体、微图、复杂标记、单位、Tooltip 和定义内容继续由原版源码提供。

表格保留“自定义列配置”和“导出 Excel (CSV)”文字入口，以及底部分页和每页条数选择；表内搜索只搜索当前表。阅读时的列配置、排序、页码、筛选和粒度只影响当前查看状态，不写回正式设计。编辑状态的表格呈现可保存至 tableState，未知列、重复列和非法状态会拒绝。

预览与编辑分开。布局拖动仅在编辑模式启用，卡片尺寸调整关闭；新增、复制、删除组件和导入数据通过 API/CLI 完成。编辑时显示兼容的图表类型切换，目前 c01/c02 可互换，其他图表显示当前类型及无兼容类型的原因。批注仅通过查看模式的位置批注入口使用，具体行为见 [批注说明](annotation-composer.md)。

静态 HTML 快照只读。独立网页部署包可在浏览器内筛选，但仍不提供设计编辑或上游数据刷新，不表示存在后端编辑连接。

## 旧组件的数据联动

旧 Workspace 的可视化配置原样保留。需要联动时给组件明确的 binding，不能把旧聚合快照猜成可任意筛选的明细。

```json
{
  "kind": "legacy",
  "family": "chart",
  "title": "区域收入",
  "config": {"code": "c01", "data": {"categories": ["华东"], "values": [100]}, "presentation": {"axisLabels": {"x": "收入", "y": "区域"}, "seriesLabels": ["收入"], "tooltipValueLabels": ["收入"], "units": ["万元"], "tableHeaders": ["区域", "收入"]}},
  "binding": {
    "datasetId": "sales",
    "categoryField": "region",
    "categoryTarget": "categories",
    "measures": {"values": "revenue"}
  }
}
```

sales 必须是已有 Dataset；revenue 必须是与它绑定的指标 ID。`put_component` 自动归一化 datasetId 和 measures；校验器要求所有系列绑定完整。绑定不能改变原 config 快照，渲染时才计算视图。各筛选器仍需要明确列出 componentIds。

当前支持的系列映射见 `dashboard_runtime/bindings.py`：按一维分类聚合的原图形、mc01–mc06 指标卡、明细表。mc03 还需 timeField。时间序列设置 timeGrain 后，日期字段必须声明为 date，并使用 ISO 日期。季度比例使用 SUM(分子)/SUM(分母)，不平均月度百分比。展示单位换算必须显式声明 scale。

未启用动态编码的气泡图 `r02` 的绑定使用 `categoryTarget: "clusters"`，并将 `measures` 的 `x`、`y`、`size` 分别绑定到三个已有指标。`categoryField` 是字符串类型的业务对象标识，例如代理 ID；每个标识汇总为一个气泡，标识也作为图上文字。筛选后按各指标定义重新汇总；缺少任一指标或气泡大小为负的对象不显示。点击气泡可临时筛选同一数据集中参与联动的其他组件，再次点击或清除筛选可取消。绑定气泡图的提示和数据表仅展示这三个指标，不自动计算比值。原有未绑定的气泡图保持原样。动态编码分支的等大点、显式面积编码、描述字段、提示框与跨数据集下钻统一见 [动态编码](dynamic-encoding.md)，不套用本段的三指标快照限制。

复杂网络、层级、矩阵、统计分布及 mc07–mc09 的动态绑定仍需专门变换契约；当前拒绝不完整映射，而不是补造数据或把图形简化成柱状图。这些图形的原版静态配置仍完整可用。

旧 KPI 没有绑定的同比/环比辅助值不能在筛选后继续展示为当前事实；比较绑定的计算方式见动态编码文档。

## 验证

运行 `npm --prefix runtime-ui install && npm --prefix runtime-ui run build`，然后 `python -m pytest tests/runtime -q` 和 `node --test tests/runtime/*.test.mjs`。

`test_icon_contract.py` 用真实 Chromium 实际渲染 40 款图表与 9 类 KPI；逐个检查左标题/右操作、SVG 与可访问名称、图表和表格切换、说明弹窗及 CSV 下载，并输出每个组件截图和 coverage.json。它是渲染与交互回归测试，不是与历史版本逐像素一致的声明。

`test_binding_browser.py` 验证同一显式筛选对原图表、KPI、表格生效，以及表格列设置刷新后保留。仍需在用户实际 Codex 宿主验证 MCP App。数据库执行连接器、远程 MCP、多用户权限与托管发布沿用项目文档中已说明的未实现边界。
