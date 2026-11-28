# 原生统计图

Rust 运行时将原始观测渲染为 SVG 或 PNG，用于看板、报告和独立导出。`chart_declarations` 和 `charts://declarations` 提供统计组件结构；不需要额外语言运行时。

## 声明与交付

先登记来源与带类型的数据集，再通过 `dashboard_submit` 添加组件：

```json
{"op":"put_component","id":"distribution","value":{
  "kind":"statistical","title":"响应时间分布","datasetId":"observations",
  "plot":{"type":"histogram","x":"value","bins":20},
  "analysis":{"definition":"每行表示一次请求，value 为该次请求的响应时间。","unit":"ms"}
}}
```

| 图形 | plot | 输入 |
| --- | --- | --- |
| 直方图 | `{"type":"histogram","x":"value","bins":20}` | 数值字段与 1–100 个等宽区间 |
| 箱线图 | `{"type":"boxplot","x":"group","y":"value"}` | 类别和数值；1.5 倍 IQR 须与离群点 |
| 回归图 | `{"type":"regression","x":"elapsed","y":"value"}` | 两个数值字段、散点与 OLS 直线 |

`analysis.definition` 描述观测粒度和度量含义；`analysis.unit` 标注直方图 x 轴或箱线图/回归图 y 轴。回归图 x 轴单位放在数据字段标签中。不能用聚合后的指标冒充原始观测。

报告使用普通 `chart` 围栏嵌入组件，图注作为图题。`statistical_render` 的 `format` 可选 `svg` 或 `png`，返回 data URI、图注及来源元信息。正式文档只保存声明和数据，产物按完整数据与配置派生；改变数据后重新计算。来源元信息是提供的依据，不代表业务认证。

## 限制

- 每图最多 5,000 行原始观测，每文档最多 10 个统计组件。
- 箱线图最多 20 组；回归至少 3 个完整观测、至少 2 个不同 x 值。
- 缺失和 null 观测被排除并明确计数；其他非法类型会拒绝。
- 数值绝对值不超过 1e12，类别标签不超过 100 字符。
- 不提供 KDE、置信区间、自动假设检验或因果结论。
- 不接受文件路径、URL、可执行代码和任意选项；统计组件不作为交互筛选目标。
- SVG 使用字体路径。部署时安装适合文本的字体，中文建议 Noto Serif CJK，拉丁文本可用 DejaVu Sans。

交互图表使用预设、ECharts 或 HTML/JavaScript，见[渲染入口](echarts-options.md)。
