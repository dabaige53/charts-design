产品组件的实现、语义变量和可运行预览见 [产品 React 组件](react-ui.md)。图表本体按 [图表 UI 保留说明](chart-ui.md) 迁移；`assets/ChartUI/` 和下方 PDF 摘录继续作为来源参考。

## 来源规范摘录

以下为原 PDF 的参考规则；产品操作组件的实际尺寸和结构以 [产品 React 组件](react-ui.md) 为准。

McKinsey MDS 以清晰层级、精确结构与稳定节奏组织界面。用克制的基础色承载内容，用 Electric Blue 标识操作与当前位置，把数据色留给数据表达。

## 内容与层级

- 为按钮写直接的动作名称，例如原规范的 “Cancel”“Submit”“Save”；主要动作通常放在按钮组右侧。
- 每页尽可能只保留一个 Primary 操作。取消、返回与编辑使用较低优先级。
- 卡片标题用 1–3 行，建议 2 行；正文用 2–5 行，建议 3–4 行。模态文案简洁、客观，聚焦一个任务。
- Placeholder 不替代 Label。Inline Link 保留默认下划线，状态用文字辨别。

## 颜色

- 使用 `color-brand-deep-blue`（#051C2C）承载品牌深色背景，使用 `color-white` 反白。
- 使用 `color-brand-electric-blue`（#2251FF）标识焦点、激活项与主要交互。`color-brand-cyan`（#00A9F4）用于辅助强调和深色表头交互。
- 数据图形使用 `color-data-*`。这些是功能色盘，不自动等同于成功、失败等业务语义。浅色不直接用作白底小号文字。
- 白底正文使用 `color-gray-80`；次正文可使用 `color-gray-54`。`color-gray-30`、`color-gray-18`、`color-gray-10` 用于不同分隔与表面层级。
- 浅色按钮规范另有 `color-button-action`（#1F40E6）。保持它与品牌 Electric Blue 的差别，按组件依据选择。

## 字体与字阶

- Display 使用 Bower Bold，Heading 使用 McKinsey Sans Medium；Article Lead / Body 使用 McKinsey Sans Light，其他正文使用 Regular。
- 桌面使用 `desktop-display-*`、`desktop-heading-*`、`desktop-body-*`；移动端使用相应 `mobile-*` 样式。字号和行高以明确的 px 数值为准。
- 常规正文使用 `desktop-body-default` / `mobile-body-default`：16px / 24px；小号正文为 14px / 20px。
- `sans` 与 `display` 声明原字体名称。可重用字体文件未随来源提供；网页字体样张会分别回退到 Arial / 系统字体及 Georgia / 宋体。原始画板保留字体的实际样貌。

## 间距、布局与表面

- 使用 4px 基础；标准档位为 `space-4`、`space-8`、`space-12`、`space-16`、`space-24`、`space-32`、`space-48`、`space-64`、`space-96`。
- 按文本框边缘测量间距，先设置正确行高，不按文字基线估算。
- 普通页面处于 `elevation-0`；卡片默认 `elevation-2`；Tooltip 与 Popover 用 `elevation-4`；卡片 Hover 与导航浮层用 `elevation-8`；Modal / Drawer / Picker 用 `elevation-16`。
- 分隔线使用 `border-width`（1px）。分别以 `color-gray-10`、`color-gray-30`、`color-black` 表示浅、中、深分隔。
- 原规范没有给出全局圆角、动效或统一响应式断点；不要从画板外观推成全局 Token。

## 组件规则

- 输入框与按钮高度成组使用 `control-height-small`（32px）、`control-height-default`（40px）、`control-height-large`（48px）。按钮间距使用 `button-group-gap`（12px），Fluid 宽度不超过 `button-fluid-max`（575px）。
- 表格至少三列；表头与内容使用 `table-row-height`（48px）。金额、日期右对齐。批量操作提供 Checkbox。
- 少量多选用 Tags，大量多选用 Checkbox 与计数；选取过程中保持候选菜单展开。
- Breadcrumbs 显示 2–5 层；Tabs 用于 3–8 个区段；Pagination 超过 10 页使用省略范围，并保留首尾页。
- Global Alert 位于 Header 之上；Contextual Alert 对应局部动作。Modal 的上下内边距使用 `modal-block-padding`（40px）。
- 组件页提供各组件的使用规则与原始画板静态参考。参考图用于核对外观，不是已实现的行为组件。

## 标志与图标

- Script Mark 使用 `assets/ScriptMarks/` 中的来源裁图作参考。默认深蓝版，不能彩色输出时用黑版；白版置于 Deep Blue 上。不要用普通字体重排标志。
- 来源包含图标用法和尺寸，但未提供独立矢量图标库。原图标保留在画板中；产品图标统一使用 Lucide。

## 可读性

- 白底上的 Cyan、浅色功能色和浅灰线不是通用正文色；文字、图形标记和分隔线应按用途检查。
- 深色按钮的原始 Tertiary #7F7F7F 在 Deep Blue 上约 4.33:1，低于同页 4.5:1 目标。保留来源值，采用时需明确处理。
- 原始 Default Control 边框 #B3B3B3 在白底上低于 3:1；不要只靠它表达焦点或错误。Focus 使用 Electric Blue，并同时保留状态文字。

## 使用真实组件

`components/bundle.js` 提供 `window.McKinseyMDS`，`components/bundle.css` 提供配套样式。预览加载 React 与 ReactDOM 后挂载实际组件；组件导出对应关系、参数及业务事件见 [产品 React 组件](react-ui.md) 与 `components/index.d.ts`。

在本项目 Design 画布中安装本系统，复制这两个文件至 `docs/design-canvas/project/ds/mckinseymds/components/`，使用相对路径加载。40 种图表和 16 种指标卡已在项目的独立画板中挂载。原版 PDF、图片和仍为静态资料的组件卡继续作为来源参考。
