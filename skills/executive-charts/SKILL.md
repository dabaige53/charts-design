---
name: executive-charts
description: Generate McKinsey-grade executive business charts, KPI metric cards, interactive pivot tables, and filters. Use when creating standalone business charts, data tables, or invoking component generation scripts.
---

# 咨询级高管商业图表设计规范与看板生成指南 (Executive Charts & Dashboard Suite)

本技能为企业高管经营分析看板（Dashboard）、决策指标卡、交互式数据透视表及多维筛选器组件提供统一的设计标准、52 款 ECharts 配置库与看板声明式拼装引擎。

> [!IMPORTANT]
> **核心原则与执行铁律**：
> 1. **【AI 驱动的模块化编排】**：图表是独立的原子组件，AI Agent 负责业务分析、图表选型与数据计算，渲染引擎负责 100% 严格遵循咨询规范渲染，**杜绝黑盒黑魔法猜测与单一特制代码**；
> 2. **【严禁仿写/阅读巨型 HTML 样例】**：严禁阅读或仿造 `examples/*.html` 手写 3000 行 HTML，必须通过 CLI / Python 脚本声明式生成；
> 3. **【技能只读】**：`.agents/skills/` 目录下的所有脚本与模板为**只读基础设施**，在执行任何用户任务时**严禁修改技能源码**；
> 4. **【色彩与量纲强制遵循】**：严格遵循旗舰深海蓝 `#123B5D` 与 8 色咨询定性序列，表头与 Tooltip 必须显式带量纲（万元/亿元/%/天/元/㎡），彻底消除歧义；
> 5. **【图表系统代码显式呈现】**：所有图表卡片必须在标题右侧显式展示分类代码 Badge（如 `C01`, `T06`, `R01`, `K01`）。

---

## 推荐标准工作流：AI 模块化批量出图与看板拼装 (AI Modular Workflow)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 步骤 1：业务数据深度研判与图表选型 (AI Analysis & Chart Selection)          │
│    - AI 研读用户数据 (CSV/JSON/DB)，提取核心业务维度、规模指标与效率指标   │
│    - 从 52 款麦肯锡图表库中挑选 4~6 款最佳图表代号 (如 c01/k01/r01/c04)    │
│    - 可通过 `npx charts-design batch "c01,k01,r01"` 批量生成单图预览校验   │
├─────────────────────────────────────────────────────────────────────────────┤
│ 步骤 2：AI 编写声明式看板配置 (`analysis_config.json`)                      │
│    - AI 构建 4 大 KPI 指标卡 (数值、YoY/MoM、量纲、状态徽章)               │
│    - AI 组织 4 块图表的数据序列、标题、量纲与三段式口径说明 (Overview/Rule)│
│    - AI 定义 0 到 N 个动态多维筛选器 (维度键名、多选/单选、选项列表)       │
│    - AI 整理全要素数据透视表 (带单位表头、数值行、对齐方式)                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ 步骤 3：一键确定性编译出看板 (Deterministic Dashboard Compilation)          │
│    - 执行 `npx charts-design dashboard --config analysis_config.json`      │
│    - 输出 100% 贴合业务、0 脏数据、带全套交互的咨询级高管看板               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 核心 CLI 命令与使用指南

### 1. 单图表与批量图表组件生成 - `generate_chart.py` / `npx charts-design chart`

```bash
# 1. 生成单个独立图表 HTML (内置 5+1 工具栏、转数据表、口径弹窗、系统代号 Badge)
npx charts-design chart --code t06 --output dist/chart_t06.html --open

# 2. 批量生成多个原子图表组件 (供 AI 检查或作为独立部件交付)
npx charts-design batch "c01,t06,r01,k01" --output ./dist/charts/

# 3. 提取指定图表的纯 JS ECharts Option 代码片段 (直接嵌入前端工程)
npx charts-design chart --code r01 --snippet

# 4. 终端速查 52 款图表编号代号、名称与分类
npx charts-design list
```

### 2. 高管看板拼装引擎 - `generate_dashboard.py` / `npx charts-design dashboard`

#### 方式 A：AI 组装自定义业务配置文件 (推荐！100% 确定性，零脏数据)
```bash
npx charts-design dashboard --config ./my_analysis.json --output ./dist/report.html --open
```

#### 方式 B：指定图表代号列表组合生成
```bash
npx charts-design dashboard \
    --charts "c01,t06,k01,r01,fn01,m01" \
    --title "集团核心运营效能研判看板" \
    --org "商业智能与运营决策中心" \
    --output ./dist/custom_report.html --open
```

#### 方式 C：内置行业预设看板
```bash
# 零售连锁电商 | SaaS产品 | 财务归因 | 战略矩阵 | 综合全景
npx charts-design dashboard --preset retail_ecommerce --output ./dist/retail.html --open
npx charts-design dashboard --preset saas_product --output ./dist/saas.html --open
npx charts-design dashboard --preset financial_attribution --output ./dist/financial.html --open
```

---

## 咨询级调色盘与视觉标准 (Mandatory Color Tokens)

| Token 类别 | 键名 | 色值 (HEX) | 适用场景与视觉规范 |
| :--- | :--- | :--- | :--- |
| **品牌主色** | `primary` | `#123B5D` | 旗舰深海蓝（主序列柱体、主折线、核心强调） |
| **高对比墨色** | `primaryStrong` | `#0B2A42` | 墨蓝黑（主标题、Top 1 领跑标杆、顶层徽章） |
| **辅助淡色** | `primarySoft` | `#DCE8F0` | 冰川淡蓝（辅助对比柱体、目标底槽、高亮背景） |
| **定性多系列** | `categorical` | `['#123B5D', '#2C6485', '#628EA8', '#8C9DAE', '#9A6A18', '#A4453C', '#2F6B55', '#BDD0DC']` | 8 色麦肯锡定性色系（饼图、堆叠柱图、多折线图） |
| **业务正向** | `positive` | `#2F6B55` | 咨询墨绿（正向增长、超额达成、利润拉动） |
| **业务负向** | `negative` | `#A4453C` | 咨询绯红（负向侵蚀、落后承压、成本超支） |
| **重点关注** | `attention` | `#9A6A18` | 咨询琥珀金（重点关注、预警黄牌、探索象限） |
| **文字炭黑** | `ink` | `#0F172A` | 正文文本、关键数值标签 |
| **次级板岩** | `inkMuted` | `#52606D` | 副标题、坐标轴刻度、图例文本 |
| **注脚淡灰** | `inkSubtle` | `#7B8794` | 坐标轴量纲、数据来源注脚 |
| **分割基准** | `gridline` / `rule` | `#E2E8F0` / `#CBD5E1` | 发丝级网格线与基准对齐线 |
