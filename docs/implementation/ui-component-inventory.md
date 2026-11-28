# UI 组件清单与接入状态

本文维护组件接口、源码位置、动态能力与宿主边界。原图形资料见[图表参考](../design-system/project/chart-ui.md)。

共享组件接入同一 Runtime，设计画板单独维护。剪贴板、下载、全屏和附到对话取决于目标宿主授权，实际交付时分别确认。

## 版本与分享

维护入口：`runtime-ui/src/version-center.tsx`；由 `dashboard.tsx` 接入。输入为当前文档、工具调用函数及状态刷新回调，编辑未完成或操作繁忙时禁用入口。

| 功能 | 当前能力 | 验证边界 |
| --- | --- | --- |
| 版本 | 保存版本、查看历史、恢复草稿、设为正式发布版、创建独立分享 | `dashboard_publish` 设置正式发布版，`dashboard_share_publish` 从所选保存版创建分享 |
| 分享 | 不过期 / 7 天 / 30 天、创建、替换为当前发布版本、撤销 | 替换生成新链接和密钥；不自动影响其他分享 |
| 状态 | 草稿、已保存、当前发布、过期与待清理 | 以工具返回的实际状态为准 |

## 筛选与联动

维护入口：`runtime-ui/src/controls.tsx`。应用适配：`dashboard.tsx`、`runtime.ts`。

| 组件与用途 | 输入参数 | 输出事件 | 支持状态 | 数据依赖 | 宿主依赖与状态 |
| --- | --- | --- | --- | --- | --- |
| ChoiceSelect：单选 | label、value、options、disabled | onChange(value) | 选择、展开、禁用、焦点 | Choice 列表 | 无；官方 Select，已构建 |
| MultiSelect：可搜索多选 | options、value、loadOptions | onChange(values) | 搜索、分页加载、全选、清空、数量、错误、禁用 | `dashboard_filter_options` 搜索分页；全选读取全部候选页 | 工具调用由应用传入；已接 MCP |
| RangeFilter：数值区间 | label、value、type | onApply(from,to) | 输入、校验、应用、清空 | `dashboard_view` 的范围条件 | 无；已接 MCP |
| DateRangeFilter：日期范围 | label、value | onApply(from,to) | 日历选取、完整区间、清空 | 日期字段与 ISO 日期条件 | 无；已接 MCP |
| ActiveFilters：条件标签 | items、title | onRemove(id)、onClear() | 单项移除、空条件、清空禁用 | 查看状态与图表联动条件 | 无；已接 MCP |
| FilterBar：全局及表格筛选 | document、filters、call | onChange、onClear、onApply | 多维条件、关键词、日期／数值范围、摘要、复制与粘贴筛选参数 | 定义、候选项、查看状态 | 由应用适配工具；剪贴板不可用时可手动复制 |
| 图表点击联动 | 点击点、绑定分类字段、linkGroup | 临时 runtime-linkage 条件 | 再次点击或移除恢复；显式消费者 | 绑定数据集、跨数据集同名字段 | 工具调用；已接 MCP |

在页面配置的 `manifest.filters` 中，为要直接显示的筛选项设置 `"alwaysVisible": true`。同一筛选区只要有一项明确配置该字段，就只常显值为 `true` 的项，按声明顺序排列。其余项放入「更多筛选」。全区都省略时使用默认的前三个非关键词项。配置随保存版和独立分享副本传递，报告顶部与表格各自判断。

「复用筛选」区的「复制」导出当前筛选栏的已选择条件，如 `{"region":["华东"]}`；键为筛选器 ID，值为数组。「粘贴」校验通过后替换当前筛选栏的条件，未列出的条件会清空，必选筛选器仍须提供值。

复制与粘贴仅处理当前查看状态中的筛选栏条件。图表点击联动和已保存的看板配置保持原样。

## 图表与操作

| 组件 | 输入参数 | 输出事件 | 状态与数据 | 宿主依赖 |
| --- | --- | --- | --- | --- |
| EChartSurface | option、label、className | onReady(chart)、onSelect(point) | 自适应、完整图例和原始 Formatter | ECharts；无 MCP 依赖 |
| ChartToolbar | showTable、grain、expanded、操作 callbacks | 图／表、月／季、CSV、图片、复制、放大图表、说明 | 放大按钮直接展示并切换还原图标；不支持的操作禁用并说明原因 | 父组件提供下载、剪贴板和放大弹窗；浏览器全屏下浮层跟随全屏元素 |
| ComponentView | document、id、grain、tableState | onGrain、onTableChange、onInspect、onExport、onSelect | 加载、空、错误、详情；不调用 MCP | 回调适配 |
| 指标定义与语义 | semantic_inspect 结果 | 打开／关闭 | 指标、公式、单位、来源、实际绑定和计算语义 | 实际工具结果；无预览文案替代 |

详情维护入口为 `runtime-ui/src/semantic-details.tsx`，通用简图为 `runtime-ui/src/semantic-structure.tsx`。所有组件通过展示配置的 `structureDiagram` 提供 SVG、统一坐标和标注，不依赖 ECharts option 或图表类型适配器。简图随容器缩放，结构区域没有内部滚动。共享组件负责缩放、直角引导线、标签切换和下方定义；指标引用读取当前声明。章节锚点、默认展开的六字段指标口径、明细查询、来源和表格字段保持原入口。SVG 在后端按静态白名单清理，前端再次清理并作为隔离图片展示。声明参数和失效规则见 [Runtime](dashboard-runtime.md#页面元信息与组件声明)。

各图表保留独立生成逻辑和对应数据表。生产代码读取 `src/charts`；`runtime-ui/fixtures/charts.json` 仅为画板数据。图表 Tooltip 经 DOMPurify 处理。后端统计图保持独立产物，不改用浏览器重算。

40 个预设在 `runtime-ui/src/charts/<code>.ts` 独立维护，画板名称对应 `Chart<CODE>.dc.html`。具体名称、字段与绑定能力从 `chart_declarations` 获取；不要在 UI 清单复制第二份合同。

历史 `kind=chart` 的八种声明另由 `historical-chart.ts` 读取兼容；新图表按上述注册编码声明。

## 指标卡

输入：`config` 中明确声明的值、单位、比较值、目标和趋势。输出：只读显示。数据依赖：Runtime 已计算的组件结果；不从标题猜测公式。主值附近合并必要目标、均值和比较信息，避免独立重复副标题行。

16 种 KPI 使用 `MetricCard`，对应 `Metric01.dc.html` 至 `Metric16.dc.html`。按问题选型与字段要求见[指标卡指南](../../skills/executive-charts/references/kpi-cards.md)及声明发现。

### 指标卡主体接口

| 类型 | 允许的主体内容 |
| --- | --- |
| mc01 | 主数值、同比、必要辅助数值 |
| mc02 | 主数值、同比与环比 |
| mc03 | 主数值、微型面积趋势 |
| mc04 | 主数值、进度条、目标数值 |
| mc05 | 主数值、半环、基准数值 |
| mc06 | 两个同级指标名称和值、各自比较值 |
| mc07 | 排名值和简短排名标记；不显示排名描述段落 |
| mc08 | 主值、简短阈值标记和图标；不添加原因分析 |
| mc09 | 主值、两段比例及对应数值标签 |
| mc10 | 中位数与区间图、均值及样本数量 |
| mc11 | 主值、环形进度、目标数值 |
| mc12 | 主值、迷你柱趋势、同比 |
| mc13 | 主值、实际值、目标与最多三个区间 |
| mc14 | 本期与基期条形、数值和比较标签 |
| mc15 | 1–4 个名称／数值／变化条目，可带总值 |
| mc16 | 突出的主值、比较值；不再显示 note 解读 |

比较使用真实基准，非零比较字符串保留正负号。动态绑定按指标单位格式化，快照声明提供完整显示值。业务完成率可超过 100%，图形进度显示范围为 0–100。

KPI 结构和动态绑定分别按原生声明与编码合同验证。

## 表格

维护入口：`runtime-ui/src/table.tsx`。`Tables.dc.html` 与 `InteractiveTable.dc.html` 分别展示标准表格和交互表格。

| 组件 | 输入参数 | 输出事件 | 支持状态 | 数据与宿主依赖 |
| --- | --- | --- | --- | --- |
| DataTable | config.columns／rows、state、loading、error | onChange、onExport、onSaveState | 搜索、排序、分页、总数、列顺序／显隐、空／错误／加载 | 已分页的 Runtime 行；手动分页和排序，不只处理当前页 |
| TableToolbar | keyword、callbacks | 搜索、列配置／CSV 图标及 Tooltip | 禁用与焦点 | 应用调用 `dashboard_view`、`dataset_export` |
| ColumnSettings | columns、visible、order | onChange、onOrderChange、onReset | 指针拖拽、键盘排序、上移／下移、恢复默认 | dnd-kit；桌面 Sheet、手机 Drawer |
| Pagination | page、pages、pageSize | onChange(page,pageSize) | 首／前／后／末页、每页条数、页数、边界禁用 | 父表由后端总数计算 pages |
| 列配置保存 | 当前列顺序／显隐 | 明确点击保存 | 编辑状态可保存；查看调整为临时状态 | dashboard_submit 与 revision 检查 |

导出读取全部匹配行并保留排序与可见列。后端和静态 Worker 保留原始数值用于排序与 CSV，显示格式与数据值分开。

## 基础控件与反馈

基础组件源码在 `runtime-ui/src/components/ui`，基于 shadcn/ui `b4C6dEBLto`（Radix / Sera），按项目恢复紧凑间距及字阶。常规控件高 32px、图标操作 24px、表格行最小高度 36px；图表标题 14px、指标卡标题 12px，使用 Inter。主要操作为深海蓝，图表数据色与原 PDF 参考保留。

| 组件族 | 输入与事件 | 状态 | 数据／宿主依赖 | 完成状态 |
| --- | --- | --- | --- | --- |
| Button、IconAction | label、variant、disabled、onClick | 主次、破坏性、禁用、Tooltip、焦点 | Lucide；图标有可访问名称 | 实现、构建、画板与 MCP 应用已接 |
| Input、Field、Checkbox、Select | value、label、checked、onChange | 选择、校验、禁用、焦点 | 父组件状态 | 同上 |
| Popover、Command、Calendar | open、候选项、日期、选择事件 | 搜索、键盘选项、日历选择 | 父组件状态 | 用于筛选器 |
| Badge、ActiveFilters | 状态文案、items、remove | 只读状态、可移除条件 | 父组件状态 | 同上 |
| Tooltip、Dialog、Sheet、Drawer | open、title、description、onOpenChange | 打开、关闭、键盘与焦点管理 | Radix／Vaul | 用于说明和列配置 |
| Alert、Empty、Skeleton、Toast | message、variant、loading | 错误、空结果、加载、成功／信息／警示 | Toast 使用 Sonner | 同上 |

## 应用、保存与导出

纯展示、GridStack、报告、Runtime 状态和宿主能力分别维护于 `component-view.tsx`、`grid.tsx`、`report.tsx`、`runtime.ts`、`main.tsx`／`host.ts`。临时筛选、表格和粒度不隐式保存。项目 `projectRoot` 在适配层固定；按组件加载、请求并发限制、旧响应丢弃和分块完整性检查保留。

| 能力 | 实现与运行约束 |
| --- | --- |
| 预览资源 | 带 uiBuildId 的 UI URI；过期构建需重新打开 |
| 编辑、保存、恢复 | 版本检查、批次提交、完整校验与取消布局草稿 |
| 位置批注 | 元素/区域选取、就地输入、编号、回复、解决；独立保存与冲突检查；附到宿主对话未接入 |
| CSV | 全部匹配行和受管文件分块下载；下载由宿主或浏览器适配 |
| 单图 PNG / 复制 | ECharts Canvas Blob，受浏览器或宿主权限限制 |
| HTML | 当前计算视图与共享组件，移除原始明细和连接信息 |
| 静态网页 | 共享应用、Worker、使用中的完整数据分片和构建标识 |
| 发布资源 | npm 包与原生程序；容器从源码独立构建 |

产品提供 HTML、JSON、CSV、PNG 和静态网页；设计参考 PDF 保留。详细使用见 [静态网页导出](../operations/static-deployment.md)。

## 动态与自由组件能力

内容与渲染校验由 `runtime-core/src/runtime/` 的 `model.rs`、`validation.rs`、`discovery.rs` 和 `contract.rs` 维护；展示入口包括 `metric.tsx`、`component-view.tsx`、`chart.tsx` 和 `custom-surface.tsx`。

普通系列与动态编码的当前注册范围以 `runtime-core/src/runtime/encoding.rs` 为准，不从目录条目总数推断动态能力。

预设可以合法快照显示，但不会自动获得筛选与聚合。mc07–mc10、mc15 在注册 KPI 绑定入口仍为快照。

- 绑定字段、指标和数据集必须匹配；比例按分子合计除以分母合计。
- 时间聚合需要日期合同；跨数据集联动需要明确业务字段关系。
- c01/c02 保留已实现的预设互换；自由组件通过完整声明修改，不复用该切换操作。
- 双轴不是全产品禁用项；已有 t06 与自由 ECharts 均可表达。
- 另有直方图、箱线图、回归三类原生统计图组件，独立于40个交互预设。

1. 自由组件支持本地脚本交互，统一后端数据绑定和跨组件事件桥尚待接通。
2. 任意原始 JSX 的编译、外部扩展自动安装、地图资源自动注册当前未实现；可在 HTML 中提供浏览器可执行代码和所需资源。
3. 自由图形与显式数据表的业务一致性仍由作者维护，保存校验只检查结构，不解释脚本含义。
4. 自由脚本运行失败时，组件显示错误并提供重试。

## 界面数据更新与阅读状态

前端按可见组件 ID 查询并合并结果，最多四个查询并发。筛选只更新绑定的组件；表格搜索、排序、分页和图表粒度切换只更新当前组件。请求按组件记录代次，过期的排队请求不再发送，旧响应不覆盖新选择。无需数据绑定的静态图表直接读取配置，不请求计算视图。

更新时保留现有内容，不在已有卡片内反复显示更新提示；加载状态通过 `aria-busy` 表达。图表尺寸变化和配置变化合并到同一帧处理，尺寸未变且配置未变时不重复绘制；指标卡配置未变时跳过重复渲染。表格自动高度只观察相关表格，统一读取尺寸后再更新布局。切换看板时保留当前页面至新定义返回，再替换内容；进入布局编辑不插入占据页面高度的说明。取消布局编辑会恢复原布局。HTML 快照和静态站点使用同一套 React 组件，导出不依赖浏览器自动化。

图表联动只刷新旧、新条件的关联组件，来源图保留完整类别；再次点击同一来源的同一类别取消选择。图表以稳定系列 ID 和类别名称合并数据，柱状图选中类别保留原色，其余柱子变灰；清除联动条件恢复原色。图形与指标卡主数值使用 260ms 更新过渡，生效条件行展开、收起使用短过渡；系统启用减少动态效果时直接呈现最终数据。

维护时机：组件接口、实现入口、动态能力或宿主接入状态改变时更新；视觉规则维护在 DESIGN.md，操作规则维护在标题区与绑定文档。
