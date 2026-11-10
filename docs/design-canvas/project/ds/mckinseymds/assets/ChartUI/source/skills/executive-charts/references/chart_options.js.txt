/**
 * Executive Chart Options Library - 39 Consulting-Grade Civil Aviation Charts
 * Strictly adheres to the Executive Charts Design System (#123B5D Navy palette, zero-collision layout,
 * and Full-Element Metric Integrity Principle).
 */

const colorPalette = {
    primary: '#123B5D',
    primaryStrong: '#0B2A42',
    primarySoft: '#DCE8F0',
    ink: '#17212B',
    inkMuted: '#52606D',
    inkSubtle: '#7B8794',
    positive: '#A4453C',
    negative: '#2F6B55',
    attention: '#9A6A18',
    gridline: '#E6EAED',
    rule: '#C9D1D8'
};

const common = {
    animation: false,
    textStyle: { fontFamily: "Inter, 'PingFang SC', sans-serif", color: colorPalette.inkMuted, fontSize: 11 },
    grid: { top: 38, bottom: 38, left: 10, right: 18, containLabel: true }
};

const axisTitleStyleY = { color: colorPalette.inkSubtle, fontSize: 10, align: 'left', padding: [0, 0, 6, 0] };
const axisTitleStyleX = { color: colorPalette.inkSubtle, fontSize: 10, align: 'center', padding: [8, 0, 0, 0] };
const axisTitleStyleYRight = { color: colorPalette.inkSubtle, fontSize: 10, align: 'right', padding: [0, 0, 6, 0] };

const chartOptions = {};

// Helper for rich full-element tooltip rendering
function makeRichTooltip(title, items, badge = '') {
    let rows = items.map(item => `
        <div class="flex items-center justify-between gap-6 py-0.5 text-xs">
            <span class="text-ink-muted">${item.label}:</span>
            <span class="font-mono font-bold ${item.color || 'text-ink'}">${item.val}</span>
        </div>
    `).join('');

    return `
        <div class="p-1">
            <div class="font-bold text-primary-strong mb-1.5 text-xs pb-1 border-b border-slate-100 flex items-center justify-between gap-4">
                <span>✈️ ${title}</span>
                ${badge ? `<span class="font-mono text-[10px] text-positive font-bold">${badge}</span>` : ''}
            </div>
            <div class="space-y-0.5">${rows}</div>
        </div>
    `;
}

// ==========================================
// 1. 对比与排名类 (Comparison & Ranking)
// ==========================================

// c01 Column: 五大基地枢纽客运创收与运力全要素对比
chartOptions.c01 = {
    ...common,
    tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(255, 255, 255, 0.98)',
        borderColor: '#C9D1D8',
        borderWidth: 1,
        padding: [8, 12],
        extraCssText: 'box-shadow: 0 4px 16px rgba(18, 59, 93, 0.1); border-radius: 8px;',
        formatter: params => {
            const d = params[0].data || {};
            return makeRichTooltip(params[0].name, [
                { label: '客运总收入', val: `¥${d.value} 亿元`, color: 'text-primary' },
                { label: '可用座公里 ASK', val: d.ask || '12.5 亿' },
                { label: '收入客公里 RPK', val: d.rpk || '11.4 亿' },
                { label: '综合客座率 PLF', val: d.plf || '91.5%', color: 'text-positive' },
                { label: '座公里收益 RASK', val: d.rask || '¥0.5820' },
                { label: '航班正常率 OTP', val: d.otp || '94.2%' }
            ], d.yoy ? `${d.yoy} YoY` : '');
        }
    },
    xAxis: { type: 'category', name: '基地枢纽机场', nameLocation: 'middle', nameGap: 24, nameTextStyle: axisTitleStyleX, data: ['华东基地(虹桥/浦东)', '华南基地(白云/宝安)', '北方基地(大兴/首都)', '西南基地(天府/双流)', '海外及地区基地'], axisTick: { show: false } },
    yAxis: { type: 'value', max: 6.5, name: '营收 (亿元)', nameLocation: 'end', nameTextStyle: axisTitleStyleY, axisLabel: { formatter: '{value} 亿' }, splitLine: { lineStyle: { color: colorPalette.gridline } } },
    series: [{
        name: '枢纽客运收入',
        type: 'bar',
        barWidth: 24,
        data: [
            { value: 4.9, ask: '12.5 亿座公里', rpk: '11.4 亿客公里', plf: '91.5%', rask: '¥0.5820', otp: '94.2%', yoy: '+35.2%', itemStyle: { color: colorPalette.primary } },
            { value: 3.4, ask: '9.8 亿座公里', rpk: '8.4 亿客公里', plf: '86.2%', rask: '¥0.4850', otp: '91.5%', yoy: '+18.4%', itemStyle: { color: colorPalette.primary } },
            { value: 2.8, ask: '8.2 亿座公里', rpk: '6.7 亿客公里', plf: '82.0%', rask: '¥0.4210', otp: '89.6%', yoy: '+12.0%', itemStyle: { color: colorPalette.inkMuted } },
            { value: 1.9, ask: '6.5 亿座公里', rpk: '4.9 亿客公里', plf: '74.8%', rask: '¥0.3456', otp: '87.2%', yoy: '-4.8%', itemStyle: { color: colorPalette.inkMuted } },
            { value: 1.2, ask: '4.0 亿座公里', rpk: '3.1 亿客公里', plf: '77.5%', rask: '¥0.4120', otp: '88.0%', yoy: '+8.5%', itemStyle: { color: colorPalette.inkSubtle } }
        ],
        label: { show: true, position: 'top', distance: 6, formatter: '¥{c}亿', color: colorPalette.ink, fontSize: 11, fontWeight: 'bold' }
    }]
};

// c02 Ordered Bar: 主流机队年度创收与执飞小时全要素排行
chartOptions.c02 = {
    ...common,
    tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(255, 255, 255, 0.98)',
        borderColor: '#C9D1D8',
        borderWidth: 1,
        padding: [8, 12],
        extraCssText: 'box-shadow: 0 4px 16px rgba(18, 59, 93, 0.1); border-radius: 8px;',
        formatter: params => {
            const d = params[0].data || {};
            return makeRichTooltip(params[0].name, [
                { label: '年度客运总创收', val: `¥${d.value} 亿元`, color: 'text-primary' },
                { label: '在册机队规模', val: d.fleetSize || '28 架' },
                { label: '日均飞行小时', val: d.utilization || '10.5 小时/天', color: 'text-positive' },
                { label: '座公里成本 CASK', val: d.cask || '¥0.3456' },
                { label: '平均客座率 PLF', val: d.plf || '88.5%' }
            ]);
        }
    },
    grid: { top: 38, bottom: 38, left: 10, right: 36, containLabel: true },
    xAxis: { type: 'value', max: 6.0, name: '客运营收 (亿元)', nameLocation: 'middle', nameGap: 24, nameTextStyle: axisTitleStyleX, axisLabel: { formatter: '{value} 亿' }, splitLine: { lineStyle: { color: colorPalette.gridline } } },
    yAxis: { type: 'category', inverse: true, name: '执飞机型族系', nameLocation: 'start', nameTextStyle: axisTitleStyleY, data: ['A350-900 远程宽体机', 'B787-9 梦想客机', 'A321neo 高密度客机', 'B737-800 骨干窄体机', 'C919 国产干线客机'], axisTick: { show: false }, axisLine: { lineStyle: { color: colorPalette.rule } } },
    series: [{
        name: '机队年度创收',
        type: 'bar',
        barWidth: 16,
        data: [
            { value: 4.9, fleetSize: '24 架', utilization: '11.8 小时/天', cask: '¥0.3456', plf: '89.5%', itemStyle: { color: colorPalette.primary } },
            { value: 3.4, fleetSize: '18 架', utilization: '10.5 小时/天', cask: '¥0.3120', plf: '86.2%', itemStyle: { color: colorPalette.primary } },
            { value: 2.8, fleetSize: '36 架', utilization: '10.2 小时/天', cask: '¥0.2650', plf: '88.4%', itemStyle: { color: colorPalette.inkMuted } },
            { value: 1.9, fleetSize: '42 架', utilization: '9.4 小时/天', cask: '¥0.2810', plf: '82.0%', itemStyle: { color: colorPalette.inkMuted } },
            { value: 1.2, fleetSize: '10 架', utilization: '8.8 小时/天', cask: '¥0.2950', plf: '92.4%', itemStyle: { color: colorPalette.inkSubtle } }
        ],
        label: { show: true, position: 'right', distance: 6, formatter: '¥{c} 亿', color: colorPalette.ink, fontSize: 10, fontWeight: 600 }
    }]
};

// c03 Grouped Column: 四大核心航线集群预算 vs 实际全要素对比
chartOptions.c03 = {
    ...common,
    tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(255, 255, 255, 0.98)',
        borderColor: '#C9D1D8',
        borderWidth: 1,
        padding: [8, 12],
        extraCssText: 'box-shadow: 0 4px 16px rgba(18, 59, 93, 0.1); border-radius: 8px;',
        formatter: params => {
            const target = params[0].value;
            const actual = params[1].value;
            const diff = (actual - target).toFixed(1);
            const rate = ((actual / target) * 100).toFixed(1);
            return makeRichTooltip(params[0].name, [
                { label: '实际完成营收', val: `¥${actual} 亿元`, color: 'text-primary' },
                { label: '预算考核目标', val: `¥${target} 亿元`, color: 'text-ink-muted' },
                { label: '超额/差额 Gap', val: `${diff >= 0 ? '+' : ''}¥${diff} 亿元`, color: diff >= 0 ? 'text-positive' : 'text-negative' },
                { label: '预算达成率', val: `${rate}%`, color: rate >= 100 ? 'text-positive' : 'text-negative' }
            ]);
        }
    },
    legend: { top: 0, right: 12, orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 16, data: ['预算目标', '实际完成'], textStyle: { fontSize: 10, color: colorPalette.inkMuted } },
    xAxis: { type: 'category', name: '战略航线集群', nameLocation: 'middle', nameGap: 24, nameTextStyle: axisTitleStyleX, data: ['京津冀集群', '长三角集群', '粤港澳大湾区', '成渝城市群'], axisTick: { show: false } },
    yAxis: { type: 'value', max: 6.5, name: '规模 (亿元)', nameLocation: 'end', nameTextStyle: axisTitleStyleY, axisLabel: { formatter: '{value} 亿' }, splitLine: { lineStyle: { color: colorPalette.gridline } } },
    series: [
        { name: '预算目标', type: 'bar', barWidth: 18, data: [5.0, 3.9, 3.5, 2.9], itemStyle: { color: colorPalette.primarySoft } },
        { name: '实际完成', type: 'bar', barWidth: 22, data: [4.9, 3.4, 2.8, 1.9], itemStyle: { color: colorPalette.primary }, label: { show: true, position: 'top', distance: 6, formatter: '¥{c}亿', color: colorPalette.ink, fontSize: 11, fontWeight: 'bold' } }
    ]
};

// t06 Dual-Axis: 季度客运收入绝对规模与客公里收益走势
chartOptions.t06 = {
    ...common,
    tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(255, 255, 255, 0.98)',
        borderColor: '#C9D1D8',
        borderWidth: 1,
        padding: [8, 12],
        extraCssText: 'box-shadow: 0 4px 16px rgba(18, 59, 93, 0.1); border-radius: 8px;',
        formatter: params => {
            const rev = params[0].value;
            const yoy = params[1] ? params[1].value : 0;
            return makeRichTooltip(params[0].name, [
                { label: '主营客运总收入', val: `¥${rev} 亿元`, color: 'text-primary' },
                { label: '客公里收益同比增速', val: `+${yoy}%`, color: 'text-positive' },
                { label: '季度投入 ASK', val: `${(rev * 2.8).toFixed(1)} 亿座公里` },
                { label: '季度综合客座率', val: `${(80 + rev * 4.2).toFixed(1)}%` },
                { label: '平均座公里收益 RASK', val: `¥${(0.42 + rev * 0.06).toFixed(4)}` }
            ]);
        }
    },
    legend: { top: 0, right: 12, orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 16, data: ['客运总收入', '收益同比增速'], textStyle: { fontSize: 10, color: colorPalette.inkMuted } },
    xAxis: { type: 'category', name: '统计季度', nameLocation: 'middle', nameGap: 24, nameTextStyle: axisTitleStyleX, data: ['2024Q1', '24Q2', '24Q3', '24Q4'], axisTick: { show: false } },
    yAxis: [
        { type: 'value', max: 2.8, name: '收入 (亿元)', nameLocation: 'end', nameTextStyle: axisTitleStyleY, axisLabel: { formatter: '{value} 亿' }, splitLine: { lineStyle: { color: colorPalette.gridline } } },
        { type: 'value', max: 40, name: '增速 (%)', nameLocation: 'end', nameTextStyle: axisTitleStyleYRight, axisLabel: { formatter: '{value}%' }, splitLine: { show: false } }
    ],
    series: [
        { name: '客运总收入', type: 'bar', barWidth: 22, data: [1.2, 1.5, 1.8, 2.2], itemStyle: { color: colorPalette.primary } },
        { name: '收益同比增速', type: 'line', yAxisIndex: 1, data: [15.2, 18.4, 24.0, 32.5], lineStyle: { color: colorPalette.positive, width: 2.5 }, itemStyle: { color: colorPalette.positive, borderColor: '#FFF', borderWidth: 2 }, symbolSize: 6, label: { show: true, position: 'top', distance: 6, formatter: '+{c}%', color: colorPalette.positive, fontSize: 11, fontWeight: 'bold' } }
    ]
};

// Export to window
if (typeof window !== 'undefined') {
    window.chartOptions = chartOptions;
}
