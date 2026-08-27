"""Single-source HTML, CSS, and content renderer for explanation dialogs."""

EXPLANATION_TRIGGER_ICON = r'''<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>'''

EXPLANATION_DIALOG_CSS = r"""
        .chart-explain-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 22px;
            height: 22px;
            border-radius: 6px;
            border: 1px solid #E2E8F0;
            background: #F8FAFC;
            color: #64748B;
            cursor: pointer;
            padding: 0;
            line-height: 1;
            transition: all .2s cubic-bezier(0.16, 1, 0.3, 1);
            flex-shrink: 0;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
        }
        .chart-explain-btn svg { stroke: #64748B; transition: stroke .2s ease; }
        .chart-explain-btn:hover {
            background: #123B5D;
            border-color: #123B5D;
            color: #FFFFFF;
            transform: scale(1.12);
            box-shadow: 0 3px 8px rgba(18, 59, 93, 0.2);
        }
        .chart-explain-btn:hover svg { stroke: #FFFFFF; }
        .chart-explain-btn:active { transform: scale(0.95); }
        dialog.explanation-dialog {
            width: min(720px, calc(100vw - 32px));
            max-width: 720px;
            margin: auto;
            background: #FFFFFF;
            color: #17212B;
            border: 1px solid #CBD5E1;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 25px 50px -12px rgba(18, 59, 93, 0.25);
            padding: 0;
            max-height: 85vh;
        }
        dialog.explanation-dialog::backdrop {
            background: rgba(11, 42, 66, 0.45);
            backdrop-filter: blur(4px);
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
            grid-template-columns: repeat(2, minmax(0, 1fr));
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
        @media (max-width: 560px) {
            .exp-axis-grid { grid-template-columns: 1fr; }
        }
"""

EXPLANATION_DIALOG_SHELL = '<dialog id="app-explain-dialog" class="explanation-dialog"></dialog>'

EXPLANATION_DIALOG_RENDERER_JS = r"""
        function renderSharedExplanationDialogContent(explanation = {}) {
            const title = explanation.title || '图表与指标说明';
            const overview = explanation.overview || '该图表呈现业务多维经营分析数据，辅助管理层洞察关键业务特征。';
            const type = explanation.type || '分析图表';
            const period = explanation.period || '报告周期';
            const comparison = explanation.comparison || '按业务统一口径';
            const structure = explanation.structure || {};
            const xAxis = structure.xAxis || { name: '分析维度', meaning: '业务时间或分类维度', range: '标准化范围' };
            const yAxis = structure.yAxis || { name: '指标量纲', meaning: '绝对数值或百分比', range: '自适应区间' };
            const series = Array.isArray(structure.series) ? structure.series : [];
            const metrics = Array.isArray(explanation.metrics) && explanation.metrics.length
                ? explanation.metrics
                : [{ name: title, definition: overview, formula: '标准业务核算公式', rule: '遵循统一业务核算与数据治理口径。' }];

            return `
                <header class="exp-dialog-topbar">
                    <div class="flex items-center gap-2.5 min-w-0">
                        <span class="w-6 h-6 rounded-md bg-blue-50 text-[#123B5D] flex items-center justify-center flex-shrink-0">
                            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
                        </span>
                        <h3 class="text-sm font-bold text-[#0B2A42] truncate">${title}</h3>
                    </div>
                    <button id="closeExplainModalBtn" type="button" class="dialog-close w-7 h-7 rounded-md flex items-center justify-center text-slate-400 hover:bg-slate-100 hover:text-slate-700 cursor-pointer transition-colors" aria-label="关闭">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                    </button>
                </header>
                <div class="exp-dialog-body custom-scrollbar">
                    <div class="exp-overview-box">
                        <p class="text-xs text-slate-600 leading-relaxed m-0">${overview}</p>
                        <div class="exp-specs-strip">
                            <span class="exp-spec-badge"><strong class="text-slate-400 font-medium mr-1">图表类型:</strong>${type}</span>
                            <span class="exp-spec-badge"><strong class="text-slate-400 font-medium mr-1">统计周期:</strong>${period}</span>
                            <span class="exp-spec-badge"><strong class="text-slate-400 font-medium mr-1">对比基准:</strong>${comparison}</span>
                        </div>
                    </div>
                    <div class="border border-slate-200 rounded-lg p-3 bg-white space-y-2">
                        <div class="text-xs font-bold text-[#123B5D] flex items-center gap-1.5">
                            <svg class="w-4 h-4 inline-block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.9a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/></svg>
                            <span>坐标系维度与数据序列架构</span>
                        </div>
                        <div class="exp-axis-grid">
                            <div class="exp-axis-cell">
                                <div class="font-bold text-[#0B2A42] mb-1">X 轴 · ${xAxis.name}</div>
                                <div class="text-slate-600 text-[11px]"><span class="text-slate-400 mr-1.5">业务含义:</span>${xAxis.meaning}</div>
                                <div class="text-slate-600 text-[11px]"><span class="text-slate-400 mr-1.5">数据粒度:</span>${xAxis.range || ''}</div>
                            </div>
                            <div class="exp-axis-cell">
                                <div class="font-bold text-[#0B2A42] mb-1">Y 轴 · ${yAxis.name}</div>
                                <div class="text-slate-600 text-[11px]"><span class="text-slate-400 mr-1.5">业务含义:</span>${yAxis.meaning}</div>
                                <div class="text-slate-600 text-[11px]"><span class="text-slate-400 mr-1.5">量纲刻度:</span>${yAxis.range || ''}</div>
                            </div>
                        </div>
                        ${series.length ? `
                            <div class="flex flex-wrap gap-2 pt-1">
                                ${series.map(item => `
                                    <div class="inline-flex items-center gap-1 text-[11px] bg-slate-50 border border-slate-200 px-2 py-0.5 rounded">
                                        <span class="w-1.5 h-1.5 rounded-full bg-[#123B5D]"></span>
                                        <span class="font-semibold text-slate-700">${item.name}</span>
                                        <span class="text-slate-400">(${item.desc || ''})</span>
                                    </div>
                                `).join('')}
                            </div>
                        ` : ''}
                    </div>
                    <div class="space-y-2">
                        <div class="text-xs font-bold text-[#123B5D] flex items-center gap-1.5">
                            <svg class="w-4 h-4 inline-block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="16" height="20" x="4" y="2" rx="2"/><line x1="8" x2="16" y1="6" y2="6"/><line x1="16" x2="16" y1="14" y2="18"/><path d="M16 10h.01"/><path d="M12 10h.01"/><path d="M8 10h.01"/><path d="M12 14h.01"/><path d="M8 14h.01"/><path d="M12 18h.01"/><path d="M8 18h.01"/></svg>
                            <span>核心指标业务口径与数学公式</span>
                        </div>
                        <div class="space-y-2">
                            ${metrics.map(metric => `
                                <div class="exp-metric-card space-y-1.5">
                                    <div class="text-xs font-bold text-[#0B2A42]">${metric.name}</div>
                                    <div class="text-xs flex items-baseline gap-2"><span class="text-slate-400 w-16 shrink-0 text-[11px]">业务定义</span><span class="text-slate-700 leading-relaxed">${metric.definition}</span></div>
                                    <div class="text-xs flex items-baseline gap-2"><span class="text-slate-400 w-16 shrink-0 text-[11px]">计算公式</span><span class="text-slate-700"><code class="exp-formula">${metric.formula}</code></span></div>
                                    ${metric.rule ? `<div class="text-xs flex items-baseline gap-2"><span class="text-slate-400 w-16 shrink-0 text-[11px]">判定规则</span><span class="text-slate-600 text-[11.5px] leading-relaxed">${metric.rule}</span></div>` : ''}
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            `;
        }
"""
