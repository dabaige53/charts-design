# 产品 React 组件

产品操作组件基于 shadcn/ui 预设 `b4C6dEBLto` 的 `radix-sera` 结构，采用 Stone 中性色、Lucide 和项目紧凑尺寸。组件结构和样式维护在 `runtime-ui/src`。主要操作使用深海蓝 `#123B5D`，焦点使用 `#2C6485`；图表保留原数据色。

## 实现与预览

| 设计系统组件 | 实际导出 | 维护文件 |
| --- | --- | --- |
| Buttons、Cards | Button、Card 及其结构部件 | `runtime-ui/src/components/ui` |
| Select | ChoiceSelect | `runtime-ui/src/controls.tsx` |
| MultiSelect | MultiSelect | `runtime-ui/src/controls.tsx` |
| DatePicker | DateRangeFilter | `runtime-ui/src/controls.tsx` |
| TextInputs、Checkboxes | Input、Checkbox、Field | `runtime-ui/src/components/ui` |
| Tags、Badges | ActiveFilters、StatusBadge | `runtime-ui/src/controls.tsx` |
| Tooltips、Modals | IconAction、ExplanationDialog | `runtime-ui/src/controls.tsx` |
| DataTables、Pagination | DataTable、Pagination | `runtime-ui/src/table.tsx`、`controls.tsx` |
| Alerts | Alert、Toast／Sonner | `runtime-ui/src/components/ui/alert.tsx`、`controls.tsx` |
| 图表、指标卡 | EChartSurface、MetricCard | `runtime-ui/src/chart.tsx`、`metric.tsx` |

可运行预览中的数据来自设计适配入口，仅用于展示。生产入口 `main.tsx` 不导入这些示例。图表和指标卡逐张展示在现有设计画布中；筛选器、表格的附属操作放在各自画板内。

组件 props、事件、数据和宿主依赖见 [组件清单](../../ui-component-inventory.md)。完整的 React 类型由 `runtime-ui/dist/types` 构建生成。

## 语义变量

运行变量的维护入口是 `runtime-ui/src/styles.css`。本系统 `tokens.json` 中的 `ui-*` 是对应的设计映射；`color-data-*` 及 ChartUI 项目色不作为交互状态色。

| Tailwind / shadcn 变量 | 设计 token |
| --- | --- |
| background、card、popover | ui-background |
| canvas | ui-canvas |
| foreground、popover-foreground | ui-foreground |
| primary、primary-foreground | ui-primary、ui-primary-foreground |
| secondary、muted | ui-muted |
| muted-foreground | ui-muted-foreground |
| accent | ui-accent |
| border、input、ring | ui-border、ui-input、ui-ring |
| destructive | ui-destructive |
| 预设基础圆角 | ui-radius；各组件是否使用圆角由 Sera 默认样式决定 |

使用 shadcn variants 和语义变量。组件边距及字阶在共享组件源码中统一调整，保留 Sera 的边框、焦点和交互结构。图表编码继续使用保留的数据色；报告采用单栏阅读排版。

## 紧凑尺寸与组合

Button 的 default、sm、xs、lg 高度为 32、28、24、40px；图表操作使用 24px 的 icon-xs。Input、InputGroup 和默认 Select 高 32px，采用一致的完整边框。Table 正文 12px，表头与内容行最小高度 36px；内容行上下内边距 8px。ToggleGroup 使用紧凑 sm 变体。

卡片使用 CardHeader、CardTitle、CardDescription、CardAction、CardContent。水平内边距 16px，上方 12px、下方 16px；普通卡片标题区与内容区间隔 12px，指标卡使用 size="sm" 和 8px 间隔。图表和指标卡标题基准为 16px、最小 14px，均使用 Inter；描述在 12–16px 之间调整。实际标题和留白随容器宽高调整。图表工具栏位于标题右侧；表格总数、每页条数和分页在底部排列，窄屏换行。保留画板位置、尺寸和已保存的看板网格。

Inter Variable 和 Lora Variable 随组件资源提供；卡片标题使用 Inter，其他标题可使用 Lora。MCP 应用将字体打入 CSS；设计系统通过 `type.fonts` 加载本地字体文件，不依赖外部字体服务。原 PDF 的字体、尺寸与来源资产仍作为历史参考。

## 构建与交付

在项目根目录运行：

```sh
node runtime-ui/scripts/build.mjs
pnpm --dir runtime-ui exec tsc -p tsconfig.build.json --noCheck
pnpm --dir runtime-ui package:runtime
pnpm --dir runtime-ui package:design
```

构建只写 `runtime-ui/dist`。`ui:package` 将应用资源复制到后端发布目录；`ui:package:design` 将同一组件实现的设计 bundle 复制到本系统。画板资源通过 claude-design 的资源更新步骤单独维护，修改前读取当前文件并保留用户编辑。

本次按用户要求直接调整紧凑尺寸与操作色，仅生成和同步交付资源，不运行验证、检查或测试。


## 筛选与图标操作

筛选栏默认展示前三个非文本条件；应用可通过 `DashboardApp.primaryFilterIds` 指定常用条件及顺序，其余条件集中到“更多筛选”。多选使用 Popover / Command，可搜索、全选、清空并分页读取候选项；日期范围使用 Popover / Calendar，并提供近 7 天、近 30 天、本月、上月和本年快捷范围。文本搜索使用 InputGroup，数值范围在 Popover 内使用 Field / Input；所有条件沿用 MCP 声明的字段及 in、range、contains 操作。已生效条件支持单项移除与重置，无条件时不渲染条件标签行。

`selectionMode=single` 的条件复用可搜索候选列表，每次只保留一项；没有该标记时仍为多选。页头“看板备注”支持关联整个看板或指定组件，位置框选与对话附件不在此入口内。

筛选区下方集中显示当前范围、适用的图表粒度与快照数据更新时间。日期未限制时明确显示“全部日期”。仅当快照标记为 fixture 时显示“示例数据”；不从标题猜测时间范围。说明弹窗使用该组件实际接收的查看条件，不用已保存条件替代临时筛选。

编辑布局、保存、取消、自定义列和 CSV 导出统一使用 IconAction；图标保留 Tooltip、aria-label、禁用原因和键盘焦点。表格操作图标为 32px，页头操作为 24px。

## 容器缩放

KPI 使用 ResizeObserver 读取可用宽高及内容自然高度，统一调整文字、间距和微图尺寸，内容按实际宽度换行，不再对整组文字做 transform 缩放。常规主值至少 28px、双指标主值至少 24px、大字主值至少 32px；辅助说明至少 12px。微图与进度条随可用空间调整，内容顶部对齐，无内部滚动。清单卡没有主值时不显示占位横线。图表在容器尺寸改变时重新计算文字、图例、标记和绘图区留白；分类、数值、单位和数据绑定不变。标题及卡片留白也随卡片宽高调整，现有网格和画板坐标不变。

页面底色为 Stone 淡灰 `#F5F5F4`；筛选栏使用白色 card 表面与细边框，输入和轮廓按钮使用白色 background 表面。筛选项作为完整控件换行，不拆散标签与选值。

## 操作分组、说明与恢复

图表操作按“查看方式”“导出与复制”“全屏与说明”分组，所有入口直接可见。图表和表格卡片宽度不超过 640px 时，工具区整行排在标题和描述之后；组内控件保持相邻。表内搜索、列配置和导出与信息入口处于同一操作区。

`SemanticDetails` 按概览、当前统计范围、坐标与序列、指标计算、字段及来源组织内容。绑定指标以 Runtime 声明为准；只有已明确的聚合方式才转换成中文公式，不补写业务定义或阈值。原始配置放在末尾的展开区。字段单位可取自字段字典或同数据集对应字段的指标声明。

`RecoveryAlert` 显示受影响内容与恢复动作，技术异常放在展开区。单个组件的数据失败只影响该组件，可独立重新加载；说明请求可单独重试。页面有已加载数据时保留当前看板，编辑中的错误可返回编辑，不自动提交、取消或覆盖草稿。

本次按 critique 的五项建议修改实现，仅生成和打包资源；未运行类型检查、LSP、UI 测试、浏览器自动化或截图验收。
