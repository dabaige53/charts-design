# 原生 ECharts 配置覆盖

40 个预设继续负责默认图形、卡片和布局。`config.echarts` 提供一个原生 ECharts JSON 配置入口，适用于 MCP 预览、本机 Runtime、Runtime 的 HTML/PDF 导出和单组件导出。

渲染顺序：预设生成默认 option → 原有数据绑定更新数据 → 合并 `config.echarts` → ECharts 渲染。没有该字段时保持原有行为。

## 使用

读取 `dashboard_get` 后，通过现有 `dashboard_patch` / `put_component` 更新组件的完整配置。保留组件原来的 `code`、`data`、`presentation` 和 `binding`，增加 `config.echarts`。不需要新工具。

例如，在 `c01` 的配置中增加以下内容，可以按数据项着色，并调整标签和坐标轴：

```json
{
  "echarts": {
    "color": ["#123B5D", "#628EA8", "#A17B45"],
    "series": [{
      "colorBy": "data",
      "itemStyle": {"color": null},
      "label": {"show": true, "position": "top", "formatter": "{b}: {c}"}
    }],
    "xAxis": {"axisLabel": {"rotate": 20}},
    "tooltip": {"trigger": "axis"}
  }
}
```

`itemStyle.color: null` 清除预设的固定颜色，让 ECharts 使用调色盘。`colorBy: "data"` 按数据顺序配色；需要筛选前后稳定的分类颜色时，应使用 ECharts 的显式分类映射，例如气泡图的 `visualMap.categories`。

气泡图 `r02` 的数据项为 `[x, y, size, name]`。可以用第四维的名称进行分类着色：

```json
{
  "echarts": {
    "series": [{"itemStyle": {"color": null}}],
    "visualMap": {
      "type": "piecewise",
      "dimension": 3,
      "categories": ["代理 A", "代理 B"],
      "inRange": {"color": ["#123B5D", "#A17B45"]},
      "outOfRange": {"color": "#7B8794"},
      "left": "right",
      "top": "middle"
    }
  }
}
```

这些是常用示例，不是允许字段的白名单。其他原生 JSON 配置，如 `markLine`、`markArea`、`dataZoom`、`brush`、`graphic` 和 `emphasis`，也会传给 ECharts；具体组合是否有效由 ECharts 决定。

## 合并规则与范围

- 对象逐层合并。只提供 `label.show` 不会清除该标签的其他默认配置。
- `series`、坐标轴、图例、绘图区等组件数组，先匹配已有 `id`，没有匹配时按数组位置合并。对象形式表示该组件的第一个元素；空数组清空该组件列表。
- 普通数组（如 `color`、`series.data`）整体替换；显式 `null` 会保留并交给 ECharts。未提供的值继续使用预设。
- 原生配置的额外字段原样保留，不逐项加入 MCP 专用字段，也不因未经单独验证而拒绝。
- 渲染模块使用当前安装的 ECharts 标准完整发行包。额外地图资源、第三方扩展或 ECharts GL 仍需对应资源和注册；配置入口不会自动下载插件。
- 支持 JSON 值和 ECharts 字符串格式模板；保留预设已有的函数。不会把 JavaScript 函数字符串解析为可执行代码。
- 数据绑定、统计计算、点击联动和数据表保持原有约定。依赖这些能力时应保留系列的数据及分类含义。显式覆盖 `series.data`、坐标轴数据或 `dataset` 只影响图表，不会同步改变绑定数据集、统计结果或数据表。

`chart_declarations` 会说明该入口及已验证示例的范围。显示选项透传不表示所有 ECharts 功能组合都经过项目验收。
