# McKinsey-Grade Executive Charts & Dashboard Suite (麦肯锡风格图表设计与高管决策看板套件)

Enterprise-grade, McKinsey/Bloomberg/FT-caliber business charts, KPI decision cards, interactive pivot tables, and responsive executive dashboards built with Tailwind CSS and Apache ECharts 5.5.

本项目提供了一整套麦肯锡/彭博/FT 级别的企业高管经营分析图表、决策指标卡、交互式数据透视表及多维全局筛选器，并配有完整的 CLI 自动化生成引擎与 Antigravity / Stitch 技能库规范。

---

## 当前版本：1.2.0（runtime 0.6.0）

翻页、筛选、编辑和刷新复用图表实例，MCP 支持局部数据响应。图表数据表超过 100 行时按滚动位置渲染；说明图标弹窗的数据区每页最多 20 行，完整 CSV 导出不变。密集图表缩放、筛选全选与取消全选、版本检查继续保留。见 [运行时与刷新说明](docs/dashboard-runtime.md)。更新源码后执行 `npm --prefix runtime-ui ci && npm --prefix runtime-ui run build`，重新连接 MCP 后打开最新预览。用户数据目录可以继续使用。

## 两条 Skills 与 MCP 生成路径

- **Dashboard**：保留 [executive-charts Skill](skills/executive-charts/SKILL.md) 和原有案例；MCP 案例 `charts://examples/executive-dashboard`。
- **分析报告**：[analytical-reports Skill](skills/analytical-reports/SKILL.md)，以认可的学术单栏版式为母稿；MCP 案例 `charts://examples/academic-report`。

MCP 可从空白文档声明数据、指标和图表，再写入包含嵌入图表的 Markdown 并渲染。调用 `generation_examples` 发现案例，`chart_declarations` 阅读声明合同，然后 create → patch → validate → preview。案例数据均为合成数据，调用方必须用真实输入重写分析，不是仅导出一个母稿页面。见 [完整生成流程](docs/generation-tracks.md)。

## 本地个人分析报告 + Dashboard

Runtime 提供两种可切换的呈现方式：Dashboard 保留响应式网格，分析报告是一整篇 Markdown 文档，以学术论文式单栏版面阅读。像写文档一样写标题、段落、加粗、列表和引用，在需要图表的位置插入 chart 代码块，图表就会在文字之间渲染。两种模式共享组件、数据、指标口径和版本记录，不需要部署企业平台。

```bash
npm --prefix runtime-ui install
npm --prefix runtime-ui run build
# 空白报告，不自动填入案例数据
python3 -m dashboard_runtime --root ./boards init analysis --mode report --title "我的分析报告"
# 可选：明确标记的合成数据示例
python3 -m dashboard_runtime --root ./boards init report-demo --mode report --demo
python3 -m dashboard_runtime --root ./boards serve --port 8765
```

打开 `serve` 打印的本地链接，编辑 Markdown 源文并预览。图表引用写成：

````markdown
# 我的分析报告

*副标题由作者填写*

**摘要：** 说明分析范围、主要观察与限制。

**关键词：** 收入；描述性分析

## 我的观察

先写**分析与依据**，正文用[图](#fig-trend)引用下方图表。

```chart
{"componentId":"trend","caption":"月度收入变化","source":"数据来源：作者提供并核对的收入快照。"}
```

图表后继续写解读、限制和下一步。
````

源文保存在 `manifest.report.markdown`，CLI/MCP 使用 `set_report_markdown` 更新。图表 ID 必须指向已有的非文字组件；`caption`（最多 500 字符）和 `source`（最多 1,000 字符）是可选纯文字字符串，仅含 `componentId` 的旧代码块仍有效。图号按源文顺序生成，`[图](#fig-trend)` 自动显示对应图号并跳转；同一组件出现多次时，引用指向第一次出现的位置。二级章节标题自动编号，源文不必手写编号；作者、摘要、关键词及来源须由作者提供，不自动补写。保存时校验引用和 JSON，拒绝未知字段与重复键，普通代码块不会执行。分析文字由作者维护，筛选图表后需要复核文字结论。支持 JSON 保存/恢复及离线 HTML 导出，旧版段落块报告仍可读取。完整合同、CLI/MCP 源文工作流和使用边界见 [Runtime 文档](docs/dashboard-runtime.md)。

## 推荐：积木式构建 Dashboard

CLI workspace 将筛选器、KPI、图表和表格拆成独立小文件。Agent 可以逐块添加、检查和验证，只在 `build` 阶段于内存中合并完整配置。

```bash
# 演示数据仅用于验证工具；业务交付时换成已确认的数据
CHARTS_DEMO="skills/executive-charts/references/quickstart"
python3 skills/executive-charts/scripts/dashboard_workspace.py init ./sales-board \
  --title "销售经营看板（示例）" --org "经营分析部"
python3 skills/executive-charts/scripts/dashboard_workspace.py add kpi ./sales-board revenue \
  --from "$CHARTS_DEMO/revenue.kpi.json"
python3 skills/executive-charts/scripts/dashboard_workspace.py add chart ./sales-board regional-sales \
  --from "$CHARTS_DEMO/regional-sales.chart.json"
python3 skills/executive-charts/scripts/dashboard_workspace.py table set ./sales-board \
  --from "$CHARTS_DEMO/sales.table.json"
python3 skills/executive-charts/scripts/dashboard_workspace.py add filter ./sales-board region \
  --label "区域" --type multi-select --option 华东=华东 --option 华南=华南 \
  --field region --consumer revenue --consumer regional-sales
python3 skills/executive-charts/scripts/dashboard_workspace.py inspect ./sales-board --json
python3 skills/executive-charts/scripts/dashboard_workspace.py validate ./sales-board --strict --json
python3 skills/executive-charts/scripts/dashboard_workspace.py build ./sales-board --output ./dist/sales.html
```

脚本随 Skill 一起提供，直接由本机 `python3` 运行，无需安装 npm 包。完整命令与组件 schema 见 [`skills/executive-charts/references/dashboard-workspace.md`](skills/executive-charts/references/dashboard-workspace.md)。

## 人工视觉展示 (Human Showcase)

`examples/` 用于人工浏览视觉效果，不是 Agent 的配置模板或源码输入。生成新看板时优先使用 CLI workspace 与图表目录元数据。

| 看板文件 | 业务场景分类 | 核心图表与分析重点 |
| :--- | :--- | :--- |
| [**`examples/executive_report.html`**](examples/executive_report.html) | **# 核心研判** | 航线网络与机队效能穿透、RASK/PLF 联动、14 列表格、全局多维筛选 |
| [**`examples/sample_executive_monthly.html`**](examples/sample_executive_monthly.html) | **# 经营月度** | 总裁级经营月度早报、时序营收走势、预算达成率子弹图、客座率散点跨度 |
| [**`examples/sample_financial_attribution.html`**](examples/sample_financial_attribution.html) | **# 财务归因** | EBITDA 毛利归因瀑布图、收支剪刀差盈亏线、成本敏感度多因子分析 |
| [**`examples/sample_saas_product_analytics.html`**](examples/sample_saas_product_analytics.html) | **# SaaS 产品** | 订阅漏斗全链路转化、MRR 留存热力图、NDR / LTV 单元经济学透视 |
| [**`examples/sample_strategic_matrix_portfolio.html`**](examples/sample_strategic_matrix_portfolio.html) | **# 战略矩阵** | BCG 增长-份额战略四象限、资产组合气泡阵列、多维能力雷达对标 |
| [**`examples/gallery.html`**](examples/gallery.html) | **# 全谱系画廊** | 已注册图表的全要素样式墙与交互示例 |

---

## 本地脚本使用 (Local Scripts)

Skill 内置生成脚本，使用本机 Python 直接运行。真实业务看板优先使用上面的 workspace 流程；`generate_dashboard.py` 仅保留整页 preset/config 兼容入口。

```bash
git clone https://github.com/dabaige53/charts-design.git
cd charts-design

# 生成看板
python3 skills/executive-charts/scripts/generate_dashboard.py \
    --preset executive_report --output ./examples/report.html --open

# 生成单图表
python3 skills/executive-charts/scripts/generate_chart.py --code t06 --output ./chart_t06.html
```

### 脚本速查

| 脚本 / 子命令 | 说明 | 示例 |
| :--- | :--- | :--- |
| `dashboard_workspace.py init/add/inspect/validate/build` | 分步组装并严格编译 dashboard workspace | `python3 skills/executive-charts/scripts/dashboard_workspace.py init ./board` |
| `generate_dashboard.py` | 兼容生成整页 preset/config 看板 | `python3 skills/executive-charts/scripts/generate_dashboard.py --preset executive_monthly -o report.html` |
| `generate_chart.py --code` | 生成独立图表组件（带 5+1 工具栏） | `python3 skills/executive-charts/scripts/generate_chart.py --code t06 -o chart.html` |
| `generate_chart.py --list` | 终端打印全部已注册图表编号与分类 | `python3 skills/executive-charts/scripts/generate_chart.py --list` |

---

## 核心亮点 (Key Features)

- **40 款已注册咨询级图表**：涵盖对比、趋势、构成、分布、关系、转化、财务归因、监控 8 大核心分析意图。
- **图表卡片标配 5+1 交互工具栏**：
  - 时间粒度切换（月度 <-> 季度平滑过渡）
  - 图表 / 数据透视表一键互转（可视化与二维数据表无缝切换）
  - 一键导出 CSV（带 UTF-8 BOM 防 Excel 乱码）
  - 复制 2x 高清 PNG（直接粘贴入 PPT）
  - 全屏沉浸研判（自适应高度，按 ESC 退出）
  - 业务口径说明 `(i)`（原生 `<dialog>` 弹窗展示定义、计算公式与判定规则）
- **交互式数据透视表**：
  - 自定义列配置抽屉（列显隐勾选 + HTML5 原生拖拽重排 Drag & Drop + 一键恢复默认）
  - 智能多列类型感知排序（自动识别货币、百分比、增速正负值与评级）
  - 严格单行横向滑动（`whitespace-nowrap` + `overflow-x-auto`，单元格点击一键复制数值）
- **零碰撞几何视觉法则**：深海蓝 `#123B5D` 商务调色盘、25% 天空留白保护、双 Y 轴图例居中、穿透式 Tooltip。
- **开箱即用 CLI 引擎**：支持通过命令行一键自由组合生成高管看板或提取单图表 ECharts Option 代码片段。

---


## 项目结构 (Project Architecture)

```
charts-design/
├── bin/                                # 可选 Node.js 兼容薄壳
│   └── cli.js                         # 委派至 Skill 内置 Python 脚本
├── skills/                             # 技能库 (包含核心 executive-charts)
│   └── executive-charts/               # 麦肯锡高管商业图表技能包
│       ├── SKILL.md                    # 技能标准与强制遵循规范
│       ├── scripts/                    # 看板与图表生成 CLI (generate_dashboard.py, generate_chart.py)
│       ├── references/                 # 设计系统 Token、数据规范与图表 Option 库
│       └── examples/                   # 核心看板与画廊案例
├── examples/                           # 6 大高管看板与画廊独立演示入口
│   ├── executive_report.html           # # 核心研判
│   ├── sample_executive_monthly.html   # # 经营月度
│   ├── sample_financial_attribution.html # # 财务归因
│   ├── sample_saas_product_analytics.html # # SaaS 产品
│   ├── sample_strategic_matrix_portfolio.html # # 战略矩阵
│   ├── sample_comprehensive_taxonomy_showcase.html # # 全要素透视
│   ├── gallery.html                    # # 全谱系画廊
│   └── index.html                      # 案例总览
├── tests/                              # 自动化测试代码
│   └── test_generation.py              # 看板与图表生成回归测试脚本
├── package.json                        # npm 包元数据（非推荐运行入口）
├── README.md                           # 根目录唯独文档说明
└── .gitignore
```

---

## 开源协议 (License)

MIT License

### Seaborn 统计图（可选）

安装 `pip install ".[statistics]"` 后，同一个 MCP 可声明直方图、箱线图、回归散点图，输出 SVG/PNG 并嵌入 Markdown 报告。保留 ECharts 交互图表。统计图直接读取原始观测行，显示口径、来源与缺失值计数；见 [声明合同与边界](docs/seaborn-backend.md)。

动态系列、固定大小散点和可配置提示字段见 [动态图表声明与覆盖范围](docs/dynamic-encoding.md)。
