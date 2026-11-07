# McKinsey-Grade Executive Charts & Dashboard Suite (麦肯锡风格图表设计与高管决策看板套件)

---

文档总览见 [docs/README.md](docs/README.md)，开发与维护的按任务阅读入口见 [AGENTS.md](AGENTS.md)。

## 版本与运行入口

包版本以 `package.json` 为准，Runtime 版本以 `pyproject.toml` 和 `dashboard_runtime/__init__.py` 为准。

## 两条 Skills 与 MCP 生成路径

- **Dashboard**：保留 [executive-charts Skill](skills/executive-charts/SKILL.md) 和原有案例；MCP 案例 `charts://examples/executive-dashboard`。
- **分析报告**：[analytical-reports Skill](skills/analytical-reports/SKILL.md)，以认可的学术单栏版式为母稿；MCP 案例 `charts://examples/academic-report`。

MCP 可从空白文档声明数据、指标和图表，再写入包含嵌入图表的 Markdown 并渲染。调用 `generation_examples` 发现案例，`chart_declarations` 阅读声明合同，创建空白文档后，按共享流程开始编辑批次、提交修改、完成检查，再预览一次。每次 MCP 项目调用显式传入报表资产目录的绝对路径 `projectRoot`。案例数据均为合成数据，调用方必须用真实输入重写分析，不是仅导出一个母稿页面。见 [完整生成流程](docs/generation-tracks.md)。

## 本地个人分析报告 + Dashboard

Runtime 提供两种独立的呈现方式，生成时确定类型：Dashboard 保留响应式网格，分析报告是一整篇 Markdown 文档，以学术论文式单栏版面阅读。像写文档一样写标题、段落、加粗、列表和引用，在需要图表的位置插入 chart 代码块，图表就会在文字之间渲染。两种模式共享组件、数据、指标口径和版本记录，不需要部署企业平台。

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

## 自托管服务器：远程 MCP + 网页预览

在自己的服务器上运行一个进程，同时提供 Streamable HTTP MCP（Bearer 令牌）和看板、分析报告的浏览器预览。`dashboard_preview` 会额外返回带签名、可过期、可撤销的 `previewUrl`，不支持 MCP Apps 的客户端也能把链接交给读者；`dashboard_share` 可签发只读或编辑链接。

```bash
npm --prefix runtime-ui ci && npm --prefix runtime-ui run build
python3 -m pip install 'mcp>=1.28,<2'
python3 -m dashboard_runtime server --workspace /data/projects --public-url https://charts.example.com --token "<随机长令牌>"
claude mcp add --transport http charts-design https://charts.example.com/mcp --header "Authorization: Bearer <随机长令牌>"
```

远程调用中的 `projectRoot` 是项目名，不接受任意服务器路径。Docker、systemd 与 nginx 示例在 `deploy/`；部署、权限与边界见 [自托管服务器](docs/self-hosted-server.md)。

## 构图与指标卡：按问题选择，避免千篇一律

- **7 种布局模板**：`executive`、`focus`、`bento`、`sidebar`、`grid3`、`narrative`、`scorecard`，一条 `apply_layout_template` 操作同时生成桌面/平板/手机布局；未指定模板时新组件按角色排列，不再全宽堆叠。见 [布局模板](skills/executive-charts/references/layout_templates.md)。
- **16 种指标卡**：在原有 mc01–mc09 之外新增中位数极差、环形进度、迷你柱趋势、子弹目标、双期对比、指标清单、大字主指标（mc10–mc16），并给出每种卡回答的问题、字段与可绑定目标。见 [指标卡选型](skills/executive-charts/references/kpi-cards.md)。
- **按问题选图**：`chart_recommend` 根据分析意图与数据形态排列 40 种图表，标注可筛选绑定的图形，并降低本页已用图形的排序。
- **图表自适应**：窄卡片中自动为轴名称留出空间、截断拥挤类目、滚动过长图例；指标卡数值不再在单位中间换行。

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

## 项目结构 (Project Architecture)

```
charts-design/
├── AGENTS.md                           # 按任务阅读文档的入口
├── README.md                           # 项目用途与快速开始
├── docs/                               # 项目规范、实现说明与历史证据
│   ├── README.md                       # 文档总览
│   └── agent/file-management.md         # 文件存放与维护规则
├── bin/                                # CLI、MCP 启动与本地更新入口
├── deploy/                             # 自托管服务器的 Docker、systemd、nginx 示例
├── dashboard_runtime/                  # 状态、数据、查询、MCP 与共享网页模块
│   └── examples/academic-report.md      # 分析报告案例的唯一 Markdown 母稿
├── runtime-ui/                         # 原组件提取与前端打包
├── skills/
│   ├── executive-charts/               # Dashboard Skill、组件、脚本与参考材料
│   └── analytical-reports/             # 分析报告 Skill 与阅读母稿规范
├── examples/                           # 人工浏览的看板与画廊案例
├── tests/                              # 生成器、Runtime、协议与浏览器检查
├── package.json                        # Node 入口、检查命令与包发布清单
├── pyproject.toml                      # Python 依赖、版本与包配置
├── mcp.json                            # MCP 启动配置模板
└── .github/workflows/                  # CI 检查
```

---

## 开源协议 (License)

MIT License

### Seaborn 统计图（可选）

安装 `pip install ".[statistics]"` 后，同一个 MCP 可声明直方图、箱线图、回归散点图，输出 SVG/PNG 并嵌入 Markdown 报告。保留 ECharts 交互图表。统计图直接读取原始观测行，显示口径、来源与缺失值计数；见 [声明合同与边界](docs/seaborn-backend.md)。

动态系列、固定大小散点和可配置提示字段见 [动态图表声明与覆盖范围](docs/dynamic-encoding.md)。
