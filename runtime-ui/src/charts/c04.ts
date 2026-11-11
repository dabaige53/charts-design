// Migrated from aefb7e857663a42a6bb426f8b5ba3eca48cb950e; business data comes through props.
import type { ChartDefinition } from "./types";
const definition: ChartDefinition = {
  code: "c04",
  optionBuilder: (d: any, gran: any, tokens: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabel = (presentation.seriesLabels || ["偏离值"])[0];
    const tooltipLabel = (presentation.tooltipValueLabels || [seriesLabel])[0];
    const unit = (presentation.units || [cfg.unit || ""])[0];
    return {
      ...tokens.commonOption,
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(255, 255, 255, 0.98)",
        borderColor: tokens.palette.rule,
        borderWidth: 1,
        padding: [8, 12],
        extraCssText:
          "box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;",
        formatter: (params: any) => {
          const val = params[0].value;
          return `<div class="font-bold text-primary-strong mb-1">${params[0].name}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">${tooltipLabel}:</span><span class="font-mono font-bold ${val >= 0 ? "text-positive" : "text-negative"}">${val >= 0 ? "+" : ""}${val}${unit ? ` ${unit}` : ""}</span></div>`;
        },
      },
      grid: { top: 38, bottom: 38, left: 10, right: 25, containLabel: true },
      xAxis: {
        type: "value",
        name: axisLabels.x || `${seriesLabel}${unit ? ` (${unit})` : ""}`,
        nameLocation: "middle",
        nameGap: 24,
        nameTextStyle: tokens.axisTitleStyleX,
        axisLabel: { formatter: (value: any) => `${value}${unit || ""}` },
        splitLine: { lineStyle: { color: tokens.palette.gridline } },
      },
      yAxis: {
        type: "category",
        inverse: true,
        name: axisLabels.y || "类别",
        nameLocation: "start",
        nameTextStyle: tokens.axisTitleStyleY,
        data: d.fleets,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "#94A3B8", width: 1.2 } },
        axisLabel: { color: "#0F172A", fontSize: 11, fontWeight: 700 },
      },
      series: [
        {
          name: seriesLabel,
          type: "bar",
          barMaxWidth: 28,
          barMinWidth: 4,
          data: d.deviations.map((val: any) => ({
            value: val,
            itemStyle: {
              color:
                val >= 0 ? tokens.palette.positive : tokens.palette.negative,
            },
          })),
          label: {
            show: true,
            position: "right",
            distance: 6,
            formatter: (params: any) =>
              `${params.value >= 0 ? "+" : ""}${params.value}${unit || ""}`,
            color: tokens.palette.ink,
            fontSize: 10,
            fontWeight: 600,
          },
        },
      ],
    };
  },
  tableDataExtractor: (d: any, gran: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabel = (presentation.seriesLabels || ["偏离值"])[0];
    const unit = (presentation.units || [cfg.unit || ""])[0];
    return {
      headers: presentation.tableHeaders || [
        axisLabels.y || "类别",
        `${seriesLabel}${unit ? ` (${unit})` : ""}`,
      ],
      rows: d.fleets.map((f: any, i: any) => [
        f,
        `${d.deviations[i]}${unit ? ` ${unit}` : ""}`,
      ]),
    };
  },
};
export default definition;
