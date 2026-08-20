# 麦肯锡级高管商业图表与数据看板设计规范 (Executive Design Standards & Guidelines)

本文档为高管商业图表、决策看板与高密度数据表格的**独立设计建议与视觉工程规范中心**。
任何图表生成、UI 调整与页面重构均需严格遵守本规范中的色彩令牌、几何零碰撞法则、全要素 Tooltip 及排版层次。

---

## 1. 咨询级调色盘与语义 Token 规范 (Color Palette & Semantic Tokens)

本系统采用麦肯锡（McKinsey）、英国《金融时报》（Financial Times）与彭博（Bloomberg）风格的高级商务深海蓝体系，杜绝高饱和度与刺眼荧光色。

```javascript
const colorTokens = {
    // 品牌与主序列
    primary: '#123B5D',        // 旗舰深海蓝（主序列柱体、主折线、核心强调）
    primaryStrong: '#0B2A42',  // 墨蓝黑（高对比主标题、顶层徽章背景）
    primarySoft: '#DCE8F0',    // 冰川淡蓝（辅助对比柱体、目标底槽、高亮背景）
    
    // 文本与排版
    ink: '#17212B',            // 炭黑（正文文本、关键数值标签）
    inkMuted: '#52606D',       // 板岩深灰（次要序列、副标题、坐标刻度）
    inkSubtle: '#7B8794',      // 板岩淡灰（坐标轴量纲、数据来源注脚）
    
    // 业务语义色（严格遵循中国金融市场红正绿负标准）
    positive: '#A4453C',       // 绯红（正向增长、超额达成、利润拉动）
    negative: '#2F6B55',       // 祖母绿（负向侵蚀、落后滞后、成本扣减）
    attention: '#9A6A18',      // 琥珀金（重点关注、预警黄牌、探索象限）
    
    // 界面结构与背景
    canvas: '#FFFFFF',         // 纯白卡片底色
    surfaceGround: '#F8FAFC',  // 极淡灰蓝整页背景
    gridline: '#E6EAED',       // 发丝级网格分割线（1px）
    rule: '#C9D1D8'            // 坐标轴基准线、容器边框线
};
```

---

## 2. 零碰撞几何布局黄金法则 (Zero-Collision Geometry Laws)

所有 ECharts 图表必须遵循几何零碰撞标准，彻底消除标题、图例、轴名称与数据标签相互叠字或出界：

```
┌─────────────────────────────────────────────────────────────┐
│ 卡片 Header: 标题 (左) + 粒度/转表/导CSV/复制/全屏/(i) (右) │
├─────────────────────────────────────────────────────────────┤
│ Chart Canvas:                                               │
│             [ 图例 1 ]  [ 图例 2 ] (居中 top: 0, left: center)│
│                                                             │
│ 左Y轴名称 (收入)                              右Y轴名称(增速) │
│ (align: left)                                (align: right) │
│  ↑                                                       ↑  │
│  │ 25% 天空留白 (yAxis.max = val.max * 1.25)             │  │
│  │ ┌─────┐ 92.4%                     +18.5% ─●           │  │
│  │ │     │                                   │           │  │
│  └─┴─────┴───────────────────────────────────┴───────────┤  │
│   X轴名称 (统计时段) (middle, nameGap: 22)                  │
└─────────────────────────────────────────────────────────────┘
```

1. **双 Y 轴图例居中准则**：在双 Y 轴复合图（如 `t06`, `k04`）中，图例**100% 强制配置 `legend: { top: 0, left: 'center' }`**，`grid.top: 52px`；左 Y 轴 `align: 'left'`，右 Y 轴 `align: 'right'`，彻底杜绝右上角图例与右轴名称叠字；
2. **横向条形图起点锁定**：在 `inverse: true` 的降序条形图中，必须显式配置 `yAxis.nameLocation: 'start'`，防止标题下沉重叠 0 刻度；
3. **25% 天空留白法则 (Sky Headroom)**：所有柱图/折线图 `yAxis.max: val => Math.ceil(val.max * 1.25)`，柱顶数值标签永不与 Y 轴量纲粘连；
4. **柱内高对比度打标**：蝴蝶图 (`c08`) 与龙卷风图 (`fn03`) 采用柱内纯白反显打标（`position: 'inside'`, `color: '#FFFFFF'`），避免外置标签被右侧或左侧 Canvas 边界裁切；
5. **极简坐标轴线**：X 轴与 Y 轴刻度线隐藏（`axisTick: { show: false }`），分割线采用 `gridline: '#E6EAED'`，保持画布呼吸感。

---

## 3. 全要素指标生态与穿透 Tooltip 规范 (Full-Element Indicator Law)

> [!IMPORTANT]
> **严禁输出孤立标量的“玩具图表”！** 任何经营图表必须建立 **“规模 + 供给 + 效率 + 效益 + 增速”** 完整闭环，并通过统一的穿透式 Tooltip 渲染。

```javascript
// 规范 Tooltip 配置
tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(255, 255, 255, 0.98)',
    borderColor: '#C9D1D8',
    borderWidth: 1,
    padding: [8, 12],
    extraCssText: 'box-shadow: 0 4px 16px rgba(18, 59, 93, 0.1); border-radius: 8px;',
    formatter: params => {
        const d = params[0].data || {};
        return `
            <div class="font-bold text-primary-strong mb-1.5 text-xs pb-1 border-b border-slate-100 flex items-center justify-between gap-4">
                <span>✈️ ${params[0].name}</span>
                <span class="font-mono text-[10px] text-positive font-bold">${d.yoy || ''} YoY</span>
            </div>
            <div class="space-y-0.5 text-xs">
                <div class="flex justify-between gap-6"><span class="text-ink-muted">客运总收入:</span><span class="font-mono font-bold text-primary">¥${d.value || params[0].value} 亿元</span></div>
                <div class="flex justify-between gap-6"><span class="text-ink-muted">可用座公里 ASK:</span><span class="font-mono font-medium text-ink">${d.ask || '-'}</span></div>
                <div class="flex justify-between gap-6"><span class="text-ink-muted">收入客公里 RPK:</span><span class="font-mono font-medium text-ink">${d.rpk || '-'}</span></div>
                <div class="flex justify-between gap-6"><span class="text-ink-muted">综合客座率 PLF:</span><span class="font-mono font-bold text-positive">${d.plf || '-'}</span></div>
                <div class="flex justify-between gap-6"><span class="text-ink-muted">座公里收益 RASK:</span><span class="font-mono font-bold text-ink">${d.rask || '-'}</span></div>
                <div class="flex justify-between gap-6"><span class="text-ink-muted">航班正常率 OTP:</span><span class="font-mono font-medium text-ink">${d.otp || '-'}</span></div>
            </div>
        `;
    }
}
```

---

## 4. 纯粹字体排版层级与“去竖条”铁律 (Pure Typographic Hierarchy)

> [!IMPORTANT]
> **严禁在正式报告的标题左侧添加任何粗竖线/竖条颜色修饰（如 `border-l-4`, `border-l-primary`）**。
> 咨询级高管排版必须依靠纯粹的**字体粗细、字号与字偶距层级（Typographic Hierarchy）**来构建视觉结构：

```html
<!-- 正确示范：纯粹优雅的高管标题排版结构 -->
<div class="space-y-1">
    <div class="text-[11px] font-bold text-primary tracking-widest uppercase">EVIDENCE CHAIN · 核心证据链</div>
    <h2 class="text-base md:text-lg font-bold text-primary-strong tracking-tight">季度规模增长与大区横向透视</h2>
    <p class="text-xs text-ink-muted leading-relaxed">依托双轴复合走势与垂直柱状对比，研判业务大盘增速拐点与大区贡献极差</p>
</div>
```

---

## 5. 高密度数据表格排版与数值对齐准则 (Data Table Standards)

1. **三向对齐法则**：
   - **文本字段严格靠左 (`text-left`)**：如航线代码、起降城市对、责任机长、所属基地；
   - **数值/金额严格靠右 (`text-right`)**：如收入、班次、客座率、RASK、CASK；
   - **评级/状态徽章严格居中 (`text-center`)**：如 S/A/B 级徽章、预算达成进度条。
2. **等宽数字与千分位规范**：
   - 所有数值必须声明 `font-mono` 或 `tabular-nums`，确保小数点与纵向对齐；
   - 金额大于 1 亿使用 `¥X.XX 亿`，小于 1 亿使用 `¥X,XXX 万`；
   - 百分比保留 1 位小数（如 `86.8%`），座公里 RASK/CASK 保留 4 位小数（如 `¥0.5420`）。
3. **HTML5 原生拖拽排序列 (Drag & Drop)**：
   - 自定义列抽屉中支持鼠标拖拽条目重排表格列，零页面刷新。

---

## 6. 响应式与视口约束规范 (Responsive & Viewport Constraints)

- **页面容器最大宽度**：`max-w-[1600px] mx-auto`（确保在 2K / 4K / 超宽带鱼屏上不发散失焦）；
- **单图卡片最小呼吸宽度**：`min-width: 580px`（确保双列网格下坐标轴与图例文本 100% 舒展）；
- **吸顶磨砂玻璃筛选栏**：必须配置 `position: sticky; top: 0; z-index: 40; backdrop-filter: blur(12px);`，向下滚动时无缝吸附；
- **全屏沉浸研判**：卡片全屏时高度自适应 `calc(100vh - 120px)`，监听 `ESC` 键平滑退出并自动触发 `inst.resize()`。

---

## 🚫 反模式与绝对禁止清单 (Anti-Patterns)

- ❌ **严禁生成静态假数据/假 SVG 微图**：所有 Sparkline 与 Gauge 必须由 ECharts 实例动态渲染；
- ❌ **严禁在双 Y 轴图表中将图例放置在右上角**；
- ❌ **严禁原生 Select 箭头与文字堆叠**：必须采用物理隔离的自定义 Trigger 按钮；
- ❌ **严禁 CSV 导出中文乱码**：必须在 CSV 内容头部注入 `\uFEFF` UTF-8 BOM 字符；
- ❌ **严禁标题左侧添加粗竖条色块 (`border-l-4`)**。
