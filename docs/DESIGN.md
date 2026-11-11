---
name: charts-design UI
description: 面向经营分析的紧凑看板、指标卡、图表和数据表格
colors:
  primary: "#123b5d"
  focus: "#2c6485"
  brand-ink: "#051c2c"
  canvas: "#f5f5f4"
  surface: "oklch(1 0 0)"
  foreground: "oklch(0.147 0.004 49.25)"
  on-primary: "oklch(0.985 0.001 106.423)"
  muted: "oklch(0.97 0.001 106.424)"
  muted-foreground: "oklch(0.553 0.013 58.071)"
  border: "oklch(0.923 0.003 48.717)"
  destructive: "oklch(0.577 0.245 27.325)"
typography:
  page-title:
    fontFamily: "'Inter Variable', sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.4
  component-title:
    fontFamily: "'Inter Variable', sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "'Inter Variable', sans-serif"
    fontSize: "13px"
    lineHeight: 1.5
  label:
    fontFamily: "'Inter Variable', sans-serif"
    fontSize: "12px"
    fontWeight: 500
  metric:
    fontFamily: "'Inter Variable', sans-serif"
    fontSize: "clamp(28px, calc(32px * var(--metric-scale, 1)), 48px)"
    fontWeight: 600
    lineHeight: 1.2
  formula:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
    fontSize: "11.5px"
rounded:
  square: "0px"
  detail-card: "8px"
  detail-dialog: "12px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label}"
    rounded: "{rounded.square}"
    height: "32px"
    padding: "0 12px"
  button-outline:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    typography: "{typography.label}"
    rounded: "{rounded.square}"
    height: "32px"
    padding: "0 12px"
  button-icon:
    textColor: "{colors.foreground}"
    rounded: "{rounded.square}"
    size: "24px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    typography: "{typography.label}"
    rounded: "{rounded.square}"
    height: "32px"
    padding: "4px 10px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.square}"
    padding: "12px 16px 16px"
---

# Design System: charts-design UI

## Overview

**Creative North Star: "清晰层级、精确结构与稳定节奏"**

界面用于查看经营数据、比较指标、调整筛选和追溯计算依据。以紧凑密度、稳定布局和清楚的操作反馈组织内容。页面使用淡灰底，数据组件使用白色表面；操作色保持克制，数据色继续承担图表编码。

设计变量来自当前 React 源码；修改组件后同步更新本文。

**Key Characteristics:**

- 层级清楚：页面标题、组件标题、主数值和辅助文字各有用途。
- 结构精确：共享组件统一尺寸、内容边距与状态。
- 节奏稳定：数据更新保留原内容，不让加载提示挤动卡片。
- 内容可信：指标定义、公式和明细来自当前组件绑定。

实现入口为 [`runtime-ui/src/styles.css`](../runtime-ui/src/styles.css) 和 [`runtime-ui/src/components/ui`](../runtime-ui/src/components/ui)。[产品 React 组件](design-system/project/react-ui.md) 负责组件导出、设计映射和构建入口；[图表 UI 保留说明](design-system/project/chart-ui.md) 负责图表来源。归档 PDF 的字体、Electric Blue 与运行组件的当前变量分别维护，不混成一套值。

配套文件为 [`.impeccable/design.json`](.impeccable/design.json)。按项目规则，文档及配套预览保存在 `docs/`，不在根目录再建同名副本。工具需要显式读取这两个路径；不假定根目录自动发现已接通。

## Colors

### Primary

`primary` 为深海蓝，承载主要动作和选择状态。`focus` 为蓝色焦点，承载键盘焦点与交互边界。`brand-ink` 为深色标题和主数值用色。

### Neutral

`canvas` 为页面底色；`surface` 为卡片、输入和弹窗表面。`foreground` 承载正文，`muted-foreground` 承载次要说明。`muted` 用于辅助表面，`border` 用于输入边框和表格分隔。

`destructive` 表达破坏性操作和错误。图表分类色独立维护于 [`chart.tsx`](../runtime-ui/src/chart.tsx)。

**The Source Separation Rule.** 操作变量、图表数据色和归档参考分别维护；复制参考页面时不能覆盖当前运行变量。

页面使用浅色主题，图表与详情面板使用白底。

## Typography

界面正文、页面标题和组件标题使用 Inter 无衬线字体；Lora Variable 随资源提供。

| 角色 | 用途 |
| --- | --- |
| `page-title` | 看板页首标题 |
| `component-title` | 图表、指标卡和表格的卡片标题 |
| `body` | 全局正文基准 |
| `label` | 控件、表格、辅助说明的紧凑字阶 |
| `metric` | 指标卡主数值；使用等宽数字，随容器缩放 |
| `formula` | 详情中的计算公式 |

非 KPI 卡片描述随容器在 12–16px 之间调整。KPI 禁止副标题、描述或解读段落；仅保留标题、数值、单位、比较值和必要数值标签。主数值和辅助数值分别缩放，组件标题保持统一字阶。报告正文使用 `.prose-report` 单栏排版。

**The Title Role Rule.** 新组件复用组件标题角色，不按图表类型自行添加一套大标题。

## Layout

看板采用 GridStack 网格。按网格容器宽度分为三档：小于 600px 为 4 列，600px 至小于 1000px 为 8 列，1000px 起为 12 列。单元高度为 48px，网格 `margin` 为 8px。这是容器断点，不等同于所有控件的屏幕断点。

页面主体默认内边距为 16px；小屏为 12px。页首可换行，标题和操作分组排列。筛选栏使用白色表面、细边框和 12px 内边距；常用条件同组排列，更多条件展开，生效条件在独立行表达。

卡片基准水平内边距为 16px，上方为 12px、下方为 16px；普通卡片内容间隔为 12px，指标卡为 8px。实际尺寸乘以组件的容器缩放系数，避免将基准值误当成所有卡片的固定尺寸。

短表按实际行高收缩，默认最多按 10 行计算高度；保留用户明确保存的非默认尺寸。查看模式锁定网格；编辑模式才启用拖动与缩放。

**The Stable Update Rule.** 查询期间保留已有组件。更新提示不占据卡片正文空间，局部操作只更新相关内容。

## Elevation & Depth

主要通过淡灰页面、白色卡片和细分隔建立层次。当前 Card 使用 Tailwind 的 `shadow-sm` 和一层低透明度细轮廓；不要将归档 PDF 的 elevation 等级直接套进当前组件。

Tooltip 使用前景色表面及小阴影。Dialog 默认遮罩为低透明度黑色并使用轻微背景模糊；详情弹窗在遮罩上显示独立白色表面。浮层负责提示和聚焦，不用于装饰普通卡片。

阴影值由 Tailwind 构建生成。

## Shapes

按钮、输入和主卡片以直角为主。详情中的说明块使用 `detail-card` 圆角，详情弹窗使用 `detail-dialog` 圆角。基础样式虽然提供半径变量，各组件是否使用圆角仍由实际组件决定，不建立“全站统一圆角”的假规则。

输入与表格采用细边框。图标使用 Lucide；项目现有的指标信息图标沿用共享 SVG。新增图标不得用文字字符或 emoji 替代。

## Components

### Buttons and inputs

默认按钮与输入采用前置信息中的高度和紧凑字阶。按钮另有 24、28、40px 高度；图表的紧凑图标操作为 24px。主要动作使用实色，辅助动作使用描边或无底色样式。

按钮保留 hover、键盘焦点、禁用和错误状态；禁用时降低透明度并阻止操作。输入用焦点色强调边框，错误用错误色表达。占位文字不替代输入名称。

### Filters and selection

单选、多选、日期范围、数值范围和生效条件复用共享控件。多选保留搜索、数量、全选和清除能力。图表联动条件可以单独取消，也能通过全部重置清除。候选项、临时筛选状态及数据查询的职责见 [Runtime 说明](dashboard-runtime.md)。

### Cards and chart actions

卡片使用标题、操作和内容的共享结构；非 KPI 卡片可带描述。KPI 的定义、公式和解释放在详情中，不放在卡片正文。图表和表格操作区在右侧；窄卡片的工具栏由共享 `ChartToolbar` 处理，不为每张卡重新设计一组按钮。图表预设是起点，不是形态上限；自由 ECharts 和 HTML/JavaScript 组件沿用同一外壳，按实际能力显示操作。

指标卡内容在可用高度中居中。辅助信息只在有业务含义时显示，不重复堆放“目标”“均值”等空泛副标题。图形、单位、图例和数据提示保留各图表自己的语义。

### Tables

表格使用 12px 正文和等宽数字，表头与内容行的最小高度为 36px；内容单元上下内边距为 8px、左右为 12px。表头和对应列内容共享对齐基准，排序图标独立留位，不挤动标题文字。

当前默认列标题和对应的数字、日期、文字内容全部居中，排序箭头独立留位。这是用户于 2026-11-10 确认并已落实到共享表格组件的约定；当前 DataTable 不再按列 `align` 改为左右分列。卡片标题与列标题是两件事。

主表默认每页 10 行，搜索、排序、分页由 Runtime 执行；列显示及顺序复用列配置面板。底部排列行数、每页条数和分页。不要用空白行凑满高度。

### Details

指标详情使用宽度上限 720px、最大高度 85vh 的弹窗和 52px 固定标题栏；正文单独滚动。顶部章节导航按实际内容显示图表结构、指标口径、表格字段、明细数据和数据来源。点击导航平滑上下滚动到对应章节，遵循减少动态效果设置。章节标题与正文共用左边界，来源信息使用固定标签列。

图表结构统一展示组件保存的 `structureDiagram`，由 Agent 根据每张图的实际结构生成静态 SVG 与标注，同批保存。简图居中并随容器缩放，图表宽度不超过 600px，指标卡宽度不超过 480px；结构区域不设置内部滚动。前端按统一坐标缩放并绘制直角引导线；点击标签突出连线，图下仅显示名称与描述，再次点击收起。有关联指标时直接读取当前指标定义。缺少简图显示“结构说明未配置”，声明修改后未提交简图显示“结构说明待更新”，均保留其余详情。简图展示固定结构，业务数值和筛选结果由图表另行呈现。

每个指标使用一张独立卡片，浅色标题区将单位以括号紧跟指标名称，并可展开或收起；卡片正文默认展开六个字段：业务定义、统计范围、计算公式、汇总方式、数值显示、计算边界。业务定义和统计范围占整行，其余字段分两列，窄屏改为单列。范围采用标签，明确声明的比例计算采用分式，汇总过程采用箭头，数值显示提供标注为格式预览的样式。未配置规则明确标注，不推造业务口径；不重复增加“字段与图形映射”模块。

公式使用浅底色和细边框。绑定指标优先采用当前声明，不能用目录案例公式填补空结果。MCP 中绑定数据集的组件可以在底部读取筛选后的明细，默认每页 10 行；静态快照不据此获得实时查询能力。

### Motion and feedback

图表保留实例，以稳定系列标识合并结果；数据更新使用 260ms 过渡，首次绘制和尺寸调整不播放入场动画。指标卡主数值、进度条和环形进度采用同量级更新过渡。

柱状图选中类别保留原色，其他柱子变灰；再次点击同一来源、同一类别取消选择。生效条件行展开、收起采用短过渡。系统要求减少动态效果时直接呈现最终状态。

请求失败时保留错误说明和可执行的恢复动作。位置批注使用选择锚点、编号和编辑结构，详见 [批注说明](annotation-composer.md)。

## Do's and Don'ts

### Do:

- **Do** 复用共享组件和当前语义变量，修改后同步设计记录。
- **Do** 保持标题角色、表头与数据对齐、图标尺寸和边距一致。
- **Do** 用真实绑定解释指标，保留单位、筛选范围和明细入口。
- **Do** 在局部更新中保留内容、选择状态和减少动态效果路径。
- **Do** 分别维护设计资产、运行源码与打包产物。

### Don't:

- **Don't** 将归档 PDF 的字体、操作色或尺寸写成当前产品已经使用的值。
- **Don't** 将讨论、构建成功或静态预览写成 MCP 宿主已完成验收。
- **Don't** 在数据更新时清空整张卡片，或用加载文字挤动图表。
- **Don't** 为缺少定义的指标编造公式、阈值或来源。
- **Don't** 用一套全局圆角或图表大标题覆盖现有组件差异。

## 组件复用、画板与保真

使用共享基础组件及完整的交互结构，保留键盘操作、焦点、可访问名称，以及加载、空、错误、禁用和选择状态。安装与组合组件前检查现有配置和官方接口；不只改自制控件外观来替代其交互能力。

一个组件类型一个画板，相关状态与附属操作集中维护；同类相邻排列，保留用户布局、内容和导航。设计资产是参考与编辑成果，生产代码从维护源码构建，不从案例提取业务内容。

导入、迁移和视觉重构逐项保留图表类型、几何、比例、坐标、基线、排序、单位、精度、图例、标签、Tooltip、预测、置信区间、阈值、目标线，以及已有筛选、联动、下钻和动态编码。复杂形态保持自身逻辑，不替换成普通柱状图；指标卡不替换成文本。

原图表配置、presentation、指标卡类型与数值字段、表格列和行都应无损保留。组件外壳、可用粒度切换、数据表、导出、全屏和指标详情按实际能力保留。

表格保留排序、列配置、显隐与重排、恢复默认、分页和导出。已汇总快照不会因导入而自动支持交叉筛选；其已有筛选声明保留为元信息，动态工作需要明确数据绑定。预设切换必须经过兼容检查，不能任意转换所有图形。

迁移应检查配置、绑定和交互语义，而不只对照外观。已经在历史导入中丢失的字段只能从原资产恢复，不能由新渲染器推造。

维护时机：通用视觉、交互、组件复用或迁移保真要求改变时更新；组件接口与实现状态维护在组件清单，单次检查保存到 records/。
