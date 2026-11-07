# 指标卡选型指南（mc01–mc16）

指标卡按“要回答的问题”选型，不按顺序套用 mc01–mc04。MCP 中 `chart_declarations {}` 返回 `kpiGuide`，`chart_declarations {"code":"mc13"}` 返回该卡的字段、可绑定目标和可通过校验的合成示例；`chart_recommend` 会按分析意图给出 `kpiShapes`。字段校验以 `scripts/core/component_schemas.py` 为准。

## 按问题选卡

| 问题 | 首选 | 备选 | 说明 |
| --- | --- | --- | --- |
| 核心指标现在多大 | mc01 基础数值卡 | mc16 大字主指标卡 | 每页最多一张 mc16，配一句作者撰写的解读 |
| 同比/环比在涨还是跌 | mc02 同环比波动卡 | mc14 双期对比卡 | mc14 同时展示本期与上期的绝对规模 |
| 近期连续走势 | mc03 迷你面积卡 | mc12 迷你柱趋势卡 | 离散周期（月、周）且强调最近一期时用 mc12 |
| 目标完成到哪一步 | mc04 进度条卡 | mc11 环形进度卡、mc13 子弹目标卡 | 需要“欠佳/达标/优秀”区间或目标线时用 mc13 |
| 0–100 分值在刻度上的位置 | mc05 半环仪表卡 | mc11 | 正常率、满意度等有满分的指标 |
| 两个同级指标并列 | mc06 双指标并列卡 | mc14 | 规模与效率、供给与需求 |
| 排名与梯队 | mc07 排位徽章卡 | — | 仅快照 |
| 超出阈值需要关注 | mc08 阈值预警卡 | — | 琥珀色提示，不使用涨跌红绿；仅快照 |
| 两部分构成占比 | mc09 结构分段卡 | mc15 指标清单卡 | 三项以上或口径不可相加时用 mc15；仅快照 |
| 偏态分布的典型值与离散度 | mc10 中位数极差分布卡 | — | 客单价、时长；`stats` 来自原始观测；仅快照 |
| 同一主题的 2–4 个子指标 | mc15 指标清单卡 | mc06 | 清单不代表可以相加；仅快照 |

## 组合规则

- 一行 KPI 优先用 2–4 种不同形态；需要直接横向比较的卡保持同一形态。
- 与布局搭配：mc16 主指标适合 `focus`、`scorecard` 模板；6 张以上 KPI 用 `scorecard`；KPI 需要常驻可见用 `sidebar`。见 [布局模板](layout_templates.md)。
- 筛选需要重算时，绑定 `bindableTargets` 中的字段（如 mc13 的 `actual`/`target`，mc14 的 `currentValue`/`priorValue`，mc12 的 `timeField`）。mc07–mc10、mc15 只支持快照，不能作为筛选消费者。
- mc13 的 `ranges` 默认是绝对值；绑定后目标会随筛选变化时，使用 `rangeBasis: "target"` 并把区间写成目标的比例（如 `[0.8, 1.0]`）。
- 同比、环比、目标、区间等比较值必须有真实依据并明确提供，系统不推算；无依据时省略字段，卡片显示中性值。
- 解读文字（mc16 `note`）由作者维护，筛选后不会自动改写，交付前复核。

## 必填字段速查

| 类型 | 必填 | 常用可选 |
| --- | --- | --- |
| mc01 / mc02 / mc08 / mc16 | `label`, `value` | `yoy`, `mom`, `subLabel`, `subVal`, `statusBadge`, `alertLabel`, `note` |
| mc03 / mc12 | `label`, `value`, `sparkMonths`, `sparkData`（或绑定 `timeField`） | `trendLabel`, `yoy` |
| mc04 / mc05 / mc11 | `label`, `value`；mc11 需 `percent` 或数值型 `value` | `percent`, `gaugeSub`, `trendLabel` |
| mc06 | `label`, `leftTitle`, `leftVal`, `rightTitle`, `rightVal` | `leftYoy`, `rightYoy` |
| mc07 | `label`, `value` | `rankSub`, `rankBadge` |
| mc09 | `label`, `value`, `segLeftWidth`, `segRightWidth`, `subLabel`, `subVal` | — |
| mc10 | `label`, `value`, `stats{min,p25,median,p75,max}` | `meanText`, `sampleText`, `valueLabel` |
| mc13 | `label`, `value`, `actual`, `target` | `ranges`, `rangeBasis`, `max`, `unit` |
| mc14 | `label`, `value`, `currentValue`, `priorValue` | `currentLabel`, `priorLabel`, `yoy`, `deltaLabel`, `unit` |
| mc15 | `label`, `items[1..4]{label,value,delta?}` | `value`, `valueLabel` |
