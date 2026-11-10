// Migrated from aefb7e857663a42a6bb426f8b5ba3eca48cb950e; business data comes through props.
import type { ChartDefinition } from "./types";
const definition: ChartDefinition = {
  code: "f01",
  optionBuilder: (d: any, gran: any, tokens: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const seriesLabel = (presentation.seriesLabels || ["数值"])[0];
    const tooltipLabel = (presentation.tooltipValueLabels || [seriesLabel])[0];
    const unit = (presentation.units || [cfg.unit || ""])[0];
    return {
      tooltip: {
        trigger: "item",
        backgroundColor: "rgba(255, 255, 255, 0.98)",
        borderColor: tokens.palette.rule,
        borderWidth: 1,
        padding: [8, 12],
        extraCssText:
          "box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;",
        formatter: (params: any) =>
          `<div class="font-bold text-primary-strong mb-1">${params.name}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">${tooltipLabel}:</span><span class="font-mono font-bold text-primary">${params.value}${unit ? ` ${unit}` : ""} (${params.percent}%)</span></div>`,
      },
      series: [
        {
          type: "funnel",
          left: "12%",
          width: "76%",
          top: 25,
          bottom: 25,
          gap: 3,
          name: seriesLabel,
          label: {
            show: true,
            position: "inside",
            formatter: (params: any) =>
              `${params.name}\n${params.value}${unit ? ` ${unit}` : ""} (${params.percent}%)`,
            color: "#FFF",
            fontSize: 11,
            fontWeight: 600,
          },
          data: d.stages,
        },
      ],
    };
  },
  tableDataExtractor: (d: any, gran: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const seriesLabel = (presentation.seriesLabels || ["数值"])[0];
    const unit = (presentation.units || [cfg.unit || ""])[0];
    const labels = presentation.labels || {};
    const baselineIndex =
      (presentation.derivedMetricRules || {}).baselineIndex || 0;
    const baseline = d.stages[baselineIndex]
      ? d.stages[baselineIndex].value
      : 0;
    return {
      headers: presentation.tableHeaders || [
        labels.stageHeader || "阶段",
        `${seriesLabel}${unit ? ` (${unit})` : ""}`,
        labels.ratioHeader || "总体占比",
      ],
      rows: d.stages.map((s: any) => [
        s.name,
        `${s.value}${unit ? ` ${unit}` : ""}`,
        `${baseline ? ((s.value / baseline) * 100).toFixed(1) : "0.0"}%`,
      ]),
    };
  },
};
export default definition;
