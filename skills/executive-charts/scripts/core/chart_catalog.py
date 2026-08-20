# Complete chart builders dictionary for all 30+ charts across the 6 dashboard files

ALL_CHARTS = {
    # c08 Butterfly
    "c08": """{
        id: 'chart-c08',
        code: 'c08',
        title: '国内航线 vs 国际及地区航线主要基地客运规模对比',
        subtitle: '按大区基地维度对称呈现国内与国际航线客运收入分布',
        explainKey: 'c08',
        data: {
            categories: ['华东基地', '华南基地', '北方基地', '西南基地'],
            domestic: [4.9, 3.4, 2.8, 1.9],
            intl: [1.8, 1.2, 1.5, 0.6]
        },
        optionBuilder: (d, gran, tokens) => ({
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
                    params.forEach(p => {
                        res += `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">${p.seriesName}:</span><span class="font-mono font-bold text-primary">¥${Math.abs(p.value)} 亿元</span></div>`;
                    });
                    return res;
                }
            },
            legend: { top: 0, left: 'center', orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 20, data: ['国内航线', '国际及地区航线'], textStyle: { fontSize: 10, color: tokens.palette.inkMuted } },
            grid: [
                { top: 40, bottom: 38, left: 15, width: '42%', containLabel: true },
                { top: 40, bottom: 38, right: 15, width: '42%', containLabel: true }
            ],
            xAxis: [
                { gridIndex: 0, type: 'value', inverse: true, max: 6.0, axisLabel: { formatter: '¥{value}亿' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
                { gridIndex: 1, type: 'value', max: 3.0, axisLabel: { formatter: '¥{value}亿' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } }
            ],
            yAxis: [
                { gridIndex: 0, type: 'category', position: 'right', data: d.categories, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { show: true, color: '#0F172A', fontWeight: 700 } },
                { gridIndex: 1, type: 'category', position: 'left', data: d.categories, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { show: false } }
            ],
            series: [
                { name: '国内航线', type: 'bar', xAxisIndex: 0, yAxisIndex: 0, barMaxWidth: 26, barMinWidth: 4, data: d.domestic, itemStyle: { color: tokens.palette.primary }, label: { show: true, position: 'insideLeft', formatter: '¥{c}亿', color: '#FFF', fontSize: 10, fontWeight: 600 } },
                { name: '国际及地区航线', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, barMaxWidth: 26, barMinWidth: 4, data: d.intl, itemStyle: { color: tokens.palette.inkMuted }, label: { show: true, position: 'insideRight', formatter: '¥{c}亿', color: '#FFF', fontSize: 10, fontWeight: 600 } }
            ]
        }),
        tableDataExtractor: (d) => ({
            headers: ['基地枢纽', '国内航线营收 (亿元)', '国际航线营收 (亿元)', '国际化占比'],
            rows: d.categories.map((c, i) => [c, `¥${d.domestic[i]} 亿`, `¥${d.intl[i]} 亿`, `${((d.intl[i]/(d.domestic[i]+d.intl[i]))*100).toFixed(1)}%`])
        })
    }""",

    # c05 Lollipop (Clean without dataZoom)
    "c05": """{
        id: 'chart-c05',
        code: 'c05',
        title: '航司各乘机服务环节 NPS 满意度排行',
        subtitle: '对标呈现行李直挂、机上餐食、贵宾厅等环节满意度评分与顺位',
        explainKey: 'c05',
        data: {
            categories: ['行李直挂', '快速安检', '贵宾休息室', '机上餐食', '客舱Wi-Fi', '登机引导', '退改签响应'],
            scores: [94, 88, 82, 76, 71, 68, 65]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${params[0].name}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">NPS 满意度得分:</span><span class="font-mono font-bold text-primary">${params[0].value} 分</span></div>`
            },
            grid: { top: 38, bottom: 38, left: 10, right: 25, containLabel: true },
            xAxis: { type: 'value', min: 60, max: 100, name: '满意度 (分)', nameLocation: 'middle', nameGap: 24, nameTextStyle: tokens.axisTitleStyleX, axisLabel: { formatter: '{value}分' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            yAxis: { type: 'category', inverse: true, name: '服务触点', nameLocation: 'start', nameTextStyle: tokens.axisTitleStyleY, data: d.categories, axisTick: { show: false }, axisLine: { lineStyle: { color: '#94A3B8', width: 1.2 } }, axisLabel: { color: '#0F172A', fontSize: 12, fontWeight: 700 } },
            series: [
                { name: '满意度基准杆', type: 'bar', barWidth: 3, data: d.scores, itemStyle: { color: tokens.palette.primarySoft }, z: 1 },
                { name: 'NPS 满意度得分', type: 'scatter', symbolSize: 14, data: d.scores, itemStyle: { color: tokens.palette.primary, borderColor: '#FFF', borderWidth: 2 }, label: { show: true, position: 'right', distance: 6, formatter: '{c}分', color: tokens.palette.ink, fontSize: 10, fontWeight: 600 }, z: 2 }
            ]
        }),
        tableDataExtractor: (d) => ({
            headers: ['服务环节触点', 'NPS 满意度得分', '服务评级'],
            rows: d.categories.map((c, i) => [c, `${d.scores[i]} 分`, d.scores[i] >= 85 ? '标杆服务 (S)' : d.scores[i] >= 75 ? '优良服务 (A)' : '待优化 (B)'])
        })
    }""",

    # c07 Overlaid Bar (Clean without dataZoom)
    "c07": """{
        id: 'chart-c07',
        code: 'c07',
        title: '核心航线集群上年度同期 vs 当期运力投放对比',
        subtitle: '直观对比上一年度同期基期与当期实际完成运力与营收规模',
        explainKey: 'c07',
        data: {
            clusters: ['京津冀集群', '长三角集群', '粤港澳大湾区', '成渝城市群', '西北枢纽群', '东北走廊'],
            base2024: [3.8, 4.2, 3.0, 2.1, 1.8, 1.2],
            curr2025: [4.5, 5.2, 3.6, 2.6, 2.2, 1.5]
        },
        optionBuilder: (d, gran, tokens) => ({
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
                    res += `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">2024同期:</span><span class="font-mono font-bold text-ink-muted">¥${params[0].value} 亿</span></div>`;
                    res += `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">2025当期:</span><span class="font-mono font-bold text-primary">¥${params[1].value} 亿</span></div>`;
                    const diff = (params[1].value - params[0].value).toFixed(1);
                    res += `<div class="flex items-center justify-between gap-4 py-0.5 border-t border-slate-100 mt-1 pt-1"><span class="text-ink-muted">净增量:</span><span class="font-mono font-bold text-positive">+¥${diff} 亿</span></div>`;
                    return res;
                }
            },
            legend: { top: 0, right: 12, orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 14, data: ['2024同期', '2025当期'], textStyle: { fontSize: 10, color: tokens.palette.inkMuted } },
            xAxis: { type: 'category', data: d.clusters, axisTick: { show: false } },
            yAxis: { type: 'value', max: 6.0, name: '运力营收 (亿元)', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '{value} 亿' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [
                { name: '2024同期', type: 'bar', barWidth: 26, barGap: '-100%', data: d.base2024, itemStyle: { color: '#CBD5E1' } },
                { name: '2025当期', type: 'bar', barWidth: 16, data: d.curr2025, itemStyle: { color: tokens.palette.primary }, label: { show: true, position: 'top', distance: 6, formatter: '¥{c}亿', color: tokens.palette.ink, fontSize: 10, fontWeight: 600 } }
            ]
        }),
        tableDataExtractor: (d) => ({
            headers: ['航线集群', '2024同期 (亿元)', '2025当期 (亿元)', '净增额 (亿元)', '增长率'],
            rows: d.clusters.map((c, i) => [c, `¥${d.base2024[i]} 亿`, `¥${d.curr2025[i]} 亿`, `+¥${(d.curr2025[i]-d.base2024[i]).toFixed(1)} 亿`, `+${(((d.curr2025[i]-d.base2024[i])/d.base2024[i])*100).toFixed(1)}%`])
        })
    }""",

    # t01 Line Trend with dataZoom
    "t01": """{
        id: 'chart-t01',
        code: 't01',
        title: '民航旅客月度运输总周转量 RPK 走势',
        subtitle: '反映全年各月份旅客实际运输总周转量 RPK 的连续平滑演进轨迹',
        explainKey: 't01',
        data: {
            months: ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'],
            rpk: [142, 168, 155, 160, 185, 192, 220, 235, 198, 215, 170, 188]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${params[0].name} 旅客周转量</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">有效RPK:</span><span class="font-mono font-bold text-primary">${params[0].value} 亿客公里</span></div>`
            },
            xAxis: { type: 'category', data: d.months, axisTick: { show: false } },
            yAxis: { type: 'value', min: 100, max: 260, name: 'RPK (亿客公里)', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '{value}' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [{
                name: '旅客运输总周转量',
                type: 'line',
                smooth: true,
                data: d.rpk,
                lineStyle: { color: tokens.palette.primary, width: 2.5 },
                itemStyle: { color: tokens.palette.primary, borderColor: '#FFF', borderWidth: 2 },
                areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(18, 59, 93, 0.25)' }, { offset: 1, color: 'rgba(18, 59, 93, 0.01)' }]) }
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['月份', 'RPK周转量 (亿客公里)', '环比变动'],
            rows: d.months.map((m, i) => [m, `${d.rpk[i]} 亿客公里`, i === 0 ? '-' : `${d.rpk[i] >= d.rpk[i-1] ? '+' : ''}${(d.rpk[i]-d.rpk[i-1])} 亿`])
        })
    }""",

    # t03 Step Line
    "t03": """{
        id: 'chart-t03',
        code: 't03',
        title: '常旅客飞行航段与金银卡升级阶梯门槛',
        subtitle: '呈现常旅客飞行定级航段对应会员等级的阶梯升级门槛规则',
        explainKey: 't03',
        data: {
            segments: ['0-10段 (普卡)', '11-25段 (银卡)', '26-50段 (金卡)', '51-90段 (白金卡)', '90+段 (终身白金)'],
            rates: [0.18, 0.25, 0.32, 0.40, 0.45]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${params[0].name}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">积分兑换单价:</span><span class="font-mono font-bold text-primary">¥${params[0].value} / 航段</span></div>`
            },
            xAxis: { type: 'category', data: d.segments, axisTick: { show: false } },
            yAxis: { type: 'value', min: 0.15, max: 0.50, name: '积分兑换单价 (元/段)', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '¥{value}' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [{
                name: '阶梯回馈率',
                type: 'line',
                step: 'start',
                data: d.rates,
                lineStyle: { color: tokens.palette.primary, width: 2.5 },
                itemStyle: { color: tokens.palette.primary, borderColor: '#FFF', borderWidth: 2 }
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['定级航段阶梯', '会员等级', '单航段积分兑换率'],
            rows: d.segments.map((s, i) => [s.split(' ')[0], s.split(' ')[1].replace(/[()]/g, ''), `¥${d.rates[i]} / 段`])
        })
    }""",

    # k05 Solid Pie
    "k05": """{
        id: 'chart-k05',
        code: 'k05',
        title: '国内航线 vs 国际及地区航线收入占比',
        subtitle: '展示国内与国际航线在客运收入大盘中的份额结构占比',
        explainKey: 'k05',
        data: {
            shares: [
                { value: 72, name: '国内主营航线 (72%)', itemStyle: { color: '#123B5D' } },
                { value: 28, name: '国际及地区航线 (28%)', itemStyle: { color: '#94A3B8' } }
            ]
        },
        optionBuilder: (d, gran, tokens) => ({
            tooltip: {
                trigger: 'item',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: '{b}: {c}% 营收配比'
            },
            series: [{
                type: 'pie',
                radius: '65%',
                center: ['50%', '52%'],
                label: { show: true, position: 'inside', formatter: '{b}\\n{c}%', color: '#FFF', fontSize: 11, fontWeight: 600 },
                data: d.shares
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['市场航网类型', '客运收入配比', '年创收预估'],
            rows: d.shares.map(s => [s.name.split(' ')[0], `${s.value}%`, `¥${((s.value/100)*48.5).toFixed(1)} 亿`])
        })
    }""",

    # d02 Boxplot
    "d02": """{
        id: 'chart-d02',
        code: 'd02',
        title: '各大基地航线平均单座票价收益分布特征',
        subtitle: '呈现各大基地航线单座票价收益的极值、四分位数与中位数分布',
        explainKey: 'd02',
        data: {
            categories: ['华东基地', '华南基地', '北方基地', '西南基地'],
            boxData: [
                [320, 450, 580, 720, 950],
                [300, 420, 540, 680, 890],
                [280, 390, 510, 640, 820],
                [240, 350, 460, 590, 760]
            ]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'item',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => {
                    const v = params.value;
                    return `<div class="font-bold text-primary-strong mb-1">${params.name} 票价离散度</div><div class="space-y-0.5 text-xs"><div class="flex justify-between gap-4"><span class="text-ink-muted">最高单座:</span><span class="font-mono font-bold text-primary">¥${v[5]}</span></div><div class="flex justify-between gap-4"><span class="text-ink-muted">上四分位 (Q3):</span><span class="font-mono font-medium text-ink">¥${v[4]}</span></div><div class="flex justify-between gap-4"><span class="text-ink-muted">中位数 (Q2):</span><span class="font-mono font-bold text-positive">¥${v[3]}</span></div><div class="flex justify-between gap-4"><span class="text-ink-muted">下四分位 (Q1):</span><span class="font-mono font-medium text-ink">¥${v[2]}</span></div><div class="flex justify-between gap-4"><span class="text-ink-muted">最低单座:</span><span class="font-mono font-bold text-ink-muted">¥${v[1]}</span></div></div>`;
                }
            },
            xAxis: { type: 'category', data: d.categories, axisTick: { show: false } },
            yAxis: { type: 'value', min: 200, max: 1000, name: '单座收益 (元)', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '¥{value}' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [{
                name: '票价收益箱体',
                type: 'boxplot',
                data: d.boxData,
                itemStyle: { color: tokens.palette.primarySoft, borderColor: tokens.palette.primary, borderWidth: 1.5 }
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['基地枢纽', '最低单座 (元)', '中位数 (元)', '最高单座 (元)'],
            rows: d.categories.map((c, i) => [c, `¥${d.boxData[i][0]}`, `¥${d.boxData[i][2]}`, `¥${d.boxData[i][4]}`])
        })
    }""",

    # r03 Correlation Heatmap
    "r03": """{
        id: 'chart-r03',
        code: 'r03',
        title: '民航运营核心要素相关性系数矩阵',
        subtitle: '量化客座率、票价指数、日利用率、准点率与利润率的关联强度',
        explainKey: 'r03',
        data: {
            dimensions: ['客座率', '票价指数', '日利用率', '准点率', '利润率'],
            matrix: [
                [0, 0, 1.00], [0, 1, 0.45], [0, 2, 0.72], [0, 3, 0.58], [0, 4, 0.82],
                [1, 0, 0.45], [1, 1, 1.00], [1, 2, 0.38], [1, 3, 0.42], [1, 4, 0.88],
                [2, 0, 0.72], [2, 1, 0.38], [2, 2, 1.00], [2, 3, 0.65], [2, 4, 0.75],
                [3, 0, 0.58], [3, 1, 0.42], [3, 2, 0.65], [3, 3, 1.00], [3, 4, 0.68],
                [4, 0, 0.82], [4, 1, 0.88], [4, 2, 0.75], [4, 3, 0.68], [4, 4, 1.00]
            ]
        },
        optionBuilder: (d, gran, tokens) => ({
            tooltip: {
                position: 'top',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${d.dimensions[params.value[0]]} ✕ ${d.dimensions[params.value[1]]}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">皮尔逊相关系数:</span><span class="font-mono font-bold text-primary">${params.value[2].toFixed(2)}</span></div>`
            },
            grid: { top: 20, bottom: 38, left: 10, right: 18, containLabel: true },
            xAxis: { type: 'category', data: d.dimensions, axisTick: { show: false } },
            yAxis: { type: 'category', data: d.dimensions, axisTick: { show: false } },
            visualMap: { min: 0.3, max: 1.0, show: false, inRange: { color: ['#F0F5F9', '#8EA4B8', '#123B5D', '#0B2A42'] } },
            series: [{
                type: 'heatmap',
                data: d.matrix,
                label: { show: true, formatter: params => params.value[2].toFixed(2), color: '#FFFFFF', fontSize: 10, fontWeight: 600 },
                itemStyle: { borderColor: '#FFFFFF', borderWidth: 2 }
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['要素 A', '要素 B', '相关系数 (r)', '相关强度'],
            rows: [
                ['客座率', '利润率', '0.82', '强正相关 (极高联动)'],
                ['票价指数', '利润率', '0.88', '强正相关 (决定性拉动)'],
                ['日利用率', '客座率', '0.72', '中强正相关'],
                ['准点率', '利润率', '0.68', '中强正相关']
            ]
        })
    }""",

    # c03 Grouped Column (Clean without dataZoom)
    "c03": """{
        id: 'chart-c03',
        code: 'c03',
        title: '四大核心航线集群预算收入 vs 实际完成',
        subtitle: '对比各大航线集群年度预算配额与实际完成情况及超额缺口',
        explainKey: 'c03',
        data: {
            clusters: ['京津冀集群', '长三角集群', '粤港澳大湾区', '成渝城市群'],
            budget: [4.2, 4.8, 3.5, 2.5],
            actual: [4.5, 5.2, 3.6, 2.6]
        },
        optionBuilder: (d, gran, tokens) => ({
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
                    res += `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">预算配额:</span><span class="font-mono font-bold text-ink-muted">¥${params[0].value} 亿</span></div>`;
                    res += `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">实际创收:</span><span class="font-mono font-bold text-primary">¥${params[1].value} 亿</span></div>`;
                    const rate = ((params[1].value / params[0].value) * 100).toFixed(1);
                    res += `<div class="flex items-center justify-between gap-4 py-0.5 border-t border-slate-100 mt-1 pt-1"><span class="text-ink-muted">达成率:</span><span class="font-mono font-bold text-positive">${rate}%</span></div>`;
                    return res;
                }
            },
            legend: { top: 0, right: 12, orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 14, data: ['预算配额', '实际创收'], textStyle: { fontSize: 10, color: tokens.palette.inkMuted } },
            xAxis: { type: 'category', data: d.clusters, axisTick: { show: false } },
            yAxis: { type: 'value', max: 6.5, name: '客运规模 (亿元)', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '{value} 亿' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [
                { name: '预算配额', type: 'bar', barWidth: 16, data: d.budget, itemStyle: { color: tokens.palette.primarySoft } },
                { name: '实际创收', type: 'bar', barWidth: 16, data: d.actual, itemStyle: { color: tokens.palette.primary }, label: { show: true, position: 'top', distance: 6, formatter: '¥{c}亿', color: tokens.palette.ink, fontSize: 10, fontWeight: 600 } }
            ]
        }),
        tableDataExtractor: (d) => ({
            headers: ['航线集群', '预算配额 (亿元)', '实际创收 (亿元)', '超额收益 (亿元)', '达成率'],
            rows: d.clusters.map((c, i) => [c, `¥${d.budget[i]} 亿`, `¥${d.actual[i]} 亿`, `+¥${(d.actual[i]-d.budget[i]).toFixed(1)} 亿`, `${((d.actual[i]/d.budget[i])*100).toFixed(1)}%`])
        })
    }""",

    # fn02 Scissors
    "fn02": """{
        id: 'chart-fn02',
        code: 'fn02',
        title: '季度客运总收入与运营总成本盈亏演变',
        subtitle: '反映营业收入与运营总成本（航油/起降/折旧）的走势及盈亏平衡拐点',
        explainKey: 'fn02',
        data: {
            quarters: ['2024Q1', '24Q2', '24Q3', '24Q4'],
            revenue: [1.2, 1.5, 1.8, 2.3],
            cost: [1.3, 1.4, 1.5, 1.7]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => {
                    let res = `<div class="font-bold text-primary-strong mb-1">${params[0].name} 财务收支</div>`;
                    res += `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">客运总收入:</span><span class="font-mono font-bold text-primary">¥${params[0].value} 亿元</span></div>`;
                    res += `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">运营总成本:</span><span class="font-mono font-bold text-ink-muted">¥${params[1].value} 亿元</span></div>`;
                    const profit = (params[0].value - params[1].value).toFixed(1);
                    res += `<div class="flex items-center justify-between gap-4 py-0.5 border-t border-slate-100 mt-1 pt-1"><span class="text-ink-muted">净利润剪刀差:</span><span class="font-mono font-bold ${profit >= 0 ? 'text-positive' : 'text-negative'}">${profit >= 0 ? '+' : ''}¥${profit} 亿</span></div>`;
                    return res;
                }
            },
            legend: { top: 0, right: 12, orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 14, data: ['客运总收入', '运营总成本'], textStyle: { fontSize: 10, color: tokens.palette.inkMuted } },
            xAxis: { type: 'category', data: d.quarters, axisTick: { show: false } },
            yAxis: { type: 'value', max: 2.8, name: '金额 (亿元)', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '{value} 亿' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [
                { name: '客运总收入', type: 'line', data: d.revenue, lineStyle: { color: tokens.palette.primary, width: 2.5 }, itemStyle: { color: tokens.palette.primary, borderColor: '#FFF', borderWidth: 2 }, label: { show: true, position: 'top', formatter: '¥{c}亿', color: tokens.palette.ink, fontSize: 10, fontWeight: 600 } },
                { name: '运营总成本', type: 'line', data: d.cost, lineStyle: { color: tokens.palette.inkSubtle, width: 2, type: 'dashed' }, itemStyle: { color: tokens.palette.inkSubtle }, label: { show: true, position: 'bottom', formatter: '¥{c}亿', color: tokens.palette.inkMuted, fontSize: 10 } }
            ]
        }),
        tableDataExtractor: (d) => ({
            headers: ['季度', '客运总收入 (亿元)', '运营总成本 (亿元)', '当季净利润 (亿元)'],
            rows: d.quarters.map((q, i) => [q, `¥${d.revenue[i]} 亿`, `¥${d.cost[i]} 亿`, `${d.revenue[i] >= d.cost[i] ? '+' : ''}¥${(d.revenue[i]-d.cost[i]).toFixed(1)} 亿`])
        })
    }""",

    # f02 Sankey (Consultancy Grade Navy & Slate Tokens)
    "f02": """{
        id: 'chart-f02',
        code: 'f02',
        title: '客货运主营收入向成本与航油分流资金流向',
        subtitle: '清晰呈现客货运收入扣减航油、起降费与机组薪酬后转化为综合毛利',
        explainKey: 'f02',
        data: {
            nodes: [
                { name: '客运机票主收入', itemStyle: { color: '#0B2A42' } },
                { name: '货邮及辅营收入', itemStyle: { color: '#3A5A78' } },
                { name: '主营业务总营收', itemStyle: { color: '#123B5D' } },
                { name: '综合经营毛利', itemStyle: { color: '#1B4D75' } },
                { name: '航油采购成本', itemStyle: { color: '#52606D' } },
                { name: '机场起降与保障', itemStyle: { color: '#7B8794' } },
                { name: '机组薪酬与折旧', itemStyle: { color: '#94A3B8' } },
                { name: '企业所得税', itemStyle: { color: '#CBD5E1' } },
                { name: '航线净利润', itemStyle: { color: '#2F6B55' } }
            ],
            links: [
                { source: '客运机票主收入', target: '主营业务总营收', value: 10.5 },
                { source: '货邮及辅营收入', target: '主营业务总营收', value: 2.5 },
                { source: '主营业务总营收', target: '航油采购成本', value: 3.8 },
                { source: '主营业务总营收', target: '机场起降与保障', value: 2.2 },
                { source: '主营业务总营收', target: '机组薪酬与折旧', value: 1.5 },
                { source: '主营业务总营收', target: '综合经营毛利', value: 5.5 },
                { source: '综合经营毛利', target: '企业所得税', value: 1.2 },
                { source: '综合经营毛利', target: '航线净利润', value: 4.3 }
            ]
        },
        optionBuilder: (d, gran, tokens) => ({
            tooltip: {
                trigger: 'item',
                triggerOn: 'mousemove',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${params.data.source ? params.data.source + ' ➔ ' + params.data.target : params.name}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">流转资金:</span><span class="font-mono font-bold text-primary">${params.value || '-'} 亿元</span></div>`
            },
            series: [{
                type: 'sankey',
                left: '8%',
                right: '12%',
                top: 25,
                bottom: 25,
                nodeWidth: 16,
                nodeGap: 14,
                emphasis: { focus: 'adjacency' },
                data: d.nodes,
                links: d.links,
                lineStyle: { color: 'source', curveness: 0.5, opacity: 0.18 },
                label: { color: tokens.palette.ink, fontSize: 11, fontWeight: 700 }
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['资金流入源', '资金流向端', '金额体量 (亿元)'],
            rows: d.links.map(l => [l.source, l.target, `¥${l.value} 亿`])
        })
    }""",

    # c04 Diverging Bar
    "c04": """{
        id: 'chart-c04',
        code: 'c04',
        title: '各机队板块座公里收益相对行业基准偏离',
        subtitle: '以全行业统一座公里基准收益率为参考线，量化各机队的超额或滞后幅度',
        explainKey: 'c04',
        data: {
            fleets: ['远程宽体客机 (A350/B787)', '骨干窄体客机 (A321/B737)', '国产干支客机 (C919/ARJ21)', '全货机机队 (B777F)'],
            deviations: [18.2, 6.4, -5.8, -12.4]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => {
                    const val = params[0].value;
                    return `<div class="font-bold text-primary-strong mb-1">${params[0].name}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">基准偏离度:</span><span class="font-mono font-bold ${val >= 0 ? 'text-positive' : 'text-negative'}">${val >= 0 ? '+' : ''}${val}%</span></div>`;
                }
            },
            grid: { top: 38, bottom: 38, left: 10, right: 25, containLabel: true },
            xAxis: { type: 'value', min: -20, max: 25, name: '偏离度 (%)', nameLocation: 'middle', nameGap: 24, nameTextStyle: tokens.axisTitleStyleX, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            yAxis: { type: 'category', inverse: true, name: '机队板块', nameLocation: 'start', nameTextStyle: tokens.axisTitleStyleY, data: d.fleets, axisTick: { show: false }, axisLine: { lineStyle: { color: '#94A3B8', width: 1.2 } }, axisLabel: { color: '#0F172A', fontSize: 11, fontWeight: 700 } },
            series: [{
                name: '相对行业基准偏离',
                type: 'bar',
                barMaxWidth: 28,
                barMinWidth: 4,
                data: d.deviations.map(val => ({
                    value: val,
                    itemStyle: { color: val >= 0 ? tokens.palette.positive : tokens.palette.negative }
                })),
                label: { show: true, position: 'right', distance: 6, formatter: params => `${params.value >= 0 ? '+' : ''}${params.value}%`, color: tokens.palette.ink, fontSize: 10, fontWeight: 600 }
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['机队板块', '相对基准偏离度', '行业超额能力评估'],
            rows: d.fleets.map((f, i) => [f, `${d.deviations[i] >= 0 ? '+' : ''}${d.deviations[i]}%`, d.deviations[i] > 10 ? '显著超额 (Alpha)' : d.deviations[i] >= 0 ? '略高于行业' : '落后需改善'])
        })
    }""",

    # m03 Threshold Alert
    "m03": """{
        id: 'chart-m03',
        code: 'm03',
        title: '各机场地面服务与延误保障费用超支红线监控',
        subtitle: '监控各机场配餐、地面摆渡与延误改签安置费用并标识 5.0% 警戒红线',
        explainKey: 'm03',
        data: {
            airports: ['上海虹桥', '北京大兴', '广州白云', '成都天府', '深圳宝安'],
            overage: [6.8, 3.2, 5.4, 2.1, 7.5]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => {
                    const val = params[0].value;
                    return `<div class="font-bold text-primary-strong mb-1">${params[0].name} 地面保障</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">费用超支率:</span><span class="font-mono font-bold ${val > 5.0 ? 'text-positive' : 'text-negative'}">${val}% ${val > 5.0 ? '(超红线)' : '(合规)'}</span></div>`;
                }
            },
            xAxis: { type: 'category', data: d.airports, axisTick: { show: false } },
            yAxis: { type: 'value', max: 10.0, name: '超支率 (%)', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [{
                name: '地面费用超支率',
                type: 'bar',
                barMaxWidth: 36,
                barMinWidth: 6,
                data: d.overage.map(v => ({
                    value: v,
                    itemStyle: { color: v > 5.0 ? tokens.palette.positive : tokens.palette.primary }
                })),
                label: { show: true, position: 'top', distance: 6, formatter: '{c}%', color: tokens.palette.ink, fontSize: 10, fontWeight: 600 },
                markLine: {
                    symbol: 'none',
                    lineStyle: { type: 'dashed', color: tokens.palette.positive, width: 1.5 },
                    data: [{ yAxis: 5.0, label: { formatter: '  5% 预警红线', position: 'insideStartTop', color: tokens.palette.positive, fontSize: 10, fontWeight: 600, padding: [2, 6], backgroundColor: '#FFFFFF', borderColor: tokens.palette.positive, borderWidth: 1, borderRadius: 4 } }]
                }
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['机场港口', '超支率 (%)', '5% 红线状态'],
            rows: d.airports.map((a, i) => [a, `${d.overage[i]}%`, d.overage[i] > 5.0 ? '🔴 超出预警红线' : '🟢 预算范围内'])
        })
    }""",

    # fn04 Base=100
    "fn04": """{
        id: 'chart-fn04',
        code: 'fn04',
        title: '各大基地主营航线收入归一增长指数走势',
        subtitle: '消除基地体量差异，对比华东、华南、北方与西南基地主营航线的成长动能',
        explainKey: 'fn04',
        data: {
            nodes: ['24Q1 (基期)', '24Q2', '24Q3', '24Q4', '25Q1'],
            east: [100, 118, 142, 185, 210],
            south: [100, 112, 130, 160, 182],
            north: [100, 108, 120, 145, 162],
            west: [100, 105, 115, 132, 148]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;'
            },
            legend: { top: 0, right: 12, orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 12, data: ['华东基地', '华南基地', '北方基地', '西南基地'], textStyle: { fontSize: 10, color: tokens.palette.inkMuted } },
            xAxis: { type: 'category', data: d.nodes, axisTick: { show: false } },
            yAxis: { type: 'value', min: 80, max: 240, name: '增长指数 (Base=100)', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '{value}' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [
                { name: '华东基地', type: 'line', data: d.east, lineStyle: { color: tokens.palette.primary, width: 2.5 }, itemStyle: { color: tokens.palette.primary } },
                { name: '华南基地', type: 'line', data: d.south, lineStyle: { color: tokens.palette.positive, width: 2 }, itemStyle: { color: tokens.palette.positive } },
                { name: '北方基地', type: 'line', data: d.north, lineStyle: { color: tokens.palette.inkMuted, width: 1.8 }, itemStyle: { color: tokens.palette.inkMuted } },
                { name: '西南基地', type: 'line', data: d.west, lineStyle: { color: tokens.palette.inkSubtle, width: 1.5, type: 'dashed' }, itemStyle: { color: tokens.palette.inkSubtle } }
            ]
        }),
        tableDataExtractor: (d) => ({
            headers: ['报告周期', '华东 (虹桥/浦东)', '华南 (白云/宝安)', '北方 (大兴/首都)', '西南 (天府/双流)'],
            rows: d.nodes.map((n, i) => [n, `${d.east[i]} 指数`, `${d.south[i]} 指数`, `${d.north[i]} 指数`, `${d.west[i]} 指数`])
        })
    }""",

    # d01 Histogram (Clean without dataZoom)
    "d01": """{
        id: 'chart-d01',
        code: 'd01',
        title: '旅客平均机票购票金额频数分布',
        subtitle: '展示特价舱、标准经济舱、全价舱与两舱机票的购票频数与聚集分布',
        explainKey: 'd01',
        data: {
            brackets: ['¥300-600', '¥600-1000', '¥1000-1500', '¥1500-2200', '¥2200+'],
            counts: [120, 380, 490, 260, 95]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${params[0].name} 票价区间</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">购票频数:</span><span class="font-mono font-bold text-primary">${params[0].value} 万张</span></div>`
            },
            xAxis: { type: 'category', data: d.brackets, axisTick: { show: false } },
            yAxis: { type: 'value', max: 600, name: '出票量 (万张)', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '{value}万' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [{
                name: '出票频数',
                type: 'bar',
                barWidth: 26,
                data: d.counts,
                itemStyle: { color: tokens.palette.primary },
                label: { show: true, position: 'top', distance: 6, formatter: '{c}万', color: tokens.palette.ink, fontSize: 10, fontWeight: 600 }
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['票价区间', '出票量 (万张)', '出票占比'],
            rows: d.brackets.map((b, i) => [b, `${d.counts[i]} 万张`, `${((d.counts[i]/1345)*100).toFixed(1)}%`])
        })
    }""",

    # d03 Density Curve
    "d03": """{
        id: 'chart-d03',
        code: 'd03',
        title: '航线综合客座率离散度概率分布',
        subtitle: '拟合全网航线实际综合客座率连续分布特征与正态偏度特征',
        explainKey: 'd03',
        data: {
            plfRange: ['60%', '65%', '70%', '75%', '80%', '85%', '90%', '95%', '100%'],
            density: [0.02, 0.05, 0.12, 0.28, 0.45, 0.68, 0.52, 0.22, 0.06]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">客座率水位: ${params[0].name}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">分布密度系数:</span><span class="font-mono font-bold text-primary">${params[0].value}</span></div>`
            },
            xAxis: { type: 'category', data: d.plfRange, axisTick: { show: false } },
            yAxis: { type: 'value', max: 0.8, name: '概率密度', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '{value}' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [{
                name: '客座率分布拟合',
                type: 'line',
                smooth: true,
                data: d.density,
                lineStyle: { color: tokens.palette.primary, width: 2.5 },
                itemStyle: { color: tokens.palette.primary },
                areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(18, 59, 93, 0.3)' }, { offset: 1, color: 'rgba(18, 59, 93, 0.02)' }]) }
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['客座率区间', '概率密度拟合值', '特征判定'],
            rows: d.plfRange.map((r, i) => [r, `${d.density[i]}`, i === 5 ? '🎯 众数集中区间 (85%)' : '-'])
        })
    }""",

    # t04 Stacked Area (Time Series Structure with dataZoom)
    "t04": """{
        id: 'chart-t04',
        code: 't04',
        title: '客运、货邮与航空辅营业务收入结构演变',
        subtitle: '追踪两舱客票、经济舱客票、腹舱货运与航空辅营在历史时序中的占比',
        explainKey: 't04',
        data: {
            quarters: ['23Q3', '23Q4', '24Q1', '24Q2', '24Q3', '24Q4', '25Q1', '25Q2'],
            premium: [0.7, 0.8, 0.8, 0.9, 1.2, 1.4, 1.6, 1.8],
            economy: [2.5, 2.7, 2.8, 3.2, 3.8, 4.2, 4.6, 5.0],
            cargo: [0.4, 0.5, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            ancillary: [0.2, 0.3, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;'
            },
            legend: { top: 0, right: 12, orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 12, data: ['两舱客票', '经济舱客票', '腹舱货运', '航空辅营'], textStyle: { fontSize: 10, color: tokens.palette.inkMuted } },
            xAxis: { type: 'category', data: d.quarters, axisTick: { show: false } },
            yAxis: { type: 'value', max: 9.0, name: '创收规模 (亿元)', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '{value} 亿' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [
                { name: '两舱客票', type: 'line', stack: 'total', areaStyle: {}, data: d.premium, itemStyle: { color: '#0B2A42' } },
                { name: '经济舱客票', type: 'line', stack: 'total', areaStyle: {}, data: d.economy, itemStyle: { color: '#123B5D' } },
                { name: '腹舱货运', type: 'line', stack: 'total', areaStyle: {}, data: d.cargo, itemStyle: { color: '#8EA4B8' } },
                { name: '航空辅营', type: 'line', stack: 'total', areaStyle: {}, data: d.ancillary, itemStyle: { color: '#DCE8F0' } }
            ]
        }),
        tableDataExtractor: (d) => ({
            headers: ['统计季度', '两舱客票 (亿元)', '经济舱客票 (亿元)', '腹舱货运 (亿元)', '航空辅营 (亿元)'],
            rows: d.quarters.map((q, i) => [q, `¥${d.premium[i]} 亿`, `¥${d.economy[i]} 亿`, `¥${d.cargo[i]} 亿`, `¥${d.ancillary[i]} 亿`])
        })
    }""",

    # t02 Forecast Line (Clean without dataZoom)
    "t02": """{
        id: 'chart-t02',
        code: 't02',
        title: '总可用座公里 ASK 历史投放与未来旺季预测',
        subtitle: '对比历史实际运力供给与未来春运/暑运旺季情景预测走廊',
        explainKey: 't02',
        data: {
            quarters: ['24Q1', '24Q2', '24Q3', '24Q4', '25Q1 (E)', '25Q2 (E)'],
            actual: [42.0, 48.5, 56.0, 52.0, null, null],
            forecast: [null, null, null, 52.0, 58.5, 65.0]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;'
            },
            legend: { top: 0, right: 12, orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 14, data: ['历史实测运力', '未来预测走廊'], textStyle: { fontSize: 10, color: tokens.palette.inkMuted } },
            xAxis: { type: 'category', data: d.quarters, axisTick: { show: false } },
            yAxis: { type: 'value', min: 30, max: 75, name: 'ASK 运力 (亿座公里)', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '{value}' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [
                { name: '历史实测运力', type: 'line', data: d.actual, lineStyle: { color: tokens.palette.primary, width: 2.5 }, itemStyle: { color: tokens.palette.primary, borderColor: '#FFF', borderWidth: 2 } },
                { name: '未来预测走廊', type: 'line', data: d.forecast, lineStyle: { color: tokens.palette.positive, width: 2.5, type: 'dashed' }, itemStyle: { color: tokens.palette.positive, borderColor: '#FFF', borderWidth: 2 } }
            ]
        }),
        tableDataExtractor: (d) => ({
            headers: ['季度', '可用座公里 ASK (亿座公里)', '性质'],
            rows: d.quarters.map((q, i) => [q, `${d.actual[i] || d.forecast[i]} 亿座公里`, i < 4 ? '历史实测结算' : '未来模型预测 (E)'])
        })
    }""",

    # k02 100% Stacked Bar
    "k02": """{
        id: 'chart-k02',
        code: 'k02',
        title: '各大核心基地直销 vs OTA 渠道销售配比',
        subtitle: '横向对比各大基地枢纽在官方 App 直销、大客户协议与 OTA 渠道配比',
        explainKey: 'k02',
        data: {
            hubs: ['华东基地', '华南基地', '北方基地', '西南基地'],
            appDirect: [48, 42, 38, 32],
            corpDirect: [28, 25, 24, 20],
            ota: [24, 33, 38, 48]
        },
        optionBuilder: (d, gran, tokens) => ({
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
                    let res = `<div class="font-bold text-primary-strong mb-1">${params[0].name} 渠道结构</div>`;
                    params.forEach(p => {
                        res += `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">${p.seriesName}:</span><span class="font-mono font-bold text-primary">${p.value}%</span></div>`;
                    });
                    return res;
                }
            },
            legend: { top: 0, right: 12, orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 12, data: ['官方App直销', '大客户直签', 'OTA代理平台'], textStyle: { fontSize: 10, color: tokens.palette.inkMuted } },
            grid: { top: 38, bottom: 38, left: 10, right: 25, containLabel: true },
            xAxis: { type: 'value', max: 100, name: '销售占比 (%)', nameLocation: 'middle', nameGap: 24, nameTextStyle: tokens.axisTitleStyleX, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            yAxis: { type: 'category', inverse: true, name: '枢纽基地', nameLocation: 'start', nameTextStyle: tokens.axisTitleStyleY, data: d.hubs, axisTick: { show: false }, axisLine: { lineStyle: { color: '#94A3B8', width: 1.2 } }, axisLabel: { color: '#0F172A', fontSize: 12, fontWeight: 700 } },
            series: [
                { name: '官方App直销', type: 'bar', stack: 'total', barWidth: 18, data: d.appDirect, itemStyle: { color: '#0B2A42' }, label: { show: true, formatter: '{c}%', color: '#FFF', fontSize: 9 } },
                { name: '大客户直签', type: 'bar', stack: 'total', data: d.corpDirect, itemStyle: { color: '#123B5D' }, label: { show: true, formatter: '{c}%', color: '#FFF', fontSize: 9 } },
                { name: 'OTA代理平台', type: 'bar', stack: 'total', data: d.ota, itemStyle: { color: '#8EA4B8' }, label: { show: true, formatter: '{c}%', color: '#FFF', fontSize: 9 } }
            ]
        }),
        tableDataExtractor: (d) => ({
            headers: ['枢纽基地', '官网App直销', '大客户直签', 'OTA平台分销', '综合直销率'],
            rows: d.hubs.map((h, i) => [h, `${d.appDirect[i]}%`, `${d.corpDirect[i]}%`, `${d.ota[i]}%`, `${d.appDirect[i] + d.corpDirect[i]}%`])
        })
    }""",

    # r02 3D Bubble
    "r02": """{
        id: 'chart-r02',
        code: 'r02',
        title: '常旅客获客成本 CAC 与生命周期价值 LTV 分布',
        subtitle: '量化高端商旅、普通商务与大众旅客的获客成本与生命周期价值关系',
        explainKey: 'r02',
        data: {
            clusters: [
                [3.2, 28.5, 45, '白金卡高端商旅'],
                [2.1, 16.8, 120, '金卡高频商务'],
                [1.2, 8.4, 380, '银卡大众商旅'],
                [0.4, 2.1, 950, '普卡休闲度假']
            ]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${params.data[3]}</div><div class="space-y-0.5 text-xs"><div class="flex justify-between gap-4"><span class="text-ink-muted">单客 CAC:</span><span class="font-mono font-bold text-ink">¥${params.data[0]} 万元</span></div><div class="flex justify-between gap-4"><span class="text-ink-muted">单客 LTV:</span><span class="font-mono font-bold text-primary">¥${params.data[1]} 万元</span></div><div class="flex justify-between gap-4"><span class="text-ink-muted">LTV/CAC倍数:</span><span class="font-mono font-bold text-positive">${(params.data[1]/params.data[0]).toFixed(1)}x</span></div><div class="flex justify-between gap-4"><span class="text-ink-muted">在册客群规模:</span><span class="font-mono font-bold text-ink-muted">${params.data[2]} 万人</span></div></div>`
            },
            xAxis: { type: 'value', min: 0, max: 4.5, name: '获客成本 CAC (万元)', nameLocation: 'middle', nameGap: 24, nameTextStyle: tokens.axisTitleStyleX, axisLabel: { formatter: '¥{value}万' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            yAxis: { type: 'value', min: 0, max: 35, name: '生命周期价值 LTV (万元)', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '¥{value}万' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [{
                type: 'scatter',
                data: d.clusters,
                symbolSize: val => Math.sqrt(val[2]) * 4 + 8,
                itemStyle: { color: tokens.palette.primary, borderColor: '#FFF', borderWidth: 2 },
                label: { show: true, position: 'top', formatter: params => params.data[3], color: tokens.palette.ink, fontSize: 10, fontWeight: 600 }
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['客群分类', '获客成本 CAC (万元)', '生命周期价值 LTV (万元)', 'LTV/CAC 倍数', '规模人数 (万人)'],
            rows: d.clusters.map(c => [c[3], `¥${c[0]}万`, `¥${c[1]}万`, `${(c[1]/c[0]).toFixed(1)}x`, `${c[2]} 万人`])
        })
    }""",

    # f03 Cohort
    "f03": """{
        id: 'chart-f03',
        code: 'f03',
        title: '新增常旅客会员批次 M0~M3 乘机复购留存',
        subtitle: '追踪各季度新入会会员在生命周期前 3 个月的乘机复购留存率演变',
        explainKey: 'f03',
        data: {
            cohorts: ['24Q1 批次', '24Q2 批次', '24Q3 批次', '24Q4 批次'],
            months: ['M0', 'M1', 'M2', 'M3'],
            matrix: [
                [0, 0, 100], [1, 0, 88], [2, 0, 78], [3, 0, 72],
                [0, 1, 100], [1, 1, 90], [2, 1, 82], [3, 1, 76],
                [0, 2, 100], [1, 2, 92], [2, 2, 85], [3, 2, 80],
                [0, 3, 100], [1, 3, 94], [2, 3, 88], [3, 3, 84]
            ]
        },
        optionBuilder: (d, gran, tokens) => ({
            tooltip: {
                position: 'top',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${d.cohorts[params.value[1]]} ➔ ${d.months[params.value[0]]}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">乘机复购留存率:</span><span class="font-mono font-bold text-primary">${params.value[2]}%</span></div>`
            },
            grid: { top: 20, bottom: 38, left: 10, right: 18, containLabel: true },
            xAxis: { type: 'category', data: d.months, axisTick: { show: false } },
            yAxis: { type: 'category', data: d.cohorts, axisTick: { show: false } },
            visualMap: { min: 70, max: 100, show: false, inRange: { color: ['#DCE8F0', '#8EA4B8', '#123B5D', '#0B2A42'] } },
            series: [{
                type: 'heatmap',
                data: d.matrix,
                label: { show: true, formatter: params => params.value[2] + '%', color: '#FFFFFF', fontSize: 11, fontWeight: 600 },
                itemStyle: { borderColor: '#FFFFFF', borderWidth: 2 }
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['会员批次', 'M0 注册成行', 'M1 留存率', 'M2 留存率', 'M3 复购留存'],
            rows: d.cohorts.map((c, i) => [c, '100%', `${d.matrix[i*4+1][2]}%`, `${d.matrix[i*4+2][2]}%`, `${d.matrix[i*4+3][2]}%`])
        })
    }""",

    # m01 Bullet Graph
    "m01": """{
        id: 'chart-m01',
        code: 'm01',
        title: '民航年度战略关键绩效考核达成情况',
        subtitle: '对比各项民航运营核心 KPI 实际考核值与目标基准线差距',
        explainKey: 'm01',
        data: {
            metrics: ['客运总收入', '综合客座率', '航班正常率', '直销渠道比'],
            actual: [106.8, 104.2, 98.5, 94.0],
            target: 100.0
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${params[0].name}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">战略达成进度:</span><span class="font-mono font-bold ${params[0].value >= 100 ? 'text-positive' : 'text-negative'}">${params[0].value}%</span></div>`
            },
            grid: { top: 38, bottom: 38, left: 10, right: 25, containLabel: true },
            xAxis: { type: 'value', max: 130, name: '达成率 (%)', nameLocation: 'middle', nameGap: 24, nameTextStyle: tokens.axisTitleStyleX, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            yAxis: { type: 'category', inverse: true, name: '考核指标', nameLocation: 'start', nameTextStyle: tokens.axisTitleStyleY, data: d.metrics, axisTick: { show: false }, axisLine: { lineStyle: { color: '#94A3B8', width: 1.2 } }, axisLabel: { color: '#0F172A', fontSize: 12, fontWeight: 700 } },
            series: [
                {
                    name: '实际完成达成率',
                    type: 'bar',
                    barWidth: 18,
                    data: d.actual,
                    itemStyle: { color: tokens.palette.primary },
                    label: { show: true, position: 'right', distance: 6, formatter: '{c}%', color: tokens.palette.ink, fontSize: 10, fontWeight: 600 },
                    markLine: {
                        symbol: 'none',
                        lineStyle: { type: 'dashed', color: tokens.palette.positive, width: 2 },
                        data: [{ xAxis: 100, label: { formatter: '100% 目标线', position: 'start', color: tokens.palette.positive, fontSize: 10, fontWeight: 600, padding: [2, 6], backgroundColor: '#FFFFFF', borderColor: tokens.palette.positive, borderWidth: 1, borderRadius: 4 } }]
                    }
                }
            ]
        }),
        tableDataExtractor: (d) => ({
            headers: ['战略考核指标', '实际达成率 (%)', '考核基准线', '达标状态'],
            rows: d.metrics.map((m, i) => [m, `${d.actual[i]}%`, '100.0%', d.actual[i] >= 100 ? '🟢 超额达成' : '🟡 接近目标'])
        })
    }""",

    # d04 24H Heatmap
    "d04": """{
        id: 'chart-d04',
        code: 'd04',
        title: '全周 24 小时航班起降与枢纽港吞吐高峰时刻',
        subtitle: '定位一周内各时段枢纽机场航班波进出港与停机位负荷密度峰值',
        explainKey: 'd04',
        data: {
            days: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
            hours: ['00:00', '03:00', '06:00', '09:00', '12:00', '15:00', '18:00', '21:00'],
            data: [
                [0,0,12],[1,0,8],[2,0,15],[3,0,65],[4,0,88],[5,0,92],[6,0,70],[7,0,40],
                [0,1,10],[1,1,5],[2,1,18],[3,1,72],[4,1,95],[5,1,98],[6,1,75],[7,1,45],
                [0,2,14],[1,2,6],[2,2,16],[3,2,68],[4,2,90],[5,2,94],[6,2,72],[7,2,42],
                [0,3,11],[1,3,9],[2,3,20],[3,3,75],[4,3,92],[5,3,96],[6,3,78],[7,3,48],
                [0,4,15],[1,4,7],[2,4,14],[3,4,60],[4,4,85],[5,4,89],[6,4,65],[7,4,35],
                [0,5,8],[1,5,4],[2,5,6],[3,5,25],[4,5,38],[5,5,42],[6,5,30],[7,5,20],
                [0,6,6],[1,6,3],[2,6,5],[3,6,20],[4,6,32],[5,6,35],[6,6,28],[7,6,18]
            ]
        },
        optionBuilder: (d, gran, tokens) => ({
            tooltip: {
                position: 'top',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${d.days[params.value[1]]} ${d.hours[params.value[0]]} 时段</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">航班起降吞吐指数:</span><span class="font-mono font-bold text-primary">${params.value[2]}</span></div>`
            },
            grid: { top: 20, bottom: 38, left: 10, right: 18, containLabel: true },
            xAxis: { type: 'category', data: d.hours, axisTick: { show: false } },
            yAxis: { type: 'category', data: d.days, axisTick: { show: false } },
            visualMap: { min: 0, max: 100, show: false, inRange: { color: ['#F0F5F9', '#8EA4B8', '#123B5D', '#0B2A42'] } },
            series: [{
                type: 'heatmap',
                data: d.data,
                label: { show: true, formatter: params => params.value[2], color: '#FFFFFF', fontSize: 10, fontWeight: 600 },
                itemStyle: { borderColor: '#FFFFFF', borderWidth: 2 }
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['时段特征', '高峰时段 (09:00-18:00)', '夜间低谷 (00:00-06:00)', '运行保障提示'],
            rows: [
                ['工作日高峰 (周一~周四)', '吞吐指数 88-98', '吞吐指数 5-15', '加大机坪滑行及安检通道资源调度'],
                ['周末出行 (周五~周日)', '吞吐指数 35-89', '吞吐指数 3-8', '客流适度放缓，安排机务定检']
            ]
        })
    }""",

    # r04 Network Graph
    "r04": """{
        id: 'chart-r04',
        code: 'r04',
        title: '全国核心枢纽机场航线网络拓扑关联图',
        subtitle: '呈现北京、上海、广州等主枢纽与各区域节点的航线协同流向与关联强度',
        explainKey: 'r04',
        data: {
            nodes: [
                { name: '北京大兴/首都', symbolSize: 32, itemStyle: { color: '#0B2A42' } },
                { name: '上海虹桥/浦东', symbolSize: 32, itemStyle: { color: '#123B5D' } },
                { name: '广州白云', symbolSize: 28, itemStyle: { color: '#123B5D' } },
                { name: '成都天府', symbolSize: 24, itemStyle: { color: '#3A5A78' } },
                { name: '深圳宝安', symbolSize: 24, itemStyle: { color: '#3A5A78' } },
                { name: '西安咸阳', symbolSize: 18, itemStyle: { color: '#8EA4B8' } },
                { name: '昆明长水', symbolSize: 18, itemStyle: { color: '#8EA4B8' } }
            ],
            links: [
                { source: '北京大兴/首都', target: '上海虹桥/浦东', lineStyle: { width: 4 } },
                { source: '上海虹桥/浦东', target: '广州白云', lineStyle: { width: 3.5 } },
                { source: '北京大兴/首都', target: '广州白云', lineStyle: { width: 3 } },
                { source: '上海虹桥/浦东', target: '成都天府', lineStyle: { width: 2.5 } },
                { source: '北京大兴/首都', target: '深圳宝安', lineStyle: { width: 2.5 } },
                { source: '广州白云', target: '成都天府', lineStyle: { width: 2 } },
                { source: '成都天府', target: '西安咸阳', lineStyle: { width: 1.5 } },
                { source: '广州白云', target: '昆明长水', lineStyle: { width: 1.5 } }
            ]
        },
        optionBuilder: (d, gran, tokens) => ({
            tooltip: {
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${params.name}</div><div class="text-xs text-ink-muted">核心枢纽干线网络拓扑节点</div>`
            },
            series: [{
                type: 'graph',
                layout: 'force',
                force: { repulsion: 220, edgeLength: [60, 120] },
                data: d.nodes,
                links: d.links,
                roam: true,
                label: { show: true, position: 'right', formatter: '{b}', color: tokens.palette.ink, fontSize: 10, fontWeight: 600 },
                lineStyle: { color: tokens.palette.primary, curveness: 0.2 }
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['枢纽机场节点', '辐射航线数', '节点等级'],
            rows: d.nodes.map(n => [n.name, n.symbolSize > 25 ? '80+ 条黄金干线' : '35+ 条区域干线', n.symbolSize > 25 ? '全国超大型主枢纽' : '区域骨干枢纽'])
        })
    }""",

    # c06 Dumbbell
    "c06": """{
        id: 'chart-c06',
        code: 'c06',
        title: '各大基地重点商务航线客座率跃升跨度',
        subtitle: '对比四大枢纽基地在淡季基期与商务旺季当期的客座率跃升幅度',
        explainKey: 'c06',
        data: {
            hubs: ['华东基地', '华南基地', '北方基地', '西南基地'],
            offSeason: [76.5, 74.2, 71.8, 68.5],
            peakSeason: [92.4, 89.6, 87.5, 84.2]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => {
                    const idx = params[0].dataIndex;
                    const diff = (d.peakSeason[idx] - d.offSeason[idx]).toFixed(1);
                    return `<div class="font-bold text-primary-strong mb-1">${d.hubs[idx]} 航线客座率</div><div class="space-y-0.5 text-xs"><div class="flex justify-between gap-4"><span class="text-ink-muted">淡季基期:</span><span class="font-mono font-medium text-ink-muted">${d.offSeason[idx]}%</span></div><div class="flex justify-between gap-4"><span class="text-ink-muted">旺季当期:</span><span class="font-mono font-bold text-primary">${d.peakSeason[idx]}%</span></div><div class="flex justify-between gap-4 border-t border-slate-100 mt-1 pt-1"><span class="text-ink-muted">跃升跨度:</span><span class="font-mono font-bold text-positive">+${diff}pp</span></div></div>`;
                }
            },
            legend: { top: 0, right: 12, orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 14, data: ['淡季基期', '旺季当期'], textStyle: { fontSize: 10, color: tokens.palette.inkMuted } },
            grid: { top: 38, bottom: 38, left: 10, right: 25, containLabel: true },
            xAxis: { type: 'value', min: 60, max: 100, name: '客座率 (%)', nameLocation: 'middle', nameGap: 24, nameTextStyle: tokens.axisTitleStyleX, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            yAxis: { type: 'category', inverse: true, name: '枢纽大区', nameLocation: 'start', nameTextStyle: tokens.axisTitleStyleY, data: d.hubs, axisTick: { show: false }, axisLine: { lineStyle: { color: '#94A3B8', width: 1.2 } }, axisLabel: { color: '#0F172A', fontSize: 12, fontWeight: 700 } },
            series: [
                {
                    name: '淡季基期',
                    type: 'scatter',
                    symbolSize: 12,
                    data: d.offSeason,
                    itemStyle: { color: tokens.palette.inkSubtle }
                },
                {
                    name: '旺季当期',
                    type: 'scatter',
                    symbolSize: 14,
                    data: d.peakSeason,
                    itemStyle: { color: tokens.palette.primary, borderColor: '#FFF', borderWidth: 2 },
                    label: { show: true, position: 'right', distance: 6, formatter: '{c}%', color: tokens.palette.ink, fontSize: 10, fontWeight: 600 }
                }
            ]
        }),
        tableDataExtractor: (d) => ({
            headers: ['枢纽基地', '淡季基期客座率', '旺季当期客座率', '跃升跨度'],
            rows: d.hubs.map((h, i) => [h, `${d.offSeason[i]}%`, `${d.peakSeason[i]}%`, `+${(d.peakSeason[i]-d.offSeason[i]).toFixed(1)}pp`])
        })
    }""",

    # t05 Slopegraph
    "t05": """{
        id: 'chart-t05',
        code: 't05',
        title: '机队机型优化升级前后座公里成本 CASK 对照',
        subtitle: '评估新一代节油客机替换老旧机型后座公里成本 CASK 的改善斜率',
        explainKey: 't05',
        data: {
            stages: ['换装前 (2024)', '换装后 (2025)'],
            lines: [
                { name: '远程宽体机队 (A350 替换 B767)', data: [45.2, 38.1], color: '#123B5D' },
                { name: '骨干窄体机队 (A321neo 替换 A320ceo)', data: [36.5, 31.2], color: '#0B2A42' },
                { name: '支线机队 (ARJ21 规模化投入)', data: [38.0, 34.5], color: '#52606D' }
            ]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'item',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${params.seriesName}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">${d.stages[params.dataIndex]}:</span><span class="font-mono font-bold text-primary">¥0.${params.value} / 座公里</span></div>`
            },
            xAxis: { type: 'category', data: d.stages, axisTick: { show: false } },
            yAxis: { type: 'value', min: 25, max: 50, name: 'CASK (分/座公里)', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '{value}分' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: d.lines.map(l => ({
                name: l.name,
                type: 'line',
                data: l.data,
                lineStyle: { color: l.color, width: 2.5 },
                itemStyle: { color: l.color, borderColor: '#FFF', borderWidth: 2 },
                label: { show: true, position: 'top', formatter: '¥0.{c}', color: tokens.palette.ink, fontSize: 10, fontWeight: 600 }
            }))
        }),
        tableDataExtractor: (d) => ({
            headers: ['机队换装项目', '换装前 CASK', '换装后 CASK', '成本节约改善率'],
            rows: d.lines.map(l => [l.name, `¥0.${l.data[0]}`, `¥0.${l.data[1]}`, `-${(((l.data[0]-l.data[1])/l.data[0])*100).toFixed(1)}%`])
        })
    }""",

    # k01 Donut KPI
    "k01": """{
        id: 'chart-k01',
        code: 'k01',
        title: '旅客舱位等级与出行客群构成分布',
        subtitle: '反映公商务出行、休闲度假、探亲求学与团队政务等不同客群的构成占比',
        explainKey: 'k01',
        data: {
            demographics: [
                { value: 42, name: '公商务高频出行 (42%)', itemStyle: { color: '#0B2A42' } },
                { value: 30, name: '休闲旅游度假 (30%)', itemStyle: { color: '#123B5D' } },
                { value: 18, name: '探亲求学探访 (18%)', itemStyle: { color: '#4A6B8A' } },
                { value: 10, name: '政务团队出行 (10%)', itemStyle: { color: '#8EA4B8' } }
            ]
        },
        optionBuilder: (d, gran, tokens) => ({
            tooltip: {
                trigger: 'item',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: '{b}: {c}% 客群构成'
            },
            series: [{
                type: 'pie',
                radius: ['45%', '70%'],
                center: ['50%', '52%'],
                avoidLabelOverlap: false,
                label: { show: true, position: 'outside', formatter: '{b}', fontSize: 10, color: tokens.palette.ink },
                labelLine: { length: 10, length2: 10 },
                data: d.demographics
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['客群细分', '客群占比 (%)', '年承运人次预估'],
            rows: d.demographics.map(s => [s.name.split(' ')[0], `${s.value}%`, `${((s.value/100)*5420).toFixed(0)} 万人次`])
        })
    }""",

    # k04 Pareto 80/20
    "k04": """{
        id: 'chart-k04',
        code: 'k04',
        title: '航班延误与服务投诉主因帕累托 80/20 诊断',
        subtitle: '依延误发生频数降序与累计占比曲线识别 80% 核心运行阻碍',
        explainKey: 'k04',
        data: {
            causes: ['天气及流量管制', '前序航班晚到', '跑道维护及保障', '飞机机械偶发', '其他地服原因'],
            counts: [480, 320, 140, 60, 30],
            cumPercent: [46.6, 77.7, 91.3, 97.1, 100.0]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${params[0].name}</div><div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">延误频次:</span><span class="font-mono font-bold text-primary">${params[0].value} 架次</span></div><div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">累计贡献率:</span><span class="font-mono font-bold text-positive">${params[1].value}%</span></div>`
            },
            legend: { top: 0, left: 'center', orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 20, data: ['延误架次', '累计占比曲线'], textStyle: { fontSize: 10, color: tokens.palette.inkMuted } },
            grid: { top: 52, bottom: 38, left: 10, right: 18, containLabel: true },
            xAxis: { type: 'category', data: d.causes, axisTick: { show: false } },
            yAxis: [
                { type: 'value', max: 600, name: '延误架次', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '{value}' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
                { type: 'value', min: 0, max: 115, name: '累计 (%)', nameLocation: 'end', nameTextStyle: { color: tokens.palette.inkSubtle, fontSize: 10, align: 'right', padding: [0, 0, 6, 0] }, axisLabel: { formatter: '{value}%' }, splitLine: { show: false } }
            ],
            series: [
                { name: '延误架次', type: 'bar', barWidth: 22, data: d.counts, itemStyle: { color: tokens.palette.primary } },
                {
                    name: '累计占比曲线',
                    type: 'line',
                    yAxisIndex: 1,
                    data: d.cumPercent,
                    lineStyle: { color: tokens.palette.positive, width: 2.5 },
                    itemStyle: { color: tokens.palette.positive, borderColor: '#FFF', borderWidth: 2 },
                    label: { show: true, position: 'top', formatter: '{c}%', color: tokens.palette.positive, fontSize: 10, fontWeight: 600 },
                    markLine: {
                        symbol: 'none',
                        lineStyle: { type: 'dashed', color: tokens.palette.positive, width: 1.5 },
                        data: [{ yAxis: 80, label: { formatter: '  80% 核心诱因界线', position: 'insideStartTop', color: tokens.palette.positive, fontSize: 10, fontWeight: 600, padding: [2, 6], backgroundColor: '#FFFFFF', borderColor: tokens.palette.positive, borderWidth: 1, borderRadius: 4 } }]
                    }
                }
            ]
        }),
        tableDataExtractor: (d) => ({
            headers: ['延误主因分类', '发生频次 (架次)', '累计占比 (%)', '帕累托判定'],
            rows: d.causes.map((c, i) => [c, `${d.counts[i]} 架次`, `${d.cumPercent[i]}%`, d.cumPercent[i] <= 80 ? '🔴 关键核心诱因 (前80%)' : '次要长尾诱因'])
        })
    }""",

    # k03 Treemap
    "k03": """{
        id: 'chart-k03',
        code: 'k03',
        title: '民航机队在册客机资产估值分布',
        subtitle: '通过几何面积直观映射各机型机队的账面净值与资产估值体量',
        explainKey: 'k03',
        data: {
            assets: [
                { name: 'A350-900 远程机队', value: 12.5 },
                { name: 'B787-9 梦想客机', value: 8.8 },
                { name: 'A321neo 主力窄体', value: 6.4 },
                { name: 'B737-800 骨干客机', value: 4.8 },
                { name: 'C919 国产干线客机', value: 3.2 },
                { name: 'ARJ21 支线机队', value: 1.6 }
            ]
        },
        optionBuilder: (d, gran, tokens) => ({
            tooltip: {
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: params => `<div class="font-bold text-primary-strong mb-1">${params.name}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">机队估值净额:</span><span class="font-mono font-bold text-primary">¥${params.value} 亿元</span></div>`
            },
            series: [{
                type: 'treemap',
                width: '92%',
                height: '84%',
                top: 15,
                bottom: 15,
                roam: false,
                nodeClick: false,
                breadcrumb: { show: false },
                itemStyle: { borderColor: '#FFF', borderWidth: 2, gapWidth: 2 },
                color: ['#0B2A42', '#123B5D', '#2B5578', '#4A7296', '#6F91B0', '#9BB5CC'],
                data: d.assets
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['机型机队', '在册资产估值 (亿元)', '资产占比'],
            rows: d.assets.map(a => [a.name, `¥${a.value} 亿`, `${((a.value/37.3)*100).toFixed(1)}%`])
        })
    }""",

    # k06 Sunburst
    "k06": """{
        id: 'chart-k06',
        code: 'k06',
        title: '航线网络国内外与区域层级结构',
        subtitle: '呈现国内干线/支线与国际远程/周边区域航线的同心多层级客运构成',
        explainKey: 'k06',
        data: {
            hierarchy: [
                {
                    name: '国内网络 (72%)',
                    itemStyle: { color: '#123B5D' },
                    children: [
                        { name: '商务干线 (50%)', value: 50, itemStyle: { color: '#0B2A42' } },
                        { name: '区域支线 (22%)', value: 22, itemStyle: { color: '#2B5578' } }
                    ]
                },
                {
                    name: '国际网络 (28%)',
                    itemStyle: { color: '#52606D' },
                    children: [
                        { name: '洲际远程 (18%)', value: 18, itemStyle: { color: '#6F91B0' } },
                        { name: '周边短程 (10%)', value: 10, itemStyle: { color: '#9BB5CC' } }
                    ]
                }
            ]
        },
        optionBuilder: (d, gran, tokens) => ({
            tooltip: {
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;',
                formatter: '{b}: {c}% 航网体量'
            },
            series: [{
                type: 'sunburst',
                radius: ['15%', '85%'],
                center: ['50%', '52%'],
                data: d.hierarchy,
                label: { rotate: 'radial', fontSize: 10, color: '#FFF' },
                itemStyle: { borderColor: '#FFF', borderWidth: 2 }
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['层级分类', '细分航网板块', '占总运力比重'],
            rows: [
                ['国内航线网络', '商务黄金干线', '50.0%'],
                ['国内航线网络', '区域干支结合', '22.0%'],
                ['国际航线网络', '欧美洲际远程', '18.0%'],
                ['国际航线网络', '日韩东南亚短程', '10.0%']
            ]
        })
    }""",

    # m02 Fan Chart
    "m02": """{
        id: 'chart-m02',
        code: 'm02',
        title: '春运及暑运民航客运量预测扩散走廊',
        subtitle: '基于历史基线展示未来春运与暑运客运量悲观、基准与乐观扩散区间',
        explainKey: 'm02',
        data: {
            quarters: ['24Q1', '24Q2', '24Q3', '24Q4', '25Q1(E)', '25Q2(E)'],
            baseline: [8.5, 9.2, 11.5, 10.2, 12.0, 13.5],
            optimistic: [8.5, 9.2, 11.5, 10.2, 13.2, 15.2],
            pessimistic: [8.5, 9.2, 11.5, 10.2, 10.8, 11.8]
        },
        optionBuilder: (d, gran, tokens) => ({
            ...tokens.commonOption,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;'
            },
            legend: { top: 0, right: 12, orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 12, data: ['乐观情景', '基准预测', '悲观情景'], textStyle: { fontSize: 10, color: tokens.palette.inkMuted } },
            xAxis: { type: 'category', data: d.quarters, axisTick: { show: false } },
            yAxis: { type: 'value', min: 6.0, max: 17.0, name: '客运营收 (亿元)', nameLocation: 'end', nameTextStyle: tokens.axisTitleStyleY, axisLabel: { formatter: '{value} 亿' }, splitLine: { lineStyle: { color: tokens.palette.gridline } } },
            series: [
                { name: '乐观情景', type: 'line', data: d.optimistic, lineStyle: { color: tokens.palette.positive, width: 2, type: 'dashed' }, itemStyle: { color: tokens.palette.positive } },
                { name: '基准预测', type: 'line', data: d.baseline, lineStyle: { color: tokens.palette.primary, width: 2.5 }, itemStyle: { color: tokens.palette.primary, borderColor: '#FFF', borderWidth: 2 } },
                { name: '悲观情景', type: 'line', data: d.pessimistic, lineStyle: { color: tokens.palette.negative, width: 2, type: 'dashed' }, itemStyle: { color: tokens.palette.negative } }
            ]
        }),
        tableDataExtractor: (d) => ({
            headers: ['预测周期', '悲观情景 (亿元)', '基准预测 (亿元)', '乐观情景 (亿元)'],
            rows: d.quarters.map((q, i) => [q, `¥${d.pessimistic[i]} 亿`, `¥${d.baseline[i]} 亿`, `¥${d.optimistic[i]} 亿`])
        })
    }""",

    # r05 Radar
    "r05": """{
        id: 'chart-r05',
        code: 'r05',
        title: '航司综合运营多维能力雷达评估',
        subtitle: '对标行业顶尖水准，量化准点率、客座率、单位收益、机队利用率与服务评分',
        explainKey: 'r05',
        data: {
            indicators: [
                { name: '航班正常率', max: 100 },
                { name: '综合客座率', max: 100 },
                { name: '座公里收益', max: 100 },
                { name: '机队日利用率', max: 100 },
                { name: 'NPS客户满意度', max: 100 }
            ],
            seriesData: [
                { value: [92, 88, 85, 90, 86], name: '当期实测效能' },
                { value: [85, 80, 78, 82, 80], name: '行业基准参考' }
            ]
        },
        optionBuilder: (d, gran, tokens) => ({
            tooltip: {
                backgroundColor: 'rgba(255, 255, 255, 0.98)',
                borderColor: tokens.palette.rule,
                borderWidth: 1,
                padding: [8, 12],
                extraCssText: 'box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;'
            },
            legend: { top: 0, right: 12, orient: 'horizontal', icon: 'rect', itemWidth: 10, itemHeight: 10, itemGap: 14, data: ['当期实测效能', '行业基准参考'], textStyle: { fontSize: 10, color: tokens.palette.inkMuted } },
            radar: {
                indicator: d.indicators,
                shape: 'polygon',
                radius: '65%',
                center: ['50%', '55%'],
                axisName: { color: tokens.palette.ink, fontSize: 10, fontWeight: 600 },
                splitLine: { lineStyle: { color: tokens.palette.gridline } },
                splitArea: { show: true, areaStyle: { color: ['#F8FAFC', '#FFFFFF'] } }
            },
            series: [{
                type: 'radar',
                data: [
                    { value: d.seriesData[0].value, name: d.seriesData[0].name, itemStyle: { color: tokens.palette.primary }, areaStyle: { color: 'rgba(18, 59, 93, 0.25)' } },
                    { value: d.seriesData[1].value, name: d.seriesData[1].name, itemStyle: { color: tokens.palette.inkSubtle }, lineStyle: { type: 'dashed' } }
                ]
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['评估维度', '当期实测得分', '行业基准参考', '能力偏离'],
            rows: d.indicators.map((ind, i) => [ind.name, `${d.seriesData[0].value[i]} 分`, `${d.seriesData[1].value[i]} 分`, `+${d.seriesData[0].value[i] - d.seriesData[1].value[i]} 分`])
        })
    }""",

    # m04 Semi-Gauge
    "m04": """{
        id: 'chart-m04',
        code: 'm04',
        title: '民航年度主营营收预算目标综合达成率',
        subtitle: '大字直显机队与客货运全网年度预算目标的综合推进完成比例',
        explainKey: 'm04',
        data: {
            rate: 84.5,
            target: '100.0%'
        },
        optionBuilder: (d, gran, tokens) => ({
            series: [{
                type: 'gauge',
                startAngle: 180,
                endAngle: 0,
                min: 0,
                max: 100,
                radius: '100%',
                center: ['50%', '70%'],
                progress: { show: true, width: 18, itemStyle: { color: tokens.palette.primary } },
                axisLine: { lineStyle: { width: 18, color: [[1, '#EEF2F5']] } },
                axisTick: { show: false },
                splitLine: { show: false },
                axisLabel: { show: false },
                pointer: { show: false },
                title: { show: true, offsetCenter: [0, '25%'], fontSize: 11, color: tokens.palette.inkSubtle },
                detail: {
                    valueAnimation: false,
                    offsetCenter: [0, '-10%'],
                    fontSize: 28,
                    fontWeight: 'bold',
                    formatter: '{value}%',
                    color: tokens.palette.ink
                },
                data: [{ value: d.rate, name: '年度目标综合完成率' }]
            }]
        }),
        tableDataExtractor: (d) => ({
            headers: ['考核指标', '当前完成率', '基准目标', '考核判定'],
            rows: [['年度主营营收综合完成率', `${d.rate}%`, d.target, '🎯 推进节奏良好']]
        })
    }"""
}

ALL_CHART_BUILDERS = ALL_CHARTS
