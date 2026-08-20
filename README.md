# McKinsey-Grade Executive Charts & Dashboard Suite (麦肯锡风格图表设计与高管决策看板套件)

Enterprise-grade, McKinsey/Bloomberg/FT-caliber business charts, KPI decision cards, interactive pivot tables, and responsive executive dashboards built with Tailwind CSS and Apache ECharts 5.5.

本项目提供了一整套麦肯锡/彭博/FT 级别的企业高管经营分析图表、决策指标卡、交互式数据透视表及多维全局筛选器，并配有完整的 CLI 自动化生成引擎与 Antigravity / Stitch 技能库规范。

---

## 核心看板快速体验 (Executive Dashboards)

所有标准高管决策看板与全谱系画廊已归档至 [**`examples/`**](examples/) 目录，直接在浏览器中打开即可沉浸研判：

| 看板文件 | 业务场景分类 | 核心图表与分析重点 |
| :--- | :--- | :--- |
| [**`examples/executive_report.html`**](examples/executive_report.html) | **# 核心研判** | 航线网络与机队效能穿透、RASK/PLF 联动、14 列表格、全局多维筛选 |
| [**`examples/sample_executive_monthly.html`**](examples/sample_executive_monthly.html) | **# 经营月度** | 总裁级经营月度早报、时序营收走势、预算达成率子弹图、客座率散点跨度 |
| [**`examples/sample_financial_attribution.html`**](examples/sample_financial_attribution.html) | **# 财务归因** | EBITDA 毛利归因瀑布图、收支剪刀差盈亏线、成本敏感度多因子分析 |
| [**`examples/sample_saas_product_analytics.html`**](examples/sample_saas_product_analytics.html) | **# SaaS 产品** | 订阅漏斗全链路转化、MRR 留存热力图、NDR / LTV 单元经济学透视 |
| [**`examples/sample_strategic_matrix_portfolio.html`**](examples/sample_strategic_matrix_portfolio.html) | **# 战略矩阵** | BCG 增长-份额战略四象限、资产组合气泡阵列、多维能力雷达对标 |
| [**`examples/gallery.html`**](examples/gallery.html) | **# 全谱系画廊** | 52 款麦肯锡咨询级图表全要素样式墙与全量交互示例 |

---

## 安装与使用 (Installation & Usage)

### 方式一：npx 零安装直接运行（推荐）

无需 clone 仓库，一行命令即可生成高管看板（需本机已安装 Python 3.10+）：

```bash
# 安装并运行
npx charts-design dashboard --preset executive_monthly --output ./monthly.html --open

# 自由组合图表生成自定义看板
npx charts-design dashboard --charts "c01,t06,k01,r01,fn01,m01" \
    --title "集团核心运营效能研判看板" --output ./report.html --open

# 生成单图表组件
npx charts-design chart --code t06 --output ./chart_t06.html --open

# 提取纯 JS ECharts Option 代码片段（直接嵌入 React/Vue）
npx charts-design chart --code r01 --snippet

# 查看全部 52 款图表编号
npx charts-design list
```

### 方式二：Clone 仓库本地使用

```bash
git clone https://github.com/dabaige53/charts-design.git
cd charts-design

# 生成看板
python skills/executive-charts/scripts/generate_dashboard.py \
    --preset executive_report --output ./examples/report.html --open

# 生成单图表
python skills/executive-charts/scripts/generate_chart.py --code t06 --output ./chart_t06.html
```

### CLI 子命令速查

| 子命令 | 说明 | 示例 |
| :--- | :--- | :--- |
| `dashboard` | 生成完整高管看板（筛选栏 + KPI 卡 + 图表矩阵 + 透视表） | `npx charts-design dashboard --preset executive_monthly -o report.html` |
| `chart` | 生成独立图表组件（带 5+1 工具栏） | `npx charts-design chart --code t06 -o chart.html` |
| `list` | 终端打印 52 款图表编号与分类 | `npx charts-design list` |

---

## 核心亮点 (Key Features)

- **52 款咨询级图表全谱系 (Taxonomy 52)**：涵盖对比、趋势、构成、分布、关系、转化、财务归因、监控 8 大核心分析意图。
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
├── bin/                                # npx CLI 入口 (Node.js 薄壳封装)
│   └── cli.js                         # 自动检测 Python 3 并委派至生成脚本
├── skills/                             # 技能库 (包含核心 executive-charts)
│   └── executive-charts/               # 麦肯锡高管商业图表技能包
│       ├── SKILL.md                    # 技能标准与强制遵循规范
│       ├── scripts/                    # 看板与图表生成 CLI (generate_dashboard.py, generate_chart.py)
│       ├── references/                 # 设计系统 Token、数据规范与 52 款 Option 库
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
├── package.json                        # npm 包配置 (支持 npx charts-design)
├── README.md                           # 根目录唯独文档说明
└── .gitignore
```

---

## 开源协议 (License)

MIT License
