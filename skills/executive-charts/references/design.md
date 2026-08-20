---
version: 2.0
name: executive-charts-and-reports-design-system
description: >-
  A restrained executive data-storytelling and visualization design system for Chinese management reports and enterprise BI.
  It enforces a paper-white canvas, charcoal typography, controlled navy accents (#123B5D), direct labeling,
  strict source notes, complete axis title collision governance, and high-impact decision narrative frameworks
  ("3 Charts + 1 Table + Metric Cards").

colors:
  primary: "#123B5D"
  primary-strong: "#0B2A42"
  primary-soft: "#DCE8F0"
  ink: "#17212B"
  ink-muted: "#52606D"
  ink-subtle: "#7B8794"
  canvas: "#FFFFFF"
  surface-subtle: "#F6F7F8"
  surface-emphasis: "#EEF2F5"
  rule: "#C9D1D8"
  gridline: "#E6EAED"
  positive: "#2F6B55"
  negative: "#A4453C"
  attention: "#9A6A18"
  on-primary: "#FFFFFF"

typography:
  page-title:
    fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif"
    fontSize: 28px
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: -0.3px
  page-deck:
    fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif"
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.6
  section-number:
    fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif"
    fontSize: 11px
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: 1.2px
  chart-title:
    fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif"
    fontSize: 18px
    fontWeight: 700
    lineHeight: 1.35
  chart-subtitle:
    fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.55
  body:
    fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.55
  body-emphasis:
    fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif"
    fontSize: 13px
    fontWeight: 600
    lineHeight: 1.55
  chart-label:
    fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif"
    fontSize: 11px
    fontWeight: 500
    lineHeight: 1.4
  data-label:
    fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif"
    fontSize: 11px
    fontWeight: 600
    lineHeight: 1.4
    fontFeature: tnum
  table-header:
    fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif"
    fontSize: 11px
    fontWeight: 700
    lineHeight: 1.4
    letterSpacing: 0.2px
  table-body:
    fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: tnum
  caption:
    fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif"
    fontSize: 11px
    fontWeight: 400
    lineHeight: 1.5

rounded:
  none: 0px
  xs: 2px
  sm: 4px
  md: 6px

spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px
  section: 48px

components:
  page-shell:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    maxWidth: 1600px
    desktopPadding: 32px
    mobilePadding: 16px
  card-container:
    backgroundColor: "{colors.canvas}"
    borderColor: "{colors.rule}"
    borderWidth: 1px
    borderRadius: "{rounded.sm}"
    boxShadow: "0 1px 3px rgba(0,0,0,0.04)"
  action-table:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    headerBackground: "{colors.surface-emphasis}"
    rowBorder: "1px solid {colors.rule}"
    rounded: "{rounded.xs}"
    cellPadding: 10px 14px
---

# 高管级数据可视化与战略分析报告设计系统 (DESIGN.md)

## 一、 系统定位与设计哲学

本设计系统旨在为**企业中高管决策、经营分析复盘、战略洞察与商业智能看板**提供一套严谨、克制、结论先行的数据表达标准。

### 核心原则 (Core Tenets)
1. **结论先行 (Judgment-First)**：标题即核心判断，副标题即统计口径与时间窗口，避免“销售额趋势”等无意义标签。
2. **证据闭环 (Evidence-Chain)**：图表紧跟业务判断提供可视化佐证，表格提供行动决议（Action Items）与责任人跟进。
3. **极简克制 (Restrained Elegance)**：全屏以“纸白（#FFFFFF）”为底，炭黑（#17212B）为字，单一海军蓝（#123B5D）为主调，正负情绪色（#2F6B55 松石绿、#A4453C 克制红）严格服务于业务偏离。
4. **全端防遮挡与零碰撞 (Zero-Collision Layout)**：所有坐标轴、数值标签、图例均遵循严格的几何避让规范，确保在任何分辨率下无叠字、无裁剪。

---

## 二、 坐标轴与图层布局约束金标准 (Axis Layout Standards)

经过大量多端屏幕与真实高管看板测试，全库确立如下不可动摇的 ECharts 布局配置标准：

### 1. 垂直类目图（柱状/折线/面积/直方图等）
- **Y 轴（数值量纲）**：
  - `nameLocation: 'end'`（顶端放置）
  - `nameTextStyle: { color: '#7B8794', fontSize: 10, align: 'left', padding: [0, 0, 6, 0] }`
  - 格式规范：明确中文单位，如 `销售额 (亿元)`、`活跃客户数 (家)`。
- **X 轴（分类与时间维度）**：
  - `nameLocation: 'middle'`（下侧居中定锚）
  - `nameGap: 24`（距离刻度标签 24px，杜绝下沉压盖）
  - `nameTextStyle: { color: '#7B8794', fontSize: 10, align: 'center' }`
- **网格（Grid）**：`{ top: 35, bottom: 36, left: 10, right: 18, containLabel: true }`

### 2. 横向条形图（`yAxis.inverse: true`）
- **Y 轴（类目名称）**：
  - **强制要求**：`nameLocation: 'start'`（在 `inverse: true` 下，`start` 为最上方），杜绝标题沉底压盖 `0` 刻度。
  - `nameTextStyle: { color: '#7B8794', fontSize: 10, align: 'left', padding: [0, 0, 6, 0] }`
- **X 轴（数值量纲）**：
  - `nameLocation: 'middle'`，`nameGap: 24`，下侧居中标注量纲（如 `规模 (亿元)`、`达成率 (%)`）。

### 3. 双 Y 轴复合图 (Dual-Axis Combo)
- **左 Y 轴**：`nameLocation: 'end'`, `align: 'left'`, `name: '营收 (亿元)'`
- **右 Y 轴**：`nameLocation: 'end'`, `align: 'right'`, `name: '增速 (%)'`
- **中间图例 (Legend)**：精简命名（如 `['营业收入', '同比增速']`），居中放置并留足左右边距（`itemGap: 16`），`grid.top: 42`。
- **柱体 vs 折线防重叠**：柱体数值放 `insideBottom`（底部沉锚），折线数值放 `top`（折线上方），垂直隔离 100px+。

---

## 三、 全谱系图表资产库 (9 大类 · 43 款标准资产)

| 意图分类 | 图表代号与名称 | 核心适用场景与高管表达要点 |
| :--- | :--- | :--- |
| **1. 对比与排名** | `c01` 标准垂直柱状图<br>`c02` 排序横向条形图<br>`c03` 分组对比柱状图<br>`c04` 双向偏离条形图<br>`c05` 棒棒糖图<br>`c06` 哑铃对比图<br>`c07` 重叠达成柱状图<br>`c08` 双向对称蝴蝶图 | 跨实体/大区规模排序；长文本类目展示；基期 vs 当期渗透率对比；线上 vs 线下渠道对称对照。 |
| **2. 时间与趋势** | `t01` 单线走势图<br>`t02` 预测虚实走势图<br>`t03` 阶梯走势图<br>`t04` 堆叠面积图<br>`t05` 斜率对照图<br>`t06` 双 Y 轴柱线复合图 | 月度/季度时序跟踪；历史实际 vs 未来预测；调价离散节点；产品结构演变；绝对金额与同比增速复合观测。 |
| **3. 构成与层级** | `k01` 中心指标环形图<br>`k02` 100% 堆叠条形图<br>`k03` 矩形树图 (Treemap)<br>`k04` 帕累托图 (80/20)<br>`k05` 实心饼图<br>`k06` 双层嵌套饼图 | 客户群结构分布；渠道占比结构；预算与研发投入层级拆解；质量缺陷与流失主因二八定律识别。 |
| **4. 分布与离散** | `d01` 频数分布直方图<br>`d02` 箱线图 (Boxplot)<br>`d03` 概率密度曲线图<br>`d04` 24H 时间热力矩阵 | 订单客单价区间密度；各大区合同金额分布离散度；工单响应时长分布；用户全周活跃时刻热力。 |
| **5. 关系与相关** | `r01` 战略 BCG 四象限矩阵<br>`r02` 战略 3D 气泡图<br>`r03` 多维相关系数矩阵<br>`r04` 业务拓扑网络关系图 | 业务增速 vs 利润率象限定位；获客成本 CAC vs LTV 客户价值；多业务指标协同性；组织与资金拓扑。 |
| **6. 流程与转化** | `f01` 商业决策转化漏斗<br>`f02` 资金价值链桑基图<br>`f03` 留存队列 Cohort 热力图 | 销售线索全链路漏斗；收入-成本-利润流向分布；新客批次 M0~M3 留存衰减轨迹。 |
| **7. 财务与归因** | `fn01` EBITDA 瀑布归因图<br>`fn02` 盈亏平衡收支图<br>`fn03` 敏感性龙卷风图<br>`fn04` 基准归一指数图 | 期初到期末利润归因桥梁；变动成本与固定成本盈亏临界；关键经营变量敏感度降序；多业务线基期对齐。 |
| **8. 目标与监控** | `m01` 目标考核子弹图<br>`m02` 不确定性扇形预测图<br>`m03` 红线阈值监控图<br>`m04` 半环进度仪表盘 | 关键 KPI 达成与 Target 线；未来不确定性情景走廊；超时率 5% 警戒红线；年度综合目标达成率。 |
| **9. 经典指标卡** | `mc01` 基础数值卡<br>`mc02` 同环比波动卡<br>`mc03` 微走势迷你面积卡<br>`mc04` 目标进度条形卡 | 核心财务总量展示；双向增减幅度直观呈现；14天高频脉冲趋势；倒计时与目标差额直观量化。 |

---

## 四、 十大经典战略与经营分析报告体系架构 (10 Executive Reports)

在管理看板与高管汇报中，页面采用 **“KPI 矩阵 + 核心图表证据链 + 战略决议行动表”** 的完整闭环：

### 1. 集团经营月度全景复盘报告 (Executive Monthly Business Review)
- **分析意图**：全面复盘集团当月营收、利润、现金流及大区达成质量，定位主要增减利因素。
- **配置组合**：
  - KPI 卡：累计总营收 (24.85亿)、综合毛利率 (58.4%)、EBITDA (5.42亿)、经营净现金流 (3.80亿)
  - 核心图表 1：营收绝对金额与同比增速双 Y 轴图 (`t06`)
  - 核心图表 2：利润变动 EBITDA 瀑布归因图 (`fn01`)
  - 核心图表 3：各大区渠道结构 100% 堆叠条图 (`k02`)
  - 决议表格：高管行动清单（增量线索跟进、低利业务管控、责任人与完成期限）

### 2. SaaS 订阅经营与单客经济模型报告 (SaaS Metrics & Unit Economics)
- **分析意图**：评估 SaaS 经常性收入健康度、客户生命周期价值及获客投入产出比。
- **配置组合**：
  - KPI 卡：年度经常性收入 ARR (4.85亿)、月度净留存率 NDR (118.5%)、LTV/CAC 比率 (4.2x)、月流失率 (0.8%)
  - 核心图表 1：历史实测与未来预测走势图 (`t02`)
  - 核心图表 2：获客成本 CAC vs LTV 战略气泡图 (`r02`)
  - 核心图表 3：月度获客批次留存热力矩阵 (`f03`)
  - 决议表格：大客户挽留策略与产品续约保障责任表

### 3. 战略产品线竞争格局与 BCG 四象限矩阵报告 (Strategic Product Portfolio & BCG Matrix)
- **分析意图**：识别明星业务、现金牛业务、探索业务与收缩业务，优化战略资源配置。
- **配置组合**：
  - KPI 卡：核心产品数 (12款)、高增业务占比 (42.5%)、战略研发投入 (1.85亿)、平均毛利率 (62.0%)
  - 核心图表 1：业务增速 vs 利润率战略四象限散点图 (`r01`)
  - 核心图表 2：核心产品线 ARR 降序排名条图 (`c02`)
  - 核心图表 3：关键变量波动敏感性龙卷风图 (`fn03`)
  - 决议表格：产品孵化与资源倾斜优先级决议表

### 4. 全链路营销 ROI 与销售转化漏斗报告 (Marketing ROI & Funnel Conversion)
- **分析意图**：穿透全渠道获客漏斗，发现流失瓶颈，优化投放预算 ROI。
- **配置组合**：
  - KPI 卡：营销总预算 (4,200万)、线索总数 (5,000条)、商机转化率 (12.0%)、综合单客获取成本 (7,000元)
  - 核心图表 1：商机全链路转化漏斗图 (`f01`)
  - 核心图表 2：多渠道投入产出偏离条图 (`c04`)
  - 核心图表 3：客户签约周期分布直方图 (`d01`)
  - 决议表格：高 ROI 渠道加码与低效渠道止损执行清单

### 5. 财务盈利与 EBITDA 杜邦归因深度报告 (Financial Profitability & EBITDA Attribution)
- **分析意图**：深度拆解净资产收益率 ROE，从利润率、周转率和财务杠杆三个维度穿透盈利质量。
- **配置组合**：
  - KPI 卡：净资产收益率 ROE (18.6%)、营业净利率 (22.4%)、资产周转率 (0.83次)、权益乘数 (1.65x)
  - 核心图表 1：EBITDA 利润归因瀑布桥梁图 (`fn01`)
  - 核心图表 2：季度收支与盈亏平衡点分析 (`fn02`)
  - 核心图表 3：业务线基准归一指数走势图 (`fn04`)
  - 决议表格：成本节降与固定费用控制方案表

### 6. 大客户销售管线 (Pipeline) 与赢单预测看板 (Enterprise Sales Pipeline & Win-Loss)
- **分析意图**：监控战略商机推进健康度、销售目标达成差距及输单核心原因。
- **配置组合**：
  - KPI 卡：管线商机总额 (8.60亿)、加权预测赢单 (5.20亿)、综合赢单率 (38.5%)、年度目标达成进度 (84.5%)
  - 核心图表 1：战略大客户销售考核子弹图 (`m01`)
  - 核心图表 2：输单主因 80/20 帕累托图 (`k04`)
  - 核心图表 3：各大区新老客户渗透率哑铃图 (`c06`)
  - 决议表格：Top 10 重点商机推进跟进表

### 7. 供应链履约效率与交付质量监控报告 (Supply Chain Fulfillment & Quality Control)
- **分析意图**：监控订单履约时效、全链路节点延误及交付缺陷率，保障履约 SLA。
- **配置组合**：
  - KPI 卡：准时交付率 OTD (96.8%)、平均履约周期 (3.2天)、交付客诉率 (0.42%)、异常超时订单 (18起)
  - 核心图表 1：关键监控节点超时率与 5% 红线阈值图 (`m03`)
  - 核心图表 2：履约响应耗时概率密度曲线 (`d03`)
  - 核心图表 3：制造交付中心网络拓扑流向图 (`r04`)
  - 决议表格：供应链瓶颈工序整改清单

### 8. 用户行为特征与活跃留存深度分析报告 (User Behavior, Cohort & Retention)
- **分析意图**：洞察用户活跃习惯、生命周期留存及高价值客户画像。
- **配置组合**：
  - KPI 卡：月活跃用户 MAU (185万)、次月留存率 (68.0%)、日均使用时长 (42分钟)、核心功能渗透率 (54.2%)
  - 核心图表 1：全周 24 小时活跃时刻热力图 (`d04`)
  - 核心图表 2：获客批次 M0~M3 队列留存热力矩阵 (`f03`)
  - 核心图表 3：客单金额分布直方图 (`d01`)
  - 决议表格：高价值客群促活与流失预警干预方案

### 9. 集团资金流向与业务价值链桑基报告 (Corporate Cash Flow & Value Chain Sankey)
- **分析意图**：穿透集团资金流动路径，清晰呈现主营收入如何转化为综合毛利并分配至研发、营销与净利润。
- **配置组合**：
  - KPI 卡：总资金流入 (10.00亿)、综合毛利额 (6.50亿)、期间总费用 (4.30亿)、净利润结余 (2.20亿)
  - 核心图表 1：收入-成本-利润资金流向桑基图 (`f02`)
  - 核心图表 2：研发/营销/营收多维相关矩阵 (`r03`)
  - 核心图表 3：2024~2025 战略变革斜率对照图 (`t05`)
  - 决议表格：资金头寸调配与费用管控方案表

### 10. 战略风险、敏感性与情景走廊预测报告 (Strategic Risk, Sensitivity & Scenario Forecast)
- **分析意图**：压力测试极端市场环境下核心经营指标的波动范围，制定应急预案。
- **配置组合**：
  - KPI 卡：综合风险指数 (28.5 低风险)、极端情景最大回撤 (-15.2%)、对冲覆盖率 (85.0%)、安全边际 (¥3.20亿)
  - 核心图表 1：净利润敏感性龙卷风图 (`fn03`)
  - 核心图表 2：未来 4 季度扇形不确定性预测走廊 (`m02`)
  - 核心图表 3：宏观因子相关系数热力矩阵 (`r03`)
  - 决议表格：极端情景压力测试应对预案与触发阈值表

---

## 五、 数据展示表格资产标准 (10. 数据展示表格 · 2 款)

以高密度、清晰结构化形式直接承载与呈现多维业务数据指标，作为图表之外的关键数据表达资产。

### 表格数字与格式化黄金铁律 (Data Formatting & Alignment Golden Standards)
1. **货币与大数单位换算 (Currency & Scale Conversion)**：
   - 货币必须加 `¥` 前缀；
   - 针对大于等于万级的数值，规范转化为 **“万”、“千万”、“亿”、“万亿”** 中文量纲，且**只保留 1 位小数**（如 `¥4.9 亿`、`¥3.4 亿`、`¥38.8 万`、`¥6,800 万`），去除无意义的多余小数位。
2. **百分比位数规范 (Percentage Precision)**：
   - 所有百分比指标（达成率、同比、环比、毛利、NDR、SLA）**严格保留 1 位小数**（如 `97.0%`、`88.3%`、`+35.2%`、`-4.8%`、`68.5%`）。
3. **单位微观经济学指标规范 (Micro-Unit Economics Precision)**：
   - 座公里收入 (RASK)、单位算力核时单价、每千次 API 请求成本等高精度微观指标，**严格保留 4 位小数**（如 `¥0.3456`、`¥0.2810`、`¥0.1950`、`¥0.1425`）。
4. **表格数字对齐铁律 (Strict Column Alignment)**：
   - **数值/金额/百分比/单位指标列**：**强制右对齐 (`text-right font-mono tabular-nums`)**，确保千分位与小数点上下垂直绝对齐整；
   - **文本列 (编码/业务线/大区/主管)**：**强制左对齐 (`text-left`)**；
   - **组件与状态列 (双色进度槽/微点评级芯片)**：**强制居中对齐 (`text-center`)**；
   - **表头与表体对齐必须 100% 严格一致**。

| 表格代号与名称 | 扩展列数与核心字段 | 适用业务场景与交互规范 |
| :--- | :--- | :--- |
| **`tb01` 标准多维数据展示表格 (无筛选器)** | **全要素经营数据**：`编码`、`核心业务线`、`责任大区`、`负责人`、`当期营收 (¥4.9亿)`、`预算目标`、`预算达成进度 (97.0%)`、`同比 YoY`、`环比 MoM`、`综合毛利`、`座公里/核时收入 (¥0.3456)`、`付费客户 (1.3万户)`、`客单均价 (¥38.8万)`、`健康评级`。<br>表头浅灰 `#F8FAFC`，数值等宽字体 `font-mono`，悬浮微高亮。 | 适合静态长图报告、经营分析看板中的核心业务明细数据通栏呈现。 |
| **`tb02` 交互式筛选数据展示表格 (带筛选器)** | **13 列多维即时检索明细**：`核心业务线`、`负责大区`、`大区主管`、`当期实收`、`目标达成进度`、`同比 YoY`、`环比 MoM`、`金额留存 NDR`、`座公里/核时收入 (¥0.3456)`、`客单均价`、`商机管线 (¥1.8亿)`、`履约 SLA`、`状态评级`。<br>内置顶部工具栏：关键词即时搜索框 + 大区/分类下拉筛选 + 实时匹配条数统计。 | 适合交互式中台 BI 经营大屏、多维业务下钻与数据检索表格。 |

---

## 六、 高管商业分析长图报告排版黄金法则 (Executive Long-Page Layout Standards)

在构建任何高管级经营分析报告、战略汇报长图或商业决策看板时，必须严格遵守以下排版栅格规范：

1. **核心 KPI 指标卡区 (Metric Row)**：
   - **4 列并排 / 2x2 响应式网格 (`grid-cols-2 lg:grid-cols-4`)**：展示大盘核心指标（营收、MRR、利润、目标达成率）。
2. **图表证据链区 (Evidence Charts Grid)**：
   - **强制采用【双列并排对齐】(`grid-cols-1 md:grid-cols-2`)，严禁 3 列拥挤排版**：
   - 单图卡片获得 650px+ 充分宽度与 310px 适宜高度，使双 Y 轴走势、100% 堆叠条、BCG 矩阵、3D 气泡、留存矩阵等图表呼吸舒展；
   - 图表按业务语义两两配对（如规模⇋结构、矩阵⇋归因、漏斗⇋单客、留存⇋敏感度、目标⇋预测）。
3. **管理决策与明细表格区 (Executive Action & Data Tables)**：
   - **⚡ 强制采用【单列全屏通栏】(`w-full` / `col-span-full`)，绝对禁止使用双列！**
   - **设计机理**：高管决议表与明细数据表包含多列关键字段（序号、证据链发现、核心管理决议、主责部门、交付期限、带微点状态徽章），只有单列通栏才能提供宽阔、连贯的横向决策视野与完整的文本展开空间。

---

## 七、 图例体系设计与分列布局规范 (Legend Taxonomy & Layout Standards)

针对不同图表类型、系列数量与视觉重心，建立 **4 种差异化图例布局形态**：

| 图例布局形式 | 适用图表场景 | ECharts 配置特征与参数 |
| :--- | :--- | :--- |
| **1. 单列垂直图例 (Single-Column Vertical)** | 环形图、饼图、极坐标图 (`k01`, `k05`, `k06`) | `orient: 'vertical'`, `right: 8~14`, `top: 'middle'`，微圆点 `itemWidth: 8~9`，垂直间距 `itemGap: 10`。图表主体相应左偏 (`center: ['38%', '50%']`) 为图例留白。 |
| **2. 双列对齐图例 (2-Column Paired Horizontal)** | 双Y轴复合、预算对比、哑铃跨度、折线预测、龙卷风、帕累托、盈亏平衡 (`t06`, `c03`, `c06`, `c07`, `c08`, `t02`, `fn02`, `fn03`, `fn04`, `k04`, `m01`) | `orient: 'horizontal'`, `top: 0`, `right: 12` 或 `left: 'center'`，`itemGap: 14~24`，`itemWidth: 10~14`，`itemHeight: 8~10`，紧凑清晰，两两呼应。 |
| **3. 4 列横向展开图例 (4-Column Horizontal Compact)** | 100% 堆叠条、堆叠面积、组织斜率、多组箱线 (`k02`, `t04`, `t05`, `d02`) | `orient: 'horizontal'`, `top: 0`, `left: 'center'`，`itemGap: 16~18`，文字字号 `10px`，多分类指标一字展开，平衡画面重心。 |
| **4. 单序列自明无图例 (Single-Series Minimalist)** | 单值柱状、排序横条、单线走势、瀑布归因、直方图、漏斗、散点气泡、热力矩阵 (`c01`, `c02`, `c04`, `c05`, `t01`, `fn01`, `f01`, `d01`, `d03`, `d04`, `r01`, `r02`, `r03`, `r04`, `m02`, `m03`, `m04`) | 精准省略多余图例框，指标名称与量纲内化于卡片标题、Y 轴顶端或象限水印中，保持最高数据墨水比。 |
