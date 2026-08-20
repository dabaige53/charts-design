# Executive Charts & Dashboard Generator Suite (图表与看板生成脚本套件)

本目录提供麦肯锡咨询级数据可视化组件与高管看板生成工具。Dashboard 的默认工作流是积木式 workspace：小组件独立维护、逐步验证、最终编译。

1. **`dashboard_workspace.py`**：创建、检查、验证和编译可组合 workspace。
2. **`generate_chart.py`**：生成独立图表组件、短名单预览或代码片段。
3. **`generate_dashboard.py`**：底层 HTML 编译器，并保留旧版单 JSON/preset 入口。

## 0. 积木式 Dashboard Workspace（推荐）

```bash
charts-design dashboard init ./board --title "经营决策看板"
charts-design dashboard add kpi ./board revenue \
  --label "营业收入" --value 224 --unit "万元"
charts-design dashboard add chart ./board regional-sales \
  --code c01 --title "各区域营业收入" --unit "万元" \
  --data-file ./regional-sales.json
charts-design dashboard inspect ./board --json
charts-design dashboard validate ./board --strict --json
charts-design dashboard build ./board --output ./dist/board.html
```

CSV 自动推断先生成可审查草稿，不直接作为最终图表证据：

```bash
charts-design dashboard import-csv ./board --csv ./data.csv
```

组件 schema 与稳定 JSON 输出约定见 [`../references/dashboard-workspace.md`](../references/dashboard-workspace.md)。

---

## 1. 单图表生成引擎 (`generate_chart.py`)

### 核心功能
- 支持 52 款完整分类图表（`c01~c08`, `t01~t06`, `k01~k06`, `d01~d04`, `r01~r05`, `f01~f03`, `fn01~fn04`, `m01~m04`）；
- 单文件自带 Tailwind CSS、ECharts 5.5.0 与 Lucide 矢量图标，开箱即用；
- 具备图表/表格视图切换、CSV/Excel 导出、高清 PNG 图片一键复制至 PPT、全屏研判与业务口径弹窗。

### 常用命令示例
```bash
# 1. 查看全部 52 款图表编号及中文释义
python scripts/generate_chart.py --list

# 2. 生成单个独立图表 HTML
python scripts/generate_chart.py --code c01 --output ./dist/chart_c01.html

# 3. 自定义图表标题并生成后自动在浏览器中打开
python scripts/generate_chart.py --code t06 --title "2026年客运总收入与客公里收益走势" --output ./dist/my_t06.html --open

# 4. 批量生成全部 52 款独立图表 HTML
python scripts/generate_chart.py --batch --outdir ./dist/all_charts/

# 5. 打印指定图表的原始 JavaScript ECharts 配置代码片段
python scripts/generate_chart.py --code r01 --snippet
```

---

## 2. 旧版整页入口 (`generate_dashboard.py`)

### 兼容能力
- 一键生成 7 大标准业务场景预设看板（零售连锁与电商、SaaS 产品分析、财务边际归因、民航综合研判、战略业务四象限、全景大满贯、月度决算）；
- 支持通过 `--config <file.json>` 传入 100% 自定义业务数据（标题、多维筛选器、4大KPI、图表矩阵、数据透视表）；
- 支持自由按图表编号任意拼装（如 `--charts "c01,t06,r01,fn01,m01,k04"`）；
- 标配 **吸顶多维筛选栏**（带智能搜索建议面板、互斥下拉、Active 胶囊标签）、**数据透视表**（列拖拽排序、列显隐配置、单行防折行、左右流畅滑动、分页、单元格复制与 CSV 导出）与 **咨询级指标说明词典**。

### 常用命令示例
```bash
# 1. 生成 7 大预设高管看板之一并立即在浏览器中打开
python scripts/generate_dashboard.py --preset retail_ecommerce --output ./dist/retail.html --open
python scripts/generate_dashboard.py --preset saas_product --output ./dist/saas_product.html
python scripts/generate_dashboard.py --preset financial_attribution --output ./dist/financial.html
python scripts/generate_dashboard.py --preset executive_report --output ./dist/executive_report.html
python scripts/generate_dashboard.py --preset strategic_matrix --output ./dist/strategic.html

# 2. 传入自定义业务数据 JSON 配置文件 (100% 任意行业定制)
python scripts/generate_dashboard.py --config ./custom_retail.json --output ./dist/my_retail.html --open

# 3. 自由选择图表编号组合生成专属高管看板
python scripts/generate_dashboard.py \
  --charts "c01,t06,k01,r01,fn01,m01,k04,c06" \
  --title "集团核心运营效能与战略财务研判看板" \
  --org "商业智能与运营决算中心" \
  --output ./dist/custom_board.html \
  --open
```

---

## 3. 核心模块与代码目录

```text
scripts/
├── generate_chart.py         # 单图表生成 CLI 与 Python API 入口
├── generate_dashboard.py     # 完整高管看板生成 CLI 与 Python API 入口
├── README.md                 # 脚本套件使用指南
└── core/
    ├── chart_catalog.py      # 52 款完整图表配置函数与数据抽取器 (ALL_CHARTS)
    ├── chart_builders.py     # 核心看板图表构建字典 (CHARTS_JS_DEFINITIONS)
    ├── dashboard_template.py # 生产级前端渲染框架与 DOM 交互引擎 (BASE_TEMPLATE)
    ├── explanations.py       # 52 款图表与 KPI 咨询级指标口径词典 (CHART_EXPLANATIONS_DATA)
    └── table_data.py         # 全要素航线数据集与表头元数据 (TABLE_COLUMNS / TABLE_ROWS)
```

---

## 4. Python API 调用示例

在您的自定义 Python 脚本或自动化工作流中，可直接导入上述模块进行调用：

```python
from scripts.generate_chart import generate_standalone_chart
from scripts.generate_dashboard import generate_dashboard

# 生成单图表
generate_standalone_chart(code="c01", output_path="./my_c01.html")

# 生成完整看板
generate_dashboard(
    preset_name="executive_report",
    chart_codes=["c01", "t06", "r01", "fn01", "m01", "k04"],
    title="我的高管决策看板",
    output_path="./my_dashboard.html"
)
```
