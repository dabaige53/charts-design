# 图标、标题区与原版数据绑定

## 交互约束

所有看板、图表、KPI、表格卡片的标题与描述在左上角；操作位于右上角。主界面按钮使用 Lucide SVG，不使用字符、Emoji 或 icon font 冒充图标。按钮保留 aria-label、悬停提示和键盘焦点。菜单项、表单和数据本身保留正常文字，避免让用户猜每个图标。

16px SVG、1.65 描边、28px 点击区。窄卡片收起次要操作到右上角更多菜单；功能没有删除。时间粒度、图表类型、明细搜索、列设置、每页条数使用图标入口和弹出菜单。表格分页操作也移到右上角，记录数保留在左侧。布局拖动手柄仅在编辑模式出现。原图表的几何、指标卡主体、微图、复杂标记、单位、Tooltip 和说明仍由原版源码提供。

网页、CLI HTML 导出、MCP App 共用同一个构建包。静态 HTML 是只读快照，不能冒充有后端连接的编辑器。

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

气泡图 `r02` 的绑定使用 `categoryTarget: "clusters"`，并将 `measures` 的 `x`、`y`、`size` 分别绑定到三个已有指标。`categoryField` 是字符串类型的业务对象标识，例如代理 ID；每个标识汇总为一个气泡，标识也作为图上文字。筛选后按各指标定义重新汇总；缺少任一指标或气泡大小为负的对象不显示。点击气泡可临时筛选同一数据集中参与联动的其他组件，再次点击或清除筛选可取消。绑定气泡图的提示和数据表仅展示这三个指标，不自动计算比值。原有未绑定的气泡图保持原样。

复杂网络、层级、矩阵、统计分布及 mc07–mc09 的动态绑定仍需专门变换契约；当前拒绝不完整映射，而不是补造数据或把图形简化成柱状图。这些图形的原版静态配置仍完整可用。

表格的列顺序、显隐、页码、每页数量、排序持久化在 tableState。未知列、重复列和非法状态会拒绝。旧 KPI 没有绑定的同比/环比辅助值不能在筛选后继续展示为当前事实。

## 验证

运行 `npm --prefix runtime-ui install && npm --prefix runtime-ui run build`，然后 `python -m pytest tests/runtime -q` 和 `node --test tests/runtime/*.test.mjs`。

`test_icon_contract.py` 用真实 Chromium 实际渲染 40 款图表与 9 类 KPI；逐个检查左标题/右操作、SVG 与可访问名称、图表和表格切换、说明弹窗及 CSV 下载，并输出每个组件截图和 coverage.json。它是渲染与交互回归测试，不是与历史版本逐像素一致的声明。

`test_binding_browser.py` 验证同一显式筛选对原图表、KPI、表格生效，以及表格列设置刷新后保留。仍需在用户实际 Codex 宿主验证 MCP App。数据库执行连接器、远程 MCP、多用户权限与托管发布沿用项目文档中已说明的未实现边界。
