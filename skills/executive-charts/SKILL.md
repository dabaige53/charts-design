---
name: executive-charts
description: Generate McKinsey-grade executive business charts, KPI metric cards, interactive pivot tables, and filters. Use when creating standalone business charts, data tables, or invoking component generation scripts.
---

# 咨询级高管商业图表设计规范与看板生成指南

本技能为企业高管经营分析看板（Dashboard）、决策指标卡、交互式数据透视表及多维筛选器组件提供统一的设计标准、ECharts 配置库与看板生成工具。

> [!IMPORTANT]
> **核心原则与执行铁律**：
> 1. **【严禁仿写/阅读巨型 HTML 样例】**：严禁阅读或仿造 `examples/*.html` 手写 3000 行 HTML，必须通过 CLI / Python 脚本声明式生成；
> 2. **【技能只读】**：`.agents/skills/` 目录下的所有脚本与模板为**只读基础设施**，在执行任何用户任务时**严禁修改技能源码**；
> 3. **【禁止套娃】**：严禁为了生成图表或看板而派生 `invoke_subagent`，必须在当前步骤直接通过 CLI 或 Python 脚本生成目标 HTML 文件；
> 4. **【零数据纯净骨架】**：模板与图表引擎 100% 由数据驱动，绝不内置民航假数据；
> 5. **【全自动数据生成】**：若用户提供了 CSV 数据，首选使用 `--from-csv` 1 秒全自动直出纯净看板！

---

## 核心看板与图表生成指令 (Dashboard & Component CLI)

### 1. 组合生成高管看板 (Dashboard) - `scripts/generate_dashboard.py`

#### 方式 A：从业务 CSV 一键全自动生成（首选！100% 数据驱动，0 脏数据）
用户提供了 CSV 数据文件时，直接调用：
```bash
# 从 CSV 自动识别维度、数值、比率与量纲，1 秒直出纯净报告
python scripts/generate_dashboard.py --from-csv ./零售门店经营明细.csv --output ./dist/retail.html --open

# 或使用全局 npm / npx 命令
npx charts-design from-csv ./零售门店经营明细.csv --output ./dist/retail.html --open
```

#### 方式 B：自定义业务数据配置文件 (JSON 自由定制任何行业)
编写 `custom_data.json`（支持自定义 `meta`、`filters`、`kpis`、`charts`、`table`）并一键生成：
```bash
python scripts/generate_dashboard.py --config ./custom_data.json --output ./dist/my_dashboard.html --open
```

#### 方式 C：按行业预设一键生成（内置 7 大主流业务场景）
```bash
# 零售连锁与电商运营看板 (GMV/客单价/坪效/复购率/门店透视表)
python scripts/generate_dashboard.py --preset retail_ecommerce --output ./dist/retail.html --open

# SaaS 产品与客户生命周期看板 (ARR/CAC/NDR/留存漏斗/客户透视表)
python scripts/generate_dashboard.py --preset saas_product --output ./dist/saas.html --open

# 财务边际贡献与成本穿透看板 (营收/EBITDA/资金桑基图/事业部透视表)
python scripts/generate_dashboard.py --preset financial_attribution --output ./dist/financial.html --open

# 战略四象限与风险矩阵 / 全要素全景大满贯 / 月度决算看板
python scripts/generate_dashboard.py --preset strategic_matrix --output ./dist/strategic.html
python scripts/generate_dashboard.py --preset comprehensive --output ./dist/comprehensive.html
python scripts/generate_dashboard.py --preset executive_monthly --output ./dist/monthly.html
```

#### 方式 D：自由组合 52 款图表代号
```bash
python scripts/generate_dashboard.py \
    --charts "c01,t06,k01,r01,fn01,m01,k04,c06" \
    --title "集团核心运营效能与财务战略研判看板" \
    --org "管理委员会 · 商业智能与决算中心" \
    --output ./dist/custom_dashboard.html --open
```

---

### 2. 按需生成单图表组件与代码片段 - `scripts/generate_chart.py`
```bash
# 生成单个独立图表 HTML (内置 5+1 工具栏、转数据表、口径弹窗)
python scripts/generate_chart.py --code t06 --output dist/chart_t06.html --open

# 提取指定图表的纯 JS ECharts Option 代码片段 (直接嵌入前端工程)
python scripts/generate_chart.py --code r01 --snippet

# 终端速查 52 款图表编号代号、名称与分类
python scripts/generate_chart.py --list
```

---

### 3. CLI 参数速查

#### 看板生成参数 (`scripts/generate_dashboard.py` / `npx charts-design`)
| 参数 | 简写 | 说明 | 使用示例 |
| :--- | :--- | :--- | :--- |
| `--from-csv` | `--csv` | 传入业务 CSV 文件，全自动数据探测并生成 100% 贴合的数据看板 | `--from-csv ./data.csv` |
| `--preset` | `-p` | 预设行业主题（`retail_ecommerce`, `saas_product`, `financial_attribution` 等） | `--preset retail_ecommerce` |
| `--config` | `-f` | 自定义 JSON 配置文件路径（完全覆盖或扩展业务数据与结构） | `--config ./my_data.json` |
| `--charts` | `-c` | 组合图表代号逗号分隔列表（如 `"c01,t06,r01,m01"`） | `--charts "c01,t06,r01"` |
| `--title` | `-t` | 看板主标题 | `--title "零售连锁经营看板"` |
| `--org` | - | 机构/部门署名 | `--org "集团战略决算中心"` |
| `--output` | `-o` | 目标 HTML 文件路径 | `--output ./dist/report.html` |
| `--open` | - | 生成后自动在默认浏览器中打开预览 | `--open` |

---

## 强制遵循规范 (Mandatory Standards)

### 1. UI 视觉与设计风格 (强制遵循)
- **视觉标准对齐**：必须严格遵循 [`references/design_standards.md`](references/design_standards.md) 中的旗舰深海蓝 `#123B5D` 主色体系、红正绿负金融语义色与白底卡片质感；
- **数据格式化与量纲对齐**：表头、图表 Y 轴、Tooltip、KPI 卡片显式携带量纲（万元/亿元/%/天/人），按指标类型智能格式化，杜绝量纲歧义；
- **标题纯粹无图标**：严禁在标题左侧添加任何前置装饰图标或粗竖条色块 (`border-l-4`)，依靠纯粹的字体字偶距构建层级；
- **自包含与响应式**：必须支持 100% 离线自包含，支持自适应移动端与 4K 大屏。
