# UI 组件清单与接入状态

本文维护组件接口、源码位置、动态能力与接入状态。原图形资料见 [图表参考](design-system/project/chart-ui.md)，阶段安排见 [整改计划](plans/ui-refactor-plan.md)；单次检查结果维护在 records/。

## 六项状态

| 范围 | 规范或参考 | 画板示例 | 组件实现 | 已构建 | 真实 Runtime 数据 | 本项目 MCP |
| --- | --- | --- | --- | --- | --- | --- |
| 筛选、条件、范围与日期 | 已整理 | 筛选器内集中展示 | 官方组件组合 | 已构建 | 工具适配已接 | 协议已验；宿主显示待确认 |
| 图表与操作栏 | 40 种定义及动态编码 | 每种独立；操作栏相邻 | ECharts TypeScript 模块 | 已构建 | 聚合与动态绑定已接 | 协议已验；宿主显示待确认 |
| 指标卡 | 16 种及指标定义 | 每种独立 | MetricCard | 已构建 | 后端主值、比较和趋势 | 协议已验；宿主显示待确认 |
| 标准、交互表格 | 表格与操作区规范 | 两张表格画板 | shadcn/ui + TanStack Table | 已构建 | 后端搜索、排序、分页 | 协议已验；宿主显示待确认 |
| 基础控件与反馈 | 语义变量与官方结构 | 同类与附属状态归组 | 官方源码与业务组合 | 已构建 | 由父组件传入状态 | 随应用使用；宿主显示待确认 |
| 布局与报告容器 | 保留 12/8/4 列与 Markdown 合同 | 原布局示意保留 | GridStack、ReportView | 已构建 | 保存、恢复与版本已接 | 协议已验；宿主交互待确认 |

“真实 Runtime 数据”表示组件的数据入口已连接本项目工具；协议验证使用临时项目和明确标注的合成数据，通过实际 stdio MCP 调用，不读取业务项目。所有 UI 运行效果、剪贴板、全屏及宿主下载尚未在目标宿主确认。

## 筛选与联动

维护入口：`runtime-ui/src/controls.tsx`。应用适配：`dashboard.tsx`、`runtime.ts`。

| 组件与用途 | 输入参数 | 输出事件 | 支持状态 | 数据依赖 | 宿主依赖与状态 |
| --- | --- | --- | --- | --- | --- |
| ChoiceSelect：单选 | label、value、options、disabled | onChange(value) | 选择、展开、禁用、焦点 | Choice 列表 | 无；官方 Select，已构建 |
| MultiSelect：可搜索多选 | options、value、loadOptions | onChange(values) | 搜索、分页加载、全选、清空、数量、错误、禁用 | `dashboard_filter_options` 搜索分页；全选读取全部候选页 | 工具调用由应用传入；已接 MCP |
| RangeFilter：数值区间 | label、value、type | onApply(from,to) | 输入、校验、应用、清空 | `dashboard_view` 的范围条件 | 无；已接 MCP |
| DateRangeFilter：日期范围 | label、value | onApply(from,to) | 日历选取、完整区间、清空 | 日期字段与 ISO 日期条件 | 无；已接 MCP |
| ActiveFilters：条件标签 | items、title | onRemove(id)、onClear() | 单项移除、空条件、清空禁用 | 查看状态与图表联动条件 | 无；已接 MCP |
| FilterBar：全局筛选 | document、filters、call | onChange、onClear | 多维条件、关键词、日期／数值范围、摘要 | 定义、候选项、查看状态 | 由应用适配工具；已构建 |
| 图表点击联动 | 点击点、绑定分类字段、linkGroup | 临时 runtime-linkage 条件 | 再次点击或移除恢复；显式消费者 | 绑定数据集、跨数据集同名字段 | 工具调用；已接 MCP |

## 图表与操作

| 组件 | 输入参数 | 输出事件 | 状态与数据 | 宿主依赖 |
| --- | --- | --- | --- | --- |
| EChartSurface | option、label、className | onReady(chart)、onSelect(point) | 自适应、完整图例和原始 Formatter | ECharts；无 MCP 依赖 |
| ChartToolbar | showTable、grain、操作 callbacks | 图／表、月／季、CSV、图片、复制、全屏、说明 | 不支持的操作禁用并说明原因 | 父组件提供下载、剪贴板和全屏 |
| ComponentView | document、id、grain、tableState | onGrain、onTableChange、onInspect、onExport、onSelect | 加载、空、错误、详情；不调用 MCP | 回调适配 |
| 指标定义与语义 | semantic_inspect 结果 | 打开／关闭 | 指标、公式、单位、来源、实际绑定和计算语义 | 实际工具结果；无预览文案替代 |

各图表保留独立生成逻辑和对应数据表。生产代码读取 `src/charts`；`runtime-ui/fixtures/charts.json` 仅为画板数据。图表 Tooltip 经 DOMPurify 处理。后端统计图保持独立产物，不改用浏览器重算。

| 编码 | 类型 | 实现 | 画板 | 接入 |
| --- | --- | --- | --- | --- |
| c01 | 标准垂直柱状图 | `runtime-ui/src/charts/c01.ts` | `ChartC01.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| c02 | 排序横向条形图 | `runtime-ui/src/charts/c02.ts` | `ChartC02.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| c03 | 分组对比柱状图 | `runtime-ui/src/charts/c03.ts` | `ChartC03.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| c04 | 双向偏离条形图 | `runtime-ui/src/charts/c04.ts` | `ChartC04.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| c05 | 棒棒糖图 | `runtime-ui/src/charts/c05.ts` | `ChartC05.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| c06 | 哑铃跨度图 | `runtime-ui/src/charts/c06.ts` | `ChartC06.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| c07 | 目标重叠达成柱 | `runtime-ui/src/charts/c07.ts` | `ChartC07.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| c08 | 双向对峙蝴蝶图 | `runtime-ui/src/charts/c08.ts` | `ChartC08.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| d01 | 客单价频数直方图 | `runtime-ui/src/charts/d01.ts` | `ChartD01.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| d02 | 多大区合同箱线图 | `runtime-ui/src/charts/d02.ts` | `ChartD02.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| d03 | 工单响应密度曲线 | `runtime-ui/src/charts/d03.ts` | `ChartD03.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| d04 | 24H 全周热力矩阵 | `runtime-ui/src/charts/d04.ts` | `ChartD04.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| f01 | 商业决策转化漏斗 | `runtime-ui/src/charts/f01.ts` | `ChartF01.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| f02 | 资金价值链桑基图 | `runtime-ui/src/charts/f02.ts` | `ChartF02.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| f03 | 客户批次留存 Cohort | `runtime-ui/src/charts/f03.ts` | `ChartF03.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| fn01 | EBITDA 瀑布归因图 | `runtime-ui/src/charts/fn01.ts` | `ChartFN01.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| fn02 | 盈亏平衡剪刀差走势 | `runtime-ui/src/charts/fn02.ts` | `ChartFN02.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| fn03 | 敏感性龙卷风图 | `runtime-ui/src/charts/fn03.ts` | `ChartFN03.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| fn04 | 基准归一指数走势 | `runtime-ui/src/charts/fn04.ts` | `ChartFN04.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| k01 | 中心指标环形图 | `runtime-ui/src/charts/k01.ts` | `ChartK01.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| k02 | 100%堆叠条形图 | `runtime-ui/src/charts/k02.ts` | `ChartK02.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| k03 | 矩形树图 | `runtime-ui/src/charts/k03.ts` | `ChartK03.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| k04 | 帕累托 80/20 诊断图 | `runtime-ui/src/charts/k04.ts` | `ChartK04.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| k05 | 标准实心饼图 | `runtime-ui/src/charts/k05.ts` | `ChartK05.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| k06 | 双层嵌套同心饼图 | `runtime-ui/src/charts/k06.ts` | `ChartK06.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| m01 | 目标考核子弹图 | `runtime-ui/src/charts/m01.ts` | `ChartM01.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| m02 | 不确定性扇形预测图 | `runtime-ui/src/charts/m02.ts` | `ChartM02.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| m03 | 红线阈值监控图 | `runtime-ui/src/charts/m03.ts` | `ChartM03.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| m04 | 半环进度仪表盘 | `runtime-ui/src/charts/m04.ts` | `ChartM04.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| r01 | 战略 BCG 四象限矩阵 | `runtime-ui/src/charts/r01.ts` | `ChartR01.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| r02 | 战略 3D 气泡图 | `runtime-ui/src/charts/r02.ts` | `ChartR02.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| r03 | 多维相关系数热力图 | `runtime-ui/src/charts/r03.ts` | `ChartR03.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| r04 | 业务拓扑网络关系图 | `runtime-ui/src/charts/r04.ts` | `ChartR04.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| r05 | 多维能力雷达图 | `runtime-ui/src/charts/r05.ts` | `ChartR05.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| t01 | 极简单线走势图 | `runtime-ui/src/charts/t01.ts` | `ChartT01.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| t02 | 实测与预测折线图 | `runtime-ui/src/charts/t02.ts` | `ChartT02.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| t03 | 阶梯步阶折线图 | `runtime-ui/src/charts/t03.ts` | `ChartT03.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| t04 | 堆叠面积演进图 | `runtime-ui/src/charts/t04.ts` | `ChartT04.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| t05 | 战略斜率对照图 | `runtime-ui/src/charts/t05.ts` | `ChartT05.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |
| t06 | 双Y轴柱线复合图 | `runtime-ui/src/charts/t06.ts` | `ChartT06.dc.html` | 已构建、数据与 MCP 适配已接；宿主待确认 |

历史 `kind=chart` 的八种声明另由 `historical-chart.ts` 读取兼容；新图表按上述注册编码声明。

## 指标卡

输入：`config` 中明确声明的值、单位、比较值、目标和趋势。输出：只读显示。数据依赖：Runtime 已计算的组件结果；不从标题猜测公式。主值附近合并必要目标、均值和比较信息，避免独立重复副标题行。所有类型已构建、接入数据与 MCP 适配，宿主待确认。

| 编码 | 类型 | 画板 |
| --- | --- | --- |
| mc01 | 基础数值卡 | `Metric01.dc.html` |
| mc02 | 同环比波动卡 | `Metric02.dc.html` |
| mc03 | 微走势迷你面积卡 | `Metric03.dc.html` |
| mc04 | 目标进度条形卡 | `Metric04.dc.html` |
| mc05 | 迷你半环仪表卡 | `Metric05.dc.html` |
| mc06 | 双指标并列卡 | `Metric06.dc.html` |
| mc07 | 排位梯队徽章卡 | `Metric07.dc.html` |
| mc08 | 阈值预警卡 | `Metric08.dc.html` |
| mc09 | 结构分段卡 | `Metric09.dc.html` |
| mc10 | 中位数极差分布卡 | `Metric10.dc.html` |
| mc11 | 环形进度卡 | `Metric11.dc.html` |
| mc12 | 迷你柱趋势卡 | `Metric12.dc.html` |
| mc13 | 子弹目标卡 | `Metric13.dc.html` |
| mc14 | 双期对比卡 | `Metric14.dc.html` |
| mc15 | 指标清单卡 | `Metric15.dc.html` |
| mc16 | 大字主指标卡 | `Metric16.dc.html` |

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

KPI 专用形态的数据校验仍存在历史路径差异。禁止描述的写入与展示规则统一执行，不表示所有历史形态已共用完整校验器。

## 表格

维护入口：`runtime-ui/src/table.tsx`。`Tables.dc.html` 与 `InteractiveTable.dc.html` 分别展示标准表格和交互表格。

| 组件 | 输入参数 | 输出事件 | 支持状态 | 数据与宿主依赖 |
| --- | --- | --- | --- | --- |
| DataTable | config.columns／rows、state、loading、error | onChange、onExport、onSaveState | 搜索、排序、分页、总数、列顺序／显隐、空／错误／加载 | 已分页的 Runtime 行；手动分页和排序，不只处理当前页 |
| TableToolbar | keyword、callbacks | 搜索、列配置／CSV 图标及 Tooltip | 禁用与焦点 | 应用调用 `dashboard_view`、`dataset_export` |
| ColumnSettings | columns、visible、order | onChange、onOrderChange、onReset | 指针拖拽、键盘排序、上移／下移、恢复默认 | dnd-kit；桌面 Sheet、手机 Drawer |
| Pagination | page、pages、pageSize | onChange(page,pageSize) | 首／前／后／末页、每页条数、页数、边界禁用 | 父表由后端总数计算 pages |
| 列配置保存 | 当前列顺序／显隐 | 明确点击保存 | 编辑状态可保存；查看调整为临时状态 | begin → patch → finish、revision 检查 |

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

| 能力 | 实现与数据状态 | 验证边界 |
| --- | --- | --- |
| 预览资源 | 带 uiBuildId 的 `ui://` 资源，后端可读取 | 实际 stdio MCP 已通过；目标宿主未打开确认 |
| 编辑／检查点／恢复 | 版本检查、项目编辑批次、取消布局草稿 | 后端协议已通过；拖拽和缩放未做 UI 验证 |
| 位置批注 | `position-comments.tsx`：元素／区域选取、就地输入、编号、回复、解决与重新标记；项目批注独立保存并检查冲突；操作图标、正文与回复区分层 | 已接 MCP 工具、构建打包并通过源码诊断；未运行 UI 测试或浏览器自动化；宿主附到对话未接入 |
| CSV | 全部匹配行；受管文件分块下载 | 实际工具已通过；宿主下载待确认 |
| 单图 PNG／复制 | ECharts Canvas Blob；浏览器或宿主适配 | 已构建；目标宿主权限与操作待确认 |
| HTML 快照 | 当前计算视图、共享组件，移除原始明细与连接 | 导出与资源检查通过；未渲染验收 |
| 独立静态网页 | 共享应用／Worker、使用中数据集分片与构建标识 | ZIP 内容与数据范围检查通过；未部署 |
| 发布资源 | npm、Python 包包含编译资源；容器独立构建阶段 | 本地包内容检查；Docker 镜像未构建 |

PDF 产品导出已取消，设计参考 PDF 保留。详细使用见 [静态网页导出](static-deployment.md)。




## 动态与自由组件能力

内容与渲染校验由工作区 `component_schemas.py`、Runtime 的 `model.py`、`legacy.py`、`declarations.py` 和 `contract.py` 维护；展示入口包括 `metric.tsx`、`component-view.tsx`、`chart.tsx` 和 `custom-surface.tsx`。

普通系列与动态编码的当前注册范围以 `dashboard_runtime/bindings.py` 为准，不从目录条目总数推断动态能力。

预设可以合法快照显示，但不会自动获得筛选与聚合。mc07–mc10、mc15 在注册 KPI 绑定入口仍为快照。

- 绑定字段、指标和数据集必须匹配；比例按分子合计除以分母合计。
- 时间聚合需要日期合同；跨数据集联动需要明确业务字段关系。
- c01/c02 保留已实现的预设互换；自由组件通过完整声明修改，不复用该切换操作。
- 双轴不是全产品禁用项；已有 t06 与自由 ECharts 均可表达。
- 另有直方图、箱线图、回归三类 Seaborn 静态组件，独立于40个交互预设。

1. 自由组件支持本地脚本交互，统一后端数据绑定和跨组件事件桥尚待接通。
2. 任意原始 JSX 的编译、外部扩展自动安装、地图资源自动注册当前未实现；可在 HTML 中提供浏览器可执行代码和所需资源。
3. 自由图形与显式数据表的业务一致性仍由作者维护，保存校验只检查结构，不解释脚本含义。
4. 自由脚本运行失败时，组件显示错误并提供重试。
5. 旧参考文件仍保留历史信息。当前 skill 明确规定其不能覆盖新产品规则；后续修改这些文件时应按现行要求更新。

## 界面数据更新与阅读状态

前端按可见组件 ID 查询并合并结果，最多四个查询并发。筛选只更新绑定的组件；表格搜索、排序、分页和图表粒度切换只更新当前组件。请求按组件记录代次，过期的排队请求不再发送，旧响应不覆盖新选择。无需数据绑定的静态图表直接读取配置，不请求计算视图。

更新时保留现有内容，不在已有卡片内反复显示更新提示；加载状态通过 `aria-busy` 表达。图表尺寸变化和配置变化合并到同一帧处理，尺寸未变且配置未变时不重复绘制；指标卡配置未变时跳过重复渲染。表格自动高度只观察相关表格，统一读取尺寸后再更新布局。切换看板时保留当前页面至新定义返回，再替换内容；进入布局编辑不插入占据页面高度的说明。取消布局编辑会恢复原布局。HTML 快照和静态站点使用同一套 React 组件，导出不依赖浏览器自动化。

图表联动只刷新旧、新条件的关联组件，来源图保留完整类别；再次点击同一来源的同一类别取消选择。图表以稳定系列 ID 和类别名称合并数据，柱状图选中类别保留原色，其余柱子变灰；清除联动条件恢复原色。图形与指标卡主数值使用 260ms 更新过渡，生效条件行展开、收起使用短过渡；系统启用减少动态效果时直接呈现最终数据。

维护时机：组件接口、实现入口、动态能力或宿主接入状态改变时更新；视觉规则维护在 DESIGN.md，操作规则维护在标题区与绑定文档。
