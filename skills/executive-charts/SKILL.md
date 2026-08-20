---
name: executive-charts
description: Generate McKinsey-grade executive business charts, KPI metric cards, interactive pivot tables, and filters. Use when creating standalone business charts, data tables, or invoking component generation scripts.
---

# 咨询级高管商业图表设计规范与看板生成指南

本技能为企业高管经营分析看板（Dashboard）、决策指标卡、交互式数据透视表及多维筛选器组件提供统一的设计标准、ECharts 配置库与看板生成工具。

> [!IMPORTANT]
> **核心原则与执行铁律**：
> 1. **【技能只读】**：`.agents/skills/` 目录下的所有脚本与模板为**只读基础设施**，在执行任何用户任务时**严禁修改技能源码**；
> 2. **【禁止套娃】**：严禁为了生成图表或看板而派生 `invoke_subagent`，必须在当前步骤直接通过 CLI 或 Python 脚本生成目标 HTML 文件；
> 3. **【UI 规范强制遵循】**：UI 视觉调色盘、咨询级设计风格、表格结构与交互、图表卡片 5+1 工具栏与代码结构必须 100% 遵循本技能规范；
> 4. **【业务数据自由定制】**：行业主题（零售电商/SaaS/金融财务/供应链/民航等）、KPI、图表数据与透视表内容通过 `--preset <name>` 或 `--config <custom.json>` 自由定义。

---

## 核心看板与图表生成指令 (Dashboard & Component CLI)

### 1. 组合生成高管看板 (Dashboard) - `scripts/generate_dashboard.py`

#### 方式 A：按行业预设一键生成（内置 7 大主流业务场景）
```bash
# 零售连锁与电商运营看板 (GMV/客单价/坪效/复购率/门店透视表)
python scripts/generate_dashboard.py --preset retail_ecommerce --output ./dist/retail.html --open

# SaaS 产品与客户生命周期看板 (ARR/CAC/NDR/留存漏斗/客户透视表)
python scripts/generate_dashboard.py --preset saas_product --output ./dist/saas.html --open

# 财务边际贡献与成本穿透看板 (营收/EBITDA/资金桑基图/事业部透视表)
python scripts/generate_dashboard.py --preset financial_attribution --output ./dist/financial.html --open

# 航空机队与航线运营效能看板
python scripts/generate_dashboard.py --preset executive_report --output ./dist/executive_report.html --open

# 战略四象限与风险矩阵 / 全要素全景大满贯 / 月度决算看板
python scripts/generate_dashboard.py --preset strategic_matrix --output ./dist/strategic.html
python scripts/generate_dashboard.py --preset comprehensive --output ./dist/comprehensive.html
python scripts/generate_dashboard.py --preset executive_monthly --output ./dist/monthly.html
```

#### 方式 B：自定义业务数据配置文件 (100% 自由定制任何行业)
编写 `custom_data.json`（支持自定义 `meta`、`filters`、`kpis`、`charts`、`table`）并一键生成：
```bash
python scripts/generate_dashboard.py --config ./custom_data.json --output ./dist/my_dashboard.html --open
```

#### 方式 C：自由组合 52 款图表代号
```bash
python scripts/generate_dashboard.py \
    --charts "c01,t06,k01,r01,fn01,m01,k04,c06" \
    --title "集团核心运营效能与财务战略研判看板" \
    --org "管理委员会 · 商业智能与决算中心" \
    --output ./dist/custom_dashboard.html --open
```

### 2. 按需生成单图表组件与代码片段 - `scripts/generate_chart.py`
```bash
# 生成单个独立图表 HTML (内置 5+1 工具栏、转数据表、口径弹窗)
python scripts/generate_chart.py --code t06 --output dist/chart_t06.html --open

# 提取指定图表的纯 JS ECharts Option 代码片段 (直接嵌入前端工程)
python scripts/generate_chart.py --code r01 --snippet

# 终端速查 52 款图表编号代号、名称与分类
python scripts/generate_chart.py --list
```

### 3. CLI 参数速查

#### 看板生成参数 (`scripts/generate_dashboard.py`)
| 参数 | 简写 | 说明 | 使用示例 |
| :--- | :--- | :--- | :--- |
| `--preset` | `-p` | 预设行业主题（`retail_ecommerce`, `saas_product`, `financial_attribution`, `executive_report` 等） | `--preset retail_ecommerce` |
| `--config` | `-f` | 自定义 JSON 配置文件路径（完全覆盖或扩展业务数据与结构） | `--config ./my_data.json` |
| `--charts` | `-c` | 组合图表代号逗号分隔列表（如 `"c01,t06,r01,m01"`） | `--charts "c01,t06,r01"` |
| `--title` | `-t` | 看板主标题 | `--title "零售连锁经营看板"` |
| `--org` | - | 机构/部门署名 | `--org "集团战略决算中心"` |
| `--output` | `-o` | 目标 HTML 文件路径 | `--output ./dist/report.html` |
| `--open` | - | 生成后自动在默认浏览器中打开预览 | `--open` |

#### 单图表生成参数 (`scripts/generate_chart.py`)
| 参数 | 简写 | 说明 | 使用示例 |
| :--- | :--- | :--- | :--- |
| `--code` | `-c` | 指定 52 款图表代号 | `--code t06` |
| `--output` | `-o` | 目标 HTML 文件路径 | `--output dist/chart_t06.html` |
| `--title` | `-t` | 自定义图表标题 | `--title "季度营收复合走势"` |
| `--snippet` | - | 仅在终端打印纯 JS Option 代码片段 | `--code r01 --snippet` |
| `--open` | - | 生成后自动打开浏览器预览 | `--open` |
| `--list` | `-l` | 终端打印 52 款图表编号与名称列表 | `--list` |

---

## 强制遵循规范 (Mandatory Standards)

### 1. UI 视觉与设计风格 (强制遵循)
- **视觉标准对齐**：必须严格遵循 [`references/design_standards.md`](references/design_standards.md) 中的旗舰深海蓝 `#123B5D` 主色体系、红正绿负金融语义色与白底卡片质感；
- **数据格式化对齐**：必须严格遵循 [`references/data_formatting_standards.md`](references/data_formatting_standards.md) 中的货币换算（亿/万）、百分比 1 位小数及 `font-mono` / `tabular-nums` 等宽排版；
- **标题纯粹无图标**：严禁在标题左侧添加任何前置装饰图标或粗竖条色块 (`border-l-4`)，依靠纯粹的字体字偶距构建层级；
- **零碰撞几何布局**：双 Y 轴图例居中 (`legend: { top: 0, left: 'center' }` + `grid.top: 52px`)；柱/线图保留 25% 天空留白 (`yAxis.max`)；降序条形图显式设置 `yAxis.nameLocation: 'start'`；
- **真实 ECharts 渲染**：微走势图（mc03）与微仪表盘（mc05）必须由真实 ECharts 实例动态渲染且具备 Hover Tooltip，严禁静态假 SVG。

### 2. 图表卡片 5+1 交互工具栏 (强制遵循)
生成的图表卡片右上角必须标配：
- **粒度切换**：支持 `月度` <-> `季度` 统计粒度平滑切换；
- **图表 / 数据透视表一键互转**：在 ECharts 可视化图表与高密度二维数据表之间无缝切换；
- **一键导出 CSV**：头部注入 `\uFEFF` UTF-8 BOM 字符，防止 Windows Excel 乱码；
- **复制 2x 高清 PNG**：调用 `inst.getDataURL({ pixelRatio: 2 })` 写入系统剪贴板，支持直接粘贴入 PPT；
- **全屏沉浸研判**：卡片全屏自适应展示并自动触发 `inst.resize()`，支持按 `ESC` 退出；
- **业务口径说明 `(i)`**：原生 `<dialog>` 弹窗呈现图表业务定义 (Overview)、数学公式 (`formula`) 与判定规则。

### 3. 表格结构与交互规范 (强制遵循)
- **自定义列配置抽屉**：列显隐勾选 + HTML5 原生拖拽重排 (Drag & Drop) + 一键恢复默认；
- **智能多列类型感知排序 (`▲/▼`)**：自动识别货币、百分比、增速正负值与评级权重进行真实数值升降序；
- **严格单行横向滑动**：声明 `whitespace-nowrap` + `overflow-x-auto`，严禁单元格折行；
- **三向对齐与复制**：文本靠左 (`text-left`)，数值靠右 (`text-right` + `font-mono`)，状态居中 (`text-center`)，单元格点击一键复制。

---

## 自由定制维度 (Flexible Customization)

以下维度不设限制，由用户与业务场景自由定义：
1. **页面布局形式**：支持单图卡片、双栏网格、三栏透视、指标卡矩阵或侧边栏布局；
2. **行业与业务主题**：通用适用于民航、金融财务、SaaS 经营、电商零售、物流供应链等任何行业；
3. **数据指标与分析口径**：指标名称、图表标题、字段定义及口径字典完全按用户业务需求自由定制。

---

## 图表选型与设计体系

### 1. 8 大分析意图与图表选型速查

完整 52 款图表代码与标准 ECharts Option 库见 [`references/chart_catalog.json`](references/chart_catalog.json)：

| 核心分析意图 | 推荐图表代号与名称 | ECharts 系列 | 典型应用方向 |
| :--- | :--- | :--- | :--- |
| **1. 对比与排名** | `c01` 柱状图 / `c02` 排序条形图 / `c08` 蝴蝶图 | `bar` | 分部门/区域创收对比、产品线排行、双向对称比较 |
| **2. 时间与趋势** | `t01` 趋势折线 / `t04` 堆叠面积 / `t06` 柱线复合 | `line / bar` | 月度营收时序、业务结构演变、收入与增速双轴 |
| **3. 构成与层级** | `k01` 环形图 / `k03` 矩形树图 / `k04` 帕累托图 | `pie / treemap` | 客群/渠道构成、资产体量分布、80/20 根因诊断 |
| **4. 分布与离散** | `d01` 直方图 / `d02` 箱线图 / `d04` 热力图 | `bar / boxplot` | 价格区间分布、收益离散度、时段 x 维度热力 |
| **5. 关系与相关** | `r01` 四象限散点 / `r03` 相关性矩阵 / `r05` 雷达图 | `scatter / radar` | BCG 增长-份额矩阵、多因子相关性、多维能力对标 |
| **6. 流程与转化** | `f01` 漏斗图 / `f02` 桑基图 / `f03` 留存热力 | `funnel / sankey` | 销售漏斗转化、资金/流量流向、用户批次留存 |
| **7. 财务与归因** | `fn01` 瀑布图 / `fn02` 剪刀差盈亏 / `fn03` 敏感性 | `bar / line` | 毛利至 EBITDA 逐项归因、收支平衡线、弹性敏感度 |
| **8. 目标与监控** | `m01` 子弹图 / `m02` 扩散走廊 / `m03` 阈值红线 | `bar / markLine` | 战略 KPI 达成、预测走廊、预算超支监控 |

### 2. 10 种 KPI 指标卡体系 (`mc01` ~ `mc10`)
- `mc01`: 基础大字数值卡（核心数值 + 同比标签）
- `mc02`: 同环比双差波动卡（YoY / MoM 双列示）
- `mc03`: 微走势火花曲线卡（真实 ECharts 12M 平滑折线面积图 + Hover Tooltip）
- `mc04`: 胶囊进度与缺口对标卡（进度条 + 实际 vs 配额）
- `mc05`: 半环形微仪表盘达成卡（真实 ECharts 半环微仪表盘 + 行业标杆线）
- `mc06`: 双维裂变对标卡（供给 vs 周转双柱成对）
- `mc07`: 战略排名与梯队徽章卡（排名勋章 + S 级领跑评级）
- `mc08`: 红线阈值动态预警卡（超支率 + 5% 红线警示框 + 呼吸警示灯）
- `mc09`: 多段结构分部占比卡（多段复合进度条）
- `mc10`: 中位数与极差分布卡（中位数大字 + 四分位 P25~P75 极差条）

---

## 核心规范与外部资源指针 (Mandatory Reference Specs)

| 类别 | 资源指针 | 核心内容 | 约束属性 |
| :--- | :--- | :--- | :--- |
| **设计系统与 Token** | [`references/design_standards.md`](references/design_standards.md) | 调色盘 Token、零碰撞几何法则、全要素 Tooltip 源码 | **强制遵循** |
| **数据与数值规范** | [`references/data_formatting_standards.md`](references/data_formatting_standards.md) | 货币换算、百分比精度、座公里 4 位小数等宽排版 | **强制遵循** |
| **图表 Option 库** | [`references/chart_catalog.json`](references/chart_catalog.json) | 52 款图表全谱系代号与完整 ECharts Option 规范源码 | **标准基准** |
| **业务口径字典** | [`references/chart_explanations.json`](references/chart_explanations.json) | 52 款图表业务定义、数学公式 (`formula`)、判定规则 | **标准基准** |
| **布局与案例库** | [`references/layout_templates.md`](references/layout_templates.md) | 网格布局、视口约束、卡片尺寸规范 | 参考实现 |
| | [`examples/`](examples/) | 8 个全真交互生产级 HTML 完整页面与大画廊源码 | 案例参考 |
| **自动化生成脚本** | [`scripts/generate_dashboard.py`](scripts/generate_dashboard.py) | 高管看板（Dashboard）一键生成与图表自由组装脚本 | 核心引擎 |
| | [`scripts/generate_chart.py`](scripts/generate_chart.py) | 单图表 HTML 导出与代码片段提取工具 | 组件工具 |
| | [`scripts/README.md`](scripts/README.md) | 脚本使用指南与 Python API 文档 | 工具文档 |
