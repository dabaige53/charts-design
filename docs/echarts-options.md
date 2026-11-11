# 原生 ECharts 与自由组件

40 个图表是预设，不是可生成图形的上限。图表有三条入口，均通过 `put_component` 保存为 `kind: "legacy"`、`family: "chart"`，复用标题、布局和详情外壳：

| renderer | 内容 | 代码要求 |
| --- | --- | --- |
| `preset`（默认） | 预设 `data`、`presentation`，可加 `echarts` 覆盖 | 已注册代码 |
| `echarts` | 完整原生 `echarts` option，不套预设几何和自适应改写 | 任意非空业务代码 |
| `html` | 完整 HTML/CSS/JavaScript，可包含 SVG、Canvas 或浏览器可执行的 React bundle | 任意非空业务代码 |

未注册代码不能省略渲染方式。保存时会明确提示选择 `echarts` 或 `html`，避免保存成功却由前端报“未注册图表”。这不是禁止库外图表。

原生 ECharts 组件支持共享图片导出和复制。两种自由组件均可提供 `config.table: {headers: string[], rows: array[]}`，用于共享图／表切换和 CSV；未提供时不显示这些操作。HTML 自由组件不显示依赖宿主 ECharts 实例的图片导出和复制。

自由组件当前使用显式数据快照，不接预设 `binding`、`datasetId` 或 `measures`。代码会拒绝这些不受支持的组合；不会把不能重算的图伪装成全局筛选消费者。自由脚本可自行实现组件内选择、动画、切换等交互。全局筛选与后端聚合仍通过已实现的绑定路径工作。

### 自由 ECharts 声明

以下为明确的合成示例；无需借用 c01 等预设代码：

```json
{
  "kind": "legacy",
  "family": "chart",
  "title": "示例阶段贡献",
  "config": {
    "code": "stage-contribution",
    "renderer": "echarts",
    "echarts": {
      "tooltip": {"trigger": "item"},
      "series": [{"type": "funnel", "data": [
        {"name": "阶段 A", "value": 100},
        {"name": "阶段 B", "value": 65}
      ]}]
    },
    "table": {"headers": ["阶段", "示例值"], "rows": [["阶段 A", 100], ["阶段 B", 65]]}
  }
}
```

### 自由脚本声明

```json
{
  "kind": "legacy",
  "family": "chart",
  "title": "示例交互",
  "config": {
    "code": "custom-interaction",
    "renderer": "html",
    "data": {"values": [12, 18]},
    "html": "<button id=\"next\">切换示例值</button><output id=\"value\"></output><script>let i=0;const output=document.getElementById('value');const draw=()=>output.textContent=window.chartData.values[i];document.getElementById('next').onclick=()=>{i=(i+1)%2;draw()};draw();</script>"
  }
}
```

脚本在独立 iframe 中执行，读取 `window.chartData`。允许内联脚本与样式、HTTPS 脚本／模块／字体／图片及请求，可加载自己需要的库和浏览器可执行的 React。原始 JSX 不会自动编译。内联代码和资源应由组件作者明确提供，不在主应用中使用 `eval`。

iframe 只开放 `allow-scripts`，不开放同源、宿主 DOM、弹窗、表单或顶层导航。资源策略不允许嵌套页面和 HTTP／本机资源。脚本错误会显示在组件内，并提供重新运行入口。宿主额外 CSP、网络及资源的跨域许可仍可能影响外部库；需要离线交付时应内联代码与所需资源。

## 预设原生覆盖

`config.echarts` 也可继续覆盖已注册预设，适用于共享 React Runtime 的预览和 HTML／静态网页导出。PDF 导出已取消。

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
- 渲染模块使用当前安装的 ECharts 标准完整发行包。额外地图资源、第三方扩展或 ECharts GL 仍需对应资源和注册；配置入口不会自动下载插件。
- 支持 JSON 值和 ECharts 字符串格式模板；保留预设已有的函数。不会把 JavaScript 函数字符串解析为可执行代码。
- 数据绑定、统计计算、点击联动和数据表保持原有约定。依赖这些能力时应保留系列的数据及分类含义。显式覆盖 `series.data`、坐标轴数据或 `dataset` 只影响图表，不会同步改变绑定数据集、统计结果或数据表。
