# Base template with 100% solid, non-overlapping sticky table headers
from .runtime_bundle import render_runtime_bundle
from .filter_bindings import FILTER_BINDINGS_JS
from .palette import categorical_js, echarts_palette_js, tailwind_colors_js
from .explanation_dialog import (
    EXPLANATION_DIALOG_CSS,
    EXPLANATION_DIALOG_RENDERER_JS,
    EXPLANATION_DIALOG_SHELL,
    EXPLANATION_TRIGGER_ICON,
)

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__PAGE_TITLE__</title>
    <!-- Tailwind CSS with Forms & Container Queries -->
    <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: __TAILWIND_COLORS__,
                    fontFamily: {
                        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "'PingFang SC'", "'Segoe UI'", "sans-serif"],
                        mono: ["'JetBrains Mono'", "Menlo", "Monaco", "Consolas", "monospace"]
                    }
                }
            }
        }
    </script>
    <!-- ECharts 5.5 -->
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
    <style>
        /* Bulletproof Icon & UI Styling */
        svg {
            display: inline-block;
            vertical-align: middle;
        }
        .chart-action-btn svg {
            width: 13px !important;
            height: 13px !important;
            display: block !important;
            stroke: currentColor !important;
        }
        .card-body-wrap {
            height: 270px;
            min-height: 270px;
            width: 100%;
            position: relative;
            overflow: hidden;
        }
        .card-chart-pane {
            width: 100% !important;
            height: 100% !important;
            min-height: 270px;
        }
        .card-table-pane {
            width: 100% !important;
            height: 100% !important;
            min-height: 270px;
        }
        
        /* Sticky Glassmorphism Global Filter Bar */
        .sticky-filter-bar {
            position: -webkit-sticky !important;
            position: sticky !important;
            top: 0 !important;
            z-index: 40 !important;
            background: rgba(255, 255, 255, 0.96) !important;
            backdrop-filter: blur(12px) !important;
            -webkit-backdrop-filter: blur(12px) !important;
            border-bottom: 1px solid rgba(203, 213, 225, 0.8) !important;
            box-shadow: 0 4px 14px rgba(18, 59, 93, 0.05) !important;
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
        }

        .tabular-nums { font-variant-numeric: tabular-nums; }
        .custom-scrollbar::-webkit-scrollbar { width: 4px; height: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: #F1F5F9; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 4px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #94A3B8; }
        
        .section-card {
            background: #FFFFFF;
            border-radius: 8px;
            border: 1px solid #E2E8F0;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
            position: relative;
        }
        .section-card:hover {
            box-shadow: 0 6px 18px rgba(18, 59, 93, 0.07);
            border-color: #CBD5E1;
        }
        
        /* Modern Info & Utility Action Buttons */
        .chart-action-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            border-radius: 6px;
            border: 1px solid #E2E8F0;
            background: #F8FAFC;
            color: #52606D;
            cursor: pointer;
            padding: 0;
            line-height: 1;
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
            flex-shrink: 0;
            box-shadow: 0 1px 2px rgba(0,0,0,0.02);
        }
        .chart-action-btn:hover {
            background: #123B5D;
            border-color: #123B5D;
            color: #FFFFFF;
            transform: scale(1.08);
            box-shadow: 0 3px 8px rgba(18, 59, 93, 0.2);
        }
        .chart-action-btn:active {
            transform: scale(0.94);
        }
        .chart-action-btn.active-state {
            background: #123B5D;
            border-color: #123B5D;
            color: #FFFFFF;
        }
        
        /* Drag and Drop Column Item Styles */
        .drag-col-item {
            user-select: none;
            transition: background-color 0.15s, border-color 0.15s, transform 0.15s;
        }
        .drag-col-item.dragging {
            opacity: 0.45;
            transform: scale(0.98);
            border: 1px dashed #123B5D !important;
            background: #F0F5F9 !important;
        }
        .drag-col-item.drag-over {
            border-top: 2px solid #123B5D !important;
            background: #EBF3F8 !important;
        }

__EXPLANATION_DIALOG_CSS__

        /* Fullscreen Focus Mode */
        @keyframes fullscreenExpand {
            0% { opacity: 0; transform: scale(0.97) translateY(8px); }
            100% { opacity: 1; transform: scale(1) translateY(0); }
        }
        .card-fullscreen {
            position: fixed !important;
            inset: 0 !important;
            z-index: 9999 !important;
            width: 100vw !important;
            height: 100vh !important;
            max-width: none !important;
            border-radius: 0 !important;
            padding: 1.5rem 2.5rem !important;
            background: #FFFFFF !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: flex-start !important;
            overflow: hidden !important;
            box-shadow: none !important;
            animation: fullscreenExpand 0.26s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        .card-fullscreen .card-header-wrap {
            flex-shrink: 0 !important;
            margin-bottom: 1rem !important;
            padding-bottom: 0.75rem !important;
            border-bottom: 1px solid #E2E8F0 !important;
        }
        .card-fullscreen .card-body-wrap {
            flex: 1 1 0% !important;
            height: calc(100vh - 120px) !important;
            min-height: 0 !important;
            width: 100% !important;
        }
        .card-fullscreen .card-chart-pane,
        .card-fullscreen .card-table-pane {
            width: 100% !important;
            height: 100% !important;
            animation: fadeInPane 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        @keyframes fadeInPane {
            from { opacity: 0; transform: translateY(4px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Toast Animation */
        @keyframes toastSlideUp {
            from { opacity: 0; transform: translate(-50%, 14px) scale(0.96); }
            to { opacity: 1; transform: translate(-50%, 0) scale(1); }
        }
        .toast-active {
            animation: toastSlideUp 0.24s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
    </style>
</head>
<body class="bg-[#F8FAFC] text-ink min-h-screen font-sans antialiased pb-20">

    <!-- App Root Container -->
    <div id="dashboard-app">
        <!-- 1. Header Area (Rendered by Engine) -->
        <header id="app-header" class="bg-white border-b border-slate-200 px-6 py-3.5 relative z-20 shadow-xs"></header>

        <!-- 2. Sticky Multi-Filter Bar (Rendered by Engine) -->
        <section id="app-filters" class="sticky-filter-bar border-b border-slate-200 z-30"></section>

        <!-- 3. Main Content Container -->
        <main class="max-w-[1600px] mx-auto px-6 pt-6 space-y-6">
            <!-- Tier 1: 4 Executive Metric Cards -->
            <section id="app-kpis" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4"></section>

            <!-- Tier 2: Responsive Charts Grid -->
            <section id="app-charts-grid" class="grid grid-cols-1 lg:grid-cols-2 gap-5"></section>

            <!-- Tier 3: 14-Column Full Aviation Table -->
            <section id="app-table-section" class="section-card p-5"></section>
        </main>

        <!-- 4. Native Dialog for Metrics & Chart Explanations -->
        __EXPLANATION_DIALOG_SHELL__

        <!-- 5. Toast Feedback Container -->
        <div id="app-toast-container" class="fixed bottom-6 right-6 z-50 flex flex-col gap-2 pointer-events-none"></div>
    </div>

    <!-- ================================================================= -->
    <!-- 📊 【数据配置层】 (DATA BLOCK / DASHBOARD_CONFIG)                   -->
    <!-- 核心业务数据、指标卡、图表数据源、表格配置与口径字典在此集中维护        -->
    <!-- ================================================================= -->
    <script id="dashboard-data">
__DASHBOARD_CONFIG_CODE__
    </script>

    <!-- ================================================================= -->
    <!-- 🚀 【渲染与交互引擎层】 (VIEW & INTERACTION ENGINE)                 -->
    <!-- 统一负责 DOM 渲染、ECharts 生命周期、全景联动与微操作控制器           -->
    <!-- ================================================================= -->
    <script id="dashboard-engine">
    (function() {
        'use strict';

        // 1. McKinsey / Bloomberg Design Tokens
        const TOKENS = {
            // Generated from scripts/core/palette.py: positive = 红涨, negative = 绿跌.
            palette: __ECHARTS_PALETTE__,
            commonOption: {
                color: __CATEGORICAL_COLORS__,
                animation: true,
                animationDuration: 350,
                grid: { top: 40, bottom: 40, left: 12, right: 24, containLabel: true },
                textStyle: { fontFamily: 'Inter, -apple-system, sans-serif', color: '#0F172A' },
                xAxis: {
                    axisLabel: { color: '#1E293B', fontSize: 11, fontWeight: 600 },
                    axisLine: { lineStyle: { color: '#94A3B8', width: 1.2 } },
                    axisTick: { lineStyle: { color: '#94A3B8' } },
                    splitLine: { lineStyle: { color: '#E2E8F0', type: 'dashed' } }
                },
                yAxis: {
                    axisLabel: { color: '#1E293B', fontSize: 11, fontWeight: 600 },
                    axisLine: { lineStyle: { color: '#94A3B8', width: 1.2 } },
                    axisTick: { lineStyle: { color: '#94A3B8' } },
                    splitLine: { lineStyle: { color: '#E2E8F0', type: 'dashed' } }
                }
            },
            axisTitleStyleY: { color: '#0B2A42', fontSize: 11, fontWeight: 700, align: 'left', padding: [0, 0, 6, 0] },
            axisTitleStyleX: { color: '#0B2A42', fontSize: 11, fontWeight: 700, align: 'center', padding: [8, 0, 0, 0] }
        };

        // Premium Lucide SVG Vector Icons (24x24 Pixel-Perfect Precision)
        const LUCIDE_ICONS = {
            plane: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/></svg>',
            globe: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>',
            barChart: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/></svg>',
            trendingUp: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>',
            compass: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>',
            award: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/></svg>',
            checkCircle: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="m9 12 2 2 4-4"/></svg>',
            maximize: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" x2="14" y1="3" y2="10"/><line x1="3" x2="10" y1="21" y2="14"/></svg>',
            minimize: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" x2="21" y1="10" y2="3"/><line x1="3" x2="10" y1="21" y2="14"/></svg>',
            viewToggle: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/></svg>',
            copy: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>',
            info: '__EXPLANATION_TRIGGER_ICON__',
            chevronDown: '<svg class="w-3.5 h-3.5 text-ink-subtle" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>',
            search: '<svg class="w-3.5 h-3.5 text-ink-subtle absolute left-2 top-2 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
            reset: '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>',
            export: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>',
            columns: '<svg class="w-3.5 h-3.5 text-ink-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M12 3v18"/></svg>',
            dragHandle: '<svg class="w-3 h-3 text-slate-400 cursor-grab active:cursor-grabbing mr-1.5 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor"><circle cx="8" cy="6" r="2"/><circle cx="16" cy="6" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="8" cy="18" r="2"/><circle cx="16" cy="18" r="2"/></svg>',
            layers: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.9a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/></svg>',
            calculator: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="16" height="20" x="4" y="2" rx="2"/><line x1="8" x2="16" y1="6" y2="6"/><line x1="16" x2="16" y1="14" y2="18"/><path d="M16 10h.01"/><path d="M12 10h.01"/><path d="M8 10h.01"/><path d="M12 14h.01"/><path d="M8 14h.01"/><path d="M12 18h.01"/><path d="M8 18h.01"/></svg>',
            close: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>',
            chartLine: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>',
            chartPie: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>',
            chartScatter: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="7.5" cy="7.5" r="1.5" fill="currentColor"/><circle cx="18.5" cy="5.5" r="1.5" fill="currentColor"/><circle cx="11.5" cy="11.5" r="1.5" fill="currentColor"/><circle cx="7.5" cy="16.5" r="1.5" fill="currentColor"/><circle cx="17.5" cy="14.5" r="1.5" fill="currentColor"/><path d="M3 3v18h18"/></svg>'
        };

        function getChartCategoryIcon(code) { return ""; }

        // 2. Universal Chart Data To Table Dynamic Converter Engine
        class ChartDataToTableConverter {
            static convert(inst, chartCfg) {
                if (!inst) return null;
                const opt = inst.getOption();
                if (!opt || !opt.series || opt.series.length === 0) return null;

                const series0 = opt.series[0];
                const seriesType = series0.type;

                // 1. Cartesian coordinate charts (Bar, Line, Scatter, Boxplot, Heatmap)
                if (opt.xAxis && opt.xAxis.length > 0 && opt.yAxis && opt.yAxis.length > 0) {
                    const xAxis = opt.xAxis[0];
                    const yAxis = opt.yAxis[0];
                    const xData = xAxis.data || (opt.xAxis[1] && opt.xAxis[1].data) || [];
                    const yData = yAxis.data || [];

                    // A. Horizontal Category (yAxis is Category)
                    if (yAxis.type === 'category' && yData.length > 0) {
                        const yTitle = yAxis.name || '维度项目';
                        const headers = [yTitle];
                        const activeSeries = opt.series.filter(s => s.data && s.data.length > 0 && s.itemStyle?.color !== 'transparent' && s.name && !s.name.includes('基准杆') && !s.name.includes('底槽'));
                        activeSeries.forEach(s => headers.push(s.name || '数值'));

                        const rows = yData.map((catName, idx) => {
                            const row = [catName];
                            activeSeries.forEach(s => {
                                let val = s.data?.[idx];
                                if (typeof val === 'object' && val !== null) val = val.value;
                                row.push(val !== undefined && val !== null ? (typeof val === 'number' ? val.toLocaleString() : val) : '-');
                            });
                            return row;
                        });
                        return { headers, rows };
                    }

                    // B. Vertical Category (xAxis is Category)
                    if (xData.length > 0) {
                        const xTitle = xAxis.name || '统计时段 / 类别';
                        const headers = [xTitle];
                        const activeSeries = opt.series.filter(s => s.data && s.data.length > 0 && s.itemStyle?.color !== 'transparent');
                        activeSeries.forEach(s => headers.push(s.name || '数值'));

                        const rows = xData.map((xVal, idx) => {
                            const row = [xVal];
                            activeSeries.forEach(s => {
                                let val = s.data?.[idx];
                                if (typeof val === 'object' && val !== null) val = val.value;
                                row.push(val !== undefined && val !== null ? (typeof val === 'number' ? val.toLocaleString() : val) : '-');
                            });
                            return row;
                        });
                        return { headers, rows };
                    }

                    // C. Scatter / Bubble / Quadrant
                    if (seriesType === 'scatter') {
                        const xName = xAxis.name || 'X 轴指标';
                        const yName = yAxis.name || 'Y 轴指标';
                        const headers = ['业务项目', xName, yName];
                        const sample = series0.data?.[0];
                        if (Array.isArray(sample) && sample.length >= 4) headers.push('体量 / 规模');

                        const rows = (series0.data || []).map(item => {
                            if (Array.isArray(item)) {
                                if (item.length === 3 && typeof item[2] === 'string') return [item[2], item[0], item[1]];
                                if (item.length >= 4 && typeof item[3] === 'string') return [item[3], item[0], item[1], item[2]];
                                return ['-', item[0], item[1]];
                            }
                            return ['-', item.value?.[0], item.value?.[1]];
                        });
                        return { headers, rows };
                    }

                    // D. Boxplot
                    if (seriesType === 'boxplot') {
                        const headers = [xAxis.name || '分类项目', '最小值 (Min)', '下四分位 (Q1)', '中位数 (Q2)', '上四分位 (Q3)', '最大值 (Max)'];
                        const rows = (xData || []).map((cat, idx) => {
                            const box = series0.data?.[idx] || [];
                            return [cat, box[0] ?? '-', box[1] ?? '-', box[2] ?? '-', box[3] ?? '-', box[4] ?? '-'];
                        });
                        return { headers, rows };
                    }

                    // E. Heatmap
                    if (seriesType === 'heatmap') {
                        const headers = [xAxis.name || 'X 轴时段', yAxis.name || 'Y 轴维度', '指数数值'];
                        const rows = (series0.data || []).map(cell => {
                            const xIdx = cell[0];
                            const yIdx = cell[1];
                            const val = cell[2];
                            return [xData[xIdx] || xIdx, yData[yIdx] || yIdx, val];
                        });
                        return { headers, rows };
                    }
                }

                // 2. Pie / Donut / Funnel
                if (seriesType === 'pie' || seriesType === 'funnel') {
                    const data = series0.data || [];
                    const total = data.reduce((acc, cur) => acc + (Number(cur.value) || 0), 0);
                    const headers = ['业务分类', '数值体量', '结构占比 (%)'];
                    const rows = data.map(item => {
                        const pct = total > 0 ? ((Number(item.value) / total) * 100).toFixed(1) + '%' : '-';
                        return [item.name || '-', typeof item.value === 'number' ? item.value.toLocaleString() : item.value, pct];
                    });
                    return { headers, rows };
                }

                // 3. Sankey
                if (seriesType === 'sankey') {
                    const links = series0.links || [];
                    const headers = ['资金流入源 (Source)', '流转目标端 (Target)', '流转金额 (亿元)'];
                    const rows = links.map(l => [l.source, l.target, l.value ? `¥${l.value} 亿` : '-']);
                    return { headers, rows };
                }

                // 4. Radar
                if (seriesType === 'radar') {
                    const indicators = opt.radar?.[0]?.indicator || [];
                    const headers = ['对标评估维度', ...(series0.data || []).map(d => d.name || '得分')];
                    const rows = indicators.map((ind, i) => {
                        const row = [ind.name];
                        (series0.data || []).forEach(d => row.push(d.value?.[i] ?? '-'));
                        return row;
                    });
                    return { headers, rows };
                }

                // 5. Sunburst / Treemap
                if (seriesType === 'sunburst' || seriesType === 'treemap') {
                    const headers = ['主板块', '细分子节点', '规模体量'];
                    const rows = [];
                    function traverse(nodes, parentName = '全网板块') {
                        nodes.forEach(node => {
                            if (node.children && node.children.length > 0) {
                                traverse(node.children, node.name);
                            } else {
                                rows.push([parentName, node.name, node.value ? `¥${node.value} 亿` : '-']);
                            }
                        });
                    }
                    traverse(series0.data || []);
                    return { headers, rows };
                }

                // Fallback
                return {
                    headers: ['项目', '数值'],
                    rows: (series0.data || []).map((v, i) => [`第 ${i + 1} 项`, typeof v === 'object' ? JSON.stringify(v) : v])
                };
            }
        }

        // 3. Global State Management (100% Dynamic & Zero-Data BI Engine)
__FILTER_BINDINGS_JS__

        class StateStore {
            constructor(config) {
                this.config = {...(config || {}), kpis: (config?.kpis || []).map(kpi => ({...kpi}))};
                const usedChartInstanceIds = new Set();
                this.config.charts = (this.config.charts || []).map((chart, index) => {
                    const rawIdentity = chart.instanceId || chart.id || chart.code || `component-${index + 1}`;
                    const safeIdentity = String(rawIdentity).toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
                    const requestedId = chart.instanceId || chart.id || `chart-${safeIdentity || 'component'}-${index + 1}`;
                    let instanceId = requestedId;
                    let duplicateIndex = 2;
                    while (usedChartInstanceIds.has(instanceId)) instanceId = `${requestedId}-${duplicateIndex++}`;
                    usedChartInstanceIds.add(instanceId);
                    return { ...chart, instanceId, id: instanceId };
                });
                
                // 1. Normalize Dynamic Filters Array
                let rawFilters = this.config.filters || [];
                let filterDefs = [];

                if (Array.isArray(rawFilters)) {
                    filterDefs = rawFilters.map((f, idx) => ({
                        id: f.id || f.key || `filter_${idx}`,
                        key: f.key || f.id || `filter_${idx}`,
                        label: f.label || `维度 ${idx + 1}`,
                        type: f.type || (f.options?.length > 0 && f.options[0]?.default !== undefined ? 'select' : 'select'),
                        fields: Array.isArray(f.fields) ? [...f.fields] : [],
                        componentIds: Array.isArray(f.componentIds) ? [...f.componentIds] : [],
                        options: (f.options || []).map(opt => ({
                            value: opt.value ?? opt.val ?? opt.name ?? '',
                            label: opt.label ?? opt.name ?? opt.val ?? '',
                            default: opt.default ?? opt.active ?? false
                        }))
                    }));
                } else if (typeof rawFilters === 'object') {
                    // Legacy Object Format Normalization
                    const labels = rawFilters.labels || {};
                    if (rawFilters.seasons && rawFilters.seasons.length) {
                        filterDefs.push({
                            key: 'period',
                            label: labels.time || '统计周期',
                            type: 'select',
                            options: rawFilters.seasons.map(s => ({ value: s.value || s.val, label: s.label, default: s.default || s.active }))
                        });
                    }
                    if (rawFilters.hubs && rawFilters.hubs.length) {
                        filterDefs.push({
                            key: 'hub',
                            label: labels.hub || '所属区域',
                            type: 'multi-select',
                            options: rawFilters.hubs.map(h => ({ value: h.value || h.val || h.name, label: h.label || h.name || h.val, default: h.default !== false }))
                        });
                    }
                    if (rawFilters.fleets && rawFilters.fleets.length) {
                        filterDefs.push({
                            key: 'fleet',
                            label: labels.fleet || '业务业态',
                            type: 'select',
                            options: rawFilters.fleets.map(fl => ({ value: fl.value || fl.val, label: fl.label, default: fl.val === 'ALL' || fl.value === 'ALL' }))
                        });
                    }
                    if (rawFilters.routes && rawFilters.routes.length) {
                        filterDefs.push({
                            key: 'route',
                            label: labels.route || '业务渠道',
                            type: 'select',
                            options: rawFilters.routes.map(r => ({ value: r.value || r.val, label: r.label, default: r.val === 'ALL' || r.value === 'ALL' }))
                        });
                    }
                }

                this.filterDefs = filterDefs;

                // 2. Initialize Filter States & Defaults
                this.filterValues = {};
                this.filterLabels = {};
                this.defaultFilterValues = {};
                this.defaultFilterLabels = {};

                filterDefs.forEach(f => {
                    if (f.type === 'multi-select') {
                        const defSelected = f.options.filter(o => o.default).map(o => o.value);
                        const allVals = f.options.map(o => o.value);
                        const initialSet = new Set(defSelected.length > 0 ? defSelected : allVals);
                        this.filterValues[f.key] = initialSet;
                        this.defaultFilterValues[f.key] = new Set(initialSet);
                        this.filterLabels[f.key] = initialSet.size === allVals.length ? `全部${f.label}` : `已选 ${initialSet.size} 项`;
                        this.defaultFilterLabels[f.key] = this.filterLabels[f.key];
                    } else {
                        const defOpt = f.options.find(o => o.default) || f.options[0] || { value: 'ALL', label: `全部${f.label}` };
                        this.filterValues[f.key] = defOpt.value;
                        this.defaultFilterValues[f.key] = defOpt.value;
                        this.filterLabels[f.key] = defOpt.label;
                        this.defaultFilterLabels[f.key] = defOpt.label;
                    }
                });

                this.keyword = '';
                this.chartCrossFilter = null;

                // Backward-compatible filters proxy
                this.filters = {
                    time: this.filterValues['period'] || 'CURRENT',
                    timeLabel: this.filterLabels['period'] || '全周期',
                    hubs: this.filterValues['hub'] || new Set(),
                    fleet: this.filterValues['fleet'] || 'ALL',
                    fleetLabel: this.filterLabels['fleet'] || '全部',
                    route: this.filterValues['route'] || 'ALL',
                    routeLabel: this.filterLabels['route'] || '全部',
                    keyword: '',
                    chartCrossFilter: null
                };

                this.table = {
                    page: 1,
                    pageSize: 10,
                    sortCol: null,
                    sortDir: 'asc',
                    orderedColumns: [...(this.config.table?.columns || [])],
                    visibleCols: new Set((this.config.table?.columns || []).map(c => c.key))
                };
                this.chartInstances = {};
                this.chartGranularities = {};
            }
        }

        // 4. UI Renderer with Multi-Style High-Impact KPI Cards & Consulting Design Tokens
        function parseKPIValue(value) {
            const number = Number.parseFloat(String(value ?? '').replace(/,/g, ''));
            return Number.isFinite(number) ? number : null;
        }

        // 红涨绿跌: signed changes color by direction; unsigned values stay neutral.
        function trendDirection(value) {
            if (typeof value === 'number') return value > 0 ? 1 : value < 0 ? -1 : 0;
            const text = String(value ?? '').trim();
            if (/^[↑▲]/.test(text)) return 1;
            if (/^[↓▼]/.test(text)) return -1;
            const match = text.match(/^([-+＋−－])[ ]*[¥$€]?[ ]*([0-9.,]+)/);
            if (!match || !(Number.parseFloat(match[2].replace(/,/g, '')) > 0)) return 0;
            return '+＋'.includes(match[1]) ? 1 : -1;
        }

        function trendTextClass(value, neutralClass = 'text-ink-muted') {
            const direction = trendDirection(value);
            return direction > 0 ? 'text-positive' : direction < 0 ? 'text-negative' : neutralClass;
        }

        function comparisonText(value) {
            if (typeof value === 'number') return Number.isFinite(value) ? (value > 0 ? '+' : '') + value : '—';
            return value ?? '—';
        }

        function trendBadgeClass(value) {
            const direction = trendDirection(value);
            if (direction > 0) return 'bg-positive/10 text-positive border-positive/20';
            if (direction < 0) return 'bg-negative/10 text-negative border-negative/20';
            return 'bg-slate-100 text-ink-muted border-slate-200';
        }

        class DashboardRenderer {
            constructor(state, root = document) {
                this.state = state;
                this.config = state.config;
                this.root = root;
            }

            getById(id) {
                return this.root.getElementById?.(id) || this.root.querySelector?.(`#${CSS.escape(id)}`);
            }

            query(selector) {
                return this.root.querySelector(selector);
            }

            renderHeader() {
                const meta = this.config.meta;
                const container = this.getById('app-header');
                if (!container) return;

                // Match Lucide Icon
                let iconSvg = LUCIDE_ICONS.plane;
                if (meta.iconKey && LUCIDE_ICONS[meta.iconKey]) iconSvg = LUCIDE_ICONS[meta.iconKey];
                else if (meta.title.includes('效能') || meta.title.includes('监控')) iconSvg = LUCIDE_ICONS.trendingUp;
                else if (meta.title.includes('财务') || meta.title.includes('成本')) iconSvg = LUCIDE_ICONS.barChart;
                else if (meta.title.includes('全谱系') || meta.title.includes('综合')) iconSvg = LUCIDE_ICONS.globe;
                else if (meta.title.includes('矩阵') || meta.title.includes('战略')) iconSvg = LUCIDE_ICONS.compass;

                container.innerHTML = `
                    <div class="max-w-[1600px] mx-auto flex flex-wrap items-center justify-between gap-4">
                        <div class="flex items-center gap-3">
                            <div class="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-white font-bold text-sm shadow-sm border border-slate-700/30">
                                ${iconSvg}
                            </div>
                            <div>
                                <h1 class="text-base font-bold text-primary-strong tracking-tight">${meta.title}</h1>
                                <p class="text-[11px] text-ink-subtle">${[meta.org, meta.system].filter(Boolean).join(' · ') || '商业智能与运营决策中心 · 决策支持系统'}</p>
                            </div>
                        </div>
                        <div class="flex items-center gap-3 text-xs">
                            <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#123B5D]/6 border border-[#123B5D]/15 text-[#123B5D] text-xs font-mono font-medium">
                                <span class="w-1.5 h-1.5 rounded-full bg-primary"></span>
                                ${meta.statusText || '全域多维数据实时协同'}
                            </span>
                        </div>
                    </div>
                `;
            }

            renderFilters() {
                const defs = this.state.filterDefs;
                const container = this.getById('app-filters');
                if (!container) return;

                let filterControlsHtml = '';
                defs.forEach(f => {
                    if (f.type === 'multi-select') {
                        const curSet = this.state.filterValues[f.key] || new Set();
                        const curLabel = this.state.filterLabels[f.key] || `全部${f.label}`;
                        const badgeCount = curSet.size;

                        const optionsHtml = f.options.map(opt => `
                            <label class="flex items-center justify-between p-1.5 hover:bg-slate-50 rounded cursor-pointer text-xs filter-opt-row" data-label="${opt.label}">
                                <span class="flex items-center gap-2">
                                    <input type="checkbox" value="${opt.value}" ${curSet.has(opt.value) ? 'checked' : ''} onchange="window.App.onMultiFilterChange('${f.key}')" class="rounded text-primary focus:ring-0">
                                    <span class="font-medium">${opt.label}</span>
                                </span>
                            </label>
                        `).join('');

                        filterControlsHtml += `
                            <div class="relative" id="filterWrap_${f.key}" data-component-id="${f.id}">
                                <button onclick="window.App.toggleDropdown('filterMenu_${f.key}', event)" class="h-[32px] px-3 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-md text-xs font-medium text-ink flex items-center gap-2 transition focus:outline-none focus:border-primary">
                                    <span class="text-ink-subtle">${f.label}:</span>
                                    <span id="selectedLabel_${f.key}" class="font-semibold text-primary truncate max-w-[130px]">${curLabel}</span>
                                    <span id="countBadge_${f.key}" class="bg-primary text-white text-[10px] px-1.5 py-0.2 rounded-full font-mono">${badgeCount}</span>
                                    ${LUCIDE_ICONS.chevronDown}
                                </button>
                                <div id="filterMenu_${f.key}" class="hidden absolute top-full left-0 mt-1.5 w-64 bg-white border border-slate-200 rounded-lg shadow-xl p-2.5 z-50 space-y-2">
                                    <div class="relative">
                                        <input type="text" oninput="window.App.filterMultiDropdown('${f.key}', this.value)" placeholder="搜索${f.label}..." class="w-full text-xs pl-7 pr-2 py-1 bg-slate-50 border border-slate-200 rounded text-ink focus:outline-none focus:border-primary focus:bg-white">
                                        <svg class="w-3.5 h-3.5 text-ink-subtle absolute left-2 top-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                                    </div>
                                    <div class="flex items-center justify-between text-[11px] text-ink-subtle pb-1 border-b border-slate-100">
                                        <button onclick="window.App.setAllMultiOptions('${f.key}', true)" class="hover:text-primary font-medium">全选</button>
                                        <span class="text-slate-300">|</span>
                                        <button onclick="window.App.setAllMultiOptions('${f.key}', false)" class="hover:text-primary font-medium">清空</button>
                                        <span class="ml-auto text-[10px] text-ink-subtle">多选过滤</span>
                                    </div>
                                    <div class="space-y-1 max-h-44 overflow-y-auto custom-scrollbar" id="multiOptionsContainer_${f.key}">
                                        ${optionsHtml}
                                    </div>
                                </div>
                            </div>
                        `;
                    } else {
                        // Single Select Dropdown
                        const curVal = this.state.filterValues[f.key];
                        const curLabel = this.state.filterLabels[f.key] || f.options[0]?.label || `全部${f.label}`;

                        const optionsHtml = f.options.map(opt => `
                            <div onclick="window.App.selectFilterOption('${f.key}', '${opt.value}', '${opt.label}')" class="px-3 py-2 text-xs text-ink hover:bg-slate-50 cursor-pointer flex items-center justify-between font-medium">
                                <span>${opt.label}</span>
                                ${opt.value === curVal ? '<span class="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-mono font-semibold">当前</span>' : ''}
                            </div>
                        `).join('');

                        filterControlsHtml += `
                            <div class="relative" id="filterWrap_${f.key}" data-component-id="${f.id}">
                                <button onclick="window.App.toggleDropdown('filterMenu_${f.key}', event)" class="h-[32px] px-3 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-md text-xs font-medium text-ink flex items-center gap-2 transition focus:outline-none focus:border-primary">
                                    <span class="text-ink-subtle">${f.label}:</span>
                                    <span id="selectedLabel_${f.key}" class="font-semibold text-primary truncate max-w-[130px]">${curLabel}</span>
                                    ${LUCIDE_ICONS.chevronDown}
                                </button>
                                <div id="filterMenu_${f.key}" class="hidden absolute top-full left-0 mt-1.5 min-w-48 bg-white border border-slate-200 rounded-lg shadow-xl py-1 z-50">
                                    <div class="px-2.5 py-1 text-[10px] font-bold text-ink-subtle uppercase border-b border-slate-100">选择${f.label}</div>
                                    ${optionsHtml}
                                </div>
                            </div>
                        `;
                    }
                });

                const sampleCols = (this.config.table?.columns || []).filter(c => c.align !== 'right').slice(0, 3).map(c => c.title);
                const searchPh = sampleCols.length > 0 ? `检索${sampleCols.join('、')}...` : '输入关键词全局检索...';

                container.innerHTML = `
                    <div class="max-w-[1600px] mx-auto px-6 py-3">
                        <div class="flex flex-wrap items-center justify-between gap-3">
                            <!-- Left Controls -->
                            <div class="flex flex-wrap items-center gap-2.5">
                                ${filterControlsHtml}

                                <!-- Global Keyword Search -->
                                <div class="relative" id="globalSearchWrap">
                                    <div class="relative flex items-center">
                                        <input type="text" id="globalKeywordSearch" onfocus="window.App.showSearchSuggestions()" oninput="window.App.onSearchInput(this.value)" onkeydown="window.App.onSearchKeyDown(event)" placeholder="${searchPh}" class="h-[32px] w-48 text-xs pl-7 pr-7 bg-slate-50 border border-slate-200 rounded-md text-ink placeholder:text-ink-subtle focus:outline-none focus:border-primary focus:bg-white focus:w-64 transition-all" autocomplete="off">
                                        ${LUCIDE_ICONS.search}
                                        <button id="clearSearchBtn" onclick="window.App.clearSearchKeyword(event)" class="hidden absolute right-2 w-4 h-4 rounded-full bg-slate-200 hover:bg-slate-300 text-ink text-[10px] font-bold flex items-center justify-center transition-colors">✕</button>
                                    </div>
                                    <div id="searchSuggestionsDropdown" class="hidden absolute left-0 top-full mt-1.5 w-80 bg-white border border-slate-200 rounded-lg shadow-2xl p-2.5 z-60 text-xs custom-scrollbar max-h-80 overflow-y-auto">
                                        <div id="searchSuggestionsContent"></div>
                                    </div>
                                </div>
                            </div>

                            <!-- Right Status & Reset -->
                            <div class="flex items-center gap-3">
                                <div class="flex items-center gap-1.5 text-xs text-ink-subtle">
                                    <span>已生效条件:</span>
                                    <span id="activeFilterBadgeCount" class="inline-flex items-center justify-center bg-primary text-white font-mono text-[11px] font-bold h-5 min-w-[20px] px-1 rounded-full">0</span>
                                </div>
                                <button onclick="window.App.resetAllGlobalFilters()" class="h-[32px] px-3 bg-slate-100 hover:bg-slate-200 text-ink-muted hover:text-ink text-xs font-semibold rounded-md transition flex items-center gap-1.5">
                                    ${LUCIDE_ICONS.reset}
                                    <span>一键重置</span>
                                </button>
                            </div>
                        </div>

                        <!-- Active Chips Tray -->
                        <div id="activeChipsTray" class="hidden pt-2.5 mt-2.5 border-t border-slate-100 flex flex-wrap items-center gap-2">
                            <span class="text-[11px] text-ink-subtle font-medium">当前检索聚焦:</span>
                            <div id="chipsContainer" class="flex flex-wrap items-center gap-1.5"></div>
                            <button onclick="window.App.resetAllGlobalFilters()" class="text-[11px] text-primary hover:underline ml-2 font-medium">清空所有条件</button>
                        </div>
                    </div>
                `;
            }

            renderKPIs() {
                const kpis = this.config.kpis || [];
                const container = this.getById('app-kpis');
                if (!container) return;

                const markup = kpis.map(kpi => {
                    const cardType = kpi.type || 'mc01';

                    // 1. mc01: Standard Value Card
                    if (cardType === 'mc01') {
                        return `
                            <div class="section-card p-4 flex flex-col justify-between">
                                <div class="flex items-center justify-between mb-1">
                                    <span class="text-xs text-ink-muted font-medium">${kpi.label}</span>
                                    <div class="flex items-center gap-1.5">
                                        <span class="inline-flex items-center gap-1.5 text-[10px] text-primary bg-primary/5 border border-primary/15 px-2 py-0.5 rounded font-medium">
                                            <span class="w-1.5 h-1.5 rounded-full bg-primary"></span>${kpi.statusBadge || '核算中'}
                                        </span>
                                        <button class="chart-explain-btn" data-explain-chart="${kpi.explainKey || 'mc01'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                    </div>
                                </div>
                                <div class="flex items-baseline gap-2 my-1">
                                    <span class="text-2xl font-extrabold text-primary-strong tracking-tight font-mono tabular-nums">${kpi.value ?? '—'}</span>
                                    <span class="text-xs font-semibold ${trendTextClass(kpi.yoy)} font-mono">${comparisonText(kpi.yoy)}</span>
                                </div>
                                <div class="pt-2 mt-1 border-t border-slate-100 text-[11px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '统计口径'}</span>
                                    <span class="text-primary font-semibold">${kpi.subVal ?? '—'}</span>
                                </div>
                            </div>
                        `;
                    }

                    // 2. mc02: YoY / MoM Delta Card
                    if (cardType === 'mc02') {
                        return `
                            <div class="section-card p-4 flex flex-col justify-between">
                                <div class="flex items-center justify-between mb-1">
                                    <span class="text-xs text-ink-muted font-medium">${kpi.label}</span>
                                    <button class="chart-explain-btn" data-explain-chart="${kpi.explainKey || 'mc02'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="flex items-baseline gap-2 my-1">
                                    <span class="text-2xl font-extrabold text-primary-strong tracking-tight font-mono tabular-nums">${kpi.value ?? '—'}</span>
                                </div>
                                <div class="flex items-center gap-1.5 my-1">
                                    <span class="inline-flex items-center gap-0.5 px-2 py-0.5 rounded text-[10px] font-bold border ${trendBadgeClass(kpi.yoy)} font-mono">同比 ${comparisonText(kpi.yoy)}</span>
                                    <span class="inline-flex items-center gap-0.5 px-2 py-0.5 rounded text-[10px] font-bold border ${trendBadgeClass(kpi.mom)} font-mono">环比 ${comparisonText(kpi.mom)}</span>
                                </div>
                                <div class="pt-2 mt-1 border-t border-slate-100 text-[11px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '同比增量'}</span>
                                    <span class="${trendTextClass(kpi.subVal, 'text-primary')} font-semibold">${kpi.subVal ?? '—'}</span>
                                </div>
                            </div>
                        `;
                    }

                    // 3. mc03: Sparkline Area Mini-Chart Card (Real Interactive Dynamic ECharts Sparkline)
                    if (cardType === 'mc03') {
                        return `
                            <div class="section-card p-4 flex flex-col justify-between">
                                <div class="flex items-center justify-between mb-1">
                                    <span class="text-xs text-ink-muted font-medium">${kpi.label}</span>
                                    <button class="chart-explain-btn" data-explain-chart="${kpi.explainKey || 'mc03'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="flex items-baseline justify-between gap-2">
                                    <div class="flex items-baseline gap-1.5">
                                        <span class="text-2xl font-extrabold text-primary-strong tracking-tight font-mono tabular-nums">${kpi.value ?? '—'}</span>
                                        <span class="text-xs font-bold ${trendTextClass(kpi.yoy)} font-mono">${comparisonText(kpi.yoy)}</span>
                                    </div>
                                    <span class="text-[10px] font-semibold border ${trendBadgeClass(kpi.trendLabel)} px-1.5 py-0.5 rounded font-mono">${kpi.trendLabel ?? '—'}</span>
                                </div>
                                <div id="kpi-spark-${kpi.id}" class="w-full h-11 my-1"></div>
                                <div class="pt-1.5 border-t border-slate-100 text-[10px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '周期均值'}</span>
                                    <span class="text-ink-muted font-semibold">${kpi.subVal ?? '—'}</span>
                                </div>
                            </div>
                        `;
                    }

                    // 4. mc04: Goal & Progress Bar Card
                    if (cardType === 'mc04') {
                        const progress = parseKPIValue(kpi.value);
                        const barWidth = Math.max(0, Math.min(100, progress ?? 0));
                        return `
                            <div class="section-card p-4 flex flex-col justify-between">
                                <div class="flex items-center justify-between mb-1">
                                    <span class="text-xs text-ink-muted font-medium">${kpi.label}</span>
                                    <button class="chart-explain-btn" data-explain-chart="${kpi.explainKey || 'mc04'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="flex items-baseline justify-between my-0.5">
                                    <span class="text-2xl font-extrabold text-primary-strong tracking-tight font-mono tabular-nums">${kpi.value ?? '—'}</span>
                                    <span class="text-[11px] font-bold ${trendTextClass(kpi.yoy, 'text-primary')} font-mono">${comparisonText(kpi.yoy)}</span>
                                </div>
                                <div class="w-full bg-slate-200/80 h-2.5 rounded-full overflow-hidden my-1.5">
                                    <div class="bg-primary h-full rounded-full transition-all" style="width: ${barWidth}%;"></div>
                                </div>
                                <div class="pt-1.5 border-t border-slate-100 text-[11px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '考核目标'}</span>
                                    <span class="${trendTextClass(kpi.subVal, 'text-primary')} font-bold">${kpi.subVal ?? '—'}</span>
                                </div>
                            </div>
                        `;
                    }

                    // 5. mc05: Mini Semi-Gauge Card (Real Dynamic ECharts Semi-Gauge)
                    if (cardType === 'mc05') {
                        return `
                            <div class="section-card p-4 flex flex-col justify-between">
                                <div class="flex items-center justify-between mb-1">
                                    <span class="text-xs text-ink-muted font-medium">${kpi.label}</span>
                                    <button class="chart-explain-btn" data-explain-chart="${kpi.explainKey || 'mc05'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="flex items-baseline justify-between gap-2">
                                    <div class="flex items-baseline gap-1.5">
                                        <span class="text-2xl font-extrabold text-primary-strong tracking-tight font-mono tabular-nums">${kpi.value ?? '—'}</span>
                                    </div>
                                    <span class="text-[10px] text-primary font-semibold bg-primary/8 border border-primary/20 px-1.5 py-0.5 rounded font-mono">${kpi.gaugeSub ?? '—'}</span>
                                </div>
                                <div id="kpi-gauge-${kpi.id}" class="w-full h-11 my-1"></div>
                                <div class="pt-1.5 border-t border-slate-100 text-[10px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '行业基准'}</span>
                                    <span class="${trendTextClass(kpi.subVal)} font-semibold">${kpi.subVal ?? '—'}</span>
                                </div>
                            </div>
                        `;
                    }

                    // 6. mc06: Dual-Metric Split Card
                    if (cardType === 'mc06') {
                        return `
                            <div class="section-card p-4 flex flex-col justify-between">
                                <div class="flex items-center justify-between mb-1">
                                    <span class="text-xs text-ink-muted font-medium">${kpi.label}</span>
                                    <button class="chart-explain-btn" data-explain-chart="${kpi.explainKey || 'mc06'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="grid grid-cols-2 gap-2 divide-x divide-slate-100 my-1">
                                    <div>
                                        <span class="text-[10px] text-ink-subtle block">${kpi.leftTitle || '规模指标'}</span>
                                        <div class="text-lg font-extrabold text-primary-strong font-mono tabular-nums">${kpi.leftVal ?? '—'}</div>
                                        <span class="text-[10px] ${trendTextClass(kpi.leftYoy)} font-bold font-mono">${comparisonText(kpi.leftYoy)}</span>
                                    </div>
                                    <div class="pl-2">
                                        <span class="text-[10px] text-ink-subtle block">${kpi.rightTitle || '效能指标'}</span>
                                        <div class="text-lg font-extrabold text-primary font-mono tabular-nums">${kpi.rightVal ?? '—'}</div>
                                        <span class="text-[10px] ${trendTextClass(kpi.rightYoy)} font-bold font-mono">${comparisonText(kpi.rightYoy)}</span>
                                    </div>
                                </div>
                                <div class="pt-2 mt-1 border-t border-slate-100 text-[11px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '周转匹配率'}</span>
                                    <span class="text-primary font-semibold">${kpi.subVal ?? '—'}</span>
                                </div>
                            </div>
                        `;
                    }

                    // 6. mc07: Ranking Tier Badge Card
                    if (cardType === 'mc07') {
                        return `
                            <div class="section-card p-4 flex flex-col justify-between">
                                <div class="flex items-center justify-between mb-1">
                                    <span class="text-xs text-ink-muted font-medium">${kpi.label}</span>
                                    <button class="chart-explain-btn" data-explain-chart="${kpi.explainKey || 'mc07'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="flex items-center justify-between my-1">
                                    <div class="flex items-center gap-2">
                                        <span class="w-7 h-7 rounded-full bg-[#9A6A18]/10 border border-[#9A6A18]/25 text-[#9A6A18] flex items-center justify-center font-bold text-xs shadow-xs">
                                            ${LUCIDE_ICONS.award}
                                        </span>
                                        <div>
                                            <span class="text-sm font-extrabold text-primary-strong">${kpi.value ?? '—'}</span>
                                            <p class="text-[10px] text-ink-subtle">${kpi.rankSub ?? '—'}</p>
                                        </div>
                                    </div>
                                    <span class="px-2 py-0.5 rounded bg-primary text-white text-[11px] font-mono font-bold">${kpi.rankBadge ?? '—'}</span>
                                </div>
                                <div class="pt-2 mt-1 border-t border-slate-100 text-[11px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '市场占有率'}</span>
                                    <span class="text-primary font-semibold">${kpi.subVal ?? '—'}</span>
                                </div>
                            </div>
                        `;
                    }

                    // 7. mc08: Threshold Alert Card
                    if (cardType === 'mc08') {
                        return `
                            <div class="section-card p-4 flex flex-col justify-between border-[#9A6A18]/30 bg-[#9A6A18]/5">
                                <div class="flex items-center justify-between mb-1">
                                    <span class="text-xs font-semibold text-[#9A6A18] flex items-center gap-1.5">
                                        <span class="w-2 h-2 rounded-full bg-[#9A6A18] animate-pulse"></span>
                                        ${kpi.label}
                                    </span>
                                    <button class="chart-explain-btn" data-explain-chart="${kpi.explainKey || 'mc08'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="flex items-baseline gap-2 my-1">
                                    <span class="text-2xl font-extrabold text-[#0B2A42] tracking-tight font-mono tabular-nums">${kpi.value ?? '—'}</span>
                                    <span class="px-2 py-0.5 rounded bg-[#9A6A18]/15 border border-[#9A6A18]/30 text-[#9A6A18] text-[10px] font-bold font-mono">${kpi.alertLabel ?? '—'}</span>
                                </div>
                                <div class="pt-2 mt-1 border-t border-[#9A6A18]/20 text-[11px] text-ink-muted flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '成本占比'}</span>
                                    <span class="font-bold text-[#9A6A18]">${kpi.subVal ?? '—'}</span>
                                </div>
                            </div>
                        `;
                    }

                    // 8. mc09: Segment Breakdown Card
                    if (cardType === 'mc09') {
                        return `
                            <div class="section-card p-4 flex flex-col justify-between">
                                <div class="flex items-center justify-between mb-1">
                                    <span class="text-xs text-ink-muted font-medium">${kpi.label}</span>
                                    <button class="chart-explain-btn" data-explain-chart="${kpi.explainKey || 'mc09'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="flex items-baseline justify-between my-0.5">
                                    <span class="text-xl font-extrabold text-primary-strong tracking-tight font-mono tabular-nums">${kpi.value ?? '—'}</span>
                                    <span class="text-[10px] ${trendTextClass(kpi.yoy, 'text-ink-subtle')} font-mono">${comparisonText(kpi.yoy)}</span>
                                </div>
                                <div class="w-full h-2.5 rounded-full overflow-hidden flex my-1.5 shadow-inner bg-slate-100">
                                    <div class="bg-primary h-full transition-all" style="width: ${parseKPIValue(kpi.segLeftWidth) ?? 0}%;"></div>
                                    <div class="bg-[#8EA4B8] h-full transition-all" style="width: ${parseKPIValue(kpi.segRightWidth) ?? 0}%;"></div>
                                </div>
                                <div class="pt-1.5 border-t border-slate-100 text-[10px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-primary"></span>${kpi.subLabel ?? '—'}</span>
                                    <span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-[#8EA4B8]"></span>${kpi.subVal ?? '—'}</span>
                                </div>
                            </div>
                        `;
                    }

                    // Default Standard Card Fallback
                    return `
                        <div class="section-card p-4 flex flex-col justify-between">
                            <div class="flex items-center justify-between mb-1">
                                <span class="text-xs text-ink-muted font-medium">${kpi.label}</span>
                                <button class="chart-explain-btn" data-explain-chart="${kpi.explainKey || 'mc01'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                            </div>
                            <div class="flex items-baseline gap-2 my-1">
                                <span class="text-2xl font-extrabold text-primary-strong tracking-tight font-mono tabular-nums">${kpi.value ?? '—'}</span>
                                <span class="text-xs font-semibold ${trendTextClass(kpi.yoy)} font-mono">${comparisonText(kpi.yoy)}</span>
                            </div>
                            <div class="pt-2 mt-1 border-t border-slate-100 text-[11px] text-ink-subtle flex items-center justify-between font-mono">
                                <span>${kpi.subLabel ?? '—'}</span>
                                <span class="text-primary font-semibold">${kpi.subVal ?? '—'}</span>
                            </div>
                        </div>
                    `;
                }).join('');
                if (!document.createElement) { container.innerHTML = markup; return; }
                const draft = document.createElement('div');
                draft.innerHTML = markup;
                Array.from(draft.children).forEach((card, index) => {
                    const componentId = kpis[index]?.id || `kpi-${index + 1}`;
                    card.id = componentId;
                    card.dataset.componentId = componentId;
                    card.dataset.kpiType = kpis[index]?.type || 'mc01';
                    card.dataset.kpiSignature = JSON.stringify(kpis[index]);
                    const old = Array.from(container.children).find(node => node.dataset.componentId === componentId);
                    if (old && old.dataset.kpiSignature === card.dataset.kpiSignature) { container.appendChild(old); return; }
                    if (old && old.dataset.kpiType === card.dataset.kpiType) {
                        old.dataset.kpiSignature = card.dataset.kpiSignature;
                        // Keep widget hosts (and their ECharts canvas) while refreshing card text.
                        card.querySelectorAll('[id^="kpi-spark-"], [id^="kpi-gauge-"]').forEach(host => {
                            const existing = old.querySelector(`#${CSS.escape(host.id)}`);
                            if (existing) host.replaceWith(existing);
                        });
                        const chrome = old.querySelector('.component-header');
                        if (chrome) {
                            chrome.remove();
                            // The embedding adapter owns the header and its aligned body slots.
                            card.firstElementChild?.remove();
                            if (old.classList.contains('kpi-aligned')) {
                                const sections = Array.from(card.children);
                                const value = sections.shift();
                                const footer = sections.pop();
                                const aux = document.createElement('div');
                                aux.className = 'kpi-aux';
                                aux.append(...sections);
                                value?.classList.add('kpi-headline');
                                footer?.classList.add('kpi-footer');
                                card.replaceChildren(...(value ? [value] : []), aux, ...(footer ? [footer] : []));
                            }
                        }
                        old.replaceChildren(...card.childNodes);
                        if (chrome) old.prepend(chrome);
                        container.appendChild(old);
                    } else { old?.remove(); container.appendChild(card); }
                });
                const ids = new Set(kpis.map((kpi, index) => kpi.id || `kpi-${index + 1}`));
                Array.from(container.children).forEach(card => { if (!ids.has(card.dataset.componentId)) card.remove(); });
            }

            renderChartsGrid() {
                const charts = this.config.charts || [];
                const container = this.getById('app-charts-grid');
                if (!container) return;

                const markup = charts.map(chart => {
                    const colClass = chart.colSpan === 2 ? 'lg:col-span-2' : '';
                    const granTabs = chart.hasGranularity ? `
                        <div class="inline-flex bg-slate-100/90 p-0.5 rounded-md text-[11px]">
                            <button type="button" class="granularity-tab-btn px-2 py-0.5 rounded bg-white text-primary-strong font-semibold shadow-xs" data-component-id="${chart.instanceId}" data-granularity="month">月度</button>
                            <button type="button" class="granularity-tab-btn px-2 py-0.5 rounded text-ink-muted hover:text-ink font-medium" data-component-id="${chart.instanceId}" data-granularity="quarter">季度</button>
                        </div>
                    ` : '';

                    return `
                        <div class="section-card p-5 flex flex-col justify-between ${colClass}" data-component-id="${chart.instanceId}" data-chart-code="${chart.code || ''}">
                            <!-- Card Header -->
                            <div class="card-header-wrap flex flex-wrap items-start justify-between gap-3 mb-3" id="header-${chart.instanceId}">
                                <div class="min-w-0 max-w-[65%]">
                                    <div class="flex items-center gap-2">
                                        <h3 class="text-sm font-bold text-primary-strong tracking-tight truncate">${chart.title}</h3>
                                        ${chart.code ? `<span class="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-slate-100 text-slate-600 border border-slate-200 flex-shrink-0">${chart.code.toUpperCase()}</span>` : ''}
                                    </div>
                                    <p class="text-xs text-ink-muted mt-0.5 leading-relaxed truncate">${chart.subtitle || ''}</p>
                                </div>
                                <div class="flex items-center gap-1.5 flex-shrink-0">
                                    ${granTabs}
                                    <!-- View Toggle (Chart ↔ Table) -->
                                    <button type="button" class="chart-action-btn view-toggle-btn" data-component-id="${chart.instanceId}" aria-label="切换图表/数据表视图" title="切换图表/动态数据表视图">
                                        ${LUCIDE_ICONS.viewToggle}
                                    </button>
                                    <!-- Export Chart CSV -->
                                    <button type="button" class="chart-action-btn export-chart-btn" data-component-id="${chart.instanceId}" data-chart-title="${chart.title}" aria-label="导出图表数据为 CSV / Excel" title="导出图表当前结构化数据 (CSV / Excel)">
                                        ${LUCIDE_ICONS.export}
                                    </button>
                                    <!-- Copy Chart PNG -->
                                    <button type="button" class="chart-action-btn copy-chart-btn" data-component-id="${chart.instanceId}" data-chart-title="${chart.title}" aria-label="复制高清图表至剪贴板" title="复制高清图表至剪贴板 (可直接粘贴入 PPT)">
                                        ${LUCIDE_ICONS.copy}
                                    </button>
                                    <!-- Fullscreen Focus -->
                                    <button type="button" class="chart-action-btn fullscreen-btn" data-component-id="${chart.instanceId}" aria-label="全屏沉浸研判" title="全屏沉浸研判 (Esc退出)">
                                        ${LUCIDE_ICONS.maximize}
                                    </button>
                                    <!-- Info Dialog -->
                                    <button type="button" class="chart-explain-btn" data-explain-chart="${chart.explainKey || chart.code}" aria-label="查看业务口径说明" title="查看业务口径与计算公式说明">
                                        ${LUCIDE_ICONS.info}
                                    </button>
                                </div>
                            </div>
                            <!-- Card Body Pane -->
                            <div class="card-body-wrap relative w-full h-[270px] overflow-hidden">
                                <div id="${chart.id}" class="card-chart-pane w-full h-full"></div>
                                <div id="table-pane-${chart.instanceId}" class="card-table-pane hidden w-full h-full"></div>
                            </div>
                        </div>
                    `;
                }).join('');
                if (!document.createElement) { container.innerHTML = markup; return; }
                const draft = document.createElement('div');
                draft.innerHTML = markup;
                const retained = new Set();
                Array.from(draft.children).forEach(card => {
                    const old = Array.from(container.children).find(node => node.dataset.componentId === card.dataset.componentId && node.dataset.chartCode === card.dataset.chartCode);
                    const target = old || card;
                    if (old && !old.querySelector('.component-header')) {
                        old.querySelector('.card-header-wrap')?.replaceWith(card.querySelector('.card-header-wrap'));
                        old.className = card.className;
                        const granularity = this.state.chartGranularities[card.dataset.componentId] || 'month';
                        old.querySelectorAll('.granularity-tab-btn').forEach(button => {
                            const active = button.dataset.granularity === granularity;
                            button.classList.toggle('bg-white', active);
                            button.classList.toggle('text-primary-strong', active);
                            button.classList.toggle('font-semibold', active);
                            button.classList.toggle('shadow-xs', active);
                            button.classList.toggle('text-ink-muted', !active);
                        });
                    }
                    retained.add(target);
                    container.appendChild(target);
                });
                Array.from(container.children).forEach(card => { if (!retained.has(card)) card.remove(); });
            }

            renderTableSection() {
                const tableCfg = this.config.table;
                const container = this.getById('app-table-section');
                if (!container) return;
                container.dataset.componentId = tableCfg.id || 'table';

                container.innerHTML = `
                    <div class="flex flex-wrap items-center justify-between gap-4 mb-4 pb-3 border-b border-slate-100">
                        <div class="flex items-center gap-2">
                            <span class="w-2.5 h-2.5 rounded-full bg-primary flex-shrink-0"></span>
                            <h3 data-dashboard-table-title class="text-sm font-bold text-primary-strong tracking-tight">${tableCfg.title || '全要素业务运营效能多维透视表'}</h3>
                            
                        </div>
                        <div class="flex items-center gap-2">
                            <!-- Column Manager Drawer Toggle -->
                            <div class="relative" id="colDrawerWrap">
                                <button id="colDrawerBtn" onclick="window.App.toggleColumnDrawer(event)" class="px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-xs font-semibold rounded-md shadow-2xs flex items-center gap-1.5 transition-colors cursor-pointer">
                                    ${LUCIDE_ICONS.columns}
                                    <span>自定义列配置</span>
                                </button>
                                <div id="colDrawerMenu" class="hidden absolute right-0 top-full mt-2 w-72 bg-white border border-slate-200 rounded-lg shadow-xl p-3 z-60 text-xs max-h-96 overflow-y-auto custom-scrollbar">
                                    <div class="font-bold text-primary-strong pb-2 mb-2 border-b border-slate-100 flex items-center justify-between">
                                        <div class="flex items-center gap-1.5">
                                            <span>列显隐与拖拽排序</span>
                                            <span class="text-[10px] text-ink-subtle font-normal">(按住拖动)</span>
                                        </div>
                                        <button onclick="window.App.resetDefaultColumns()" class="text-[10px] text-primary hover:underline font-normal cursor-pointer">恢复默认</button>
                                    </div>
                                    <div id="colCheckboxesContainer" class="space-y-1 text-xs text-ink"></div>
                                </div>
                            </div>

                            <!-- Table Export CSV -->
                            <button onclick="window.App.exportTableToCSV()" class="px-3 py-1.5 bg-primary text-white hover:bg-primary-strong text-xs font-semibold rounded-md shadow-xs flex items-center gap-1.5 transition-colors cursor-pointer">
                                ${LUCIDE_ICONS.export}
                                <span>导出 Excel (CSV)</span>
                            </button>

                            <!-- Table Info Button -->
                            <button class="chart-explain-btn" data-explain-chart="table_airline_main" aria-label="查看表格指标说明" title="查看表格指标说明">
                                ${LUCIDE_ICONS.info}
                            </button>
                        </div>
                    </div>

                    <!-- 14-Column Multi-Metric Table -->
                    <div class="border border-slate-200 rounded-lg overflow-hidden bg-white shadow-2xs">
                        <div class="overflow-x-auto custom-scrollbar w-full">
                            <table class="w-full text-xs text-left border-collapse min-w-[1450px]" id="main14ColTable">
                                <thead id="main14ColThead" class="bg-slate-50/90 text-primary-strong font-bold border-b border-slate-200 select-none">
                                    <!-- Dynamic Columns -->
                                </thead>
                                <tbody id="main14ColTbody" class="divide-y divide-slate-100">
                                    <!-- Dynamic Rows -->
                                </tbody>
                            </table>
                        </div>
                        <!-- Table Pagination Bar -->
                        <div class="px-4 py-3 bg-slate-50/80 border-t border-slate-200 flex flex-wrap items-center justify-between gap-3 text-xs text-ink-muted">
                            <div class="flex items-center gap-2">
                                <span id="tablePaginationInfo">显示第 1 - 10 条 · 共 35 条记录</span>
                                <span class="text-slate-300">|</span>
                                <label class="flex items-center gap-1.5">
                                    <span>每页</span>
                                    <select onchange="window.App.onTablePageSizeChange(this.value)" class="bg-white border border-slate-200 rounded px-2 py-1 text-xs text-ink focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 cursor-pointer">
                                        <option value="10" selected>10 条</option>
                                        <option value="25">25 条</option>
                                        <option value="50">50 条</option>
                                        <option value="all">全部</option>
                                    </select>
                                </label>
                            </div>
                            <div class="flex items-center gap-1">
                                <button id="tablePrevBtn" onclick="window.App.prevTablePage()" class="px-2.5 py-1 bg-white border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed rounded text-xs text-ink">上一页</button>
                                <span id="tablePageIndicator" class="px-2.5 font-mono font-bold text-ink text-xs">1 / 4</span>
                                <button id="tableNextBtn" onclick="window.App.nextTablePage()" class="px-2.5 py-1 bg-white border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed rounded text-xs text-ink">下一页</button>
                            </div>
                        </div>
                    </div>
                `;
            }

            renderDialog() {
                const container = this.getById('app-explain-dialog');
                if (!container) return;
                container.className = 'explanation-dialog';
                container.innerHTML = '';
            }

            renderExplanationDialogContent(chartKey, explanations) {
                const cardEl = this.query(`[data-explain-chart="${chartKey}"]`)?.closest('.section-card');
                const defaultTitle = cardEl?.querySelector('h3')?.textContent || cardEl?.querySelector('.text-ink-muted')?.textContent || '业务经营分析指标说明';

                const chartCfg = (this.config.charts || []).find(c => c.code === chartKey || c.id === chartKey || c.explainKey === chartKey);
                const rawExp = explanations?.[chartKey] || (chartCfg ? explanations?.[chartCfg.code] : null) || {};

                const expTitle = rawExp.title || chartCfg?.title || defaultTitle;
                const expOverview = rawExp.overview || chartCfg?.desc || `${expTitle}：聚焦业务关键量化指标的多维演变、构成分布与核心效能，辅助管理层开展战略研判与运营决算。`;
                const expType = rawExp.type || "高管经营分析图表";
                const expPeriod = rawExp.period || this.state.filters.timeLabel || "报告考核期";
                const expComparison = rawExp.comparison || "按企业统一经营管理会计口径";

                let structure = rawExp.structure;
                if (!structure || !structure.xAxis || !structure.yAxis) {
                    structure = {
                        xAxis: { name: "统计维度", meaning: "业务时间序列、分类层级或组织架构单元", range: "全量口径范围" },
                        yAxis: { name: "核心量纲", meaning: "业务结算金额 (万元/亿元) 或比率指标 (%)", range: "自适应区间" },
                        series: [{ name: "执行数据序列", desc: "业务实际经营核算结果" }]
                    };
                }

                let metrics = rawExp.metrics;
                if (!metrics || metrics.length === 0) {
                    metrics = [
                        {
                            name: expTitle,
                            definition: expOverview,
                            formula: "∑ 各业务单元实际发生值 ÷ 考核基准数 × 100%",
                            rule: "遵循企业经营管理会计与统计决算标准规范，定期开展异常波动核验。"
                        }
                    ];
                }

                return renderSharedExplanationDialogContent({
                    title: expTitle,
                    overview: expOverview,
                    type: expType,
                    period: expPeriod,
                    comparison: expComparison,
                    structure,
                    metrics
                });
            }
        }

__EXPLANATION_DIALOG_RENDERER_JS__

        // 5. Main Application Controller
        class DashboardApp {
            constructor(config, root = document) {
                this.config = config;
                this.root = root;
                this.state = new StateStore(config);
                this.config = this.state.config;
                this.renderer = new DashboardRenderer(this.state, root);
                this.draggedColKey = null;
                this._mounted = false;
                this._eventController = null;
                this._resizeObserver = null;
                this._timers = new Set();
                this._chartTableCleanups = new Map();
            }

            getById(id) {
                return this.root.getElementById?.(id) || this.root.querySelector?.(`#${CSS.escape(id)}`);
            }

            query(selector) {
                return this.root.querySelector(selector);
            }

            queryAll(selector) {
                return this.root.querySelectorAll(selector);
            }

            init() {
                if (this._mounted) return this;
                this._mounted = true;
                this.root.__dashboardApp = this;
                this._eventController = new AbortController();
                // Render DOM structure
                this.renderer.renderHeader();
                this.renderer.renderFilters();
                this.renderer.renderKPIs();
                this.renderer.renderChartsGrid();
                this.renderer.renderTableSection();
                this.renderer.renderDialog();

                // Initialize ECharts instances & KPI Micro-Widgets
                this.initCharts();
                this.initKPIWidgets();

                // Initialize Table
                this.renderColCheckboxes();
                this.renderTableEngine();

                // Bind Global Event Listeners
                this.bindEvents();
                this.updateKPIsAndChartsFromFilters();
                return this;
            }

            setChartOption(instance, option) {
                // Replace data-bearing components to remove deleted series, retaining user selections.
                const previous = instance.getOption?.() || {};
                if (option.legend && previous.legend) {
                    const legends = Array.isArray(option.legend) ? option.legend : [option.legend];
                    legends.forEach((legend, index) => { legend.selected = {...previous.legend[index]?.selected, ...legend.selected}; });
                }
                if (option.dataZoom && previous.dataZoom) {
                    const zooms = Array.isArray(option.dataZoom) ? option.dataZoom : [option.dataZoom];
                    zooms.forEach((zoom, index) => {
                        const old = zoom.id ? previous.dataZoom.find(item => item.id === zoom.id) : previous.dataZoom[index];
                        if (old) Object.assign(zoom, {start: old.start, end: old.end});
                    });
                }
                instance.setOption(option, {replaceMerge: ['series', 'dataset', 'xAxis', 'yAxis', 'legend', 'dataZoom']});
            }

            updateConfig(config) {
                const next = new StateStore(config);
                const kpisChanged = JSON.stringify(this.config.kpis) !== JSON.stringify(next.config.kpis);
                const tableChanged = this.config.table !== next.config.table;
                const filtersChanged = JSON.stringify(this.config.filters) !== JSON.stringify(next.config.filters);
                const metaChanged = JSON.stringify(this.config.meta) !== JSON.stringify(next.config.meta);
                const oldCharts = new Map((this.config.charts || []).map(chart => [chart.instanceId, chart]));
                const changedCharts = new Set(next.config.charts.filter(chart => JSON.stringify(oldCharts.get(chart.instanceId)) !== JSON.stringify(chart) || String(oldCharts.get(chart.instanceId)?.optionBuilder) !== String(chart.optionBuilder) || (chart.binding && (tableChanged || filtersChanged))).map(chart => chart.instanceId));
                const compatible = new Set(next.config.charts.filter(chart => oldCharts.get(chart.instanceId)?.code === chart.code).map(chart => chart.instanceId));
                const oldKPIs = new Map((this.config.kpis || []).map(kpi => [kpi.id, kpi.type || 'mc01']));
                next.config.kpis.forEach(kpi => {
                    if (oldKPIs.get(kpi.id) === (kpi.type || 'mc01')) {
                        if (kpi.type === 'mc03') compatible.add(`kpi-spark-${kpi.id}`);
                        if (kpi.type === 'mc05') compatible.add(`kpi-gauge-${kpi.id}`);
                    }
                });
                Object.entries(this.state.chartInstances).forEach(([id, instance]) => {
                    if (!compatible.has(id)) { this._chartTableCleanups.get(id)?.(); instance.dispose(); delete this.state.chartInstances[id]; }
                });
                const table = this.state.table;
                const columns = next.table.orderedColumns;
                const columnMap = new Map(columns.map(column => [column.key, column]));
                const ordered = table.orderedColumns.filter(column => columnMap.has(column.key)).map(column => columnMap.get(column.key));
                const known = new Set(ordered.map(column => column.key));
                ordered.push(...columns.filter(column => !known.has(column.key)));
                table.orderedColumns = ordered;
                table.visibleCols = new Set(columns.filter(column => table.visibleCols.has(column.key) || !known.has(column.key)).map(column => column.key));
                if (!columnMap.has(table.sortCol)) table.sortCol = null;
                const suppliedTableState = config.tableState ?? config.table?.tableState;
                if (suppliedTableState) {
                    if (Array.isArray(suppliedTableState.columns)) {
                        const keys = [...new Set(suppliedTableState.columns)].filter(key => columnMap.has(key));
                        table.orderedColumns = [...keys.map(key => columnMap.get(key)), ...ordered.filter(column => !keys.includes(column.key))];
                    }
                    if (Array.isArray(suppliedTableState.visible)) table.visibleCols = new Set(suppliedTableState.visible.filter(key => columnMap.has(key)));
                    if (Number.isInteger(suppliedTableState.page) && suppliedTableState.page > 0) table.page = suppliedTableState.page;
                    if (Number.isInteger(suppliedTableState.pageSize) && suppliedTableState.pageSize > 0) table.pageSize = suppliedTableState.pageSize;
                    if (Object.hasOwn(suppliedTableState, 'sortCol')) table.sortCol = columnMap.has(suppliedTableState.sortCol) ? suppliedTableState.sortCol : null;
                    if (['asc', 'desc'].includes(suppliedTableState.sortDir)) table.sortDir = suppliedTableState.sortDir;
                }
                this.config = this.state.config = next.config;
                if (filtersChanged) {
                    this.state.filterValues = next.filterValues;
                    this.state.filterLabels = next.filterLabels;
                    this.state.defaultFilterValues = next.defaultFilterValues;
                    this.state.defaultFilterLabels = next.defaultFilterLabels;
                    this.state.filters = next.filters;
                }
                this.state.filterDefs = next.filterDefs;
                this.renderer.config = this.config;
                if (metaChanged) this.renderer.renderHeader();
                if (filtersChanged) this.renderer.renderFilters();
                const tableSection = this.getById('app-table-section');
                if (tableSection && this.config.table) {
                    tableSection.dataset.componentId = this.config.table.id || 'table';
                    const title = tableSection.querySelector('[data-dashboard-table-title]');
                    if (title) title.textContent = this.config.table.title || '全要素业务运营效能多维透视表';
                    const size = tableSection.querySelector('select[onchange], select[data-original-change]');
                    if (size) size.value = table.pageSize === 9999 ? 'all' : String(table.pageSize);
                }
                if (kpisChanged) this.renderer.renderKPIs();
                this.renderer.renderChartsGrid();
                this.initCharts();
                if (kpisChanged) this.initKPIWidgets();
                this.renderColCheckboxes();
                this.renderTableEngine();
                this.updateKPIsAndChartsFromFilters(changedCharts);
                return this;
            }

            initKPIWidgets() {
                const kpis = this.config.kpis || [];
                kpis.forEach(kpi => {
                    // 1. mc03: Sparkline Micro Chart
                    if (kpi.type === 'mc03') {
                        const dom = this.getById(`kpi-spark-${kpi.id}`);
                        if (dom) {
                            const months = kpi.sparkMonths;
                            const seriesData = kpi.sparkData;
                            if (!Array.isArray(months) || !Array.isArray(seriesData) || !seriesData.length || months.length !== seriesData.length) {
                                this.state.chartInstances[`kpi-spark-${kpi.id}`]?.clear();
                                return;
                            }
                            const inst = echarts.getInstanceByDom?.(dom) || echarts.init(dom);
                            this.state.chartInstances[`kpi-spark-${kpi.id}`] = inst;
                            const minVal = Math.floor(Math.min(...seriesData) * 0.95);
                            const maxVal = Math.ceil(Math.max(...seriesData) * 1.05);

                            inst.setOption({
                                animation: true,
                                animationDuration: 400,
                                grid: { top: 4, bottom: 2, left: 2, right: 2 },
                                tooltip: {
                                    trigger: 'axis',
                                    backgroundColor: 'rgba(255, 255, 255, 0.98)',
                                    borderColor: TOKENS.palette.rule,
                                    borderWidth: 1,
                                    padding: [4, 8],
                                    extraCssText: 'box-shadow: 0 2px 8px rgba(18, 59, 93, 0.08); border-radius: 4px; z-index: 50;',
                                    formatter: params => {
                                        const p = params[0];
                                        return `<div class="text-[11px] font-mono"><span class="font-bold text-primary">${p.name}:</span> <span class="font-bold text-ink">${p.value}${kpi.unit ? ' ' + kpi.unit : ''}</span></div>`;
                                    }
                                },
                                xAxis: { type: 'category', show: false, data: months },
                                yAxis: { type: 'value', show: false, min: minVal, max: maxVal },
                                series: [{
                                    type: 'line',
                                    smooth: 0.35,
                                    showSymbol: false,
                                    data: seriesData,
                                    lineStyle: { color: TOKENS.palette.primary, width: 2.2 },
                                    itemStyle: { color: TOKENS.palette.primary },
                                    areaStyle: {
                                        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                                            { offset: 0, color: 'rgba(18, 59, 93, 0.30)' },
                                            { offset: 1, color: 'rgba(18, 59, 93, 0.02)' }
                                        ])
                                    }
                                }]
                            });
                        }
                    }

                    // 2. mc05: Mini Semi-Gauge
                    if (kpi.type === 'mc05') {
                        const dom = this.getById(`kpi-gauge-${kpi.id}`);
                        if (dom) {
                            const val = parseKPIValue(kpi.value);
                            if (val === null) return;
                            const inst = echarts.getInstanceByDom?.(dom) || echarts.init(dom);
                            this.state.chartInstances[`kpi-gauge-${kpi.id}`] = inst;
                            inst.setOption({
                                animation: true,
                                series: [{
                                    type: 'gauge',
                                    startAngle: 180,
                                    endAngle: 0,
                                    min: 0,
                                    max: 100,
                                    radius: '140%',
                                    center: ['50%', '85%'],
                                    progress: { show: true, width: 7, itemStyle: { color: TOKENS.palette.primary } },
                                    axisLine: { lineStyle: { width: 7, color: [[1, '#E2E8F0']] } },
                                    axisTick: { show: false },
                                    splitLine: { show: false },
                                    axisLabel: { show: false },
                                    pointer: { show: false },
                                    detail: { show: false },
                                    data: [{ value: val }]
                                }]
                            });
                        }
                    }
                });
            }

            scheduleChartResize(instance) {
                if (!instance) return;
                this._pendingChartResize ||= new Set();
                this._pendingChartResize.add(instance);
                if (this._chartResizeFrame) return;
                this._chartResizeFrame = requestAnimationFrame(() => {
                    this._chartResizeFrame = null;
                    for (const chart of this._pendingChartResize) {
                        if (chart.isDisposed()) continue;
                        const dom = chart.getDom();
                        if (dom.isConnected && dom.clientWidth > 0 && dom.clientHeight > 0) chart.resize();
                    }
                    this._pendingChartResize.clear();
                });
            }

            initCharts() {
                const charts = this.config.charts || [];
                charts.forEach(chartCfg => {
                    const dom = this.getById(chartCfg.id);
                    if (!dom) return;
                    if (this.state.chartInstances[chartCfg.instanceId]) return;
                    const inst = echarts.getInstanceByDom?.(dom) || echarts.init(dom);
                    this.state.chartInstances[chartCfg.instanceId] = inst;
                    this.state.chartGranularities[chartCfg.instanceId] = chartCfg.defaultGranularity || 'month';

                    // Build and set option
                    const opt = chartCfg.optionBuilder(chartCfg.data, this.state.chartGranularities[chartCfg.instanceId], TOKENS, chartCfg);
                    inst.setOption(opt);

                    // Bind Cross Filtering
                    inst.on('click', (params) => {
                        if (params.name) {
                            const nameClean = params.name.split(' ')[0];
                            this.setTableCrossFilter(nameClean);
                        }
                    });
                });

                // ResizeObserver for zero-height prevention & responsive layout
                if (window.ResizeObserver) {
                    const observer = new ResizeObserver((entries) => {
                        for (const entry of entries) {
                            const inst = echarts.getInstanceByDom(entry.target);
                            if (inst && entry.contentRect.width > 0 && entry.contentRect.height > 0) {
                                this.scheduleChartResize(inst);
                            }
                        }
                    });
                    this._resizeObserver?.disconnect();
                    this._resizeObserver = observer;
                    this.queryAll('.card-chart-pane, .section-card div[id^="kpi-spark-"], .section-card div[id^="kpi-gauge-"]').forEach(el => observer.observe(el));
                }

                if (!this._resizeBound) {
                this._resizeBound = true;
                window.addEventListener('resize', () => {
                    Object.values(this.state.chartInstances).forEach(inst => this.scheduleChartResize(inst));
                }, { signal: this._eventController.signal });
                }
            }

            bindEvents() {
                const eventOptions = { signal: this._eventController.signal };
                // Dropdown dismiss on outside click
                this.root.addEventListener('click', (e) => {
                    if (!e.target.closest('[id^="filter"]') && !e.target.closest('[id$="DropdownMenu"]') && !e.target.closest('#colDrawerWrap') && !e.target.closest('#globalSearchWrap')) {
                        this.queryAll('[id$="DropdownMenu"]').forEach(m => m.classList.add('hidden'));
                        this.getById('colDrawerMenu')?.classList.add('hidden');
                        this.getById('searchSuggestionsDropdown')?.classList.add('hidden');
                    }
                }, eventOptions);

                // Explain Modal Trigger
                const modal = this.getById('app-explain-dialog');
                this.root.addEventListener('click', (e) => {
                    const btn = e.target.closest('[data-explain-chart]');
                    if (btn && modal) {
                        const code = btn.getAttribute('data-explain-chart');
                        const htmlContent = this.renderer.renderExplanationDialogContent(code, this.config.explanations);
                        modal.innerHTML = htmlContent;

                        this.getById('closeExplainModalBtn')?.addEventListener('click', () => modal?.close(), eventOptions);
                        if (typeof modal.showModal === 'function') {
                            modal.showModal();
                        } else {
                            modal.setAttribute('open', '');
                        }
                    }
                }, eventOptions);

                modal?.addEventListener('click', (e) => {
                    const rect = modal.getBoundingClientRect();
                    if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {
                        modal.close();
                    }
                }, eventOptions);

                // Granularity Switcher
                this.root.addEventListener('click', (e) => {
                    const tabBtn = e.target.closest('.granularity-tab-btn');
                    if (tabBtn) {
                        const code = tabBtn.getAttribute('data-component-id');
                        const gran = tabBtn.getAttribute('data-granularity');
                        const parent = tabBtn.parentElement;
                        parent.querySelectorAll('.granularity-tab-btn').forEach(b => {
                            b.classList.remove('bg-white', 'text-primary-strong', 'font-semibold', 'shadow-xs');
                            b.classList.add('text-ink-muted');
                        });
                        tabBtn.classList.remove('text-ink-muted');
                        tabBtn.classList.add('bg-white', 'text-primary-strong', 'font-semibold', 'shadow-xs');

                        const chartCfg = (this.config.charts || []).find(c => c.instanceId === code);
                        const inst = this.state.chartInstances[code];
                        if (chartCfg && inst) {
                            this.state.chartGranularities[code] = gran;
                            const newOpt = chartCfg.optionBuilder(chartCfg.data, gran, TOKENS, chartCfg);
                            this.setChartOption(inst, newOpt);
                            
                            // If table pane is active, refresh table dynamically
                            const card = tabBtn.closest('.section-card');
                            const tablePane = card.querySelector('.card-table-pane');
                            if (tablePane && !tablePane.classList.contains('hidden')) {
                                this.renderDynamicChartTable(code, tablePane);
                            }
                            
                            this.showToast(`已切换为${gran === 'month' ? '月度' : '季度'}统计口径`);
                        }
                    }
                }, eventOptions);

                // View Toggle (Chart ↔ Dynamic Auto-Converted Table)
                this.root.addEventListener('click', (e) => {
                    const btn = e.target.closest('.view-toggle-btn');
                    if (btn) {
                        const code = btn.getAttribute('data-component-id');
                        const card = btn.closest('.section-card');
                        const chartPane = card.querySelector('.card-chart-pane');
                        const tablePane = card.querySelector('.card-table-pane');

                        if (chartPane && tablePane) {
                            const isTableHidden = tablePane.classList.contains('hidden');
                            if (isTableHidden) {
                                chartPane.classList.add('hidden');
                                tablePane.classList.remove('hidden');
                                btn.classList.add('active-state');
                                
                                // Auto convert current ECharts instance data to structured table
                                this.renderDynamicChartTable(code, tablePane);
                                this.showToast('已呈现图表结构化数据');
                            } else {
                                this._chartTableCleanups.get(code)?.();
                                tablePane.classList.add('hidden');
                                chartPane.classList.remove('hidden');
                                btn.classList.remove('active-state');
                                this.state.chartInstances[code]?.resize();
                                this.showToast('已切回 ECharts 可视化图表视图');
                            }
                        }
                    }
                }, eventOptions);

                // Export Chart CSV Data (One Click per Chart)
                this.root.addEventListener('click', (e) => {
                    const btn = e.target.closest('.export-chart-btn');
                    if (btn) {
                        const code = btn.getAttribute('data-component-id');
                        const title = btn.getAttribute('data-chart-title') || '图表数据';
                        const inst = this.state.chartInstances[code];
                        const chartCfg = (this.config.charts || []).find(c => c.instanceId === code);
                        
                        const tdata = ChartDataToTableConverter.convert(inst, chartCfg);
                        if (tdata && tdata.headers && tdata.rows) {
                            const headerStr = tdata.headers.map(h => `"${h}"`).join(',');
                            const rowsStr = tdata.rows.map(r => r.map(v => `"${v}"`).join(','));
                            const csv = '\\uFEFF' + [headerStr, ...rowsStr].join('\\r\\n');
                            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            const gran = this.state.chartGranularities[code] || 'month';
                            const granText = gran === 'quarter' ? '季度' : '月度';
                            a.download = `${title}_${granText}数据_${new Date().toISOString().slice(0,10)}.csv`;
                            a.click();
                            URL.revokeObjectURL(url);
                            this.showToast(`已成功导出「${title}」${tdata.rows.length} 项数据至 Excel (CSV)`);
                        } else {
                            this.showToast('图表数据提取失败，请检查图表配置');
                        }
                    }
                }, eventOptions);

                // Copy Chart to Clipboard
                this.root.addEventListener('click', (e) => {
                    const btn = e.target.closest('.copy-chart-btn');
                    if (btn) {
                        const code = btn.getAttribute('data-component-id');
                        const inst = this.state.chartInstances[code];
                        if (inst) {
                            try {
                                const url = inst.getDataURL({ pixelRatio: 2, backgroundColor: '#FFFFFF' });
                                fetch(url).then(res => res.blob()).then(blob => {
                                    navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]).then(() => {
                                        this.showToast('图表高清图片已复制至剪贴板，可直接粘贴入 PPT / Word！');
                                    });
                                });
                            } catch (err) {
                                this.showToast('复制图表失败，请使用系统截图');
                            }
                        }
                    }
                }, eventOptions);

                // Fullscreen Focus Mode
                this.root.addEventListener('click', (e) => {
                    const btn = e.target.closest('.fullscreen-btn');
                    if (btn) {
                        const code = btn.getAttribute('data-component-id');
                        const card = btn.closest('.section-card');
                        const isFull = card.classList.contains('card-fullscreen');
                        if (!isFull) {
                            card.classList.add('card-fullscreen');
                            btn.innerHTML = LUCIDE_ICONS.minimize;
                            btn.setAttribute('title', '退出全屏研判 (Esc)');
                            this.showToast('已进入全屏沉浸研判模式 (按 ESC 退出)');
                        } else {
                            card.classList.remove('card-fullscreen');
                            btn.innerHTML = LUCIDE_ICONS.maximize;
                            btn.setAttribute('title', '全屏沉浸研判 (Esc退出)');
                            this.showToast('已退出全屏研判模式');
                        }
                        setTimeout(() => this.state.chartInstances[code]?.resize(), 100);
                        setTimeout(() => this.state.chartInstances[code]?.resize(), 300);
                    }
                }, eventOptions);

                // Esc to exit fullscreen
                window.addEventListener('keydown', (e) => {
                    if (e.key === 'Escape') {
                        this.queryAll('.card-fullscreen').forEach(card => {
                            card.classList.remove('card-fullscreen');
                            const btn = card.querySelector('.fullscreen-btn');
                            if (btn) {
                                btn.innerHTML = LUCIDE_ICONS.maximize;
                                btn.setAttribute('title', '全屏沉浸研判 (Esc退出)');
                            }
                        });
                        Object.values(this.state.chartInstances).forEach(i => i?.resize());
                    }
                }, eventOptions);
            }

            renderDynamicChartTable(code, tablePane) {
                const scrollTop = tablePane.firstElementChild?.scrollTop || 0;
                this._chartTableCleanups.get(code)?.();
                const inst = this.state.chartInstances[code];
                const chartCfg = (this.config.charts || []).find(c => c.instanceId === code);
                const tdata = ChartDataToTableConverter.convert(inst, chartCfg);
                if (tdata && tdata.headers && tdata.rows) {
                    const rowMarkup = (r, index) => `
                        <tr aria-rowindex="${index + 2}" class="hover:bg-slate-50 transition-colors ${index % 2 ? 'bg-slate-50/50' : ''}">
                            ${r.map((v, i) => `<td class="px-3 py-2 font-mono text-[11px] text-[#17212B] border-b border-slate-100 ${i > 0 ? 'font-semibold' : ''}">${v}</td>`).join('')}
                        </tr>`;
                    tablePane.innerHTML = `
                        <div class="w-full h-full overflow-auto bg-white rounded border border-slate-200 custom-scrollbar">
                            <table class="w-full text-xs text-left border-separate border-spacing-0">
                                <thead class="sticky top-0 z-20">
                                    <tr>
                                        ${tdata.headers.map(h => `
                                            <th class="px-3 py-2.5 whitespace-nowrap bg-[#F1F5F9] text-[#0B2A42] font-bold text-[11px] border-b border-slate-200 sticky top-0 z-20 shadow-2xs">
                                                ${h}
                                            </th>
                                        `).join('')}
                                    </tr>
                                </thead>
                                <tbody class="text-ink">
                                </tbody>
                            </table>
                        </div>
                    `;
                    const table = tablePane.querySelector('table');
                    table.setAttribute('aria-rowcount', String(tdata.rows.length + 1));
                    table.setAttribute('aria-colcount', String(tdata.headers.length));
                    const body = table.querySelector('tbody');
                    if (tdata.rows.length <= 100) body.innerHTML = tdata.rows.map(rowMarkup).join('');
                    else this.renderChartTableWindow(code, table, tdata.rows, rowMarkup, scrollTop);
                }
            }

            renderChartTableWindow(code, table, rows, rowMarkup, scrollTop) {
                const scroller = table.parentElement, body = table.querySelector('tbody');
                // Let the browser size columns using representative full-data values, then
                // freeze those widths so recycling rows cannot move the header or columns.
                const widest = rows[0].slice();
                rows.forEach(row => row.forEach((value, column) => {
                    if (String(value ?? '').length > String(widest[column] ?? '').length) widest[column] = value;
                }));
                body.innerHTML = rowMarkup(widest, 0) + rows.slice(0, 12).map(rowMarkup).join('');
                const headers = Array.from(table.querySelectorAll('thead th'));
                const widths = headers.map(header => header.getBoundingClientRect().width);
                headers.forEach((header, index) => { header.style.width = `${widths[index]}px`; });
                table.style.tableLayout = 'fixed';
                table.style.width = `${widths.reduce((sum, width) => sum + width, 0)}px`;
                table.style.minWidth = '100%';
                const estimate = body.children[1]?.getBoundingClientRect().height || 32;
                // Prefix sums of measured height differences keep wrapped rows accurate
                // without scanning every row while scrolling.
                const heights = new Map(), tree = new Float64Array(rows.length + 1);
                const prefix = count => {
                    let value = count * estimate;
                    for (let i = count; i > 0; i -= i & -i) value += tree[i];
                    return value;
                };
                const indexAt = offset => {
                    let low = 0, high = rows.length;
                    while (low < high) {
                        const mid = Math.floor((low + high) / 2);
                        if (prefix(mid + 1) <= offset) low = mid + 1; else high = mid;
                    }
                    return Math.min(rows.length - 1, low);
                };
                const measure = (index, height) => {
                    if (!height) return;
                    const delta = height - (heights.get(index) ?? estimate);
                    heights.set(index, height);
                    for (let i = index + 1; i < tree.length; i += i & -i) tree[i] += delta;
                };
                const spacer = height => `<tr aria-hidden="true"><td colspan="${headers.length}" style="height:${Math.max(0, height)}px;padding:0;border:0;line-height:0"></td></tr>`;
                let frame = null, disposed = false, start = -1, end = -1, lastWidth = scroller.clientWidth;
                scroller.style.overflowAnchor = 'none';
                const draw = () => {
                    frame = null;
                    if (disposed || !scroller.clientHeight || !scroller.clientWidth) return;
                    const headerHeight = table.tHead.getBoundingClientRect().height;
                    const viewport = Math.max(1, scroller.clientHeight - headerHeight);
                    const atBottom = scroller.scrollTop > 0 && scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 2;
                    if (lastWidth !== scroller.clientWidth) {
                        lastWidth = scroller.clientWidth;
                        heights.clear(); tree.fill(0); start = end = -1;
                    }
                    const anchor = indexAt(scroller.scrollTop), within = scroller.scrollTop - prefix(anchor);
                    const nextStart = Math.max(0, anchor - 6);
                    const nextEnd = Math.min(rows.length, indexAt(scroller.scrollTop + viewport) + 7);
                    if (nextStart !== start || nextEnd !== end) {
                        start = nextStart; end = nextEnd;
                        body.innerHTML = spacer(prefix(start)) + rows.slice(start, end).map((row, i) => rowMarkup(row, start + i)).join('') + spacer(prefix(rows.length) - prefix(end));
                    }
                    Array.from(body.children).slice(1, -1).forEach((row, i) => measure(start + i, row.getBoundingClientRect().height));
                    body.firstElementChild.firstElementChild.style.height = `${prefix(start)}px`;
                    body.lastElementChild.firstElementChild.style.height = `${Math.max(0, prefix(rows.length) - prefix(end))}px`;
                    scroller.scrollTop = atBottom ? scroller.scrollHeight - scroller.clientHeight : prefix(anchor) + within;
                    if (end < rows.length && prefix(end) < scroller.scrollTop + viewport) schedule();
                };
                const schedule = () => { if (!disposed && frame === null) frame = requestAnimationFrame(draw); };
                const observer = new ResizeObserver(schedule);
                observer.observe(scroller);
                observer.observe(table);
                scroller.addEventListener('scroll', schedule, {passive: true});
                this._chartTableCleanups.set(code, () => {
                    disposed = true;
                    scroller.removeEventListener('scroll', schedule);
                    observer.disconnect();
                    if (frame !== null) cancelAnimationFrame(frame);
                    this._chartTableCleanups.delete(code);
                });
                body.innerHTML = spacer(0) + rows.slice(0, 12).map(rowMarkup).join('') + spacer((rows.length - 12) * estimate);
                scroller.scrollTop = scrollTop;
                draw();
            }

            // Filter Handlers (100% Dynamic)
            toggleDropdown(id, event) {
                if (event) event.stopPropagation();
                const el = this.getById(id);
                if (!el) return;
                const isHidden = el.classList.contains('hidden');
                this.queryAll('[id^="filterMenu_"], [id$="DropdownMenu"]').forEach(m => m.classList.add('hidden'));
                this.getById('colDrawerMenu')?.classList.add('hidden');
                this.getById('searchSuggestionsDropdown')?.classList.add('hidden');
                if (isHidden) el.classList.remove('hidden');
            }

            selectFilterOption(key, val, label) {
                this.state.filterValues[key] = val;
                this.state.filterLabels[key] = label;
                const labelEl = this.getById(`selectedLabel_${key}`);
                if (labelEl) labelEl.textContent = label;
                this.getById(`filterMenu_${key}`)?.classList.add('hidden');
                this.onGlobalFilterChange();
            }

            filterMultiDropdown(key, query) {
                const q = query.toLowerCase();
                const container = this.getById(`multiOptionsContainer_${key}`);
                if (!container) return;
                container.querySelectorAll('.filter-opt-row').forEach(row => {
                    const label = row.getAttribute('data-label').toLowerCase();
                    row.style.display = (!q || label.includes(q)) ? 'flex' : 'none';
                });
            }

            setAllMultiOptions(key, check) {
                const container = this.getById(`multiOptionsContainer_${key}`);
                if (container) {
                    container.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = check);
                }
                this.onMultiFilterChange(key);
            }

            onMultiFilterChange(key) {
                const container = this.getById(`multiOptionsContainer_${key}`);
                const checkedVals = Array.from(container?.querySelectorAll('input[type="checkbox"]:checked') || []).map(cb => cb.value);
                const f = this.state.filterDefs.find(d => d.key === key);
                const totalCount = f?.options?.length || 0;

                this.state.filterValues[key] = new Set(checkedVals);
                const labelText = checkedVals.length === totalCount ? `全部${f?.label || ''}` : (checkedVals.length === 0 ? `未选${f?.label || ''} (0)` : `已选 ${checkedVals.length} 项`);
                this.state.filterLabels[key] = labelText;

                const labelEl = this.getById(`selectedLabel_${key}`);
                if (labelEl) labelEl.textContent = labelText;
                const badgeEl = this.getById(`countBadge_${key}`);
                if (badgeEl) badgeEl.textContent = checkedVals.length;

                this.onGlobalFilterChange();
            }

            // Legacy Shims
            selectGlobalTime(val, label) { this.selectFilterOption('period', val, label); }
            selectGlobalFleet(val, label) { this.selectFilterOption('fleet', val, label); }
            selectGlobalRoute(val, label) { this.selectFilterOption('route', val, label); }
            setAllHubs(check) { this.setAllMultiOptions('hub', check); }
            filterHubDropdownList() {
                const inp = this.getById('hubSearchInput');
                if (inp) this.filterMultiDropdown('hub', inp.value);
            }

            // Search Autocomplete Suggestions
            showSearchSuggestions() {
                const query = this.getById('globalKeywordSearch')?.value.trim();
                const dropdown = this.getById('searchSuggestionsDropdown');
                const content = this.getById('searchSuggestionsContent');
                if (!dropdown || !content) return;

                this.queryAll('[id^="filterMenu_"], [id$="DropdownMenu"]').forEach(m => m.classList.add('hidden'));
                this.getById('colDrawerMenu')?.classList.add('hidden');

                if (!query) {
                    const rows = this.config.table?.rows || [];
                    const cols = this.config.table?.columns || [];
                    const catCols = cols.filter(c => ['left', 'center'].includes(c.align || 'left') && !c.key.includes('id') && !c.key.includes('time')).slice(0, 4);

                    let sectionsHtml = '';
                    catCols.forEach(col => {
                        const vals = Array.from(new Set(rows.map(r => String(r[col.key] || '')).filter(v => v && v.length < 25))).slice(0, 6);
                        if (vals.length > 0) {
                            sectionsHtml += `
                                <div>
                                    <div class="text-[10px] text-ink-subtle font-medium mb-1">🏷️ ${col.title}</div>
                                    <div class="flex flex-wrap gap-1.5">
                                        ${vals.map(item => `
                                            <button type="button" onclick="window.App.applySearchKeyword('${item.replace(/'/g, "\\'")}')" class="px-2 py-0.5 rounded bg-slate-100 hover:bg-primary hover:text-white text-ink transition-colors text-[11px]">${item}</button>
                                        `).join('')}
                                    </div>
                                </div>
                            `;
                        }
                    });

                    content.innerHTML = `
                        <div class="space-y-2.5">
                            <div class="text-[11px] font-bold text-primary flex items-center justify-between pb-1 border-b border-slate-100">
                                <span class="flex items-center gap-1"><span>🔥</span> 快捷维度检索推荐</span>
                                <span class="text-[10px] text-ink-subtle font-normal">点击即刻筛选</span>
                            </div>
                            ${sectionsHtml || '<div class="text-xs text-ink-subtle py-2 text-center">输入任意关键词进行多维全局过滤</div>'}
                        </div>
                    `;
                } else {
                    const q = query.toLowerCase();
                    const allRows = this.config.table?.rows || [];
                    const cols = this.config.table?.columns || [];
                    const colMap = {};
                    cols.forEach(c => { colMap[c.key] = c.title; });
                    const matchedItems = [];
                    const seen = new Set();

                    allRows.forEach(r => {
                        Object.keys(r).forEach(key => {
                            if (key.startsWith('raw') || key.startsWith('_')) return;
                            const val = String(r[key] || '');
                            if (val && val.toLowerCase().includes(q) && !seen.has(val)) {
                                seen.add(val);
                                const tag = colMap[key] || '维度';
                                matchedItems.push({ val, tag, rowName: r.name || r.title || r.code || '' });
                            }
                        });
                    });

                    if (matchedItems.length === 0) {
                        content.innerHTML = `<div class="py-4 text-center text-ink-subtle text-xs">未找到匹配「${query}」的数据记录</div>`;
                    } else {
                        content.innerHTML = `
                            <div class="space-y-1">
                                <div class="text-[10px] text-ink-subtle pb-1 border-b border-slate-100 flex items-center justify-between">
                                    <span>匹配结果 (${matchedItems.length} 条)</span>
                                    <span>回车或点击确认</span>
                                </div>
                                <div class="space-y-1 pt-1 max-h-60 overflow-y-auto custom-scrollbar">
                                    ${matchedItems.slice(0, 10).map(item => {
                                        const cleanVal = item.val.replace(/'/g, "\\'");
                                        const highlightVal = item.val.split(new RegExp(`(${query})`, 'gi')).map(part => part.toLowerCase() === query.toLowerCase() ? `<span class="bg-amber-100 text-amber-900 font-bold px-0.5 rounded">${part}</span>` : part).join('');
                                        return `
                                            <div onclick="window.App.applySearchKeyword('${cleanVal}')" class="p-1.5 hover:bg-slate-50 rounded cursor-pointer flex items-center justify-between group transition-colors">
                                                <div class="flex items-center gap-2 min-w-0">
                                                    <span class="text-[10px] px-1.5 py-0.2 bg-primary/10 text-primary rounded flex-shrink-0 font-medium">${item.tag}</span>
                                                    <span class="truncate text-ink group-hover:text-primary font-medium text-xs">${highlightVal}</span>
                                                </div>
                                                <span class="text-[10px] text-slate-400 group-hover:text-primary">选择 ↵</span>
                                            </div>
                                        `;
                                    }).join('')}
                                </div>
                            </div>
                        `;
                    }
                }

                dropdown.classList.remove('hidden');
            }

            onSearchInput(val) {
                const clearBtn = this.getById('clearSearchBtn');
                if (clearBtn) {
                    if (val) clearBtn.classList.remove('hidden');
                    else clearBtn.classList.add('hidden');
                }
                this.showSearchSuggestions();
                this.onGlobalFilterChange();
            }

            onSearchKeyDown(e) {
                if (e.key === 'Enter' || e.key === 'Escape') {
                    this.getById('searchSuggestionsDropdown')?.classList.add('hidden');
                }
            }

            applySearchKeyword(val) {
                const input = this.getById('globalKeywordSearch');
                if (input) {
                    input.value = val;
                    this.getById('clearSearchBtn')?.classList.remove('hidden');
                }
                this.getById('searchSuggestionsDropdown')?.classList.add('hidden');
                this.onGlobalFilterChange();
                this.showToast(`已应用检索: 「${val}」`);
            }

            clearSearchKeyword(e) {
                if (e) e.stopPropagation();
                const input = this.getById('globalKeywordSearch');
                if (input) input.value = '';
                this.getById('clearSearchBtn')?.classList.add('hidden');
                this.getById('searchSuggestionsDropdown')?.classList.add('hidden');
                this.onGlobalFilterChange();
                this.showToast('已清空关键词检索');
            }

            onGlobalFilterChange() {
                this.state.keyword = this.getById('globalKeywordSearch')?.value.trim() || '';
                this.updateActiveChips();
                this.state.table.page = 1;
                this.renderTableEngine();
                this.updateKPIsAndChartsFromFilters();
            }

            updateKPIsAndChartsFromFilters(changedCharts = null) {
                const rows = this.getFilteredTableRows();
                const allRows = this.config.table?.rows || [];
                const isFiltered = rows.length < allRows.length;
                const boundKPIs = (this.config.kpis || []).filter(kpi => kpi.binding);
                boundKPIs.forEach(kpi => {
                    kpi.value = ComponentBindings.kpiValue(this.getFilteredTableRows(kpi.id), kpi);
                });
                if (boundKPIs.length) {
                    this.renderer.renderKPIs();
                    this.initKPIWidgets();
                }

                // 2. Dynamically update Charts (Generic & Clean)
                const charts = this.config.charts || [];
                charts.forEach(chartCfg => {
                    const instanceId = chartCfg.instanceId;
                    if (changedCharts && !changedCharts.has(instanceId)) return;
                    const inst = this.state.chartInstances[instanceId];
                    if (!inst) return;
                    const gran = this.state.chartGranularities[instanceId] || 'month';

                    try {
                        if (chartCfg.binding) {
                            chartCfg.data = ComponentBindings.chartData(this.getFilteredTableRows(instanceId), chartCfg);
                            this.setChartOption(inst, chartCfg.optionBuilder(chartCfg.data, gran, TOKENS, chartCfg));
                        } else if (typeof chartCfg.onFilterChange === 'function') {
                            chartCfg.onFilterChange(rows, isFiltered, inst, TOKENS);
                        } else if (typeof chartCfg.optionBuilder === 'function') {
                            const opt = chartCfg.optionBuilder(chartCfg.data, gran, TOKENS, chartCfg);
                            this.setChartOption(inst, opt);
                        }

                        // If table pane is currently open for this card, refresh table dynamically
                        const cardEl = this.getById(chartCfg.id)?.closest('.section-card');
                        const tablePane = cardEl?.querySelector('.card-table-pane');
                        if (tablePane && !tablePane.classList.contains('hidden')) {
                            this.renderDynamicChartTable(instanceId, tablePane);
                        }
                    } catch (err) {
                        console.error('Error updating chart ' + instanceId, err);
                    }
                });
            }

            updateActiveChips() {
                const tray = this.getById('activeChipsTray');
                const container = this.getById('chipsContainer');
                const badge = this.getById('activeFilterBadgeCount');
                if (!tray || !container) return;

                let chips = [];
                this.state.filterDefs.forEach(f => {
                    const curVal = this.state.filterValues[f.key];
                    const defVal = this.state.defaultFilterValues[f.key];

                    if (f.type === 'multi-select') {
                        if (curVal instanceof Set && curVal.size < f.options.length) {
                            const selectedLabels = f.options.filter(o => curVal.has(o.value)).map(o => o.label);
                            chips.push({ key: f.key, label: `${f.label}: ${selectedLabels.join(', ')}` });
                        }
                    } else {
                        if (curVal !== defVal && curVal !== 'ALL' && curVal !== '') {
                            chips.push({ key: f.key, label: `${f.label}: ${this.state.filterLabels[f.key]}` });
                        }
                    }
                });

                if (this.state.keyword) {
                    chips.push({ key: '_kw', label: `关键词: "${this.state.keyword}"` });
                }

                if (badge) badge.textContent = chips.length;
                if (chips.length > 0) {
                    tray.classList.remove('hidden');
                    container.innerHTML = chips.map(c => `
                        <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 text-[11px] font-medium">
                            <span>${c.label}</span>
                            <button onclick="window.App.removeFilterChip('${c.key}')" class="hover:text-primary-strong font-bold">×</button>
                        </span>
                    `).join('');
                } else {
                    tray.classList.add('hidden');
                }
            }

            removeFilterChip(key) {
                if (key === '_kw') {
                    const inp = this.getById('globalKeywordSearch');
                    if (inp) inp.value = '';
                    this.state.keyword = '';
                    this.onGlobalFilterChange();
                    return;
                }
                const f = this.state.filterDefs.find(d => d.key === key);
                if (!f) return;
                if (f.type === 'multi-select') {
                    this.setAllMultiOptions(key, true);
                } else {
                    const defVal = this.state.defaultFilterValues[key];
                    const defLabel = this.state.defaultFilterLabels[key];
                    this.selectFilterOption(key, defVal, defLabel);
                }
            }

            resetAllGlobalFilters() {
                this.state.filterDefs.forEach(f => {
                    if (f.type === 'multi-select') {
                        const allVals = f.options.map(o => o.value);
                        this.state.filterValues[f.key] = new Set(allVals);
                        this.state.filterLabels[f.key] = `全部${f.label}`;
                        const container = this.getById(`multiOptionsContainer_${f.key}`);
                        if (container) container.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
                        const labelEl = this.getById(`selectedLabel_${f.key}`);
                        if (labelEl) labelEl.textContent = `全部${f.label}`;
                        const badgeEl = this.getById(`countBadge_${f.key}`);
                        if (badgeEl) badgeEl.textContent = allVals.length;
                    } else {
                        const defVal = this.state.defaultFilterValues[f.key];
                        const defLabel = this.state.defaultFilterLabels[f.key];
                        this.state.filterValues[f.key] = defVal;
                        this.state.filterLabels[f.key] = defLabel;
                        const labelEl = this.getById(`selectedLabel_${f.key}`);
                        if (labelEl) labelEl.textContent = defLabel;
                    }
                });

                const searchInput = this.getById('globalKeywordSearch');
                if (searchInput) searchInput.value = '';
                this.state.keyword = '';
                this.state.chartCrossFilter = null;
                this.getById('tableCrossFilterTray')?.classList.add('hidden');
                this.onGlobalFilterChange();
                this.showToast('已重置恢复全部基准筛选');
            }

            // Cross Filtering
            setTableCrossFilter(val) {
                this.state.chartCrossFilter = val;
                const tray = this.getById('tableCrossFilterTray');
                const txt = this.getById('tableCrossFilterText');
                if (tray && txt) {
                    txt.textContent = `已根据图表选择联动过滤: 「${val}」`;
                    tray.classList.remove('hidden');
                }
                this.state.table.page = 1;
                this.renderTableEngine();
                this.updateKPIsAndChartsFromFilters();
                this.showToast(`表格与指标已联动过滤: ${val}`);
            }

            clearTableCrossFilter() {
                this.state.chartCrossFilter = null;
                this.getById('tableCrossFilterTray')?.classList.add('hidden');
                this.state.table.page = 1;
                this.renderTableEngine();
                this.updateKPIsAndChartsFromFilters();
                this.showToast('已清除图表联动过滤');
            }

            // Table Engine with Column Drag-and-Drop
            renderColCheckboxes() {
                const container = this.getById('colCheckboxesContainer');
                if (!container) return;

                container.innerHTML = this.state.table.orderedColumns.map((col, index) => `
                    <div class="drag-col-item flex items-center justify-between p-1.5 hover:bg-slate-50 rounded border border-transparent hover:border-slate-200 cursor-move" 
                         draggable="true" 
                         data-col-key="${col.key}" 
                         data-index="${index}">
                        <div class="flex items-center gap-1.5 min-w-0">
                            ${LUCIDE_ICONS.dragHandle}
                            <input type="checkbox" value="${col.key}" ${this.state.table.visibleCols.has(col.key) ? 'checked' : ''} onchange="window.App.onColumnVisibilityChange('${col.key}', this.checked)" class="rounded text-primary focus:ring-0">
                            <span class="truncate font-medium">${col.title}</span>
                        </div>
                        <span class="text-[10px] text-slate-400 font-mono">#${index + 1}</span>
                    </div>
                `).join('');

                this.bindColumnDragEvents();
            }

            bindColumnDragEvents() {
                const items = this.queryAll('.drag-col-item');
                items.forEach(item => {
                    item.addEventListener('dragstart', (e) => {
                        this.draggedColKey = item.getAttribute('data-col-key');
                        item.classList.add('dragging');
                        e.dataTransfer.effectAllowed = 'move';
                        e.dataTransfer.setData('text/plain', this.draggedColKey);
                    });

                    item.addEventListener('dragover', (e) => {
                        e.preventDefault();
                        e.dataTransfer.dropEffect = 'move';
                        item.classList.add('drag-over');
                    });

                    item.addEventListener('dragleave', () => {
                        item.classList.remove('drag-over');
                    });

                    item.addEventListener('drop', (e) => {
                        e.preventDefault();
                        item.classList.remove('drag-over');
                        const targetColKey = item.getAttribute('data-col-key');
                        if (this.draggedColKey && this.draggedColKey !== targetColKey) {
                            this.reorderColumns(this.draggedColKey, targetColKey);
                        }
                    });

                    item.addEventListener('dragend', () => {
                        item.classList.remove('dragging');
                        this.queryAll('.drag-col-item').forEach(el => el.classList.remove('drag-over', 'dragging'));
                    });
                });
            }

            reorderColumns(sourceKey, targetKey) {
                const cols = [...this.state.table.orderedColumns];
                const srcIdx = cols.findIndex(c => c.key === sourceKey);
                const tgtIdx = cols.findIndex(c => c.key === targetKey);

                if (srcIdx > -1 && tgtIdx > -1) {
                    const [moved] = cols.splice(srcIdx, 1);
                    cols.splice(tgtIdx, 0, moved);
                    this.state.table.orderedColumns = cols;
                    this.renderColCheckboxes();
                    this.renderTableEngine();
                    this.showToast(`已调整列顺序: 「${moved.title}」移动至 #${tgtIdx + 1}`);
                }
            }

            onColumnVisibilityChange(key, isChecked) {
                if (isChecked) this.state.table.visibleCols.add(key);
                else this.state.table.visibleCols.delete(key);
                this.renderTableEngine();
            }

            resetDefaultColumns() {
                this.state.table.orderedColumns = [...this.config.table.columns];
                this.state.table.visibleCols = new Set(this.config.table.columns.map(c => c.key));
                this.renderColCheckboxes();
                this.renderTableEngine();
                this.showToast('已恢复默认列顺序与展示');
            }

            toggleColumnDrawer(e) {
                if (e) e.stopPropagation();
                const menu = this.getById('colDrawerMenu');
                if (!menu) return;
                const isHidden = menu.classList.contains('hidden');
                this.queryAll('[id$="DropdownMenu"]').forEach(m => m.classList.add('hidden'));
                this.getById('searchSuggestionsDropdown')?.classList.add('hidden');
                if (isHidden) {
                    this.renderColCheckboxes();
                    menu.classList.remove('hidden');
                } else {
                    menu.classList.add('hidden');
                }
            }

            toggleColDrawer(e) {
                this.toggleColumnDrawer(e);
            }

            onTablePageSizeChange(val) {
                this.state.table.pageSize = val === 'all' ? 9999 : parseInt(val, 10);
                this.state.table.page = 1;
                this.renderTableEngine();
            }

            prevTablePage() {
                if (this.state.table.page > 1) {
                    this.state.table.page--;
                    this.renderTableEngine();
                }
            }

            nextTablePage() {
                const totalPages = Math.ceil((this.config.table?.remotePage?.totalRows ?? this.getFilteredTableRows().length) / this.state.table.pageSize);
                if (this.state.table.page < totalPages) {
                    this.state.table.page++;
                    this.renderTableEngine();
                }
            }

            sortTable(colKey) {
                if (this.state.table.sortCol === colKey) {
                    this.state.table.sortDir = this.state.table.sortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    this.state.table.sortCol = colKey;
                    this.state.table.sortDir = 'desc';
                }
                this.renderTableEngine();
            }

            getFilteredTableRows(componentId = null) {
                let rows = [...(this.config.table?.rows || [])];
                if (this.config.table?.remotePage) return rows;

                // 1. Dynamic Attribute Filtering
                this.state.filterDefs.forEach(f => {
                    if (componentId && !f.componentIds?.includes(componentId)) return;
                    const curVal = this.state.filterValues[f.key];
                    const declaredFields = Array.isArray(f.fields) && f.fields.length > 0 ? f.fields : null;
                    const candidateEntries = row => declaredFields
                        ? declaredFields.map(field => [field, row[field]]).filter(([, value]) => value !== undefined)
                        : Object.entries(row).filter(([key]) => !key.startsWith('raw') && !key.startsWith('_'));
                    if (f.type === 'multi-select') {
                        if (curVal instanceof Set && (declaredFields || curVal.size < f.options.length)) {
                            rows = rows.filter(r => {
                                return candidateEntries(r).some(([, value]) => curVal.has(String(value)));
                            });
                        }
                    } else {
                        if (curVal !== undefined && curVal !== 'ALL' && curVal !== 'all' && curVal !== '') {
                            const curLabel = this.state.filterLabels[f.key] || '';
                            rows = rows.filter(r => {
                                return candidateEntries(r).some(([, value]) => declaredFields
                                    ? String(value) === String(curVal)
                                    : String(value).includes(String(curVal)) || (curLabel && String(value).includes(curLabel)));
                            });
                        }
                    }
                });

                // 2. Keyword Filter
                if (this.state.keyword) {
                    const q = this.state.keyword.toLowerCase();
                    rows = rows.filter(r => Object.entries(r).some(([k, v]) => !k.startsWith('raw') && !k.startsWith('_') && String(v).toLowerCase().includes(q)));
                }

                // 3. Chart Cross Filter
                if (this.state.chartCrossFilter) {
                    const cf = this.state.chartCrossFilter.toLowerCase();
                    rows = rows.filter(r => Object.entries(r).some(([k, v]) => !k.startsWith('raw') && !k.startsWith('_') && String(v).toLowerCase().includes(cf)));
                }

                // 4. Table Column Sorting
                if (this.state.table.sortCol) {
                    const key = this.state.table.sortCol;
                    const dir = this.state.table.sortDir === 'asc' ? 1 : -1;
                    rows.sort((a, b) => {
                        let va = a[key] ?? '';
                        let vb = b[key] ?? '';
                        const rawKey = 'raw' + key.charAt(0).toUpperCase() + key.slice(1);
                        if (a[rawKey] !== undefined && b[rawKey] !== undefined) {
                            return (a[rawKey] - b[rawKey]) * dir;
                        }
                        const na = parseFloat(String(va).replace(/[^0-9.-]/g, ''));
                        const nb = parseFloat(String(vb).replace(/[^0-9.-]/g, ''));
                        if (!isNaN(na) && !isNaN(nb) && String(va).match(/\\d/) && String(vb).match(/\\d/)) {
                            return (na - nb) * dir;
                        }
                        return String(va).localeCompare(String(vb), 'zh-CN') * dir;
                    });
                }

                return rows;
            }

            formatTableCell(raw, col) {
                if (raw === undefined || raw === null || raw === '') return '—';
                if (!col.format || typeof raw !== 'number' || !Number.isFinite(raw)) return String(raw);
                const digits = col.decimals ?? (col.format === 'percent' ? 1 : 0);
                const scaled = col.format === 'percent' && col.scale === 'fraction' ? raw * 100 : raw;
                const formatter = new Intl.NumberFormat('zh-CN', {minimumFractionDigits: digits, maximumFractionDigits: digits});
                let text = formatter.format(scaled);
                const value = Number(text.replace(/,/g, ''));
                if (value === 0) text = formatter.format(0);
                return (col.signed && value > 0 ? '+' : '') + text + (col.format === 'percent' ? '%' : '');
            }

            renderTableEngine() {
                const thead = this.getById('main14ColThead');
                const tbody = this.getById('main14ColTbody');
                if (!thead || !tbody) return;

                const visibleCols = this.state.table.orderedColumns.filter(c => this.state.table.visibleCols.has(c.key));
                const allFiltered = this.getFilteredTableRows();
                const remote = this.config.table?.remotePage;
                const total = remote?.totalRows ?? allFiltered.length;
                const pageSize = this.state.table.pageSize;
                const totalPages = Math.max(1, Math.ceil(total / pageSize));

                if (this.state.table.page > totalPages) this.state.table.page = totalPages;
                const startIdx = (this.state.table.page - 1) * pageSize;
                const currentRows = remote ? allFiltered : allFiltered.slice(startIdx, startIdx + pageSize);

                // Render Thead (Strict single line with whitespace-nowrap)
                thead.innerHTML = `
                    <tr>
                        ${visibleCols.map(col => `
                            <th onclick="window.App.sortTable('${col.key}')" class="px-3.5 py-2.5 cursor-pointer hover:bg-slate-100 transition-colors text-${col.align} whitespace-nowrap select-none font-semibold text-[11px] border-b border-slate-200">
                                <div class="inline-flex items-center gap-1.5 whitespace-nowrap">
                                    <span class="whitespace-nowrap">${col.title}</span>
                                    <span class="text-[9px] text-slate-400 font-mono inline-block w-2.5 text-center">
                                        ${this.state.table.sortCol === col.key ? (this.state.table.sortDir === 'asc' ? '▲' : '▼') : '⇅'}
                                    </span>
                                </div>
                            </th>
                        `).join('')}
                    </tr>
                `;

                this._tableScrollCleanup?.();
                this._tableScrollCleanup = null;
                const tableElement = tbody.closest('table');
                tableElement?.setAttribute('aria-rowcount', String(total + 1));
                tableElement?.setAttribute('aria-colcount', String(visibleCols.length));
                // Render Tbody (Strict single line with tabular nums)
                if (currentRows.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="${visibleCols.length}" class="py-8 text-center text-ink-subtle">暂无符合筛选条件的数据记录</td></tr>`;
                } else {
                    const rowMarkup = (row, index) => `
                        <tr aria-rowindex="${startIdx + index + 2}" onmouseenter="window.App.onTableRowHover('${row.name}')" onmouseleave="window.App.onTableRowLeave()" class="hover:bg-slate-50/80 transition-colors">
                            ${visibleCols.map(col => {
                                const raw = row[col.key];
                                const hasValue = raw !== undefined && raw !== null && raw !== '';
                                let val = this.formatTableCell(raw, col);
                                const trendClass = hasValue && ['yoy', 'mom'].includes(col.key) ? trendTextClass(val, '') : '';
                                let cellStyle = trendClass ? `${trendClass} font-bold` : '';
                                if (col.key === 'rating') {
                                    if (val.includes('S')) val = `<span class="px-2 py-0.5 rounded bg-[#123B5D]/10 text-primary border border-[#123B5D]/20 font-bold text-[10px] whitespace-nowrap">${val}</span>`;
                                    else if (val.includes('A')) val = `<span class="px-2 py-0.5 rounded bg-secondary/10 text-secondary border border-secondary/20 font-bold text-[10px] whitespace-nowrap">${val}</span>`;
                                    else val = `<span class="px-2 py-0.5 rounded bg-slate-100 text-ink-muted border border-slate-200 text-[10px] whitespace-nowrap">${val}</span>`;
                                }
                                return `<td onclick="window.App.copyCell('${hasValue ? raw : ''}')" class="px-3.5 py-2 text-${col.align} font-mono text-[11px] cursor-pointer hover:underline whitespace-nowrap ${cellStyle}" title="点击复制">${val}</td>`;
                            }).join('')}
                        </tr>
                    `;
                    this.renderTableRows(tbody, currentRows, visibleCols, rowMarkup);
                }

                // Update Pagination Info
                const pageInfo = this.getById('tablePaginationInfo');
                const pageIndicator = this.getById('tablePageIndicator');
                const prevBtn = this.getById('tablePrevBtn');
                const nextBtn = this.getById('tableNextBtn');

                if (pageInfo) pageInfo.textContent = `显示第 ${total === 0 ? 0 : startIdx + 1} - ${Math.min(startIdx + pageSize, total)} 条 · 共 ${total} 条`;
                if (pageIndicator) pageIndicator.textContent = `${this.state.table.page} / ${totalPages}`;
                if (prevBtn) prevBtn.disabled = this.state.table.page <= 1;
                if (nextBtn) nextBtn.disabled = this.state.table.page >= totalPages;
            }

            renderTableRows(tbody, rows, columns, rowMarkup) {
                if (rows.length <= 100) {
                    tbody.innerHTML = rows.map(rowMarkup).join('');
                    return;
                }
                const scroller = tbody.closest('table').parentElement;
                // The existing nowrap cells produce uniform rows; measure their actual styled height.
                tbody.innerHTML = rows.slice(0, 2).map(rowMarkup).join('');
                const measured = Array.from(tbody.children).map(row => row.getBoundingClientRect().height);
                const height = measured[0];
                if (!height || measured.some(value => Math.abs(value - height) > 1)) {
                    tbody.innerHTML = rows.map(rowMarkup).join('');
                    return;
                }
                const oldMaxHeight = scroller.style.maxHeight;
                const oldOverflow = scroller.style.overflowY;
                scroller.style.maxHeight = '420px';
                scroller.style.overflowY = 'auto';
                const table = tbody.closest('table');
                const headers = Array.from(table.querySelectorAll('thead th'));
                const measure = document.createElement('canvas').getContext('2d');
                const cells = Array.from(tbody.querySelector('tr').children);
                const widths = columns.map((column, index) => {
                    const style = getComputedStyle(cells[index]);
                    measure.font = style.font || `${style.fontSize} ${style.fontFamily}`;
                    const max = rows.reduce((width, row) => Math.max(width, measure.measureText(this.formatTableCell(row[column.key], column)).width), 0);
                    const padding = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight) + 2;
                    return Math.ceil(Math.max(headers[index]?.getBoundingClientRect().width || 0, max + padding));
                });
                const oldLayout = table.style.tableLayout;
                const oldWidth = table.style.width;
                table.style.tableLayout = 'fixed';
                table.style.width = `${widths.reduce((sum, width) => sum + width, 0)}px`;
                headers.forEach((header, index) => { header.style.width = `${widths[index]}px`; });
                let frame = null;
                let lastStart = -1;
                const draw = () => {
                    frame = null;
                    const start = Math.max(0, Math.floor(scroller.scrollTop / height) - 6);
                    if (start === lastStart) return;
                    lastStart = start;
                    const end = Math.min(rows.length, start + Math.ceil((scroller.clientHeight || 420) / height) + 12);
                    const spacer = size => `<tr aria-hidden="true"><td colspan="${columns.length}" style="height:${size}px;padding:0;border:0"></td></tr>`;
                    tbody.innerHTML = spacer(start * height) + rows.slice(start, end).map((row, index) => rowMarkup(row, start + index)).join('') + spacer((rows.length - end) * height);
                };
                const onScroll = () => { if (frame === null) frame = requestAnimationFrame(draw); };
                scroller.addEventListener('scroll', onScroll, {passive: true});
                draw();
                this._tableScrollCleanup = () => {
                    scroller.removeEventListener('scroll', onScroll);
                    if (frame !== null) cancelAnimationFrame(frame);
                    scroller.style.maxHeight = oldMaxHeight;
                    scroller.style.overflowY = oldOverflow;
                    table.style.tableLayout = oldLayout;
                    table.style.width = oldWidth;
                };
            }

            onTableRowHover(routeName) {
                const keyword = routeName.split(' ')[0];
                Object.values(this.state.chartInstances).forEach(inst => {
                    inst.dispatchAction({ type: 'highlight', name: keyword });
                    inst.dispatchAction({ type: 'showTip', name: keyword });
                });
            }

            onTableRowLeave() {
                Object.values(this.state.chartInstances).forEach(inst => {
                    inst.dispatchAction({ type: 'downplay' });
                    inst.dispatchAction({ type: 'hideTip' });
                });
            }

            copyCell(text) {
                if (!text) return;
                navigator.clipboard.writeText(text).then(() => {
                    this.showToast(`已复制: "${text}"`);
                });
            }

            exportTableToCSV() {
                const visibleCols = this.state.table.orderedColumns.filter(c => this.state.table.visibleCols.has(c.key));
                const allRows = this.getFilteredTableRows();
                const header = visibleCols.map(c => `"${c.title}"`).join(',');
                const rows = allRows.map(r => visibleCols.map(c => `"${r[c.key] ?? ''}"`).join(','));
                const csv = '\\uFEFF' + [header, ...rows].join('\\r\\n');
                const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                const exportTitle = (this.config.table?.title || this.config.meta?.title || '业务运营透视表').replace(/[^a-zA-Z0-9_\\u4e00-\\u9fa5]+/g, '_');
                a.download = `${exportTitle}_${new Date().toISOString().slice(0,10)}.csv`;
                a.click();
                URL.revokeObjectURL(url);
                this.showToast(`已成功导出 ${allRows.length} 条记录至 Excel (CSV)`);
            }

            destroy() {
                if (!this._mounted) return;
                this._mounted = false;
                this._tableScrollCleanup?.();
                this._tableScrollCleanup = null;
                this._chartTableCleanups.forEach(cleanup => cleanup());
                this._resizeBound = false;
                this._timers.forEach(timer => clearTimeout(timer));
                this._timers.clear();
                this._eventController?.abort();
                this._eventController = null;
                this._resizeObserver?.disconnect();
                this._resizeObserver = null;
                if (this._chartResizeFrame) cancelAnimationFrame(this._chartResizeFrame);
                this._chartResizeFrame = null;
                this._pendingChartResize?.clear();
                Object.values(this.state.chartInstances).forEach(inst => inst?.dispose());
                this.state.chartInstances = {};
                if (this.root.__dashboardApp === this) delete this.root.__dashboardApp;
                if (window.App === this) window.App = null;
            }

            scheduleTimeout(callback, delay) {
                const timer = setTimeout(() => {
                    this._timers.delete(timer);
                    if (this._mounted) callback();
                }, delay);
                this._timers.add(timer);
                return timer;
            }

            showToast(msg) {
                const container = this.getById('app-toast-container');
                if (!container) return;
                const toast = document.createElement('div');
                toast.className = 'px-4 py-2.5 bg-primary-strong text-white text-xs font-semibold rounded-lg shadow-xl toast-active flex items-center gap-2 border border-slate-700 pointer-events-auto';
                toast.innerHTML = `<span class="flex-shrink-0">${LUCIDE_ICONS.checkCircle}</span><span>${msg}</span>`;
                container.appendChild(toast);
                this.scheduleTimeout(() => {
                    toast.style.opacity = '0';
                    toast.style.transition = 'opacity 0.3s ease';
                    this.scheduleTimeout(() => toast.remove(), 300);
                }, 2800);
            }
        }

__DASHBOARD_RUNTIME_BUNDLE__

    })();
    </script>
</body>
</html>"""

def generate_dashboard_html(config_js_code, page_title):
    return (TEMPLATE
            .replace('__PAGE_TITLE__', page_title)
            .replace('__TAILWIND_COLORS__', tailwind_colors_js())
            .replace('__ECHARTS_PALETTE__', echarts_palette_js())
            .replace('__CATEGORICAL_COLORS__', categorical_js())
            .replace('__DASHBOARD_CONFIG_CODE__', config_js_code)
            .replace('__DASHBOARD_RUNTIME_BUNDLE__', render_runtime_bundle())
            .replace('__FILTER_BINDINGS_JS__', FILTER_BINDINGS_JS)
            .replace('__EXPLANATION_DIALOG_CSS__', EXPLANATION_DIALOG_CSS)
            .replace('__EXPLANATION_DIALOG_SHELL__', EXPLANATION_DIALOG_SHELL)
            .replace('__EXPLANATION_DIALOG_RENDERER_JS__', EXPLANATION_DIALOG_RENDERER_JS)
            .replace('__EXPLANATION_TRIGGER_ICON__', EXPLANATION_TRIGGER_ICON)
            # Inline controls resolve their owning root instead of a global singleton.
            .replace('window.App.', 'window.getDashboardAppForElement(this).'))
