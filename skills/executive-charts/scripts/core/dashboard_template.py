# Base template with 100% solid, non-overlapping sticky table headers
import os
import re

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
                    colors: {
                        primary: '#123B5D',
                        'primary-strong': '#0B2A42',
                        'primary-soft': '#DCE8F0',
                        ink: '#17212B',
                        'ink-muted': '#52606D',
                        'ink-subtle': '#7B8794',
                        positive: '#A4453C',
                        negative: '#2F6B55',
                        attention: '#9A6A18',
                        gridline: '#E6EAED',
                        rule: '#C9D1D8'
                    },
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

        /* Dialog Modal Styling & Consulting-Grade Explanation Box */
        dialog.explanation-dialog {
            width: min(680px, 94vw);
            max-width: 680px;
            padding: 0;
            border: 1px solid #C9D1D8;
            border-radius: 12px;
            box-shadow: 0 20px 45px -10px rgba(11, 42, 66, 0.28), 0 0 0 1px rgba(11, 42, 66, 0.05);
            background: #FFFFFF;
            color: #17212B;
        }
        dialog.explanation-dialog::backdrop {
            background: rgba(11, 42, 66, 0.45);
            backdrop-filter: blur(4px);
        }
        dialog[open] {
            animation: modalFadeIn 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        @keyframes modalFadeIn {
            from { opacity: 0; transform: scale(0.96) translateY(8px); }
            to { opacity: 1; transform: scale(1) translateY(0); }
        }
        .exp-dialog-topbar {
            height: 52px;
            padding: 0 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #E2E8F0;
            background: #FFFFFF;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        .exp-dialog-body {
            padding: 18px 20px 24px;
            display: flex;
            flex-direction: column;
            gap: 14px;
            max-height: calc(85vh - 52px);
            overflow-y: auto;
            background: #FFFFFF;
        }
        .exp-overview-box {
            background: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 12px 14px;
        }
        .exp-specs-strip {
            display: flex;
            flex-wrap: wrap;
            gap: 6px 10px;
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px dashed #CBD5E1;
        }
        .exp-spec-badge {
            font-size: 11px;
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            padding: 2px 8px;
            border-radius: 4px;
            color: #17212B;
        }
        .exp-axis-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }
        .exp-axis-cell {
            background: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 8px 10px;
            font-size: 11.5px;
        }
        .exp-metric-card {
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 12px;
            background: #FFFFFF;
            transition: border-color .15s;
        }
        .exp-metric-card:hover { border-color: #123B5D; }
        .exp-formula {
            background: #F1F5F9;
            border: 1px solid #E2E8F0;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 11.5px;
            color: #0F172A;
        }

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
        <dialog id="app-explain-dialog" class="rounded-xl shadow-2xl overflow-hidden bg-white text-ink border border-slate-200 m-auto"></dialog>

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
            palette: {
                primary: '#123B5D',
                primaryStrong: '#0B2A42',
                primarySoft: '#DCE8F0',
                ink: '#0F172A',
                inkMuted: '#52606D',
                inkSubtle: '#7B8794',
                positive: '#A4453C',   // 咨询深红 (增长/上升)
                negative: '#2F6B55',   // 咨询墨绿 (稳健/达标/成本节约)
                attention: '#9A6A18',  // 咨询暗琥珀 (预警/关注)
                gridline: '#E2E8F0',
                rule: '#CBD5E1'
            },
            commonOption: {
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
            checkCircle: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#2F6B55" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="m9 12 2 2 4-4"/></svg>',
            maximize: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" x2="14" y1="3" y2="10"/><line x1="3" x2="10" y1="21" y2="14"/></svg>',
            minimize: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" x2="21" y1="10" y2="3"/><line x1="3" x2="10" y1="21" y2="14"/></svg>',
            viewToggle: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/></svg>',
            copy: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>',
            info: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
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

        // 3. Global State Management
        class StateStore {
            constructor(config) {
                this.config = config;
                const f = config.filters || {};
                const labels = f.labels || {};
                this.filterLabels = {
                    time: labels.time || '统计周期',
                    hub: labels.hub || '所属区域',
                    fleet: labels.fleet || '业务业态',
                    route: labels.route || '业务渠道'
                };
                const defaultSeason = (f.seasons || []).find(s => s.default || s.active) || f.seasons?.[0] || {};
                this.defaultFilters = {
                    time: defaultSeason.value || defaultSeason.val || 'CURRENT',
                    timeLabel: defaultSeason.label || '全周期',
                    hubs: new Set((f.hubs || []).map(h => h.value || h.val || h.name)),
                    fleet: 'ALL',
                    fleetLabel: `全部${this.filterLabels.fleet}`,
                    route: 'ALL',
                    routeLabel: `全部${this.filterLabels.route}`,
                    keyword: '',
                    chartCrossFilter: null
                };
                this.filters = {
                    time: this.defaultFilters.time,
                    timeLabel: this.defaultFilters.timeLabel,
                    hubs: new Set(this.defaultFilters.hubs),
                    fleet: 'ALL',
                    fleetLabel: this.defaultFilters.fleetLabel,
                    route: 'ALL',
                    routeLabel: this.defaultFilters.routeLabel,
                    keyword: '',
                    chartCrossFilter: null
                };
                this.table = {
                    page: 1,
                    pageSize: 10,
                    sortCol: null,
                    sortDir: 'asc',
                    orderedColumns: [...(config.table?.columns || [])],
                    visibleCols: new Set((config.table?.columns || []).map(c => c.key))
                };
                this.chartInstances = {};
                this.chartGranularities = {};
            }
        }

        // 4. UI Renderer with Multi-Style High-Impact KPI Cards & Consulting Design Tokens
        class DashboardRenderer {
            constructor(state) {
                this.state = state;
                this.config = state.config;
            }

            renderHeader() {
                const meta = this.config.meta;
                const container = document.getElementById('app-header');
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
                                <p class="text-[11px] text-ink-subtle">${meta.org} · ${meta.system}</p>
                            </div>
                        </div>
                        <div class="flex items-center gap-3 text-xs">
                            <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#123B5D]/6 border border-[#123B5D]/15 text-[#123B5D] text-xs font-mono font-medium">
                                <span class="w-1.5 h-1.5 rounded-full bg-[#2F6B55]"></span>
                                ${meta.statusText || '全域多维数据实时协同'}
                            </span>
                        </div>
                    </div>
                `;
            }

            renderFilters() {
                const f = this.config.filters || {};
                const labels = this.state.filterLabels;
                const container = document.getElementById('app-filters');
                if (!container) return;

                const seasonsList = (f.seasons || []).map(s => `
                    <div onclick="window.App.selectGlobalTime('${s.value || s.val}', '${s.label}')" class="px-3 py-2 text-xs text-ink hover:bg-slate-50 cursor-pointer flex items-center justify-between">
                        <span>${s.label}</span>
                        ${(s.active || s.default) ? '<span class="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-mono font-semibold">当前</span>' : ''}
                    </div>
                `).join('');

                const hubsList = (f.hubs || []).map(h => {
                    const hVal = h.value || h.val || h.name;
                    const hName = h.name || h.label || h.val;
                    return `
                    <label class="flex items-center justify-between p-1.5 hover:bg-slate-50 rounded cursor-pointer text-xs hub-opt-row" data-label="${hName}">
                        <span class="flex items-center gap-2">
                            <input type="checkbox" value="${hVal}" checked onchange="window.App.onGlobalFilterChange()" class="rounded text-primary focus:ring-0">
                            <span class="font-medium">${hName}</span>
                        </span>
                        <span class="text-[10px] text-ink-subtle font-mono">${h.count || ''}</span>
                    </label>
                `;}).join('');

                const fleetsList = (f.fleets || []).map(fl => `
                    <div onclick="window.App.selectGlobalFleet('${fl.value || fl.val}', '${fl.label}')" class="px-3 py-2 text-xs text-ink hover:bg-slate-50 cursor-pointer flex items-center justify-between font-medium">
                        <span>${fl.label}</span>
                    </div>
                `).join('');

                const routesList = (f.routes || []).map(r => `
                    <div onclick="window.App.selectGlobalRoute('${r.value || r.val}', '${r.label}')" class="px-3 py-2 text-xs text-ink hover:bg-slate-50 cursor-pointer flex items-center justify-between font-medium">
                        <span>${r.label}</span>
                    </div>
                `).join('');

                const sampleCols = (this.config.table?.columns || []).slice(0, 3).map(c => c.title);
                const searchPh = sampleCols.length > 0 ? `检索${sampleCols.join('、')}...` : '输入关键词全局检索...';

                container.innerHTML = `
                    <div class="max-w-[1600px] mx-auto px-6 py-3">
                        <div class="flex flex-wrap items-center justify-between gap-3">
                            <!-- Left Controls -->
                            <div class="flex flex-wrap items-center gap-2.5">
                                <!-- 1. 时间周期 -->
                                <div class="relative" id="filterTimeWrap">
                                    <button onclick="window.App.toggleDropdown('timeDropdownMenu', event)" class="h-[32px] px-3 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-md text-xs font-medium text-ink flex items-center gap-2 transition focus:outline-none focus:border-primary">
                                        <span class="text-ink-subtle">${labels.time}:</span>
                                        <span id="selectedTimeLabel" class="font-semibold text-primary">${this.state.filters.timeLabel}</span>
                                        ${LUCIDE_ICONS.chevronDown}
                                    </button>
                                    <div id="timeDropdownMenu" class="hidden absolute top-full left-0 mt-1.5 w-48 bg-white border border-slate-200 rounded-lg shadow-xl py-1 z-50">
                                        <div class="px-2.5 py-1 text-[10px] font-bold text-ink-subtle uppercase border-b border-slate-100">选择${labels.time}</div>
                                        ${seasonsList}
                                    </div>
                                </div>

                                <!-- 2. 所属区域 -->
                                <div class="relative" id="filterHubWrap">
                                    <button onclick="window.App.toggleDropdown('hubDropdownMenu', event)" class="h-[32px] px-3 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-md text-xs font-medium text-ink flex items-center gap-2 transition focus:outline-none focus:border-primary">
                                        <span class="text-ink-subtle">${labels.hub}:</span>
                                        <span id="selectedHubLabel" class="font-semibold text-primary truncate max-w-[130px]">全部${labels.hub}</span>
                                        <span id="hubCountBadge" class="bg-primary text-white text-[10px] px-1.5 py-0.2 rounded-full font-mono">${f.hubs?.length || 4}</span>
                                        ${LUCIDE_ICONS.chevronDown}
                                    </button>
                                    <div id="hubDropdownMenu" class="hidden absolute top-full left-0 mt-1.5 w-64 bg-white border border-slate-200 rounded-lg shadow-xl p-2.5 z-50 space-y-2">
                                        <div class="relative">
                                            <input type="text" id="hubSearchInput" oninput="window.App.filterHubDropdownList()" placeholder="搜索${labels.hub}..." class="w-full text-xs pl-7 pr-2 py-1 bg-slate-50 border border-slate-200 rounded text-ink focus:outline-none focus:border-primary focus:bg-white">
                                            <svg class="w-3.5 h-3.5 text-ink-subtle absolute left-2 top-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                                        </div>
                                        <div class="flex items-center justify-between text-[11px] text-ink-subtle pb-1 border-b border-slate-100">
                                            <button onclick="window.App.setAllHubs(true)" class="hover:text-primary font-medium">全选</button>
                                            <span class="text-slate-300">|</span>
                                            <button onclick="window.App.setAllHubs(false)" class="hover:text-primary font-medium">清空</button>
                                            <span class="ml-auto text-[10px] text-ink-subtle">多维区域</span>
                                        </div>
                                        <div class="space-y-1 max-h-44 overflow-y-auto custom-scrollbar" id="hubOptionsContainer">
                                            ${hubsList}
                                        </div>
                                    </div>
                                </div>

                                <!-- 3. 业务业态 -->
                                <div class="relative" id="filterFleetWrap">
                                    <button onclick="window.App.toggleDropdown('fleetDropdownMenu', event)" class="h-[32px] px-3 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-md text-xs font-medium text-ink flex items-center gap-2 transition focus:outline-none focus:border-primary">
                                        <span class="text-ink-subtle">${labels.fleet}:</span>
                                        <span id="selectedFleetLabel" class="font-semibold text-primary truncate max-w-[120px]">${this.state.filters.fleetLabel}</span>
                                        ${LUCIDE_ICONS.chevronDown}
                                    </button>
                                    <div id="fleetDropdownMenu" class="hidden absolute top-full left-0 mt-1.5 w-56 bg-white border border-slate-200 rounded-lg shadow-xl py-1 z-50">
                                        ${fleetsList}
                                    </div>
                                </div>

                                <!-- 4. 业务渠道/品类 -->
                                <div class="relative" id="filterRouteWrap">
                                    <button onclick="window.App.toggleDropdown('routeDropdownMenu', event)" class="h-[32px] px-3 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-md text-xs font-medium text-ink flex items-center gap-2 transition focus:outline-none focus:border-primary">
                                        <span class="text-ink-subtle">${labels.route}:</span>
                                        <span id="selectedRouteLabel" class="font-semibold text-primary truncate max-w-[120px]">${this.state.filters.routeLabel}</span>
                                        ${LUCIDE_ICONS.chevronDown}
                                    </button>
                                    <div id="routeDropdownMenu" class="hidden absolute top-full left-0 mt-1.5 w-48 bg-white border border-slate-200 rounded-lg shadow-xl py-1 z-50">
                                        ${routesList}
                                    </div>
                                </div>

                                <!-- 5. 关键词搜索 (带智能推荐下拉面板) -->
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
                const container = document.getElementById('app-kpis');
                if (!container) return;

                container.innerHTML = kpis.map(kpi => {
                    const cardType = kpi.type || 'mc01';

                    // 1. mc01: Standard Value Card
                    if (cardType === 'mc01') {
                        return `
                            <div class="section-card p-4 flex flex-col justify-between">
                                <div class="flex items-center justify-between mb-1">
                                    <span class="text-xs text-ink-muted font-medium">${kpi.label}</span>
                                    <div class="flex items-center gap-1.5">
                                        <span class="inline-flex items-center gap-1.5 text-[10px] text-[#2F6B55] bg-[#2F6B55]/8 border border-[#2F6B55]/20 px-2 py-0.5 rounded font-medium">
                                            <span class="w-1.5 h-1.5 rounded-full bg-[#2F6B55]"></span>${kpi.statusBadge || '正常核算'}
                                        </span>
                                        <button class="chart-action-btn" data-explain-chart="${kpi.explainKey || 'mc01'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                    </div>
                                </div>
                                <div class="flex items-baseline gap-2 my-1">
                                    <span class="text-2xl font-extrabold text-primary-strong tracking-tight font-mono tabular-nums">${kpi.value}</span>
                                    <span class="text-xs font-semibold ${kpi.isPositive ? 'text-positive' : 'text-negative'} font-mono">${kpi.yoy}</span>
                                </div>
                                <div class="pt-2 mt-1 border-t border-slate-100 text-[11px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '基期参考'}</span>
                                    <span class="text-primary font-semibold">${kpi.subVal || '-'}</span>
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
                                    <button class="chart-action-btn" data-explain-chart="${kpi.explainKey || 'mc02'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="flex items-baseline gap-2 my-1">
                                    <span class="text-2xl font-extrabold text-primary-strong tracking-tight font-mono tabular-nums">${kpi.value}</span>
                                </div>
                                <div class="flex items-center gap-1.5 my-1">
                                    <span class="inline-flex items-center gap-0.5 px-2 py-0.5 rounded text-[10px] font-bold bg-[#A4453C]/10 text-positive border border-[#A4453C]/20 font-mono">${kpi.yoy || '+4.8% YoY'}</span>
                                    <span class="inline-flex items-center gap-0.5 px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-ink-muted border border-slate-200 font-mono">${kpi.mom || '+1.2% MoM'}</span>
                                </div>
                                <div class="pt-2 mt-1 border-t border-slate-100 text-[11px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '同比增量'}</span>
                                    <span class="text-positive font-semibold">${kpi.subVal || '+¥0.0248'}</span>
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
                                    <button class="chart-action-btn" data-explain-chart="${kpi.explainKey || 'mc03'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="flex items-baseline justify-between gap-2">
                                    <div class="flex items-baseline gap-1.5">
                                        <span class="text-2xl font-extrabold text-primary-strong tracking-tight font-mono tabular-nums">${kpi.value}</span>
                                        <span class="text-xs font-bold text-positive font-mono">${kpi.yoy}</span>
                                    </div>
                                    <span class="text-[10px] text-[#2F6B55] font-semibold bg-[#2F6B55]/8 border border-[#2F6B55]/20 px-1.5 py-0.5 rounded font-mono">↑ 稳步攀升</span>
                                </div>
                                <div id="kpi-spark-${kpi.id}" class="w-full h-11 my-1"></div>
                                <div class="pt-1.5 border-t border-slate-100 text-[10px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '12M 均值: 84.5%'}</span>
                                    <span class="text-ink-muted font-semibold">${kpi.subVal || '峰值: 91.2%'}</span>
                                </div>
                            </div>
                        `;
                    }

                    // 4. mc04: Goal & Progress Bar Card
                    if (cardType === 'mc04') {
                        const progress = parseFloat(kpi.value) || 88.6;
                        const barWidth = Math.min(100, progress);
                        return `
                            <div class="section-card p-4 flex flex-col justify-between">
                                <div class="flex items-center justify-between mb-1">
                                    <span class="text-xs text-ink-muted font-medium">${kpi.label}</span>
                                    <button class="chart-action-btn" data-explain-chart="${kpi.explainKey || 'mc04'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="flex items-baseline justify-between my-0.5">
                                    <span class="text-2xl font-extrabold text-primary-strong tracking-tight font-mono tabular-nums">${kpi.value}</span>
                                    <span class="text-[11px] font-bold text-primary font-mono">${kpi.yoy || '达成领跑'}</span>
                                </div>
                                <div class="w-full bg-slate-200/80 h-2.5 rounded-full overflow-hidden my-1.5">
                                    <div class="bg-primary h-full rounded-full transition-all" style="width: ${barWidth}%;"></div>
                                </div>
                                <div class="pt-1.5 border-t border-slate-100 text-[11px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '计划 52.0亿ASK'}</span>
                                    <span class="text-positive font-bold">${kpi.subVal || '实际 54.2亿ASK'}</span>
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
                                    <button class="chart-action-btn" data-explain-chart="${kpi.explainKey || 'mc05'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="flex items-baseline justify-between gap-2">
                                    <div class="flex items-baseline gap-1.5">
                                        <span class="text-2xl font-extrabold text-primary-strong tracking-tight font-mono tabular-nums">${kpi.value}</span>
                                    </div>
                                    <span class="text-[10px] text-primary font-semibold bg-primary/8 border border-primary/20 px-1.5 py-0.5 rounded font-mono">${kpi.gaugeSub || '领跑全行业'}</span>
                                </div>
                                <div id="kpi-gauge-${kpi.id}" class="w-full h-11 my-1"></div>
                                <div class="pt-1.5 border-t border-slate-100 text-[10px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '行业五星基准: 90.0%'}</span>
                                    <span class="text-negative font-semibold">${kpi.subVal || '超标 +2.4pp'}</span>
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
                                    <button class="chart-action-btn" data-explain-chart="${kpi.explainKey || 'mc06'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="grid grid-cols-2 gap-2 divide-x divide-slate-100 my-1">
                                    <div>
                                        <span class="text-[10px] text-ink-subtle block">${kpi.leftTitle || '供给 ASK'}</span>
                                        <div class="text-lg font-extrabold text-primary-strong font-mono tabular-nums">${kpi.leftVal || '54.2亿'}</div>
                                        <span class="text-[10px] text-positive font-bold font-mono">${kpi.leftYoy || '+12.4%'}</span>
                                    </div>
                                    <div class="pl-2">
                                        <span class="text-[10px] text-ink-subtle block">${kpi.rightTitle || '周转 RPK'}</span>
                                        <div class="text-lg font-extrabold text-primary font-mono tabular-nums">${kpi.rightVal || '47.0亿'}</div>
                                        <span class="text-[10px] text-positive font-bold font-mono">${kpi.rightYoy || '+18.2%'}</span>
                                    </div>
                                </div>
                                <div class="pt-2 mt-1 border-t border-slate-100 text-[11px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '周转匹配率'}</span>
                                    <span class="text-primary font-semibold">${kpi.subVal || '86.8%'}</span>
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
                                    <button class="chart-action-btn" data-explain-chart="${kpi.explainKey || 'mc07'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="flex items-center justify-between my-1">
                                    <div class="flex items-center gap-2">
                                        <span class="w-7 h-7 rounded-full bg-[#9A6A18]/10 border border-[#9A6A18]/25 text-[#9A6A18] flex items-center justify-center font-bold text-xs shadow-xs">
                                            ${LUCIDE_ICONS.award}
                                        </span>
                                        <div>
                                            <span class="text-sm font-extrabold text-primary-strong">${kpi.value}</span>
                                            <p class="text-[10px] text-ink-subtle">${kpi.rankSub || '全行业领跑'}</p>
                                        </div>
                                    </div>
                                    <span class="px-2 py-0.5 rounded bg-primary text-white text-[11px] font-mono font-bold">S 级标杆</span>
                                </div>
                                <div class="pt-2 mt-1 border-t border-slate-100 text-[11px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '市场占有率'}</span>
                                    <span class="text-primary font-semibold">${kpi.subVal || '32.8% (+5.4%)'}</span>
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
                                    <button class="chart-action-btn" data-explain-chart="${kpi.explainKey || 'mc08'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="flex items-baseline gap-2 my-1">
                                    <span class="text-2xl font-extrabold text-[#0B2A42] tracking-tight font-mono tabular-nums">${kpi.value}</span>
                                    <span class="px-2 py-0.5 rounded bg-[#9A6A18]/15 border border-[#9A6A18]/30 text-[#9A6A18] text-[10px] font-bold font-mono">预算红线 5%</span>
                                </div>
                                <div class="pt-2 mt-1 border-t border-[#9A6A18]/20 text-[11px] text-ink-muted flex items-center justify-between font-mono">
                                    <span>${kpi.subLabel || '占总成本 29.3%'}</span>
                                    <span class="font-bold text-[#9A6A18]">${kpi.subVal || '套保收益 +¥0.8亿'}</span>
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
                                    <button class="chart-action-btn" data-explain-chart="${kpi.explainKey || 'mc09'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                                </div>
                                <div class="flex items-baseline justify-between my-0.5">
                                    <span class="text-xl font-extrabold text-primary-strong tracking-tight font-mono tabular-nums">${kpi.value}</span>
                                    <span class="text-[10px] text-ink-subtle font-mono">${kpi.yoy || '结构均衡'}</span>
                                </div>
                                <div class="w-full h-2.5 rounded-full overflow-hidden flex my-1.5 shadow-inner bg-slate-100">
                                    <div class="bg-primary h-full transition-all" style="width: ${kpi.segLeftWidth || '72%'};"></div>
                                    <div class="bg-[#8EA4B8] h-full transition-all" style="width: ${kpi.segRightWidth || '28%'};"></div>
                                </div>
                                <div class="pt-1.5 border-t border-slate-100 text-[10px] text-ink-subtle flex items-center justify-between font-mono">
                                    <span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-primary"></span>${kpi.subLabel || '国内: 72%'}</span>
                                    <span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-[#8EA4B8]"></span>${kpi.subVal || '国际: 28%'}</span>
                                </div>
                            </div>
                        `;
                    }

                    // Default Standard Card Fallback
                    return `
                        <div class="section-card p-4 flex flex-col justify-between">
                            <div class="flex items-center justify-between mb-1">
                                <span class="text-xs text-ink-muted font-medium">${kpi.label}</span>
                                <button class="chart-action-btn" data-explain-chart="${kpi.explainKey || 'mc01'}" aria-label="查看指标说明" title="查看指标说明">${LUCIDE_ICONS.info}</button>
                            </div>
                            <div class="flex items-baseline gap-2 my-1">
                                <span class="text-2xl font-extrabold text-primary-strong tracking-tight font-mono tabular-nums">${kpi.value}</span>
                                <span class="text-xs font-semibold ${kpi.isPositive ? 'text-positive' : 'text-negative'} font-mono">${kpi.yoy}</span>
                            </div>
                            <div class="pt-2 mt-1 border-t border-slate-100 text-[11px] text-ink-subtle flex items-center justify-between font-mono">
                                <span>${kpi.subLabel}</span>
                                <span class="text-primary font-semibold">${kpi.subVal}</span>
                            </div>
                        </div>
                    `;
                }).join('');
            }

            renderChartsGrid() {
                const charts = this.config.charts || [];
                const container = document.getElementById('app-charts-grid');
                if (!container) return;

                container.innerHTML = charts.map(chart => {
                    const colClass = chart.colSpan === 2 ? 'lg:col-span-2' : '';
                    const granTabs = chart.hasGranularity ? `
                        <div class="inline-flex bg-slate-100/90 p-0.5 rounded-md text-[11px]">
                            <button type="button" class="granularity-tab-btn px-2 py-0.5 rounded bg-white text-primary-strong font-semibold shadow-xs" data-card-code="${chart.code}" data-granularity="month">月度</button>
                            <button type="button" class="granularity-tab-btn px-2 py-0.5 rounded text-ink-muted hover:text-ink font-medium" data-card-code="${chart.code}" data-granularity="quarter">季度</button>
                        </div>
                    ` : '';

                    return `
                        <div class="section-card p-5 flex flex-col justify-between ${colClass}">
                            <!-- Card Header -->
                            <div class="card-header-wrap flex flex-wrap items-start justify-between gap-3 mb-3" id="header-${chart.code}">
                                <div class="min-w-0 max-w-[65%]">
                                    
                                    <div class="min-w-0">
                                        <h3 class="text-sm font-bold text-primary-strong tracking-tight truncate">${chart.title}</h3>
                                        <p class="text-xs text-ink-muted mt-0.5">${chart.subtitle}</p>
                                    </div>
                                </div>
                                <div class="flex items-center gap-1.5 flex-shrink-0">
                                    ${granTabs}
                                    <!-- View Toggle (Chart ↔ Table) -->
                                    <button type="button" class="chart-action-btn view-toggle-btn" data-card-code="${chart.code}" aria-label="切换图表/数据表视图" title="切换图表/动态数据表视图">
                                        ${LUCIDE_ICONS.viewToggle}
                                    </button>
                                    <!-- Export Chart CSV -->
                                    <button type="button" class="chart-action-btn export-chart-btn" data-card-code="${chart.code}" data-chart-title="${chart.title}" aria-label="导出图表数据为 CSV / Excel" title="导出图表当前结构化数据 (CSV / Excel)">
                                        ${LUCIDE_ICONS.export}
                                    </button>
                                    <!-- Copy Chart PNG -->
                                    <button type="button" class="chart-action-btn copy-chart-btn" data-card-code="${chart.code}" data-chart-title="${chart.title}" aria-label="复制高清图表至剪贴板" title="复制高清图表至剪贴板 (可直接粘贴入 PPT)">
                                        ${LUCIDE_ICONS.copy}
                                    </button>
                                    <!-- Fullscreen Focus -->
                                    <button type="button" class="chart-action-btn fullscreen-btn" data-card-code="${chart.code}" aria-label="全屏沉浸研判" title="全屏沉浸研判 (Esc退出)">
                                        ${LUCIDE_ICONS.maximize}
                                    </button>
                                    <!-- Info Dialog -->
                                    <button type="button" class="chart-action-btn" data-explain-chart="${chart.explainKey || chart.code}" aria-label="查看业务口径说明" title="查看业务口径说明">
                                        ${LUCIDE_ICONS.info}
                                    </button>
                                </div>
                            </div>
                            <!-- Card Body Pane -->
                            <div class="card-body-wrap relative w-full h-[270px] overflow-hidden">
                                <div id="${chart.id}" class="card-chart-pane w-full h-full"></div>
                                <div id="table-pane-${chart.code}" class="card-table-pane hidden w-full h-full"></div>
                            </div>
                        </div>
                    `;
                }).join('');
            }

            renderTableSection() {
                const tableCfg = this.config.table;
                const container = document.getElementById('app-table-section');
                if (!container) return;

                container.innerHTML = `
                    <div class="flex flex-wrap items-center justify-between gap-4 mb-4 pb-3 border-b border-slate-100">
                        <div class="flex items-center gap-2">
                            <span class="w-2.5 h-2.5 rounded-full bg-primary flex-shrink-0"></span>
                            <h3 class="text-sm font-bold text-primary-strong tracking-tight">${tableCfg.title || '全要素业务运营效能多维透视表'}</h3>
                            
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
                            <button class="chart-action-btn" data-explain-chart="table_airline_main" aria-label="查看表格指标说明" title="查看表格指标说明">
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
                const container = document.getElementById('app-explain-dialog');
                if (!container) return;
                container.className = 'explanation-dialog';
                container.innerHTML = '';
            }

            renderExplanationDialogContent(chartKey, explanations) {
                const cardEl = document.querySelector(`[data-explain-chart="${chartKey}"]`)?.closest('.section-card');
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

                let html = `
                    <header class="exp-dialog-topbar">
                        <div class="flex items-center gap-2.5 min-w-0">
                            <span class="w-6 h-6 rounded-md bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                                ${LUCIDE_ICONS.info}
                            </span>
                            <h3 class="text-sm font-bold text-primary-strong truncate">${expTitle}</h3>
                        </div>
                        <button id="closeExplainModalBtn" class="dialog-close w-7 h-7 rounded-md flex items-center justify-center text-ink-subtle hover:bg-slate-100 hover:text-ink cursor-pointer transition-colors" aria-label="关闭">
                            ${LUCIDE_ICONS.close}
                        </button>
                    </header>
                    <div class="exp-dialog-body custom-scrollbar space-y-3">
                        <div class="exp-overview-box">
                            <p class="text-xs text-ink leading-relaxed m-0">${expOverview}</p>
                            <div class="exp-specs-strip">
                                <span class="exp-spec-badge"><strong class="text-ink-subtle font-medium mr-1">指标/图表类型:</strong>${expType}</span>
                                <span class="exp-spec-badge"><strong class="text-ink-subtle font-medium mr-1">统计分析周期:</strong>${expPeriod}</span>
                                <span class="exp-spec-badge"><strong class="text-ink-subtle font-medium mr-1">对标决策基准:</strong>${expComparison}</span>
                            </div>
                        </div>

                        <div class="border border-slate-200 rounded-lg p-3.5 bg-white space-y-2.5">
                            <div class="text-xs font-bold text-primary flex items-center gap-1.5">
                                <span class="w-4 h-4 text-primary inline-flex items-center justify-center">${LUCIDE_ICONS.layers}</span>
                                <span>坐标系维度与数据序列架构</span>
                            </div>
                            <div class="exp-axis-grid">
                                <div class="exp-axis-cell">
                                    <div class="font-bold text-primary-strong mb-1">X 轴 · ${structure.xAxis.name}</div>
                                    <div class="text-ink-muted text-[11px]"><span class="text-ink-subtle mr-1.5">业务含义:</span>${structure.xAxis.meaning}</div>
                                    <div class="text-ink-muted text-[11px]"><span class="text-ink-subtle mr-1.5">覆盖范围:</span>${structure.xAxis.range}</div>
                                </div>
                                <div class="exp-axis-cell">
                                    <div class="font-bold text-primary-strong mb-1">Y 轴 · ${structure.yAxis.name}</div>
                                    <div class="text-ink-muted text-[11px]"><span class="text-ink-subtle mr-1.5">业务含义:</span>${structure.yAxis.meaning}</div>
                                    <div class="text-ink-muted text-[11px]"><span class="text-ink-subtle mr-1.5">量纲刻度:</span>${structure.yAxis.range}</div>
                                </div>
                            </div>
                            ${structure.series && structure.series.length ? `
                                <div class="flex flex-wrap gap-2 pt-1">
                                    ${structure.series.map(s => `
                                        <div class="inline-flex items-center gap-1 text-[11px] bg-slate-50 border border-slate-200 px-2 py-0.5 rounded">
                                            <span class="w-1.5 h-1.5 rounded-full bg-primary"></span>
                                            <span class="font-semibold text-ink">${s.name}</span>
                                            <span class="text-ink-subtle">(${s.desc})</span>
                                        </div>
                                    `).join("")}
                                </div>
                            ` : ""}
                        </div>

                        <div class="space-y-2">
                            <div class="text-xs font-bold text-primary flex items-center gap-1.5">
                                <span class="w-4 h-4 text-primary inline-flex items-center justify-center">${LUCIDE_ICONS.calculator}</span>
                                <span>核心指标业务口径与数学公式</span>
                            </div>
                            <div class="space-y-2">
                                ${metrics.map(m => `
                                    <div class="exp-metric-card space-y-1.5">
                                        <div class="flex items-center justify-between">
                                            <span class="text-xs font-bold text-primary-strong">${m.name}</span>
                                        </div>
                                        <div class="text-xs flex items-baseline gap-2">
                                            <span class="text-ink-subtle w-16 shrink-0 text-[11px]">业务定义</span>
                                            <span class="text-ink leading-relaxed">${m.definition}</span>
                                        </div>
                                        <div class="text-xs flex items-baseline gap-2">
                                            <span class="text-ink-subtle w-16 shrink-0 text-[11px]">计算公式</span>
                                            <span class="text-ink"><code class="exp-formula font-mono">${m.formula}</code></span>
                                        </div>
                                        ${m.rule ? `
                                            <div class="text-xs flex items-baseline gap-2">
                                                <span class="text-ink-subtle w-16 shrink-0 text-[11px]">治理规则</span>
                                                <span class="text-ink-muted text-[11.5px] leading-relaxed">${m.rule}</span>
                                            </div>
                                        ` : ""}
                                    </div>
                                `).join("")}
                            </div>
                        </div>
                    </div>
                    <div class="p-3 bg-slate-50 border-t border-slate-200 flex justify-end">
                        <button id="closeExplainModalFooterBtn" type="button" class="px-4 py-1.5 bg-primary text-white text-xs font-semibold rounded-md hover:bg-primary-strong transition-colors cursor-pointer shadow-xs">我知道了</button>
                    </div>
                `;

                return html;
            }
        }

        // 5. Main Application Controller
        class DashboardApp {
            constructor(config) {
                this.config = config;
                this.state = new StateStore(config);
                this.renderer = new DashboardRenderer(this.state);
                this.draggedColKey = null;
            }

            init() {
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
            }

            initKPIWidgets() {
                const kpis = this.config.kpis || [];
                kpis.forEach(kpi => {
                    // 1. mc03: Sparkline Micro Chart
                    if (kpi.type === 'mc03') {
                        const dom = document.getElementById(`kpi-spark-${kpi.id}`);
                        if (dom) {
                            const inst = echarts.init(dom);
                            this.state.chartInstances[`kpi-spark-${kpi.id}`] = inst;
                            const months = kpi.sparkMonths || ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];
                            const seriesData = kpi.sparkData || [81.5, 82.4, 83.0, 84.5, 85.2, 85.8, 86.2, 87.8, 85.5, 86.0, 86.4, 86.8];
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
                                        return `<div class="text-[11px] font-mono"><span class="font-bold text-primary">${p.name}:</span> <span class="font-bold text-ink">${p.value}${p.value > 10 ? '%' : ''}</span></div>`;
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
                        const dom = document.getElementById(`kpi-gauge-${kpi.id}`);
                        if (dom) {
                            const inst = echarts.init(dom);
                            this.state.chartInstances[`kpi-gauge-${kpi.id}`] = inst;
                            const val = parseFloat(kpi.value) || 92.4;
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

            initCharts() {
                const charts = this.config.charts || [];
                charts.forEach(chartCfg => {
                    const dom = document.getElementById(chartCfg.id);
                    if (!dom) return;
                    const inst = echarts.init(dom);
                    this.state.chartInstances[chartCfg.code] = inst;
                    this.state.chartGranularities[chartCfg.code] = chartCfg.defaultGranularity || 'month';

                    // Build and set option
                    const opt = chartCfg.optionBuilder(chartCfg.data, this.state.chartGranularities[chartCfg.code], TOKENS);
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
                                inst.resize();
                            }
                        }
                    });
                    document.querySelectorAll('.card-chart-pane, .section-card div[id^="kpi-spark-"], .section-card div[id^="kpi-gauge-"]').forEach(el => observer.observe(el));
                }

                window.addEventListener('resize', () => {
                    Object.values(this.state.chartInstances).forEach(inst => inst?.resize());
                });
            }

            bindEvents() {
                // Dropdown dismiss on outside click
                document.addEventListener('click', (e) => {
                    if (!e.target.closest('[id^="filter"]') && !e.target.closest('[id$="DropdownMenu"]') && !e.target.closest('#colDrawerWrap') && !e.target.closest('#globalSearchWrap')) {
                        document.querySelectorAll('[id$="DropdownMenu"]').forEach(m => m.classList.add('hidden'));
                        document.getElementById('colDrawerMenu')?.classList.add('hidden');
                        document.getElementById('searchSuggestionsDropdown')?.classList.add('hidden');
                    }
                });

                // Explain Modal Trigger
                const modal = document.getElementById('app-explain-dialog');
                document.addEventListener('click', (e) => {
                    const btn = e.target.closest('[data-explain-chart]');
                    if (btn && modal) {
                        const code = btn.getAttribute('data-explain-chart');
                        const htmlContent = this.renderer.renderExplanationDialogContent(code, this.config.explanations);
                        modal.innerHTML = htmlContent;

                        document.getElementById('closeExplainModalBtn')?.addEventListener('click', () => modal?.close());
                        document.getElementById('closeExplainModalFooterBtn')?.addEventListener('click', () => modal?.close());

                        if (typeof modal.showModal === 'function') {
                            modal.showModal();
                        } else {
                            modal.setAttribute('open', '');
                        }
                    }
                });

                modal?.addEventListener('click', (e) => {
                    const rect = modal.getBoundingClientRect();
                    if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {
                        modal.close();
                    }
                });

                // Granularity Switcher
                document.addEventListener('click', (e) => {
                    const tabBtn = e.target.closest('.granularity-tab-btn');
                    if (tabBtn) {
                        const code = tabBtn.getAttribute('data-card-code');
                        const gran = tabBtn.getAttribute('data-granularity');
                        const parent = tabBtn.parentElement;
                        parent.querySelectorAll('.granularity-tab-btn').forEach(b => {
                            b.classList.remove('bg-white', 'text-primary-strong', 'font-semibold', 'shadow-xs');
                            b.classList.add('text-ink-muted');
                        });
                        tabBtn.classList.remove('text-ink-muted');
                        tabBtn.classList.add('bg-white', 'text-primary-strong', 'font-semibold', 'shadow-xs');

                        const chartCfg = (this.config.charts || []).find(c => c.code === code);
                        const inst = this.state.chartInstances[code];
                        if (chartCfg && inst) {
                            this.state.chartGranularities[code] = gran;
                            const newOpt = chartCfg.optionBuilder(chartCfg.data, gran, TOKENS);
                            inst.setOption(newOpt, true);
                            
                            // If table pane is active, refresh table dynamically
                            const card = tabBtn.closest('.section-card');
                            const tablePane = card.querySelector('.card-table-pane');
                            if (tablePane && !tablePane.classList.contains('hidden')) {
                                this.renderDynamicChartTable(code, tablePane);
                            }
                            
                            this.showToast(`已切换为${gran === 'month' ? '月度' : '季度'}统计口径`);
                        }
                    }
                });

                // View Toggle (Chart ↔ Dynamic Auto-Converted Table)
                document.addEventListener('click', (e) => {
                    const btn = e.target.closest('.view-toggle-btn');
                    if (btn) {
                        const code = btn.getAttribute('data-card-code');
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
                                tablePane.classList.add('hidden');
                                chartPane.classList.remove('hidden');
                                btn.classList.remove('active-state');
                                this.state.chartInstances[code]?.resize();
                                this.showToast('已切回 ECharts 可视化图表视图');
                            }
                        }
                    }
                });

                // Export Chart CSV Data (One Click per Chart)
                document.addEventListener('click', (e) => {
                    const btn = e.target.closest('.export-chart-btn');
                    if (btn) {
                        const code = btn.getAttribute('data-card-code');
                        const title = btn.getAttribute('data-chart-title') || '图表数据';
                        const inst = this.state.chartInstances[code];
                        const chartCfg = (this.config.charts || []).find(c => c.code === code);
                        
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
                });

                // Copy Chart to Clipboard
                document.addEventListener('click', (e) => {
                    const btn = e.target.closest('.copy-chart-btn');
                    if (btn) {
                        const code = btn.getAttribute('data-card-code');
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
                });

                // Fullscreen Focus Mode
                document.addEventListener('click', (e) => {
                    const btn = e.target.closest('.fullscreen-btn');
                    if (btn) {
                        const code = btn.getAttribute('data-card-code');
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
                });

                // Esc to exit fullscreen
                window.addEventListener('keydown', (e) => {
                    if (e.key === 'Escape') {
                        document.querySelectorAll('.card-fullscreen').forEach(card => {
                            card.classList.remove('card-fullscreen');
                            const btn = card.querySelector('.fullscreen-btn');
                            if (btn) {
                                btn.innerHTML = LUCIDE_ICONS.maximize;
                                btn.setAttribute('title', '全屏沉浸研判 (Esc退出)');
                            }
                        });
                        Object.values(this.state.chartInstances).forEach(i => i?.resize());
                    }
                });
            }

            renderDynamicChartTable(code, tablePane) {
                const inst = this.state.chartInstances[code];
                const chartCfg = (this.config.charts || []).find(c => c.code === code);
                const tdata = ChartDataToTableConverter.convert(inst, chartCfg);
                if (tdata && tdata.headers && tdata.rows) {
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
                                    ${tdata.rows.map(r => `
                                        <tr class="hover:bg-slate-50 transition-colors even:bg-slate-50/50">
                                            ${r.map((v, i) => `
                                                <td class="px-3 py-2 font-mono text-[11px] text-[#17212B] border-b border-slate-100 ${i > 0 ? 'font-semibold' : ''}">
                                                    ${v}
                                                </td>
                                            `).join('')}
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    `;
                }
            }

            // Filter Handlers
            toggleDropdown(id, event) {
                if (event) event.stopPropagation();
                const el = document.getElementById(id);
                if (!el) return;
                const isHidden = el.classList.contains('hidden');
                document.querySelectorAll('[id$="DropdownMenu"]').forEach(m => m.classList.add('hidden'));
                document.getElementById('colDrawerMenu')?.classList.add('hidden');
                document.getElementById('searchSuggestionsDropdown')?.classList.add('hidden');
                if (isHidden) el.classList.remove('hidden');
            }

            // Search Autocomplete Suggestions
            showSearchSuggestions() {
                const query = document.getElementById('globalKeywordSearch')?.value.trim();
                const dropdown = document.getElementById('searchSuggestionsDropdown');
                const content = document.getElementById('searchSuggestionsContent');
                if (!dropdown || !content) return;

                document.querySelectorAll('[id$="DropdownMenu"]').forEach(m => m.classList.add('hidden'));
                document.getElementById('colDrawerMenu')?.classList.add('hidden');

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
                const clearBtn = document.getElementById('clearSearchBtn');
                if (clearBtn) {
                    if (val) clearBtn.classList.remove('hidden');
                    else clearBtn.classList.add('hidden');
                }
                this.showSearchSuggestions();
                this.onGlobalFilterChange();
            }

            onSearchKeyDown(e) {
                if (e.key === 'Enter' || e.key === 'Escape') {
                    document.getElementById('searchSuggestionsDropdown')?.classList.add('hidden');
                }
            }

            applySearchKeyword(val) {
                const input = document.getElementById('globalKeywordSearch');
                if (input) {
                    input.value = val;
                    document.getElementById('clearSearchBtn')?.classList.remove('hidden');
                }
                document.getElementById('searchSuggestionsDropdown')?.classList.add('hidden');
                this.onGlobalFilterChange();
                this.showToast(`已应用检索: 「${val}」`);
            }

            clearSearchKeyword(e) {
                if (e) e.stopPropagation();
                const input = document.getElementById('globalKeywordSearch');
                if (input) input.value = '';
                document.getElementById('clearSearchBtn')?.classList.add('hidden');
                document.getElementById('searchSuggestionsDropdown')?.classList.add('hidden');
                this.onGlobalFilterChange();
                this.showToast('已清空关键词检索');
            }

            selectGlobalTime(val, label) {
                this.state.filters.time = val;
                this.state.filters.timeLabel = label;
                document.getElementById('selectedTimeLabel').textContent = label;
                document.getElementById('timeDropdownMenu').classList.add('hidden');
                this.onGlobalFilterChange();
            }

            selectGlobalFleet(val, label) {
                this.state.filters.fleet = val;
                this.state.filters.fleetLabel = label;
                document.getElementById('selectedFleetLabel').textContent = label;
                document.getElementById('fleetDropdownMenu').classList.add('hidden');
                this.onGlobalFilterChange();
            }

            selectGlobalRoute(val, label) {
                this.state.filters.route = val;
                this.state.filters.routeLabel = label;
                document.getElementById('selectedRouteLabel').textContent = label;
                document.getElementById('routeDropdownMenu').classList.add('hidden');
                this.onGlobalFilterChange();
            }

            filterHubDropdownList() {
                const q = document.getElementById('hubSearchInput').value.toLowerCase();
                document.querySelectorAll('.hub-opt-row').forEach(row => {
                    const label = row.getAttribute('data-label').toLowerCase();
                    row.style.display = (!q || label.includes(q)) ? 'flex' : 'none';
                });
            }

            setAllHubs(check) {
                document.querySelectorAll('#hubOptionsContainer input[type="checkbox"]').forEach(cb => cb.checked = check);
                this.onGlobalFilterChange();
            }

            onGlobalFilterChange() {
                const checkedHubs = Array.from(document.querySelectorAll('#hubOptionsContainer input[type="checkbox"]:checked')).map(c => c.value);
                this.state.filters.hubs = new Set(checkedHubs);
                this.state.filters.keyword = document.getElementById('globalKeywordSearch')?.value.trim() || '';

                const totalHubCount = (this.config.filters?.hubs || []).length || 4;
                const hubLabelText = this.state.filterLabels.hub;
                document.getElementById('hubCountBadge').textContent = checkedHubs.length;
                document.getElementById('selectedHubLabel').textContent = checkedHubs.length === totalHubCount ? `全部${hubLabelText}` : (checkedHubs.length === 0 ? `未选${hubLabelText} (0)` : `已选 ${checkedHubs.length} 个`);

                this.updateActiveChips();
                this.state.table.page = 1;
                this.renderTableEngine();
                this.updateKPIsAndChartsFromFilters();
            }

            updateKPIsAndChartsFromFilters() {
                const rows = this.getFilteredTableRows();
                const allRows = this.config.table?.rows || [];
                const isFiltered = rows.length < allRows.length;

                // 1. Dynamically update KPI Cards
                if (rows.length > 0) {
                    (this.config.kpis || []).forEach(kpi => {
                        const kpiCard = document.querySelector(`[data-explain-chart="${kpi.explainKey}"]`)?.closest('.section-card');
                        if (!kpiCard) return;

                        const valEl = kpiCard.querySelector('.font-mono.tabular-nums');
                        if (!valEl) return;

                        if (!kpi._origValue) kpi._origValue = kpi.value;
                        if (!isFiltered) {
                            valEl.textContent = kpi._origValue;
                        }
                    });
                }

                // 2. Dynamically update Charts (Generic & Clean)
                const charts = this.config.charts || [];
                charts.forEach(chartCfg => {
                    const code = chartCfg.code;
                    const inst = this.state.chartInstances[code];
                    if (!inst) return;
                    const gran = this.state.chartGranularities[code] || 'month';

                    try {
                        if (typeof chartCfg.onFilterChange === 'function') {
                            chartCfg.onFilterChange(rows, isFiltered, inst, TOKENS);
                        } else if (typeof chartCfg.optionBuilder === 'function') {
                            const opt = chartCfg.optionBuilder(chartCfg.data, gran, TOKENS);
                            inst.setOption(opt, true);
                        }

                        // If table pane is currently open for this card, refresh table dynamically
                        const cardEl = document.getElementById(chartCfg.id)?.closest('.section-card');
                        const tablePane = cardEl?.querySelector('.card-table-pane');
                        if (tablePane && !tablePane.classList.contains('hidden')) {
                            this.renderDynamicChartTable(code, tablePane);
                        }
                    } catch (err) {
                        console.error('Error updating chart ' + code, err);
                    }
                });
            }

            updateActiveChips() {
                const tray = document.getElementById('activeChipsTray');
                const container = document.getElementById('chipsContainer');
                const badge = document.getElementById('activeFilterBadgeCount');
                if (!tray || !container) return;

                const labels = this.state.filterLabels;
                const totalHubCount = (this.config.filters?.hubs || []).length || 4;
                let chips = [];
                if (this.state.filters.time !== this.state.defaultFilters.time) {
                    chips.push({ key: 'time', label: `${labels.time}: ${this.state.filters.timeLabel}` });
                }
                if (this.state.filters.hubs.size > 0 && this.state.filters.hubs.size < totalHubCount) {
                    chips.push({ key: 'hub', label: `${labels.hub}: ${Array.from(this.state.filters.hubs).join(', ')}` });
                }
                if (this.state.filters.fleet !== 'ALL') {
                    chips.push({ key: 'fleet', label: `${labels.fleet}: ${this.state.filters.fleetLabel}` });
                }
                if (this.state.filters.route !== 'ALL') {
                    chips.push({ key: 'route', label: `${labels.route}: ${this.state.filters.routeLabel}` });
                }
                if (this.state.filters.keyword) {
                    chips.push({ key: 'kw', label: `关键词: "${this.state.filters.keyword}"` });
                }

                badge.textContent = chips.length;
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
                const def = this.state.defaultFilters;
                if (key === 'time') this.selectGlobalTime(def.time, def.timeLabel);
                if (key === 'hub') this.setAllHubs(true);
                if (key === 'fleet') this.selectGlobalFleet('ALL', def.fleetLabel);
                if (key === 'route') this.selectGlobalRoute('ALL', def.routeLabel);
                if (key === 'kw') { document.getElementById('globalKeywordSearch').value = ''; this.onGlobalFilterChange(); }
            }

            resetAllGlobalFilters() {
                const def = this.state.defaultFilters;
                const totalHubCount = (this.config.filters?.hubs || []).length || 4;
                const isTimeDefault = this.state.filters.time === def.time;
                const isFleetDefault = this.state.filters.fleet === 'ALL';
                const isRouteDefault = this.state.filters.route === 'ALL';
                const isSearchDefault = !document.getElementById('globalKeywordSearch')?.value?.trim();
                const isHubsAll = (!this.state.filters.hubs || this.state.filters.hubs.size === totalHubCount);
                const isCrossFilterEmpty = !this.state.filters.chartCrossFilter;

                const isAlreadyDefault = isTimeDefault && isFleetDefault && isRouteDefault && isSearchDefault && isHubsAll && isCrossFilterEmpty;

                if (isAlreadyDefault) {
                    this.showToast('当前已处于全局基准视图');
                    return;
                }

                this.selectGlobalTime(def.time, def.timeLabel);
                this.selectGlobalFleet('ALL', def.fleetLabel);
                this.selectGlobalRoute('ALL', def.routeLabel);
                if (document.getElementById('globalKeywordSearch')) document.getElementById('globalKeywordSearch').value = '';
                this.setAllHubs(true);
                this.state.filters.chartCrossFilter = null;
                document.getElementById('tableCrossFilterTray')?.classList.add('hidden');
                this.updateKPIsAndChartsFromFilters();
                this.showToast('已重置恢复全局基准视图');
            }

            // Cross Filtering
            setTableCrossFilter(val) {
                this.state.filters.chartCrossFilter = val;
                const tray = document.getElementById('tableCrossFilterTray');
                const txt = document.getElementById('tableCrossFilterText');
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
                this.state.filters.chartCrossFilter = null;
                document.getElementById('tableCrossFilterTray')?.classList.add('hidden');
                this.state.table.page = 1;
                this.renderTableEngine();
                this.updateKPIsAndChartsFromFilters();
                this.showToast('已清除图表联动过滤');
            }

            // Table Engine with Column Drag-and-Drop
            renderColCheckboxes() {
                const container = document.getElementById('colCheckboxesContainer');
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
                const items = document.querySelectorAll('.drag-col-item');
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
                        document.querySelectorAll('.drag-col-item').forEach(el => el.classList.remove('drag-over', 'dragging'));
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
                const menu = document.getElementById('colDrawerMenu');
                if (!menu) return;
                const isHidden = menu.classList.contains('hidden');
                document.querySelectorAll('[id$="DropdownMenu"]').forEach(m => m.classList.add('hidden'));
                document.getElementById('searchSuggestionsDropdown')?.classList.add('hidden');
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
                const totalPages = Math.ceil(this.getFilteredTableRows().length / this.state.table.pageSize);
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

            getFilteredTableRows() {
                let rows = [...(this.config.table.rows || [])];
                const f = this.state.filters;

                // Hubs / Region filter
                const totalHubCount = (this.config.filters?.hubs || []).length || 4;
                if (f.hubs.size > 0 && f.hubs.size < totalHubCount) {
                    rows = rows.filter(r => {
                        const hubVal = r.hub || r.region || r.area || r.zone || r.location || r.segment;
                        if (hubVal && f.hubs.has(hubVal)) return true;
                        return Object.values(r).some(v => typeof v === 'string' && f.hubs.has(v));
                    });
                }

                // Fleet / Format / Segment filter
                if (f.fleet !== 'ALL') {
                    rows = rows.filter(r => {
                        const rowVal = r.fleet || r.format || r.type || r.segment || r.tier || r.category || '';
                        if (String(rowVal).includes(f.fleet) || (f.fleetLabel && String(rowVal).includes(f.fleetLabel))) return true;
                        return Object.values(r).some(v => typeof v === 'string' && (v.includes(f.fleet) || (f.fleetLabel && v.includes(f.fleetLabel))));
                    });
                }

                // Route / Category / Channel filter
                if (f.route !== 'ALL') {
                    rows = rows.filter(r => {
                        const rowVal = r.route || r.routeType || r.channel || r.category || r.product || '';
                        if (String(rowVal).includes(f.route) || (f.routeLabel && String(rowVal).includes(f.routeLabel))) return true;
                        return Object.values(r).some(v => typeof v === 'string' && (v.includes(f.route) || (f.routeLabel && v.includes(f.routeLabel))));
                    });
                }

                // Keyword filter
                if (f.keyword) {
                    const q = f.keyword.toLowerCase();
                    rows = rows.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(q)));
                }

                // Chart Cross filter
                if (f.chartCrossFilter) {
                    const cf = f.chartCrossFilter.toLowerCase();
                    rows = rows.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(cf)));
                }

                // Sort
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

            renderTableEngine() {
                const thead = document.getElementById('main14ColThead');
                const tbody = document.getElementById('main14ColTbody');
                if (!thead || !tbody) return;

                const visibleCols = this.state.table.orderedColumns.filter(c => this.state.table.visibleCols.has(c.key));
                const allFiltered = this.getFilteredTableRows();
                const total = allFiltered.length;
                const pageSize = this.state.table.pageSize;
                const totalPages = Math.max(1, Math.ceil(total / pageSize));

                if (this.state.table.page > totalPages) this.state.table.page = totalPages;
                const startIdx = (this.state.table.page - 1) * pageSize;
                const currentRows = allFiltered.slice(startIdx, startIdx + pageSize);

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

                // Render Tbody (Strict single line with tabular nums)
                if (currentRows.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="${visibleCols.length}" class="py-8 text-center text-ink-subtle">暂无符合筛选条件的数据记录</td></tr>`;
                } else {
                    tbody.innerHTML = currentRows.map(row => `
                        <tr onmouseenter="window.App.onTableRowHover('${row.name}')" onmouseleave="window.App.onTableRowLeave()" class="hover:bg-slate-50/80 transition-colors">
                            ${visibleCols.map(col => {
                                let val = row[col.key] || '-';
                                let cellStyle = '';
                                if (col.key === 'yoy' && String(val).startsWith('+')) cellStyle = 'text-positive font-bold';
                                if (col.key === 'rating') {
                                    if (val.includes('S')) val = `<span class="px-2 py-0.5 rounded bg-[#123B5D]/10 text-primary border border-[#123B5D]/20 font-bold text-[10px] whitespace-nowrap">${val}</span>`;
                                    else if (val.includes('A')) val = `<span class="px-2 py-0.5 rounded bg-[#2F6B55]/10 text-negative border border-[#2F6B55]/20 font-bold text-[10px] whitespace-nowrap">${val}</span>`;
                                    else val = `<span class="px-2 py-0.5 rounded bg-slate-100 text-ink-muted border border-slate-200 text-[10px] whitespace-nowrap">${val}</span>`;
                                }
                                return `<td onclick="window.App.copyCell('${row[col.key] || ''}')" class="px-3.5 py-2 text-${col.align} font-mono text-[11px] cursor-pointer hover:underline whitespace-nowrap ${cellStyle}" title="点击复制">${val}</td>`;
                            }).join('')}
                        </tr>
                    `).join('');
                }

                // Update Pagination Info
                const pageInfo = document.getElementById('tablePaginationInfo');
                const pageIndicator = document.getElementById('tablePageIndicator');
                const prevBtn = document.getElementById('tablePrevBtn');
                const nextBtn = document.getElementById('tableNextBtn');

                if (pageInfo) pageInfo.textContent = `显示第 ${total === 0 ? 0 : startIdx + 1} - ${Math.min(startIdx + pageSize, total)} 条 · 共 ${total} 条`;
                if (pageIndicator) pageIndicator.textContent = `${this.state.table.page} / ${totalPages}`;
                if (prevBtn) prevBtn.disabled = this.state.table.page <= 1;
                if (nextBtn) nextBtn.disabled = this.state.table.page >= totalPages;
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
                const rows = allRows.map(r => visibleCols.map(c => `"${r[c.key] || ''}"`).join(','));
                const csv = '\\uFEFF' + [header, ...rows].join('\\r\\n');
                const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const exportTitle = (this.config.table?.title || this.config.meta?.title || '业务运营透视表').replace(/[\s/\\:]+/g, '_');\n                a.download = `${exportTitle}_${new Date().toISOString().slice(0,10)}.csv`;
                a.click();
                URL.revokeObjectURL(url);
                this.showToast(`已成功导出 ${allRows.length} 条记录至 Excel (CSV)`);
            }

            showToast(msg) {
                const container = document.getElementById('app-toast-container');
                if (!container) return;
                const toast = document.createElement('div');
                toast.className = 'px-4 py-2.5 bg-primary-strong text-white text-xs font-semibold rounded-lg shadow-xl toast-active flex items-center gap-2 border border-slate-700 pointer-events-auto';
                toast.innerHTML = `<span class="flex-shrink-0">${LUCIDE_ICONS.checkCircle}</span><span>${msg}</span>`;
                container.appendChild(toast);
                setTimeout(() => {
                    toast.style.opacity = '0';
                    toast.style.transition = 'opacity 0.3s ease';
                    setTimeout(() => toast.remove(), 300);
                }, 2800);
            }
        }

        // Robust App Bootstrapping (Supports both early & deferred execution)
        function bootApp() {
            if (window.DASHBOARD_CONFIG && !window.App) {
                window.App = new DashboardApp(window.DASHBOARD_CONFIG);
                window.App.init();
            }
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', bootApp);
        } else {
            bootApp();
        }

    })();
    </script>
</body>
</html>"""

def generate_dashboard_html(config_js_code, page_title):
    return TEMPLATE.replace('__PAGE_TITLE__', page_title).replace('__DASHBOARD_CONFIG_CODE__', config_js_code)
