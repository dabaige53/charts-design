#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
McKinsey-Grade Frontend Component & Chart Generator (咨询级前端组件生成引擎)
=============================================================================
Author: Executive Charts Skill Suite
Description:
    Generates standalone, McKinsey-grade interactive frontend components:
    1. Chart Cards: 52 taxonomy charts with 5+1 toolbar (granularity, table toggle, CSV, PNG copy, fullscreen, info dialog)
    2. Data Tables: Interactive pivot tables with sorting, nowrap scroll, cell copy, CSV export
    3. Business Explanation Modal: Complete Overview, specs, coordinate architecture, and mathematical formulas
=============================================================================
"""

import os
import sys
import json
import argparse
import subprocess

# Add local path for modular imports
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from core.chart_catalog import ALL_CHARTS
from core.chart_builders import CHARTS_JS_DEFINITIONS
ALL_CHART_BUILDERS = {**CHARTS_JS_DEFINITIONS, **ALL_CHARTS}
from core.explanations import CHART_EXPLANATIONS

CATEGORY_MAP = {
    'c': '对比与排名',
    't': '趋势与时序',
    'k': '构成与占比',
    'd': '分布与离散',
    'r': '关系与相关',
    'f': '流程与转化',
    'fn': '财务与归因',
    'm': '监控与绩效'
}

STANDALONE_CHART_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__TITLE__ - 麦肯锡咨询级图表组件</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
    <!-- Apache ECharts 5.5.0 CDN -->
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
    <style>
        :root {
            --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            --font-mono: 'JetBrains Mono', 'Fira Code', Menlo, Monaco, Consolas, monospace;
        }
        body {
            font-family: var(--font-sans);
            background-color: #F8FAFC;
            color: #0F172A;
            margin: 0;
            padding: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            box-sizing: border-box;
        }
        .chart-standalone-card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            box-shadow: 0 4px 20px -2px rgba(18, 59, 93, 0.06);
            width: 100%;
            max-width: __CARD_WIDTH__;
            padding: 24px;
            position: relative;
            transition: box-shadow 0.2s ease, transform 0.2s ease;
        }
        .chart-action-btn {
            height: 28px;
            padding: 0 8px;
            border-radius: 6px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            font-size: 11px;
            font-weight: 600;
            color: #64748B;
            border: 1px solid #E2E8F0;
            background: #FFFFFF;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .chart-action-btn:hover {
            background-color: #F1F5F9;
            color: #123B5D;
            border-color: #CBD5E1;
        }
        .chart-action-btn.icon-only {
            width: 28px;
            padding: 0;
        }
        .explanation-dialog {
            border: none;
            border-radius: 12px;
            padding: 0;
            width: 90vw;
            max-width: 640px;
            box-shadow: 0 20px 45px -10px rgba(11, 42, 66, 0.28);
            background: #FFFFFF;
        }
        .explanation-dialog::backdrop {
            background: rgba(11, 42, 66, 0.45);
            backdrop-filter: blur(4px);
        }
        .exp-dialog-topbar {
            padding: 14px 18px;
            border-bottom: 1px solid #E2E8F0;
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: #F8FAFC;
        }
        .exp-dialog-body {
            padding: 18px;
            max-height: 70vh;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }
        .exp-overview-box {
            background: #F1F5F9;
            border-left: 3px solid #123B5D;
            padding: 10px 14px;
            border-radius: 4px;
        }
        .exp-specs-strip {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 8px;
        }
        .exp-spec-badge {
            font-size: 11px;
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            padding: 2px 8px;
            border-radius: 4px;
            color: #334155;
        }
        .exp-axis-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 6px;
        }
        .exp-axis-cell {
            background: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 8px 10px;
        }
        .exp-formula {
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: var(--font-mono);
            font-size: 11px;
            color: #123B5D;
        }
        .toast-popup {
            position: fixed;
            bottom: 24px;
            left: 50%;
            transform: translateX(-50%);
            background: #0B2A42;
            color: #FFFFFF;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 500;
            z-index: 9999;
            opacity: 0;
            transition: opacity 0.2s ease;
            pointer-events: none;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
        }
        .toast-popup.show {
            opacity: 1;
        }
        .custom-scrollbar::-webkit-scrollbar {
            height: 6px;
            width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
            background: #F1F5F9;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
            background: #CBD5E1;
            border-radius: 3px;
        }
    </style>
</head>
<body>

    <div class="chart-standalone-card" id="cardContainer">
        <!-- Card Header (No Icon, Pure Typography) -->
        <div class="card-header-wrap flex flex-wrap items-start justify-between gap-3 mb-4 pb-3 border-b border-slate-100">
            <div class="min-w-0 max-w-[65%]">
                <div class="flex items-center gap-2">
                    <h3 class="text-sm font-bold text-[#0B2A42] tracking-tight truncate">__TITLE__</h3>
                    <span class="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-100 text-slate-600 border border-slate-200">__CODE__</span>
                </div>
                <p class="text-xs text-[#52606D] mt-0.5 leading-relaxed">__SUBTITLE__</p>
            </div>

            <!-- Standard 5+1 Interactive Toolbar -->
            <div class="flex items-center gap-1.5 flex-shrink-0">
                <!-- 1. Granularity Toggle -->
                <button type="button" class="chart-action-btn" id="granularityBtn" onclick="toggleGranularity()" title="切换时间统计粒度 (月度/季度)">
                    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                    <span id="granularityLabel">月度</span>
                </button>
                <!-- 2. Chart / Table Toggle -->
                <button type="button" class="chart-action-btn" id="viewToggleBtn" onclick="toggleView()" title="一键切换图表/数据透视表视图">
                    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/><path d="M15 3v18"/></svg>
                    <span id="viewToggleLabel">转表格</span>
                </button>
                <!-- 3. Export CSV (with BOM) -->
                <button type="button" class="chart-action-btn icon-only" onclick="exportCSV()" title="一键导出 CSV / Excel (UTF-8 BOM 防乱码)">
                    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
                </button>
                <!-- 4. Copy High-Res PNG -->
                <button type="button" class="chart-action-btn icon-only" onclick="copyPNG()" title="复制 2x 高清 PNG 图片 (直接粘贴入 PPT)">
                    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
                </button>
                <!-- 5. Fullscreen Focus -->
                <button type="button" class="chart-action-btn icon-only" onclick="toggleFullscreen()" title="全屏沉浸研判 (按 Esc 退出)">
                    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/></svg>
                </button>
                <!-- 6. Explanation Dialog (i) -->
                <button type="button" class="chart-action-btn icon-only" onclick="openExplanation()" title="业务定义、数学公式与判定基准 (i)">
                    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
                </button>
            </div>
        </div>

        <!-- Body: Chart Container & Table Pane -->
        <div class="relative w-full h-[__CHART_HEIGHT__px]" id="chartBodyContainer">
            <div id="chart-main" class="w-full h-full"></div>
            <div id="table-main" class="hidden w-full h-full overflow-auto custom-scrollbar bg-white rounded border border-slate-100"></div>
        </div>
    </div>

    <!-- Toast Notification -->
    <div id="toast" class="toast-popup">已复制到剪贴板</div>

    <!-- Explanation Dialog Modal -->
    <dialog id="explainDialog" class="explanation-dialog">
        <header class="exp-dialog-topbar">
            <div class="flex items-center gap-2.5 min-w-0">
                <span class="w-6 h-6 rounded-md bg-blue-50 text-[#123B5D] flex items-center justify-center flex-shrink-0">
                    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
                </span>
                <h3 class="text-sm font-bold text-[#0B2A42] truncate" id="dialogTitle">__TITLE__</h3>
            </div>
            <button onclick="closeExplanation()" class="w-7 h-7 rounded-md flex items-center justify-center text-slate-400 hover:bg-slate-100 hover:text-slate-700 cursor-pointer transition-colors" aria-label="关闭">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
        </header>
        <div class="exp-dialog-body" id="dialogBody"></div>
        <div class="p-3 bg-slate-50 border-t border-slate-200 flex justify-end">
            <button onclick="closeExplanation()" type="button" class="px-4 py-1.5 bg-[#123B5D] text-white text-xs font-semibold rounded-md hover:bg-[#0B2A42] transition-colors cursor-pointer shadow-xs">我知道了</button>
        </div>
    </dialog>

    <!-- Core Script -->
    <script>
        const TOKENS = {
            palette: {
                primary: '#123B5D',        // 旗舰深海蓝 (主序列/核心强调)
                primaryStrong: '#0B2A42',  // 墨蓝黑 (高对比主标题/关键标签)
                primarySoft: '#DCE8F0',    // 冰川淡蓝 (辅助对比/背景底槽)
                secondary: '#2C6485',      // 钢蓝 (次级对比序列)
                tertiary: '#628EA8',       // 浅灰蓝 (第三对比序列)
                slate: '#8C9DAE',          // 雾板岩灰 (第四对比序列)
                ink: '#0F172A',            // 炭黑正文
                inkMuted: '#52606D',       // 板岩深灰 (副标题/坐标刻度)
                inkSubtle: '#7B8794',      // 板岩淡灰 (注脚/量纲)
                positive: '#2F6B55',       // 咨询墨绿 (正向增长/达标/盈利)
                negative: '#A4453C',       // 咨询绯红 (负向承压/收缩/预警)
                attention: '#9A6A18',      // 咨询琥珀金 (重点关注/待研判)
                canvas: '#FFFFFF',
                surfaceGround: '#F8FAFC',
                gridline: '#E2E8F0',
                rule: '#CBD5E1',
                categorical: ['#123B5D', '#2C6485', '#628EA8', '#8C9DAE', '#9A6A18', '#A4453C', '#2F6B55', '#BDD0DC']
            },
            commonOption: {
                color: ['#123B5D', '#2C6485', '#628EA8', '#8C9DAE', '#9A6A18', '#A4453C', '#2F6B55', '#BDD0DC'],
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

        const chartBuilderFunc = __CHART_CONFIG_JS__;
        const explanationData = __EXPLANATION_JSON__;

        let chartInstance = null;
        let isTableView = false;
        let currentGranularity = 'month';
        let currentSortCol = null;
        let currentSortAsc = true;

        function initChart() {
            const chartDom = document.getElementById('chart-main');
            chartInstance = echarts.init(chartDom);
            const chartConfig = chartBuilderFunc(TOKENS);
            chartInstance.setOption(chartConfig.option);

            window.addEventListener('resize', () => {
                if (chartInstance) chartInstance.resize();
            });
        }

        function toggleGranularity() {
            currentGranularity = (currentGranularity === 'month') ? 'quarter' : 'month';
            document.getElementById('granularityLabel').textContent = (currentGranularity === 'month') ? '月度' : '季度';
            
            const chartConfig = chartBuilderFunc(TOKENS);
            if (chartConfig.granularityHandler) {
                const opt = chartConfig.granularityHandler(currentGranularity);
                chartInstance.setOption(opt, true);
            } else {
                showToast(`已切换至${currentGranularity === 'month' ? '月度' : '季度'}粒度统计`);
            }
            if (isTableView) renderTable();
        }

        function toggleView() {
            const chartEl = document.getElementById('chart-main');
            const tableEl = document.getElementById('table-main');
            const labelEl = document.getElementById('viewToggleLabel');
            isTableView = !isTableView;

            if (isTableView) {
                chartEl.classList.add('hidden');
                tableEl.classList.remove('hidden');
                labelEl.textContent = '转图表';
                renderTable();
            } else {
                tableEl.classList.add('hidden');
                chartEl.classList.remove('hidden');
                labelEl.textContent = '转表格';
                chartInstance.resize();
            }
        }

        function renderTable() {
            const tableEl = document.getElementById('table-main');
            const chartConfig = chartBuilderFunc(TOKENS);
            if (!chartConfig.tableDataExtractor) {
                tableEl.innerHTML = '<div class="p-8 text-center text-xs text-slate-400">当前图表暂无结构化表格数据</div>';
                return;
            }
            let data = chartConfig.tableDataExtractor(chartConfig.data);
            let headers = [...data.headers];
            let rows = [...data.rows];

            if (currentSortCol !== null) {
                rows.sort((a, b) => {
                    let vA = a[currentSortCol];
                    let vB = b[currentSortCol];
                    let nA = parseFloat(String(vA).replace(/[^0-9.-]/g, ''));
                    let nB = parseFloat(String(vB).replace(/[^0-9.-]/g, ''));
                    if (!isNaN(nA) && !isNaN(nB)) {
                        return currentSortAsc ? nA - nB : nB - nA;
                    }
                    return currentSortAsc ? String(vA).localeCompare(String(vB)) : String(vB).localeCompare(String(vA));
                });
            }

            tableEl.innerHTML = `
                <table class="w-full text-xs text-left border-collapse">
                    <thead class="bg-slate-50 text-[#0B2A42] font-bold border-b border-slate-200 sticky top-0 z-10">
                        <tr>
                            ${headers.map((h, idx) => `
                                <th class="px-3 py-2 border-r border-slate-200 last:border-0 cursor-pointer hover:bg-slate-100 whitespace-nowrap select-none" onclick="sortTable(${idx})">
                                    <div class="flex items-center justify-between gap-2">
                                        <span>${h}</span>
                                        <span class="text-[10px] text-slate-400">${currentSortCol === idx ? (currentSortAsc ? '▲' : '▼') : '⇅'}</span>
                                    </div>
                                </th>
                            `).join('')}
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 text-slate-700 font-mono text-[11px]">
                        ${rows.map(row => `
                            <tr class="hover:bg-blue-50/50 transition-colors">
                                ${row.map((cell, cIdx) => `
                                    <td class="px-3 py-2 border-r border-slate-100 last:border-0 whitespace-nowrap cursor-pointer hover:text-[#123B5D] hover:font-bold" onclick="copyCellText('${String(cell).replace(/'/g, "\\'")}')" title="点击复制单元格">
                                        ${cell}
                                    </td>
                                `).join('')}
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }

        function sortTable(colIdx) {
            if (currentSortCol === colIdx) {
                currentSortAsc = !currentSortAsc;
            } else {
                currentSortCol = colIdx;
                currentSortAsc = true;
            }
            renderTable();
        }

        function copyCellText(text) {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(() => showToast(`已复制: ${text}`));
            }
        }

        function exportCSV() {
            const chartConfig = chartBuilderFunc(TOKENS);
            if (!chartConfig.tableDataExtractor) return;
            const data = chartConfig.tableDataExtractor(chartConfig.data);
            let csv = '\\uFEFF' + data.headers.join(',') + '\\n';
            data.rows.forEach(r => {
                csv += r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',') + '\\n';
            });
            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${chartConfig.title || '图表数据'}_明细.csv`;
            a.click();
            URL.revokeObjectURL(url);
            showToast('已开始下载 CSV 数据明细 (带 UTF-8 BOM 防乱码)');
        }

        function copyPNG() {
            if (!chartInstance) return;
            const url = chartInstance.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#FFFFFF' });
            fetch(url).then(res => res.blob()).then(blob => {
                if (navigator.clipboard && navigator.clipboard.write) {
                    navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]).then(() => showToast('已成功复制 2x 高清图表图片至剪贴板！'));
                } else {
                    showToast('当前浏览器环境不支持直接写入图片剪贴板');
                }
            });
        }

        function toggleFullscreen() {
            const card = document.getElementById('cardContainer');
            if (!document.fullscreenElement) {
                card.requestFullscreen?.();
            } else {
                document.exitFullscreen?.();
            }
        }

        function openExplanation() {
            const dialog = document.getElementById('explainDialog');
            const body = document.getElementById('dialogBody');
            const exp = explanationData;

            let html = `
                <div class="exp-overview-box">
                    <p class="text-xs text-slate-600 leading-relaxed m-0">${exp.overview || "标准高管咨询级业务分析图表"}</p>
                    <div class="exp-specs-strip">
                        <span class="exp-spec-badge"><strong>类型:</strong> ${exp.type || "分析图表"}</span>
                        <span class="exp-spec-badge"><strong>周期:</strong> ${exp.period || "考核周期"}</span>
                        <span class="exp-spec-badge"><strong>基准:</strong> ${exp.comparison || "管理会计口径"}</span>
                    </div>
                </div>
            `;

            if (exp.structure && exp.structure.xAxis && exp.structure.yAxis) {
                html += `
                    <div class="border border-slate-200 rounded-lg p-3 bg-white space-y-2">
                        <div class="text-xs font-bold text-[#123B5D]">📐 坐标系维度与数据序列架构</div>
                        <div class="exp-axis-grid">
                            <div class="exp-axis-cell">
                                <div class="font-bold text-[#0B2A42] text-xs">X 轴 · ${exp.structure.xAxis.name}</div>
                                <div class="text-[11px] text-slate-500 mt-1">${exp.structure.xAxis.meaning}</div>
                            </div>
                            <div class="exp-axis-cell">
                                <div class="font-bold text-[#0B2A42] text-xs">Y 轴 · ${exp.structure.yAxis.name}</div>
                                <div class="text-[11px] text-slate-500 mt-1">${exp.structure.yAxis.meaning}</div>
                            </div>
                        </div>
                    </div>
                `;
            }

            if (exp.structure && exp.structure.series && exp.structure.series.length) {
                html += `
                    <div class="border border-slate-200 rounded-lg p-3 bg-white space-y-2">
                        <div class="text-xs font-bold text-[#123B5D]">📊 数据序列映射</div>
                        <div class="flex flex-wrap gap-2">
                            ${exp.structure.series.map(s => `
                                <span class="px-2 py-1 bg-slate-50 border border-slate-200 rounded text-[11px] text-slate-700">
                                    <span class="font-bold text-[#0B2A42]">● ${s.name}</span> <span class="text-slate-400">(${s.desc || ""})</span>
                                </span>
                            `).join('')}
                        </div>
                    </div>
                `;
            }

            if (exp.metrics && exp.metrics.length) {
                html += `
                    <div class="space-y-2">
                        <div class="text-xs font-bold text-[#123B5D]">📐 核心指标业务口径与数学公式</div>
                        ${exp.metrics.map(m => `
                            <div class="exp-metric-card space-y-1.5 p-3 bg-[#F8FAFC] border border-slate-200 rounded-lg">
                                <div class="font-bold text-xs text-[#0B2A42]">${m.name}</div>
                                <div class="text-xs text-slate-600 flex items-start gap-2">
                                    <span class="text-slate-400 whitespace-nowrap">业务定义</span>
                                    <span>${m.definition}</span>
                                </div>
                                <div class="text-xs flex items-center gap-2">
                                    <span class="text-slate-400 whitespace-nowrap">计算公式</span>
                                    <code class="exp-formula px-2 py-0.5 bg-white border border-slate-200 rounded font-mono text-[11px] text-[#123B5D]">${m.formula}</code>
                                </div>
                                ${m.rule ? `
                                    <div class="text-xs text-slate-600 flex items-start gap-2">
                                        <span class="text-slate-400 whitespace-nowrap">判定规则</span>
                                        <span>${m.rule}</span>
                                    </div>
                                ` : ''}
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            body.innerHTML = html;
            dialog.showModal();
        }

        function closeExplanation() {
            document.getElementById('explainDialog').close();
        }

        function showToast(msg) {
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.classList.add('show');
            setTimeout(() => t.classList.remove('show'), 2200);
        }

        document.addEventListener('DOMContentLoaded', initChart);
    </script>
</body>
</html>
"""

def generate_standalone_chart(code, output_path=None, custom_title=None, width="780px", height=340, auto_open=False):
    """Generates a standalone McKinsey-grade HTML chart file with 5+1 toolbar."""
    if code not in ALL_CHART_BUILDERS:
        raise ValueError(f"Chart code '{code}' not found in catalog! Available: {list(ALL_CHART_BUILDERS.keys())}")

    builder_js = ALL_CHART_BUILDERS[code]
    exp = CHART_EXPLANATIONS.get(code, {
        "title": custom_title or f"图表 {code.upper()}",
        "overview": "标准高管咨询级可视化图表",
        "type": "分析图表",
        "period": "考核期",
        "comparison": "管理口径"
    })

    title = custom_title or exp.get("title", f"图表 {code.upper()}")
    subtitle = exp.get("overview", "")

    html = STANDALONE_CHART_TEMPLATE
    html = html.replace('__CODE__', code.upper())
    html = html.replace('__TITLE__', title)
    html = html.replace('__SUBTITLE__', subtitle)
    html = html.replace('__CARD_WIDTH__', str(width))
    html = html.replace('__CHART_HEIGHT__', str(height))
    html = html.replace('__CHART_CONFIG_JS__', builder_js)
    html = html.replace('__EXPLANATION_JSON__', json.dumps(exp, ensure_ascii=False))

    if not output_path:
        output_path = f"./chart_{code}.html"

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Generated standalone chart '{code.upper()}' -> {output_path} ({len(html)} bytes)")

    if auto_open:
        subprocess.run(["open", output_path])

    return output_path

def list_all_charts():
    """Prints a formatted index of all 52 charts."""
    print("=" * 80)
    print("McKinsey-Grade Executive Chart Taxonomy (52 Full Spectrum)")
    print("=" * 80)
    current_prefix = ""
    for code, js in sorted(ALL_CHART_BUILDERS.items()):
        prefix = code[:2] if code.startswith('fn') else code[0]
        if prefix != current_prefix:
            current_prefix = prefix
            print(f"\n{CATEGORY_MAP.get(prefix, 'Other Category')}:")
        exp = CHART_EXPLANATIONS.get(code, {})
        title = exp.get('title', '标准业务图表')
        chart_type = exp.get('type', 'ECharts')
        print(f"  • [{code.upper():<5}] {title:<36} ({chart_type})")
    print("=" * 80)


def generate_batch_charts(codes_str, output_dir="./dist/charts", auto_open=False):
    """Generates multiple standalone charts in batch for AI inspection and selection."""
    codes = [c.strip().lower() for c in codes_str.split(',') if c.strip()]
    os.makedirs(output_dir, exist_ok=True)
    generated = []
    print(f"📦 Batch generating {len(codes)} chart components into: {output_dir}")
    for code in codes:
        if code in ALL_CHART_BUILDERS:
            out_file = os.path.join(output_dir, f"chart_{code}.html")
            generate_standalone_chart(code, output_path=out_file, auto_open=False)
            generated.append(out_file)
        else:
            print(f"⚠️ Warning: Chart code '{code}' not found in 52 taxonomy, skipping.")
    print(f"✅ Successfully generated {len(generated)} charts in batch.")
    if auto_open and generated:
        subprocess.run(["open", generated[0]])
    return generated

def main():
    parser = argparse.ArgumentParser(description="McKinsey-Grade Frontend Component & Chart Generator")
    parser.add_argument("--code", "-c", type=str, help="Chart taxonomy code (e.g. c01, t06, r01, fn01, m01)")
    parser.add_argument("--batch", "-b", type=str, help="Batch comma-separated chart codes (e.g. 'c01,t06,r01,k01')")
    parser.add_argument("--output", "-o", type=str, help="Target HTML output path (or output directory if --batch)")
    parser.add_argument("--output-dir", type=str, default="./dist/charts", help="Directory for batch generated charts")
    parser.add_argument("--title", "-t", type=str, help="Custom chart title")
    parser.add_argument("--list", "-l", action="store_true", help="List all 52 available chart codes")
    parser.add_argument("--open", action="store_true", help="Automatically open generated chart in browser")
    parser.add_argument("--snippet", action="store_true", help="Print raw JavaScript ECharts option snippet")

    args = parser.parse_args()

    if args.list:
        list_all_charts()
        return


    if args.batch:
        target_dir = args.output or args.output_dir
        generate_batch_charts(args.batch, output_dir=target_dir, auto_open=args.open)
        return

    if not args.code:
        parser.print_help()
        print("\nExample: python generate_chart.py --code c01 --output chart_c01.html --open")
        print("Batch Example: python generate_chart.py --batch 'c01,t06,r01,k01' --output-dir ./dist/charts/")
        return

    if args.snippet:
        if args.code in ALL_CHART_BUILDERS:
            print(f"// ECharts JS Option for [{args.code}]:\n" + ALL_CHART_BUILDERS[args.code])
        else:
            print(f"Error: {args.code} not found.")
        return

    generate_standalone_chart(
        code=args.code.lower(),
        output_path=args.output,
        custom_title=args.title,
        auto_open=args.open
    )

if __name__ == "__main__":
    main()
