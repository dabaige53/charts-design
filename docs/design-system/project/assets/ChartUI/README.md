这里保留的是旧 charts-design 的图表本体参考，与 PDF 中的 McKinsey 数据色盘分开。

- `chart-builders.json`：40 个原图表的原始定义，包括坐标轴、图例、Tooltip、标签、几何和专用标记；`definitions/` 按组件代码拆分。
- `project-chart-palette.json`：旧项目实际使用的颜色，不冒充 McKinsey PDF 官方色盘。
- `original-dashboard-engine.js.txt`：原模板中的渲染实现，包含指标卡主体与微图。
- `original-template-style-1.css.txt`：原模板内样式；Runtime 的图表适配、KPI 几何、自适应和原生 ECharts 覆盖代码在 `source/dashboard_runtime/web/`。
- `source/examples/`：Gallery 与原示例页面，用于恢复视觉比较。
- `preservation.json`：来源 Git 提交、文件路径、40 个图表代码和按视觉职责分类的索引。

源码全部作为 `.txt` 保存，只用于读取和迁移，不被当前应用加载。本次没有在主项目恢复旧生成器、旧 UI 或测试。后续实现按图表逐个迁移视觉与交互，不整体接回旧页面框架。
