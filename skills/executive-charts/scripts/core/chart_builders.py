# Python file exporting JavaScript string definitions for charts with dataZoom support

CHARTS_JS_DEFINITIONS = {
    # 1. t06 Dual-Axis (Quarterly & Monthly) Clean Layout
    "t06": """{
        id: 'chart-t06',
        code: 't06',
        title: '季度客运总收入与客公里收益走势',
        subtitle: '按季度/月度追踪民航主营客运收入绝对规模与客公里收益变动率',
        hasGranularity: true,
        defaultGranularity: 'month',
        explainKey: 't06',
        data: {
            month: {
                categories: ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'],
                revenue: [0.38, 0.42, 0.40, 0.45, 0.52, 0.53, 0.58, 0.60, 0.62, 0.70, 0.72, 0.78],
                yieldGrowth: [12.0, 14.5, 13.8, 16.2, 18.0, 19.5, 22.0, 24.5, 25.0, 28.2, 30.5, 32.5]
            },
            quarter: {
                categories: ['2024Q1', '24Q2', '24Q3', '24Q4'],
                revenue: [1.2, 1.5, 1.8, 2.2],
                yieldGrowth: [15.2, 18.4, 24.0, 32.5]
            }
        },
        optionBuilder: (d, gran, tokens, cfg = {}) => {
            const cur = d[gran] || d.month;
            const presentation = cfg.presentation || {};
            const axisLabels = presentation.axisLabels || {};
            const seriesLabels = presentation.seriesLabels || ['主指标', '变化率'];
            const tooltipLabels = presentation.tooltipValueLabels || seriesLabels;
            const units = presentation.units || [cfg.unit || '', '%'];
            return {
                ...tokens.commonOption,
                tooltip: {
                    trigger: 'axis',
                    backgroundColor: 'rgba(255, 255, 255, 0.98)',
                    borderColor: tokens.palette.rule,
                    borderWidth: 1,
                    padding: [8, 12],
                    extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                    formatter: params => {
                        let res = `<div class="font-bold text-primary-strong mb-1">${params[0].name}</div>`;
                        res += `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">${tooltipLabels[0]}:</span><span class="font-mono font-bold text-ink">${params[0].value}${units[0] ? ` ${units[0]}` : ''}</span></div>`;
                        if (params[1]) {
                            res += `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">${tooltipLabels[1]}:</span><span class="font-mono font-bold text-positive">${params[1].value}${units[1] ? ` ${units[1]}` : ''}</span></div>`;
                        }
                        return res;
                    }
                },
                legend: { top: 0, left: 'center', orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 20, data: seriesLabels, textStyle: { fontSize: 10, color: tokens.palette.inkMuted } },
                xAxis: { type: 'category', name: axisLabels.x || '周期', nameLocation: 'middle', nameGap: 20, nameTextStyle: tokens.axisTitleStyleX, data: cur.categories, axisTick: { show: false } },
                yAxis: [
                    { type: 'value', name: axisLabels.leftY || seriesLabels[0], nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: value => `${value}${units[0] ? ` ${units[0]}` : ''}` }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
                    { type: 'value', name: axisLabels.rightY || seriesLabels[1], nameLocation: 'end', nameTextStyle: { color: tokens.palette.inkSubtle, fontSize: 10, align: 'right', padding: [0, 0, 6, 0] }, axisLabel: { formatter: value => `${value}${units[1] || ''}` }, splitLine: { show: false } }
                ],
                series: [
                    { name: seriesLabels[0], type: 'bar', barWidth: gran === 'month' ? 14 : 26, data: cur.revenue, itemStyle: { color: tokens.palette.primary } },
                    { name: seriesLabels[1], type: 'line', yAxisIndex: 1, data: cur.yieldGrowth, lineStyle: { color: tokens.palette.positive, width: 2.5 }, itemStyle: { color: tokens.palette.positive, borderColor: '#FFF', borderWidth: 2 }, symbolSize: 6, label: { show: true, position: 'top', distance: 6, formatter: params => params.value == null ? '—' : `${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(params.value)}${units[1] || ''}`, color: tokens.palette.positive, fontSize: 10, fontWeight: 'bold' } }
                ]
            };
        },
        tableDataExtractor: (d, gran, cfg = {}) => {
            const cur = d[gran] || d.month;
            const presentation = cfg.presentation || {};
            const axisLabels = presentation.axisLabels || {};
            const seriesLabels = presentation.seriesLabels || ['主指标', '变化率'];
            const units = presentation.units || [cfg.unit || '', '%'];
            return {
                headers: presentation.tableHeaders || [axisLabels.x || '周期', `${seriesLabels[0]}${units[0] ? ` (${units[0]})` : ''}`, `${seriesLabels[1]}${units[1] ? ` (${units[1]})` : ''}`],
                rows: cur.categories.map((c, i) => [c, `${cur.revenue[i]}${units[0] ? ` ${units[0]}` : ''}`, `${cur.yieldGrowth[i]}${units[1] ? ` ${units[1]}` : ''}`])
            };
        }
    }""",

    # 2. c01 Column (5 categories, clean layout without dataZoom)
    "c01": """{
        id: 'chart-c01',
        code: 'c01',
        title: '全国各大基地枢纽机场营收贡献对比',
        subtitle: '衡量全国五大核心基地枢纽当期客运收入贡献与规模差异',
        explainKey: 'c01',
        data: {
            categories: ['华东基地', '华南基地', '北方基地', '西南基地', '海外基地'],
            values: [4.9, 3.4, 2.8, 1.9, 1.2]
        },
        optionBuilder: (d, gran, tokens, cfg = {}) => {
            const presentation = cfg.presentation || {};
            const axisLabels = presentation.axisLabels || {};
            const seriesLabel = (presentation.seriesLabels || ['数值'])[0];
            const tooltipLabel = (presentation.tooltipValueLabels || [seriesLabel])[0];
            const unit = (presentation.units || [cfg.unit || ''])[0];
            const yDomain = (presentation.domains || {}).y || {};
            return ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${params[0].name}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">${tooltipLabel}:</span><span class="font-mono font-bold text-primary">${params[0].value}${unit ? ` ${unit}` : ''}</span></div>`
            },
            xAxis: { type: 'category', name: axisLabels.x || '类别', nameLocation: 'middle', nameGap: 20, nameTextStyle: tokens.axisTitleStyleX, data: d.categories, axisTick: { show: false } },
            yAxis: { type: 'value', ...yDomain, name: axisLabels.y || `${seriesLabel}${unit ? ` (${unit})` : ''}`, nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: value => `${value}${unit ? ` ${unit}` : ''}` }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [{ name: seriesLabel, type: 'bar', barWidth: 26, data: d.values, itemStyle: { color: tokens.palette.primary }, label: { show: true, position: 'top', distance: 6, formatter: params => `${params.value}${unit ? ` ${unit}` : ''}`, color: tokens.palette.ink, fontSize: 11, fontWeight: 'bold' } }]
        });
        },
        tableDataExtractor: (d, gran, cfg = {}) => {
            const presentation = cfg.presentation || {};
            const axisLabels = presentation.axisLabels || {};
            const seriesLabel = (presentation.seriesLabels || ['数值'])[0];
            const unit = (presentation.units || [cfg.unit || ''])[0];
            return {
                headers: presentation.tableHeaders || [axisLabels.x || '类别', `${seriesLabel}${unit ? ` (${unit})` : ''}`],
                rows: d.categories.map((c, i) => [c, `${d.values[i]}${unit ? ` ${unit}` : ''}`])
            };
        }
    }""",

    # 3. c02 Ordered Bar (6 categories, clean layout without dataZoom)
    "c02": """{
        id: 'chart-c02',
        code: 'c02',
        title: '主流客运机型机队年度创收排行',
        subtitle: '评估远程宽体客机与主力窄体机队的年度创收顺位与效能',
        explainKey: 'c02',
        data: {
            categories: ['A350-900', 'B787-9', 'A321neo', 'B737-800', 'C919', 'ARJ21'],
            values: [4.9, 3.4, 2.8, 1.9, 1.5, 0.8]
        },
        optionBuilder: (d, gran, tokens, cfg = {}) => {
          const presentation = cfg.presentation || {};
          const axisLabels = presentation.axisLabels || {};
          const seriesLabel = (presentation.seriesLabels || ['数值'])[0];
          const tooltipLabel = (presentation.tooltipValueLabels || [seriesLabel])[0];
          const unit = (presentation.units || [cfg.unit || ''])[0];
          return ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${params[0].name}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">${tooltipLabel}:</span><span class="font-mono font-bold text-primary">${params[0].value}${unit ? ` ${unit}` : ''}</span></div>`
            },
            grid: { top: 38, bottom: 38, left: 10, right: 25, containLabel: true },
            xAxis: { type: 'value', name: axisLabels.x || `${seriesLabel}${unit ? ` (${unit})` : ''}`, nameLocation: 'middle', nameGap: 24, nameTextStyle: tokens.axisTitleStyleX, axisLabel: { formatter: value => `${value}${unit ? ` ${unit}` : ''}` }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            yAxis: { type: 'category', inverse: true, name: axisLabels.y || '类别', nameLocation: 'start', nameTextStyle: tokens.axisTitleStyleY, data: d.categories, axisTick: { show: false }, axisLine: { lineStyle: { color: '#94A3B8', width: 1.2 } }, axisLabel: { color: '#0F172A', fontSize: 12, fontWeight: 700 } },
            series: [{ name: seriesLabel, type: 'bar', barWidth: 18, data: d.values, itemStyle: { color: tokens.palette.primary }, label: { show: true, position: 'right', distance: 6, formatter: params => `${params.value}${unit ? ` ${unit}` : ''}`, color: tokens.palette.ink, fontSize: 10, fontWeight: 600 } }]
        });
        },
        tableDataExtractor: (d, gran, cfg = {}) => {
            const presentation = cfg.presentation || {};
            const axisLabels = presentation.axisLabels || {};
            const seriesLabel = (presentation.seriesLabels || ['数值'])[0];
            const unit = (presentation.units || [cfg.unit || ''])[0];
            return {
                headers: presentation.tableHeaders || [axisLabels.y || '类别', `${seriesLabel}${unit ? ` (${unit})` : ''}`],
                rows: d.categories.map((c, i) => [c, `${d.values[i]}${unit ? ` ${unit}` : ''}`])
            };
        }
    }""",

    # 4. r01 BCG Quadrant Clean
    "r01": """{
        id: 'chart-r01',
        code: 'r01',
        title: '航线网络战略四象限增长与收益矩阵',
        subtitle: '按客座率增速与座公里利润率定位明星快线、现金牛与待优化航线',
        explainKey: 'r01',
        data: {
            routes: [
                [35.2, 68.5, '京沪黄金快线'],
                [18.4, 62.0, '沪深商务快线'],
                [12.0, 54.2, '京广商务干线'],
                [-4.8, 42.0, '蓉京高原干线'],
                [22.5, 48.0, '沪蓉骨干快线'],
                [8.5, 71.0, '广深通勤快线']
            ]
        },
        optionBuilder: (d, gran, tokens, cfg = {}) => {
            const presentation = cfg.presentation || {};
            const axisLabels = presentation.axisLabels || {};
            const tooltipLabels = presentation.tooltipValueLabels || [axisLabels.x || 'X 值', axisLabels.y || 'Y 值'];
            const seriesLabel = (presentation.seriesLabels || ['数据点'])[0];
            const units = presentation.units || ['', ''];
            const thresholds = presentation.thresholds || { x: 0, y: 0 };
            const quadrant = (x, y) => x >= thresholds.x
                ? (y >= thresholds.y ? '第一象限' : '第四象限')
                : (y >= thresholds.y ? '第二象限' : '第三象限');
            return ({
            ...tokens.commonOption,
            tooltip: {
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${params.data[2]}</div><div class="space-y-0.5"><div class="flex justify-between gap-4"><span class="text-ink-muted">${tooltipLabels[0]}:</span><span class="font-mono font-bold text-positive">${params.data[0]}${units[0] ? ` ${units[0]}` : ''}</span></div><div class="flex justify-between gap-4"><span class="text-ink-muted">${tooltipLabels[1]}:</span><span class="font-mono font-bold text-primary">${params.data[1]}${units[1] ? ` ${units[1]}` : ''}</span></div></div>`
            },
            xAxis: { type: 'value', name: axisLabels.x || 'X 轴', nameLocation: 'middle', nameGap: 24, nameTextStyle: tokens.axisTitleStyleX, axisLabel: { formatter: value => `${value}${units[0] || ''}` }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            yAxis: { type: 'value', name: axisLabels.y || 'Y 轴', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: value => `${value}${units[1] || ''}` }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [{
                name: seriesLabel,
                type: 'scatter',
                symbolSize: 14,
                itemStyle: { color: tokens.palette.primary, borderColor: '#FFF', borderWidth: 2 },
                data: d.routes,
                label: { show: true, position: 'top', formatter: params => params.data[2], color: tokens.palette.ink, fontSize: 10, fontWeight: 600 },
                markLine: {
                    silent: true,
                    symbol: 'none',
                    lineStyle: { type: 'dashed', color: tokens.palette.rule, width: 1 },
                    data: [{ xAxis: thresholds.x }, { yAxis: thresholds.y }]
                }
            }]
        });
        },
        tableDataExtractor: (d, gran, cfg = {}) => {
            const presentation = cfg.presentation || {};
            const axisLabels = presentation.axisLabels || {};
            const units = presentation.units || ['', ''];
            const thresholds = presentation.thresholds || { x: 0, y: 0 };
            const quadrant = (x, y) => x >= thresholds.x
                ? (y >= thresholds.y ? '第一象限' : '第四象限')
                : (y >= thresholds.y ? '第二象限' : '第三象限');
            return {
                headers: presentation.tableHeaders || ['对象', axisLabels.x || 'X 值', axisLabels.y || 'Y 值', '象限'],
                rows: d.routes.map(r => [r[2], `${r[0]}${units[0] ? ` ${units[0]}` : ''}`, `${r[1]}${units[1] ? ` ${units[1]}` : ''}`, quadrant(r[0], r[1])])
            };
        }
    }""",

    # 5. fn01 Waterfall
    "fn01": """{
        id: 'chart-fn01',
        code: 'fn01',
        title: '主营客运边际利润形成与航油扣减归因',
        subtitle: '穿透客票基础毛利至当期航线边际利润 EBITDA 的核心归因链路',
        explainKey: 'fn01',
        data: {
            categories: ['基期客票毛利', '票价溢价拉动', '周转增长', '航油价格上涨', '当期EBITDA'],
            baseSteps: [0, 1.2, 1.6, 1.5, 0],
            deltas: [1.2, 0.4, 0.2, -0.3, 1.5],
            labels: ['¥1.2亿', '+¥0.4亿', '+¥0.2亿', '-¥0.3亿', '¥1.5亿']
        },
        optionBuilder: (d, gran, tokens, cfg = {}) => {
            const presentation = cfg.presentation || {};
            const axisLabels = presentation.axisLabels || {};
            const seriesLabel = (presentation.seriesLabels || ['变化值'])[0];
            const tooltipLabel = (presentation.tooltipValueLabels || [seriesLabel])[0];
            const unit = (presentation.units || [cfg.unit || ''])[0];
            const yDomain = (presentation.domains || {}).y || {};
            const formatDelta = value => `${value > 0 ? '+' : ''}${value}${unit ? ` ${unit}` : ''}`;
            return ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'shadow' },
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => {
                    const idx = params[0].dataIndex;
                    const val = d.deltas[idx];
                    return `<div class="font-bold text-primary-strong mb-1">${params[0].name}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">${tooltipLabel}:</span><span class="font-mono font-bold ${val >= 0 ? 'text-positive' : 'text-negative'}">${formatDelta(val)}</span></div>`;
                }
            },
            xAxis: { type: 'category', name: axisLabels.x || '类别', nameLocation: 'middle', nameGap: 20, nameTextStyle: tokens.axisTitleStyleX, data: d.categories, axisTick: { show: false } },
            yAxis: { type: 'value', ...yDomain, name: axisLabels.y || `${seriesLabel}${unit ? ` (${unit})` : ''}`, nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: value => `${value}${unit ? ` ${unit}` : ''}` }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [
                { type: 'bar', stack: 'total', itemStyle: { borderColor: 'transparent', color: 'transparent' }, data: d.baseSteps },
                {
                    type: 'bar',
                    stack: 'total',
                    barWidth: 22,
                    name: seriesLabel,
                    data: d.deltas.map((value, index) => ({ value: Math.abs(value), itemStyle: { color: index === 0 ? tokens.palette.primary : index === d.deltas.length - 1 ? tokens.palette.primaryStrong : value >= 0 ? tokens.palette.positive : tokens.palette.negative } })),
                    label: {
                        show: true,
                        position: 'top',
                        formatter: params => formatDelta(d.deltas[params.dataIndex]),
                        color: tokens.palette.ink,
                        fontSize: 10,
                        fontWeight: 600
                    }
                }
            ]
        });
        },
        tableDataExtractor: (d, gran, cfg = {}) => {
            const presentation = cfg.presentation || {};
            const axisLabels = presentation.axisLabels || {};
            const seriesLabel = (presentation.seriesLabels || ['变化值'])[0];
            const unit = (presentation.units || [cfg.unit || ''])[0];
            const labels = presentation.labels || {};
            return {
                headers: presentation.tableHeaders || [axisLabels.x || '类别', `${seriesLabel}${unit ? ` (${unit})` : ''}`, labels.directionHeader || '方向'],
                rows: d.categories.map((c, i) => [c, `${d.deltas[i] > 0 ? '+' : ''}${d.deltas[i]}${unit ? ` ${unit}` : ''}`, d.deltas[i] >= 0 ? (labels.positive || '正向') : (labels.negative || '负向')])
            };
        }
    }""",

    # 6. f01 Funnel
    "f01": """{
        id: 'chart-f01',
        code: 'f01',
        title: '航司官方渠道机票预订全链路流转漏斗',
        subtitle: '监控自航班检索至完成出票支付全链路转化率与留存',
        explainKey: 'f01',
        data: {
            stages: [
                { value: 5000, name: '航线航班检索', itemStyle: { color: '#0B2A42' } },
                { value: 2800, name: '舱位票价选择', itemStyle: { color: '#123B5D' } },
                { value: 1400, name: '乘机人信息录入', itemStyle: { color: '#3A5A78' } },
                { value: 600, name: '完成出票支付', itemStyle: { color: '#52606D' } }
            ]
        },
        optionBuilder: (d, gran, tokens, cfg = {}) => {
            const presentation = cfg.presentation || {};
            const seriesLabel = (presentation.seriesLabels || ['数值'])[0];
            const tooltipLabel = (presentation.tooltipValueLabels || [seriesLabel])[0];
            const unit = (presentation.units || [cfg.unit || ''])[0];
            return ({
            tooltip: {
                trigger: 'item',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${params.name}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">${tooltipLabel}:</span><span class="font-mono font-bold text-primary">${params.value}${unit ? ` ${unit}` : ''} (${params.percent}%)</span></div>`
            },
            series: [{
                type: 'funnel',
                left: '12%',
                width: '76%',
                top: 25,
                bottom: 25,
                gap: 3,
                name: seriesLabel,
                label: { show: true, position: 'inside', formatter: params => `${params.name}\\n${params.value}${unit ? ` ${unit}` : ''} (${params.percent}%)`, color: '#FFF', fontSize: 11, fontWeight: 600 },
                data: d.stages
            }]
        });
        },
        tableDataExtractor: (d, gran, cfg = {}) => {
            const presentation = cfg.presentation || {};
            const seriesLabel = (presentation.seriesLabels || ['数值'])[0];
            const unit = (presentation.units || [cfg.unit || ''])[0];
            const labels = presentation.labels || {};
            const baselineIndex = (presentation.derivedMetricRules || {}).baselineIndex || 0;
            const baseline = d.stages[baselineIndex] ? d.stages[baselineIndex].value : 0;
            return {
                headers: presentation.tableHeaders || [labels.stageHeader || '阶段', `${seriesLabel}${unit ? ` (${unit})` : ''}`, labels.ratioHeader || '总体占比'],
                rows: d.stages.map(s => [s.name, `${s.value}${unit ? ` ${unit}` : ''}`, `${baseline ? ((s.value / baseline) * 100).toFixed(1) : '0.0'}%`])
            };
        }
    }""",

    # 7. fn03 Tornado
    "fn03": """{
        id: 'chart-fn03',
        code: 'fn03',
        title: '民航经营关键变量敏感性分析',
        subtitle: '测试平均票价、客座率、航油采购价与汇率变动对净利润的影响弹性',
        explainKey: 'fn03',
        data: {
            variables: ['客单票价 (+10%)', '综合客座率 (+5pp)', '航油采购价 (+10%)', '美元汇率 (+5%)'],
            negative: [-52, -38, -25, -12],
            positive: [52, 38, 25, 12]
        },
        optionBuilder: (d, gran, tokens, cfg = {}) => {
            const presentation = cfg.presentation || {};
            const axisLabels = presentation.axisLabels || {};
            const seriesLabels = presentation.seriesLabels || ['负向', '正向'];
            const tooltipLabels = presentation.tooltipValueLabels || seriesLabels;
            const unit = (presentation.units || [cfg.unit || ''])[0];
            const xDomain = (presentation.domains || {}).x || {};
            return ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'shadow' },
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => {
                    let res = `<div class="font-bold text-primary-strong mb-1">${params[0].name}</div>`;
                    params.forEach((p, index) => {
                        res += `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">${tooltipLabels[index] || p.seriesName}:</span><span class="font-mono font-bold text-primary">${p.value}${unit ? ` ${unit}` : ''}</span></div>`;
                    });
                    return res;
                }
            },
            legend: { top: 0, left: 'center', orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 20, data: seriesLabels, textStyle: { fontSize: 10, color: tokens.palette.inkMuted } },
            grid: { top: 38, bottom: 38, left: 10, right: 30, containLabel: true },
            xAxis: { type: 'value', ...xDomain, name: axisLabels.x || '数值', nameLocation: 'middle', nameGap: 24, nameTextStyle: tokens.axisTitleStyleX, axisLabel: { formatter: value => `${value}${unit ? ` ${unit}` : ''}` }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            yAxis: { type: 'category', name: axisLabels.y || '变量', nameLocation: 'start', nameTextStyle: tokens.axisTitleStyleY, data: d.variables, axisTick: { show: false }, axisLine: { lineStyle: { color: '#94A3B8', width: 1.2 } }, axisLabel: { color: '#0F172A', fontSize: 11, fontWeight: 700 } },
            series: [
                { name: seriesLabels[0], type: 'bar', stack: 'total', barWidth: 16, data: d.negative, itemStyle: { color: tokens.palette.negative }, label: { show: true, position: 'insideLeft', formatter: params => `${params.value}${unit ? ` ${unit}` : ''}`, color: '#FFF', fontSize: 10, fontWeight: 600 } },
                { name: seriesLabels[1], type: 'bar', stack: 'total', barWidth: 16, data: d.positive, itemStyle: { color: tokens.palette.positive }, label: { show: true, position: 'insideRight', formatter: params => `+${params.value}${unit ? ` ${unit}` : ''}`, color: '#FFF', fontSize: 10, fontWeight: 600 } }
            ]
        });
        },
        tableDataExtractor: (d, gran, cfg = {}) => {
            const presentation = cfg.presentation || {};
            const axisLabels = presentation.axisLabels || {};
            const seriesLabels = presentation.seriesLabels || ['负向', '正向'];
            const unit = (presentation.units || [cfg.unit || ''])[0];
            return {
                headers: presentation.tableHeaders || [axisLabels.y || '变量', `${seriesLabels[0]}${unit ? ` (${unit})` : ''}`, `${seriesLabels[1]}${unit ? ` (${unit})` : ''}`],
                rows: d.variables.map((v, i) => [v, `${d.negative[i]}${unit ? ` ${unit}` : ''}`, `+${d.positive[i]}${unit ? ` ${unit}` : ''}`])
            };
        }
    }"""
}
